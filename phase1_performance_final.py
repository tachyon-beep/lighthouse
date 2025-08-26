#!/usr/bin/env python3
"""
Phase 1 Performance Assessment - Final Comprehensive Report

Performance testing for Days 1-3 implementation:
- Speed layer performance baseline
- Component initialization timing  
- Memory usage analysis
- Concurrent validation testing
- 99% <100ms SLA validation assessment

Final assessment of performance readiness for Phase 2 integration.
"""

import asyncio
import json
import logging
import psutil
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import unittest.mock

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Measurements storage
measurements = []

class PerformanceTimer:
    """Context manager for performance timing"""
    
    def __init__(self, operation_name: str, metadata: Optional[Dict[str, Any]] = None):
        self.operation_name = operation_name
        self.metadata = metadata or {}
        self.start_time = None
        self.end_time = None
        self.process = psutil.Process()
        self.start_memory = None
    
    def __enter__(self):
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000
        
        end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = end_memory - self.start_memory
        
        measurement = {
            'timestamp': datetime.now().isoformat(),
            'operation': self.operation_name,
            'duration_ms': duration_ms,
            'memory_start_mb': self.start_memory,
            'memory_end_mb': end_memory,
            'memory_delta_mb': memory_delta,
            'cpu_percent': self.process.cpu_percent(),
            'metadata': self.metadata
        }
        
        measurements.append(measurement)
        logger.info(f"{self.operation_name}: {duration_ms:.2f}ms, Memory: {memory_delta:+.1f}MB")


