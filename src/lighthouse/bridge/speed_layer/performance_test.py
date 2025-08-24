"""
Performance Test for Speed Layer Optimizations

Benchmarks the optimized components against performance requirements:
- Memory Cache: <1ms response time
- Policy Cache: <5ms response time  
- Pattern Cache: <10ms response time
- Overall: 99% of requests <100ms
"""

import asyncio
import time
import statistics
from typing import List, Tuple
import logging

from .optimized_memory_cache import OptimizedMemoryCache
from .optimized_policy_cache import OptimizedPolicyCache
from .optimized_pattern_cache import OptimizedPatternCache
from .optimized_dispatcher import OptimizedSpeedLayerDispatcher
from .models import ValidationRequest, ValidationResult, ValidationDecision, ValidationConfidence, CacheEntry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceTester:
    """Comprehensive performance testing for Speed Layer optimizations"""
    
    def __init__(self):
        self.memory_cache = OptimizedMemoryCache(max_size=1000)
        self.policy_cache = OptimizedPolicyCache()
        self.pattern_cache = OptimizedPatternCache()
        self.dispatcher = OptimizedSpeedLayerDispatcher()
        
        # Test data
        self.test_requests = self._generate_test_requests()
    
    def _generate_test_requests(self) -> List[ValidationRequest]:
        """Generate diverse test requests"""
        requests = []
        
        # Safe operations
        for i in range(100):
            requests.append(ValidationRequest(
                tool_name="Read",
                tool_input={"file_path": f"/test/file_{i}.txt"},
                agent_id=f"agent_{i % 10}"
            ))
        
        # Bash commands
        bash_commands = [
            "ls -la /home/user",
            "cat config.json",
            "grep error *.log",
            "find . -name '*.py'",
            "rm temp.txt",
            "chmod 755 script.sh",
            "sudo rm -rf /dangerous/path",  # Should be blocked
            "dd if=/dev/zero of=/dev/sda",   # Should be blocked
        ]
        
        for i, cmd in enumerate(bash_commands):
            for j in range(10):  # Multiple copies for cache testing
                requests.append(ValidationRequest(
                    tool_name="Bash",
                    tool_input={"command": cmd},
                    agent_id=f"agent_{j % 5}"
                ))
        
        # File operations
        for i in range(50):
            requests.append(ValidationRequest(
                tool_name="Write",
                tool_input={
                    "file_path": f"/project/src/module_{i}.py",
                    "content": f"# Module {i}\nprint('hello world')"
                },
                agent_id=f"agent_{i % 3}"
            ))
        
        return requests
    
    async def test_memory_cache_performance(self) -> Dict[str, float]:
        """Test memory cache performance - target <1ms"""
        logger.info("Testing Memory Cache Performance (<1ms target)...")
        
        # Warm up cache
        for i in range(10):
            dummy_result = ValidationResult(
                decision=ValidationDecision.APPROVED,
                confidence=ValidationConfidence.HIGH,
                reason="Test result",
                request_id=f"test_{i}",
                processing_time_ms=0.1
            )
            await self.memory_cache.set(f"hash_{i}", dummy_result)
        
        # Test get performance
        get_times = []
        for i in range(1000):
            start = time.perf_counter()
            result = await self.memory_cache.get(f"hash_{i % 10}")
            end = time.perf_counter()
            get_times.append((end - start) * 1000)  # Convert to ms
        
        # Test set performance  
        set_times = []
        for i in range(100):
            dummy_result = ValidationResult(
                decision=ValidationDecision.APPROVED,
                confidence=ValidationConfidence.HIGH,
                reason="Perf test",
                request_id=f"perf_{i}",
                processing_time_ms=0.1
            )
            
            start = time.perf_counter()
            await self.memory_cache.set(f"perf_hash_{i}", dummy_result)
            end = time.perf_counter()
            set_times.append((end - start) * 1000)
        
        stats = {
            'get_avg_ms': statistics.mean(get_times),
            'get_p95_ms': statistics.quantiles(get_times, n=20)[18],  # 95th percentile
            'get_p99_ms': statistics.quantiles(get_times, n=100)[98],  # 99th percentile
            'set_avg_ms': statistics.mean(set_times),
            'set_p95_ms': statistics.quantiles(set_times, n=20)[18],
            'target_met': statistics.mean(get_times) < 1.0
        }
        
        logger.info(f"Memory Cache: avg={stats['get_avg_ms']:.3f}ms, p95={stats['get_p95_ms']:.3f}ms, p99={stats['get_p99_ms']:.3f}ms")
        logger.info(f"Memory Cache Target (<1ms): {'✅ MET' if stats['target_met'] else '❌ MISSED'}")
        
        return stats
    
    async def test_policy_cache_performance(self) -> Dict[str, float]:
        """Test policy cache performance - target <5ms"""
        logger.info("Testing Policy Cache Performance (<5ms target)...")
        
        # Wait for policy rules to load
        await asyncio.sleep(1.0)
        
        eval_times = []
        for request in self.test_requests[:200]:  # Test subset
            start = time.perf_counter()
            result = await self.policy_cache.evaluate(request)
            end = time.perf_counter()
            eval_times.append((end - start) * 1000)
        
        stats = {
            'avg_ms': statistics.mean(eval_times),
            'p95_ms': statistics.quantiles(eval_times, n=20)[18],
            'p99_ms': statistics.quantiles(eval_times, n=100)[98] if len(eval_times) > 100 else max(eval_times),
            'target_met': statistics.mean(eval_times) < 5.0
        }
        
        logger.info(f"Policy Cache: avg={stats['avg_ms']:.3f}ms, p95={stats['p95_ms']:.3f}ms, p99={stats['p99_ms']:.3f}ms")
        logger.info(f"Policy Cache Target (<5ms): {'✅ MET' if stats['target_met'] else '❌ MISSED'}")
        
        return stats
    
    async def test_pattern_cache_performance(self) -> Dict[str, float]:
        """Test pattern cache performance - target <10ms"""
        logger.info("Testing Pattern Cache Performance (<10ms target)...")
        
        # Wait for model to load
        await asyncio.sleep(2.0)
        
        predict_times = []
        for request in self.test_requests[:100]:  # Smaller subset for ML
            start = time.perf_counter()
            prediction = await self.pattern_cache.predict(request)
            end = time.perf_counter()
            predict_times.append((end - start) * 1000)
        
        stats = {
            'avg_ms': statistics.mean(predict_times),
            'p95_ms': statistics.quantiles(predict_times, n=20)[18],
            'p99_ms': statistics.quantiles(predict_times, n=100)[98] if len(predict_times) > 100 else max(predict_times),
            'target_met': statistics.mean(predict_times) < 10.0
        }
        
        logger.info(f"Pattern Cache: avg={stats['avg_ms']:.3f}ms, p95={stats['p95_ms']:.3f}ms, p99={stats['p99_ms']:.3f}ms")
        logger.info(f"Pattern Cache Target (<10ms): {'✅ MET' if stats['target_met'] else '❌ MISSED'}")
        
        return stats
    
    async def test_end_to_end_performance(self) -> Dict[str, float]:
        """Test end-to-end dispatcher performance - target 99% <100ms"""
        logger.info("Testing End-to-End Performance (99% <100ms target)...")
        
        await self.dispatcher.start()
        
        # Let system warm up
        await asyncio.sleep(1.0)
        
        e2e_times = []
        for request in self.test_requests:
            start = time.perf_counter()
            result = await self.dispatcher.validate_request(request)
            end = time.perf_counter()
            e2e_times.append((end - start) * 1000)
        
        await self.dispatcher.stop()
        
        # Calculate statistics
        avg_time = statistics.mean(e2e_times)
        p95_time = statistics.quantiles(e2e_times, n=20)[18]
        p99_time = statistics.quantiles(e2e_times, n=100)[98]
        
        # Check target: 99% of requests < 100ms
        under_100ms = sum(1 for t in e2e_times if t < 100.0)
        percent_under_100ms = (under_100ms / len(e2e_times)) * 100
        
        stats = {
            'avg_ms': avg_time,
            'p95_ms': p95_time,
            'p99_ms': p99_time,
            'percent_under_100ms': percent_under_100ms,
            'target_met': percent_under_100ms >= 99.0,
            'total_requests': len(e2e_times)
        }
        
        logger.info(f"End-to-End: avg={avg_time:.1f}ms, p95={p95_time:.1f}ms, p99={p99_time:.1f}ms")
        logger.info(f"Under 100ms: {percent_under_100ms:.1f}% of {len(e2e_times)} requests")
        logger.info(f"End-to-End Target (99% <100ms): {'✅ MET' if stats['target_met'] else '❌ MISSED'}")
        
        return stats
    
    async def run_comprehensive_benchmark(self) -> Dict[str, any]:
        """Run complete performance benchmark suite"""
        logger.info("="*60)
        logger.info("LIGHTHOUSE SPEED LAYER PERFORMANCE BENCHMARK")
        logger.info("="*60)
        
        results = {}
        
        # Individual component tests
        results['memory_cache'] = await self.test_memory_cache_performance()
        await asyncio.sleep(0.5)
        
        results['policy_cache'] = await self.test_policy_cache_performance()  
        await asyncio.sleep(0.5)
        
        results['pattern_cache'] = await self.test_pattern_cache_performance()
        await asyncio.sleep(0.5)
        
        # End-to-end test
        results['end_to_end'] = await self.test_end_to_end_performance()
        
        # Performance summary
        logger.info("\n" + "="*60)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("="*60)
        
        targets_met = 0
        total_targets = 4
        
        for component, stats in results.items():
            status = "✅ PASSED" if stats.get('target_met', False) else "❌ FAILED"
            if stats.get('target_met', False):
                targets_met += 1
            logger.info(f"{component.upper():15s}: {status}")
        
        overall_score = (targets_met / total_targets) * 100
        logger.info(f"\nOVERALL SCORE: {overall_score:.0f}% ({targets_met}/{total_targets} targets met)")
        
        if overall_score >= 75:
            logger.info("🚀 SPEED LAYER OPTIMIZATION: SUCCESS")
        else:
            logger.warning("⚠️  SPEED LAYER OPTIMIZATION: NEEDS IMPROVEMENT")
        
        logger.info("="*60)
        
        results['overall_score'] = overall_score
        results['targets_met'] = targets_met
        results['total_targets'] = total_targets
        
        return results


async def run_performance_test():
    """Main entry point for performance testing"""
    tester = PerformanceTester()
    results = await tester.run_comprehensive_benchmark()
    return results


if __name__ == "__main__":
    # Run performance test
    import sys
    sys.path.insert(0, '/home/john/lighthouse/src')
    
    results = asyncio.run(run_performance_test())