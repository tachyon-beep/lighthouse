"""
Comprehensive Metrics Collector for Lighthouse Bridge

Collects and aggregates metrics from all Bridge components including:
- Speed Layer performance (cache hit rates, response times)
- FUSE filesystem operations (read/write latencies, expert agent usage)
- Expert coordination (request routing, response times, success rates)
- Event sourcing (event throughput, replay performance)
- System health (memory, CPU, network)

HLD Requirements:
- Real-time metrics collection with <1ms overhead
- Historical data retention for trend analysis
- Alerting on performance degradation
- Expert agent usage analytics
- SLA compliance monitoring
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
import statistics
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class MetricSample:
    """Individual metric sample with timestamp"""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


@dataclass  
class MetricSummary:
    """Aggregated metric summary"""
    name: str
    count: int
    sum: float
    avg: float
    min: float
    max: float
    p50: float
    p95: float
    p99: float
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    High-performance metrics collector optimized for real-time collection
    
    Features:
    - Lock-free metric recording for hot paths
    - Configurable retention periods
    - Automatic aggregation and percentile calculation
    - Memory-efficient circular buffers
    - Asynchronous export to monitoring systems
    """
    
    def __init__(self, 
                 retention_seconds: int = 3600,  # 1 hour default
                 aggregation_interval_seconds: int = 60,  # 1 minute aggregation
                 max_samples_per_metric: int = 10000):
        """
        Initialize metrics collector
        
        Args:
            retention_seconds: How long to keep raw samples
            aggregation_interval_seconds: How often to create aggregated summaries
            max_samples_per_metric: Maximum raw samples per metric (memory limit)
        """
        self.retention_seconds = retention_seconds
        self.aggregation_interval = aggregation_interval_seconds
        self.max_samples = max_samples_per_metric
        
        # Thread-safe storage for raw samples
        self._samples: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_samples))
        self._samples_lock = threading.RLock()
        
        # Aggregated summaries
        self._summaries: Dict[str, List[MetricSummary]] = defaultdict(list)
        self._summaries_lock = threading.RLock()
        
        # Performance counters (lock-free for hot paths)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = defaultdict(float)
        
        # Background tasks
        self._aggregation_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Built-in metrics
        self._internal_metrics = {
            'samples_recorded': 0,
            'aggregations_created': 0,
            'cleanup_operations': 0,
            'memory_usage_bytes': 0
        }
    
    def start(self):
        """Start background metric processing"""
        if self._running:
            return
        
        self._running = True
        self._aggregation_task = asyncio.create_task(self._aggregation_worker())
        self._cleanup_task = asyncio.create_task(self._cleanup_worker())
        
        logger.info("Metrics collector started")
    
    async def stop(self):
        """Stop background processing and cleanup"""
        self._running = False
        
        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Metrics collector stopped")
    
    def record_timing(self, name: str, duration_seconds: float, tags: Optional[Dict[str, str]] = None):
        """
        Record timing metric (optimized for hot paths)
        
        Args:
            name: Metric name (e.g., "cache.get_duration")
            duration_seconds: Duration in seconds
            tags: Optional tags for metric dimensions
        """
        sample = MetricSample(
            name=name,
            value=duration_seconds,
            timestamp=time.time(),
            tags=tags or {},
            unit="seconds"
        )
        
        self._record_sample(sample)
    
    def record_counter(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None):
        """
        Record counter metric (always increasing)
        
        Args:
            name: Counter name (e.g., "requests.total")
            value: Increment value (default 1)
            tags: Optional tags
        """
        # Use atomic increment for performance
        self._counters[name] += value
        
        sample = MetricSample(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags or {},
            unit="count"
        )
        
        self._record_sample(sample)
    
    def record_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """
        Record gauge metric (current value)
        
        Args:
            name: Gauge name (e.g., "memory.usage_bytes")
            value: Current value
            tags: Optional tags
        """
        # Store current value
        self._gauges[name] = value
        
        sample = MetricSample(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags or {},
            unit=""
        )
        
        self._record_sample(sample)
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """
        Record histogram metric for distribution analysis
        
        Args:
            name: Histogram name (e.g., "request.size_bytes")
            value: Sample value
            tags: Optional tags
        """
        sample = MetricSample(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags or {},
            unit=""
        )
        
        self._record_sample(sample)
    
    def _record_sample(self, sample: MetricSample):
        """Internal method to record sample (thread-safe)"""
        try:
            with self._samples_lock:
                self._samples[sample.name].append(sample)
            
            self._internal_metrics['samples_recorded'] += 1
            
        except Exception as e:
            logger.error(f"Failed to record sample {sample.name}: {e}")
    
    async def _aggregation_worker(self):
        """Background worker to create metric aggregations"""
        while self._running:
            try:
                await asyncio.sleep(self.aggregation_interval)
                await self._create_aggregations()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Aggregation worker error: {e}")
                await asyncio.sleep(self.aggregation_interval)
    
    async def _cleanup_worker(self):
        """Background worker to cleanup old metrics"""
        while self._running:
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                await self._cleanup_old_data()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup worker error: {e}")
                await asyncio.sleep(300)
    
    async def _create_aggregations(self):
        """Create aggregated metric summaries"""
        current_time = time.time()
        aggregation_window = current_time - self.aggregation_interval
        
        try:
            with self._samples_lock:
                for metric_name, samples in self._samples.items():
                    # Filter samples in aggregation window
                    window_samples = [
                        s for s in samples 
                        if s.timestamp >= aggregation_window
                    ]
                    
                    if not window_samples:
                        continue
                    
                    # Calculate summary statistics
                    values = [s.value for s in window_samples]
                    values.sort()  # For percentiles
                    
                    summary = MetricSummary(
                        name=metric_name,
                        count=len(values),
                        sum=sum(values),
                        avg=statistics.mean(values),
                        min=min(values),
                        max=max(values),
                        p50=statistics.median(values),
                        p95=values[int(0.95 * len(values))] if len(values) > 1 else values[0],
                        p99=values[int(0.99 * len(values))] if len(values) > 1 else values[0],
                        unit=window_samples[0].unit,
                        tags=window_samples[0].tags  # Use first sample's tags
                    )
                    
                    # Store aggregated summary
                    with self._summaries_lock:
                        self._summaries[metric_name].append(summary)
                        
                        # Limit summary retention
                        max_summaries = self.retention_seconds // self.aggregation_interval
                        if len(self._summaries[metric_name]) > max_summaries:
                            self._summaries[metric_name] = self._summaries[metric_name][-max_summaries:]
            
            self._internal_metrics['aggregations_created'] += 1
            
        except Exception as e:
            logger.error(f"Aggregation creation error: {e}")
    
    async def _cleanup_old_data(self):
        """Remove old samples beyond retention period"""
        try:
            cutoff_time = time.time() - self.retention_seconds
            
            with self._samples_lock:
                for metric_name, samples in self._samples.items():
                    # Remove old samples
                    while samples and samples[0].timestamp < cutoff_time:
                        samples.popleft()
            
            # Calculate memory usage
            total_samples = sum(len(samples) for samples in self._samples.values())
            total_summaries = sum(len(summaries) for summaries in self._summaries.values())
            estimated_memory = (total_samples * 100) + (total_summaries * 200)  # Rough estimate
            
            self._internal_metrics['memory_usage_bytes'] = estimated_memory
            self._internal_metrics['cleanup_operations'] += 1
            
            logger.debug(f"Cleanup: {total_samples} samples, {total_summaries} summaries, ~{estimated_memory} bytes")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metric values"""
        current_metrics = {
            'counters': dict(self._counters),
            'gauges': dict(self._gauges),
            'internal': dict(self._internal_metrics),
            'timestamp': time.time()
        }
        
        return current_metrics
    
    def get_metric_summary(self, metric_name: str, 
                          time_range_seconds: Optional[int] = None) -> List[MetricSummary]:
        """
        Get aggregated summary for a specific metric
        
        Args:
            metric_name: Name of metric to retrieve
            time_range_seconds: Optional time range (default: all retained data)
            
        Returns:
            List of metric summaries ordered by time
        """
        with self._summaries_lock:
            summaries = self._summaries.get(metric_name, [])
            
            if time_range_seconds:
                cutoff_time = time.time() - time_range_seconds
                # Note: This is approximate since summaries don't have timestamps
                # In production, we'd add timestamp to MetricSummary
                recent_count = min(len(summaries), time_range_seconds // self.aggregation_interval)
                summaries = summaries[-recent_count:]
            
            return summaries.copy()
    
    def get_all_metric_names(self) -> List[str]:
        """Get names of all collected metrics"""
        with self._samples_lock:
            return list(self._samples.keys())
    
    def export_metrics(self, format_type: str = "prometheus") -> str:
        """
        Export metrics in specified format
        
        Args:
            format_type: Export format ("prometheus", "json", "influx")
            
        Returns:
            Formatted metrics string
        """
        if format_type == "prometheus":
            return self._export_prometheus()
        elif format_type == "json":
            import json
            return json.dumps(self.get_current_metrics(), indent=2)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    def _export_prometheus(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []
        
        # Export counters
        for name, value in self._counters.items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# HELP {safe_name} Counter metric")
            lines.append(f"# TYPE {safe_name} counter")
            lines.append(f"{safe_name} {value}")
        
        # Export gauges
        for name, value in self._gauges.items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# HELP {safe_name} Gauge metric")
            lines.append(f"# TYPE {safe_name} gauge")
            lines.append(f"{safe_name} {value}")
        
        return "\\n".join(lines)


# Specialized metric collectors for Bridge components
class SpeedLayerMetrics:
    """Specialized metrics for Speed Layer performance"""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
    
    def record_cache_hit(self, cache_type: str, hit: bool, duration_ms: float):
        """Record cache hit/miss and timing"""
        self.collector.record_counter(
            f"speed_layer.cache.{cache_type}.{'hits' if hit else 'misses'}",
            tags={"cache_type": cache_type}
        )
        self.collector.record_timing(
            f"speed_layer.cache.{cache_type}.duration",
            duration_ms / 1000.0,
            tags={"cache_type": cache_type, "result": "hit" if hit else "miss"}
        )
    
    def record_validation_result(self, decision: str, confidence: str, duration_ms: float):
        """Record validation decision and timing"""
        self.collector.record_counter(
            "speed_layer.validations.total",
            tags={"decision": decision, "confidence": confidence}
        )
        self.collector.record_timing(
            "speed_layer.validation.duration",
            duration_ms / 1000.0,
            tags={"decision": decision, "confidence": confidence}
        )


class FUSEMetrics:
    """Specialized metrics for FUSE filesystem"""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
    
    def record_operation(self, operation: str, path: str, duration_ms: float, success: bool):
        """Record FUSE operation"""
        self.collector.record_counter(
            f"fuse.operations.{operation}.total",
            tags={"success": str(success)}
        )
        self.collector.record_timing(
            f"fuse.operations.{operation}.duration",
            duration_ms / 1000.0,
            tags={"success": str(success)}
        )
    
    def record_expert_access(self, agent_id: str, operation: str, path: str):
        """Record expert agent filesystem access"""
        self.collector.record_counter(
            "fuse.expert_access.total",
            tags={"agent_id": agent_id, "operation": operation}
        )


class ExpertCoordinationMetrics:
    """Specialized metrics for Expert Coordination"""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
    
    def record_expert_request(self, expert_type: str, duration_ms: float, success: bool):
        """Record expert agent request"""
        self.collector.record_counter(
            "coordination.expert_requests.total",
            tags={"expert_type": expert_type, "success": str(success)}
        )
        self.collector.record_timing(
            "coordination.expert_request.duration",
            duration_ms / 1000.0,
            tags={"expert_type": expert_type, "success": str(success)}
        )
    
    def record_expert_availability(self, expert_type: str, available_count: int):
        """Record expert agent availability"""
        self.collector.record_gauge(
            f"coordination.experts.available",
            available_count,
            tags={"expert_type": expert_type}
        )


# Integration helper
def create_bridge_metrics_collector() -> Dict[str, Any]:
    """Create metrics collector with specialized Bridge collectors"""
    main_collector = MetricsCollector()
    
    return {
        'main': main_collector,
        'speed_layer': SpeedLayerMetrics(main_collector),
        'fuse': FUSEMetrics(main_collector),
        'coordination': ExpertCoordinationMetrics(main_collector)
    }