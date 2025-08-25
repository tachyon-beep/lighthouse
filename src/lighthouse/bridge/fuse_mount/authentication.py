"""
FUSE Filesystem Authentication Module

Provides secure authentication for FUSE operations, ensuring all filesystem
access is properly authenticated and authorized for expert agents.

Security Features:
- Agent identity validation
- Session-based authentication
- Permission-based access control
- Audit logging for all filesystem operations
"""

import asyncio
import hashlib
import hmac
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Set, List
from datetime import datetime, timedelta

# Import race condition prevention
from .race_condition_fixes import (
    get_race_prevention, OperationType, RaceConditionError
)

logger = logging.getLogger(__name__)


@dataclass
class AgentSession:
    """Authenticated agent session"""
    agent_id: str
    session_id: str
    created_at: datetime
    last_access: datetime
    permissions: Set[str]
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class FileSystemPermission:
    """Filesystem permission definition"""
    path: str
    operation: str  # read, write, execute, list
    granted: bool
    reason: str


class FUSEAuthenticationManager:
    """
    Secure authentication manager for FUSE filesystem operations
    
    Provides comprehensive authentication and authorization for expert agents
    accessing the FUSE filesystem, ensuring all operations are properly
    authenticated and audited.
    """
    
    def __init__(self, auth_secret: str):
        """
        Initialize authentication manager
        
        Args:
            auth_secret: Secret key for HMAC authentication
        """
        self.auth_secret = auth_secret.encode('utf-8')
        
        # Active sessions
        self.active_sessions: Dict[str, AgentSession] = {}
        
        # Session management
        self.session_timeout = timedelta(hours=2)
        self.max_sessions_per_agent = 5
        
        # Permission cache
        self.permission_cache: Dict[str, Dict[str, bool]] = {}
        self.cache_timeout = 300  # 5 minutes
        
        # Audit logging
        self.access_log: List[Dict[str, any]] = []
        self.max_log_entries = 10000
        
        # Rate limiting
        self.operation_counts: Dict[str, List[float]] = {}
        self.max_operations_per_minute = 1000
        
        # Race condition prevention
        self.race_prevention = get_race_prevention()
    
    def authenticate_agent(self, 
                          agent_id: str, 
                          challenge: str, 
                          response: str,
                          permissions: Optional[Set[str]] = None) -> Optional[str]:
        """
        Authenticate agent and create session
        
        Args:
            agent_id: Unique agent identifier
            challenge: Authentication challenge
            response: HMAC response from agent
            permissions: Set of permissions for this session
            
        Returns:
            Session ID if authentication successful, None otherwise
        """
        try:
            # Verify HMAC response
            expected_response = hmac.new(
                self.auth_secret,
                f"{agent_id}:{challenge}".encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(response, expected_response):
                logger.warning(f"Authentication failed for agent {agent_id}: invalid HMAC")
                self._log_access("auth_failed", agent_id, None, "Invalid HMAC response")
                return None
            
            # Check session limits
            existing_sessions = [s for s in self.active_sessions.values() if s.agent_id == agent_id]
            if len(existing_sessions) >= self.max_sessions_per_agent:
                # Remove oldest session
                oldest_session = min(existing_sessions, key=lambda s: s.last_access)
                del self.active_sessions[oldest_session.session_id]
            
            # Create new session
            session_id = str(uuid.uuid4())
            session = AgentSession(
                agent_id=agent_id,
                session_id=session_id,
                created_at=datetime.utcnow(),
                last_access=datetime.utcnow(),
                permissions=permissions or self._get_default_permissions()
            )
            
            self.active_sessions[session_id] = session
            
            logger.info(f"Agent {agent_id} authenticated successfully, session: {session_id}")
            self._log_access("auth_success", agent_id, session_id, "Agent authenticated")
            
            return session_id
            
        except Exception as e:
            logger.error(f"Authentication error for agent {agent_id}: {e}")
            self._log_access("auth_error", agent_id, None, f"Authentication error: {e}")
            return None
    
    def validate_session(self, session_id: str) -> Optional[AgentSession]:
        """
        Validate and refresh session
        
        Args:
            session_id: Session identifier
            
        Returns:
            AgentSession if valid, None if invalid/expired
        """
        if not session_id or session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Check session timeout
        if datetime.utcnow() - session.last_access > self.session_timeout:
            logger.info(f"Session {session_id} expired for agent {session.agent_id}")
            del self.active_sessions[session_id]
            self._log_access("session_expired", session.agent_id, session_id, "Session expired")
            return None
        
        # Refresh last access time
        session.last_access = datetime.utcnow()
        return session
    
    def check_permission(self, 
                        session_id: str, 
                        path: str, 
                        operation: str) -> FileSystemPermission:
        """
        Check if agent has permission for filesystem operation
        
        Args:
            session_id: Agent session ID
            path: Filesystem path
            operation: Operation type (read, write, execute, list)
            
        Returns:
            FileSystemPermission with granted status and reason
        """
        # Validate session first
        session = self.validate_session(session_id)
        if not session:
            return FileSystemPermission(
                path=path,
                operation=operation,
                granted=False,
                reason="Invalid or expired session"
            )
        
        # Check rate limiting
        if not self._check_rate_limit(session.agent_id):
            self._log_access("rate_limited", session.agent_id, session_id, 
                           f"Rate limit exceeded for {operation} on {path}")
            return FileSystemPermission(
                path=path,
                operation=operation,
                granted=False,
                reason="Rate limit exceeded"
            )
        
        # Check cached permissions
        cache_key = f"{session.agent_id}:{path}:{operation}"
        if cache_key in self.permission_cache:
            cache_entry = self.permission_cache[cache_key]
            if time.time() - cache_entry.get('timestamp', 0) < self.cache_timeout:
                granted = cache_entry.get('granted', False)
                reason = cache_entry.get('reason', 'Cached decision')
                
                if granted:
                    self._log_access("access_granted", session.agent_id, session_id,
                                   f"Cached permission for {operation} on {path}")
                
                return FileSystemPermission(
                    path=path,
                    operation=operation,
                    granted=granted,
                    reason=reason
                )
        
        # Evaluate permissions
        granted, reason = self._evaluate_permission(session, path, operation)
        
        # Cache decision
        self.permission_cache[cache_key] = {
            'granted': granted,
            'reason': reason,
            'timestamp': time.time()
        }
        
        # Log access attempt
        if granted:
            self._log_access("access_granted", session.agent_id, session_id,
                           f"Permission granted for {operation} on {path}")
        else:
            self._log_access("access_denied", session.agent_id, session_id,
                           f"Permission denied for {operation} on {path}: {reason}")
        
        return FileSystemPermission(
            path=path,
            operation=operation,
            granted=granted,
            reason=reason
        )
    
    def _evaluate_permission(self, 
                           session: AgentSession, 
                           path: str, 
                           operation: str) -> tuple[bool, str]:
        """
        Evaluate permission based on session and path
        
        Args:
            session: Agent session
            path: Filesystem path
            operation: Operation type
            
        Returns:
            Tuple of (granted: bool, reason: str)
        """
        # Parse path components
        path_parts = [p for p in path.split('/') if p]
        
        if not path_parts:
            # Root directory - read-only access for listing
            if operation in ['read', 'list']:
                return True, "Root directory read access"
            else:
                return False, "Root directory is read-only"
        
        section = path_parts[0]
        
        # Section-based permissions
        if section == 'current':
            # /current - Read/write for authenticated agents
            if 'filesystem_write' in session.permissions and operation in ['read', 'write', 'list']:
                return True, f"Agent has filesystem_write permission"
            elif operation in ['read', 'list']:
                return 'filesystem_read' in session.permissions, "Read-only access to current files"
            else:
                return False, "Write access requires filesystem_write permission"
        
        elif section == 'history':
            # /history - Read-only for all authenticated agents
            if operation in ['read', 'list']:
                return 'filesystem_read' in session.permissions, "Read access to historical files"
            else:
                return False, "History section is read-only"
        
        elif section == 'shadows':
            # /shadows - Read access for agents with AST permissions
            if operation in ['read', 'list']:
                return 'ast_access' in session.permissions, "AST access required for shadows"
            else:
                return False, "Shadow files are read-only"
        
        elif section == 'context':
            # /context - Read access to context packages
            if operation in ['read', 'list']:
                return 'context_access' in session.permissions, "Context access permission required"
            else:
                return False, "Context packages are read-only"
        
        elif section == 'streams':
            # /streams - Named pipe access for expert coordination
            if operation in ['read', 'write']:
                return 'stream_access' in session.permissions, "Stream access for expert coordination"
            else:
                return False, "Invalid stream operation"
        
        elif section == 'debug':
            # /debug - Debug access for authorized agents
            if operation in ['read', 'list']:
                return 'debug_access' in session.permissions, "Debug access permission required"
            else:
                return False, "Debug section is read-only"
        
        else:
            return False, f"Unknown filesystem section: {section}"
    
    def _get_default_permissions(self) -> Set[str]:
        """Get default permission set for authenticated agents"""
        return {
            'filesystem_read',    # Read access to current files
            'filesystem_write',   # Write access to current files  
            'context_access',     # Access to context packages
            'stream_access'       # Access to communication streams
        }
    
    def _check_rate_limit(self, agent_id: str) -> bool:
        """Check rate limiting for agent"""
        current_time = time.time()
        
        if agent_id not in self.operation_counts:
            self.operation_counts[agent_id] = []
        
        # Clean old entries (older than 1 minute)
        cutoff_time = current_time - 60.0
        self.operation_counts[agent_id] = [
            t for t in self.operation_counts[agent_id] if t > cutoff_time
        ]
        
        # Check current rate
        if len(self.operation_counts[agent_id]) >= self.max_operations_per_minute:
            return False
        
        # Record current operation
        self.operation_counts[agent_id].append(current_time)
        return True
    
    def _log_access(self, action: str, agent_id: str, session_id: Optional[str], details: str):
        """Log filesystem access for audit purposes"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'agent_id': agent_id,
            'session_id': session_id,
            'details': details
        }
        
        self.access_log.append(log_entry)
        
        # Limit log size
        if len(self.access_log) > self.max_log_entries:
            self.access_log = self.access_log[-int(self.max_log_entries * 0.8):]
    
    def logout_session(self, session_id: str) -> bool:
        """
        Logout and invalidate session
        
        Args:
            session_id: Session to logout
            
        Returns:
            True if logout successful
        """
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            del self.active_sessions[session_id]
            
            logger.info(f"Agent {session.agent_id} logged out, session {session_id}")
            self._log_access("logout", session.agent_id, session_id, "Agent logged out")
            
            return True
        
        return False
    
    def cleanup_expired_sessions(self):
        """Cleanup expired sessions (should be called periodically)"""
        current_time = datetime.utcnow()
        expired_sessions = []
        
        for session_id, session in self.active_sessions.items():
            if current_time - session.last_access > self.session_timeout:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            session = self.active_sessions[session_id]
            del self.active_sessions[session_id]
            self._log_access("session_cleanup", session.agent_id, session_id, "Session expired during cleanup")
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, any]]:
        """Get session information for debugging/monitoring"""
        session = self.validate_session(session_id)
        if not session:
            return None
        
        return {
            'agent_id': session.agent_id,
            'session_id': session.session_id,
            'created_at': session.created_at.isoformat(),
            'last_access': session.last_access.isoformat(),
            'permissions': list(session.permissions),
            'source_ip': session.source_ip,
            'user_agent': session.user_agent
        }
    
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, any]]:
        """Get recent audit log entries"""
        return self.access_log[-limit:] if limit > 0 else self.access_log
    
    # Race Condition Prevention Methods
    
    async def safe_read_operation(self, session_id: str, path: str, 
                                 operation_callback) -> any:
        """Perform safe read operation with race condition protection."""
        session = self.validate_session(session_id)
        if not session:
            raise PermissionError("Invalid session")
        
        permission = self.check_permission(session_id, path, "read")
        if not permission.granted:
            raise PermissionError(f"Read permission denied: {permission.reason}")
        
        async with self.race_prevention.atomic_operation(
            path, OperationType.READ, session.agent_id
        ) as operation_id:
            try:
                result = operation_callback(path)
                self._log_access("read", session.agent_id, session_id, 
                               f"Safe read of {path} (op: {operation_id})")
                return result
            except Exception as e:
                self._log_access("read_error", session.agent_id, session_id,
                               f"Failed read of {path}: {str(e)}")
                raise
    
    async def safe_write_operation(self, session_id: str, path: str,
                                  operation_callback) -> any:
        """Perform safe write operation with race condition protection."""
        session = self.validate_session(session_id)
        if not session:
            raise PermissionError("Invalid session")
        
        permission = self.check_permission(session_id, path, "write")
        if not permission.granted:
            raise PermissionError(f"Write permission denied: {permission.reason}")
        
        async with self.race_prevention.atomic_operation(
            path, OperationType.WRITE, session.agent_id, validate_checksum=True
        ) as operation_id:
            try:
                result = operation_callback(path)
                self._log_access("write", session.agent_id, session_id,
                               f"Safe write to {path} (op: {operation_id})")
                return result
            except RaceConditionError as e:
                self._log_access("race_condition", session.agent_id, session_id,
                               f"Race condition in write to {path}: {str(e)}")
                raise
            except Exception as e:
                self._log_access("write_error", session.agent_id, session_id,
                               f"Failed write to {path}: {str(e)}")
                raise
    
    async def safe_create_operation(self, session_id: str, path: str,
                                   operation_callback) -> any:
        """Perform safe create operation with race condition protection."""
        session = self.validate_session(session_id)
        if not session:
            raise PermissionError("Invalid session")
        
        permission = self.check_permission(session_id, path, "write")
        if not permission.granted:
            raise PermissionError(f"Create permission denied: {permission.reason}")
        
        async with self.race_prevention.atomic_operation(
            path, OperationType.CREATE, session.agent_id
        ) as operation_id:
            try:
                result = operation_callback(path)
                self._log_access("create", session.agent_id, session_id,
                               f"Safe create of {path} (op: {operation_id})")
                return result
            except RaceConditionError as e:
                self._log_access("race_condition", session.agent_id, session_id,
                               f"Race condition in create of {path}: {str(e)}")
                raise
            except Exception as e:
                self._log_access("create_error", session.agent_id, session_id,
                               f"Failed create of {path}: {str(e)}")
                raise
    
    async def safe_delete_operation(self, session_id: str, path: str,
                                   operation_callback) -> any:
        """Perform safe delete operation with race condition protection."""
        session = self.validate_session(session_id)
        if not session:
            raise PermissionError("Invalid session")
        
        permission = self.check_permission(session_id, path, "write")
        if not permission.granted:
            raise PermissionError(f"Delete permission denied: {permission.reason}")
        
        async with self.race_prevention.atomic_operation(
            path, OperationType.DELETE, session.agent_id
        ) as operation_id:
            try:
                result = operation_callback(path)
                self._log_access("delete", session.agent_id, session_id,
                               f"Safe delete of {path} (op: {operation_id})")
                return result
            except RaceConditionError as e:
                self._log_access("race_condition", session.agent_id, session_id,
                               f"Race condition in delete of {path}: {str(e)}")
                raise
            except Exception as e:
                self._log_access("delete_error", session.agent_id, session_id,
                               f"Failed delete of {path}: {str(e)}")
                raise
    
    def get_race_condition_stats(self) -> Dict[str, any]:
        """Get race condition prevention statistics."""
        return self.race_prevention.get_statistics()


# Authentication integration for FUSE context
class FUSEAuthenticationContext:
    """
    Authentication context for FUSE operations
    
    Provides thread-local authentication context for FUSE operations,
    enabling proper authentication without modifying FUSE method signatures.
    """
    
    def __init__(self, auth_manager: FUSEAuthenticationManager):
        self.auth_manager = auth_manager
        self._current_session: Optional[str] = None
    
    def set_session(self, session_id: Optional[str]):
        """Set current session for FUSE operations"""
        self._current_session = session_id
    
    def get_current_agent(self) -> Optional[str]:
        """Get current authenticated agent ID"""
        if not self._current_session:
            return None
        
        session = self.auth_manager.validate_session(self._current_session)
        return session.agent_id if session else None
    
    def check_access(self, path: str, operation: str) -> bool:
        """Check if current session has access to path/operation"""
        if not self._current_session:
            return False
        
        permission = self.auth_manager.check_permission(
            self._current_session, path, operation
        )
        return permission.granted
    
    # Race-condition-safe operation methods
    
    async def safe_operation(self, path: str, operation_type: str,
                            operation_callback) -> any:
        """Perform operation with race condition protection."""
        if not self._current_session:
            raise PermissionError("No active session")
        
        # Map operation types to safe methods
        operation_map = {
            "read": self.auth_manager.safe_read_operation,
            "write": self.auth_manager.safe_write_operation,
            "create": self.auth_manager.safe_create_operation,
            "delete": self.auth_manager.safe_delete_operation
        }
        
        safe_method = operation_map.get(operation_type)
        if not safe_method:
            raise ValueError(f"Unknown operation type: {operation_type}")
        
        return await safe_method(self._current_session, path, operation_callback)