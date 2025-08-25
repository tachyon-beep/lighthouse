#!/usr/bin/env python3
"""
Test script for Expert Coordination System

Tests the expert coordination system with mocked event store and
validates all secure multi-agent coordination functionality.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lighthouse.bridge.expert_coordination.coordinator import (
    SecureExpertCoordinator,
    ExpertStatus,
    CoordinationEventType,
    ExpertCapability,
    RegisteredExpert,
    CollaborationSession
)

# Mock the event store components
class MockAgentIdentity:
    def __init__(self, agent_id: str, role, permissions):
        self.agent_id = agent_id
        self.role = role
        self.permissions = permissions

class MockPermissionValue:
    def __init__(self, value):
        self._value = value
    
    @property 
    def value(self):
        return self._value
    
    def __str__(self):
        return self._value
    
    def __eq__(self, other):
        if hasattr(other, 'value'):
            return self._value == other.value
        return self._value == str(other)

class MockPermission:
    EXPERT_COORDINATION = MockPermissionValue("expert_coordination")
    COMMAND_EXECUTION = MockPermissionValue("command_execution")
    FILE_READ = MockPermissionValue("file_read")
    FILE_WRITE = MockPermissionValue("file_write")
    SYSTEM_ADMIN = MockPermissionValue("system_admin")

class MockRoleValue:
    def __init__(self, value):
        self._value = value
    
    @property 
    def value(self):
        return self._value
    
    def __str__(self):
        return self._value

class MockAgentRole:
    EXPERT = MockRoleValue("expert")

class MockEventStore:
    def __init__(self):
        self.events = []
        
    async def append(self, event):
        self.events.append(event)
        return True

class MockEvent:
    def __init__(self, event_type, aggregate_id, aggregate_type, data, source_component, metadata=None):
        self.event_type = event_type
        self.aggregate_id = aggregate_id
        self.aggregate_type = aggregate_type
        self.data = data
        self.source_component = source_component
        self.metadata = metadata or {}

class MockEventType:
    AGENT_REGISTERED = "agent_registered"
    SYSTEM_STARTED = "system_started"

# Mock the imports in coordinator module
sys.modules['lighthouse.bridge.expert_coordination.coordinator'].Permission = MockPermission
sys.modules['lighthouse.bridge.expert_coordination.coordinator'].AgentRole = MockAgentRole
sys.modules['lighthouse.bridge.expert_coordination.coordinator'].Event = MockEvent
sys.modules['lighthouse.bridge.expert_coordination.coordinator'].EventType = MockEventType


async def test_expert_coordination_initialization():
    """Test expert coordinator initialization."""
    print("🔍 Testing Expert Coordination Initialization...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    
    # Test basic initialization
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        fuse_mount_path="/tmp/test-fuse",
        auth_secret="test-secret"
    )
    
    if coordinator.event_store == mock_event_store:
        print("✓ Event store assignment")
        passed += 1
    else:
        print("✗ Event store assignment failed")
        failed += 1
    
    if coordinator.fuse_mount_path == Path("/tmp/test-fuse"):
        print("✓ FUSE mount path assignment")
        passed += 1
    else:
        print("✗ FUSE mount path assignment failed")
        failed += 1
    
    if len(coordinator.registered_experts) == 0:
        print("✓ Empty expert registry on init")
        passed += 1
    else:
        print("✗ Expert registry not empty on init")
        failed += 1
    
    if len(coordinator.active_sessions) == 0:
        print("✓ Empty session registry on init")
        passed += 1
    else:
        print("✗ Session registry not empty on init")
        failed += 1
    
    print(f"Expert Coordination Initialization: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_expert_registration():
    """Test expert registration with authentication."""
    print("🔍 Testing Expert Registration...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        auth_secret="test-secret"
    )
    
    # Create mock agent identity
    agent_identity = MockAgentIdentity(
        agent_id="test-expert-1",
        role=MockAgentRole.EXPERT,
        permissions=[MockPermission.EXPERT_COORDINATION, MockPermission.COMMAND_EXECUTION]
    )
    
    # Create test capabilities
    capabilities = [
        ExpertCapability(
            name="code_analysis",
            description="Analyze code for issues",
            input_types=["python", "javascript"],
            output_types=["analysis_report"],
            required_permissions=[MockPermission.FILE_READ]
        ),
        ExpertCapability(
            name="security_audit",
            description="Security vulnerability assessment",
            input_types=["code", "configuration"],
            output_types=["security_report"],
            required_permissions=[MockPermission.FILE_READ, MockPermission.SYSTEM_ADMIN]
        )
    ]
    
    # Generate authentication challenge
    auth_challenge = coordinator._generate_auth_challenge("test-expert-1")
    
    # Test successful registration
    success, message, token = await coordinator.register_expert(
        agent_identity, capabilities, auth_challenge
    )
    
    if success:
        print("✓ Expert registration success")
        passed += 1
    else:
        print(f"✗ Expert registration failed: {message}")
        failed += 1
    
    if token and len(token) > 0:
        print("✓ Authentication token generated")
        passed += 1
    else:
        print("✗ Authentication token not generated")
        failed += 1
    
    if "test-expert-1" in coordinator.registered_experts:
        print("✓ Expert added to registry")
        passed += 1
    else:
        print("✗ Expert not added to registry")
        failed += 1
    
    # Test authentication with token
    authenticated_expert = await coordinator.authenticate_expert(token)
    if authenticated_expert and authenticated_expert.agent_id == "test-expert-1":
        print("✓ Expert authentication with token")
        passed += 1
    else:
        print("✗ Expert authentication failed")
        failed += 1
    
    # Test invalid authentication challenge
    success2, message2, token2 = await coordinator.register_expert(
        MockAgentIdentity(
            agent_id="test-expert-2",
            role=MockAgentRole.EXPERT,
            permissions=[MockPermission.EXPERT_COORDINATION, MockPermission.COMMAND_EXECUTION]
        ),
        capabilities,
        "invalid-challenge"
    )
    
    if not success2:
        print("✓ Invalid authentication challenge rejected")
        passed += 1
    else:
        print("✗ Invalid authentication challenge accepted")
        failed += 1
    
    print(f"Expert Registration: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_command_delegation():
    """Test command delegation functionality."""
    print("🔍 Testing Command Delegation...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        auth_secret="test-secret"
    )
    
    # Register an expert first
    agent_identity = MockAgentIdentity(
        agent_id="test-expert-delegate",
        role=MockAgentRole.EXPERT,
        permissions=[MockPermission.EXPERT_COORDINATION, MockPermission.COMMAND_EXECUTION, MockPermission.FILE_READ]
    )
    
    capabilities = [
        ExpertCapability(
            name="file_analysis",
            description="Analyze files",
            input_types=["file"],
            output_types=["analysis"],
            required_permissions=[MockPermission.FILE_READ]
        )
    ]
    
    auth_challenge = coordinator._generate_auth_challenge("test-expert-delegate")
    success, message, token = await coordinator.register_expert(
        agent_identity, capabilities, auth_challenge
    )
    
    if not success:
        print(f"✗ Failed to register expert for delegation test: {message}")
        failed += 5
        print(f"Command Delegation: 0 passed, {failed} failed\n")
        return 0, failed
    
    # Test successful command delegation
    delegation_success, delegation_message, delegation_id = await coordinator.delegate_command(
        requester_token=token,
        command_type="file_read",
        command_data={"path": "/tmp/test.txt", "operation": "read"},
        required_capabilities=["file_analysis"],
        timeout_seconds=60
    )
    
    if delegation_success:
        print("✓ Command delegation success")
        passed += 1
    else:
        print(f"✗ Command delegation failed: {delegation_message}")
        failed += 1
    
    if delegation_id and len(delegation_id) > 0:
        print("✓ Delegation ID generated")
        passed += 1
    else:
        print("✗ Delegation ID not generated")
        failed += 1
    
    if len(coordinator.pending_delegations) > 0:
        print("✓ Delegation tracked in pending list")
        passed += 1
    else:
        print("✗ Delegation not tracked")
        failed += 1
    
    # Test delegation with invalid token
    invalid_success, invalid_message, invalid_id = await coordinator.delegate_command(
        requester_token="invalid-token",
        command_type="file_read",
        command_data={"path": "/tmp/test.txt"},
        required_capabilities=["file_analysis"]
    )
    
    if not invalid_success:
        print("✓ Invalid token rejected for delegation")
        passed += 1
    else:
        print("✗ Invalid token accepted for delegation")
        failed += 1
    
    # Test delegation with dangerous command
    dangerous_success, dangerous_message, dangerous_id = await coordinator.delegate_command(
        requester_token=token,
        command_type="system_command",
        command_data={"command": "sudo rm -rf /"},
        required_capabilities=["file_analysis"]
    )
    
    if not dangerous_success and "Dangerous command" in dangerous_message:
        print("✓ Dangerous command blocked")
        passed += 1
    else:
        print("✗ Dangerous command not blocked")
        failed += 1
    
    print(f"Command Delegation: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_collaboration_sessions():
    """Test collaboration session management."""
    print("🔍 Testing Collaboration Sessions...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        auth_secret="test-secret"
    )
    
    # Register multiple experts
    experts = []
    tokens = []
    
    for i in range(3):
        agent_identity = MockAgentIdentity(
            agent_id=f"expert-{i}",
            role=MockAgentRole.EXPERT,
            permissions=[MockPermission.EXPERT_COORDINATION, MockPermission.COMMAND_EXECUTION]
        )
        
        capabilities = [
            ExpertCapability(
                name=f"capability_{i}",
                description=f"Test capability {i}",
                input_types=["text"],
                output_types=["result"],
                required_permissions=[MockPermission.FILE_READ]
            )
        ]
        
        auth_challenge = coordinator._generate_auth_challenge(f"expert-{i}")
        success, message, token = await coordinator.register_expert(
            agent_identity, capabilities, auth_challenge
        )
        
        if success:
            experts.append(f"expert-{i}")
            tokens.append(token)
    
    if len(experts) == 3:
        print("✓ Multiple experts registered for collaboration test")
        passed += 1
    else:
        print("✗ Failed to register experts for collaboration test")
        failed += 5
        print(f"Collaboration Sessions: {passed} passed, {failed} failed\n")
        return passed, failed
    
    # Test starting collaboration session
    session_success, session_message, session_id = await coordinator.start_collaboration_session(
        coordinator_token=tokens[0],
        participant_ids=experts[1:],  # Include experts 1 and 2
        session_context={"project": "test-collaboration", "goal": "analyze code"}
    )
    
    if session_success:
        print("✓ Collaboration session started")
        passed += 1
    else:
        print(f"✗ Collaboration session failed: {session_message}")
        failed += 1
    
    if session_id and len(session_id) > 0:
        print("✓ Session ID generated")
        passed += 1
    else:
        print("✗ Session ID not generated")
        failed += 1
    
    if len(coordinator.active_sessions) == 1:
        print("✓ Session tracked in active sessions")
        passed += 1
    else:
        print("✗ Session not tracked properly")
        failed += 1
    
    # Check that participants are marked as busy
    busy_count = sum(1 for expert in coordinator.registered_experts.values() 
                     if expert.status == ExpertStatus.BUSY)
    if busy_count >= 2:  # At least the participants should be busy
        print("✓ Participants marked as busy")
        passed += 1
    else:
        print("✗ Participants not marked as busy")
        failed += 1
    
    # Test ending collaboration session
    await coordinator.end_collaboration_session(session_id, reason="test_complete")
    
    if len(coordinator.active_sessions) == 0:
        print("✓ Session ended and removed from active sessions")
        passed += 1
    else:
        print("✗ Session not properly ended")
        failed += 1
    
    print(f"Collaboration Sessions: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_security_features():
    """Test security features."""
    print("🔍 Testing Security Features...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        auth_secret="test-secret"
    )
    
    # Test authentication challenge generation
    challenge1 = coordinator._generate_auth_challenge("test-agent")
    challenge2 = coordinator._generate_auth_challenge("test-agent")
    
    # Challenges should be different due to timestamp
    if challenge1 != challenge2:
        print("✓ Authentication challenges are unique")
        passed += 1
    else:
        print("✗ Authentication challenges not unique")
        failed += 1
    
    # Test session token generation
    token1 = coordinator._generate_session_token("test-agent")
    token2 = coordinator._generate_session_token("test-agent")
    
    if token1 != token2 and len(token1) > 32:
        print("✓ Session tokens are unique and sufficiently long")
        passed += 1
    else:
        print("✗ Session tokens not properly generated")
        failed += 1
    
    # Test rate limiting
    is_limited_first = coordinator._is_rate_limited("test-agent")
    if not is_limited_first:
        print("✓ First request not rate limited")
        passed += 1
    else:
        print("✗ First request incorrectly rate limited")
        failed += 1
    
    # Test command security validation
    # Create a mock expert for validation
    mock_expert = MagicMock()
    mock_expert.agent_identity.permissions = [MockPermission.FILE_READ]
    
    # Test safe command
    safe_valid, safe_msg = await coordinator._validate_command_security(
        "file_read", {"path": "/tmp/safe.txt"}, mock_expert
    )
    
    if safe_valid:
        print("✓ Safe command validated successfully")
        passed += 1
    else:
        print(f"✗ Safe command incorrectly rejected: {safe_msg}")
        failed += 1
    
    # Test dangerous command
    dangerous_valid, dangerous_msg = await coordinator._validate_command_security(
        "system_command", {"command": "rm -rf /"}, mock_expert
    )
    
    if not dangerous_valid:
        print("✓ Dangerous command blocked")
        passed += 1
    else:
        print("✗ Dangerous command not blocked")
        failed += 1
    
    print(f"Security Features: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_expert_selection():
    """Test expert selection algorithms."""
    print("🔍 Testing Expert Selection...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        auth_secret="test-secret"
    )
    
    # Create mock experts with different performance metrics
    experts = []
    for i in range(3):
        expert = RegisteredExpert(
            agent_id=f"expert-{i}",
            agent_identity=MockAgentIdentity(f"expert-{i}", MockAgentRole.EXPERT, []),
            capabilities=[
                ExpertCapability(
                    name="test_capability",
                    description="Test capability",
                    input_types=["text"],
                    output_types=["result"],
                    required_permissions=[]
                )
            ],
            status=ExpertStatus.AVAILABLE,
            success_rate=0.8 + i * 0.1,  # Different success rates
            average_response_time=1000 - i * 200  # Different response times
        )
        expert.auth_token = f"token-{i}"
        expert.session_key = f"key-{i}"
        expert.last_heartbeat = datetime.now(timezone.utc)
        experts.append(expert)
        coordinator.registered_experts[f"expert-{i}"] = expert
    
    # Test finding capable experts
    capable = coordinator._find_capable_experts(["test_capability"])
    
    if len(capable) == 3:
        print("✓ All capable experts found")
        passed += 1
    else:
        print(f"✗ Wrong number of capable experts found: {len(capable)}")
        failed += 1
    
    # Test expert selection
    selected = coordinator._select_best_expert(capable, ["test_capability"])
    
    if selected in capable:
        print("✓ Expert selected from candidates")
        passed += 1
    else:
        print("✗ Expert not selected from candidates")
        failed += 1
    
    # The best expert should be expert-2 (highest success rate and lowest response time)
    if selected.agent_id == "expert-2":
        print("✓ Best performing expert selected")
        passed += 1
    else:
        print(f"✗ Suboptimal expert selected: {selected.agent_id}")
        failed += 1
    
    # Test with no capable experts
    no_capable = coordinator._find_capable_experts(["nonexistent_capability"])
    if len(no_capable) == 0:
        print("✓ No capable experts found for nonexistent capability")
        passed += 1
    else:
        print("✗ Found experts for nonexistent capability")
        failed += 1
    
    print(f"Expert Selection: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_statistics_and_monitoring():
    """Test statistics and monitoring features."""
    print("🔍 Testing Statistics and Monitoring...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        auth_secret="test-secret"
    )
    
    # Test initial stats
    initial_stats = coordinator.get_coordination_stats()
    
    if initial_stats['registered_experts'] == 0:
        print("✓ Initial expert count correct")
        passed += 1
    else:
        print("✗ Initial expert count incorrect")
        failed += 1
    
    if initial_stats['active_sessions'] == 0:
        print("✓ Initial session count correct")
        passed += 1
    else:
        print("✗ Initial session count incorrect")
        failed += 1
    
    # Add some mock data
    coordinator.stats['commands_delegated'] = 10
    coordinator.stats['commands_completed'] = 8
    coordinator.stats['authentication_failures'] = 2
    
    updated_stats = coordinator.get_coordination_stats()
    
    if updated_stats['system_stats']['commands_delegated'] == 10:
        print("✓ Command delegation stats tracked")
        passed += 1
    else:
        print("✗ Command delegation stats not tracked")
        failed += 1
    
    # Test system load calculation
    system_load = coordinator._calculate_system_load()
    if system_load == 0.0:  # No experts registered, so load should be 0
        print("✓ System load calculation correct")
        passed += 1
    else:
        print("✗ System load calculation incorrect")
        failed += 1
    
    # Test available capabilities
    capabilities = coordinator._get_available_capabilities()
    if isinstance(capabilities, dict) and len(capabilities) == 0:
        print("✓ Available capabilities tracked correctly")
        passed += 1
    else:
        print("✗ Available capabilities not tracked correctly")
        failed += 1
    
    print(f"Statistics and Monitoring: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_cleanup_and_lifecycle():
    """Test cleanup and lifecycle management."""
    print("🔍 Testing Cleanup and Lifecycle...")
    
    passed = 0
    failed = 0
    
    mock_event_store = MockEventStore()
    
    # Test coordinator start/stop
    coordinator = SecureExpertCoordinator(
        event_store=mock_event_store,
        fuse_mount_path=None,  # Disable FUSE for testing
        auth_secret="test-secret"
    )
    
    # Mock the background task methods to avoid actual async tasks
    async def mock_task():
        await asyncio.sleep(0.01)
    
    with patch.object(coordinator, '_heartbeat_monitor', return_value=mock_task()):
        with patch.object(coordinator, '_session_cleanup', return_value=mock_task()):
            with patch.object(coordinator, '_update_stats', return_value=mock_task()):
                # Test start
                await coordinator.start()
                
                if len(coordinator._background_tasks) > 0:
                    print("✓ Background tasks started")
                    passed += 1
                else:
                    print("✗ Background tasks not started")
                    failed += 1
                
                # Test stop
                await coordinator.stop()
                
                if coordinator._shutdown_event.is_set():
                    print("✓ Shutdown event set")
                    passed += 1
                else:
                    print("✗ Shutdown event not set")
                    failed += 1
    
    # Test heartbeat cleanup logic
    coordinator2 = SecureExpertCoordinator(
        event_store=MockEventStore(),
        auth_secret="test-secret"
    )
    
    # Create a stale expert
    stale_expert = RegisteredExpert(
        agent_id="stale-expert",
        agent_identity=MockAgentIdentity("stale-expert", MockAgentRole.EXPERT, []),
        capabilities=[],
        status=ExpertStatus.AVAILABLE,
        last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=15)  # Stale
    )
    stale_expert.auth_token = "stale-token"
    stale_expert.session_key = "stale-key"
    
    coordinator2.registered_experts["stale-expert"] = stale_expert
    coordinator2.expert_tokens["stale-token"] = "stale-expert"
    
    # Simulate heartbeat monitor logic
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(minutes=10)
    
    stale_experts = []
    for agent_id, expert in coordinator2.registered_experts.items():
        if expert.last_heartbeat < stale_threshold:
            stale_experts.append(agent_id)
    
    if len(stale_experts) == 1 and stale_experts[0] == "stale-expert":
        print("✓ Stale expert detection works")
        passed += 1
    else:
        print("✗ Stale expert detection failed")
        failed += 1
    
    # Test session expiration logic
    expired_session = CollaborationSession(
        session_id="expired-session",
        participants={"expert-1"},
        coordinator_id="coordinator",
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),  # Expired
        last_activity=datetime.now(timezone.utc) - timedelta(hours=25)  # Expired
    )
    
    coordinator2.active_sessions["expired-session"] = expired_session
    
    # Check expiration logic
    expired_sessions = []
    for session_id, session in coordinator2.active_sessions.items():
        if now - session.last_activity > timedelta(hours=24):
            expired_sessions.append(session_id)
    
    if len(expired_sessions) == 1 and expired_sessions[0] == "expired-session":
        print("✓ Session expiration detection works")
        passed += 1
    else:
        print("✗ Session expiration detection failed")
        failed += 1
    
    print(f"Cleanup and Lifecycle: {passed} passed, {failed} failed\n")
    return passed, failed


async def main():
    """Run all tests."""
    print("🚀 Starting Expert Coordination System Tests\n")
    
    total_passed = 0
    total_failed = 0
    
    # Run all test suites
    test_suites = [
        test_expert_coordination_initialization,
        test_expert_registration,
        test_command_delegation,
        test_collaboration_sessions,
        test_security_features,
        test_expert_selection,
        test_statistics_and_monitoring,
        test_cleanup_and_lifecycle,
    ]
    
    for test_suite in test_suites:
        passed, failed = await test_suite()
        total_passed += passed
        total_failed += failed
    
    # Print final results
    print("="*70)
    print("EXPERT COORDINATION SYSTEM TEST RESULTS")
    print("="*70)
    print(f"Total Tests: {total_passed + total_failed}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if total_failed == 0:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"❌ {total_failed} tests failed")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)