"""
CoordinatedAuthenticator Singleton

Provides a single shared authentication state across all EventStore instances
to solve the authentication isolation problem in the MCP system.
"""

import asyncio
import threading
import logging
from typing import Optional, Dict, Any
from .auth import SimpleAuthenticator, AgentIdentity

logger = logging.getLogger(__name__)


class CoordinatedAuthenticator:
    """
    Singleton authenticator that provides shared authentication state
    across all EventStore instances to prevent authentication isolation.
    """
    
    _instance: Optional['CoordinatedAuthenticator'] = None
    _lock = threading.Lock()
    
    def __init__(self, auth_secret: str):
        """Initialize the coordinated authenticator"""
        self._authenticator = SimpleAuthenticator(shared_secret=auth_secret)
        self._auth_lock = asyncio.Lock()
        logger.info("🏗️  CoordinatedAuthenticator singleton created")
    
    @classmethod
    def get_instance(cls, auth_secret: str = None) -> 'CoordinatedAuthenticator':
        """Get the singleton instance of CoordinatedAuthenticator"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    if auth_secret is None:
                        import secrets
                        auth_secret = secrets.token_urlsafe(32)
                    cls._instance = CoordinatedAuthenticator(auth_secret)
                    logger.info("🔐 CoordinatedAuthenticator singleton initialized")
        
        return cls._instance
    
    async def authenticate(self, agent_id: str, token: str, role) -> AgentIdentity:
        """Authenticate agent with coordinated state"""
        async with self._auth_lock:
            identity = self._authenticator.authenticate(agent_id, token, role)
            logger.info(f"✅ Agent {agent_id} authenticated in coordinated authenticator")
            return identity
    
    def create_token(self, agent_id: str) -> str:
        """Create authentication token for agent"""
        return self._authenticator.create_token(agent_id)
    
    def get_authenticated_agent(self, agent_id: str) -> Optional[AgentIdentity]:
        """Get authenticated agent identity from shared state"""
        return self._authenticator.get_authenticated_agent(agent_id)
    
    def revoke_agent_access(self, agent_id: str) -> None:
        """Revoke agent access from shared state"""
        self._authenticator.revoke_agent_access(agent_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get authenticator statistics"""
        authenticated_count = len(self._authenticator._authenticated_agents)
        return {
            "authenticated_agents": authenticated_count,
            "authenticator_type": "CoordinatedAuthenticator",
            "instance_id": id(self)
        }