"""
Integrated Load Testing + Event Store Integrity Validation
Phase 1 Days 8-10: Combined multi-agent load testing with real-time integrity monitoring

This test suite integrates:
- Multi-agent coordination load testing (10, 100, 1000+ agents)
- Real-time event store integrity monitoring 
- Cryptographic hash validation under load
- Memory pressure testing with integrity verification
- FUSE latency validation during integrity monitoring
- Chaos engineering with integrity preservation validation
"""

import asyncio
import time
import gc
import os
import tempfile
import json
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

import pytest
import pytest_asyncio

# Import our load testing and integrity monitoring frameworks
try:
    from .test_multi_agent_load import (
        MultiAgentLoadTestFramework, 
        LoadTestAgent, 
        LoadTestMetrics,
        ChaosEngineeringFramework
    )
except ImportError:
    # Fall back to direct import for single file execution
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from test_multi_agent_load import (
        MultiAgentLoadTestFramework, 
        LoadTestAgent, 
        LoadTestMetrics,
        ChaosEngineeringFramework
    )

try:
    from lighthouse.integrity.monitoring import (
        EventStoreIntegrityMonitor,
        IntegrityViolation,
        IntegrityViolationType,
        console_alert_handler,
        log_alert_handler
    )
    INTEGRITY_AVAILABLE = True
except ImportError:
    INTEGRITY_AVAILABLE = False
    
    # Mock integrity system for testing
    class EventStoreIntegrityMonitor:
        def __init__(self, *args, **kwargs):
            self.violations = []
            self.metrics = Mock()
            self.metrics.violations_detected = 0
            self.metrics.violations_resolved = 0
            self.metrics.system_integrity_score = 100.0
    
    class IntegrityViolation:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


