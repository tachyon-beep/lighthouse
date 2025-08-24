"""Authentication and authorization for Event Store access."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from enum import Enum

from pydantic import BaseModel, Field


class Permission(str, Enum):
    """Event Store permissions."""
    READ_EVENTS = "events:read"
    WRITE_EVENTS = "events:write"
    QUERY_EVENTS = "events:query"
    ADMIN_ACCESS = "admin:access"
    HEALTH_CHECK = "health:check"


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
    
    def __init__(self, shared_secret: str = "lighthouse-default-secret"):
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
            },
            AgentRole.AGENT: {
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS,
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
            },
            AgentRole.EXPERT_AGENT: {
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS, 
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
            },
            AgentRole.SYSTEM_AGENT: {
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS,
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.ADMIN_ACCESS,
            },
            AgentRole.ADMIN: {
                Permission.READ_EVENTS,
                Permission.WRITE_EVENTS,
                Permission.QUERY_EVENTS,
                Permission.HEALTH_CHECK,
                Permission.ADMIN_ACCESS,
            },
        }
    
    def authenticate(self, agent_id: str, token: str, role: AgentRole = AgentRole.AGENT) -> AgentIdentity:
        """Authenticate agent using HMAC token.
        
        Args:
            agent_id: Unique agent identifier
            token: HMAC authentication token
            role: Agent role (defaults to standard agent)
            
        Returns:
            AgentIdentity for authenticated agent
            
        Raises:
            AuthenticationError: If authentication fails
        """
        if not agent_id or not token:
            raise AuthenticationError("Agent ID and token are required")
        
        # For simple authentication, token is HMAC of agent_id + timestamp
        # Token format: "{timestamp}:{hmac_hex}"
        try:
            timestamp_str, hmac_hex = token.split(':', 1)
            timestamp = int(timestamp_str)
        except ValueError:
            raise AuthenticationError("Invalid token format")
        
        # Check if token is not too old (5 minute window)
        current_time = int(time.time())
        if abs(current_time - timestamp) > 300:  # 5 minutes
            raise AuthenticationError("Token expired or clock skew too large")
        
        # Verify HMAC
        expected_data = f"{agent_id}:{timestamp}".encode('utf-8')
        expected_hmac = hmac.new(self.shared_secret, expected_data, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(hmac_hex, expected_hmac):
            raise AuthenticationError("Invalid authentication token")
        
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
        """Create authentication token for agent (for testing/demo purposes).
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            HMAC authentication token
        """
        timestamp = int(time.time())
        data = f"{agent_id}:{timestamp}".encode('utf-8')
        hmac_digest = hmac.new(self.shared_secret, data, hashlib.sha256).hexdigest()
        return f"{timestamp}:{hmac_digest}"
    
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
        secret = "lighthouse-system-secret-change-in-production"
    
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