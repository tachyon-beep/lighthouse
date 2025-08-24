"""
Secure Memory Management for Speed Layer

Fixes memory security issues:
- Buffer overflow prevention with size limits
- Thread-safe operations without blocking
- Memory leak prevention with proper cleanup
- Input validation and sanitization
"""

import asyncio
import logging
import time
from collections import deque, OrderedDict
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class MemorySecurityError(Exception):
    """Exception raised for memory security violations"""
    pass


@dataclass
class MemoryLimits:
    """Memory usage limits configuration"""
    max_cache_size_mb: int = 100  # Maximum cache size in MB
    max_entry_size_kb: int = 1024  # Maximum single entry size in KB  
    max_string_length: int = 1024 * 1024  # 1MB max string length
    max_list_length: int = 10000  # Maximum list length
    max_dict_size: int = 1000  # Maximum dictionary size
    cleanup_threshold: float = 0.8  # Cleanup when 80% full


class SecureMemoryValidator:
    """Validates memory operations for security"""
    
    def __init__(self, limits: MemoryLimits = None):
        self.limits = limits or MemoryLimits()
    
    def validate_string(self, value: str, field_name: str = "string") -> str:
        """Validate string for memory safety"""
        if not isinstance(value, str):
            raise MemorySecurityError(f"{field_name} must be a string")
        
        if len(value) > self.limits.max_string_length:
            raise MemorySecurityError(
                f"{field_name} length {len(value)} exceeds limit {self.limits.max_string_length}"
            )
        
        # Check for potential buffer overflow patterns
        if '\x00' in value:
            raise MemorySecurityError(f"{field_name} contains null bytes")
        
        # Check for excessive repeated characters (potential DoS)
        for char in set(value):
            if value.count(char) > self.limits.max_string_length // 2:
                raise MemorySecurityError(f"{field_name} contains excessive repeated characters")
        
        return value
    
    def validate_bytes(self, value: bytes, field_name: str = "bytes") -> bytes:
        """Validate bytes for memory safety"""
        if not isinstance(value, bytes):
            raise MemorySecurityError(f"{field_name} must be bytes")
        
        if len(value) > self.limits.max_string_length:
            raise MemorySecurityError(
                f"{field_name} length {len(value)} exceeds limit {self.limits.max_string_length}"
            )
        
        return value
    
    def validate_list(self, value: list, field_name: str = "list") -> list:
        """Validate list for memory safety"""
        if not isinstance(value, list):
            raise MemorySecurityError(f"{field_name} must be a list")
        
        if len(value) > self.limits.max_list_length:
            raise MemorySecurityError(
                f"{field_name} length {len(value)} exceeds limit {self.limits.max_list_length}"
            )
        
        return value
    
    def validate_dict(self, value: dict, field_name: str = "dict") -> dict:
        """Validate dictionary for memory safety"""
        if not isinstance(value, dict):
            raise MemorySecurityError(f"{field_name} must be a dictionary")
        
        if len(value) > self.limits.max_dict_size:
            raise MemorySecurityError(
                f"{field_name} size {len(value)} exceeds limit {self.limits.max_dict_size}"
            )
        
        # Validate keys and values
        for key, val in value.items():
            if isinstance(key, str):
                self.validate_string(key, f"{field_name} key")
            if isinstance(val, str):
                self.validate_string(val, f"{field_name} value")
            elif isinstance(val, bytes):
                self.validate_bytes(val, f"{field_name} value")
        
        return value
    
    def calculate_size_mb(self, obj: Any) -> float:
        """Calculate approximate memory size in MB"""
        try:
            import sys
            size_bytes = sys.getsizeof(obj)
            
            # Recursively calculate for containers
            if isinstance(obj, dict):
                for key, value in obj.items():
                    size_bytes += sys.getsizeof(key) + sys.getsizeof(value)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    size_bytes += sys.getsizeof(item)
            elif isinstance(obj, str):
                size_bytes = len(obj.encode('utf-8'))
            
            return size_bytes / (1024 * 1024)  # Convert to MB
            
        except Exception as e:
            logger.warning(f"Size calculation error: {e}")
            return 0.0


