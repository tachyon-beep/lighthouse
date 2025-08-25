"""
Performance Baseline Measurement Infrastructure

Comprehensive system for measuring and tracking performance baselines before
integration begins, as required by Plan Charlie Phase 2.
"""

import asyncio
import json
import logging
import os
import psutil
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
import uuid

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMeasurement:
    """Single performance measurement."""
    timestamp: datetime
    operation_type: str
    duration_ms: float
    memory_usage_mb: float
    cpu_percent: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class BaselineMeasurement:
    """Baseline performance measurement for a component."""
    component: str
    timestamp: datetime
    latency_p50: float
    latency_p95: float
    latency_p99: float
    latency_mean: float
    latency_std: float
    throughput_rps: float
    memory_usage_mb: float
    memory_peak_mb: float
    cpu_usage_percent: float
    cpu_peak_percent: float
    sample_count: int
    measurement_duration_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class RegressionReport:
    """Performance regression analysis report."""
    component: str
    baseline: BaselineMeasurement
    current: BaselineMeasurement
    has_regression: bool
    regression_percentage: float
    regression_details: Dict[str, float]
    analysis_timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['baseline'] = self.baseline.to_dict()
        data['current'] = self.current.to_dict()
        data['analysis_timestamp'] = self.analysis_timestamp.isoformat()
        return data


class PerformanceRegressionDetector:
    """Advanced regression detection with statistical analysis."""
    
    def __init__(self):
        """Initialize regression detector."""
        self.thresholds = {
            'latency_p99_threshold': 1.2,      # 20% increase = regression
            'latency_p95_threshold': 1.15,     # 15% increase = regression
            'throughput_threshold': 0.8,       # 20% decrease = regression
            'memory_threshold': 1.3,           # 30% increase = regression
            'cpu_threshold': 1.2               # 20% increase = regression
        }
    
    async def compare(self, baseline: BaselineMeasurement, 
                     current: BaselineMeasurement,
                     thresholds: Optional[Dict[str, float]] = None) -> RegressionReport:
        """
        Compare current performance against baseline to detect regressions.
        
        Args:
            baseline: Baseline performance measurement
            current: Current performance measurement
            thresholds: Custom regression thresholds
            
        Returns:
            Regression analysis report
        """
        if thresholds:
            self.thresholds.update(thresholds)
        
        regression_details = {}
        has_regression = False
        
        # Latency checks (higher is worse)
        latency_regression = current.latency_p99 / baseline.latency_p99
        if latency_regression > self.thresholds['latency_p99_threshold']:
            regression_details['latency_p99'] = latency_regression
            has_regression = True
        
        latency_p95_regression = current.latency_p95 / baseline.latency_p95
        if latency_p95_regression > self.thresholds['latency_p95_threshold']:
            regression_details['latency_p95'] = latency_p95_regression
            has_regression = True
        
        # Throughput check (lower is worse)
        throughput_ratio = current.throughput_rps / max(1, baseline.throughput_rps)
        if throughput_ratio < self.thresholds['throughput_threshold']:
            regression_details['throughput'] = throughput_ratio
            has_regression = True
        
        # Memory check (higher is worse)
        memory_ratio = current.memory_peak_mb / max(1, baseline.memory_peak_mb)
        if memory_ratio > self.thresholds['memory_threshold']:
            regression_details['memory_peak'] = memory_ratio
            has_regression = True
        
        # CPU check (higher is worse for same workload)
        cpu_ratio = current.cpu_peak_percent / max(1, baseline.cpu_peak_percent)
        if cpu_ratio > self.thresholds['cpu_threshold']:
            regression_details['cpu_peak'] = cpu_ratio
            has_regression = True
        
        # Calculate overall regression percentage
        if has_regression:
            regression_values = list(regression_details.values())
            regression_percentage = (sum(regression_values) / len(regression_values) - 1) * 100
        else:
            regression_percentage = 0.0
        
        return RegressionReport(
            component=current.component,
            baseline=baseline,
            current=current,
            has_regression=has_regression,
            regression_percentage=regression_percentage,
            regression_details=regression_details,
            analysis_timestamp=datetime.utcnow()
        )


