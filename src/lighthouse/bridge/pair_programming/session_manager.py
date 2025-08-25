"""
Pair Programming Session Manager

Manages real-time collaborative programming sessions between expert agents
through the FUSE filesystem interface.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class PairProgrammingSession:
    """Active pair programming session"""
    
    session_id: str
    participants: Set[str]
    created_at: datetime
    status: str = "active"  # "active", "paused", "completed"
    shared_workspace: Optional[str] = None


class PairProgrammingSessionManager:
    """
    Manages pair programming sessions for expert agents
    
    Provides collaborative workspace management through the FUSE
    filesystem for real-time expert agent coordination.
    """
    
    def __init__(self):
        self.sessions: Dict[str, PairProgrammingSession] = {}
        self._lock = asyncio.Lock()
        
        logger.info("Pair Programming Session Manager initialized")
    
    async def create_session(self, participant_ids: List[str]) -> str:
        """Create new pair programming session"""
        async with self._lock:
            session_id = str(uuid4())
            session = PairProgrammingSession(
                session_id=session_id,
                participants=set(participant_ids),
                created_at=datetime.utcnow()
            )
            
            self.sessions[session_id] = session
            
            logger.info(f"Created pair programming session {session_id} with participants: {participant_ids}")
            return session_id
    
    async def get_session(self, session_id: str) -> Optional[PairProgrammingSession]:
        """Get session by ID"""
        return self.sessions.get(session_id)
    
    async def end_session(self, session_id: str) -> bool:
        """End pair programming session"""
        async with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].status = "completed"
                logger.info(f"Ended pair programming session {session_id}")
                return True
            return False
    
    async def get_active_sessions(self) -> List[PairProgrammingSession]:
        """Get all active sessions"""
        return [s for s in self.sessions.values() if s.status == "active"]