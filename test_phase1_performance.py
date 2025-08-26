#!/usr/bin/env python3
"""
Phase 1 Performance Assessment Script

Comprehensive performance testing for Days 1-3 implementation:
- Bridge initialization performance
- Speed layer baseline measurement
- Component startup/shutdown timing
- Memory usage analysis
- Concurrent validation testing

Tests performance readiness for 99% <100ms SLA validation requirement.
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
        self.start_cpu = None
    
    def __enter__(self):
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_cpu = self.process.cpu_percent()
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


async def test_bridge_initialization():
    """Test bridge initialization performance"""
    logger.info("=== Testing Bridge Initialization Performance ===")
    
    # Import here to avoid module loading time affecting test
    with PerformanceTimer("module_import", {"component": "bridge_modules"}):
        from lighthouse.bridge.main_bridge import LighthouseBridge
    
    # Test bridge creation (component initialization)
    with PerformanceTimer("bridge_creation", {"component": "constructor"}):
        bridge = LighthouseBridge(
            project_id="perf_test_project",
            mount_point="/tmp/lighthouse_perf_test",
            config={
                'fuse_foreground': True,
                'fuse_allow_other': False,
                'memory_cache_size': 1000,  # Smaller for testing
                'expert_timeout': 10.0
            }
        )
    
    # Test bridge startup (async component initialization) 
    with unittest.mock.patch.object(bridge.fuse_mount_manager, 'mount', unittest.mock.AsyncMock(return_value=True)), \
         unittest.mock.patch.object(bridge.fuse_mount_manager, 'unmount', unittest.mock.AsyncMock(return_value=True)):
        
        with PerformanceTimer("bridge_startup", {"component": "full_startup"}):
            startup_success = await bridge.start()
        
        if not startup_success:
            logger.error("Bridge startup failed!")
            return False
        
        # Test system status retrieval
        with PerformanceTimer("system_status", {"component": "status_retrieval"}):
            status = bridge.get_system_status()
        
        logger.info(f"Bridge status: Running={status['is_running']}, Components={len(status.get('components', {}))}")
        
        # Test bridge shutdown
        with PerformanceTimer("bridge_shutdown", {"component": "full_shutdown"}):
            await bridge.stop()
    
    return True


async def test_speed_layer_performance():
    """Test speed layer component performance"""
    logger.info("=== Testing Speed Layer Performance ===")
    
    from lighthouse.bridge.speed_layer import OptimizedSpeedLayerDispatcher
    from lighthouse.bridge.speed_layer.models import ValidationRequest
    
    # Initialize dispatcher
    with PerformanceTimer("speed_layer_init", {"component": "dispatcher"}):
        dispatcher = OptimizedSpeedLayerDispatcher(
            max_memory_cache_size=1000,
            expert_timeout=10.0
        )
    
    # Start dispatcher
    with PerformanceTimer("speed_layer_start", {"component": "dispatcher"}):
        await dispatcher.start()
    
    try:
        # Test safe command validation
        safe_request = ValidationRequest(
            tool_name="Read",
            tool_input={"file_path": "/tmp/test.txt"},
            agent_id="perf_test_agent"
        )
        
        with PerformanceTimer("safe_command_validation", {"component": "speed_layer", "command_type": "safe"}):
            result = await dispatcher.validate_request(safe_request)
        
        logger.info(f"Safe command result: {result.decision}, Cache: {result.cache_hit}")
        
        # Test risky command validation
        risky_request = ValidationRequest(
            tool_name="Bash",
            tool_input={"command": "rm /tmp/test_file"},
            agent_id="perf_test_agent"
        )
        
        with PerformanceTimer("risky_command_validation", {"component": "speed_layer", "command_type": "risky"}):
            result = await dispatcher.validate_request(risky_request)
        
        logger.info(f"Risky command result: {result.decision}, Cache: {result.cache_hit}")
        
        # Test cache hit performance (repeat safe command)
        with PerformanceTimer("cache_hit_validation", {"component": "speed_layer", "command_type": "cached"}):
            result = await dispatcher.validate_request(safe_request)
        
        logger.info(f"Cached command result: {result.decision}, Cache: {result.cache_hit}")
        
    finally:
        # Stop dispatcher
        with PerformanceTimer("speed_layer_stop", {"component": "dispatcher"}):
            await dispatcher.stop()
    
    return True


async def test_concurrent_validation():
    """Test concurrent validation performance"""
    logger.info("=== Testing Concurrent Validation Performance ===")
    
    from lighthouse.bridge.speed_layer import OptimizedSpeedLayerDispatcher
    from lighthouse.bridge.speed_layer.models import ValidationRequest
    
    dispatcher = OptimizedSpeedLayerDispatcher(max_memory_cache_size=1000)
    await dispatcher.start()
    
    try:
        # Create test requests
        test_requests = []
        for i in range(50):  # Start with 50 concurrent requests
            if i % 3 == 0:  # Safe commands
                request = ValidationRequest(
                    tool_name="Read",
                    tool_input={"file_path": f"/tmp/test_{i}.txt"},
                    agent_id=f"agent_{i}"
                )
            elif i % 3 == 1:  # File operations  
                request = ValidationRequest(
                    tool_name="Write",
                    tool_input={"file_path": f"/tmp/output_{i}.txt", "content": "test"},
                    agent_id=f"agent_{i}"
                )
            else:  # Bash commands
                request = ValidationRequest(
                    tool_name="Bash",
                    tool_input={"command": f"echo 'test {i}'"},
                    agent_id=f"agent_{i}"
                )
            test_requests.append(request)
        
        # Concurrent validation test
        with PerformanceTimer("concurrent_validation", {"component": "speed_layer", "concurrent_requests": len(test_requests)}):
            # Execute all requests concurrently
            results = await asyncio.gather(*[
                dispatcher.validate_request(req) for req in test_requests
            ])
        
        # Analyze results
        decisions = [r.decision.value for r in results]
        response_times = [r.processing_time_ms for r in results]
        cache_hits = sum(1 for r in results if r.cache_hit)
        
        logger.info(f"Concurrent validation results:")
        logger.info(f"  - Total requests: {len(results)}")
        logger.info(f"  - Cache hits: {cache_hits} ({cache_hits/len(results)*100:.1f}%)")
        logger.info(f"  - Response times - Mean: {statistics.mean(response_times):.2f}ms, P95: {statistics.quantiles(response_times, n=20)[18]:.2f}ms")
        logger.info(f"  - Decisions: {dict(zip(*zip(*[[d, decisions.count(d)] for d in set(decisions)])))}") 
        
    finally:
        await dispatcher.stop()
    
    return True


async def test_component_memory_usage():
    """Test memory usage of different components"""
    logger.info("=== Testing Component Memory Usage ===")
    
    # Baseline memory
    process = psutil.Process()
    baseline_memory = process.memory_info().rss / 1024 / 1024
    logger.info(f"Baseline memory usage: {baseline_memory:.1f}MB")
    
    # Test event store
    with PerformanceTimer("event_store_memory", {"component": "event_store"}):
        from lighthouse.event_store import EventStore
        event_store = EventStore()
        # Create some test events
        for i in range(100):
            await event_store.append_event(
                aggregate_id=f"test_{i}",
                event_type="test_event",
                event_data={"index": i, "data": f"test_data_{i}"}
            )
    
    current_memory = process.memory_info().rss / 1024 / 1024
    logger.info(f"After event store: {current_memory:.1f}MB (+{current_memory-baseline_memory:.1f}MB)")
    
    # Test FUSE components (mocked)
    with PerformanceTimer("fuse_components_memory", {"component": "fuse"}):
        from lighthouse.bridge.fuse_mount import LighthouseFUSE, FUSEMountManager
        from lighthouse.bridge.event_store import ProjectAggregate, EventStream
        from lighthouse.bridge.ast_anchoring import ASTAnchorManager, TreeSitterParser
        
        # Create components (but don't mount)
        project_aggregate = ProjectAggregate("memory_test")
        event_stream = EventStream(fuse_mount_path="/tmp/test")
        parser = TreeSitterParser()
        ast_manager = ASTAnchorManager(parser)
        
        fuse_fs = LighthouseFUSE(
            project_aggregate=project_aggregate,
            time_travel_debugger=None,
            event_stream=event_stream,
            ast_anchor_manager=ast_manager,
            auth_secret="test",
            mount_point="/tmp/test"
        )
    
    final_memory = process.memory_info().rss / 1024 / 1024
    logger.info(f"Final memory usage: {final_memory:.1f}MB (+{final_memory-baseline_memory:.1f}MB total)")
    
    return True


async def analyze_performance_results():
    """Analyze collected performance measurements"""
    logger.info("=== Performance Analysis ===")
    
    if not measurements:
        logger.error("No performance measurements collected!")
        return False
    
    # Group measurements by operation
    operations = {}
    for m in measurements:
        op = m['operation']
        if op not in operations:
            operations[op] = []
        operations[op].append(m)
    
    results = {}
    
    for op_name, op_measurements in operations.items():
        durations = [m['duration_ms'] for m in op_measurements]
        memory_deltas = [m['memory_delta_mb'] for m in op_measurements]
        
        if durations:
            results[op_name] = {
                'count': len(durations),
                'duration_mean': statistics.mean(durations),
                'duration_min': min(durations),
                'duration_max': max(durations),
                'memory_delta_mean': statistics.mean(memory_deltas) if memory_deltas else 0,
                'sample_metadata': op_measurements[0].get('metadata', {})
            }
            
            if len(durations) > 1:
                results[op_name]['duration_stdev'] = statistics.stdev(durations)
            
            if len(durations) >= 4:
                quantiles = statistics.quantiles(durations, n=4)
                results[op_name]['duration_p75'] = quantiles[2]
                results[op_name]['duration_p95'] = durations[int(len(durations) * 0.95)] if len(durations) >= 20 else max(durations)
    
    # Print results
    logger.info("\n=== PHASE 1 PERFORMANCE RESULTS ===")
    
    critical_operations = [
        'bridge_creation', 'bridge_startup', 'bridge_shutdown',
        'speed_layer_init', 'speed_layer_start',
        'safe_command_validation', 'risky_command_validation', 'cache_hit_validation',
        'concurrent_validation'
    ]
    
    sla_violations = []
    
    for op_name in critical_operations:
        if op_name in results:
            r = results[op_name]
            duration = r['duration_mean']
            
            # Check SLA compliance (different thresholds for different operations)
            if op_name in ['safe_command_validation', 'risky_command_validation', 'cache_hit_validation']:
                sla_threshold = 100.0  # 100ms for validation operations
                sla_compliant = duration < sla_threshold
                if not sla_compliant:
                    sla_violations.append(f"{op_name}: {duration:.2f}ms (>{sla_threshold}ms)")
            else:
                sla_compliant = True  # No strict SLA for initialization operations
            
            status = "✅" if sla_compliant else "❌"
            
            logger.info(f"{status} {op_name:25s}: {duration:8.2f}ms (±{r.get('duration_stdev', 0):5.2f}ms) Memory: {r['memory_delta_mean']:+6.1f}MB")
    
    # Overall assessment
    logger.info(f"\n=== PHASE 1 PERFORMANCE ASSESSMENT ===")
    
    if sla_violations:
        logger.warning("❌ SLA VIOLATIONS DETECTED:")
        for violation in sla_violations:
            logger.warning(f"   {violation}")
        performance_score = 6.0
    else:
        logger.info("✅ All critical operations meet SLA requirements")
        performance_score = 8.0
    
    # Additional analysis
    if 'concurrent_validation' in results:
        concurrent_result = results['concurrent_validation']
        concurrent_duration = concurrent_result['duration_mean']
        metadata = concurrent_result['sample_metadata']
        request_count = metadata.get('concurrent_requests', 'unknown')
        
        logger.info(f"✅ Concurrent validation ({request_count} requests): {concurrent_duration:.2f}ms")
        
        if concurrent_duration > 1000:  # More than 1 second for concurrent operations
            logger.warning("⚠️  Concurrent validation is slower than expected")
            performance_score -= 0.5
    
    # Check memory efficiency
    total_memory_delta = sum(r['memory_delta_mean'] for r in results.values())
    if total_memory_delta > 100:  # More than 100MB total memory increase
        logger.warning(f"⚠️  High memory usage: +{total_memory_delta:.1f}MB total")
        performance_score -= 0.5
    
    logger.info(f"\n🎯 PHASE 1 PERFORMANCE SCORE: {performance_score:.1f}/10")
    
    # Save detailed results
    results_file = Path(__file__).parent / "phase1_performance_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'performance_score': performance_score,
            'sla_violations': sla_violations,
            'operation_results': results,
            'raw_measurements': measurements
        }, f, indent=2)
    
    logger.info(f"📊 Detailed results saved to: {results_file}")
    
    return performance_score >= 7.0


async def main():
    """Run complete Phase 1 performance assessment"""
    logger.info("🚀 Starting Phase 1 Performance Assessment...")
    
    start_time = time.time()
    
    try:
        # Run all performance tests
        tests_passed = 0
        total_tests = 5
        
        if await test_bridge_initialization():
            tests_passed += 1
        
        if await test_speed_layer_performance():
            tests_passed += 1
        
        if await test_concurrent_validation():
            tests_passed += 1
        
        if await test_component_memory_usage():
            tests_passed += 1
        
        if await analyze_performance_results():
            tests_passed += 1
        
        # Final assessment
        total_duration = time.time() - start_time
        logger.info(f"\n⏱️  Total assessment time: {total_duration:.2f}s")
        logger.info(f"✅ Tests passed: {tests_passed}/{total_tests}")
        
        if tests_passed == total_tests:
            logger.info("🎉 Phase 1 performance assessment PASSED")
            return True
        else:
            logger.error("❌ Phase 1 performance assessment FAILED")
            return False
    
    except Exception as e:
        logger.error(f"💥 Performance assessment failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = asyncio.run(main())
    sys.exit(0 if success else 1)