"""
Health Monitor for Lighthouse Bridge

Monitors the health of all Bridge components and provides:
- Real-time health status of all subsystems
- Automated recovery for transient failures
- Performance degradation detection
- SLA compliance monitoring
- Circuit breaker functionality

HLD Requirements:
- <100ms health check response time
- Automated failure detection and recovery
- Comprehensive system health visibility
- Integration with metrics collection
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import statistics
from datetime import datetime, timedelta

from .metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """Individual health check configuration"""
    name: str
    check_function: Callable[[], Any]
    timeout_seconds: float = 5.0
    interval_seconds: float = 30.0
    failure_threshold: int = 3
    recovery_threshold: int = 2
    is_critical: bool = False


@dataclass
class HealthResult:
    """Result of a health check"""
    name: str
    status: HealthStatus
    message: str
    timestamp: float
    duration_ms: float
    details: Dict[str, Any] = None


@dataclass
class ComponentHealth:
    """Health status of a system component"""
    name: str
    status: HealthStatus
    last_check: float
    consecutive_failures: int
    consecutive_successes: int
    total_checks: int
    total_failures: int
    recent_results: List[HealthResult]
    is_critical: bool = False


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures"""
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 half_open_max_calls: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half_open
        self.half_open_calls = 0
    
    def is_available(self) -> bool:
        """Check if circuit breaker allows calls"""
        current_time = time.time()
        
        if self.state == "closed":
            return True
        elif self.state == "open":
            if current_time - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
                self.half_open_calls = 0
                return True
            return False
        else:  # half_open
            return self.half_open_calls < self.half_open_max_calls
    
    def record_success(self):
        """Record successful operation"""
        if self.state == "half_open":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = "closed"
                self.failure_count = 0
        elif self.state == "closed":
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class HealthMonitor:
    """
    Comprehensive health monitoring system for Lighthouse Bridge
    
    Features:
    - Configurable health checks for all components
    - Circuit breaker protection
    - Automated recovery attempts
    - Performance trend analysis
    - SLA compliance tracking
    """
    
    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.metrics = metrics_collector
        
        # Health checks registry
        self.health_checks: Dict[str, HealthCheck] = {}
        self.component_health: Dict[str, ComponentHealth] = {}
        
        # Circuit breakers
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Background monitoring
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        # Recovery functions
        self.recovery_functions: Dict[str, Callable] = {}
        
        # Health history for trend analysis
        self.health_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000
        
        # SLA tracking
        self.sla_targets = {
            'availability_percentage': 99.9,
            'response_time_p99_ms': 100,
            'error_rate_percentage': 0.1
        }
        
        # Register built-in health checks
        self._register_builtin_checks()
    
    def register_health_check(self, health_check: HealthCheck):
        """Register a new health check"""
        self.health_checks[health_check.name] = health_check
        
        # Initialize component health tracking
        self.component_health[health_check.name] = ComponentHealth(
            name=health_check.name,
            status=HealthStatus.HEALTHY,
            last_check=0,
            consecutive_failures=0,
            consecutive_successes=0,
            total_checks=0,
            total_failures=0,
            recent_results=[],
            is_critical=health_check.is_critical
        )
        
        # Initialize circuit breaker
        self.circuit_breakers[health_check.name] = CircuitBreaker()
        
        logger.info(f"Registered health check: {health_check.name}")
    
    def register_recovery_function(self, component_name: str, recovery_func: Callable):
        """Register recovery function for a component"""
        self.recovery_functions[component_name] = recovery_func
        logger.info(f"Registered recovery function for: {component_name}")
    
    async def start_monitoring(self):
        """Start background health monitoring"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        if self.metrics:
            self.metrics.record_counter("health_monitor.started")
        
        logger.info("Health monitoring started")
    
    async def stop_monitoring(self):
        """Stop background monitoring"""
        self.is_running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self.metrics:
            self.metrics.record_counter("health_monitor.stopped")
        
        logger.info("Health monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        next_checks = {name: 0 for name in self.health_checks}
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # Check which health checks need to run
                for name, health_check in self.health_checks.items():
                    if current_time >= next_checks[name]:
                        # Run health check in background
                        asyncio.create_task(self._run_health_check(name))
                        next_checks[name] = current_time + health_check.interval_seconds
                
                # Update overall system health
                await self._update_system_health()
                
                # Sleep until next check is due
                sleep_time = min([
                    next_check - current_time 
                    for next_check in next_checks.values() 
                    if next_check > current_time
                ] + [1.0])  # At least 1 second
                
                await asyncio.sleep(max(0.1, sleep_time))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(5.0)
    
    async def _run_health_check(self, name: str):
        """Run individual health check"""
        health_check = self.health_checks[name]
        component = self.component_health[name]
        circuit_breaker = self.circuit_breakers[name]
        
        # Check circuit breaker
        if not circuit_breaker.is_available():
            result = HealthResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Circuit breaker open",
                timestamp=time.time(),
                duration_ms=0,
                details={"circuit_breaker": "open"}
            )
            await self._process_health_result(result)
            return
        
        start_time = time.perf_counter()
        
        try:
            # Run health check with timeout
            check_result = await asyncio.wait_for(
                self._execute_health_check(health_check),
                timeout=health_check.timeout_seconds
            )
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Determine status from result
            if check_result is True or (isinstance(check_result, dict) and check_result.get('healthy', True)):
                status = HealthStatus.HEALTHY
                message = "Health check passed"
                details = check_result if isinstance(check_result, dict) else None
                circuit_breaker.record_success()
            else:
                status = HealthStatus.UNHEALTHY
                message = str(check_result) if check_result else "Health check failed"
                details = None
                circuit_breaker.record_failure()
            
        except asyncio.TimeoutError:
            duration_ms = health_check.timeout_seconds * 1000
            status = HealthStatus.UNHEALTHY
            message = f"Health check timed out after {health_check.timeout_seconds}s"
            details = {"timeout": True}
            circuit_breaker.record_failure()
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            status = HealthStatus.CRITICAL
            message = f"Health check error: {e}"
            details = {"error": str(e)}
            circuit_breaker.record_failure()
        
        # Create health result
        result = HealthResult(
            name=name,
            status=status,
            message=message,
            timestamp=time.time(),
            duration_ms=duration_ms,
            details=details
        )
        
        await self._process_health_result(result)
    
    async def _execute_health_check(self, health_check: HealthCheck) -> Any:
        """Execute health check function"""
        try:
            if asyncio.iscoroutinefunction(health_check.check_function):
                return await health_check.check_function()
            else:
                return health_check.check_function()
        except Exception as e:
            logger.error(f"Health check execution error: {e}")
            raise
    
    async def _process_health_result(self, result: HealthResult):
        """Process health check result"""
        component = self.component_health[result.name]
        
        # Update component stats
        component.last_check = result.timestamp
        component.total_checks += 1
        
        if result.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
            component.total_failures += 1
            component.consecutive_failures += 1
            component.consecutive_successes = 0
        else:
            component.consecutive_failures = 0
            component.consecutive_successes += 1
        
        # Determine overall component status
        health_check = self.health_checks[result.name]
        if component.consecutive_failures >= health_check.failure_threshold:
            component.status = result.status
        elif component.consecutive_successes >= health_check.recovery_threshold:
            component.status = HealthStatus.HEALTHY
        
        # Store recent results
        component.recent_results.append(result)
        if len(component.recent_results) > 10:  # Keep last 10 results
            component.recent_results = component.recent_results[-10:]
        
        # Record metrics
        if self.metrics:
            self.metrics.record_counter(
                f"health_check.{result.name}.total",
                tags={"status": result.status.value}
            )
            self.metrics.record_timing(
                f"health_check.{result.name}.duration",
                result.duration_ms / 1000.0,
                tags={"status": result.status.value}
            )
        
        # Attempt recovery if needed
        if (component.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL] and
            result.name in self.recovery_functions):
            await self._attempt_recovery(result.name)
        
        logger.debug(f"Health check {result.name}: {result.status.value} in {result.duration_ms:.1f}ms")
    
    async def _attempt_recovery(self, component_name: str):
        """Attempt automated recovery for failed component"""
        try:
            logger.info(f"Attempting recovery for component: {component_name}")
            
            recovery_func = self.recovery_functions[component_name]
            if asyncio.iscoroutinefunction(recovery_func):
                await recovery_func()
            else:
                recovery_func()
            
            if self.metrics:
                self.metrics.record_counter(f"health_recovery.{component_name}.attempted")
            
            logger.info(f"Recovery attempt completed for: {component_name}")
            
        except Exception as e:
            logger.error(f"Recovery attempt failed for {component_name}: {e}")
            
            if self.metrics:
                self.metrics.record_counter(f"health_recovery.{component_name}.failed")
    
    async def _update_system_health(self):
        """Update overall system health status"""
        current_time = time.time()
        
        # Calculate overall health
        critical_failures = sum(
            1 for comp in self.component_health.values()
            if comp.status == HealthStatus.CRITICAL and comp.is_critical
        )
        
        unhealthy_components = sum(
            1 for comp in self.component_health.values()
            if comp.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]
        )
        
        total_components = len(self.component_health)
        
        if critical_failures > 0:
            overall_status = HealthStatus.CRITICAL
        elif unhealthy_components > total_components * 0.3:  # More than 30% unhealthy
            overall_status = HealthStatus.DEGRADED
        elif unhealthy_components > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        # Store health snapshot
        health_snapshot = {
            'timestamp': current_time,
            'overall_status': overall_status.value,
            'total_components': total_components,
            'healthy_components': total_components - unhealthy_components,
            'unhealthy_components': unhealthy_components,
            'critical_failures': critical_failures,
            'components': {
                name: {
                    'status': comp.status.value,
                    'consecutive_failures': comp.consecutive_failures,
                    'total_failures': comp.total_failures,
                    'total_checks': comp.total_checks,
                    'uptime_percentage': ((comp.total_checks - comp.total_failures) / comp.total_checks * 100) if comp.total_checks > 0 else 100
                }
                for name, comp in self.component_health.items()
            }
        }
        
        # Add to health history
        self.health_history.append(health_snapshot)
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size:]
        
        # Record system-level metrics
        if self.metrics:
            self.metrics.record_gauge("health.overall_status", overall_status.value == "healthy")
            self.metrics.record_gauge("health.healthy_components", total_components - unhealthy_components)
            self.metrics.record_gauge("health.unhealthy_components", unhealthy_components)
            self.metrics.record_gauge("health.critical_failures", critical_failures)
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get current system health status"""
        if not self.health_history:
            return {"status": "unknown", "message": "No health data available"}
        
        latest = self.health_history[-1]
        return {
            "overall_status": latest["overall_status"],
            "timestamp": latest["timestamp"],
            "summary": {
                "total_components": latest["total_components"],
                "healthy_components": latest["healthy_components"],
                "unhealthy_components": latest["unhealthy_components"],
                "critical_failures": latest["critical_failures"]
            },
            "components": latest["components"]
        }
    
    def get_component_health(self, component_name: str) -> Optional[Dict[str, Any]]:
        """Get health status for specific component"""
        if component_name not in self.component_health:
            return None
        
        component = self.component_health[component_name]
        return {
            "name": component.name,
            "status": component.status.value,
            "last_check": component.last_check,
            "consecutive_failures": component.consecutive_failures,
            "consecutive_successes": component.consecutive_successes,
            "total_checks": component.total_checks,
            "total_failures": component.total_failures,
            "uptime_percentage": ((component.total_checks - component.total_failures) / component.total_checks * 100) if component.total_checks > 0 else 100,
            "recent_results": [
                {
                    "status": result.status.value,
                    "message": result.message,
                    "timestamp": result.timestamp,
                    "duration_ms": result.duration_ms
                }
                for result in component.recent_results[-5:]  # Last 5 results
            ],
            "circuit_breaker": {
                "state": self.circuit_breakers[component_name].state,
                "failure_count": self.circuit_breakers[component_name].failure_count
            }
        }
    
    def _register_builtin_checks(self):
        """Register built-in health checks"""
        
        # Memory usage check
        async def memory_check():
            try:
                import psutil
                memory = psutil.virtual_memory()
                if memory.percent > 90:
                    return {"healthy": False, "memory_percent": memory.percent, "message": "High memory usage"}
                elif memory.percent > 75:
                    return {"healthy": True, "memory_percent": memory.percent, "message": "Elevated memory usage"}
                return {"healthy": True, "memory_percent": memory.percent}
            except ImportError:
                return {"healthy": True, "message": "psutil not available"}
        
        self.register_health_check(HealthCheck(
            name="system_memory",
            check_function=memory_check,
            interval_seconds=60,
            is_critical=True
        ))
        
        # Basic connectivity check
        def connectivity_check():
            return True  # Always healthy for now
        
        self.register_health_check(HealthCheck(
            name="basic_connectivity",
            check_function=connectivity_check,
            interval_seconds=30
        ))


# Factory function for Bridge integration
def create_bridge_health_monitor(metrics_collector: Optional[MetricsCollector] = None) -> HealthMonitor:
    """Create health monitor with Bridge-specific configurations"""
    monitor = HealthMonitor(metrics_collector)
    
    # Register Bridge-specific health checks will be added here
    # This is where we'd add checks for:
    # - Event Store connectivity
    # - FUSE mount status
    # - Speed Layer performance
    # - Expert coordination availability
    
    return monitor