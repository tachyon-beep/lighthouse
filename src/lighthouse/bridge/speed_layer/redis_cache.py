"""
Redis Distributed Cache for Speed Layer

High-performance distributed cache using Redis for multi-instance coordination
and persistent cache storage across Bridge instances.

Features:
- Distributed cache coordination
- JSON serialization for complex objects
- Connection pooling for performance
- Cache clustering and sharding support
- Automatic failover and reconnection
- Comprehensive health monitoring
- TTL management and eviction policies
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
import hashlib

try:
    import redis
    import redis.asyncio as redis_async
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .models import ValidationResult, ValidationDecision, ValidationConfidence, ValidationRequest

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Redis configuration for distributed cache"""
    
    # Connection settings
    host: str = "localhost"
    port: int = 6379
    password: Optional[str] = None
    db: int = 0
    
    # Connection pool settings
    max_connections: int = 50
    socket_timeout: float = 1.0
    socket_connect_timeout: float = 1.0
    health_check_interval: int = 30
    
    # Cache settings
    key_prefix: str = "lighthouse:cache"
    default_ttl: int = 3600  # 1 hour
    max_key_size: int = 1000
    max_value_size: int = 100000  # 100KB
    
    # Clustering (for future expansion)
    cluster_mode: bool = False
    cluster_nodes: List[Tuple[str, int]] = None
    
    def __post_init__(self):
        if self.cluster_nodes is None:
            self.cluster_nodes = []