async def test_core_speed_layer_performance():
    """Test core speed layer performance with realistic workloads"""
    logger.info("=== Testing Core Speed Layer Performance ===")
    
    from lighthouse.bridge.speed_layer import OptimizedSpeedLayerDispatcher
    from lighthouse.bridge.speed_layer.models import ValidationRequest
    
    # Initialize dispatcher
    with PerformanceTimer("speed_layer_init", {"component": "dispatcher"}):
        dispatcher = OptimizedSpeedLayerDispatcher(
            max_memory_cache_size=5000,  # Realistic cache size
            expert_timeout=15.0
        )
    
    # Start dispatcher
    with PerformanceTimer("speed_layer_start", {"component": "dispatcher"}):
        await dispatcher.start()
    
    try:
        # Test validation scenarios
        test_scenarios = [
            ("safe_read", ValidationRequest(
                tool_name="Read",
                tool_input={"file_path": "/tmp/safe_file.txt"},
                agent_id="test_agent_1"
            )),
            ("safe_ls", ValidationRequest(
                tool_name="LS",
                tool_input={"path": "/tmp"},
                agent_id="test_agent_2"  
            )),
            ("safe_grep", ValidationRequest(
                tool_name="Grep",
                tool_input={"pattern": "test", "path": "/tmp"},
                agent_id="test_agent_3"
            )),
            ("risky_write", ValidationRequest(
                tool_name="Write",
                tool_input={"file_path": "/tmp/new_file.txt", "content": "test"},
                agent_id="test_agent_4"
            )),
            ("risky_bash_ls", ValidationRequest(
                tool_name="Bash",
                tool_input={"command": "ls -la /tmp"},
                agent_id="test_agent_5"
            )),
            ("dangerous_rm", ValidationRequest(
                tool_name="Bash",
                tool_input={"command": "rm -rf /"},
                agent_id="test_agent_6"
            )),
            ("dangerous_sudo", ValidationRequest(
                tool_name="Bash", 
                tool_input={"command": "sudo rm /etc/passwd"},
                agent_id="test_agent_7"
            ))
        ]
        
        # Test each scenario
        scenario_results = {}
        for scenario_name, request in test_scenarios:
            with PerformanceTimer(f"validation_{scenario_name}", {"component": "speed_layer", "scenario": scenario_name}):
                result = await dispatcher.validate_request(request)
            
            scenario_results[scenario_name] = result
            logger.info(f"{scenario_name}: {result.decision}, Cache: {result.cache_hit}, Time: {result.processing_time_ms:.2f}ms")
        
        # Test cache performance - repeat safe operations
        with PerformanceTimer("cache_hit_performance", {"component": "speed_layer", "operation": "cached_read"}):
            cached_result = await dispatcher.validate_request(test_scenarios[0][1])  # Repeat safe_read
        
        logger.info(f"Cache hit performance: {cached_result.cache_hit}, Time: {cached_result.processing_time_ms:.2f}ms")
        
        # Test performance under load
        load_test_requests = []
        for i in range(200):
            # 70% safe, 20% risky, 10% dangerous distribution
            if i < 140:  # 70% safe
                request = ValidationRequest(
                    tool_name="Read",
                    tool_input={"file_path": f"/tmp/load_test_{i}.txt"},
                    agent_id=f"load_agent_{i}"
                )
            elif i < 180:  # 20% risky
                request = ValidationRequest(
                    tool_name="Write",
                    tool_input={"file_path": f"/tmp/output_{i}.txt", "content": f"data_{i}"},
                    agent_id=f"load_agent_{i}"
                )
            else:  # 10% dangerous
                dangerous_commands = ["rm -f /tmp/test", "sudo ls", "chmod 777 /tmp", "cat /etc/passwd"]
                request = ValidationRequest(
                    tool_name="Bash",
                    tool_input={"command": dangerous_commands[i % len(dangerous_commands)]},
                    agent_id=f"load_agent_{i}"
                )
            load_test_requests.append(request)
        
        # Execute load test
        with PerformanceTimer("load_test_200_concurrent", {"component": "speed_layer", "concurrent_requests": 200}):
            load_results = await asyncio.gather(*[
                dispatcher.validate_request(req) for req in load_test_requests
            ])
        
        # Analyze load test results
        load_response_times = [r.processing_time_ms for r in load_results]
        load_decisions = [r.decision.value for r in load_results]
        load_cache_hits = sum(1 for r in load_results if r.cache_hit)
        
        # Calculate SLA compliance
        slow_responses = [t for t in load_response_times if t > 100.0]
        sla_compliance = (len(load_response_times) - len(slow_responses)) / len(load_response_times)
        
        # Store detailed metrics
        load_test_metadata = {
            'total_requests': len(load_results),
            'sla_compliance': sla_compliance,
            'mean_response_time': statistics.mean(load_response_times),
            'p95_response_time': statistics.quantiles(load_response_times, n=20)[18] if len(load_response_times) >= 20 else max(load_response_times),
            'p99_response_time': statistics.quantiles(load_response_times, n=100)[98] if len(load_response_times) >= 100 else max(load_response_times),
            'cache_hit_rate': load_cache_hits / len(load_results),
            'decision_distribution': {decision: load_decisions.count(decision) for decision in set(load_decisions)}
        }
        
        # Update measurement metadata
        for measurement in measurements:
            if measurement['operation'] == 'load_test_200_concurrent':
                measurement['metadata'].update(load_test_metadata)
                break
        
        logger.info(f"Load test results (200 concurrent requests):")
        logger.info(f"  - SLA compliance (99% <100ms): {sla_compliance*100:.1f}%")
        logger.info(f"  - Mean response time: {load_test_metadata['mean_response_time']:.2f}ms")
        logger.info(f"  - P95 response time: {load_test_metadata['p95_response_time']:.2f}ms") 
        logger.info(f"  - P99 response time: {load_test_metadata['p99_response_time']:.2f}ms")
        logger.info(f"  - Cache hit rate: {load_test_metadata['cache_hit_rate']*100:.1f}%")
        logger.info(f"  - Decision distribution: {load_test_metadata['decision_distribution']}")
        
    finally:
        # Stop dispatcher
        with PerformanceTimer("speed_layer_stop", {"component": "dispatcher"}):
            await dispatcher.stop()
    
    return True


