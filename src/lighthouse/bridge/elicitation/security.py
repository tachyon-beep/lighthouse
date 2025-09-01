"""
Security components for elicitation: rate limiting, audit logging, and nonce management.
"""

import time
import secrets
import hashlib
import hmac
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
import asyncio
import logging

from .events import ElicitationSecurityEvent

logger = logging.getLogger(__name__)


class ElicitationSecurityError(Exception):
    """Security-related elicitation error."""
    def __init__(self, message: str, error_code: str = None, severity: str = "MEDIUM"):
        super().__init__(message)
        self.error_code = error_code
        self.severity = severity


class TokenBucket:
    """Token bucket for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """Consume tokens if available."""
        async with self._lock:
            await self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def _refill(self):
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bucket status."""
        return {
            "tokens_available": self.tokens,
            "capacity": self.capacity,
            "refill_rate": self.refill_rate
        }


class ElicitationRateLimiter:
    """Rate limiter for elicitation requests and responses."""
    
    def __init__(self, 
                 max_requests_per_minute: int = 10,
                 max_responses_per_minute: int = 20,
                 burst_allowance: int = 3):
        self.request_buckets: Dict[str, TokenBucket] = {}
        self.response_buckets: Dict[str, TokenBucket] = {}
        
        # Rate limits (configurable)
        self.max_requests_per_minute = max_requests_per_minute
        self.max_responses_per_minute = max_responses_per_minute
        self.burst_allowance = burst_allowance
        
        # Tracking for metrics
        self.violations: Dict[str, int] = {}
    
    async def allow_elicitation(self, agent_id: str) -> bool:
        """Check if agent can create new elicitation."""
        if agent_id not in self.request_buckets:
            self.request_buckets[agent_id] = TokenBucket(
                capacity=self.max_requests_per_minute + self.burst_allowance,
                refill_rate=self.max_requests_per_minute / 60  # per second
            )
        
        allowed = await self.request_buckets[agent_id].consume(1)
        if not allowed:
            self._record_violation(agent_id, "request")
        return allowed
    
    async def allow_response(self, agent_id: str) -> bool:
        """Check if agent can respond to elicitation."""
        if agent_id not in self.response_buckets:
            self.response_buckets[agent_id] = TokenBucket(
                capacity=self.max_responses_per_minute + self.burst_allowance,
                refill_rate=self.max_responses_per_minute / 60  # per second
            )
        
        allowed = await self.response_buckets[agent_id].consume(1)
        if not allowed:
            self._record_violation(agent_id, "response")
        return allowed
    
    def _record_violation(self, agent_id: str, violation_type: str):
        """Record rate limit violation."""
        key = f"{agent_id}:{violation_type}"
        self.violations[key] = self.violations.get(key, 0) + 1
    
    def get_rate_limit_status(self, agent_id: str) -> Dict[str, Any]:
        """Get current rate limit status for agent."""
        request_bucket = self.request_buckets.get(agent_id)
        response_bucket = self.response_buckets.get(agent_id)
        
        return {
            "requests_remaining": request_bucket.get_status()["tokens_available"] if request_bucket else self.max_requests_per_minute,
            "responses_remaining": response_bucket.get_status()["tokens_available"] if response_bucket else self.max_responses_per_minute,
            "max_requests_per_minute": self.max_requests_per_minute,
            "max_responses_per_minute": self.max_responses_per_minute,
            "violations": {
                "requests": self.violations.get(f"{agent_id}:request", 0),
                "responses": self.violations.get(f"{agent_id}:response", 0)
            }
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get rate limiter metrics."""
        return {
            "total_agents_tracked": len(set(list(self.request_buckets.keys()) + list(self.response_buckets.keys()))),
            "total_violations": sum(self.violations.values()),
            "violations_by_type": self.violations
        }


class NonceStore:
    """Secure nonce storage for replay protection."""
    
    def __init__(self):
        self.used_nonces: Set[str] = set()
        self.nonce_metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = 3600  # Clean up expired nonces every hour
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Start background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def shutdown(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def store_nonce(self, nonce: str, elicitation_id: str, timeout_seconds: int) -> bool:
        """Store nonce with expiration."""
        async with self._lock:
            if nonce in self.used_nonces:
                # Nonce already used - potential replay attack
                logger.warning(f"Replay attack detected: nonce {nonce[:8]}... already used")
                return False
            
            self.used_nonces.add(nonce)
            self.nonce_metadata[nonce] = {
                "elicitation_id": elicitation_id,
                "stored_at": time.time(),
                "expires_at": time.time() + timeout_seconds
            }
            return True
    
    async def consume_nonce(self, nonce: str) -> bool:
        """Consume nonce if available (for response verification)."""
        async with self._lock:
            if nonce not in self.used_nonces:
                # Nonce not found - invalid response
                return False
            
            # Mark as consumed (keep in set for replay protection)
            if nonce in self.nonce_metadata:
                self.nonce_metadata[nonce]["consumed"] = True
                self.nonce_metadata[nonce]["consumed_at"] = time.time()
            
            return True
    
    async def remove_nonce(self, elicitation_id: str):
        """Remove nonces associated with elicitation."""
        async with self._lock:
            to_remove = []
            for nonce, metadata in self.nonce_metadata.items():
                if metadata.get("elicitation_id") == elicitation_id:
                    to_remove.append(nonce)
            
            for nonce in to_remove:
                self.used_nonces.discard(nonce)
                del self.nonce_metadata[nonce]
    
    async def _cleanup_loop(self):
        """Background task to clean up expired nonces."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in nonce cleanup: {e}")
    
    async def _cleanup_expired(self):
        """Remove expired nonces."""
        async with self._lock:
            now = time.time()
            to_remove = []
            
            for nonce, metadata in self.nonce_metadata.items():
                if metadata.get("expires_at", now) < now:
                    to_remove.append(nonce)
            
            for nonce in to_remove:
                self.used_nonces.discard(nonce)
                del self.nonce_metadata[nonce]
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} expired nonces")


