"""
Memory Rule Cache

High-performance in-memory cache for the most frequently used validation patterns.
Provides sub-millisecond lookups for hot validation requests.

Features:
- LRU eviction with hot entry protection
- Bloom filter for fast negative lookups
- Automatic cache warming from historical data
- Thread-safe operations
"""

import asyncio
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .models import CacheEntry, ValidationRequest, ValidationResult

logger = logging.getLogger(__name__)


class BloomFilter:
    """Simple Bloom filter for fast negative lookups"""
    
    def __init__(self, capacity: int = 10000, error_rate: float = 0.01):
        """Initialize Bloom filter with given capacity and error rate"""
        import math
        
        self.capacity = capacity
        self.error_rate = error_rate
        
        # Calculate optimal bit array size and number of hash functions
        self.bit_array_size = int(-capacity * math.log(error_rate) / (math.log(2) ** 2))
        self.hash_count = int(self.bit_array_size * math.log(2) / capacity)
        
        # Use a set of integers to represent bit array (Python optimization)
        self.bit_array: Set[int] = set()
        self.item_count = 0
    
    def _hash(self, item: str) -> List[int]:
        """Generate multiple hash values for an item"""
        hashes = []
        for i in range(self.hash_count):
            # Use different salts for each hash function
            salted_item = f"{item}:{i}"
            hash_value = int(hashlib.md5(salted_item.encode()).hexdigest(), 16)
            hashes.append(hash_value % self.bit_array_size)
        return hashes
    
    def add(self, item: str):
        """Add item to Bloom filter"""
        for hash_value in self._hash(item):
            self.bit_array.add(hash_value)
        self.item_count += 1
    
    def might_contain(self, item: str) -> bool:
        """Check if item might be in the set (no false negatives)"""
        for hash_value in self._hash(item):
            if hash_value not in self.bit_array:
                return False
        return True
    
    def clear(self):
        """Clear the Bloom filter"""
        self.bit_array.clear()
        self.item_count = 0


