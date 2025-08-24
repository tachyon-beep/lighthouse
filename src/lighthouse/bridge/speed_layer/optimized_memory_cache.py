"""
Optimized Memory Cache for Speed Layer

Ultra-fast in-memory cache optimized for <1ms response times.
Uses async locks, pre-allocated structures, and optimized algorithms.

Performance Optimizations:
- Async locks instead of threading locks
- FastHash instead of MD5 for Bloom filter  
- Pre-allocated circular buffers
- Lock-free hot path for common cases
- Batch operations for reduced lock contention
"""

import asyncio
import hashlib
import logging
import time
try:
    import xxhash
    HAS_XXHASH = True
except ImportError:
    HAS_XXHASH = False
from collections import OrderedDict, deque
from typing import Dict, List, Optional, Set, Tuple

from .models import CacheEntry, ValidationRequest, ValidationResult

logger = logging.getLogger(__name__)


class FastBloomFilter:
    """Optimized Bloom filter using xxHash for speed"""
    
    def __init__(self, capacity: int = 10000, error_rate: float = 0.01):
        import math
        
        self.capacity = capacity
        self.error_rate = error_rate
        
        # Calculate optimal bit array size and number of hash functions
        self.bit_array_size = int(-capacity * math.log(error_rate) / (math.log(2) ** 2))
        self.hash_count = min(int(self.bit_array_size * math.log(2) / capacity), 8)  # Cap at 8 hashes
        
        # Use bitarray for memory efficiency (fallback to set if not available)
        try:
            import bitarray
            self.bit_array = bitarray.bitarray(self.bit_array_size)
            self.bit_array.setall(0)
            self._use_bitarray = True
        except ImportError:
            self.bit_array = set()
            self._use_bitarray = False
        
        self.item_count = 0
    
    def _fast_hash(self, item: str, seed: int) -> int:
        """Fast hash using xxHash (falls back to builtin hash)"""
        if HAS_XXHASH:
            try:
                return xxhash.xxh32(item.encode(), seed=seed).intdigest() % self.bit_array_size
            except:
                pass
        
        # Fallback to Python's builtin hash
        return hash(f"{item}:{seed}") % self.bit_array_size
    
    def add(self, item: str):
        """Add item to Bloom filter"""
        for i in range(self.hash_count):
            hash_value = self._fast_hash(item, i)
            if self._use_bitarray:
                self.bit_array[hash_value] = 1
            else:
                self.bit_array.add(hash_value)
        self.item_count += 1
    
    def might_contain(self, item: str) -> bool:
        """Check if item might be in the set (no false negatives)"""
        for i in range(self.hash_count):
            hash_value = self._fast_hash(item, i)
            if self._use_bitarray:
                if not self.bit_array[hash_value]:
                    return False
            else:
                if hash_value not in self.bit_array:
                    return False
        return True
    
    def clear(self):
        """Clear the Bloom filter"""
        if self._use_bitarray:
            self.bit_array.setall(0)
        else:
            self.bit_array.clear()
        self.item_count = 0


