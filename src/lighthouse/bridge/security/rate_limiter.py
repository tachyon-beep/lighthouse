"""
Advanced DoS Protection and Rate Limiting

Implements multiple layers of rate limiting and DoS protection
as required by Plan Charlie Phase 1.
"""

import asyncio
import time
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum
import hashlib
import threading

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Rate limit exceeded."""
    pass


class DoSProtectionLevel(Enum):
    """DoS protection levels."""
    NONE = "none"
    BASIC = "basic" 
    ENHANCED = "enhanced"
    MAXIMUM = "maximum"


@dataclass
class RateLimit:
    """Rate limit configuration."""
    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int
    window_size_seconds: int = 60
    
    def __post_init__(self):
        """Validate rate limit configuration."""
        if self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if self.requests_per_hour <= 0:
            raise ValueError("requests_per_hour must be positive")
        if self.burst_limit <= 0:
            raise ValueError("burst_limit must be positive")


@dataclass
class ClientMetrics:
    """Metrics for a client."""
    request_count_1min: int = 0
    request_count_1hour: int = 0
    request_history: deque = None
    burst_count: int = 0
    last_request_time: float = 0
    suspicious_activity_score: float = 0
    blocked_until: Optional[float] = None
    
    def __post_init__(self):
        if self.request_history is None:
            self.request_history = deque(maxlen=1000)


class EnhancedRateLimiter:
    """
    Enterprise-grade rate limiter with DoS protection.
    
    Features:
    - Per-client rate limiting with multiple time windows
    - Burst protection
    - Adaptive rate limiting based on system load
    - Suspicious activity detection
    - Temporary blocking for bad actors
    - Memory-efficient sliding windows
    """
    
    def __init__(self, 
                 protection_level: DoSProtectionLevel = DoSProtectionLevel.ENHANCED,
                 default_rate_limit: Optional[RateLimit] = None):
        """
        Initialize rate limiter.
        
        Args:
            protection_level: DoS protection level
            default_rate_limit: Default rate limit (uses reasonable defaults if None)
        """
        self.protection_level = protection_level
        self.default_rate_limit = default_rate_limit or RateLimit(
            requests_per_minute=100,
            requests_per_hour=1000,
            burst_limit=20,
            window_size_seconds=60
        )
        
        # Client tracking
        self.client_metrics: Dict[str, ClientMetrics] = defaultdict(ClientMetrics)
        self.rate_limits: Dict[str, RateLimit] = {}
        self.blocked_clients: Set[str] = set()
        
        # System-wide protection
        self.global_request_count = 0
        self.global_request_history = deque(maxlen=10000)
        self.system_overload_threshold = 1000  # requests per minute
        self.is_under_attack = False
        
        # Threading safety
        self.lock = threading.RLock()
        
        # Cleanup task
        self.cleanup_task = None
        self.start_cleanup_task()
    
    def set_client_rate_limit(self, client_id: str, rate_limit: RateLimit) -> None:
        """Set custom rate limit for specific client."""
        with self.lock:
            self.rate_limits[client_id] = rate_limit
    
    def check_rate_limit(self, client_id: str, request_weight: int = 1) -> bool:
        """
        Check if client is within rate limits.
        
        Args:
            client_id: Client identifier
            request_weight: Weight of the request (default: 1)
            
        Returns:
            True if request is allowed
            
        Raises:
            RateLimitError: If rate limit exceeded
        """
        if self.protection_level == DoSProtectionLevel.NONE:
            return True
        
        current_time = time.time()
        
        with self.lock:
            # Check if client is blocked
            if client_id in self.blocked_clients:
                metrics = self.client_metrics[client_id]
                if metrics.blocked_until and current_time < metrics.blocked_until:
                    raise RateLimitError(
                        f"Client {client_id} is temporarily blocked until "
                        f"{datetime.fromtimestamp(metrics.blocked_until)}"
                    )
                else:
                    # Unblock client
                    self.blocked_clients.discard(client_id)
                    metrics.blocked_until = None
            
            # Get rate limit for client
            rate_limit = self.rate_limits.get(client_id, self.default_rate_limit)
            metrics = self.client_metrics[client_id]
            
            # Update global statistics
            self.global_request_count += request_weight
            self.global_request_history.append(current_time)
            
            # Check system overload
            if self._is_system_overloaded():
                if self.protection_level in [DoSProtectionLevel.ENHANCED, DoSProtectionLevel.MAXIMUM]:
                    # Reduce rate limits during overload
                    rate_limit = RateLimit(
                        requests_per_minute=max(10, rate_limit.requests_per_minute // 4),
                        requests_per_hour=max(100, rate_limit.requests_per_hour // 4),
                        burst_limit=max(5, rate_limit.burst_limit // 2)
                    )
            
            # Update client metrics
            self._update_client_metrics(client_id, current_time, request_weight, metrics)
            
            # Check burst limit
            if self._check_burst_limit(metrics, rate_limit, current_time):
                return True
            
            # Check minute limit
            if self._check_minute_limit(metrics, rate_limit):
                return True
            
            # Check hour limit  
            if self._check_hour_limit(metrics, rate_limit):
                return True
            
            # All limits exceeded
            return False
    
    def _update_client_metrics(self, client_id: str, current_time: float, 
                              request_weight: int, metrics: ClientMetrics) -> None:
        """Update client metrics with new request."""
        # Add to request history
        metrics.request_history.append(current_time)
        
        # Update counters
        metrics.request_count_1min += request_weight
        metrics.request_count_1hour += request_weight
        
        # Calculate time since last request
        time_since_last = current_time - metrics.last_request_time
        metrics.last_request_time = current_time
        
        # Detect suspicious activity
        if time_since_last < 0.1:  # More than 10 requests per second
            metrics.suspicious_activity_score += 10
        elif time_since_last < 1.0:  # More than 1 request per second
            metrics.suspicious_activity_score += 1
        else:
            # Decay suspicious activity score
            metrics.suspicious_activity_score = max(0, metrics.suspicious_activity_score - 0.1)
        
        # Block clients with high suspicious activity
        if (self.protection_level == DoSProtectionLevel.MAXIMUM and 
            metrics.suspicious_activity_score > 50):
            self._block_client(client_id, 300)  # Block for 5 minutes
    
    def _check_burst_limit(self, metrics: ClientMetrics, rate_limit: RateLimit, 
                          current_time: float) -> bool:
        """Check burst limit."""
        # Count requests in last 10 seconds for burst detection
        burst_window = current_time - 10
        recent_requests = sum(1 for t in metrics.request_history if t > burst_window)
        
        if recent_requests > rate_limit.burst_limit:
            raise RateLimitError(
                f"Burst limit exceeded: {recent_requests} requests in 10 seconds "
                f"(limit: {rate_limit.burst_limit})"
            )
        return True
    
    def _check_minute_limit(self, metrics: ClientMetrics, rate_limit: RateLimit) -> bool:
        """Check per-minute limit."""
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Count requests in last minute
        minute_requests = sum(1 for t in metrics.request_history if t > minute_ago)
        
        if minute_requests >= rate_limit.requests_per_minute:
            raise RateLimitError(
                f"Rate limit exceeded: {minute_requests} requests per minute "
                f"(limit: {rate_limit.requests_per_minute})"
            )
        return True
    
    def _check_hour_limit(self, metrics: ClientMetrics, rate_limit: RateLimit) -> bool:
        """Check per-hour limit."""
        current_time = time.time()
        hour_ago = current_time - 3600
        
        # Count requests in last hour
        hour_requests = sum(1 for t in metrics.request_history if t > hour_ago)
        
        if hour_requests >= rate_limit.requests_per_hour:
            raise RateLimitError(
                f"Hourly rate limit exceeded: {hour_requests} requests per hour "
                f"(limit: {rate_limit.requests_per_hour})"
            )
        return True
    
    def _is_system_overloaded(self) -> bool:
        """Check if system is under DoS attack."""
        if len(self.global_request_history) < 100:
            return False
        
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Count global requests in last minute
        recent_requests = sum(1 for t in self.global_request_history if t > minute_ago)
        
        was_under_attack = self.is_under_attack
        self.is_under_attack = recent_requests > self.system_overload_threshold
        
        if self.is_under_attack and not was_under_attack:
            logger.warning(
                f"DoS attack detected: {recent_requests} requests/minute "
                f"(threshold: {self.system_overload_threshold})"
            )
        elif not self.is_under_attack and was_under_attack:
            logger.info("DoS attack subsided, returning to normal operation")
        
        return self.is_under_attack
    
    def _block_client(self, client_id: str, duration_seconds: int) -> None:
        """Block client for specified duration."""
        with self.lock:
            self.blocked_clients.add(client_id)
            self.client_metrics[client_id].blocked_until = time.time() + duration_seconds
            
            logger.warning(
                f"Blocked client {client_id} for {duration_seconds} seconds "
                f"due to suspicious activity"
            )
    
    def get_client_status(self, client_id: str) -> Dict[str, Any]:
        """Get detailed status for client."""
        with self.lock:
            metrics = self.client_metrics.get(client_id)
            if not metrics:
                return {"exists": False}
            
            current_time = time.time()
            minute_ago = current_time - 60
            hour_ago = current_time - 3600
            
            minute_requests = sum(1 for t in metrics.request_history if t > minute_ago)
            hour_requests = sum(1 for t in metrics.request_history if t > hour_ago)
            
            return {
                "exists": True,
                "requests_per_minute": minute_requests,
                "requests_per_hour": hour_requests,
                "suspicious_activity_score": metrics.suspicious_activity_score,
                "is_blocked": client_id in self.blocked_clients,
                "blocked_until": metrics.blocked_until,
                "last_request_time": metrics.last_request_time,
                "total_requests": len(metrics.request_history)
            }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system-wide rate limiting status."""
        current_time = time.time()
        minute_ago = current_time - 60
        
        recent_requests = sum(1 for t in self.global_request_history if t > minute_ago)
        
        return {
            "total_clients": len(self.client_metrics),
            "blocked_clients": len(self.blocked_clients),
            "requests_per_minute": recent_requests,
            "is_under_attack": self.is_under_attack,
            "protection_level": self.protection_level.value,
            "total_requests": len(self.global_request_history)
        }
    
    def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of old metrics."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                self._cleanup_old_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")
    
    def _cleanup_old_metrics(self) -> None:
        """Clean up old client metrics."""
        current_time = time.time()
        cleanup_threshold = current_time - 3600  # Keep 1 hour of history
        
        with self.lock:
            clients_to_remove = []
            
            for client_id, metrics in self.client_metrics.items():
                # Remove old requests from history
                while (metrics.request_history and 
                       metrics.request_history[0] < cleanup_threshold):
                    metrics.request_history.popleft()
                
                # Remove clients with no recent activity
                if (not metrics.request_history or 
                    metrics.last_request_time < cleanup_threshold):
                    clients_to_remove.append(client_id)
            
            # Remove inactive clients
            for client_id in clients_to_remove:
                del self.client_metrics[client_id]
                self.blocked_clients.discard(client_id)
                self.rate_limits.pop(client_id, None)
            
            # Clean up global history
            while (self.global_request_history and 
                   self.global_request_history[0] < cleanup_threshold):
                self.global_request_history.popleft()
    
    async def shutdown(self) -> None:
        """Shutdown rate limiter."""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass


# Global rate limiter instance
_global_rate_limiter: Optional[EnhancedRateLimiter] = None


def get_global_rate_limiter() -> EnhancedRateLimiter:
    """Get global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        protection_level = DoSProtectionLevel.ENHANCED
        if hasattr(os, 'environ'):
            import os
            level_str = os.environ.get('LIGHTHOUSE_DOS_PROTECTION', 'enhanced').lower()
            try:
                protection_level = DoSProtectionLevel(level_str)
            except ValueError:
                protection_level = DoSProtectionLevel.ENHANCED
        
        _global_rate_limiter = EnhancedRateLimiter(protection_level=protection_level)
    
    return _global_rate_limiter


def check_rate_limit(client_id: str, request_weight: int = 1) -> bool:
    """
    Check rate limit for client using global rate limiter.
    
    Args:
        client_id: Client identifier
        request_weight: Weight of request (default: 1)
        
    Returns:
        True if allowed
        
    Raises:
        RateLimitError: If rate limit exceeded
    """
    return get_global_rate_limiter().check_rate_limit(client_id, request_weight)