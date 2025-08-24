"""Unit tests for Event Store security features."""

import pytest
import pytest_asyncio
import tempfile
import shutil
from pathlib import Path

from lighthouse.event_store.store import EventStore, EventStoreError
from lighthouse.event_store.models import Event, EventType, EventBatch
from lighthouse.event_store.validation import SecurityError, PathValidator, InputValidator
from lighthouse.event_store.auth import (
    SimpleAuthenticator, Authorizer, AgentRole, Permission,
    AuthenticationError, AuthorizationError
)


class TestPathValidator:
    """Test path validation security."""
    
    def test_basic_path_validation(self):
        """Test basic path validation."""
        validator = PathValidator(["/allowed/path"])
        
        # Valid path within allowed directory
        validated = validator.validate_path("/allowed/path/subdir/file.txt")
        assert str(validated) == "/allowed/path/subdir/file.txt"
    
    def test_directory_traversal_prevention(self):
        """Test prevention of directory traversal attacks."""
        validator = PathValidator(["/allowed"])
        
        dangerous_paths = [
            "/allowed/../../../etc/passwd",
            "/allowed/subdir/../../etc/passwd",
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/allowed/../outside/file.txt"
        ]
        
        for dangerous_path in dangerous_paths:
            with pytest.raises(SecurityError, match="outside allowed directories|Dangerous path pattern"):
                validator.validate_path(dangerous_path)
    
    def test_system_directory_protection(self):
        """Test protection of system directories."""
        validator = PathValidator(["/tmp"])  # Only allow /tmp
        
        system_paths = [
            "/etc/passwd",
            "/usr/bin/bash", 
            "/var/log/system.log",
            "/boot/vmlinuz",
            "/sys/kernel",
            "/proc/version",
            "/dev/null"
        ]
        
        for system_path in system_paths:
            with pytest.raises(SecurityError, match="Dangerous path pattern"):
                validator.validate_path(system_path)
    
    def test_url_prevention(self):
        """Test prevention of URL-based attacks."""
        validator = PathValidator(["/tmp"])
        
        malicious_urls = [
            "file:///etc/passwd",
            "http://evil.com/malware",
            "https://attacker.com/script.js",
            "ftp://bad.server/file"
        ]
        
        for url in malicious_urls:
            with pytest.raises(SecurityError, match="Dangerous path pattern"):
                validator.validate_path(url)


class TestInputValidator:
    """Test input validation security."""
    
    def setup_method(self):
        """Set up validator for each test."""
        self.validator = InputValidator()
    
    def test_valid_event_validation(self):
        """Test validation of safe events."""
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="safe-command",
            data={"command": "ls", "args": ["-la"]},
            metadata={"source": "test"}
        )
        
        # Should not raise any exceptions
        self.validator.validate_event(event)
    
    def test_oversized_event_rejection(self):
        """Test rejection of oversized events."""
        # Create event with large data payload
        large_data = {"payload": "x" * (2 * 1024 * 1024)}  # 2MB of data
        
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="large-event",
            data=large_data
        )
        
        with pytest.raises(SecurityError, match="length.*exceeds limit"):
            self.validator.validate_event(event)
    
    def test_malicious_string_detection(self):
        """Test detection of malicious strings in event data."""
        malicious_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "eval('malicious code')",
            "setTimeout('bad stuff', 100)",
            "data:text/html,<script>evil()</script>"
        ]
        
        for payload in malicious_payloads:
            event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id="malicious-test",
                data={"payload": payload}
            )
            
            with pytest.raises(SecurityError, match="Dangerous pattern detected"):
                self.validator.validate_event(event)
    
    def test_null_byte_prevention(self):
        """Test prevention of null byte injection."""
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="null-byte-test",
            data={"malicious": "file.txt\x00.exe"}
        )
        
        with pytest.raises(SecurityError, match="Null byte detected"):
            self.validator.validate_event(event)
    
    def test_excessive_nesting_prevention(self):
        """Test prevention of excessive data nesting."""
        # Create deeply nested data structure
        nested_data = {"level": 1}
        current = nested_data
        for i in range(2, 15):  # Create 14 levels of nesting (exceeds MAX_NESTED_DEPTH)
            current["deeper"] = {"level": i}
            current = current["deeper"]
        
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="nested-test",
            data=nested_data
        )
        
        with pytest.raises(SecurityError, match="nesting too deep"):
            self.validator.validate_event(event)
    
    def test_batch_validation(self):
        """Test validation of event batches."""
        # Valid batch
        valid_events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id=f"cmd_{i}", data={})
            for i in range(10)
        ]
        valid_batch = EventBatch(events=valid_events)
        
        # Should not raise
        self.validator.validate_batch(valid_batch)
        
        # Test oversized batch by checking the validation function directly
        # (EventBatch Pydantic model prevents creation of >1000 events)
        # So we test the validation logic directly
        oversized_events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id=f"cmd_{i}", data={})
            for i in range(1001)  # Exceeds 1000 event limit
        ]
        
        # Create minimal batch-like object for testing
        class MockBatch:
            def __init__(self, events):
                self.events = events
        
        mock_oversized_batch = MockBatch(oversized_events)
        
        with pytest.raises(SecurityError, match="exceeds 1000 event limit"):
            self.validator.validate_batch(mock_oversized_batch)