class OptimizedMemoryCache:
    """Ultra-fast memory cache optimized for <1ms response times"""
    
    def __init__(self, max_size: int = 10000, hot_threshold: int = 10):
        """
        Initialize optimized memory cache
        
        Args:
            max_size: Maximum number of entries to store
            hot_threshold: Access count threshold for "hot" entries
        """
        self.max_size = max_size
        self.hot_threshold = hot_threshold
        
        # Async-safe storage with separate locks for read/write
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hot_entries: Dict[str, CacheEntry] = {}
        self._read_lock = asyncio.Lock()  # Async lock for concurrent reads
        self._write_lock = asyncio.Lock()  # Separate write lock to minimize contention
        
        # Optimized Bloom filter
        self._bloom_filter = FastBloomFilter(capacity=max_size * 2)
        
        # Pre-allocated statistics (lock-free atomic operations)
        self._stats = {
            'hits': 0,
            'misses': 0, 
            'evictions': 0,
            'hot_promotions': 0
        }
        
        # Batch operations queue for reducing lock contention
        self._batch_queue: deque = deque(maxlen=100)
        self._batch_task: Optional[asyncio.Task] = None
        
        # Performance optimizations
        self._last_cleanup_time = time.time()
        self._cleanup_interval = 60.0  # seconds
    
    async def get(self, command_hash: str) -> Optional[ValidationResult]:
        """
        Ultra-fast cache get with <1ms target
        
        Optimizations:
        - Fast negative lookup with optimized Bloom filter
        - Hot cache check without locks
        - Minimal lock contention
        """
        # Ultra-fast negative lookup - no locks needed
        if not self._bloom_filter.might_contain(command_hash):
            self._stats['misses'] += 1
            return None
        
        # Check hot entries first (lock-free for performance)
        if command_hash in self._hot_entries:
            entry = self._hot_entries[command_hash]
            if not entry.is_expired:
                self._stats['hits'] += 1
                return entry.access()
            else:
                # Remove expired hot entry asynchronously
                asyncio.create_task(self._remove_expired_hot_entry(command_hash))
        
        # Main cache check with minimal locking
        async with self._read_lock:
            if command_hash in self._cache:
                entry = self._cache[command_hash]
                
                # Quick expiration check
                if entry.is_expired:
                    # Queue removal for batch processing
                    self._batch_queue.append(('remove', command_hash))
                    self._stats['misses'] += 1
                    return None
                
                # Move to end (LRU) - this is fast in OrderedDict
                self._cache.move_to_end(command_hash)
                
                # Get result and check for hot promotion
                result = entry.access()
                
                # Queue hot promotion for batch processing if needed
                if entry.is_hot and command_hash not in self._hot_entries:
                    self._batch_queue.append(('promote', command_hash, entry))
                
                self._stats['hits'] += 1
                return result
        
        self._stats['misses'] += 1
        return None
    
    async def set(self, command_hash: str, result: ValidationResult, ttl_seconds: int = 300):
        """
        Fast cache set with batched operations
        """
        entry = CacheEntry(
            result=result,
            created_at=time.time(),
            ttl_seconds=ttl_seconds
        )
        
        # Add to Bloom filter immediately (no lock needed)
        self._bloom_filter.add(command_hash)
        
        # Use minimal locking with batch processing
        async with self._write_lock:
            # Fast eviction check
            if len(self._cache) >= self.max_size:
                # Remove oldest entry
                oldest_key, oldest_entry = self._cache.popitem(last=False)
                self._stats['evictions'] += 1
            
            # Add new entry
            self._cache[command_hash] = entry
        
        # Start batch processor if not running
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._process_batch_operations())
    
    async def _remove_expired_hot_entry(self, command_hash: str):
        """Remove expired hot entry asynchronously"""
        if command_hash in self._hot_entries:
            del self._hot_entries[command_hash]
    
    async def _process_batch_operations(self):
        """Process batched operations to reduce lock contention"""
        await asyncio.sleep(0.001)  # Small delay to batch operations
        
        operations_to_process = []
        
        # Collect batch operations
        while self._batch_queue and len(operations_to_process) < 50:
            operations_to_process.append(self._batch_queue.popleft())
        
        if not operations_to_process:
            return
        
        # Process operations with single write lock
        async with self._write_lock:
            for operation in operations_to_process:
                try:
                    if operation[0] == 'remove':
                        command_hash = operation[1]
                        if command_hash in self._cache:
                            del self._cache[command_hash]
                    
                    elif operation[0] == 'promote':
                        command_hash, entry = operation[1], operation[2]
                        if command_hash not in self._hot_entries and command_hash in self._cache:
                            self._hot_entries[command_hash] = entry
                            del self._cache[command_hash]
                            self._stats['hot_promotions'] += 1
                            
                except Exception as e:
                    logger.warning(f"Batch operation error: {e}")
    
    async def periodic_cleanup(self, interval_seconds: int = 60):
        """
        Optimized periodic cleanup with minimal impact
        """
        while True:
            try:
                current_time = time.time()
                
                # Only run cleanup if enough time has passed
                if current_time - self._last_cleanup_time < interval_seconds:
                    await asyncio.sleep(1.0)
                    continue
                
                expired_keys = []
                
                # Quick scan for expired entries (read lock only)
                async with self._read_lock:
                    # Check main cache
                    for key, entry in list(self._cache.items()):
                        if entry.is_expired:
                            expired_keys.append(key)
                    
                    # Check hot entries
                    for key, entry in list(self._hot_entries.items()):
                        if entry.is_expired:
                            expired_keys.append(key)
                
                # Remove expired entries if any found
                if expired_keys:
                    async with self._write_lock:
                        for key in expired_keys:
                            self._cache.pop(key, None)
                            self._hot_entries.pop(key, None)
                    
                    logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
                self._last_cleanup_time = current_time
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
                await asyncio.sleep(interval_seconds)
    
    def get_stats(self) -> Dict[str, any]:
        """Get cache statistics"""
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = (self._stats['hits'] / total * 100) if total > 0 else 0.0
        
        return {
            'size': len(self._cache) + len(self._hot_entries),
            'max_size': self.max_size,
            'hot_entries': len(self._hot_entries),
            'hit_rate': hit_rate,
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'evictions': self._stats['evictions'],
            'hot_promotions': self._stats['hot_promotions'],
            'bloom_filter_size': self._bloom_filter.item_count
        }
    
    def clear(self):
        """Clear all cache entries"""
        self._cache.clear()
        self._hot_entries.clear()
        self._bloom_filter.clear()
        
        # Reset statistics
        for key in self._stats:
            self._stats[key] = 0