@dataclass 
class CacheStats:
    """Cache statistics and health metrics"""
    
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    
    # Performance metrics
    avg_get_time_ms: float = 0.0
    avg_set_time_ms: float = 0.0
    
    # Redis-specific metrics
    memory_usage_bytes: int = 0
    connected_clients: int = 0
    total_keys: int = 0
    
    # Connection health
    connection_errors: int = 0
    last_error: Optional[str] = None
    uptime_seconds: float = 0.0
    
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class RedisDistributedCache:
    """
    High-performance distributed cache using Redis
    
    Provides persistent, distributed caching for the Speed Layer with
    automatic failover, connection pooling, and comprehensive monitoring.
    """
    
    def __init__(self, config: Optional[RedisConfig] = None):
        """
        Initialize Redis distributed cache
        
        Args:
            config: Redis configuration, uses defaults if None
        """
        self.config = config or RedisConfig()
        self.stats = CacheStats()
        
        # Redis clients (sync and async)
        self.redis_client: Optional[redis.Redis] = None
        self.async_client: Optional[redis_async.Redis] = None
        
        # Connection management
        self.connection_pool: Optional[redis.ConnectionPool] = None
        self.async_pool: Optional[redis_async.ConnectionPool] = None
        
        # Monitoring
        self.start_time = time.time()
        self._health_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        # Serialization
        self._serializer = json
        
        logger.info(f"Redis distributed cache initialized (available: {REDIS_AVAILABLE})")
    
    async def initialize(self) -> bool:
        """
        Initialize Redis connections and verify connectivity
        
        Returns:
            True if initialization successful
        """
        if not REDIS_AVAILABLE:
            logger.error("Redis not available - install redis-py package")
            return False
        
        try:
            logger.info("Initializing Redis distributed cache...")
            
            # Create connection pools
            self.connection_pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password,
                db=self.config.db,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                health_check_interval=self.config.health_check_interval,
                decode_responses=True
            )
            
            self.async_pool = redis_async.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password,
                db=self.config.db,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                health_check_interval=self.config.health_check_interval,
                decode_responses=True
            )
            
            # Create clients
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            self.async_client = redis_async.Redis(connection_pool=self.async_pool)
            
            # Test connections
            await self._test_connection()
            
            # Start health monitoring
            self._health_task = asyncio.create_task(self._monitor_health())
            
            self._is_connected = True
            logger.info("Redis distributed cache initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            self.stats.connection_errors += 1
            self.stats.last_error = str(e)
            return False
    
    async def _test_connection(self):
        """Test Redis connection"""
        try:
            # Test sync client
            if self.redis_client:
                self.redis_client.ping()
            
            # Test async client
            if self.async_client:
                await self.async_client.ping()
            
            logger.info("Redis connection test successful")
            
        except Exception as e:
            raise Exception(f"Redis connection test failed: {e}")
    
    async def get(self, key: str) -> Optional[ValidationResult]:
        """
        Get cached validation result
        
        Args:
            key: Cache key (usually command hash)
            
        Returns:
            Cached ValidationResult or None if not found
        """
        if not self._is_connected:
            return None
        
        start_time = time.perf_counter()
        
        try:
            full_key = f"{self.config.key_prefix}:{key}"
            
            # Get from Redis
            cached_data = await self.async_client.get(full_key)
            
            if cached_data:
                # Deserialize cached result
                result_data = self._serializer.loads(cached_data)
                result = ValidationResult(
                    decision=ValidationDecision(result_data['decision']),
                    confidence=ValidationConfidence(result_data['confidence']),
                    reason=result_data['reason'],
                    request_id=result_data.get('request_id', 'cached'),
                    processing_time_ms=result_data.get('processing_time_ms', 0.0),
                    cache_hit=True,
                    cache_layer="redis",
                    expert_required=result_data.get('expert_required', False),
                    expert_context=result_data.get('expert_context'),
                    risk_level=result_data.get('risk_level', 'low'),
                    security_concerns=result_data.get('security_concerns', []),
                    timestamp=result_data.get('timestamp', time.time())
                )
                
                # Update stats
                self.stats.hits += 1
                response_time = (time.perf_counter() - start_time) * 1000
                self._update_avg_time('get', response_time)
                
                logger.debug(f"Redis cache hit: {key}")
                return result
            else:
                self.stats.misses += 1
                logger.debug(f"Redis cache miss: {key}")
                return None
                
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            self.stats.errors += 1
            self.stats.last_error = str(e)
            return None
        finally:
            response_time = (time.perf_counter() - start_time) * 1000
            self._update_avg_time('get', response_time)
    
    async def set(self, 
                 key: str, 
                 result: ValidationResult, 
                 ttl: Optional[int] = None) -> bool:
        """
        Cache validation result
        
        Args:
            key: Cache key (usually command hash)
            result: ValidationResult to cache
            ttl: Time to live in seconds, uses default if None
            
        Returns:
            True if successfully cached
        """
        if not self._is_connected:
            return False
        
        start_time = time.perf_counter()
        
        try:
            # Validate key and value size
            if len(key) > self.config.max_key_size:
                logger.warning(f"Key too large: {len(key)} bytes")
                return False
            
            # Serialize result
            result_data = {
                'decision': result.decision.value,
                'confidence': result.confidence.value,
                'reason': result.reason,
                'request_id': result.request_id,
                'processing_time_ms': result.processing_time_ms,
                'cache_hit': result.cache_hit,
                'cache_layer': result.cache_layer,
                'expert_required': result.expert_required,
                'expert_context': result.expert_context,
                'risk_level': result.risk_level,
                'security_concerns': result.security_concerns,
                'timestamp': result.timestamp,
                'cached_at': time.time()
            }
            
            serialized_data = self._serializer.dumps(result_data)
            
            if len(serialized_data) > self.config.max_value_size:
                logger.warning(f"Value too large: {len(serialized_data)} bytes")
                return False
            
            # Set in Redis with TTL
            full_key = f"{self.config.key_prefix}:{key}"
            ttl_seconds = ttl or self.config.default_ttl
            
            success = await self.async_client.setex(full_key, ttl_seconds, serialized_data)
            
            if success:
                self.stats.sets += 1
                logger.debug(f"Redis cache set: {key} (TTL: {ttl_seconds}s)")
            
            return bool(success)
            
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            self.stats.errors += 1
            self.stats.last_error = str(e)
            return False
        finally:
            response_time = (time.perf_counter() - start_time) * 1000
            self._update_avg_time('set', response_time)
    
    async def delete(self, key: str) -> bool:
        """
        Delete cached entry
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if deletion successful
        """
        if not self._is_connected:
            return False
        
        try:
            full_key = f"{self.config.key_prefix}:{key}"
            deleted = await self.async_client.delete(full_key)
            
            if deleted:
                self.stats.deletes += 1
                logger.debug(f"Redis cache delete: {key}")
            
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            self.stats.errors += 1
            return False
    
    async def clear_pattern(self, pattern: str = "*") -> int:
        """
        Clear cached entries matching pattern
        
        Args:
            pattern: Key pattern to match (default: all cache keys)
            
        Returns:
            Number of keys deleted
        """
        if not self._is_connected:
            return 0
        
        try:
            full_pattern = f"{self.config.key_prefix}:{pattern}"
            keys = await self.async_client.keys(full_pattern)
            
            if keys:
                deleted = await self.async_client.delete(*keys)
                logger.info(f"Redis cache cleared {deleted} keys matching pattern: {pattern}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Redis clear error for pattern {pattern}: {e}")
            self.stats.errors += 1
            return 0
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """
        Get comprehensive cache information and statistics
        
        Returns:
            Dictionary with cache info and Redis server statistics
        """
        info = {
            'connected': self._is_connected,
            'config': asdict(self.config),
            'stats': asdict(self.stats),
            'uptime_seconds': time.time() - self.start_time,
            'redis_available': REDIS_AVAILABLE
        }
        
        if self._is_connected and self.redis_client:
            try:
                # Get Redis server info
                redis_info = self.redis_client.info()
                
                info.update({
                    'redis_version': redis_info.get('redis_version'),
                    'memory_usage_bytes': redis_info.get('used_memory', 0),
                    'connected_clients': redis_info.get('connected_clients', 0),
                    'total_keys': await self._count_cache_keys(),
                    'redis_uptime_seconds': redis_info.get('uptime_in_seconds', 0),
                    'redis_memory_human': redis_info.get('used_memory_human', 'unknown')
                })
                
            except Exception as e:
                logger.error(f"Error getting Redis info: {e}")
                info['redis_info_error'] = str(e)
        
        return info
    
    async def _count_cache_keys(self) -> int:
        """Count cache keys"""
        try:
            keys = await self.async_client.keys(f"{self.config.key_prefix}:*")
            return len(keys)
        except Exception:
            return 0
    
    def _update_avg_time(self, operation: str, time_ms: float):
        """Update average operation time using exponential moving average"""
        alpha = 0.1  # Smoothing factor
        
        if operation == 'get':
            self.stats.avg_get_time_ms = (
                alpha * time_ms + (1 - alpha) * self.stats.avg_get_time_ms
            )
        elif operation == 'set':
            self.stats.avg_set_time_ms = (
                alpha * time_ms + (1 - alpha) * self.stats.avg_set_time_ms
            )
    
    async def _monitor_health(self):
        """Monitor Redis connection health"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                if self._is_connected:
                    # Health check ping
                    await self.async_client.ping()
                    
                    # Update uptime
                    self.stats.uptime_seconds = time.time() - self.start_time
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Redis health check failed: {e}")
                self.stats.connection_errors += 1
                self.stats.last_error = str(e)
                self._is_connected = False
                
                # Attempt reconnection
                try:
                    await self._test_connection()
                    self._is_connected = True
                    logger.info("Redis connection restored")
                except Exception:
                    logger.error("Redis reconnection failed")
    
    async def shutdown(self):
        """Shutdown Redis cache connections"""
        logger.info("Shutting down Redis distributed cache...")
        
        # Cancel health monitoring
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        # Close connections
        if self.async_client:
            await self.async_client.close()
        
        if self.connection_pool:
            self.connection_pool.disconnect()
        
        if self.async_pool:
            await self.async_pool.disconnect()
        
        self._is_connected = False
        logger.info("Redis distributed cache shutdown complete")


# Factory functions for easy integration

def create_redis_cache(host: str = "localhost",
                      port: int = 6379,
                      password: Optional[str] = None,
                      **kwargs) -> RedisDistributedCache:
    """Create Redis cache with custom configuration"""
    config = RedisConfig(
        host=host,
        port=port, 
        password=password,
        **kwargs
    )
    return RedisDistributedCache(config)


def create_production_redis_cache(redis_url: str,
                                 password: Optional[str] = None) -> RedisDistributedCache:
    """Create production Redis cache from URL"""
    # Parse Redis URL (redis://host:port/db)
    if redis_url.startswith("redis://"):
        # Simple URL parsing for production use
        import urllib.parse
        parsed = urllib.parse.urlparse(redis_url)
        
        config = RedisConfig(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=password or parsed.password,
            db=int(parsed.path.lstrip("/")) if parsed.path else 0,
            max_connections=100,  # Higher for production
            default_ttl=7200,     # 2 hours for production
            health_check_interval=10
        )
    else:
        # Fallback to localhost
        config = RedisConfig(
            host=redis_url,
            password=password,
            max_connections=100,
            default_ttl=7200
        )
    
    return RedisDistributedCache(config)


async def test_redis_cache() -> bool:
    """Test Redis cache functionality"""
    cache = create_redis_cache()
    
    try:
        success = await cache.initialize()
        if not success:
            return False
        
        # Test set/get
        test_result = ValidationResult(
            decision=ValidationDecision.APPROVED,
            reason="Test validation",
            confidence=0.95,
            metadata={"test": True}
        )
        
        await cache.set("test_key", test_result, ttl=60)
        retrieved = await cache.get("test_key")
        
        if retrieved and retrieved.decision == ValidationDecision.APPROVED:
            logger.info("Redis cache test successful")
            return True
        else:
            logger.error("Redis cache test failed")
            return False
            
    except Exception as e:
        logger.error(f"Redis cache test error: {e}")
        return False
    finally:
        await cache.shutdown()