class IntegratedLoadIntegrityTestFramework:
    """
    Combined framework for load testing with integrity monitoring
    """
    
    def __init__(self, 
                 load_framework: MultiAgentLoadTestFramework = None,
                 integrity_monitor: EventStoreIntegrityMonitor = None):
        self.load_framework = load_framework or MultiAgentLoadTestFramework()
        self.integrity_monitor = integrity_monitor or EventStoreIntegrityMonitor(
            secret_key="integrated_test_secret",
            alert_callbacks=[self._integrity_alert_handler],
            check_interval=0.5
        )
        
        # Integration tracking
        self.integrity_violations_during_load = []
        self.load_events_monitored = 0
        self.integration_metrics = {
            'events_registered_for_monitoring': 0,
            'integrity_checks_during_load': 0,
            'violations_during_load_test': 0,
            'load_test_integrity_score': 100.0
        }
    
    def _integrity_alert_handler(self, violation: IntegrityViolation):
        """Handle integrity violations detected during load testing"""
        self.integrity_violations_during_load.append({
            'violation_id': violation.violation_id,
            'violation_type': violation.violation_type.value if hasattr(violation.violation_type, 'value') else str(violation.violation_type),
            'event_id': violation.event_id,
            'agent_id': violation.agent_id,
            'detected_at': violation.detected_at.isoformat() if hasattr(violation.detected_at, 'isoformat') else str(violation.detected_at),
            'severity': violation.severity
        })
        
        self.integration_metrics['violations_during_load_test'] += 1
        print(f"🚨 Load Test Integrity Violation: {violation.violation_id} - {violation.violation_type}")
    
    async def run_integrated_load_test_with_integrity(self, 
                                                    agent_configs: List[Dict[str, Any]],
                                                    duration_seconds: int = 60,
                                                    integrity_monitoring: bool = True) -> Dict[str, Any]:
        """
        Run integrated load test with real-time integrity monitoring
        
        Args:
            agent_configs: Configuration for load test agents
            duration_seconds: Duration of load test
            integrity_monitoring: Whether to enable integrity monitoring
            
        Returns:
            Combined metrics from load testing and integrity monitoring
        """
        # Setup load testing agents
        self.load_framework.create_agent_pool(agent_configs)
        
        # Start integrity monitoring if enabled
        if integrity_monitoring and INTEGRITY_AVAILABLE:
            await self.integrity_monitor.start_realtime_monitoring(num_processors=2)
            print(f"✅ Started integrity monitoring for {len(agent_configs)} agent load test")
        
        try:
            # Hook into load framework to register events for integrity monitoring
            original_generate_command = self.load_framework._generate_test_command
            self.load_framework._generate_test_command = self._generate_command_with_integrity_registration
            
            # Run load test
            print(f"🚀 Starting integrated load test: {len(agent_configs)} agents for {duration_seconds}s")
            load_metrics = await self.load_framework.run_load_test(duration_seconds)
            
            # Brief settling period for integrity checks to complete
            await asyncio.sleep(2)
            
            # Collect integrated results
            results = {
                'load_metrics': {
                    'total_agents': load_metrics.total_agents,
                    'avg_response_time': load_metrics.avg_response_time,
                    'p95_response_time': load_metrics.p95_response_time,
                    'p99_response_time': load_metrics.p99_response_time,
                    'error_rate': load_metrics.error_rate,
                    'memory_peak_mb': load_metrics.memory_peak_mb,
                    'fuse_operations': len(load_metrics.fuse_operation_times),
                    'avg_fuse_latency': sum(load_metrics.fuse_operation_times) / max(1, len(load_metrics.fuse_operation_times))
                },
                'integrity_metrics': self.integration_metrics.copy(),
                'violations_detected': self.integrity_violations_during_load.copy()
            }
            
            # Add integrity monitor metrics if available
            if INTEGRITY_AVAILABLE and hasattr(self.integrity_monitor, 'get_integrity_report'):
                integrity_report = self.integrity_monitor.get_integrity_report()
                results['integrity_system_report'] = integrity_report
            
            return results
            
        finally:
            # Cleanup - stop integrity monitoring
            if integrity_monitoring and INTEGRITY_AVAILABLE:
                await self.integrity_monitor.stop_realtime_monitoring()
                print("✅ Stopped integrity monitoring")
    
    def _generate_command_with_integrity_registration(self, agent: LoadTestAgent) -> Dict[str, Any]:
        """Generate command and register it for integrity monitoring"""
        # Generate base command
        command = {
            'tool_name': 'Bash',
            'tool_input': {'command': f'echo "agent_{agent.agent_id}_cmd_{agent.command_count}"'},
            'agent_id': agent.agent_id,
            'timestamp': time.time(),
            'command_id': f"cmd_{agent.agent_id}_{agent.command_count}"
        }
        
        # Register for integrity monitoring
        if INTEGRITY_AVAILABLE:
            self.integrity_monitor.register_event(
                event_id=command['command_id'],
                event_data=command,
                agent_id=agent.agent_id
            )
            
            self.integration_metrics['events_registered_for_monitoring'] += 1
        
        return command


# Test fixtures for integrated testing

@pytest_asyncio.fixture
async def integrated_test_framework():
    """Fixture providing integrated load + integrity test framework"""
    framework = IntegratedLoadIntegrityTestFramework()
    yield framework
    
    # Cleanup
    if hasattr(framework.integrity_monitor, 'stop_realtime_monitoring'):
        try:
            await framework.integrity_monitor.stop_realtime_monitoring()
        except:
            pass


# Integrated test scenarios

