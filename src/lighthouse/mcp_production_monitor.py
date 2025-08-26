#!/usr/bin/env python3
"""
MCP Production Monitoring and Hardening

Provides comprehensive production monitoring, error handling, and 
operational excellence patterns for the Lighthouse MCP server.

Features:
- Health monitoring and alerting
- Circuit breaker patterns
- Graceful degradation
- Performance monitoring
- Error tracking and recovery
"""

import asyncio
import logging
import time
import json
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """System health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DOWN = "down"


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """Individual health check definition"""
    name: str
    check_function: Callable
    timeout: float = 5.0
    critical: bool = True
    enabled: bool = True
    last_run: Optional[float] = None
    last_result: Optional[bool] = None
    last_error: Optional[str] = None


@dataclass
class Alert:
    """System alert"""
    level: AlertLevel
    component: str
    message: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerState:
    """Circuit breaker state tracking"""
    failure_count: int = 0
    last_failure: Optional[float] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    next_attempt: Optional[float] = None


class CircuitBreaker:
    """
    Circuit Breaker Pattern Implementation
    
    Provides fault tolerance and graceful degradation for external dependencies.
    """
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 timeout: float = 10.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.timeout = timeout
        self.state = CircuitBreakerState()
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        
        async with self._lock:
            if self.state.state == "OPEN":
                if time.time() < self.state.next_attempt:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
                else:
                    self.state.state = "HALF_OPEN"
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
            
            # Success - reset circuit breaker
            async with self._lock:
                self.state.failure_count = 0
                self.state.state = "CLOSED"
                self.state.last_failure = None
                self.state.next_attempt = None
            
            return result
            
        except Exception as e:
            # Failure - update circuit breaker
            async with self._lock:
                self.state.failure_count += 1
                self.state.last_failure = time.time()
                
                if self.state.failure_count >= self.failure_threshold:
                    self.state.state = "OPEN"
                    self.state.next_attempt = time.time() + self.recovery_timeout
                elif self.state.state == "HALF_OPEN":
                    self.state.state = "OPEN"
                    self.state.next_attempt = time.time() + self.recovery_timeout
            
            raise e
    
    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state"""
        return {
            "state": self.state.state,
            "failure_count": self.state.failure_count,
            "last_failure": self.state.last_failure,
            "next_attempt": self.state.next_attempt
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class ProductionMonitor:
    """
    Production Monitoring and Hardening System
    
    Provides comprehensive monitoring, alerting, and operational 
    capabilities for production MCP deployment.
    """
    
    def __init__(self):
        # Health monitoring
        self.health_checks: Dict[str, HealthCheck] = {}
        self.overall_health = HealthStatus.HEALTHY
        self.last_health_check = 0.0
        
        # Alerting
        self.alerts: deque = deque(maxlen=1000)
        self.alert_handlers: List[Callable] = []
        
        # Circuit breakers for external dependencies
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Performance monitoring
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.performance_thresholds = {
            "response_time_ms": 100,
            "error_rate_percent": 1.0,
            "memory_usage_mb": 100
        }
        
        # Error tracking
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.recent_errors: deque = deque(maxlen=100)
        
        # Configuration
        self.monitoring_enabled = True
        self.health_check_interval = 30.0
        self.alert_cooldown = 300.0  # 5 minutes
        self.last_alerts: Dict[str, float] = {}
    
    def register_health_check(self, 
                            name: str, 
                            check_function: Callable,
                            timeout: float = 5.0,
                            critical: bool = True) -> None:
        """Register a health check"""
        
        self.health_checks[name] = HealthCheck(
            name=name,
            check_function=check_function,
            timeout=timeout,
            critical=critical
        )
        
        logger.info(f"Registered health check: {name}")
    
    def register_circuit_breaker(self, 
                               name: str,
                               failure_threshold: int = 5,
                               recovery_timeout: float = 60.0) -> CircuitBreaker:
        """Register and return a circuit breaker"""
        
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )
        
        self.circuit_breakers[name] = breaker
        logger.info(f"Registered circuit breaker: {name}")
        
        return breaker
    
    async def run_health_checks(self) -> HealthStatus:
        """Run all health checks and determine overall health"""
        
        if not self.monitoring_enabled:
            return HealthStatus.HEALTHY
        
        healthy_checks = 0
        critical_failures = 0
        total_checks = len([hc for hc in self.health_checks.values() if hc.enabled])
        
        if total_checks == 0:
            return HealthStatus.HEALTHY
        
        for health_check in self.health_checks.values():
            if not health_check.enabled:
                continue
            
            try:
                # Run health check with timeout
                result = await asyncio.wait_for(
                    health_check.check_function(),
                    timeout=health_check.timeout
                )
                
                health_check.last_run = time.time()
                health_check.last_result = result
                health_check.last_error = None
                
                if result:
                    healthy_checks += 1
                elif health_check.critical:
                    critical_failures += 1
                    
            except Exception as e:
                health_check.last_run = time.time()
                health_check.last_result = False
                health_check.last_error = str(e)
                
                if health_check.critical:
                    critical_failures += 1
                
                logger.error(f"Health check {health_check.name} failed: {e}")
        
        # Determine overall health
        if critical_failures > 0:
            self.overall_health = HealthStatus.CRITICAL
        elif healthy_checks / total_checks < 0.5:
            self.overall_health = HealthStatus.DEGRADED
        elif healthy_checks / total_checks < 0.8:
            self.overall_health = HealthStatus.DEGRADED
        else:
            self.overall_health = HealthStatus.HEALTHY
        
        self.last_health_check = time.time()
        return self.overall_health
    
    async def emit_alert(self, 
                        level: AlertLevel, 
                        component: str, 
                        message: str,
                        context: Dict[str, Any] = None) -> None:
        """Emit an alert with cooldown management"""
        
        alert_key = f"{component}:{message}"
        now = time.time()
        
        # Check cooldown
        if alert_key in self.last_alerts:
            if now - self.last_alerts[alert_key] < self.alert_cooldown:
                return  # Skip duplicate alert within cooldown
        
        # Create alert
        alert = Alert(
            level=level,
            component=component,
            message=message,
            context=context or {}
        )
        
        self.alerts.append(alert)
        self.last_alerts[alert_key] = now
        
        # Notify alert handlers
        for handler in self.alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")
        
        logger.warning(f"Alert [{level.value.upper()}] {component}: {message}")
    
    def record_metric(self, name: str, value: float) -> None:
        """Record a performance metric"""
        self.metrics[name].append((time.time(), value))
        
        # Check thresholds and emit alerts
        if name in self.performance_thresholds:
            threshold = self.performance_thresholds[name]
            if value > threshold:
                asyncio.create_task(self.emit_alert(
                    AlertLevel.WARNING,
                    "performance",
                    f"{name} exceeded threshold: {value} > {threshold}"
                ))
    
    def record_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """Record an error for tracking"""
        error_type = type(error).__name__
        self.error_counts[error_type] += 1
        
        error_info = {
            "type": error_type,
            "message": str(error),
            "timestamp": time.time(),
            "context": context or {}
        }
        
        self.recent_errors.append(error_info)
        
        # Emit alert for high error rates
        total_errors = sum(self.error_counts.values())
        if total_errors > 0 and total_errors % 10 == 0:  # Every 10 errors
            asyncio.create_task(self.emit_alert(
                AlertLevel.ERROR,
                "error_tracking", 
                f"High error rate: {total_errors} total errors"
            ))
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report"""
        
        health_checks_status = {}
        for name, hc in self.health_checks.items():
            health_checks_status[name] = {
                "enabled": hc.enabled,
                "critical": hc.critical,
                "last_run": hc.last_run,
                "last_result": hc.last_result,
                "last_error": hc.last_error
            }
        
        circuit_breaker_status = {}
        for name, cb in self.circuit_breakers.items():
            circuit_breaker_status[name] = cb.get_state()
        
        recent_alerts = [
            {
                "level": alert.level.value,
                "component": alert.component,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "resolved": alert.resolved
            }
            for alert in list(self.alerts)[-10:]  # Last 10 alerts
        ]
        
        return {
            "overall_health": self.overall_health.value,
            "last_health_check": self.last_health_check,
            "health_checks": health_checks_status,
            "circuit_breakers": circuit_breaker_status,
            "recent_alerts": recent_alerts,
            "error_counts": dict(self.error_counts),
            "monitoring_enabled": self.monitoring_enabled
        }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary"""
        
        summary = {}
        for name, metric_data in self.metrics.items():
            if not metric_data:
                continue
            
            values = [value for _, value in metric_data]
            summary[name] = {
                "current": values[-1] if values else 0,
                "average": sum(values) / len(values) if values else 0,
                "max": max(values) if values else 0,
                "min": min(values) if values else 0,
                "count": len(values)
            }
        
        return summary
    
    async def start_monitoring(self) -> None:
        """Start background monitoring tasks"""
        
        if not self.monitoring_enabled:
            return
        
        async def health_check_loop():
            """Background health check loop"""
            while self.monitoring_enabled:
                try:
                    await self.run_health_checks()
                    await asyncio.sleep(self.health_check_interval)
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")
                    await asyncio.sleep(10)  # Brief pause on error
        
        # Start monitoring task
        asyncio.create_task(health_check_loop())
        logger.info("Production monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring"""
        self.monitoring_enabled = False
        logger.info("Production monitoring stopped")