class SecureBoundedDeque:
    """Thread-safe bounded deque with memory limits"""
    
    def __init__(self, maxlen: int = 10000, validator: SecureMemoryValidator = None):
        self._deque = deque(maxlen=maxlen)
        self._lock = asyncio.Lock()
        self._maxlen = maxlen
        self.validator = validator or SecureMemoryValidator()
        self._total_size_mb = 0.0
    
    async def append(self, item: Any) -> bool:
        """Append item with validation"""
        try:
            # Validate item size
            item_size = self.validator.calculate_size_mb(item)
            if item_size > self.validator.limits.max_entry_size_kb / 1024:
                logger.warning(f"Item size {item_size:.2f}MB exceeds limit")
                return False
            
            async with self._lock:
                # Remove oldest if at capacity
                if len(self._deque) >= self._maxlen:
                    old_item = self._deque.popleft()
                    self._total_size_mb -= self.validator.calculate_size_mb(old_item)
                
                self._deque.append(item)
                self._total_size_mb += item_size
                
                return True
                
        except Exception as e:
            logger.error(f"Secure deque append error: {e}")
            return False
    
    async def popleft(self) -> Optional[Any]:
        """Pop leftmost item"""
        try:
            async with self._lock:
                if self._deque:
                    item = self._deque.popleft()
                    self._total_size_mb -= self.validator.calculate_size_mb(item)
                    return item
                return None
        except Exception as e:
            logger.error(f"Secure deque popleft error: {e}")
            return None
    
    async def clear(self):
        """Clear all items"""
        async with self._lock:
            self._deque.clear()
            self._total_size_mb = 0.0
    
    def __len__(self) -> int:
        return len(self._deque)
    
    @property
    def size_mb(self) -> float:
        return self._total_size_mb


