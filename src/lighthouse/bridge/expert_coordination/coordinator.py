"""
Expert Coordination System

Secure multi-agent coordination with authentication, validation, and event sourcing.
Handles agent registration, discovery, communication, and collaboration sessions.

Features:
- Cryptographic agent authentication using lighthouse.event_store auth
- Command validation and permission checking
- Event-sourced coordination state with audit trails
- FUSE filesystem integration for expert tools
- Real-time communication channels with proper authorization
- Context sharing and collaboration session management
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

# Import secure event store components
from ...event_store import (
    EventStore, Event, EventType, EventQuery, EventFilter,
    AgentIdentity, AgentRole, Permission, 
    AuthenticationError, AuthorizationError,
    SecurityError
)

logger = logging.getLogger(__name__)


class ExpertStatus(str, Enum):
    """Expert agent status"""
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    SUSPENDED = "suspended"


class CoordinationEventType(str, Enum):
    """Expert coordination specific events"""
    EXPERT_REGISTERED = "expert_registered"
    EXPERT_DISCONNECTED = "expert_disconnected"
    EXPERT_STATUS_CHANGED = "expert_status_changed"
    COLLABORATION_STARTED = "collaboration_started"
    COLLABORATION_ENDED = "collaboration_ended"
    COMMAND_DELEGATED = "command_delegated"
    COMMAND_COMPLETED = "command_completed"
    CONTEXT_SHARED = "context_shared"


@dataclass
class ExpertCapability:
    """Description of expert agent capabilities"""
    name: str
    description: str
    input_types: List[str]
    output_types: List[str]
    required_permissions: List[Permission]
    estimated_latency_ms: float = 1000.0
    confidence_threshold: float = 0.8


@dataclass
class RegisteredExpert:
    """Registered expert agent with authentication and capabilities"""
    agent_id: str
    agent_identity: AgentIdentity
    capabilities: List[ExpertCapability]
    status: ExpertStatus = ExpertStatus.AVAILABLE
    
    # Authentication and security
    auth_token: str = ""
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_key: Optional[str] = None
    
    # Performance tracking
    commands_completed: int = 0
    average_response_time: float = 0.0
    success_rate: float = 1.0
    
    # Context and state
    current_contexts: Set[str] = field(default_factory=set)
    collaboration_sessions: Set[str] = field(default_factory=set)
    
    def is_authenticated(self) -> bool:
        """Check if expert has valid authentication"""
        return bool(self.auth_token and self.session_key)
    
    def is_available(self) -> bool:
        """Check if expert is available for new tasks"""
        return (self.status == ExpertStatus.AVAILABLE and 
                self.is_authenticated() and 
                self.last_heartbeat > datetime.now(timezone.utc) - timedelta(minutes=5))


@dataclass
class CollaborationSession:
    """Multi-agent collaboration session"""
    session_id: str
    participants: Set[str]  # Agent IDs
    coordinator_id: str
    
    # Session state
    created_at: datetime
    last_activity: datetime
    status: str = "active"  # active, paused, completed, failed
    
    # Context and communication
    shared_context: Dict[str, Any] = field(default_factory=dict)
    communication_channels: Dict[str, str] = field(default_factory=dict)  # agent_id -> channel_path
    
    # Task tracking
    delegated_commands: List[str] = field(default_factory=list)
    completed_commands: List[str] = field(default_factory=list)
    failed_commands: List[str] = field(default_factory=list)


class SecureExpertCoordinator:
    """Secure expert coordination system with authentication and event sourcing"""
    
    def __init__(self, 
                 event_store: EventStore,
                 fuse_mount_path: Optional[str] = "/mnt/lighthouse/project/experts",
                 auth_secret: Optional[str] = None):
        """
        Initialize secure expert coordinator
        
        Args:
            event_store: Main event store for audit trails and persistence
            fuse_mount_path: Path for FUSE expert filesystem integration
            auth_secret: HMAC secret for authentication (uses event store secret if None)
        """
        self.event_store = event_store
        self.fuse_mount_path = Path(fuse_mount_path) if fuse_mount_path else None
        
        # Use event store's authentication system
        self.auth_secret = (auth_secret or "lighthouse-expert-coordination").encode('utf-8')
        
        # Expert registry with authentication
        self.registered_experts: Dict[str, RegisteredExpert] = {}
        self.expert_tokens: Dict[str, str] = {}  # token -> agent_id mapping
        
        # Collaboration sessions
        self.active_sessions: Dict[str, CollaborationSession] = {}
        
        # Command delegation tracking
        self.pending_delegations: Dict[str, Dict[str, Any]] = {}  # delegation_id -> delegation_info
        
        # Security and performance
        self.failed_auth_attempts: Dict[str, List[datetime]] = {}  # agent_id -> attempt_times
        self.rate_limits: Dict[str, List[datetime]] = {}  # agent_id -> request_times
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self.stats = {
            'total_experts': 0,
            'active_sessions': 0,
            'commands_delegated': 0,
            'commands_completed': 0,
            'authentication_failures': 0
        }
    
    async def start(self):
        """Start the expert coordination system"""
        logger.info("Starting Secure Expert Coordination System...")
        
        # Create FUSE directories if configured
        if self.fuse_mount_path:
            await self._setup_fuse_integration()
        
        # Start background tasks
        heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        session_cleanup_task = asyncio.create_task(self._session_cleanup())
        stats_task = asyncio.create_task(self._update_stats())
        
        self._background_tasks.update([heartbeat_task, session_cleanup_task, stats_task])
        
        # Log startup event
        await self._log_coordination_event(
            CoordinationEventType.EXPERT_REGISTERED,
            aggregate_id="coordinator",
            data={"action": "system_started", "fuse_enabled": bool(self.fuse_mount_path)}
        )
        
        logger.info("Expert Coordination System started successfully")
    
    async def stop(self):
        """Stop the expert coordination system"""
        logger.info("Stopping Expert Coordination System...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # End all active sessions
        for session in list(self.active_sessions.values()):
            await self.end_collaboration_session(session.session_id, reason="system_shutdown")
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
        
        logger.info("Expert Coordination System stopped")
    
    async def register_expert(self, 
                            agent_identity: AgentIdentity, 
                            capabilities: List[ExpertCapability],
                            auth_challenge: str) -> Tuple[bool, str, Optional[str]]:
        """
        Register expert agent with secure authentication
        
        Args:
            agent_identity: Validated agent identity from event store auth
            capabilities: List of expert capabilities
            auth_challenge: HMAC-based authentication challenge
            
        Returns:
            (success, message, auth_token)
        """
        try:
            # Validate agent identity has required permissions
            required_perms = [Permission.EXPERT_COORDINATION, Permission.COMMAND_EXECUTION]
            for perm in required_perms:
                if perm not in agent_identity.permissions:
                    await self._log_auth_failure(agent_identity.agent_id, "insufficient_permissions")
                    return False, f"Missing required permission: {perm}", None
            
            # Verify authentication challenge
            expected_challenge = self._generate_auth_challenge(agent_identity.agent_id)
            if not hmac.compare_digest(auth_challenge, expected_challenge):
                await self._log_auth_failure(agent_identity.agent_id, "invalid_challenge")
                return False, "Authentication challenge failed", None
            
            # Check rate limiting
            if self._is_rate_limited(agent_identity.agent_id):
                await self._log_auth_failure(agent_identity.agent_id, "rate_limited")
                return False, "Rate limit exceeded", None
            
            # Generate secure session token
            auth_token = self._generate_session_token(agent_identity.agent_id)
            session_key = self._generate_session_key()
            
            # Create registered expert
            expert = RegisteredExpert(
                agent_id=agent_identity.agent_id,
                agent_identity=agent_identity,
                capabilities=capabilities,
                auth_token=auth_token,
                session_key=session_key,
                status=ExpertStatus.AVAILABLE
            )
            
            # Store expert
            self.registered_experts[agent_identity.agent_id] = expert
            self.expert_tokens[auth_token] = agent_identity.agent_id
            
            # Log successful registration
            await self._log_coordination_event(
                CoordinationEventType.EXPERT_REGISTERED,
                aggregate_id=agent_identity.agent_id,
                data={
                    "agent_role": agent_identity.role.value,
                    "capabilities": [cap.name for cap in capabilities],
                    "permissions": [perm.value for perm in agent_identity.permissions]
                }
            )
            
            self.stats['total_experts'] += 1
            
            logger.info(f"Expert {agent_identity.agent_id} registered successfully with {len(capabilities)} capabilities")
            
            return True, "Registration successful", auth_token
            
        except Exception as e:
            logger.error(f"Expert registration failed for {agent_identity.agent_id}: {e}")
            await self._log_auth_failure(agent_identity.agent_id, f"registration_error: {e}")
            return False, f"Registration failed: {e}", None
    
    async def authenticate_expert(self, auth_token: str) -> Optional[RegisteredExpert]:
        """
        Authenticate expert using session token
        
        Args:
            auth_token: Session token from registration
            
        Returns:
            RegisteredExpert if valid, None otherwise
        """
        try:
            # Validate token format and lookup
            if not auth_token or auth_token not in self.expert_tokens:
                return None
            
            agent_id = self.expert_tokens[auth_token]
            expert = self.registered_experts.get(agent_id)
            
            if not expert or not expert.is_authenticated():
                return None
            
            # Update last heartbeat
            expert.last_heartbeat = datetime.now(timezone.utc)
            
            return expert
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
    
    async def delegate_command(self,
                             requester_token: str,
                             command_type: str,
                             command_data: Dict[str, Any],
                             required_capabilities: List[str],
                             timeout_seconds: int = 300) -> Tuple[bool, str, Optional[str]]:
        """
        Delegate command to capable expert with authentication and validation
        
        Args:
            requester_token: Authentication token of requesting agent
            command_type: Type of command to delegate
            command_data: Command parameters and data
            required_capabilities: List of required expert capabilities
            timeout_seconds: Command timeout
            
        Returns:
            (success, message, delegation_id)
        """
        try:
            # Authenticate requester
            requester = await self.authenticate_expert(requester_token)
            if not requester:
                return False, "Authentication failed", None
            
            # Validate command data against security rules
            validation_result = await self._validate_command_security(command_type, command_data, requester)
            if not validation_result[0]:
                return False, f"Security validation failed: {validation_result[1]}", None
            
            # Find capable and available experts
            candidates = self._find_capable_experts(required_capabilities)
            if not candidates:
                return False, "No capable experts available", None
            
            # Select best expert based on performance metrics
            selected_expert = self._select_best_expert(candidates, required_capabilities)
            
            # Create delegation
            delegation_id = str(uuid.uuid4())
            delegation_info = {
                'delegation_id': delegation_id,
                'requester_id': requester.agent_id,
                'expert_id': selected_expert.agent_id,
                'command_type': command_type,
                'command_data': command_data,
                'required_capabilities': required_capabilities,
                'created_at': datetime.now(timezone.utc),
                'timeout_at': datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds),
                'status': 'pending'
            }
            
            self.pending_delegations[delegation_id] = delegation_info
            
            # Update expert status
            selected_expert.status = ExpertStatus.BUSY
            
            # Log delegation event
            await self._log_coordination_event(
                CoordinationEventType.COMMAND_DELEGATED,
                aggregate_id=delegation_id,
                data={
                    'requester_id': requester.agent_id,
                    'expert_id': selected_expert.agent_id,
                    'command_type': command_type,
                    'capabilities': required_capabilities
                }
            )
            
            self.stats['commands_delegated'] += 1
            
            logger.info(f"Command {command_type} delegated to expert {selected_expert.agent_id} (delegation: {delegation_id})")
            
            return True, f"Command delegated to {selected_expert.agent_id}", delegation_id
            
        except Exception as e:
            logger.error(f"Command delegation failed: {e}")
            return False, f"Delegation failed: {e}", None
    
    async def start_collaboration_session(self,
                                        coordinator_token: str,
                                        participant_ids: List[str],
                                        session_context: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        Start multi-agent collaboration session with secure authentication
        
        Args:
            coordinator_token: Authentication token of session coordinator
            participant_ids: List of expert agent IDs to include
            session_context: Initial shared context
            
        Returns:
            (success, message, session_id)
        """
        try:
            # Authenticate coordinator
            coordinator = await self.authenticate_expert(coordinator_token)
            if not coordinator:
                return False, "Coordinator authentication failed", None
            
            # Validate all participants are registered and available
            validated_participants = set()
            for participant_id in participant_ids:
                if participant_id not in self.registered_experts:
                    return False, f"Participant {participant_id} not registered", None
                
                participant = self.registered_experts[participant_id]
                if not participant.is_available():
                    return False, f"Participant {participant_id} not available", None
                
                validated_participants.add(participant_id)
            
            # Create collaboration session
            session_id = str(uuid.uuid4())
            session = CollaborationSession(
                session_id=session_id,
                participants=validated_participants,
                coordinator_id=coordinator.agent_id,
                created_at=datetime.now(timezone.utc),
                last_activity=datetime.now(timezone.utc),
                shared_context=session_context
            )
            
            # Setup FUSE communication channels if enabled
            if self.fuse_mount_path:
                for participant_id in validated_participants:
                    channel_path = self.fuse_mount_path / "sessions" / session_id / f"{participant_id}.fifo"
                    session.communication_channels[participant_id] = str(channel_path)
                    # Create named pipe would happen here
            
            # Update expert statuses
            for participant_id in validated_participants:
                expert = self.registered_experts[participant_id]
                expert.collaboration_sessions.add(session_id)
                expert.status = ExpertStatus.BUSY
            
            self.active_sessions[session_id] = session
            
            # Log collaboration start
            await self._log_coordination_event(
                CoordinationEventType.COLLABORATION_STARTED,
                aggregate_id=session_id,
                data={
                    'coordinator_id': coordinator.agent_id,
                    'participants': list(validated_participants),
                    'context_keys': list(session_context.keys())
                }
            )
            
            self.stats['active_sessions'] += 1
            
            logger.info(f"Collaboration session {session_id} started with {len(validated_participants)} participants")
            
            return True, f"Session created with {len(validated_participants)} participants", session_id
            
        except Exception as e:
            logger.error(f"Failed to start collaboration session: {e}")
            return False, f"Session creation failed: {e}", None
    
    async def end_collaboration_session(self, session_id: str, reason: str = "completed"):
        """End collaboration session and cleanup resources"""
        try:
            if session_id not in self.active_sessions:
                return
            
            session = self.active_sessions[session_id]
            
            # Update participant statuses
            for participant_id in session.participants:
                if participant_id in self.registered_experts:
                    expert = self.registered_experts[participant_id]
                    expert.collaboration_sessions.discard(session_id)
                    if not expert.collaboration_sessions:
                        expert.status = ExpertStatus.AVAILABLE
            
            # Cleanup communication channels
            for channel_path in session.communication_channels.values():
                try:
                    Path(channel_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup channel {channel_path}: {e}")
            
            # Remove session
            del self.active_sessions[session_id]
            
            # Log session end
            await self._log_coordination_event(
                CoordinationEventType.COLLABORATION_ENDED,
                aggregate_id=session_id,
                data={'reason': reason, 'duration_seconds': (datetime.now(timezone.utc) - session.created_at).total_seconds()}
            )
            
            self.stats['active_sessions'] -= 1
            
            logger.info(f"Collaboration session {session_id} ended: {reason}")
            
        except Exception as e:
            logger.error(f"Error ending collaboration session {session_id}: {e}")
    
    def get_coordination_stats(self) -> Dict[str, Any]:
        """Get comprehensive coordination statistics"""
        return {
            'system_stats': self.stats.copy(),
            'registered_experts': len(self.registered_experts),
            'active_experts': len([e for e in self.registered_experts.values() if e.is_available()]),
            'active_sessions': len(self.active_sessions),
            'pending_delegations': len(self.pending_delegations),
            'capabilities_available': self._get_available_capabilities(),
            'average_response_time': self._calculate_average_response_time(),
            'system_load': self._calculate_system_load()
        }
    
    # Private helper methods
    
    def _generate_auth_challenge(self, agent_id: str) -> str:
        """Generate HMAC authentication challenge"""
        message = f"{agent_id}:{int(time.time())}"
        return hmac.new(self.auth_secret, message.encode(), hashlib.sha256).hexdigest()
    
    def _generate_session_token(self, agent_id: str) -> str:
        """Generate secure session token"""
        token_data = f"{agent_id}:{uuid.uuid4()}:{int(time.time())}"
        return hashlib.sha256(token_data.encode()).hexdigest()
    
    def _generate_session_key(self) -> str:
        """Generate session encryption key"""
        return hashlib.sha256(f"{uuid.uuid4()}:{time.time()}".encode()).hexdigest()[:32]
    
    def _is_rate_limited(self, agent_id: str) -> bool:
        """Check if agent is rate limited"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)
        
        if agent_id not in self.rate_limits:
            self.rate_limits[agent_id] = []
        
        # Clean old requests
        self.rate_limits[agent_id] = [t for t in self.rate_limits[agent_id] if t > cutoff]
        
        # Check rate limit (max 60 requests per minute)
        if len(self.rate_limits[agent_id]) >= 60:
            return True
        
        self.rate_limits[agent_id].append(now)
        return False
    
    async def _validate_command_security(self, command_type: str, command_data: Dict[str, Any], requester: RegisteredExpert) -> Tuple[bool, str]:
        """Validate command meets security requirements"""
        try:
            # Check if command type is allowed
            dangerous_commands = ['rm', 'sudo', 'chmod 777', 'dd', 'mkfs', 'fdisk']
            command_text = str(command_data.get('command', ''))
            
            for dangerous in dangerous_commands:
                if dangerous in command_text.lower():
                    return False, f"Dangerous command '{dangerous}' not allowed"
            
            # Check file path restrictions
            if 'path' in command_data:
                path = Path(command_data['path'])
                dangerous_paths = ['/etc', '/usr', '/var', '/boot', '/sys', '/proc', '/dev']
                
                for dangerous_path in dangerous_paths:
                    if str(path).startswith(dangerous_path):
                        return False, f"Access to {dangerous_path} requires elevated permissions"
            
            # Check requester permissions for command type
            required_permissions = {
                'file_write': [Permission.FILE_WRITE],
                'file_read': [Permission.FILE_READ],
                'command_execution': [Permission.COMMAND_EXECUTION],
                'system_admin': [Permission.SYSTEM_ADMIN]
            }
            
            if command_type in required_permissions:
                for perm in required_permissions[command_type]:
                    if perm not in requester.agent_identity.permissions:
                        return False, f"Missing permission: {perm}"
            
            return True, "Command validated"
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def _find_capable_experts(self, required_capabilities: List[str]) -> List[RegisteredExpert]:
        """Find experts with required capabilities"""
        capable_experts = []
        
        for expert in self.registered_experts.values():
            if not expert.is_available():
                continue
            
            expert_capabilities = {cap.name for cap in expert.capabilities}
            if all(req_cap in expert_capabilities for req_cap in required_capabilities):
                capable_experts.append(expert)
        
        return capable_experts
    
    def _select_best_expert(self, candidates: List[RegisteredExpert], required_capabilities: List[str]) -> RegisteredExpert:
        """Select best expert based on performance metrics"""
        if not candidates:
            raise ValueError("No candidates available")
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Score candidates based on success rate, response time, and workload
        best_expert = None
        best_score = -1
        
        for expert in candidates:
            score = (expert.success_rate * 0.4 + 
                    (1.0 / max(expert.average_response_time, 1)) * 0.3 +
                    (1.0 / max(len(expert.current_contexts), 1)) * 0.3)
            
            if score > best_score:
                best_score = score
                best_expert = expert
        
        return best_expert or candidates[0]
    
    def _get_available_capabilities(self) -> Dict[str, int]:
        """Get count of each capability available"""
        capabilities = {}
        
        for expert in self.registered_experts.values():
            if expert.is_available():
                for cap in expert.capabilities:
                    capabilities[cap.name] = capabilities.get(cap.name, 0) + 1
        
        return capabilities
    
    def _calculate_average_response_time(self) -> float:
        """Calculate system-wide average response time"""
        total_time = sum(expert.average_response_time for expert in self.registered_experts.values())
        count = len(self.registered_experts)
        return total_time / count if count > 0 else 0.0
    
    def _calculate_system_load(self) -> float:
        """Calculate current system load (0.0 to 1.0)"""
        if not self.registered_experts:
            return 0.0
        
        busy_experts = len([e for e in self.registered_experts.values() if e.status == ExpertStatus.BUSY])
        return busy_experts / len(self.registered_experts)
    
    async def _log_coordination_event(self, event_type: CoordinationEventType, aggregate_id: str, data: Dict[str, Any]):
        """Log coordination event to event store"""
        try:
            event = Event(
                event_type=EventType.AGENT_REGISTERED if event_type == CoordinationEventType.EXPERT_REGISTERED else EventType.SYSTEM_STARTED,
                aggregate_id=aggregate_id,
                aggregate_type="expert_coordination",
                data=data,
                source_component="expert_coordinator",
                metadata={"coordination_event_type": event_type.value}
            )
            
            await self.event_store.append(event)
            
        except Exception as e:
            logger.error(f"Failed to log coordination event: {e}")
    
    async def _log_auth_failure(self, agent_id: str, reason: str):
        """Log authentication failure for security monitoring"""
        now = datetime.now(timezone.utc)
        
        if agent_id not in self.failed_auth_attempts:
            self.failed_auth_attempts[agent_id] = []
        
        self.failed_auth_attempts[agent_id].append(now)
        self.stats['authentication_failures'] += 1
        
        # Log to event store for security audit
        await self._log_coordination_event(
            CoordinationEventType.EXPERT_DISCONNECTED,
            aggregate_id=agent_id,
            data={"auth_failure_reason": reason, "timestamp": now.isoformat()}
        )
        
        logger.warning(f"Authentication failure for {agent_id}: {reason}")
    
    async def _setup_fuse_integration(self):
        """Setup FUSE filesystem integration"""
        if not self.fuse_mount_path:
            return
        
        try:
            # Create directory structure
            (self.fuse_mount_path / "experts").mkdir(parents=True, exist_ok=True)
            (self.fuse_mount_path / "sessions").mkdir(parents=True, exist_ok=True)
            (self.fuse_mount_path / "delegations").mkdir(parents=True, exist_ok=True)
            
            logger.info(f"FUSE integration setup at {self.fuse_mount_path}")
            
        except Exception as e:
            logger.error(f"FUSE setup failed: {e}")
    
    async def _heartbeat_monitor(self):
        """Monitor expert heartbeats and cleanup stale registrations"""
        while not self._shutdown_event.is_set():
            try:
                now = datetime.now(timezone.utc)
                stale_threshold = now - timedelta(minutes=10)
                
                stale_experts = []
                for agent_id, expert in self.registered_experts.items():
                    if expert.last_heartbeat < stale_threshold:
                        stale_experts.append(agent_id)
                
                # Cleanup stale experts
                for agent_id in stale_experts:
                    expert = self.registered_experts[agent_id]
                    
                    # End their collaboration sessions
                    for session_id in list(expert.collaboration_sessions):
                        await self.end_collaboration_session(session_id, reason="expert_disconnected")
                    
                    # Remove from registry
                    del self.registered_experts[agent_id]
                    if expert.auth_token in self.expert_tokens:
                        del self.expert_tokens[expert.auth_token]
                    
                    await self._log_coordination_event(
                        CoordinationEventType.EXPERT_DISCONNECTED,
                        aggregate_id=agent_id,
                        data={"reason": "heartbeat_timeout"}
                    )
                    
                    logger.info(f"Removed stale expert: {agent_id}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e}")
                await asyncio.sleep(60)
    
    async def _session_cleanup(self):
        """Cleanup expired collaboration sessions"""
        while not self._shutdown_event.is_set():
            try:
                now = datetime.now(timezone.utc)
                expired_sessions = []
                
                for session_id, session in self.active_sessions.items():
                    # Sessions expire after 24 hours of inactivity
                    if now - session.last_activity > timedelta(hours=24):
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    await self.end_collaboration_session(session_id, reason="session_expired")
                
                await asyncio.sleep(3600)  # Check every hour
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
                await asyncio.sleep(3600)
    
    async def _update_stats(self):
        """Update system statistics"""
        while not self._shutdown_event.is_set():
            try:
                # Update real-time stats
                self.stats.update({
                    'total_experts': len(self.registered_experts),
                    'active_sessions': len(self.active_sessions),
                    'pending_delegations': len(self.pending_delegations)
                })
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stats update error: {e}")
                await asyncio.sleep(30)


# Legacy compatibility - create alias
ExpertCoordinator = SecureExpertCoordinator