class ElicitationAuditLogger:
    """Comprehensive audit logging for elicitation security events."""
    
    def __init__(self, event_store=None):
        self.event_store = event_store
        self.security_log: list = []
        self.violation_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def log_elicitation_created(self,
                                     elicitation_id: str,
                                     from_agent: str,
                                     to_agent: str,
                                     message_hash: str,
                                     security_level: str):
        """Log elicitation creation."""
        event = {
            "event_type": "ELICITATION_CREATED",
            "elicitation_id": elicitation_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message_hash": message_hash,
            "security_level": security_level,
            "timestamp": time.time(),
            "event_id": f"audit_{secrets.token_hex(8)}"
        }
        
        await self._append_log(event)
        
        if self.event_store:
            await self.event_store.append(
                ElicitationSecurityEvent({
                    "violation_type": "AUDIT",
                    "agent": from_agent,
                    "severity": "INFO",
                    "elicitation_id": elicitation_id,
                    "details": event
                })
            )
    
    async def log_elicitation_response(self,
                                      elicitation_id: str,
                                      responding_agent: str,
                                      response_type: str,
                                      data_hash: Optional[str],
                                      security_level: str):
        """Log elicitation response."""
        event = {
            "event_type": "ELICITATION_RESPONSE",
            "elicitation_id": elicitation_id,
            "responding_agent": responding_agent,
            "response_type": response_type,
            "data_hash": data_hash,
            "security_level": security_level,
            "timestamp": time.time(),
            "event_id": f"audit_{secrets.token_hex(8)}"
        }
        
        await self._append_log(event)
    
    async def log_security_violation(self,
                                    event_type: str,
                                    agent: str,
                                    elicitation_id: Optional[str],
                                    severity: str,
                                    **details):
        """Log security violation."""
        event = {
            "event_type": event_type,
            "agent": agent,
            "elicitation_id": elicitation_id,
            "severity": severity,
            "details": details,
            "timestamp": time.time(),
            "event_id": f"violation_{secrets.token_hex(8)}"
        }
        
        await self._append_log(event)
        
        # Track violation counts
        async with self._lock:
            key = f"{agent}:{event_type}"
            self.violation_counts[key] = self.violation_counts.get(key, 0) + 1
        
        # Log to event store if available
        if self.event_store and severity in ["HIGH", "CRITICAL"]:
            await self.event_store.append(
                ElicitationSecurityEvent({
                    "violation_type": event_type,
                    "agent": agent,
                    "severity": severity,
                    "elicitation_id": elicitation_id,
                    "details": details
                })
            )
        
        # Log to standard logger
        logger.warning(f"Security violation: {event_type} by {agent} (severity: {severity})")
    
    async def log_validation_failure(self,
                                    elicitation_id: str,
                                    agent: str,
                                    validation_type: str):
        """Log validation failure."""
        await self.log_security_violation(
            event_type="VALIDATION_FAILURE",
            agent=agent,
            elicitation_id=elicitation_id,
            severity="MEDIUM",
            validation_type=validation_type
        )
    
    async def log_elicitation_expired(self,
                                     elicitation_id: str,
                                     agent: str):
        """Log elicitation expiration."""
        event = {
            "event_type": "ELICITATION_EXPIRED",
            "elicitation_id": elicitation_id,
            "agent": agent,
            "timestamp": time.time(),
            "event_id": f"audit_{secrets.token_hex(8)}"
        }
        
        await self._append_log(event)
    
    async def _append_log(self, event: Dict[str, Any]):
        """Append event to audit log."""
        async with self._lock:
            self.security_log.append(event)
            
            # Keep only last 10000 events in memory
            if len(self.security_log) > 10000:
                self.security_log = self.security_log[-10000:]
    
    def get_audit_summary(self) -> Dict[str, Any]:
        """Get audit summary statistics."""
        return {
            "total_events": len(self.security_log),
            "violation_counts": self.violation_counts,
            "recent_violations": [
                event for event in self.security_log[-100:]
                if "violation" in event.get("event_id", "")
            ]
        }
    
    def get_agent_history(self, agent_id: str) -> list:
        """Get audit history for specific agent."""
        return [
            event for event in self.security_log
            if event.get("agent") == agent_id or 
               event.get("from_agent") == agent_id or
               event.get("responding_agent") == agent_id
        ]