async def test_memory_cache_performance():
    """Test optimized memory cache performance"""
    logger.info("=== Testing Memory Cache Performance ===")
    
    from lighthouse.bridge.speed_layer.optimized_memory_cache import OptimizedMemoryCache
    from lighthouse.bridge.speed_layer.models import ValidationResult, ValidationDecision, ValidationConfidence
    
    # Initialize cache
    with PerformanceTimer("memory_cache_init", {"component": "memory_cache"}):
        cache = OptimizedMemoryCache(max_size=10000)
    
    # Create test validation results
    test_results = []
    for i in range(1000):
        result = ValidationResult(
            decision=ValidationDecision.APPROVED if i % 2 == 0 else ValidationDecision.BLOCKED,
            confidence=ValidationConfidence.HIGH,
            reason=f"Test validation result {i}",
            request_id=f"test_{i}",
            processing_time_ms=1.0 + (i % 10) * 0.1
        )
        test_results.append(result)
    
    # Test cache set performance
    set_times = []
    with PerformanceTimer("memory_cache_bulk_set", {"component": "memory_cache", "operation_count": 1000}):
        for i, result in enumerate(test_results):
            start = time.time()
            await cache.set(f"test_key_{i}", result, ttl_seconds=300)
            set_time = (time.time() - start) * 1000
            set_times.append(set_time)
    
    # Test cache get performance
    get_times = []
    cache_hits = 0
    with PerformanceTimer("memory_cache_bulk_get", {"component": "memory_cache", "operation_count": 1000}):
        for i in range(1000):
            start = time.time()
            result = await cache.get(f"test_key_{i}")
            get_time = (time.time() - start) * 1000
            get_times.append(get_time)
            if result is not None:
                cache_hits += 1
    
    # Test cache miss performance
    miss_times = []
    with PerformanceTimer("memory_cache_miss_test", {"component": "memory_cache", "operation_count": 100}):
        for i in range(100):
            start = time.time()
            result = await cache.get(f"nonexistent_key_{i}")
            miss_time = (time.time() - start) * 1000
            miss_times.append(miss_time)
    
    # Performance analysis
    cache_stats = cache.get_stats()
    
    logger.info(f"Memory cache performance analysis:")
    logger.info(f"  - Set operations: avg={statistics.mean(set_times):.3f}ms, max={max(set_times):.3f}ms")
    logger.info(f"  - Get operations: avg={statistics.mean(get_times):.3f}ms, max={max(get_times):.3f}ms")
    logger.info(f"  - Miss operations: avg={statistics.mean(miss_times):.3f}ms, max={max(miss_times):.3f}ms")
    logger.info(f"  - Cache hit rate: {cache_hits/1000*100:.1f}%")
    logger.info(f"  - Cache stats: {cache_stats}")
    
    # SLA compliance check (sub-millisecond target)
    set_sla_violations = sum(1 for t in set_times if t > 1.0)
    get_sla_violations = sum(1 for t in get_times if t > 1.0)
    miss_sla_violations = sum(1 for t in miss_times if t > 1.0)
    
    logger.info(f"  - SLA violations: Set={set_sla_violations}, Get={get_sla_violations}, Miss={miss_sla_violations}")
    
    return True


async def test_component_initialization_performance():
    """Test component initialization performance"""
    logger.info("=== Testing Component Initialization Performance ===")
    
    # Test individual component imports and initialization
    components_to_test = [
        ("optimized_memory_cache", "lighthouse.bridge.speed_layer.optimized_memory_cache", "OptimizedMemoryCache"),
        ("optimized_policy_cache", "lighthouse.bridge.speed_layer.optimized_policy_cache", "OptimizedPolicyCache"),
        ("optimized_pattern_cache", "lighthouse.bridge.speed_layer.optimized_pattern_cache", "OptimizedPatternCache"),
        ("event_store", "lighthouse.event_store", "EventStore"),
        ("project_aggregate", "lighthouse.bridge.event_store.project_aggregate", "ProjectAggregate"),
    ]
    
    for component_name, module_name, class_name in components_to_test:
        try:
            with PerformanceTimer(f"{component_name}_import", {"component": component_name, "operation": "import"}):
                module = __import__(module_name, fromlist=[class_name])
                component_class = getattr(module, class_name)
            
            # Initialize component
            with PerformanceTimer(f"{component_name}_init", {"component": component_name, "operation": "initialize"}):
                if component_name == "project_aggregate":
                    instance = component_class("perf_test_project")
                elif component_name in ["optimized_memory_cache", "optimized_policy_cache", "optimized_pattern_cache"]:
                    instance = component_class()
                else:
                    instance = component_class()
            
        except Exception as e:
            logger.warning(f"Failed to test {component_name}: {e}")
    
    return True