@pytest.mark.asyncio
@pytest.mark.load
@pytest.mark.integrity
class TestIntegratedLoadIntegrityScenarios:
    """Integrated load testing with event store integrity validation"""
    
    async def test_10_agent_load_with_integrity_monitoring(self, integrated_test_framework):
        """Test 10 agent load with real-time integrity monitoring"""
        agent_configs = [
            {'type': 'integrity_test', 'command_rate': 2.0, 'complexity': 'medium'}
            for _ in range(10)
        ]
        
        results = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=30,
            integrity_monitoring=True
        )
        
        # Validate load performance
        assert results['load_metrics']['total_agents'] == 10
        assert results['load_metrics']['avg_response_time'] < 0.1  # <100ms
        assert results['load_metrics']['error_rate'] < 0.01  # <1% errors
        
        # Validate integrity monitoring
        assert results['integrity_metrics']['events_registered_for_monitoring'] > 0
        assert results['integrity_metrics']['violations_during_load_test'] == 0  # No violations expected
        
        print(f"✅ 10-agent load test: {results['integrity_metrics']['events_registered_for_monitoring']} events monitored")
    
    async def test_100_agent_load_with_integrity_monitoring(self, integrated_test_framework):
        """Test 100 agent load with integrity monitoring under scale"""
        agent_configs = [
            {
                'type': 'standard',
                'command_rate': 1.0 if i % 2 == 0 else 0.5,
                'complexity': ['low', 'medium'][i % 2]
            }
            for i in range(100)
        ]
        
        results = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=45,
            integrity_monitoring=True
        )
        
        # Validate load performance at scale
        assert results['load_metrics']['total_agents'] == 100
        assert results['load_metrics']['p95_response_time'] < 0.2  # 95th percentile <200ms
        assert results['load_metrics']['error_rate'] < 0.05  # <5% errors under scale
        
        # Validate integrity monitoring scales
        assert results['integrity_metrics']['events_registered_for_monitoring'] > 100
        assert results['integrity_metrics']['violations_during_load_test'] == 0
        
        print(f"✅ 100-agent load test: {results['integrity_metrics']['events_registered_for_monitoring']} events monitored")
    
    @pytest.mark.slow  
    async def test_1000_agent_load_with_integrity_monitoring(self, integrated_test_framework):
        """Test 1000+ agent load with integrity monitoring - marked slow"""
        agent_configs = [
            {
                'type': 'standard',
                'command_rate': 0.2,  # Lower rate for stability at scale
                'complexity': 'low' if i < 800 else 'medium'
            }
            for i in range(1000)
        ]
        
        results = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=60,
            integrity_monitoring=True
        )
        
        # Validate load performance at extreme scale
        assert results['load_metrics']['total_agents'] == 1000
        assert results['load_metrics']['p99_response_time'] < 1.0  # 99th percentile <1s
        assert results['load_metrics']['error_rate'] < 0.1  # <10% errors at extreme scale
        
        # Validate integrity monitoring works at scale
        assert results['integrity_metrics']['events_registered_for_monitoring'] > 500
        
        print(f"✅ 1000-agent load test: {results['integrity_metrics']['events_registered_for_monitoring']} events monitored")