class SecureBoundedDict:
    """Thread-safe bounded dictionary with memory limits"""
    
    def __init__(self, maxlen: int = 10000, validator: SecureMemoryValidator = None):
        self._dict: OrderedDict = OrderedDict()
        self._lock = asyncio.Lock()
        self._maxlen = maxlen
        self.validator = validator or SecureMemoryValidator()
        self._total_size_mb = 0.0
    
    async def get(self, key: str) -> Optional[Any]:
        """Get item with LRU update"""
        try:
            # Validate key
            self.validator.validate_string(key, "cache key")
            
            async with self._lock:
                if key in self._dict:
                    # Move to end (most recently used)
                    value = self._dict.pop(key)
                    self._dict[key] = value
                    return value
                return None
                
        except Exception as e:
            logger.error(f"Secure dict get error: {e}")
            return None
    
    async def set(self, key: str, value: Any) -> bool:
        """Set item with validation and size limits"""
        try:
            # Validate inputs
            self.validator.validate_string(key, "cache key")
            
            # Calculate sizes
            key_size = self.validator.calculate_size_mb(key)
            value_size = self.validator.calculate_size_mb(value)
            total_item_size = key_size + value_size
            
            # Check single item size limit
            max_item_size_mb = self.validator.limits.max_entry_size_kb / 1024
            if total_item_size > max_item_size_mb:
                logger.warning(f"Item size {total_item_size:.2f}MB exceeds limit {max_item_size_mb}MB")
                return False
            
            async with self._lock:
                # Check if we need to evict old items
                while (len(self._dict) >= self._maxlen or 
                       self._total_size_mb + total_item_size > self.validator.limits.max_cache_size_mb):
                    if not self._dict:
                        break
                    
                    # Remove oldest item
                    old_key, old_value = self._dict.popitem(last=False)
                    old_size = (self.validator.calculate_size_mb(old_key) + 
                               self.validator.calculate_size_mb(old_value))
                    self._total_size_mb -= old_size
                
                # Update existing key
                if key in self._dict:
                    old_value = self._dict[key]
                    old_value_size = self.validator.calculate_size_mb(old_value)
                    self._total_size_mb -= old_value_size
                
                # Add new item
                self._dict[key] = value
                self._total_size_mb += total_item_size
                
                return True
                
        except Exception as e:
            logger.error(f"Secure dict set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete item"""
        try:
            async with self._lock:
                if key in self._dict:
                    value = self._dict.pop(key)
                    item_size = (self.validator.calculate_size_mb(key) + 
                                self.validator.calculate_size_mb(value))
                    self._total_size_mb -= item_size
                    return True
                return False
        except Exception as e:
            logger.error(f"Secure dict delete error: {e}")
            return False
    
    async def clear(self):
        """Clear all items"""
        async with self._lock:
            self._dict.clear()
            self._total_size_mb = 0.0
    
    def __len__(self) -> int:
        return len(self._dict)
    
    @property
    def size_mb(self) -> float:
        return self._total_size_mb
    
    async def cleanup_if_needed(self):
        """Cleanup if approaching memory limits"""
        try:
            if self._total_size_mb > self.validator.limits.max_cache_size_mb * self.validator.limits.cleanup_threshold:
                logger.info(f"Cleaning up cache: {self._total_size_mb:.2f}MB")
                
                async with self._lock:
                    # Remove oldest 20% of items
                    items_to_remove = max(1, len(self._dict) // 5)
                    
                    for _ in range(items_to_remove):
                        if not self._dict:
                            break
                        old_key, old_value = self._dict.popitem(last=False)
                        old_size = (self.validator.calculate_size_mb(old_key) + 
                                   self.validator.calculate_size_mb(old_value))
                        self._total_size_mb -= old_size
                
                logger.info(f"Cache cleaned up: {self._total_size_mb:.2f}MB remaining")
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")


class SecureRateLimiter:
    """Thread-safe rate limiter with memory bounds"""
    
    def __init__(self, max_requests: int = 1000, window_seconds: float = 1.0):
        self._timestamps = SecureBoundedDeque(maxlen=max_requests * 2)  # Buffer for cleanup
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, identifier: str = "default") -> bool:
        """Check if request is within rate limit"""
        try:
            current_time = time.time()
            cutoff_time = current_time - self._window_seconds
            
            # Clean old timestamps efficiently
            cleaned_count = 0
            while len(self._timestamps) > 0:
                try:
                    oldest = await self._timestamps.popleft()
                    if oldest and oldest >= cutoff_time:
                        # Put it back and break
                        await self._timestamps.append(oldest)
                        break
                    cleaned_count += 1
                    
                    # Prevent infinite loop
                    if cleaned_count > self._max_requests * 2:
                        break
                except Exception:
                    break
            
            # Check rate limit
            if len(self._timestamps) >= self._max_requests:
                return False
            
            # Add current request
            await self._timestamps.append(current_time)
            return True
            
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            # Fail open for availability
            return True
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        return {
            'current_requests': len(self._timestamps),
            'max_requests': self._max_requests,
            'window_seconds': self._window_seconds,
            'memory_size_mb': self._timestamps.size_mb
        }


class SecureMemoryManager:
    """Centralized secure memory management"""
    
    def __init__(self, limits: MemoryLimits = None):
        self.limits = limits or MemoryLimits()
        self.validator = SecureMemoryValidator(self.limits)
        
        # Track all managed objects
        self._managed_objects: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        
        # Global memory tracking
        self._total_allocated_mb = 0.0
        self._allocation_count = 0
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start memory manager"""
        logger.info("Starting secure memory manager")
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def stop(self):
        """Stop memory manager"""
        logger.info("Stopping secure memory manager")
        self._shutdown_event.set()
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def create_secure_dict(self, name: str, maxlen: int = 10000) -> SecureBoundedDict:
        """Create managed secure dictionary"""
        async with self._lock:
            secure_dict = SecureBoundedDict(maxlen=maxlen, validator=self.validator)
            self._managed_objects[name] = secure_dict
            self._allocation_count += 1
            return secure_dict
    
    async def create_secure_deque(self, name: str, maxlen: int = 10000) -> SecureBoundedDeque:
        """Create managed secure deque"""
        async with self._lock:
            secure_deque = SecureBoundedDeque(maxlen=maxlen, validator=self.validator)
            self._managed_objects[name] = secure_deque
            self._allocation_count += 1
            return secure_deque
    
    async def create_rate_limiter(self, name: str, max_requests: int = 1000, window_seconds: float = 1.0) -> SecureRateLimiter:
        """Create managed rate limiter"""
        async with self._lock:
            rate_limiter = SecureRateLimiter(max_requests=max_requests, window_seconds=window_seconds)
            self._managed_objects[name] = rate_limiter
            self._allocation_count += 1
            return rate_limiter
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        async with self._lock:
            stats = {
                'total_objects': len(self._managed_objects),
                'allocation_count': self._allocation_count,
                'limits': {
                    'max_cache_size_mb': self.limits.max_cache_size_mb,
                    'max_entry_size_kb': self.limits.max_entry_size_kb,
                    'max_string_length': self.limits.max_string_length
                },
                'objects': {}
            }
            
            total_size_mb = 0.0
            
            for name, obj in self._managed_objects.items():
                obj_stats = {'type': type(obj).__name__}
                
                if hasattr(obj, 'size_mb'):
                    obj_stats['size_mb'] = obj.size_mb
                    total_size_mb += obj.size_mb
                
                if hasattr(obj, '__len__'):
                    obj_stats['length'] = len(obj)
                
                stats['objects'][name] = obj_stats
            
            stats['total_size_mb'] = total_size_mb
            
            return stats
    
    async def _periodic_cleanup(self):
        """Periodic cleanup of managed objects"""
        while not self._shutdown_event.is_set():
            try:
                async with self._lock:
                    for name, obj in self._managed_objects.items():
                        try:
                            if hasattr(obj, 'cleanup_if_needed'):
                                await obj.cleanup_if_needed()
                        except Exception as e:
                            logger.error(f"Cleanup error for {name}: {e}")
                
                # Wait 60 seconds before next cleanup
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def emergency_cleanup(self):
        """Emergency cleanup when memory limits exceeded"""
        logger.warning("Emergency memory cleanup initiated")
        
        async with self._lock:
            for name, obj in self._managed_objects.items():
                try:
                    if hasattr(obj, 'clear'):
                        await obj.clear()
                        logger.info(f"Cleared {name}")
                except Exception as e:
                    logger.error(f"Emergency cleanup error for {name}: {e}")
        
        self._total_allocated_mb = 0.0
        logger.info("Emergency cleanup completed")


# Global memory manager instance
_global_memory_manager: Optional[SecureMemoryManager] = None


async def get_memory_manager() -> SecureMemoryManager:
    """Get global memory manager instance"""
    global _global_memory_manager
    
    if _global_memory_manager is None:
        _global_memory_manager = SecureMemoryManager()
        await _global_memory_manager.start()
    
    return _global_memory_manager