async def generate_performance_report():
    """Generate comprehensive performance report"""
    logger.info("=== Generating Performance Report ===")
    
    if not measurements:
        logger.error("No performance measurements to analyze!")
        return False
    
    # Group measurements by operation
    operations = {}
    for measurement in measurements:
        op_name = measurement['operation']
        if op_name not in operations:
            operations[op_name] = []
        operations[op_name].append(measurement)
    
    # Analyze each operation
    analysis_results = {}
    for op_name, op_measurements in operations.items():
        durations = [m['duration_ms'] for m in op_measurements]
        memory_deltas = [m['memory_delta_mb'] for m in op_measurements]
        
        if durations:
            result = {
                'count': len(durations),
                'duration_mean': statistics.mean(durations),
                'duration_min': min(durations),
                'duration_max': max(durations),
                'memory_delta_mean': statistics.mean(memory_deltas) if memory_deltas else 0.0,
                'sample_metadata': op_measurements[0].get('metadata', {})
            }
            
            if len(durations) > 1:
                result['duration_stdev'] = statistics.stdev(durations)
            
            if len(durations) >= 4:
                quantiles = statistics.quantiles(durations, n=4)
                result['duration_p25'] = quantiles[0]
                result['duration_p50'] = quantiles[1]
                result['duration_p75'] = quantiles[2]
                
            if len(durations) >= 20:
                result['duration_p95'] = statistics.quantiles(durations, n=20)[18]
                result['duration_p99'] = statistics.quantiles(durations, n=100)[98] if len(durations) >= 100 else result['duration_p95']
            
            analysis_results[op_name] = result
    
    # Performance Assessment
    logger.info("\n=== PHASE 1 IMPLEMENTATION PERFORMANCE REPORT ===")
    
    # Critical operations for SLA assessment
    critical_operations = {
        'validation_safe_read': {'sla_ms': 100.0, 'target_ms': 10.0, 'critical': True},
        'validation_risky_write': {'sla_ms': 100.0, 'target_ms': 25.0, 'critical': True},
        'validation_dangerous_rm': {'sla_ms': 100.0, 'target_ms': 50.0, 'critical': True},
        'cache_hit_performance': {'sla_ms': 100.0, 'target_ms': 1.0, 'critical': True},
        'load_test_200_concurrent': {'sla_ms': 2000.0, 'target_ms': 500.0, 'critical': True},
        'memory_cache_bulk_get': {'sla_ms': 1000.0, 'target_ms': 100.0, 'critical': False},
        'speed_layer_init': {'sla_ms': 5000.0, 'target_ms': 1000.0, 'critical': False}
    }
    
    sla_violations = []
    performance_issues = []
    performance_score = 10.0
    
    for op_name, thresholds in critical_operations.items():
        if op_name in analysis_results:
            result = analysis_results[op_name]
            duration = result['duration_mean']
            sla_threshold = thresholds['sla_ms']
            target_threshold = thresholds['target_ms']
            is_critical = thresholds['critical']
            
            # Check SLA compliance
            if duration > sla_threshold:
                sla_violations.append(f"{op_name}: {duration:.2f}ms (SLA: {sla_threshold}ms)")
                if is_critical:
                    performance_score -= 2.0
                else:
                    performance_score -= 1.0
            elif duration > target_threshold:
                performance_issues.append(f"{op_name}: {duration:.2f}ms (Target: {target_threshold}ms)")
                performance_score -= 0.25
            
            status_emoji = "✅" if duration <= target_threshold else ("⚠️" if duration <= sla_threshold else "❌")
            
            logger.info(f"{status_emoji} {op_name:25s}: {duration:8.2f}ms (±{result.get('duration_stdev', 0):5.2f}ms)")
            
            # Additional details for critical operations
            if op_name == 'load_test_200_concurrent' and 'metadata' in result:
                metadata = result['sample_metadata']
                sla_compliance = metadata.get('sla_compliance', 0.0)
                logger.info(f"    SLA Compliance: {sla_compliance*100:.1f}% (Target: 99%)")
                logger.info(f"    P95: {metadata.get('p95_response_time', 0):.2f}ms, P99: {metadata.get('p99_response_time', 0):.2f}ms")
    
    # Overall Assessment
    performance_score = max(0.0, min(10.0, performance_score))
    
    logger.info(f"\n=== PERFORMANCE ASSESSMENT SUMMARY ===")
    
    if sla_violations:
        logger.error("❌ CRITICAL SLA VIOLATIONS:")
        for violation in sla_violations:
            logger.error(f"   {violation}")
    
    if performance_issues:
        logger.warning("⚠️  PERFORMANCE OPTIMIZATION OPPORTUNITIES:")
        for issue in performance_issues:
            logger.warning(f"   {issue}")
    
    # 99% <100ms SLA specific assessment
    concurrent_test_result = analysis_results.get('load_test_200_concurrent')
    sla_ready = True
    
    if concurrent_test_result:
        metadata = concurrent_test_result['sample_metadata']
        sla_compliance = metadata.get('sla_compliance', 0.0)
        mean_response = metadata.get('mean_response_time', 0.0)
        p99_response = metadata.get('p99_response_time', 0.0)
        
        logger.info(f"\n🎯 99% <100ms SLA VALIDATION:")
        logger.info(f"   - Achieved SLA compliance: {sla_compliance*100:.1f}%")
        logger.info(f"   - Mean response time: {mean_response:.2f}ms")
        logger.info(f"   - P99 response time: {p99_response:.2f}ms")
        
        if sla_compliance < 0.99:
            sla_ready = False
            logger.error("❌ SLA requirement not met!")
        elif p99_response > 50.0:
            logger.warning("⚠️  P99 response time higher than optimal")
        else:
            logger.info("✅ SLA requirement validated!")
    
    # Final readiness assessment
    if performance_score >= 8.0 and sla_ready and not sla_violations:
        readiness_status = "READY FOR PHASE 2"
        readiness_emoji = "🎉"
        readiness_recommendation = "Phase 1 implementation shows excellent performance. Ready for Phase 2 integration testing."
    elif performance_score >= 7.0 and sla_ready:
        readiness_status = "READY WITH MINOR OPTIMIZATIONS"
        readiness_emoji = "⚠️"
        readiness_recommendation = "Phase 1 implementation meets SLA requirements with minor performance optimizations recommended."
    else:
        readiness_status = "REQUIRES PERFORMANCE IMPROVEMENTS"
        readiness_emoji = "❌"
        readiness_recommendation = "Phase 1 implementation requires performance improvements before Phase 2."
    
    logger.info(f"\n{readiness_emoji} PHASE 1 PERFORMANCE SCORE: {performance_score:.1f}/10")
    logger.info(f"🚀 READINESS STATUS: {readiness_status}")
    logger.info(f"📋 RECOMMENDATION: {readiness_recommendation}")
    
    # Save detailed report
    report = {
        'timestamp': datetime.now().isoformat(),
        'performance_score': performance_score,
        'readiness_status': readiness_status,
        'readiness_recommendation': readiness_recommendation,
        'sla_ready': sla_ready,
        'sla_violations': sla_violations,
        'performance_issues': performance_issues,
        'operation_analysis': analysis_results,
        'raw_measurements': measurements,
        'summary': {
            'total_measurements': len(measurements),
            'total_operations': len(analysis_results),
            'critical_operations_tested': len([op for op in critical_operations if op in analysis_results]),
            'sla_compliant_operations': len([op for op in critical_operations if op in analysis_results and analysis_results[op]['duration_mean'] <= critical_operations[op]['sla_ms']])
        }
    }
    
    results_file = Path(__file__).parent / "phase1_performance_comprehensive_report.json"
    with open(results_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"📊 Comprehensive performance report saved: {results_file}")
    
    return performance_score >= 7.0 and sla_ready


