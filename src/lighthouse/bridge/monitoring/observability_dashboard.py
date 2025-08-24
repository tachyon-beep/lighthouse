"""
Observability Dashboard for Lighthouse Bridge

Provides comprehensive visibility into Bridge operations including:
- Real-time metrics visualization
- Health status monitoring
- Performance trend analysis
- Expert agent coordination tracking
- SLA compliance reporting

HLD Requirements:
- Real-time dashboard updates
- Historical trend analysis
- Expert agent usage analytics
- Performance bottleneck identification
- Alert management interface
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time

from .metrics_collector import MetricsCollector
from .health_monitor import HealthMonitor, HealthStatus

logger = logging.getLogger(__name__)


class ObservabilityDashboard:
    """
    Comprehensive observability dashboard for Lighthouse Bridge
    
    Provides unified view of:
    - System health and performance
    - Expert agent coordination
    - FUSE filesystem usage
    - Speed Layer efficiency
    - Event sourcing throughput
    """
    
    def __init__(self, 
                 metrics_collector: MetricsCollector,
                 health_monitor: HealthMonitor):
        self.metrics = metrics_collector
        self.health = health_monitor
        
        # Dashboard state
        self.is_running = False
        self.update_task: Optional[asyncio.Task] = None
        self.update_interval = 5.0  # seconds
        
        # Dashboard data
        self.dashboard_data: Dict[str, Any] = {}
        self.alerts: List[Dict[str, Any]] = []
        self.max_alerts = 100
        
        # Performance thresholds for alerting
        self.performance_thresholds = {
            'speed_layer_p99_ms': 100,
            'fuse_operation_p95_ms': 10,
            'expert_response_p99_ms': 30000,  # 30 seconds
            'cache_hit_rate_percent': 95,
            'error_rate_percent': 1.0
        }
        
        # Initialize dashboard
        self._initialize_dashboard()
    
    def _initialize_dashboard(self):
        """Initialize dashboard with default structure"""
        self.dashboard_data = {
            'timestamp': time.time(),
            'system_overview': {
                'status': 'unknown',
                'uptime_hours': 0,
                'total_requests': 0,
                'active_experts': 0
            },
            'performance_metrics': {
                'speed_layer': {},
                'fuse_filesystem': {},
                'expert_coordination': {},
                'event_sourcing': {}
            },
            'health_status': {
                'overall_status': 'unknown',
                'component_health': {}
            },
            'expert_analytics': {
                'active_agents': [],
                'request_distribution': {},
                'success_rates': {},
                'average_response_times': {}
            },
            'sla_compliance': {
                'availability_percent': 0,
                'performance_compliance': {},
                'error_rates': {}
            },
            'recent_alerts': [],
            'trends': {
                'request_rate': [],
                'response_times': [],
                'error_rates': [],
                'expert_utilization': []
            }
        }
    
    async def start_dashboard(self):
        """Start dashboard data collection"""
        if self.is_running:
            return
        
        self.is_running = True
        self.update_task = asyncio.create_task(self._update_loop())
        
        logger.info("Observability dashboard started")
    
    async def stop_dashboard(self):
        """Stop dashboard updates"""
        self.is_running = False
        
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Observability dashboard stopped")
    
    async def _update_loop(self):
        """Main dashboard update loop"""
        while self.is_running:
            try:
                await self._update_dashboard_data()
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dashboard update error: {e}")
                await asyncio.sleep(self.update_interval)
    
    async def _update_dashboard_data(self):
        """Update all dashboard data"""
        current_time = time.time()
        self.dashboard_data['timestamp'] = current_time
        
        # Update system overview
        await self._update_system_overview()
        
        # Update performance metrics
        await self._update_performance_metrics()
        
        # Update health status
        await self._update_health_status()
        
        # Update expert analytics
        await self._update_expert_analytics()
        
        # Update SLA compliance
        await self._update_sla_compliance()
        
        # Update trends
        await self._update_trends()
        
        # Check for alerts
        await self._check_alerts()
    
    async def _update_system_overview(self):
        """Update system overview metrics"""
        current_metrics = self.metrics.get_current_metrics()
        
        overview = self.dashboard_data['system_overview']
        overview.update({
            'total_requests': current_metrics.get('counters', {}).get('requests.total', 0),
            'active_experts': current_metrics.get('gauges', {}).get('coordination.experts.active', 0),
            'memory_usage_mb': current_metrics.get('gauges', {}).get('system.memory_usage_bytes', 0) / 1024 / 1024
        })
        
        # Calculate uptime (simplified)
        if 'start_time' not in overview:
            overview['start_time'] = time.time()
        overview['uptime_hours'] = (time.time() - overview['start_time']) / 3600
    
    async def _update_performance_metrics(self):
        """Update performance metrics for all components"""
        perf_metrics = self.dashboard_data['performance_metrics']
        
        # Speed Layer metrics
        speed_layer = {}
        for cache_type in ['memory', 'policy', 'pattern']:
            cache_metrics = self.metrics.get_metric_summary(f'speed_layer.cache.{cache_type}.duration', 300)
            if cache_metrics:
                latest = cache_metrics[-1] if cache_metrics else None
                if latest:
                    speed_layer[f'{cache_type}_cache'] = {
                        'avg_ms': latest.avg * 1000,
                        'p95_ms': latest.p95 * 1000,
                        'p99_ms': latest.p99 * 1000,
                        'requests': latest.count
                    }
        
        # Calculate cache hit rates
        for cache_type in ['memory', 'policy', 'pattern']:
            hits = self.metrics.get_current_metrics().get('counters', {}).get(f'speed_layer.cache.{cache_type}.hits', 0)
            misses = self.metrics.get_current_metrics().get('counters', {}).get(f'speed_layer.cache.{cache_type}.misses', 0)
            total = hits + misses
            if total > 0:
                hit_rate = (hits / total) * 100
                if f'{cache_type}_cache' not in speed_layer:
                    speed_layer[f'{cache_type}_cache'] = {}
                speed_layer[f'{cache_type}_cache']['hit_rate_percent'] = hit_rate
        
        perf_metrics['speed_layer'] = speed_layer
        
        # FUSE filesystem metrics
        fuse_metrics = {}
        for operation in ['read', 'write', 'getattr', 'readdir']:
            operation_metrics = self.metrics.get_metric_summary(f'fuse.operations.{operation}.duration', 300)
            if operation_metrics:
                latest = operation_metrics[-1] if operation_metrics else None
                if latest:
                    fuse_metrics[f'{operation}_operation'] = {
                        'avg_ms': latest.avg * 1000,
                        'p95_ms': latest.p95 * 1000,
                        'p99_ms': latest.p99 * 1000,
                        'count': latest.count
                    }
        
        perf_metrics['fuse_filesystem'] = fuse_metrics
        
        # Expert coordination metrics
        coordination_metrics = {}
        expert_request_metrics = self.metrics.get_metric_summary('coordination.expert_request.duration', 300)
        if expert_request_metrics:
            latest = expert_request_metrics[-1] if expert_request_metrics else None
            if latest:
                coordination_metrics['expert_requests'] = {
                    'avg_ms': latest.avg * 1000,
                    'p95_ms': latest.p95 * 1000,
                    'p99_ms': latest.p99 * 1000,
                    'count': latest.count
                }
        
        perf_metrics['expert_coordination'] = coordination_metrics
    
    async def _update_health_status(self):
        """Update health status information"""
        system_health = self.health.get_system_health()
        
        self.dashboard_data['health_status'] = {
            'overall_status': system_health.get('overall_status', 'unknown'),
            'last_updated': system_health.get('timestamp', time.time()),
            'summary': system_health.get('summary', {}),
            'component_health': {}
        }
        
        # Get detailed component health
        for component_name in self.health.component_health.keys():
            component_health = self.health.get_component_health(component_name)
            if component_health:
                self.dashboard_data['health_status']['component_health'][component_name] = {
                    'status': component_health['status'],
                    'uptime_percent': component_health['uptime_percentage'],
                    'last_check': component_health['last_check'],
                    'consecutive_failures': component_health['consecutive_failures']
                }
    
    async def _update_expert_analytics(self):
        """Update expert agent analytics"""
        analytics = self.dashboard_data['expert_analytics']
        current_metrics = self.metrics.get_current_metrics()
        
        # Active agents (simplified - would need integration with actual expert registry)
        analytics['active_agents'] = []
        
        # Request distribution by expert type
        analytics['request_distribution'] = {}
        
        # Success rates by expert type
        analytics['success_rates'] = {}
        
        # Average response times
        analytics['average_response_times'] = {}
        
        # Expert utilization metrics
        expert_access_total = current_metrics.get('counters', {}).get('fuse.expert_access.total', 0)
        analytics['total_expert_accesses'] = expert_access_total
    
    async def _update_sla_compliance(self):
        """Update SLA compliance metrics"""
        sla = self.dashboard_data['sla_compliance']
        
        # Calculate availability percentage
        system_health = self.health.get_system_health()
        if system_health.get('summary'):
            total_components = system_health['summary'].get('total_components', 1)
            healthy_components = system_health['summary'].get('healthy_components', 0)
            availability = (healthy_components / total_components) * 100 if total_components > 0 else 0
            sla['availability_percent'] = availability
        
        # Performance compliance
        sla['performance_compliance'] = {}
        
        # Speed Layer P99 compliance
        speed_layer_metrics = self.dashboard_data['performance_metrics'].get('speed_layer', {})
        for cache_type in ['memory', 'policy', 'pattern']:
            cache_key = f'{cache_type}_cache'
            if cache_key in speed_layer_metrics:
                p99_ms = speed_layer_metrics[cache_key].get('p99_ms', 0)
                target_ms = self.performance_thresholds.get(f'speed_layer_p99_ms', 100)
                sla['performance_compliance'][f'{cache_type}_cache_p99'] = p99_ms <= target_ms
        
        # FUSE operation compliance
        fuse_metrics = self.dashboard_data['performance_metrics'].get('fuse_filesystem', {})
        for operation in ['read', 'write', 'getattr']:
            operation_key = f'{operation}_operation'
            if operation_key in fuse_metrics:
                p95_ms = fuse_metrics[operation_key].get('p95_ms', 0)
                target_ms = self.performance_thresholds.get('fuse_operation_p95_ms', 10)
                sla['performance_compliance'][f'{operation}_p95'] = p95_ms <= target_ms
        
        # Calculate overall SLA compliance
        compliant_metrics = sum(1 for compliant in sla['performance_compliance'].values() if compliant)
        total_metrics = len(sla['performance_compliance'])
        sla['overall_compliance_percent'] = (compliant_metrics / total_metrics * 100) if total_metrics > 0 else 100
    
    async def _update_trends(self):
        """Update trend data for charts"""
        trends = self.dashboard_data['trends']
        current_time = time.time()
        
        # Request rate trend
        current_requests = self.metrics.get_current_metrics().get('counters', {}).get('requests.total', 0)
        trends['request_rate'].append({
            'timestamp': current_time,
            'value': current_requests
        })
        
        # Keep only last 100 data points for trends
        max_points = 100
        for trend_name in trends:
            if len(trends[trend_name]) > max_points:
                trends[trend_name] = trends[trend_name][-max_points:]
    
    async def _check_alerts(self):
        """Check for performance issues and generate alerts"""
        current_time = time.time()
        new_alerts = []
        
        # Check Speed Layer performance
        speed_layer_metrics = self.dashboard_data['performance_metrics'].get('speed_layer', {})
        for cache_type in ['memory', 'policy', 'pattern']:
            cache_key = f'{cache_type}_cache'
            if cache_key in speed_layer_metrics:
                p99_ms = speed_layer_metrics[cache_key].get('p99_ms', 0)
                if p99_ms > self.performance_thresholds.get('speed_layer_p99_ms', 100):
                    new_alerts.append({
                        'timestamp': current_time,
                        'severity': 'warning',
                        'component': 'speed_layer',
                        'metric': f'{cache_type}_cache_p99',
                        'message': f'{cache_type} cache P99 latency is {p99_ms:.1f}ms (threshold: {self.performance_thresholds["speed_layer_p99_ms"]}ms)',
                        'value': p99_ms,
                        'threshold': self.performance_thresholds['speed_layer_p99_ms']
                    })
        
        # Check cache hit rates
        for cache_type in ['memory', 'policy', 'pattern']:
            cache_key = f'{cache_type}_cache'
            if cache_key in speed_layer_metrics:
                hit_rate = speed_layer_metrics[cache_key].get('hit_rate_percent', 100)
                if hit_rate < self.performance_thresholds.get('cache_hit_rate_percent', 95):
                    new_alerts.append({
                        'timestamp': current_time,
                        'severity': 'warning',
                        'component': 'speed_layer',
                        'metric': f'{cache_type}_cache_hit_rate',
                        'message': f'{cache_type} cache hit rate is {hit_rate:.1f}% (threshold: {self.performance_thresholds["cache_hit_rate_percent"]}%)',
                        'value': hit_rate,
                        'threshold': self.performance_thresholds['cache_hit_rate_percent']
                    })
        
        # Check FUSE performance
        fuse_metrics = self.dashboard_data['performance_metrics'].get('fuse_filesystem', {})
        for operation in ['read', 'write', 'getattr']:
            operation_key = f'{operation}_operation'
            if operation_key in fuse_metrics:
                p95_ms = fuse_metrics[operation_key].get('p95_ms', 0)
                if p95_ms > self.performance_thresholds.get('fuse_operation_p95_ms', 10):
                    new_alerts.append({
                        'timestamp': current_time,
                        'severity': 'warning',
                        'component': 'fuse_filesystem',
                        'metric': f'{operation}_p95',
                        'message': f'FUSE {operation} P95 latency is {p95_ms:.1f}ms (threshold: {self.performance_thresholds["fuse_operation_p95_ms"]}ms)',
                        'value': p95_ms,
                        'threshold': self.performance_thresholds['fuse_operation_p95_ms']
                    })
        
        # Check system health alerts
        health_status = self.dashboard_data['health_status']
        if health_status['overall_status'] in ['unhealthy', 'critical']:
            new_alerts.append({
                'timestamp': current_time,
                'severity': 'critical' if health_status['overall_status'] == 'critical' else 'error',
                'component': 'system_health',
                'metric': 'overall_status',
                'message': f'System health is {health_status["overall_status"]}',
                'value': health_status['overall_status']
            })
        
        # Add new alerts
        self.alerts.extend(new_alerts)
        
        # Keep only recent alerts
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        # Update dashboard with recent alerts
        self.dashboard_data['recent_alerts'] = self.alerts[-10:]  # Last 10 alerts
        
        # Log critical alerts
        for alert in new_alerts:
            if alert['severity'] == 'critical':
                logger.critical(f"CRITICAL ALERT: {alert['message']}")
            elif alert['severity'] == 'error':
                logger.error(f"ERROR ALERT: {alert['message']}")
            elif alert['severity'] == 'warning':
                logger.warning(f"WARNING ALERT: {alert['message']}")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get current dashboard data"""
        return self.dashboard_data.copy()
    
    def get_component_details(self, component: str) -> Dict[str, Any]:
        """Get detailed information for a specific component"""
        details = {}
        
        if component == 'speed_layer':
            details = {
                'metrics': self.dashboard_data['performance_metrics'].get('speed_layer', {}),
                'health': self.dashboard_data['health_status']['component_health'].get('speed_layer', {}),
                'recent_trends': [
                    point for point in self.dashboard_data['trends']['response_times']
                    if point.get('component') == 'speed_layer'
                ][-20:]  # Last 20 points
            }
        
        elif component == 'fuse_filesystem':
            details = {
                'metrics': self.dashboard_data['performance_metrics'].get('fuse_filesystem', {}),
                'health': self.dashboard_data['health_status']['component_health'].get('fuse_mount', {}),
                'expert_usage': self.dashboard_data['expert_analytics'].get('total_expert_accesses', 0)
            }
        
        elif component == 'expert_coordination':
            details = {
                'metrics': self.dashboard_data['performance_metrics'].get('expert_coordination', {}),
                'analytics': self.dashboard_data['expert_analytics'],
                'health': self.dashboard_data['health_status']['component_health'].get('expert_coordinator', {})
            }
        
        return details
    
    def get_alerts(self, severity: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get alerts, optionally filtered by severity"""
        alerts = self.alerts
        
        if severity:
            alerts = [alert for alert in alerts if alert['severity'] == severity]
        
        return alerts[-limit:] if limit else alerts
    
    def get_sla_report(self, time_range_hours: int = 24) -> Dict[str, Any]:
        """Generate SLA compliance report"""
        current_sla = self.dashboard_data['sla_compliance']
        
        report = {
            'time_range_hours': time_range_hours,
            'generated_at': time.time(),
            'availability': {
                'current_percent': current_sla.get('availability_percent', 0),
                'target_percent': 99.9,
                'compliant': current_sla.get('availability_percent', 0) >= 99.9
            },
            'performance': {
                'overall_compliance_percent': current_sla.get('overall_compliance_percent', 0),
                'details': current_sla.get('performance_compliance', {})
            },
            'alerts_summary': {
                'total_alerts': len(self.alerts),
                'critical_alerts': len([a for a in self.alerts if a['severity'] == 'critical']),
                'error_alerts': len([a for a in self.alerts if a['severity'] == 'error']),
                'warning_alerts': len([a for a in self.alerts if a['severity'] == 'warning'])
            }
        }
        
        return report
    
    def export_metrics(self, format_type: str = "json") -> str:
        """Export dashboard data in specified format"""
        if format_type == "json":
            return json.dumps(self.get_dashboard_data(), indent=2)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")


# Factory function for Bridge integration
def create_observability_dashboard(
    metrics_collector: MetricsCollector,
    health_monitor: HealthMonitor
) -> ObservabilityDashboard:
    """Create observability dashboard with Bridge integration"""
    dashboard = ObservabilityDashboard(metrics_collector, health_monitor)
    return dashboard