@pytest.mark.asyncio
@pytest.mark.integrity 
class TestIntegrityViolationDetectionUnderLoad:
    """Test integrity violation detection capabilities during load testing"""
    
    async def test_integrity_violation_detection_during_load(self, integrated_test_framework):
        """Test that integrity violations are detected even under load"""
        agent_configs = [
            {'type': 'standard', 'command_rate': 3.0, 'complexity': 'medium'}
            for _ in range(20)
        ]
        
        # Start load test
        load_task = asyncio.create_task(
            integrated_test_framework.run_integrated_load_test_with_integrity(
                agent_configs=agent_configs,
                duration_seconds=30,
                integrity_monitoring=True
            )
        )
        
        # Simulate integrity violation during load test
        async def inject_violation():
            await asyncio.sleep(10)  # Wait for load to ramp up
            
            if INTEGRITY_AVAILABLE:
                # Register a legitimate event
                test_event = {
                    'command_id': 'violation_test_001',
                    'tool_name': 'Bash',
                    'command': 'echo "original"',
                    'timestamp': time.time()
                }
                
                integrated_test_framework.integrity_monitor.register_event(
                    event_id='violation_test_001',
                    event_data=test_event,
                    agent_id='violation_test_agent'
                )
                
                await asyncio.sleep(1)
                
                # Simulate tampering by validating with different data
                tampered_event = test_event.copy()
                tampered_event['command'] = 'echo "tampered!"'
                
                # This should trigger a violation
                integrated_test_framework.integrity_monitor.validate_event_integrity(
                    'violation_test_001',
                    tampered_event
                )
                
                print("🔴 Simulated integrity violation during load test")
        
        # Run load test and violation injection concurrently
        violation_task = asyncio.create_task(inject_violation())
        
        results = await load_task
        await violation_task
        
        # Verify violation was detected despite load
        if INTEGRITY_AVAILABLE:
            assert results['integrity_metrics']['violations_during_load_test'] >= 1
            assert len(results['violations_detected']) >= 1
            
            violation = results['violations_detected'][0]
            assert violation['event_id'] == 'violation_test_001'
            
            print(f"✅ Integrity violation detected during load: {violation['violation_id']}")
        
        # Load performance should not be significantly impacted by violation detection
        assert results['load_metrics']['avg_response_time'] < 0.15  # <150ms average
    
    async def test_cryptographic_hash_validation_under_memory_pressure(self, integrated_test_framework):
        """Test cryptographic hash validation remains reliable under memory pressure"""
        # Create memory-intensive load
        agent_configs = [
            {'type': 'memory_intensive', 'command_rate': 2.0, 'complexity': 'high'}
            for _ in range(50)
        ]
        
        # Force initial garbage collection
        gc.collect()
        initial_memory = integrated_test_framework.load_framework.process.memory_info().rss / 1024 / 1024
        
        results = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=45,
            integrity_monitoring=True
        )
        
        # Verify integrity monitoring worked despite memory pressure
        assert results['integrity_metrics']['events_registered_for_monitoring'] > 0
        assert results['load_metrics']['memory_peak_mb'] > initial_memory  # Memory pressure created
        
        # No integrity violations should occur from memory pressure alone
        assert results['integrity_metrics']['violations_during_load_test'] == 0
        
        # System should remain stable
        memory_growth = results['load_metrics']['memory_peak_mb'] - initial_memory
        assert memory_growth < 1000, f"Memory growth {memory_growth:.1f}MB excessive during integrity monitoring"
        
        print(f"✅ Integrity monitoring stable under {memory_growth:.1f}MB memory pressure")


@pytest.mark.asyncio
@pytest.mark.chaos
@pytest.mark.integrity
class TestChaosEngineeringWithIntegrityPreservation:
    """Test integrity preservation during chaos engineering scenarios"""
    
    async def test_network_partition_integrity_preservation(self, integrated_test_framework):
        """Test that integrity monitoring continues during network partitions"""
        agent_configs = [
            {'type': 'standard', 'command_rate': 1.0, 'complexity': 'medium'}
            for _ in range(30)
        ]
        
        # Create chaos framework
        chaos_framework = ChaosEngineeringFramework(integrated_test_framework.load_framework)
        
        async def run_with_chaos():
            # Start integrity monitoring
            results = await integrated_test_framework.run_integrated_load_test_with_integrity(
                agent_configs=agent_configs,
                duration_seconds=50,
                integrity_monitoring=True
            )
            return results
        
        async def inject_network_partition():
            await asyncio.sleep(15)  # Let load stabilize
            
            # Simulate network partition for 20 seconds
            await chaos_framework.simulate_network_partition(partition_duration=20.0)
            print("🌪️ Network partition simulation completed")
        
        # Run load test with chaos injection
        results, _ = await asyncio.gather(
            run_with_chaos(),
            inject_network_partition(),
            return_exceptions=True
        )
        
        # Integrity monitoring should continue despite partition
        assert results['integrity_metrics']['events_registered_for_monitoring'] > 0
        
        # Some performance degradation expected during partition, but integrity preserved
        assert results['load_metrics']['error_rate'] < 0.3  # <30% errors during partition
        assert results['integrity_metrics']['violations_during_load_test'] == 0  # No integrity violations from partition
        
        print(f"✅ Integrity preserved during network partition: {results['integrity_metrics']['events_registered_for_monitoring']} events monitored")


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.integrity
class TestFUSELatencyWithIntegrityMonitoring:
    """Test FUSE operation latency during integrity monitoring"""
    
    async def test_fuse_latency_with_integrity_monitoring_overhead(self, integrated_test_framework):
        """Test FUSE operations maintain <5ms latency even with integrity monitoring"""
        # Create FUSE-heavy workload
        agent_configs = [
            {'type': 'fuse_heavy', 'command_rate': 4.0, 'complexity': 'medium'}
            for _ in range(40)
        ]
        
        results = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=40,
            integrity_monitoring=True
        )
        
        # Validate FUSE performance with integrity monitoring overhead
        if results['load_metrics']['fuse_operations'] > 0:
            avg_fuse_latency = results['load_metrics']['avg_fuse_latency']
            
            # FUSE operations should remain <5ms even with integrity overhead
            assert avg_fuse_latency < 0.005, f"FUSE latency {avg_fuse_latency*1000:.2f}ms exceeds 5ms with integrity monitoring"
            
            print(f"✅ FUSE latency maintained: {avg_fuse_latency*1000:.2f}ms average with integrity monitoring")
        
        # Integrity monitoring should not significantly impact FUSE performance
        assert results['integrity_metrics']['events_registered_for_monitoring'] > 0
        assert results['load_metrics']['p95_response_time'] < 0.1  # Overall system performance maintained


