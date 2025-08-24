"""
Speed Layer Architecture

Provides <100ms response time for 99% of validation operations through:
- Memory cache (sub-millisecond lookups)
- Policy cache (1-5ms rule evaluation) 
- Pattern cache (5-10ms ML pattern matching)
- Expert escalation (for the remaining 1%)

Performance Requirements:
- 99% of requests served in <100ms
- 95% cache hit ratio
- Sub-millisecond memory lookups
- Automatic cache warming and refresh
"""

# Import both original and optimized versions
from .dispatcher import SpeedLayerDispatcher
from .optimized_dispatcher import OptimizedSpeedLayerDispatcher
from .memory_cache import MemoryRuleCache
from .optimized_memory_cache import OptimizedMemoryCache
from .policy_cache import PolicyEngineCache
from .optimized_policy_cache import OptimizedPolicyCache
from .pattern_cache import MLPatternCache
from .optimized_pattern_cache import OptimizedPatternCache

# Use optimized versions by default for performance
SpeedLayerDispatcher = OptimizedSpeedLayerDispatcher  # Override with optimized version
MemoryRuleCache = OptimizedMemoryCache  # Override with optimized version
PolicyEngineCache = OptimizedPolicyCache  # Override with optimized version
MLPatternCache = OptimizedPatternCache  # Override with optimized version

__all__ = [
    'SpeedLayerDispatcher',
    'OptimizedSpeedLayerDispatcher',
    'MemoryRuleCache',
    'OptimizedMemoryCache', 
    'PolicyEngineCache',
    'OptimizedPolicyCache',
    'MLPatternCache',
    'OptimizedPatternCache'
]