class PerformanceMeasurementCollector:
    """Collects performance measurements for operations."""
    
    def __init__(self, max_samples: int = 10000):
        """Initialize measurement collector."""
        self.measurements: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_samples))
        self.active_measurements: Dict[str, Dict[str, Any]] = {}
        self.system_monitor = psutil.Process()
        
    async def start_measurement(self, operation_type: str, 
                               metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Start measuring an operation.
        
        Args:
            operation_type: Type of operation being measured
            metadata: Additional metadata about the operation
            
        Returns:
            Measurement ID for stopping measurement
        """
        measurement_id = str(uuid.uuid4())
        
        # Capture initial state
        initial_memory = self.system_monitor.memory_info().rss / 1024 / 1024  # MB
        initial_cpu = self.system_monitor.cpu_percent()
        
        self.active_measurements[measurement_id] = {
            'operation_type': operation_type,
            'start_time': time.perf_counter(),
            'start_timestamp': datetime.utcnow(),
            'initial_memory': initial_memory,
            'initial_cpu': initial_cpu,
            'metadata': metadata or {}
        }
        
        return measurement_id
    
    async def finish_measurement(self, measurement_id: str) -> PerformanceMeasurement:
        """
        Finish measuring an operation.
        
        Args:
            measurement_id: ID returned by start_measurement
            
        Returns:
            Performance measurement result
        """
        if measurement_id not in self.active_measurements:
            raise ValueError(f"Unknown measurement ID: {measurement_id}")
        
        active = self.active_measurements[measurement_id]
        
        # Calculate duration
        duration_s = time.perf_counter() - active['start_time']
        duration_ms = duration_s * 1000
        
        # Capture final state
        final_memory = self.system_monitor.memory_info().rss / 1024 / 1024  # MB
        final_cpu = self.system_monitor.cpu_percent()
        
        measurement = PerformanceMeasurement(
            timestamp=active['start_timestamp'],
            operation_type=active['operation_type'],
            duration_ms=duration_ms,
            memory_usage_mb=max(final_memory, active['initial_memory']),
            cpu_percent=max(final_cpu, active['initial_cpu']),
            metadata=active['metadata']
        )
        
        # Store measurement
        self.measurements[active['operation_type']].append(measurement)
        
        # Clean up
        del self.active_measurements[measurement_id]
        
        return measurement
    
    async def measure_operation(self, operation_type: str, 
                               operation_func: Callable,
                               metadata: Optional[Dict[str, Any]] = None) -> PerformanceMeasurement:
        """
        Measure a complete operation.
        
        Args:
            operation_type: Type of operation
            operation_func: Function to execute and measure
            metadata: Additional metadata
            
        Returns:
            Performance measurement
        """
        measurement_id = await self.start_measurement(operation_type, metadata)
        
        try:
            if asyncio.iscoroutinefunction(operation_func):
                result = await operation_func()
            else:
                result = operation_func()
            
            measurement = await self.finish_measurement(measurement_id)
            measurement.metadata['result'] = 'success'
            measurement.metadata['operation_result'] = str(result)[:100]  # Truncate
            
            return measurement
            
        except Exception as e:
            measurement = await self.finish_measurement(measurement_id)
            measurement.metadata['result'] = 'error'
            measurement.metadata['error'] = str(e)[:100]  # Truncate
            raise
    
    def get_measurements(self, operation_type: str, 
                        limit: Optional[int] = None) -> List[PerformanceMeasurement]:
        """Get measurements for an operation type."""
        measurements = list(self.measurements.get(operation_type, []))
        if limit:
            measurements = measurements[-limit:]
        return measurements
    
    def get_all_measurements(self) -> Dict[str, List[PerformanceMeasurement]]:
        """Get all measurements grouped by operation type."""
        return {
            op_type: list(measurements)
            for op_type, measurements in self.measurements.items()
        }


class PerformanceBaselineManager:
    """
    Main performance baseline management system.
    
    Establishes baselines before component integration and provides
    regression detection throughout development.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize baseline manager.
        
        Args:
            storage_path: Path to store baseline data (default: ./data/baselines)
        """
        self.storage_path = Path(storage_path or "./data/baselines")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.collector = PerformanceMeasurementCollector()
        self.regression_detector = PerformanceRegressionDetector()
        
        # Baseline storage
        self.baselines: Dict[str, BaselineMeasurement] = {}
        
        # Load existing baselines
        self._load_baselines()
    
    def _load_baselines(self) -> None:
        """Load baselines from storage."""
        baseline_file = self.storage_path / "baselines.json"
        
        if baseline_file.exists():
            try:
                with open(baseline_file, 'r') as f:
                    data = json.load(f)
                
                for component, baseline_data in data.items():
                    baseline_data['timestamp'] = datetime.fromisoformat(baseline_data['timestamp'])
                    self.baselines[component] = BaselineMeasurement(**baseline_data)
                
                logger.info(f"Loaded {len(self.baselines)} performance baselines")
                
            except Exception as e:
                logger.error(f"Failed to load baselines: {str(e)}")
    
    def _save_baselines(self) -> None:
        """Save baselines to storage."""
        baseline_file = self.storage_path / "baselines.json"
        
        try:
            data = {
                component: baseline.to_dict()
                for component, baseline in self.baselines.items()
            }
            
            with open(baseline_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
            logger.info(f"Saved {len(self.baselines)} performance baselines")
            
        except Exception as e:
            logger.error(f"Failed to save baselines: {str(e)}")
    
    async def establish_baseline(self, component: str, 
                                measurement_duration_seconds: int = 60,
                                target_operations: int = 1000) -> BaselineMeasurement:
        """
        Establish performance baseline for component before integration.
        
        Args:
            component: Component name to baseline
            measurement_duration_seconds: How long to measure
            target_operations: Target number of operations to measure
            
        Returns:
            Baseline measurement
        """
        logger.info(f"Establishing baseline for {component} (duration: {measurement_duration_seconds}s, target: {target_operations} ops)")
        
        start_time = time.time()
        measurements = []
        operation_count = 0
        
        # Measurement loop
        while (time.time() - start_time < measurement_duration_seconds and
               operation_count < target_operations):
            
            try:
                # Create a representative operation for this component
                operation_func = self._get_component_operation(component)
                
                measurement = await self.collector.measure_operation(
                    f"{component}_baseline",
                    operation_func,
                    {'baseline_run': True, 'operation_number': operation_count}
                )
                
                measurements.append(measurement)
                operation_count += 1
                
                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.001)
                
            except Exception as e:
                logger.warning(f"Baseline measurement failed for {component}: {str(e)}")
        
        if not measurements:
            raise ValueError(f"No successful measurements collected for {component}")
        
        # Calculate baseline statistics
        durations = [m.duration_ms for m in measurements]
        memory_usage = [m.memory_usage_mb for m in measurements]
        cpu_usage = [m.cpu_percent for m in measurements]
        
        baseline = BaselineMeasurement(
            component=component,
            timestamp=datetime.utcnow(),
            latency_p50=statistics.median(durations),
            latency_p95=statistics.quantiles(durations, n=20)[18] if len(durations) > 20 else max(durations),
            latency_p99=statistics.quantiles(durations, n=100)[98] if len(durations) > 100 else max(durations),
            latency_mean=statistics.mean(durations),
            latency_std=statistics.stdev(durations) if len(durations) > 1 else 0.0,
            throughput_rps=operation_count / (time.time() - start_time),
            memory_usage_mb=statistics.mean(memory_usage),
            memory_peak_mb=max(memory_usage),
            cpu_usage_percent=statistics.mean(cpu_usage),
            cpu_peak_percent=max(cpu_usage),
            sample_count=len(measurements),
            measurement_duration_seconds=time.time() - start_time
        )
        
        # Store baseline
        self.baselines[component] = baseline
        self._save_baselines()
        
        logger.info(f"Baseline established for {component}:")
        logger.info(f"  Latency P99: {baseline.latency_p99:.2f}ms")
        logger.info(f"  Throughput: {baseline.throughput_rps:.2f} RPS")
        logger.info(f"  Memory peak: {baseline.memory_peak_mb:.2f} MB")
        logger.info(f"  Samples: {baseline.sample_count}")
        
        return baseline
    
    def _get_component_operation(self, component: str) -> Callable:
        """Get representative operation for component baseline measurement."""
        
        # Component-specific operations
        component_operations = {
            'event_store': self._event_store_operation,
            'validation_engine': self._validation_engine_operation,
            'expert_coordination': self._expert_coordination_operation,
            'fuse_filesystem': self._fuse_filesystem_operation,
            'authentication_system': self._authentication_operation,
            'rate_limiter': self._rate_limiter_operation
        }
        
        operation = component_operations.get(component)
        if not operation:
            # Default operation - measure basic system performance
            operation = self._default_operation
        
        return operation
    
    async def _event_store_operation(self):
        """Representative event store operation."""
        # Simulate event store write + read
        data = {"test": "data", "timestamp": time.time()}
        # This would normally interact with actual event store
        await asyncio.sleep(0.001)  # Simulate I/O
        return len(json.dumps(data))
    
    async def _validation_engine_operation(self):
        """Representative validation engine operation."""
        # Simulate command validation
        command = "test command for validation"
        # This would normally run through validation pipeline
        await asyncio.sleep(0.002)  # Simulate processing
        return len(command)
    
    async def _expert_coordination_operation(self):
        """Representative expert coordination operation."""
        # Simulate expert consensus request
        experts = ["expert1", "expert2", "expert3"]
        # This would normally coordinate expert responses
        await asyncio.sleep(0.005)  # Simulate coordination
        return len(experts)
    
    async def _fuse_filesystem_operation(self):
        """Representative FUSE filesystem operation."""
        # Simulate file system operation
        path = "/test/path/file.txt"
        content = "test content"
        # This would normally interact with FUSE mount
        await asyncio.sleep(0.001)  # Simulate file I/O
        return len(path) + len(content)
    
    async def _authentication_operation(self):
        """Representative authentication operation."""
        # Simulate token validation
        token = "test_token_123456789"
        # This would normally validate HMAC token
        await asyncio.sleep(0.0005)  # Simulate crypto operations
        return len(token)
    
    async def _rate_limiter_operation(self):
        """Representative rate limiter operation."""
        # Simulate rate limit check
        client_id = "test_client"
        # This would normally check rate limits
        await asyncio.sleep(0.0001)  # Simulate lookup
        return len(client_id)
    
    async def _default_operation(self):
        """Default system operation measurement."""
        # Basic CPU and memory operation
        data = list(range(100))
        result = sum(x * x for x in data)
        await asyncio.sleep(0.001)
        return result
    
    async def measure_current_performance(self, component: str,
                                         sample_size: int = 100) -> BaselineMeasurement:
        """
        Measure current performance for component.
        
        Args:
            component: Component to measure
            sample_size: Number of samples to collect
            
        Returns:
            Current performance measurement
        """
        logger.info(f"Measuring current performance for {component} ({sample_size} samples)")
        
        start_time = time.time()
        measurements = []
        
        for i in range(sample_size):
            try:
                operation_func = self._get_component_operation(component)
                
                measurement = await self.collector.measure_operation(
                    f"{component}_current",
                    operation_func,
                    {'current_run': True, 'sample_number': i}
                )
                
                measurements.append(measurement)
                
            except Exception as e:
                logger.warning(f"Current measurement failed for {component}: {str(e)}")
        
        if not measurements:
            raise ValueError(f"No successful measurements collected for {component}")
        
        # Calculate current performance statistics
        durations = [m.duration_ms for m in measurements]
        memory_usage = [m.memory_usage_mb for m in measurements]
        cpu_usage = [m.cpu_percent for m in measurements]
        
        return BaselineMeasurement(
            component=f"{component}_current",
            timestamp=datetime.utcnow(),
            latency_p50=statistics.median(durations),
            latency_p95=statistics.quantiles(durations, n=20)[18] if len(durations) > 20 else max(durations),
            latency_p99=statistics.quantiles(durations, n=100)[98] if len(durations) > 100 else max(durations),
            latency_mean=statistics.mean(durations),
            latency_std=statistics.stdev(durations) if len(durations) > 1 else 0.0,
            throughput_rps=len(measurements) / (time.time() - start_time),
            memory_usage_mb=statistics.mean(memory_usage),
            memory_peak_mb=max(memory_usage),
            cpu_usage_percent=statistics.mean(cpu_usage),
            cpu_peak_percent=max(cpu_usage),
            sample_count=len(measurements),
            measurement_duration_seconds=time.time() - start_time
        )
    
    async def detect_performance_regression(self, component: str,
                                          thresholds: Optional[Dict[str, float]] = None) -> RegressionReport:
        """
        Detect if component performance has regressed from baseline.
        
        Args:
            component: Component to check for regression
            thresholds: Custom regression thresholds
            
        Returns:
            Regression analysis report
        """
        if component not in self.baselines:
            raise ValueError(f"No baseline found for component: {component}")
        
        baseline = self.baselines[component]
        current = await self.measure_current_performance(component)
        
        regression = await self.regression_detector.compare(
            baseline=baseline,
            current=current,
            thresholds=thresholds
        )
        
        if regression.has_regression:
            logger.error(f"Performance regression detected in {component}:")
            for metric, ratio in regression.regression_details.items():
                logger.error(f"  {metric}: {ratio:.2f}x baseline")
        else:
            logger.info(f"No performance regression detected in {component}")
        
        return regression
    
    def get_baseline(self, component: str) -> Optional[BaselineMeasurement]:
        """Get baseline for component."""
        return self.baselines.get(component)
    
    def list_baselines(self) -> List[str]:
        """List all components with baselines."""
        return list(self.baselines.keys())
    
    def get_baseline_summary(self) -> Dict[str, Any]:
        """Get summary of all baselines."""
        return {
            'total_baselines': len(self.baselines),
            'baselines': {
                component: {
                    'latency_p99_ms': baseline.latency_p99,
                    'throughput_rps': baseline.throughput_rps,
                    'memory_peak_mb': baseline.memory_peak_mb,
                    'established': baseline.timestamp.isoformat()
                }
                for component, baseline in self.baselines.items()
            }
        }


# Global baseline manager
_global_baseline_manager: Optional[PerformanceBaselineManager] = None


def get_baseline_manager() -> PerformanceBaselineManager:
    """Get global baseline manager instance."""
    global _global_baseline_manager
    if _global_baseline_manager is None:
        _global_baseline_manager = PerformanceBaselineManager()
    return _global_baseline_manager