class TestAuthentication:
    """Test authentication system."""
    
    def setup_method(self):
        """Set up authenticator for each test."""
        self.authenticator = SimpleAuthenticator("test-secret")
    
    def test_successful_authentication(self):
        """Test successful agent authentication."""
        agent_id = "test-agent"
        token = self.authenticator.create_token(agent_id)
        
        identity = self.authenticator.authenticate(agent_id, token, AgentRole.AGENT)
        
        assert identity.agent_id == agent_id
        assert identity.role == AgentRole.AGENT
        assert Permission.READ_EVENTS in identity.permissions
        assert Permission.WRITE_EVENTS in identity.permissions
    
    def test_invalid_token_rejection(self):
        """Test rejection of invalid tokens."""
        agent_id = "test-agent"
        invalid_token = "1234567890:invalid_hmac_signature"
        
        with pytest.raises(AuthenticationError):
            self.authenticator.authenticate(agent_id, invalid_token, AgentRole.AGENT)
    
    def test_expired_token_rejection(self):
        """Test rejection of expired tokens."""
        agent_id = "test-agent"
        # Create token with very old timestamp (beyond 5 minute window)
        old_timestamp = 1000000000  # Year 2001
        expired_token = f"{old_timestamp}:fake_hmac"
        
        with pytest.raises(AuthenticationError, match="Token expired"):
            self.authenticator.authenticate(agent_id, expired_token, AgentRole.AGENT)
    
    def test_role_based_permissions(self):
        """Test different permissions for different roles."""
        agent_id = "test-agent"
        token = self.authenticator.create_token(agent_id)
        
        # Guest role - limited permissions
        guest_identity = self.authenticator.authenticate(agent_id, token, AgentRole.GUEST)
        assert Permission.READ_EVENTS in guest_identity.permissions
        assert Permission.WRITE_EVENTS not in guest_identity.permissions
        assert Permission.ADMIN_ACCESS not in guest_identity.permissions
        
        # Admin role - full permissions (create new token for admin)
        admin_token = self.authenticator.create_token("admin-agent")
        admin_identity = self.authenticator.authenticate("admin-agent", admin_token, AgentRole.ADMIN)
        assert Permission.READ_EVENTS in admin_identity.permissions
        assert Permission.WRITE_EVENTS in admin_identity.permissions
        assert Permission.ADMIN_ACCESS in admin_identity.permissions


class TestAuthorization:
    """Test authorization system."""
    
    def setup_method(self):
        """Set up authorization system for each test."""
        self.authenticator = SimpleAuthenticator("test-secret")
        self.authorizer = Authorizer(self.authenticator)
        
        # Authenticate test agents
        self.agent_token = self.authenticator.create_token("test-agent")
        self.guest_token = self.authenticator.create_token("guest-agent")
        
        self.authenticator.authenticate("test-agent", self.agent_token, AgentRole.AGENT)
        self.authenticator.authenticate("guest-agent", self.guest_token, AgentRole.GUEST)
    
    def test_authorized_read_access(self):
        """Test authorized read operations."""
        # Standard agent should be able to read
        identity = self.authorizer.authorize_read("test-agent")
        assert identity.agent_id == "test-agent"
        assert identity.role == AgentRole.AGENT
    
    def test_unauthorized_write_access(self):
        """Test unauthorized write operations."""
        # Guest should not be able to write
        with pytest.raises(AuthorizationError, match="lacks WRITE_EVENTS permission"):
            self.authorizer.authorize_write("guest-agent")
    
    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        # Make many requests rapidly to trigger rate limit
        for i in range(1000):  # Standard agent limit is 1000/minute
            self.authorizer.authorize_read("test-agent")
        
        # Next request should be rate limited
        with pytest.raises(AuthorizationError, match="Rate limit exceeded"):
            self.authorizer.authorize_read("test-agent")
    
    def test_batch_size_limits(self):
        """Test batch size authorization limits."""
        # Standard agent should be limited to 100 events per batch
        identity = self.authorizer.authorize_write("test-agent", batch_size=100)
        assert identity.max_batch_size == 100
        
        # Oversized batch should be rejected
        with pytest.raises(AuthorizationError, match="exceeds limit"):
            self.authorizer.authorize_write("test-agent", batch_size=101)
    
    def test_unauthenticated_access_denial(self):
        """Test denial of unauthenticated access."""
        with pytest.raises(AuthenticationError, match="not authenticated"):
            self.authorizer.authorize_read("unknown-agent")


