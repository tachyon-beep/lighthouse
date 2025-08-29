"""Authentication and authorization for Event Store access."""

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from enum import Enum

from pydantic import BaseModel, Field


class Permission(str, Enum):
    """Event Store and system permissions."""
    # Event Store permissions
    READ_EVENTS = "events:read"
    WRITE_EVENTS = "events:write"
    QUERY_EVENTS = "events:query"
    ADMIN_ACCESS = "admin:access"
    HEALTH_CHECK = "health:check"
    
    # Expert coordination permissions
    EXPERT_COORDINATION = "expert:coordination"
    
    # Shadow Filesystem permissions (for Expert Agents via FUSE mount)
    SHADOW_READ = "shadow:read"        # Read from /mnt/lighthouse/project/
    SHADOW_WRITE = "shadow:write"      # Write to shadow filesystem
    SHADOW_ANNOTATE = "shadow:annotate"  # Add annotations to shadows
    
    # Direct Filesystem permissions (for Builder Agents ONLY)
    FILESYSTEM_READ = "filesystem:read"   # Direct filesystem read
    FILESYSTEM_WRITE = "filesystem:write" # Direct filesystem write
    FILESYSTEM_EXECUTE = "filesystem:execute" # Execute filesystem commands
    
    # Command execution permissions
    COMMAND_EXECUTION = "command:execute"
    COMMAND_VALIDATION = "command:validate"
    
    # System-level permissions
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_CONFIG = "system:config"
    
    # Specialized agent permissions
    BRIDGE_ACCESS = "bridge:access"
    CONTEXT_SHARING = "context:share"
    SESSION_MANAGEMENT = "session:manage"
    
    # Security and audit permissions
    AUDIT_ACCESS = "audit:access"
    SECURITY_REVIEW = "security:review"


class AgentRole(str, Enum):
    """Agent roles with different permission levels."""
    GUEST = "guest"                    # Read-only access to public events
    AGENT = "agent"                    # Standard agent permissions
    EXPERT_AGENT = "expert_agent"      # Enhanced permissions for specialized agents
    SYSTEM_AGENT = "system_agent"      # System-level agents
    ADMIN = "admin"                    # Full administrative access


class AgentIdentity(BaseModel):
    """Agent identity and authentication information."""
    
    agent_id: str = Field(..., min_length=1, max_length=64)
    agent_name: Optional[str] = Field(None, max_length=256)
    role: AgentRole
    permissions: Set[Permission] = Field(default_factory=set)
    
    # Session information
    session_id: Optional[str] = None
    authenticated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    
    # Agent-specific scopes
    allowed_aggregates: Set[str] = Field(default_factory=set)  # Aggregates this agent can access
    allowed_streams: Set[str] = Field(default_factory=set)     # Streams this agent can access
    
    # Rate limiting
    max_requests_per_minute: int = Field(default=1000)
    max_batch_size: int = Field(default=100)
    
    def is_expired(self) -> bool:
        """Check if authentication has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if agent has specific permission."""
        return permission in self.permissions
    
    def can_access_aggregate(self, aggregate_id: str) -> bool:
        """Check if agent can access specific aggregate."""
        if not self.allowed_aggregates:
            return True  # No restrictions
        return aggregate_id in self.allowed_aggregates
    
    def can_access_stream(self, stream_id: str) -> bool:
        """Check if agent can access specific stream."""
        if not self.allowed_streams:
            return True  # No restrictions
        return stream_id in self.allowed_streams


class AuthenticationError(Exception):
    """Authentication failure."""
    pass


class AuthorizationError(Exception):
    """Authorization failure."""
    pass