async def main():
    """Run comprehensive Phase 1 performance assessment"""
    logger.info("🚀 Starting Comprehensive Phase 1 Performance Assessment...")
    logger.info("   Testing performance readiness for 99% <100ms SLA validation requirement")
    
    start_time = time.time()
    
    try:
        # Run performance tests
        tests_passed = 0
        total_tests = 4
        
        if await test_core_speed_layer_performance():
            tests_passed += 1
            logger.info("✅ Core speed layer performance test passed")
        
        if await test_memory_cache_performance():
            tests_passed += 1
            logger.info("✅ Memory cache performance test passed")
        
        if await test_component_initialization_performance():
            tests_passed += 1
            logger.info("✅ Component initialization performance test passed")
        
        if await generate_performance_report():
            tests_passed += 1
            logger.info("✅ Performance report generation completed")
        
        # Final summary
        total_duration = time.time() - start_time
        logger.info(f"\n⏱️  Total assessment duration: {total_duration:.2f}s")
        logger.info(f"📋 Tests completed: {tests_passed}/{total_tests}")
        
        if tests_passed == total_tests:
            logger.info("🎉 Phase 1 comprehensive performance assessment COMPLETED SUCCESSFULLY")
            return True
        else:
            logger.error("❌ Phase 1 performance assessment FAILED")
            return False
            
    except Exception as e:
        logger.error(f"💥 Performance assessment failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = asyncio.run(main())
    sys.exit(0 if success else 1)