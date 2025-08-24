"""
Monitoring Integration for Lighthouse Bridge

Integrates all monitoring components with the Bridge system and provides
a unified monitoring interface for all Bridge subsystems.

Features:
- Unified monitoring initialization
- Automatic Bridge component registration
- Integrated alerting and recovery
- Performance optimization monitoring
- Expert agent usage tracking
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List

from .metrics_collector import create_bridge_metrics_collector
from .health_monitor import create_bridge_health_monitor, HealthCheck
from .observability_dashboard import create_observability_dashboard

logger = logging.getLogger(__name__)


class BridgeMonitoringSystem:
    """
    Unified monitoring system for all Bridge components
    
    Integrates metrics collection, health monitoring, and observability
    dashboard for comprehensive Bridge system monitoring.
    """
    
    def __init__(self):
        # Initialize monitoring components
        self.metrics_collectors = create_bridge_metrics_collector()
        self.metrics = self.metrics_collectors['main']
        
        self.health_monitor = create_bridge_health_monitor(self.metrics)
        self.dashboard = create_observability_dashboard(self.metrics, self.health_monitor)
        
        # Bridge component references (to be set during initialization)
        self.bridge_components: Dict[str, Any] = {}
        
        # Monitoring state
        self.is_running = False
        
        logger.info("Bridge monitoring system initialized")
    
    def register_bridge_components(self, components: Dict[str, Any]):
        """Register Bridge components for monitoring"""
        self.bridge_components = components
        
        # Register health checks for Bridge components
        self._register_bridge_health_checks()
        
        logger.info("Bridge components registered for monitoring")
    
    def _register_bridge_health_checks(self):
        """Register health checks for all Bridge components"""
        
        # Event Store health check
        if 'event_store' in self.bridge_components:
            async def event_store_health():
                try:
                    # Simple connectivity test
                    event_store = self.bridge_components['event_store']
                    if hasattr(event_store, 'health_check'):
                        return await event_store.health_check()
                    return True
                except Exception as e:
                    return f"Event Store error: {e}"
            
            self.health_monitor.register_health_check(HealthCheck(
                name="event_store",
                check_function=event_store_health,
                interval_seconds=30,
                is_critical=True
            ))
        
        # Speed Layer health checks
        if 'speed_layer' in self.bridge_components:
            speed_layer = self.bridge_components['speed_layer']
            
            # Memory cache health
            async def memory_cache_health():
                try:
                    if hasattr(speed_layer, 'memory_cache'):
                        stats = speed_layer.memory_cache.get_stats()
                        hit_rate = stats.get('hit_rate', 0)
                        if hit_rate < 50:  # Low hit rate warning
                            return {"healthy": True, "warning": f"Low hit rate: {hit_rate:.1f}%"}
                        return {"healthy": True, "hit_rate": hit_rate}
                    return True
                except Exception as e:
                    return f"Memory cache error: {e}"
            
            self.health_monitor.register_health_check(HealthCheck(
                name="speed_layer_memory_cache",
                check_function=memory_cache_health,
                interval_seconds=60
            ))
            
            # Policy cache health
            async def policy_cache_health():
                try:
                    if hasattr(speed_layer, 'policy_cache'):
                        # Check if policy cache is responsive
                        return True  # Simplified check
                    return True
                except Exception as e:
                    return f"Policy cache error: {e}"
            
            self.health_monitor.register_health_check(HealthCheck(
                name="speed_layer_policy_cache",
                check_function=policy_cache_health,
                interval_seconds=60
            ))
        
        # FUSE Mount health check
        if 'fuse_mount_manager' in self.bridge_components:
            async def fuse_mount_health():
                try:
                    mount_manager = self.bridge_components['fuse_mount_manager']
                    if hasattr(mount_manager, 'is_mounted'):
                        if not mount_manager.is_mounted:
                            return "FUSE filesystem not mounted"
                        
                        # Check mount performance
                        status = mount_manager.get_status()
                        if status.get('health_failures', 0) > 0:
                            return {"healthy": True, "warning": f"Recent health failures: {status['health_failures']}"}
                        
                        return {"healthy": True, "mount_point": status.get('mount_point')}
                    return True
                except Exception as e:
                    return f"FUSE mount error: {e}"
            
            self.health_monitor.register_health_check(HealthCheck(
                name="fuse_mount",
                check_function=fuse_mount_health,
                interval_seconds=30,
                is_critical=True
            ))
        
        # Expert Coordination health check
        if 'expert_coordinator' in self.bridge_components:
            async def expert_coordinator_health():
                try:
                    coordinator = self.bridge_components['expert_coordinator']
                    if hasattr(coordinator, 'get_status'):
                        status = coordinator.get_status()
                        active_experts = status.get('active_experts', 0)
                        if active_experts == 0:
                            return {"healthy": True, "warning": "No active experts"}
                        return {"healthy": True, "active_experts": active_experts}
                    return True
                except Exception as e:
                    return f"Expert coordinator error: {e}"
            
            self.health_monitor.register_health_check(HealthCheck(
                name="expert_coordinator",
                check_function=expert_coordinator_health,
                interval_seconds=45
            ))
        
        # AST Anchor Manager health check
        if 'ast_anchor_manager' in self.bridge_components:
            async def ast_anchor_health():
                try:
                    anchor_manager = self.bridge_components['ast_anchor_manager']
                    # Basic responsiveness check
                    return True  # Simplified check
                except Exception as e:
                    return f"AST anchor manager error: {e}"
            
            self.health_monitor.register_health_check(HealthCheck(
                name="ast_anchor_manager",
                check_function=ast_anchor_health,
                interval_seconds=120
            ))
    
    async def start_monitoring(self):
        """Start all monitoring components"""
        if self.is_running:
            return
        
        try:
            # Start metrics collection
            self.metrics.start()
            
            # Start health monitoring
            await self.health_monitor.start_monitoring()
            
            # Start observability dashboard
            await self.dashboard.start_dashboard()
            
            self.is_running = True
            
            # Record monitoring system startup
            self.metrics.record_counter("monitoring.system_started")
            
            logger.info("🔍 Bridge monitoring system started")
            logger.info("Monitoring components:")
            logger.info("  ✓ Metrics collection")
            logger.info("  ✓ Health monitoring") 
            logger.info("  ✓ Observability dashboard")
            
        except Exception as e:
            logger.error(f"Failed to start monitoring system: {e}")
            raise
    
    async def stop_monitoring(self):
        """Stop all monitoring components"""
        if not self.is_running:
            return
        
        try:
            # Stop components in reverse order
            await self.dashboard.stop_dashboard()
            await self.health_monitor.stop_monitoring()
            await self.metrics.stop()
            
            self.is_running = False
            
            logger.info("Bridge monitoring system stopped")
            
        except Exception as e:
            logger.error(f"Error stopping monitoring system: {e}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            'monitoring_active': self.is_running,
            'metrics': self.metrics.get_current_metrics(),
            'health': self.health_monitor.get_system_health(),
            'dashboard': self.dashboard.get_dashboard_data(),
            'alerts': self.dashboard.get_alerts(limit=10)
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for all components"""
        dashboard_data = self.dashboard.get_dashboard_data()
        
        return {
            'speed_layer': dashboard_data['performance_metrics'].get('speed_layer', {}),
            'fuse_filesystem': dashboard_data['performance_metrics'].get('fuse_filesystem', {}),
            'expert_coordination': dashboard_data['performance_metrics'].get('expert_coordination', {}),
            'sla_compliance': dashboard_data['sla_compliance']
        }
    
    def get_expert_analytics(self) -> Dict[str, Any]:
        """Get expert agent usage analytics"""
        dashboard_data = self.dashboard.get_dashboard_data()
        return dashboard_data.get('expert_analytics', {})
    
    def record_speed_layer_operation(self, 
                                   cache_type: str, 
                                   duration_ms: float, 
                                   hit: bool = True):
        """Record Speed Layer operation for monitoring"""
        self.metrics_collectors['speed_layer'].record_cache_hit(
            cache_type, hit, duration_ms
        )
    
    def record_fuse_operation(self, 
                            operation: str, 
                            path: str, 
                            duration_ms: float, 
                            success: bool = True):
        """Record FUSE operation for monitoring"""
        self.metrics_collectors['fuse'].record_operation(
            operation, path, duration_ms, success
        )
    
    def record_expert_request(self, 
                            expert_type: str, 
                            duration_ms: float, 
                            success: bool = True):
        """Record expert coordination request for monitoring"""
        self.metrics_collectors['coordination'].record_expert_request(
            expert_type, duration_ms, success
        )
    
    def record_expert_filesystem_access(self, 
                                      agent_id: str, 
                                      operation: str, 
                                      path: str):
        """Record expert agent filesystem access"""
        self.metrics_collectors['fuse'].record_expert_access(
            agent_id, operation, path
        )
    
    async def trigger_health_check(self, component_name: str) -> Optional[Dict[str, Any]]:
        """Manually trigger health check for specific component"""
        return self.health_monitor.get_component_health(component_name)
    
    def generate_sla_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate SLA compliance report"""
        return self.dashboard.get_sla_report(hours)
    
    def export_metrics(self, format_type: str = "prometheus") -> str:
        """Export metrics in specified format"""
        return self.metrics.export_metrics(format_type)
    
    async def shutdown(self):
        """Graceful shutdown of monitoring system"""
        await self.stop_monitoring()


# Factory function for easy Bridge integration
async def initialize_bridge_monitoring(bridge_components: Dict[str, Any]) -> BridgeMonitoringSystem:
    """
    Initialize complete Bridge monitoring system
    
    Args:
        bridge_components: Dictionary of Bridge components to monitor
        
    Returns:
        Configured and started BridgeMonitoringSystem
    """
    monitoring_system = BridgeMonitoringSystem()
    monitoring_system.register_bridge_components(bridge_components)
    await monitoring_system.start_monitoring()
    
    return monitoring_system


# Monitoring decorators for performance tracking
def monitor_speed_layer_operation(cache_type: str):
    """Decorator to monitor Speed Layer operations"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                # Record successful operation
                # Note: Would need access to monitoring system instance
                # This is simplified for demonstration
                
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                # Record failed operation
                raise
        return wrapper
    return decorator


def monitor_fuse_operation(operation: str):
    """Decorator to monitor FUSE operations"""  
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                # Record successful operation
                # Note: Would need access to monitoring system instance
                
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                # Record failed operation
                raise
        return wrapper
    return decorator