class SimpleAuthenticator:
    """Simple HMAC-based authenticator for Event Store access.
    
    This is a basic implementation for Phase 1. In production, this would
    be replaced with JWT tokens, mTLS, or other enterprise authentication.
    """
    
    def __init__(self, shared_secret: str = None):
        if shared_secret is None:
            shared_secret = os.environ.get('LIGHTHOUSE_AUTH_SECRET') or secrets.token_urlsafe(32)
        """Initialize authenticator with shared secret.
        
        Args:
            shared_secret: Secret key for HMAC authentication
        """
        self.shared_secret = shared_secret.encode('utf-8')
        self._authenticated_agents: Dict[str, AgentIdentity] = {}
        
        # Set up default role permissions
        self._setup_default_permissions()
    
    def _setup_default_permissions(self) -> None:
        """Set up default permissions for each role."""
        self.role_permissions = {
            AgentRole.GUEST: {
                Permission.READ_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.SHADOW_READ,  # Guests can only read shadow files via FUSE
            },
            AgentRole.AGENT: {  # Builder agents with direct filesystem access
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS,
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.FILESYSTEM_READ,   # Direct filesystem access
                Permission.FILESYSTEM_WRITE,  # Direct filesystem access
                Permission.FILESYSTEM_EXECUTE, # Can execute commands
                Permission.COMMAND_EXECUTION,
                Permission.COMMAND_VALIDATION,
                Permission.CONTEXT_SHARING,
            },
            AgentRole.EXPERT_AGENT: {  # Expert agents with shadow-only access
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS, 
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.SHADOW_READ,      # Shadow filesystem only
                Permission.SHADOW_WRITE,     # Shadow filesystem only
                Permission.SHADOW_ANNOTATE,  # Can annotate shadows
                Permission.COMMAND_VALIDATION,  # Can validate but not execute
                Permission.EXPERT_COORDINATION,
                Permission.CONTEXT_SHARING,
                Permission.SESSION_MANAGEMENT,
                Permission.BRIDGE_ACCESS,
                Permission.SECURITY_REVIEW,
            },
            AgentRole.SYSTEM_AGENT: {  # System agents need both shadow and filesystem
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS,
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.SHADOW_READ,       # Shadow access for coordination
                Permission.SHADOW_WRITE,
                Permission.SHADOW_ANNOTATE,
                Permission.FILESYSTEM_READ,   # Direct access for system tasks
                Permission.FILESYSTEM_WRITE,
                Permission.FILESYSTEM_EXECUTE,
                Permission.COMMAND_EXECUTION,
                Permission.COMMAND_VALIDATION,
                Permission.EXPERT_COORDINATION,
                Permission.CONTEXT_SHARING,
                Permission.SESSION_MANAGEMENT,
                Permission.BRIDGE_ACCESS,
                Permission.SYSTEM_CONFIG,
                Permission.AUDIT_ACCESS,
                Permission.ADMIN_ACCESS,
            },
            AgentRole.ADMIN: {  # Admins have all permissions
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS,
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.SHADOW_READ,
                Permission.SHADOW_WRITE,
                Permission.SHADOW_ANNOTATE,
                Permission.FILESYSTEM_READ,
                Permission.FILESYSTEM_WRITE,
                Permission.FILESYSTEM_EXECUTE,
                Permission.COMMAND_EXECUTION,
                Permission.COMMAND_VALIDATION,
                Permission.EXPERT_COORDINATION,
                Permission.CONTEXT_SHARING,
                Permission.SESSION_MANAGEMENT,
                Permission.BRIDGE_ACCESS,
                Permission.SYSTEM_ADMIN,
                Permission.SYSTEM_CONFIG,
                Permission.AUDIT_ACCESS,
                Permission.SECURITY_REVIEW,
                Permission.ADMIN_ACCESS,
            },
        }
    
    def authenticate(self, agent_id: str, token: str, role: AgentRole = AgentRole.AGENT) -> AgentIdentity:
        """Authenticate agent using cryptographically secure HMAC token.
        
        Args:
            agent_id: Unique agent identifier
            token: HMAC authentication token with format "nonce:timestamp:hmac"
            role: Agent role (defaults to standard agent)
            
        Returns:
            AgentIdentity for authenticated agent
            
        Raises:
            AuthenticationError: If authentication fails
        """
        if not agent_id or not token:
            raise AuthenticationError("Agent ID and token are required")
        
        # Secure token format: "nonce:timestamp:hmac_hex"
        # Nonce prevents replay attacks, timestamp prevents token reuse
        try:
            parts = token.split(':', 2)
            if len(parts) != 3:
                raise ValueError("Token must have 3 parts")
            nonce_hex, timestamp_str, hmac_hex = parts
            timestamp = int(timestamp_str)
            
            # Validate nonce format (must be hex-encoded bytes)
            if len(nonce_hex) != 32:  # 16 bytes = 32 hex chars
                raise ValueError("Invalid nonce length")
            nonce_bytes = bytes.fromhex(nonce_hex)
            
        except (ValueError, TypeError) as e:
            raise AuthenticationError(f"Invalid token format: {str(e)}")
        
        # Check if token is not too old (5 minute window)
        current_time = int(time.time())
        if abs(current_time - timestamp) > 300:  # 5 minutes
            raise AuthenticationError("Token expired or clock skew too large")
        
        # Verify HMAC using secure nonce + agent_id + timestamp
        expected_data = f"{agent_id}:{nonce_hex}:{timestamp}".encode('utf-8')
        expected_hmac = hmac.new(self.shared_secret, expected_data, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(hmac_hex, expected_hmac):
            raise AuthenticationError("Invalid authentication token")
        
        # Store nonce to prevent replay attacks (in production, use Redis/database)
        if not hasattr(self, '_used_nonces'):
            self._used_nonces = set()
        
        if nonce_hex in self._used_nonces:
            raise AuthenticationError("Token replay attack detected")
        
        self._used_nonces.add(nonce_hex)
        
        # Create agent identity
        permissions = self.role_permissions.get(role, set())
        
        identity = AgentIdentity(
            agent_id=agent_id,
            role=role,
            permissions=permissions,
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),  # 24 hour expiry
            max_requests_per_minute=self._get_rate_limit_for_role(role),
            max_batch_size=self._get_batch_limit_for_role(role)
        )
        
        # Store authenticated agent
        self._authenticated_agents[agent_id] = identity
        
        return identity
    
    def get_authenticated_agent(self, agent_id: str) -> Optional[AgentIdentity]:
        """Get authenticated agent identity.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            AgentIdentity if authenticated and not expired, None otherwise
        """
        identity = self._authenticated_agents.get(agent_id)
        if identity and not identity.is_expired():
            return identity
        
        # Remove expired identity
        if identity and identity.is_expired():
            del self._authenticated_agents[agent_id]
        
        return None
    
    def revoke_authentication(self, agent_id: str) -> None:
        """Revoke agent authentication.
        
        Args:
            agent_id: Agent identifier to revoke
        """
        if agent_id in self._authenticated_agents:
            del self._authenticated_agents[agent_id]
    
    def create_token(self, agent_id: str) -> str:
        """Create cryptographically secure authentication token for agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Secure HMAC authentication token with format "nonce:timestamp:hmac"
        """
        # Generate cryptographically secure 16-byte nonce
        nonce_bytes = secrets.token_bytes(16)
        nonce_hex = nonce_bytes.hex()
        timestamp = int(time.time())
        
        # Create HMAC with nonce + agent_id + timestamp
        data = f"{agent_id}:{nonce_hex}:{timestamp}".encode('utf-8')
        hmac_digest = hmac.new(self.shared_secret, data, hashlib.sha256).hexdigest()
        
        return f"{nonce_hex}:{timestamp}:{hmac_digest}"
    
    def _get_rate_limit_for_role(self, role: AgentRole) -> int:
        """Get rate limit for agent role."""
        limits = {
            AgentRole.GUEST: 100,
            AgentRole.AGENT: 1000,
            AgentRole.EXPERT_AGENT: 2000,
            AgentRole.SYSTEM_AGENT: 5000,
            AgentRole.ADMIN: 10000,
        }
        return limits.get(role, 1000)
    
    def _get_batch_limit_for_role(self, role: AgentRole) -> int:
        """Get batch size limit for agent role."""
        limits = {
            AgentRole.GUEST: 10,
            AgentRole.AGENT: 100,
            AgentRole.EXPERT_AGENT: 500,
            AgentRole.SYSTEM_AGENT: 1000,
            AgentRole.ADMIN: 1000,
        }
        return limits.get(role, 100)


