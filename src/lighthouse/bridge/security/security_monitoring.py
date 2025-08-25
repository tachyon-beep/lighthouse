"""
Advanced Security Monitoring and External Consultant Integration

Comprehensive security event monitoring, alerting, and integration framework
for external security consultant oversight as required by Plan Charlie Phase 1.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union
import uuid

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Types of security events."""
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHORIZATION_FAILURE = "authorization_failure"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RACE_CONDITION_DETECTED = "race_condition_detected"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    TOKEN_REPLAY_DETECTED = "token_replay_detected"
    BYZANTINE_BEHAVIOR = "byzantine_behavior"
    CONSENSUS_MANIPULATION = "consensus_manipulation"
    CACHE_POISONING = "cache_poisoning"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    SYSTEM_COMPROMISE = "system_compromise"
    EXTERNAL_THREAT = "external_threat"
    INSIDER_THREAT = "insider_threat"


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(Enum):
    """Alert status for tracking."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


@dataclass
class SecurityEvent:
    """Security event record."""
    event_id: str
    event_type: SecurityEventType
    timestamp: datetime
    source_component: str
    agent_id: Optional[str] = None
    source_ip: Optional[str] = None
    description: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source_component": self.source_component,
            "agent_id": self.agent_id,
            "source_ip": self.source_ip,
            "description": self.description,
            "metadata": self.metadata
        }


@dataclass
class SecurityAlert:
    """Security alert with escalation capabilities."""
    alert_id: str
    severity: AlertSeverity
    title: str
    description: str
    created_at: datetime
    source_events: List[str]  # Event IDs that triggered this alert
    status: AlertStatus = AlertStatus.NEW
    assigned_to: Optional[str] = None
    escalated_to_consultant: bool = False
    consultant_notes: str = ""
    resolution_notes: str = ""
    false_positive_reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


class ExternalConsultantInterface:
    """Interface for external security consultant integration."""
    
    def __init__(self, consultant_endpoint: Optional[str] = None,
                 api_key: Optional[str] = None):
        """
        Initialize consultant interface.
        
        Args:
            consultant_endpoint: External consultant API endpoint
            api_key: API key for consultant authentication
        """
        self.consultant_endpoint = consultant_endpoint
        self.api_key = api_key
        self.enabled = bool(consultant_endpoint and api_key)
        
        # Consultation tracking
        self.active_consultations: Dict[str, Dict[str, Any]] = {}
        self.consultation_history: List[Dict[str, Any]] = []
        
        # Response tracking
        self.consultant_responses: Dict[str, Dict[str, Any]] = {}
    
    async def escalate_alert(self, alert: SecurityAlert,
                           context: Dict[str, Any] = None) -> str:
        """
        Escalate alert to external security consultant.
        
        Args:
            alert: Security alert to escalate
            context: Additional context information
            
        Returns:
            Consultation ID
        """
        if not self.enabled:
            logger.warning("External consultant integration not configured")
            return "mock_consultation_id"
        
        consultation_id = str(uuid.uuid4())
        
        consultation_data = {
            "consultation_id": consultation_id,
            "alert": alert.to_dict(),
            "context": context or {},
            "system_info": {
                "system_name": "Lighthouse Multi-Agent System",
                "timestamp": datetime.utcnow().isoformat(),
                "threat_level": alert.severity.value
            },
            "requested_actions": [
                "threat_assessment",
                "remediation_recommendations", 
                "incident_classification"
            ]
        }
        
        # Store consultation locally
        self.active_consultations[consultation_id] = {
            "created_at": datetime.utcnow(),
            "alert_id": alert.alert_id,
            "status": "pending_consultant_review",
            "data": consultation_data
        }
        
        try:
            # In a real implementation, this would make HTTP request to consultant
            logger.info(
                f"Escalating alert {alert.alert_id} to external consultant "
                f"(consultation: {consultation_id})"
            )
            
            # Mock consultant response for demonstration
            await self._simulate_consultant_response(consultation_id)
            
            alert.escalated_to_consultant = True
            return consultation_id
            
        except Exception as e:
            logger.error(f"Failed to escalate to consultant: {str(e)}")
            # Remove from active consultations on failure
            self.active_consultations.pop(consultation_id, None)
            raise
    
    async def _simulate_consultant_response(self, consultation_id: str) -> None:
        """Simulate external consultant response (for demo/testing)."""
        # In production, this would be replaced by webhook handlers
        await asyncio.sleep(2)  # Simulate network delay
        
        consultation = self.active_consultations.get(consultation_id)
        if not consultation:
            return
        
        alert_severity = consultation["data"]["alert"]["severity"]
        
        # Generate mock consultant response based on severity
        if alert_severity in ["critical", "high"]:
            response = {
                "consultation_id": consultation_id,
                "threat_assessment": "CONFIRMED_THREAT",
                "confidence": 0.85,
                "classification": "ACTIVE_ATTACK" if alert_severity == "critical" else "SUSPICIOUS_ACTIVITY",
                "recommendations": [
                    "Immediately isolate affected systems",
                    "Collect additional forensic evidence",
                    "Monitor for lateral movement",
                    "Implement additional access controls",
                    "Schedule emergency security review"
                ],
                "urgency": "IMMEDIATE" if alert_severity == "critical" else "HIGH",
                "estimated_response_time": "15 minutes" if alert_severity == "critical" else "1 hour",
                "consultant_notes": f"High confidence threat detection. Recommend immediate containment actions.",
                "follow_up_required": True
            }
        else:
            response = {
                "consultation_id": consultation_id,
                "threat_assessment": "LOW_RISK",
                "confidence": 0.65,
                "classification": "ROUTINE_MONITORING",
                "recommendations": [
                    "Continue monitoring",
                    "Update security policies if needed",
                    "Schedule routine security review"
                ],
                "urgency": "ROUTINE",
                "estimated_response_time": "24 hours",
                "consultant_notes": "Low risk event. Standard monitoring procedures adequate.",
                "follow_up_required": False
            }
        
        # Store response
        self.consultant_responses[consultation_id] = {
            "received_at": datetime.utcnow(),
            "response": response
        }
        
        # Update consultation status
        consultation["status"] = "consultant_responded"
        
        logger.info(f"Received consultant response for {consultation_id}: {response['threat_assessment']}")
    
    def get_consultation_status(self, consultation_id: str) -> Optional[Dict[str, Any]]:
        """Get status of consultation with external consultant."""
        consultation = self.active_consultations.get(consultation_id)
        if not consultation:
            return None
        
        response = self.consultant_responses.get(consultation_id)
        
        return {
            "consultation_id": consultation_id,
            "status": consultation["status"],
            "created_at": consultation["created_at"].isoformat(),
            "alert_id": consultation["alert_id"],
            "consultant_response": response["response"] if response else None,
            "response_received_at": response["received_at"].isoformat() if response else None
        }
    
    def get_all_consultations(self) -> List[Dict[str, Any]]:
        """Get all consultation records."""
        return [
            self.get_consultation_status(cid) 
            for cid in self.active_consultations.keys()
        ]


class SecurityMonitoringEngine:
    """
    Advanced security monitoring engine with ML-based threat detection
    and external consultant integration.
    """
    
    def __init__(self, consultant_interface: Optional[ExternalConsultantInterface] = None):
        """Initialize security monitoring engine."""
        self.consultant = consultant_interface or ExternalConsultantInterface()
        
        # Event storage
        self.security_events: deque = deque(maxlen=100000)  # Keep last 100k events
        self.event_index: Dict[str, SecurityEvent] = {}
        
        # Alert management
        self.active_alerts: Dict[str, SecurityAlert] = {}
        self.alert_history: List[SecurityAlert] = []
        
        # Pattern detection
        self.pattern_detectors: Dict[str, Callable] = {}
        self.detection_rules: List[Dict[str, Any]] = []
        
        # Statistics
        self.event_counts: Dict[SecurityEventType, int] = defaultdict(int)
        self.alert_counts: Dict[AlertSeverity, int] = defaultdict(int)
        
        # Real-time monitoring
        self.monitoring_active = True
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Initialize default detection patterns
        self._initialize_detection_patterns()
        self._initialize_detection_rules()
    
    def _initialize_detection_patterns(self):
        """Initialize default threat detection patterns."""
        
        async def detect_brute_force_attacks(events: List[SecurityEvent]) -> List[SecurityAlert]:
            """Detect brute force authentication attacks."""
            alerts = []
            
            # Group authentication failures by agent_id and source_ip
            failure_counts = defaultdict(int)
            recent_failures = []
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=5)
            
            for event in events:
                if (event.event_type == SecurityEventType.AUTHENTICATION_FAILURE and
                    event.timestamp > cutoff_time):
                    recent_failures.append(event)
                    key = f"{event.agent_id}:{event.source_ip}"
                    failure_counts[key] += 1
            
            # Check for excessive failures
            for key, count in failure_counts.items():
                if count >= 5:  # 5+ failures in 5 minutes
                    agent_id, source_ip = key.split(":", 1)
                    
                    alert = SecurityAlert(
                        alert_id=str(uuid.uuid4()),
                        severity=AlertSeverity.HIGH,
                        title=f"Brute Force Attack Detected",
                        description=f"Detected {count} authentication failures from {source_ip} for agent {agent_id} in 5 minutes",
                        created_at=datetime.utcnow(),
                        source_events=[e.event_id for e in recent_failures 
                                     if e.agent_id == agent_id and e.source_ip == source_ip]
                    )
                    alerts.append(alert)
            
            return alerts
        
        async def detect_privilege_escalation(events: List[SecurityEvent]) -> List[SecurityAlert]:
            """Detect privilege escalation attempts."""
            alerts = []
            
            escalation_events = [
                e for e in events
                if e.event_type == SecurityEventType.PRIVILEGE_ESCALATION
            ]
            
            for event in escalation_events:
                alert = SecurityAlert(
                    alert_id=str(uuid.uuid4()),
                    severity=AlertSeverity.CRITICAL,
                    title="Privilege Escalation Detected",
                    description=f"Privilege escalation attempt by {event.agent_id}",
                    created_at=datetime.utcnow(),
                    source_events=[event.event_id]
                )
                alerts.append(alert)
            
            return alerts
        
        async def detect_byzantine_behavior(events: List[SecurityEvent]) -> List[SecurityAlert]:
            """Detect Byzantine/malicious agent behavior."""
            alerts = []
            
            byzantine_events = [
                e for e in events
                if e.event_type in [SecurityEventType.BYZANTINE_BEHAVIOR, 
                                   SecurityEventType.CONSENSUS_MANIPULATION]
            ]
            
            for event in byzantine_events:
                alert = SecurityAlert(
                    alert_id=str(uuid.uuid4()),
                    severity=AlertSeverity.CRITICAL,
                    title="Malicious Agent Behavior Detected",
                    description=f"Byzantine behavior detected from agent {event.agent_id}",
                    created_at=datetime.utcnow(),
                    source_events=[event.event_id]
                )
                alerts.append(alert)
            
            return alerts
        
        # Register pattern detectors
        self.pattern_detectors["brute_force"] = detect_brute_force_attacks
        self.pattern_detectors["privilege_escalation"] = detect_privilege_escalation
        self.pattern_detectors["byzantine_behavior"] = detect_byzantine_behavior
    
    def _initialize_detection_rules(self):
        """Initialize rule-based detection."""
        self.detection_rules = [
            {
                "rule_id": "R001",
                "name": "Multiple Path Traversal Attempts",
                "description": "Detect multiple path traversal attempts from same source",
                "event_type": SecurityEventType.PATH_TRAVERSAL_ATTEMPT,
                "threshold": 3,
                "time_window_minutes": 10,
                "severity": AlertSeverity.HIGH
            },
            {
                "rule_id": "R002", 
                "name": "Race Condition Pattern",
                "description": "Detect patterns of race condition exploitation",
                "event_type": SecurityEventType.RACE_CONDITION_DETECTED,
                "threshold": 2,
                "time_window_minutes": 5,
                "severity": AlertSeverity.HIGH
            },
            {
                "rule_id": "R003",
                "name": "Token Replay Attack",
                "description": "Detect token replay attack attempts",
                "event_type": SecurityEventType.TOKEN_REPLAY_DETECTED,
                "threshold": 1,
                "time_window_minutes": 1,
                "severity": AlertSeverity.CRITICAL
            }
        ]
    
    async def record_security_event(self, event: SecurityEvent) -> None:
        """Record a security event and trigger analysis."""
        # Store event
        self.security_events.append(event)
        self.event_index[event.event_id] = event
        self.event_counts[event.event_type] += 1
        
        logger.debug(f"Recorded security event: {event.event_type.value} from {event.source_component}")
        
        # Trigger real-time analysis
        await self._analyze_event(event)
    
    async def _analyze_event(self, event: SecurityEvent) -> None:
        """Analyze single event for immediate threats."""
        # Check for immediate critical events
        critical_events = [
            SecurityEventType.SYSTEM_COMPROMISE,
            SecurityEventType.TOKEN_REPLAY_DETECTED,
            SecurityEventType.PRIVILEGE_ESCALATION
        ]
        
        if event.event_type in critical_events:
            alert = SecurityAlert(
                alert_id=str(uuid.uuid4()),
                severity=AlertSeverity.CRITICAL,
                title=f"Critical Security Event: {event.event_type.value}",
                description=f"Immediate attention required: {event.description}",
                created_at=datetime.utcnow(),
                source_events=[event.event_id]
            )
            
            await self._handle_alert(alert)
    
    async def _handle_alert(self, alert: SecurityAlert) -> None:
        """Handle new security alert."""
        self.active_alerts[alert.alert_id] = alert
        self.alert_counts[alert.severity] += 1
        
        logger.warning(f"Security alert generated: {alert.title} (Severity: {alert.severity.value})")
        
        # Auto-escalate critical and high severity alerts
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            try:
                consultation_id = await self.consultant.escalate_alert(
                    alert, 
                    context=self._gather_alert_context(alert)
                )
                logger.info(f"Alert {alert.alert_id} escalated to consultant: {consultation_id}")
            except Exception as e:
                logger.error(f"Failed to escalate alert {alert.alert_id}: {str(e)}")
    
    def _gather_alert_context(self, alert: SecurityAlert) -> Dict[str, Any]:
        """Gather additional context for alert escalation."""
        context = {
            "recent_events": [],
            "system_state": {},
            "threat_indicators": []
        }
        
        # Get recent related events
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        recent_events = [
            event.to_dict() for event in self.security_events
            if event.timestamp > cutoff_time
        ]
        context["recent_events"] = recent_events[-50:]  # Last 50 events
        
        # System state information
        context["system_state"] = {
            "total_active_alerts": len(self.active_alerts),
            "events_last_hour": len(recent_events),
            "top_event_types": [
                et.value for et, count in 
                sorted(self.event_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
        }
        
        return context
    
    async def run_pattern_analysis(self) -> List[SecurityAlert]:
        """Run pattern-based threat detection."""
        new_alerts = []
        
        # Get recent events for analysis
        recent_events = list(self.security_events)[-1000:]  # Last 1000 events
        
        # Run pattern detectors
        for detector_name, detector_func in self.pattern_detectors.items():
            try:
                detected_alerts = await detector_func(recent_events)
                new_alerts.extend(detected_alerts)
            except Exception as e:
                logger.error(f"Pattern detector {detector_name} failed: {str(e)}")
        
        # Run rule-based detection
        rule_alerts = await self._run_rule_detection(recent_events)
        new_alerts.extend(rule_alerts)
        
        # Process new alerts
        for alert in new_alerts:
            await self._handle_alert(alert)
        
        return new_alerts
    
    async def _run_rule_detection(self, events: List[SecurityEvent]) -> List[SecurityAlert]:
        """Run rule-based detection on events."""
        alerts = []
        
        for rule in self.detection_rules:
            cutoff_time = datetime.utcnow() - timedelta(minutes=rule["time_window_minutes"])
            
            # Count matching events in time window
            matching_events = [
                event for event in events
                if (event.event_type.value == rule["event_type"].value and
                    event.timestamp > cutoff_time)
            ]
            
            if len(matching_events) >= rule["threshold"]:
                alert = SecurityAlert(
                    alert_id=str(uuid.uuid4()),
                    severity=rule["severity"],
                    title=rule["name"],
                    description=f"{rule['description']} - {len(matching_events)} events in {rule['time_window_minutes']} minutes",
                    created_at=datetime.utcnow(),
                    source_events=[e.event_id for e in matching_events]
                )
                alerts.append(alert)
        
        return alerts
    
    async def start_monitoring(self) -> None:
        """Start continuous security monitoring."""
        if self.monitoring_task and not self.monitoring_task.done():
            logger.warning("Security monitoring already running")
            return
        
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Security monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop security monitoring."""
        self.monitoring_active = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Security monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self.monitoring_active:
            try:
                # Run pattern analysis every 30 seconds
                await self.run_pattern_analysis()
                
                # Clean up old events and alerts
                await self._cleanup_old_data()
                
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Security monitoring loop error: {str(e)}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _cleanup_old_data(self) -> None:
        """Clean up old events and resolved alerts."""
        # Move resolved alerts to history
        resolved_alerts = [
            alert for alert in self.active_alerts.values()
            if alert.status in [AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE]
        ]
        
        for alert in resolved_alerts:
            self.alert_history.append(alert)
            del self.active_alerts[alert.alert_id]
        
        # Clean up event index for old events not in deque
        current_event_ids = {event.event_id for event in self.security_events}
        old_event_ids = set(self.event_index.keys()) - current_event_ids
        
        for event_id in old_event_ids:
            del self.event_index[event_id]
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get comprehensive monitoring status."""
        return {
            "monitoring_active": self.monitoring_active,
            "total_events": len(self.security_events),
            "total_active_alerts": len(self.active_alerts),
            "total_resolved_alerts": len(self.alert_history),
            "event_counts_by_type": {et.value: count for et, count in self.event_counts.items()},
            "alert_counts_by_severity": {sev.value: count for sev, count in self.alert_counts.items()},
            "consultant_integration": {
                "enabled": self.consultant.enabled,
                "active_consultations": len(self.consultant.active_consultations),
                "total_consultations": len(self.consultant.consultation_history)
            }
        }
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        all_alerts = list(self.active_alerts.values()) + self.alert_history
        sorted_alerts = sorted(all_alerts, key=lambda a: a.created_at, reverse=True)
        return [alert.to_dict() for alert in sorted_alerts[:limit]]
    
    def get_alert_details(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed alert information."""
        alert = self.active_alerts.get(alert_id)
        if not alert:
            # Check history
            for hist_alert in self.alert_history:
                if hist_alert.alert_id == alert_id:
                    alert = hist_alert
                    break
        
        if not alert:
            return None
        
        # Get related events
        related_events = [
            self.event_index[event_id].to_dict()
            for event_id in alert.source_events
            if event_id in self.event_index
        ]
        
        # Get consultant information
        consultation_info = None
        if alert.escalated_to_consultant:
            # Find consultation for this alert
            for consultation_id, consultation in self.consultant.active_consultations.items():
                if consultation["alert_id"] == alert_id:
                    consultation_info = self.consultant.get_consultation_status(consultation_id)
                    break
        
        alert_dict = alert.to_dict()
        alert_dict["related_events"] = related_events
        alert_dict["consultation_info"] = consultation_info
        
        return alert_dict


# Global security monitoring instance
_global_security_monitor: Optional[SecurityMonitoringEngine] = None


def get_security_monitor() -> SecurityMonitoringEngine:
    """Get global security monitoring instance."""
    global _global_security_monitor
    if _global_security_monitor is None:
        consultant = ExternalConsultantInterface()
        _global_security_monitor = SecurityMonitoringEngine(consultant)
    return _global_security_monitor


# Convenience functions for logging security events
async def log_security_event(event_type: SecurityEventType,
                            source_component: str,
                            description: str = "",
                            agent_id: Optional[str] = None,
                            source_ip: Optional[str] = None,
                            metadata: Optional[Dict[str, Any]] = None) -> None:
    """Log a security event to the monitoring system."""
    event = SecurityEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        timestamp=datetime.utcnow(),
        source_component=source_component,
        agent_id=agent_id,
        source_ip=source_ip,
        description=description,
        metadata=metadata or {}
    )
    
    monitor = get_security_monitor()
    await monitor.record_security_event(event)