class MemoryRuleCache:
    """High-performance in-memory cache for validation rules"""
    
    def __init__(self, max_size: int = 10000, hot_threshold: int = 10):
        """
        Initialize memory cache
        
        Args:
            max_size: Maximum number of entries to store
            hot_threshold: Access count threshold for "hot" entries
        """
        self.max_size = max_size
        self.hot_threshold = hot_threshold
        
        # Thread-safe storage
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hot_entries: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        # Bloom filter for fast negative lookups
        self._bloom_filter = BloomFilter(capacity=max_size * 2)
        
        # Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        
        # Redis backup (if available)
        self._redis_client: Optional[object] = None
        if REDIS_AVAILABLE:
            try:
                self._redis_client = redis.Redis(
                    host='localhost', 
                    port=6379, 
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0
                )
                # Test connection
                self._redis_client.ping()
                logger.info("Redis backup cache enabled")
            except Exception as e:
                logger.warning(f"Redis not available: {e}")
                self._redis_client = None
    
    def get(self, command_hash: str) -> Optional[ValidationResult]:
        """
        Get cached validation result
        
        Returns None if not found or expired.
        Maintains LRU order and updates access statistics.
        """
        # Fast negative lookup with Bloom filter
        if not self._bloom_filter.might_contain(command_hash):
            self.misses += 1
            return None
        
        with self._lock:
            # Check hot entries first (no LRU impact)
            if command_hash in self._hot_entries:
                entry = self._hot_entries[command_hash]
                if not entry.is_expired:
                    self.hits += 1
                    return entry.access()
                else:
                    # Remove expired hot entry
                    del self._hot_entries[command_hash]
            
            # Check main cache
            if command_hash in self._cache:
                entry = self._cache[command_hash]
                
                # Check expiration
                if entry.is_expired:
                    del self._cache[command_hash]
                    self.misses += 1
                    return None
                
                # Move to end (most recently used)
                self._cache.move_to_end(command_hash)
                
                # Promote to hot cache if accessed frequently
                result = entry.access()
                if entry.is_hot and command_hash not in self._hot_entries:
                    self._hot_entries[command_hash] = entry
                    # Remove from main cache to avoid duplication
                    del self._cache[command_hash]
                
                self.hits += 1
                return result
        
        # Try Redis backup if available
        if self._redis_client:
            try:
                cached_data = self._redis_client.get(f"lighthouse:cache:{command_hash}")
                if cached_data:
                    # Simple JSON serialization would go here
                    # For now, just indicate we found it in Redis
                    logger.debug(f"Found {command_hash} in Redis backup")
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        self.misses += 1
        return None
    
    def set(self, command_hash: str, result: ValidationResult, ttl_seconds: int = 300):
        """
        Cache validation result
        
        Args:
            command_hash: Unique hash for the command
            result: Validation result to cache
            ttl_seconds: Time to live in seconds
        """
        entry = CacheEntry(
            result=result,
            created_at=time.time(),
            ttl_seconds=ttl_seconds
        )
        
        with self._lock:
            # Add to Bloom filter
            self._bloom_filter.add(command_hash)
            
            # Evict oldest entries if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key, oldest_entry = self._cache.popitem(last=False)
                self.evictions += 1
                logger.debug(f"Evicted {oldest_key} (age: {time.time() - oldest_entry.created_at:.1f}s)")
            
            # Add new entry
            self._cache[command_hash] = entry
        
        # Backup to Redis if available
        if self._redis_client:
            try:
                # Simple string storage for now
                self._redis_client.setex(
                    f"lighthouse:cache:{command_hash}",
                    ttl_seconds,
                    f"{result.decision.value}:{result.reason}"
                )
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
    
    def warm_cache(self, historical_requests: List[Tuple[str, ValidationResult]]):
        """
        Warm cache with historical validation data
        
        Args:
            historical_requests: List of (command_hash, result) tuples
        """
        logger.info(f"Warming cache with {len(historical_requests)} historical requests")
        
        for command_hash, result in historical_requests:
            # Add to cache with longer TTL for warmed entries
            self.set(command_hash, result, ttl_seconds=3600)
        
        logger.info(f"Cache warmed. Size: {self.size}")
    
    def invalidate_pattern(self, pattern: str):
        """
        Invalidate cache entries matching a pattern
        
        Useful when security rules change.
        """
        with self._lock:
            # Find matching keys
            keys_to_remove = []
            for key in self._cache.keys():
                if pattern in key:
                    keys_to_remove.append(key)
            
            # Remove matching entries
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
                if key in self._hot_entries:
                    del self._hot_entries[key]
            
            logger.info(f"Invalidated {len(keys_to_remove)} entries matching pattern: {pattern}")
    
    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
            self._hot_entries.clear()
            self._bloom_filter.clear()
            
            # Clear Redis backup
            if self._redis_client:
                try:
                    keys = self._redis_client.keys("lighthouse:cache:*")
                    if keys:
                        self._redis_client.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis clear error: {e}")
    
    @property
    def size(self) -> int:
        """Total number of cached entries"""
        return len(self._cache) + len(self._hot_entries)
    
    @property
    def hit_rate(self) -> float:
        """Cache hit rate percentage"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
    
    def get_stats(self) -> Dict[str, any]:
        """Get cache statistics"""
        with self._lock:
            return {
                'size': self.size,
                'max_size': self.max_size,
                'hot_entries': len(self._hot_entries),
                'hit_rate': self.hit_rate,
                'hits': self.hits,
                'misses': self.misses,
                'evictions': self.evictions,
                'bloom_filter_size': self._bloom_filter.item_count,
                'redis_available': self._redis_client is not None
            }
    
    def get_hot_patterns(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get the most frequently accessed patterns"""
        with self._lock:
            # Sort by access count
            sorted_entries = sorted(
                [(k, v.access_count) for k, v in self._hot_entries.items()],
                key=lambda x: x[1],
                reverse=True
            )
            return sorted_entries[:limit]
    
    async def periodic_cleanup(self, interval_seconds: int = 60):
        """
        Periodic cleanup of expired entries
        
        Should be run as a background task.
        """
        while True:
            try:
                current_time = time.time()
                expired_keys = []
                
                with self._lock:
                    # Check main cache
                    for key, entry in list(self._cache.items()):
                        if entry.is_expired:
                            expired_keys.append(key)
                    
                    # Check hot entries
                    for key, entry in list(self._hot_entries.items()):
                        if entry.is_expired:
                            expired_keys.append(key)
                    
                    # Remove expired entries
                    for key in expired_keys:
                        self._cache.pop(key, None)
                        self._hot_entries.pop(key, None)
                
                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
                await asyncio.sleep(interval_seconds)