class Authorizer:
    """Authorization manager for Event Store operations."""
    
    def __init__(self, authenticator: SimpleAuthenticator):
        """Initialize authorizer with authenticator.
        
        Args:
            authenticator: Authentication provider
        """
        self.authenticator = authenticator
        self._rate_limits: Dict[str, List[float]] = {}  # agent_id -> list of request timestamps
    
    def authorize_read(self, agent_id: str, aggregate_id: Optional[str] = None, 
                      stream_id: Optional[str] = None) -> AgentIdentity:
        """Authorize read operation.
        
        Args:
            agent_id: Agent requesting access
            aggregate_id: Optional aggregate being accessed
            stream_id: Optional stream being accessed
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        if not identity.has_permission(Permission.READ_EVENTS):
            raise AuthorizationError(f"Agent {agent_id} lacks READ_EVENTS permission")
        
        # Check aggregate access
        if aggregate_id and not identity.can_access_aggregate(aggregate_id):
            raise AuthorizationError(f"Agent {agent_id} cannot access aggregate {aggregate_id}")
        
        # Check stream access
        if stream_id and not identity.can_access_stream(stream_id):
            raise AuthorizationError(f"Agent {agent_id} cannot access stream {stream_id}")
        
        self._check_rate_limit(identity)
        
        return identity
    
    def authorize_write(self, agent_id: str, batch_size: int = 1, 
                       aggregate_id: Optional[str] = None) -> AgentIdentity:
        """Authorize write operation.
        
        Args:
            agent_id: Agent requesting access
            batch_size: Size of batch being written
            aggregate_id: Optional aggregate being written to
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        if not identity.has_permission(Permission.WRITE_EVENTS):
            raise AuthorizationError(f"Agent {agent_id} lacks WRITE_EVENTS permission")
        
        # Check batch size limits
        if batch_size > identity.max_batch_size:
            raise AuthorizationError(f"Batch size {batch_size} exceeds limit {identity.max_batch_size} for agent {agent_id}")
        
        # Check aggregate access
        if aggregate_id and not identity.can_access_aggregate(aggregate_id):
            raise AuthorizationError(f"Agent {agent_id} cannot write to aggregate {aggregate_id}")
        
        self._check_rate_limit(identity)
        
        return identity
    
    def authorize_query(self, agent_id: str) -> AgentIdentity:
        """Authorize query operation.
        
        Args:
            agent_id: Agent requesting access
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        if not identity.has_permission(Permission.QUERY_EVENTS):
            raise AuthorizationError(f"Agent {agent_id} lacks QUERY_EVENTS permission")
        
        self._check_rate_limit(identity)
        
        return identity
    
    def authorize_admin(self, agent_id: str) -> AgentIdentity:
        """Authorize administrative operation.
        
        Args:
            agent_id: Agent requesting access
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        if not identity.has_permission(Permission.ADMIN_ACCESS):
            raise AuthorizationError(f"Agent {agent_id} lacks ADMIN_ACCESS permission")
        
        return identity
    
    def authorize_expert_coordination(self, agent_id: str) -> AgentIdentity:
        """Authorize expert coordination operations.
        
        Args:
            agent_id: Agent requesting access
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        if not identity.has_permission(Permission.EXPERT_COORDINATION):
            raise AuthorizationError(f"Agent {agent_id} lacks EXPERT_COORDINATION permission")
        
        return identity
    
    def authorize_file_access(self, agent_id: str, operation: str = "read", file_path: Optional[str] = None) -> AgentIdentity:
        """Authorize file system operations through FUSE mount.
        
        Args:
            agent_id: Agent requesting access
            operation: Type of operation ("read" or "write")
            file_path: Optional file path being accessed
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        required_permission = Permission.FILE_READ if operation == "read" else Permission.FILE_WRITE
        
        if not identity.has_permission(required_permission):
            raise AuthorizationError(f"Agent {agent_id} lacks {required_permission} permission")
        
        # Additional security checks for sensitive paths
        if file_path:
            sensitive_paths = ['/etc', '/usr', '/var', '/boot', '/sys', '/proc', '/dev']
            for sensitive_path in sensitive_paths:
                if file_path.startswith(sensitive_path):
                    if not identity.has_permission(Permission.SYSTEM_ADMIN):
                        raise AuthorizationError(f"Access to {sensitive_path} requires SYSTEM_ADMIN permission")
        
        self._check_rate_limit(identity)
        
        return identity
    
    def authorize_command_execution(self, agent_id: str, command_type: Optional[str] = None) -> AgentIdentity:
        """Authorize command execution operations.
        
        Args:
            agent_id: Agent requesting access
            command_type: Optional type of command being executed
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated
            AuthorizationError: If agent lacks required permissions
        """
        identity = self._get_validated_identity(agent_id)
        
        if not identity.has_permission(Permission.COMMAND_EXECUTION):
            raise AuthorizationError(f"Agent {agent_id} lacks COMMAND_EXECUTION permission")
        
        # Additional checks for system-level commands
        if command_type and command_type in ['system_admin', 'system_config']:
            if not identity.has_permission(Permission.SYSTEM_ADMIN):
                raise AuthorizationError(f"Command type {command_type} requires SYSTEM_ADMIN permission")
        
        self._check_rate_limit(identity)
        
        return identity
    
    def _get_validated_identity(self, agent_id: str) -> AgentIdentity:
        """Get and validate agent identity.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Validated AgentIdentity
            
        Raises:
            AuthenticationError: If agent is not authenticated or expired
        """
        identity = self.authenticator.get_authenticated_agent(agent_id)
        if not identity:
            raise AuthenticationError(f"Agent {agent_id} is not authenticated")
        
        if identity.is_expired():
            raise AuthenticationError(f"Agent {agent_id} authentication has expired")
        
        return identity
    
    def _check_rate_limit(self, identity: AgentIdentity) -> None:
        """Check if agent is within rate limits.
        
        Args:
            identity: Agent identity to check
            
        Raises:
            AuthorizationError: If rate limit exceeded
        """
        current_time = time.time()
        agent_id = identity.agent_id
        
        # Initialize rate limit tracking
        if agent_id not in self._rate_limits:
            self._rate_limits[agent_id] = []
        
        # Remove requests older than 1 minute
        cutoff_time = current_time - 60
        self._rate_limits[agent_id] = [
            timestamp for timestamp in self._rate_limits[agent_id]
            if timestamp > cutoff_time
        ]
        
        # Check if rate limit exceeded
        if len(self._rate_limits[agent_id]) >= identity.max_requests_per_minute:
            raise AuthorizationError(f"Rate limit exceeded for agent {agent_id}: {len(self._rate_limits[agent_id])}/min")
        
        # Record current request
        self._rate_limits[agent_id].append(current_time)


def create_system_authenticator(secret: Optional[str] = None) -> SimpleAuthenticator:
    """Create system authenticator with default system agents.
    
    Args:
        secret: Optional shared secret (uses default if None)
        
    Returns:
        Configured SimpleAuthenticator
    """
    if secret is None:
        secret = os.environ.get('LIGHTHOUSE_SYSTEM_SECRET') or secrets.token_urlsafe(32)
    
    authenticator = SimpleAuthenticator(shared_secret=secret)
    
    # Pre-authenticate system agents for easier operation
    system_agents = [
        ("system-architect", AgentRole.EXPERT_AGENT),
        ("security-architect", AgentRole.EXPERT_AGENT),
        ("infrastructure-architect", AgentRole.EXPERT_AGENT),
        ("lighthouse-bridge", AgentRole.SYSTEM_AGENT),
        ("lighthouse-admin", AgentRole.ADMIN),
    ]
    
    for agent_id, role in system_agents:
        token = authenticator.create_token(agent_id)
        try:
            authenticator.authenticate(agent_id, token, role)
        except AuthenticationError:
            pass  # Ignore authentication failures during setup
    
    return authenticator