# Performance benchmarking for integrated system

@pytest.mark.asyncio
@pytest.mark.benchmark
class TestIntegratedSystemBenchmarks:
    """Benchmark integrated load testing + integrity monitoring performance"""
    
    async def test_integrated_system_baseline_performance(self, integrated_test_framework):
        """Establish baseline performance metrics for integrated system"""
        # Standard mixed workload
        agent_configs = [
            {
                'type': 'benchmark',
                'command_rate': 2.0,
                'complexity': ['low', 'medium', 'high'][i % 3]
            }
            for i in range(100)
        ]
        
        # Run with integrity monitoring
        start_time = time.time()
        results_with_integrity = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=60,
            integrity_monitoring=True
        )
        integrity_duration = time.time() - start_time
        
        # Run without integrity monitoring for comparison
        start_time = time.time()
        results_without_integrity = await integrated_test_framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=60,
            integrity_monitoring=False
        )
        no_integrity_duration = time.time() - start_time
        
        # Calculate integrity monitoring overhead
        integrity_overhead = (integrity_duration - no_integrity_duration) / no_integrity_duration
        
        print(f"📊 Baseline Performance Results:")
        print(f"  With Integrity: {results_with_integrity['load_metrics']['avg_response_time']:.3f}s avg response")
        print(f"  Without Integrity: {results_without_integrity['load_metrics']['avg_response_time']:.3f}s avg response")
        print(f"  Integrity Overhead: {integrity_overhead:.1%}")
        
        # Integrity monitoring overhead should be reasonable (<20%)
        assert integrity_overhead < 0.2, f"Integrity monitoring overhead {integrity_overhead:.1%} too high"
        
        # Performance should still meet SLAs with integrity monitoring
        assert results_with_integrity['load_metrics']['avg_response_time'] < 0.1  # <100ms
        assert results_with_integrity['load_metrics']['p95_response_time'] < 0.2  # <200ms
        
        # Events should be monitored
        assert results_with_integrity['integrity_metrics']['events_registered_for_monitoring'] > 500


if __name__ == "__main__":
    # Direct execution for testing
    async def main():
        print("🔗 Running Integrated Load + Integrity Testing...")
        
        framework = IntegratedLoadIntegrityTestFramework()
        
        # Quick integration test
        agent_configs = [
            {'type': 'demo', 'command_rate': 2.0, 'complexity': 'medium'}
            for _ in range(5)
        ]
        
        results = await framework.run_integrated_load_test_with_integrity(
            agent_configs=agent_configs,
            duration_seconds=20,
            integrity_monitoring=True
        )
        
        print("📊 Demo Results:")
        print(f"  Load: {results['load_metrics']['total_agents']} agents, {results['load_metrics']['avg_response_time']:.3f}s avg")
        print(f"  Integrity: {results['integrity_metrics']['events_registered_for_monitoring']} events monitored")
        print(f"  Violations: {results['integrity_metrics']['violations_during_load_test']}")
        
        print("✅ Integrated Load + Integrity Testing complete!")
    
    asyncio.run(main())