"""
Distributed Memory Cache with Redis Persistence

Enhanced memory cache that integrates with Redis for distributed persistence
and cross-instance coordination. Provides the same sub-millisecond performance
for local cache hits while adding distributed cache capabilities.

Features:
- Local memory cache for ultra-fast access
- Redis distributed persistence layer
- Automatic cache synchronization
- Multi-tier cache architecture
- Hot entry protection and LRU eviction
"""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple

from .memory_cache import BloomFilter  # Reuse existing Bloom filter
from .models import CacheEntry, ValidationRequest, ValidationResult
from .redis_cache import RedisDistributedCache, RedisConfig, create_redis_cache

logger = logging.getLogger(__name__)


class DistributedMemoryCache:
    """
    High-performance distributed cache with Redis persistence
    
    Provides a multi-tier caching architecture:
    1. Local memory cache (sub-millisecond access)
    2. Redis distributed cache (millisecond access, persistent)
    3. Automatic synchronization between instances
    """
    
    def __init__(self, 
                 max_size: int = 10000, 
                 hot_threshold: int = 10,
                 redis_config: Optional[RedisConfig] = None,
                 enable_redis: bool = True):
        """
        Initialize distributed memory cache
        
        Args:
            max_size: Maximum local cache size
            hot_threshold: Access count for hot entries
            redis_config: Redis configuration (None for defaults)
            enable_redis: Enable Redis distributed layer
        """
        self.max_size = max_size
        self.hot_threshold = hot_threshold
        self.enable_redis = enable_redis
        
        # Local memory cache (tier 1 - fastest)
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hot_entries: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        # Bloom filter for fast negative lookups
        self._bloom_filter = BloomFilter(capacity=max_size * 2)
        
        # Redis distributed cache (tier 2 - persistent)
        self._redis_cache: Optional[RedisDistributedCache] = None
        if enable_redis:
            try:
                self._redis_cache = create_redis_cache() if not redis_config else RedisDistributedCache(redis_config)
            except Exception as e:
                logger.warning(f"Redis distributed cache not available: {e}")
                self._redis_cache = None
        
        # Statistics
        self.local_hits = 0
        self.redis_hits = 0 
        self.total_misses = 0
        self.evictions = 0
        self.sync_operations = 0
        
        # Background synchronization
        self._sync_task: Optional[asyncio.Task] = None
        self._sync_interval = 30.0  # 30 seconds
        
        logger.info(f"Distributed memory cache initialized (Redis: {'enabled' if self._redis_cache else 'disabled'})")
    
    async def initialize(self) -> bool:
        """
        Initialize the distributed cache system
        
        Returns:
            True if initialization successful
        """
        try:
            # Initialize Redis if available
            if self._redis_cache:
                redis_success = await self._redis_cache.initialize()
                if redis_success:
                    logger.info("Redis distributed cache initialized")
                    
                    # Start background synchronization
                    self._sync_task = asyncio.create_task(self._sync_background())
                else:
                    logger.warning("Redis initialization failed, continuing with local cache only")
                    self._redis_cache = None
            
            logger.info("Distributed memory cache initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize distributed cache: {e}")
            return False
    
    async def get(self, command_hash: str) -> Optional[ValidationResult]:
        """
        Get cached validation result with multi-tier lookup
        
        Lookup order:
        1. Local hot entries (fastest)
        2. Local LRU cache
        3. Redis distributed cache
        
        Returns:
            ValidationResult if found, None otherwise
        """
        # Fast negative lookup with Bloom filter
        if not self._bloom_filter.might_contain(command_hash):
            self.total_misses += 1
            return None
        
        # Tier 1: Local memory cache
        with self._lock:
            # Check hot entries first
            if command_hash in self._hot_entries:
                entry = self._hot_entries[command_hash]
                if not entry.is_expired:
                    self.local_hits += 1
                    result = entry.access()
                    result.cache_hit = True
                    result.cache_layer = "memory_hot"
                    return result
                else:
                    # Remove expired hot entry
                    del self._hot_entries[command_hash]
            
            # Check main local cache
            if command_hash in self._cache:
                entry = self._cache[command_hash]
                if not entry.is_expired:
                    # Move to front (LRU)
                    self._cache.move_to_end(command_hash)
                    self.local_hits += 1
                    result = entry.access()
                    result.cache_hit = True
                    result.cache_layer = "memory"
                    
                    # Promote to hot entries if accessed frequently
                    if entry.is_hot and command_hash not in self._hot_entries:
                        self._hot_entries[command_hash] = entry
                    
                    return result
                else:
                    # Remove expired entry
                    del self._cache[command_hash]
        
        # Tier 2: Redis distributed cache
        if self._redis_cache:
            try:
                redis_result = await self._redis_cache.get(command_hash)
                if redis_result:
                    self.redis_hits += 1
                    redis_result.cache_hit = True
                    redis_result.cache_layer = "redis"
                    
                    # Cache in local memory for future access
                    await self._cache_locally(command_hash, redis_result)
                    
                    return redis_result
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        # Cache miss
        self.total_misses += 1
        return None
    
    async def set(self, command_hash: str, result: ValidationResult, ttl_seconds: int = 300) -> bool:
        """
        Cache validation result in both local and distributed layers
        
        Args:
            command_hash: Cache key
            result: Validation result to cache
            ttl_seconds: Time to live in seconds
            
        Returns:
            True if caching successful
        """
        try:
            # Create cache entry
            entry = CacheEntry(
                result=result,
                created_at=time.time(),
                ttl_seconds=ttl_seconds
            )
            
            # Store in local cache
            with self._lock:
                # Add to Bloom filter
                self._bloom_filter.add(command_hash)
                
                # Store in main cache
                self._cache[command_hash] = entry
                
                # Enforce size limit with LRU eviction
                if len(self._cache) > self.max_size:
                    # Evict least recently used entry (but protect hot entries)
                    oldest_key, oldest_entry = self._cache.popitem(last=False)
                    
                    # Don't evict if it's a hot entry
                    if oldest_key in self._hot_entries:
                        self._cache[oldest_key] = oldest_entry
                        self._cache.move_to_end(oldest_key)
                        
                        # Find next oldest non-hot entry
                        for key, cache_entry in list(self._cache.items()):
                            if key not in self._hot_entries:
                                del self._cache[key]
                                self.evictions += 1
                                break
                    else:
                        self.evictions += 1
            
            # Store in Redis distributed cache
            if self._redis_cache:
                try:
                    await self._redis_cache.set(command_hash, result, ttl_seconds)
                except Exception as e:
                    logger.warning(f"Redis set error: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def _cache_locally(self, command_hash: str, result: ValidationResult):
        """Cache result from Redis into local memory"""
        try:
            entry = CacheEntry(
                result=result,
                created_at=time.time(),
                ttl_seconds=300  # Use default TTL for Redis-retrieved entries
            )
            
            with self._lock:
                self._bloom_filter.add(command_hash)
                self._cache[command_hash] = entry
                
                # Enforce size limit
                if len(self._cache) > self.max_size:
                    oldest_key, _ = self._cache.popitem(last=False)
                    if oldest_key not in self._hot_entries:
                        self.evictions += 1
                    
        except Exception as e:
            logger.warning(f"Local caching error: {e}")
    
    async def delete(self, command_hash: str) -> bool:
        """
        Delete cached entry from all layers
        
        Args:
            command_hash: Cache key to delete
            
        Returns:
            True if deletion successful
        """
        success = True
        
        # Remove from local cache
        with self._lock:
            if command_hash in self._cache:
                del self._cache[command_hash]
            if command_hash in self._hot_entries:
                del self._hot_entries[command_hash]
        
        # Remove from Redis
        if self._redis_cache:
            try:
                redis_success = await self._redis_cache.delete(command_hash)
                success = success and redis_success
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
                success = False
        
        return success
    
    async def clear_all(self) -> bool:
        """Clear all cached entries"""
        try:
            # Clear local cache
            with self._lock:
                self._cache.clear()
                self._hot_entries.clear()
                self._bloom_filter.clear()
            
            # Clear Redis
            if self._redis_cache:
                await self._redis_cache.clear_pattern("*")
            
            logger.info("All cache entries cleared")
            return True
            
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, any]:
        """Get comprehensive cache statistics"""
        with self._lock:
            local_stats = {
                'local_size': len(self._cache),
                'hot_entries': len(self._hot_entries),
                'local_hits': self.local_hits,
                'redis_hits': self.redis_hits,
                'total_misses': self.total_misses,
                'evictions': self.evictions,
                'sync_operations': self.sync_operations,
                'bloom_filter_size': self._bloom_filter.item_count,
                'local_hit_rate': self.local_hits / (self.local_hits + self.redis_hits + self.total_misses) if (self.local_hits + self.redis_hits + self.total_misses) > 0 else 0,
                'overall_hit_rate': (self.local_hits + self.redis_hits) / (self.local_hits + self.redis_hits + self.total_misses) if (self.local_hits + self.redis_hits + self.total_misses) > 0 else 0
            }
        
        # Add Redis stats if available
        if self._redis_cache:
            try:
                redis_stats = await self._redis_cache.get_cache_info()
                local_stats['redis_stats'] = redis_stats
            except Exception as e:
                local_stats['redis_error'] = str(e)
        
        return local_stats
    
    async def _sync_background(self):
        """Background task for cache synchronization"""
        while True:
            try:
                await asyncio.sleep(self._sync_interval)
                
                # Perform periodic maintenance
                await self._cleanup_expired_entries()
                self.sync_operations += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background sync error: {e}")
    
    async def _cleanup_expired_entries(self):
        """Clean up expired entries from local cache"""
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
                with self._lock:
                    self._cache.pop(key, None)
                    self._hot_entries.pop(key, None)
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    async def shutdown(self):
        """Shutdown distributed cache"""
        logger.info("Shutting down distributed memory cache...")
        
        # Cancel background tasks
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown Redis
        if self._redis_cache:
            await self._redis_cache.shutdown()
        
        logger.info("Distributed memory cache shutdown complete")


# Factory function for easy integration
def create_distributed_cache(max_size: int = 10000,
                           redis_host: str = "localhost",
                           redis_port: int = 6379,
                           redis_password: Optional[str] = None) -> DistributedMemoryCache:
    """Create distributed memory cache with Redis persistence"""
    
    redis_config = RedisConfig(
        host=redis_host,
        port=redis_port,
        password=redis_password
    )
    
    return DistributedMemoryCache(
        max_size=max_size,
        redis_config=redis_config,
        enable_redis=True
    )