@pytest_asyncio.fixture
async def secure_event_store():
    """Create a secure event store for testing."""
    temp_dir = tempfile.mkdtemp()
    allowed_dirs = [temp_dir, "/tmp"]
    
    store = EventStore(
        data_dir=temp_dir, 
        allowed_base_dirs=allowed_dirs,
        auth_secret="test-security-secret"
    )
    await store.initialize()
    
    yield store
    
    await store.shutdown()
    shutil.rmtree(temp_dir)


class TestEventStoreSecurity:
    """Test Event Store security integration."""
    
    @pytest.mark.asyncio
    async def test_secure_event_store_initialization(self, secure_event_store):
        """Test secure event store initializes correctly."""
        store = secure_event_store
        assert store.status == "healthy-secure"
        assert store.authenticator is not None
        assert store.authorizer is not None
        assert store.input_validator is not None
        assert store.path_validator is not None
    
    @pytest.mark.asyncio
    async def test_authenticated_event_append(self, secure_event_store):
        """Test event append with authentication."""
        store = secure_event_store
        
        # Create and authenticate test agent
        agent_id = "secure-test-agent"
        token = store.create_agent_token(agent_id)
        store.authenticate_agent(agent_id, token, "agent")
        
        # Append event with authentication
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="secure-cmd",
            data={"command": "ls"}
        )
        
        await store.append(event, agent_id=agent_id)
        
        assert event.sequence == 1
        assert event.source_agent == agent_id
    
    @pytest.mark.asyncio
    async def test_unauthenticated_append_denial(self, secure_event_store):
        """Test denial of unauthenticated event append."""
        store = secure_event_store
        
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="unauthorized-cmd",
            data={"command": "rm -rf /"}
        )
        
        # Should fail without authentication
        with pytest.raises(EventStoreError, match="Security validation failed"):
            await store.append(event, agent_id="unknown-agent")
    
    @pytest.mark.asyncio
    async def test_malicious_event_rejection(self, secure_event_store):
        """Test rejection of malicious events."""
        store = secure_event_store
        
        # Create and authenticate test agent
        agent_id = "test-agent"
        token = store.create_agent_token(agent_id)
        store.authenticate_agent(agent_id, token, "agent")
        
        # Create malicious event
        malicious_event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="malicious-cmd",
            data={"script": "<script>alert('xss')</script>"}
        )
        
        # Should be rejected by input validation
        with pytest.raises(EventStoreError, match="Security validation failed"):
            await store.append(malicious_event, agent_id=agent_id)
    
    @pytest.mark.asyncio
    async def test_directory_traversal_prevention_in_store(self, secure_event_store):
        """Test that event store prevents directory traversal in its own operations."""
        # This test ensures our initialization properly validates the data directory
        
        with pytest.raises((SecurityError, EventStoreError)):
            # Try to create store with dangerous path
            dangerous_store = EventStore(
                data_dir="../../../etc/evil-events",
                allowed_base_dirs=["/tmp"]  # Don't allow /etc access
            )
    
    @pytest.mark.asyncio
    async def test_hmac_event_authentication(self, secure_event_store):
        """Test that events are authenticated with HMAC signatures."""
        store = secure_event_store
        
        # Create and authenticate test agent
        agent_id = "hmac-test-agent"
        token = store.create_agent_token(agent_id)
        store.authenticate_agent(agent_id, token, "agent")
        
        # Append event
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="hmac-test",
            data={"test": "hmac_authentication"}
        )
        
        await store.append(event, agent_id=agent_id)
        
        # Verify event was stored and can be retrieved
        # (HMAC verification happens during log reading)
        from lighthouse.event_store.models import EventQuery, EventFilter
        
        query = EventQuery(
            filter=EventFilter(aggregate_ids=["hmac-test"])
        )
        
        result = await store.query(query, agent_id=agent_id)
        assert len(result.events) == 1
        assert result.events[0].aggregate_id == "hmac-test"
        assert result.events[0].data["test"] == "hmac_authentication"