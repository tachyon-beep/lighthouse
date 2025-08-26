#!/usr/bin/env python3

"""
Session Security Module for Lighthouse Bridge

This module provides comprehensive session security validation, including
session token validation, timeout management, concurrent session limits,
and hijacking prevention mechanisms.
"""

import time
import hmac
import hashlib
import secrets
import logging
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """Session states for validation"""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPICIOUS = "suspicious"
    HIJACKED = "hijacked"


@dataclass
class SessionInfo:
    """Represents an active agent session"""
    session_id: str
    agent_id: str
    session_token: str
    created_at: float
    last_activity: float
    ip_address: str = ""
    user_agent: str = ""
    command_count: int = 0
    state: SessionState = SessionState.ACTIVE
    security_flags: Set[str] = field(default_factory=set)


class SessionSecurityValidator:
    """Comprehensive session security validation"""
    
    def __init__(self, secret_key: str, session_timeout: int = 3600, 
                 max_concurrent_sessions: int = 3):
        self.secret_key = secret_key
        self.session_timeout = session_timeout
        self.max_concurrent_sessions = max_concurrent_sessions
        
        # Active sessions tracking
        self.active_sessions: Dict[str, SessionInfo] = {}
        self.agent_sessions: Dict[str, List[str]] = {}  # agent_id -> [session_ids]
        
        # Security monitoring
        self.suspicious_activities: List[Dict[str, Any]] = []
        self.hijacking_attempts: List[Dict[str, Any]] = []
        
    def create_session(self, agent_id: str, ip_address: str = "", 
                      user_agent: str = "") -> SessionInfo:
        """Create a new secure session"""
        
        # Check concurrent session limit
        agent_session_count = len(self.agent_sessions.get(agent_id, []))
        if agent_session_count >= self.max_concurrent_sessions:
            # Revoke oldest session
            oldest_session_id = self.agent_sessions[agent_id][0]
            self.revoke_session(oldest_session_id, "concurrent_limit_exceeded")
        
        # Generate secure session
        session_id = secrets.token_hex(16)
        session_token = self._generate_session_token(session_id, agent_id)
        
        session = SessionInfo(
            session_id=session_id,
            agent_id=agent_id,
            session_token=session_token,
            created_at=time.time(),
            last_activity=time.time(),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Store session
        self.active_sessions[session_id] = session
        if agent_id not in self.agent_sessions:
            self.agent_sessions[agent_id] = []
        self.agent_sessions[agent_id].append(session_id)
        
        logger.info(f"Session created for agent {agent_id}: {session_id}")
        return session
    
    def validate_session(self, session_token: str, agent_id: str, 
                        ip_address: str = "", user_agent: str = "") -> bool:
        """Validate session token and detect hijacking attempts"""
        
        try:
            # Find session by token
            session = None
            for sid, sess in self.active_sessions.items():
                if sess.session_token == session_token:
                    session = sess
                    break
            
            if not session:
                logger.warning(f"Session validation failed: token not found for agent {agent_id}")
                logger.debug(f"Available sessions: {len(self.active_sessions)}, looking for token: {session_token[:50]}...")
                for sid, sess in list(self.active_sessions.items())[:3]:
                    logger.debug(f"Session {sid}: agent={sess.agent_id}, token={sess.session_token[:50]}...")
                return False
            
            # Validate agent ownership
            if session.agent_id != agent_id:
                self._record_hijacking_attempt(session_token, agent_id, "agent_mismatch")
                logger.warning(f"Session hijacking attempt: token for {session.agent_id} used by {agent_id}")
                return False
            
            # Check session expiration
            if self._is_session_expired(session):
                self.revoke_session(session.session_id, "expired")
                logger.info(f"Session expired for agent {agent_id}")
                return False
            
            # Check for suspicious activity
            if self._detect_suspicious_activity(session, ip_address, user_agent):
                session.state = SessionState.SUSPICIOUS
                session.security_flags.add("suspicious_activity")
                logger.warning(f"Suspicious activity detected for session {session.session_id}")
                return False
            
            # Update session activity
            session.last_activity = time.time()
            session.command_count += 1
            
            # Check for session abuse
            if self._detect_session_abuse(session):
                session.state = SessionState.SUSPICIOUS
                session.security_flags.add("session_abuse")
                logger.warning(f"Session abuse detected for session {session.session_id}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False
    
    def validate_websocket_hijacking(self, websocket_url: str, agent_id: str) -> bool:
        """Validate WebSocket connection against hijacking"""
        
        # Check if WebSocket URL is legitimate for this agent
        expected_pattern = f"ws://localhost:8765/agent/{agent_id}"
        if websocket_url != expected_pattern:
            self._record_hijacking_attempt(websocket_url, agent_id, "websocket_url_mismatch")
            logger.warning(f"WebSocket hijacking attempt: invalid URL {websocket_url} for agent {agent_id}")
            return False
        
        # Additional WebSocket security checks could be added here
        return True
    
    def validate_message_interception(self, message: Dict[str, Any], agent_id: str) -> bool:
        """Validate message against interception attacks"""
        
        # Check message authenticity
        if message.get("from") != agent_id:
            self._record_hijacking_attempt(str(message), agent_id, "message_from_mismatch")
            logger.warning(f"Message interception attempt: message from {message.get('from')} for agent {agent_id}")
            return False
        
        # Check for replay attacks
        if self._detect_message_replay(message, agent_id):
            logger.warning(f"Message replay attack detected for agent {agent_id}")
            return False
        
        return True
    
    def revoke_session(self, session_id: str, reason: str = "manual"):
        """Revoke a session"""
        
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session.state = SessionState.REVOKED
            
            # Remove from active sessions
            del self.active_sessions[session_id]
            
            # Remove from agent sessions
            if session.agent_id in self.agent_sessions:
                if session_id in self.agent_sessions[session.agent_id]:
                    self.agent_sessions[session.agent_id].remove(session_id)
            
            logger.info(f"Session revoked: {session_id} (reason: {reason})")
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session in self.active_sessions.items():
            if self._is_session_expired(session):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            self.revoke_session(session_id, "expired")
        
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    def get_security_report(self) -> Dict[str, Any]:
        """Generate session security report"""
        
        return {
            "active_sessions": len(self.active_sessions),
            "suspicious_activities": len(self.suspicious_activities),
            "hijacking_attempts": len(self.hijacking_attempts),
            "session_timeout": self.session_timeout,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "recent_hijacking_attempts": self.hijacking_attempts[-10:],  # Last 10
            "session_states": {
                state.value: sum(1 for s in self.active_sessions.values() if s.state == state)
                for state in SessionState
            }
        }
    
    def _generate_session_token(self, session_id: str, agent_id: str) -> str:
        """Generate cryptographically secure session token"""
        
        # Create HMAC-based token
        message = f"{session_id}:{agent_id}:{time.time()}"
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Combine message and signature
        token = f"{message}:{signature}"
        return token
    
    def _is_session_expired(self, session: SessionInfo) -> bool:
        """Check if session is expired"""
        
        return (time.time() - session.last_activity) > self.session_timeout
    
    def _detect_suspicious_activity(self, session: SessionInfo, 
                                   ip_address: str, user_agent: str) -> bool:
        """Detect suspicious session activity"""
        
        # IP address change detection
        if session.ip_address and ip_address and session.ip_address != ip_address:
            self.suspicious_activities.append({
                "type": "ip_change",
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "old_ip": session.ip_address,
                "new_ip": ip_address,
                "timestamp": time.time()
            })
            return True
        
        # User agent change detection
        if session.user_agent and user_agent and session.user_agent != user_agent:
            self.suspicious_activities.append({
                "type": "user_agent_change", 
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "old_ua": session.user_agent,
                "new_ua": user_agent,
                "timestamp": time.time()
            })
            return True
        
        return False
    
    def _detect_session_abuse(self, session: SessionInfo) -> bool:
        """Detect session abuse patterns"""
        
        # High command rate detection (more than 100 commands per minute)
        session_duration = time.time() - session.created_at
        if session_duration > 60 and session.command_count / (session_duration / 60) > 100:
            return True
        
        # Long-running session detection (more than 8 hours)
        if session_duration > 8 * 3600:
            return True
        
        return False
    
    def _detect_message_replay(self, message: Dict[str, Any], agent_id: str) -> bool:
        """Detect message replay attacks"""
        
        # Simple replay detection based on message content and timing
        message_hash = hashlib.sha256(str(message).encode()).hexdigest()
        
        # Check if we've seen this exact message recently
        for activity in self.suspicious_activities[-100:]:  # Check last 100 activities
            if (activity.get("type") == "message_processed" and 
                activity.get("agent_id") == agent_id and
                activity.get("message_hash") == message_hash and
                time.time() - activity.get("timestamp", 0) < 300):  # Within 5 minutes
                return True
        
        # Record this message
        self.suspicious_activities.append({
            "type": "message_processed",
            "agent_id": agent_id,
            "message_hash": message_hash,
            "timestamp": time.time()
        })
        
        return False
    
    def _record_hijacking_attempt(self, token_or_data: str, agent_id: str, attack_type: str):
        """Record hijacking attempt for analysis"""
        
        self.hijacking_attempts.append({
            "attack_type": attack_type,
            "target_agent": agent_id,
            "attack_data": token_or_data[:50] + "..." if len(token_or_data) > 50 else token_or_data,
            "timestamp": time.time(),
            "source_ip": "unknown"  # Would be populated in real implementation
        })