"""
Event Store Integrity Monitoring System
Phase 1 Days 8-10: Real-time integrity violation detection and alerting

Provides:
- Cryptographic hash validation for event store integrity
- Real-time integrity violation detection
- Automated alerting system for integrity breaches
- Comprehensive audit trail for security analysis
"""

import asyncio
import hashlib
import hmac
import json
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor

# Configure logging for integrity monitoring
logger = logging.getLogger(__name__)


class IntegrityViolationType(Enum):
    """Types of integrity violations that can be detected"""
    HASH_MISMATCH = "hash_mismatch"
    TIMESTAMP_ANOMALY = "timestamp_anomaly"
    EVENT_TAMPERING = "event_tampering"
    SEQUENCE_CORRUPTION = "sequence_corruption"
    UNAUTHORIZED_MODIFICATION = "unauthorized_modification"
    CRYPTOGRAPHIC_FAILURE = "cryptographic_failure"


@dataclass
class IntegrityViolation:
    """Detailed integrity violation record"""
    violation_id: str
    violation_type: IntegrityViolationType
    event_id: str
    agent_id: str
    detected_at: datetime
    expected_hash: str
    actual_hash: str
    severity: str = "high"  # low, medium, high, critical
    additional_data: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution_notes: str = ""


@dataclass 
class IntegrityMetrics:
    """Comprehensive integrity monitoring metrics"""
    total_events_monitored: int = 0
    violations_detected: int = 0
    violations_resolved: int = 0
    hash_validations_performed: int = 0
    realtime_checks_active: int = 0
    last_violation_detected: Optional[datetime] = None
    system_integrity_score: float = 100.0  # 0-100 percentage
    
    def calculate_integrity_score(self):
        """Calculate overall system integrity score"""
        if self.total_events_monitored == 0:
            return 100.0
        
        violation_rate = self.violations_detected / self.total_events_monitored
        resolution_rate = self.violations_resolved / max(1, self.violations_detected)
        
        # Score calculation: penalize violations, reward resolutions
        base_score = max(0, 100 - (violation_rate * 1000))  # Heavy penalty for violations
        resolution_bonus = resolution_rate * 10  # Bonus for resolving violations
        
        self.system_integrity_score = min(100.0, base_score + resolution_bonus)
        return self.system_integrity_score


class EventStoreIntegrityMonitor:
    """
    Real-time event store integrity monitoring with cryptographic validation
    """
    
    def __init__(self, 
                 secret_key: str,
                 alert_callbacks: List[Callable[[IntegrityViolation], None]] = None,
                 check_interval: float = 1.0):
        """
        Initialize integrity monitor
        
        Args:
            secret_key: Secret key for HMAC cryptographic validation
            alert_callbacks: List of callback functions for violation alerts
            check_interval: Interval in seconds between integrity checks
        """
        self.secret_key = secret_key
        self.alert_callbacks = alert_callbacks or []
        self.check_interval = check_interval
        
        # Internal state
        self.event_hashes: Dict[str, str] = {}
        self.event_metadata: Dict[str, Dict[str, Any]] = {}
        self.violations: List[IntegrityViolation] = []
        self.metrics = IntegrityMetrics()
        
        # Monitoring control
        self.monitoring_active = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        
        # Real-time checking
        self.realtime_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.realtime_processors: List[asyncio.Task] = []
        
        logger.info("Event store integrity monitor initialized")
    
    def calculate_event_hash(self, event_data: Dict[str, Any], use_hmac: bool = True) -> str:
        """
        Calculate cryptographic hash for event integrity verification
        
        Args:
            event_data: Event data dictionary to hash
            use_hmac: Whether to use HMAC for additional security
            
        Returns:
            Cryptographic hash string
        """
        try:
            # Serialize event data deterministically
            serialized = json.dumps(event_data, sort_keys=True, separators=(',', ':'))
            
            if use_hmac:
                # Use HMAC-SHA256 for cryptographic security
                hash_obj = hmac.new(
                    self.secret_key.encode(),
                    serialized.encode(),
                    hashlib.sha256
                )
                return hash_obj.hexdigest()
            else:
                # Use SHA256 for basic integrity checking
                return hashlib.sha256(serialized.encode()).hexdigest()
                
        except Exception as e:
            logger.error(f"Failed to calculate event hash: {e}")
            raise
    
    def register_event(self, event_id: str, event_data: Dict[str, Any], agent_id: str = None):
        """
        Register new event for integrity monitoring
        
        Args:
            event_id: Unique event identifier
            event_data: Event data to monitor
            agent_id: Agent that created the event
        """
        try:
            # Calculate baseline hash
            event_hash = self.calculate_event_hash(event_data)
            
            # Store hash and metadata
            self.event_hashes[event_id] = event_hash
            self.event_metadata[event_id] = {
                'agent_id': agent_id,
                'registered_at': datetime.now(timezone.utc),
                'original_data': event_data.copy(),
                'validation_count': 0
            }
            
            self.metrics.total_events_monitored += 1
            
            # Queue for real-time validation if monitoring active
            if self.monitoring_active:
                try:
                    self.realtime_queue.put_nowait({
                        'action': 'validate',
                        'event_id': event_id,
                        'event_data': event_data
                    })
                except asyncio.QueueFull:
                    logger.warning(f"Real-time queue full, skipping validation for {event_id}")
                    
        except Exception as e:
            logger.error(f"Failed to register event {event_id}: {e}")
    
    def validate_event_integrity(self, event_id: str, current_data: Dict[str, Any]) -> bool:
        """
        Validate event integrity against stored hash
        
        Args:
            event_id: Event ID to validate
            current_data: Current event data
            
        Returns:
            True if integrity is valid, False if violated
        """
        try:
            if event_id not in self.event_hashes:
                logger.warning(f"Event {event_id} not registered for integrity monitoring")
                return False
            
            # Calculate current hash
            current_hash = self.calculate_event_hash(current_data)
            expected_hash = self.event_hashes[event_id]
            
            self.metrics.hash_validations_performed += 1
            
            # Update validation count
            if event_id in self.event_metadata:
                self.event_metadata[event_id]['validation_count'] += 1
            
            # Check for hash mismatch
            if current_hash != expected_hash:
                self._handle_integrity_violation(
                    event_id=event_id,
                    violation_type=IntegrityViolationType.HASH_MISMATCH,
                    expected_hash=expected_hash,
                    actual_hash=current_hash,
                    current_data=current_data
                )
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate integrity for event {event_id}: {e}")
            return False
    
    def _handle_integrity_violation(self,
                                  event_id: str,
                                  violation_type: IntegrityViolationType,
                                  expected_hash: str,
                                  actual_hash: str,
                                  current_data: Dict[str, Any]):
        """
        Handle detected integrity violation with alerting
        
        Args:
            event_id: Event ID with violation
            violation_type: Type of integrity violation
            expected_hash: Expected cryptographic hash
            actual_hash: Actual hash that was detected
            current_data: Current event data showing violation
        """
        try:
            # Get agent ID from metadata
            agent_id = "unknown"
            if event_id in self.event_metadata:
                agent_id = self.event_metadata[event_id].get('agent_id', 'unknown')
            
            # Create violation record
            violation = IntegrityViolation(
                violation_id=f"INT_VIOL_{int(time.time() * 1000)}",
                violation_type=violation_type,
                event_id=event_id,
                agent_id=agent_id,
                detected_at=datetime.now(timezone.utc),
                expected_hash=expected_hash,
                actual_hash=actual_hash,
                severity=self._assess_violation_severity(violation_type, current_data),
                additional_data={
                    'original_data': self.event_metadata.get(event_id, {}).get('original_data'),
                    'current_data': current_data,
                    'detection_method': 'realtime_monitoring'
                }
            )
            
            # Store violation
            self.violations.append(violation)
            self.metrics.violations_detected += 1
            self.metrics.last_violation_detected = violation.detected_at
            
            # Update integrity score
            self.metrics.calculate_integrity_score()
            
            # Log violation
            logger.critical(f"INTEGRITY VIOLATION DETECTED: {violation.violation_id} - "
                          f"Event {event_id} from agent {agent_id} - "
                          f"Type: {violation_type.value} - Severity: {violation.severity}")
            
            # Trigger alert callbacks
            self._trigger_alerts(violation)
            
        except Exception as e:
            logger.error(f"Failed to handle integrity violation: {e}")
    
    def _assess_violation_severity(self, 
                                 violation_type: IntegrityViolationType, 
                                 current_data: Dict[str, Any]) -> str:
        """
        Assess severity of integrity violation
        
        Args:
            violation_type: Type of violation detected
            current_data: Current event data
            
        Returns:
            Severity level: "low", "medium", "high", "critical"
        """
        # Critical violations - system security breaches
        if violation_type in [
            IntegrityViolationType.EVENT_TAMPERING,
            IntegrityViolationType.UNAUTHORIZED_MODIFICATION,
            IntegrityViolationType.CRYPTOGRAPHIC_FAILURE
        ]:
            return "critical"
        
        # High violations - data integrity issues
        if violation_type in [
            IntegrityViolationType.HASH_MISMATCH,
            IntegrityViolationType.SEQUENCE_CORRUPTION
        ]:
            return "high"
        
        # Medium violations - timing anomalies
        if violation_type == IntegrityViolationType.TIMESTAMP_ANOMALY:
            return "medium"
        
        return "medium"  # Default to medium severity
    
    def _trigger_alerts(self, violation: IntegrityViolation):
        """
        Trigger all registered alert callbacks for integrity violation
        
        Args:
            violation: IntegrityViolation to alert about
        """
        for callback in self.alert_callbacks:
            try:
                callback(violation)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
    
    def add_alert_callback(self, callback: Callable[[IntegrityViolation], None]):
        """
        Add alert callback for integrity violations
        
        Args:
            callback: Function to call when violation detected
        """
        self.alert_callbacks.append(callback)
        logger.info("Added integrity violation alert callback")
    
    async def start_realtime_monitoring(self, num_processors: int = 2):
        """
        Start real-time integrity monitoring
        
        Args:
            num_processors: Number of concurrent processors for real-time checks
        """
        if self.monitoring_active:
            logger.warning("Real-time monitoring already active")
            return
        
        self.monitoring_active = True
        self.metrics.realtime_checks_active = num_processors
        
        # Start real-time processors
        self.realtime_processors = []
        for i in range(num_processors):
            processor = asyncio.create_task(self._realtime_processor(f"processor_{i}"))
            self.realtime_processors.append(processor)
        
        # Start periodic integrity sweep
        self.monitor_task = asyncio.create_task(self._periodic_integrity_sweep())
        
        logger.info(f"Started real-time integrity monitoring with {num_processors} processors")
    
    async def stop_realtime_monitoring(self):
        """Stop real-time integrity monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        self.metrics.realtime_checks_active = 0
        
        # Cancel monitor task
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Cancel processor tasks
        for processor in self.realtime_processors:
            processor.cancel()
        
        if self.realtime_processors:
            await asyncio.gather(*self.realtime_processors, return_exceptions=True)
        
        self.realtime_processors.clear()
        
        logger.info("Stopped real-time integrity monitoring")
    
    async def _realtime_processor(self, processor_id: str):
        """
        Real-time processor for integrity validation queue
        
        Args:
            processor_id: Unique identifier for this processor
        """
        logger.info(f"Real-time processor {processor_id} started")
        
        while self.monitoring_active:
            try:
                # Get next validation request
                try:
                    request = await asyncio.wait_for(
                        self.realtime_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process validation request
                if request['action'] == 'validate':
                    event_id = request['event_id']
                    event_data = request['event_data']
                    
                    # Perform validation in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        self.thread_pool,
                        self.validate_event_integrity,
                        event_id,
                        event_data
                    )
                
                # Mark task as done
                self.realtime_queue.task_done()
                
            except Exception as e:
                logger.error(f"Real-time processor {processor_id} error: {e}")
                await asyncio.sleep(0.1)
        
        logger.info(f"Real-time processor {processor_id} stopped")
    
    async def _periodic_integrity_sweep(self):
        """Periodic comprehensive integrity sweep of all monitored events"""
        logger.info("Started periodic integrity sweep")
        
        while self.monitoring_active:
            try:
                sweep_start = time.time()
                events_checked = 0
                
                # Check all registered events
                for event_id, expected_hash in list(self.event_hashes.items()):
                    if not self.monitoring_active:
                        break
                    
                    # Get original data for re-validation
                    if event_id in self.event_metadata:
                        original_data = self.event_metadata[event_id].get('original_data')
                        if original_data:
                            # Re-validate integrity
                            await asyncio.get_event_loop().run_in_executor(
                                self.thread_pool,
                                self.validate_event_integrity,
                                event_id,
                                original_data
                            )
                            events_checked += 1
                    
                    # Brief pause to avoid overwhelming system
                    if events_checked % 100 == 0:
                        await asyncio.sleep(0.01)
                
                sweep_duration = time.time() - sweep_start
                logger.info(f"Integrity sweep completed: {events_checked} events in {sweep_duration:.2f}s")
                
                # Wait before next sweep
                await asyncio.sleep(self.check_interval * 10)  # Full sweep every 10 check intervals
                
            except Exception as e:
                logger.error(f"Periodic integrity sweep error: {e}")
                await asyncio.sleep(self.check_interval)
        
        logger.info("Periodic integrity sweep stopped")
    
    def get_violations(self, 
                      unresolved_only: bool = False,
                      severity_filter: List[str] = None) -> List[IntegrityViolation]:
        """
        Get integrity violations with optional filtering
        
        Args:
            unresolved_only: Only return unresolved violations
            severity_filter: Filter by severity levels
            
        Returns:
            List of matching violations
        """
        violations = self.violations
        
        if unresolved_only:
            violations = [v for v in violations if not v.resolved]
        
        if severity_filter:
            violations = [v for v in violations if v.severity in severity_filter]
        
        return violations
    
    def resolve_violation(self, violation_id: str, resolution_notes: str = ""):
        """
        Mark violation as resolved
        
        Args:
            violation_id: ID of violation to resolve
            resolution_notes: Notes about how violation was resolved
        """
        for violation in self.violations:
            if violation.violation_id == violation_id:
                violation.resolved = True
                violation.resolution_notes = resolution_notes
                self.metrics.violations_resolved += 1
                self.metrics.calculate_integrity_score()
                
                logger.info(f"Resolved integrity violation {violation_id}: {resolution_notes}")
                return
        
        logger.warning(f"Violation {violation_id} not found for resolution")
    
    def get_integrity_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive integrity monitoring report
        
        Returns:
            Detailed integrity report
        """
        return {
            'monitoring_status': {
                'active': self.monitoring_active,
                'realtime_processors': self.metrics.realtime_checks_active,
                'check_interval': self.check_interval
            },
            'metrics': {
                'total_events_monitored': self.metrics.total_events_monitored,
                'violations_detected': self.metrics.violations_detected,
                'violations_resolved': self.metrics.violations_resolved,
                'hash_validations_performed': self.metrics.hash_validations_performed,
                'system_integrity_score': self.metrics.system_integrity_score,
                'last_violation': self.metrics.last_violation_detected.isoformat() if self.metrics.last_violation_detected else None
            },
            'violations_summary': {
                'total': len(self.violations),
                'unresolved': len([v for v in self.violations if not v.resolved]),
                'by_severity': {
                    'critical': len([v for v in self.violations if v.severity == 'critical']),
                    'high': len([v for v in self.violations if v.severity == 'high']),
                    'medium': len([v for v in self.violations if v.severity == 'medium']),
                    'low': len([v for v in self.violations if v.severity == 'low'])
                },
                'by_type': {vtype.value: len([v for v in self.violations if v.violation_type == vtype]) 
                          for vtype in IntegrityViolationType}
            },
            'recent_violations': [
                {
                    'violation_id': v.violation_id,
                    'type': v.violation_type.value,
                    'severity': v.severity,
                    'event_id': v.event_id,
                    'agent_id': v.agent_id,
                    'detected_at': v.detected_at.isoformat(),
                    'resolved': v.resolved
                }
                for v in sorted(self.violations, key=lambda x: x.detected_at, reverse=True)[:10]
            ]
        }


# Alert system implementations

def console_alert_handler(violation: IntegrityViolation):
    """Console alert handler for integrity violations"""
    print(f"\n🚨 INTEGRITY VIOLATION ALERT 🚨")
    print(f"Violation ID: {violation.violation_id}")
    print(f"Type: {violation.violation_type.value}")
    print(f"Severity: {violation.severity.upper()}")
    print(f"Event ID: {violation.event_id}")
    print(f"Agent ID: {violation.agent_id}")
    print(f"Detected: {violation.detected_at}")
    print(f"Expected Hash: {violation.expected_hash[:16]}...")
    print(f"Actual Hash: {violation.actual_hash[:16]}...")
    print("-" * 50)


def log_alert_handler(violation: IntegrityViolation):
    """Log file alert handler for integrity violations"""
    logger.critical(f"INTEGRITY VIOLATION: {violation.violation_id} | "
                   f"Type: {violation.violation_type.value} | "
                   f"Severity: {violation.severity} | "
                   f"Event: {violation.event_id} | "
                   f"Agent: {violation.agent_id} | "
                   f"Time: {violation.detected_at}")


# Example usage and testing
if __name__ == "__main__":
    async def demo_integrity_monitoring():
        print("🔐 Event Store Integrity Monitor Demo")
        
        # Create monitor with alert handlers
        monitor = EventStoreIntegrityMonitor(
            secret_key="demo_secret_key",
            alert_callbacks=[console_alert_handler, log_alert_handler],
            check_interval=0.5
        )
        
        # Start real-time monitoring
        await monitor.start_realtime_monitoring(num_processors=2)
        
        print("✅ Real-time monitoring started")
        
        # Register some test events
        test_events = [
            {'id': 'event_001', 'type': 'command_validated', 'agent': 'test_agent_1', 'data': 'test_data_1'},
            {'id': 'event_002', 'type': 'consensus_reached', 'agent': 'test_agent_2', 'data': 'test_data_2'},
            {'id': 'event_003', 'type': 'command_validated', 'agent': 'test_agent_1', 'data': 'test_data_3'},
        ]
        
        for event in test_events:
            monitor.register_event(event['id'], event, agent_id=event['agent'])
            print(f"📝 Registered event: {event['id']}")
        
        await asyncio.sleep(2)
        
        # Simulate integrity violation by modifying an event
        print("🔴 Simulating integrity violation...")
        tampered_event = test_events[1].copy()
        tampered_event['data'] = 'tampered_data!'
        
        # This will trigger a violation alert
        monitor.validate_event_integrity('event_002', tampered_event)
        
        await asyncio.sleep(1)
        
        # Generate integrity report
        print("\n📊 Integrity Report:")
        report = monitor.get_integrity_report()
        print(json.dumps(report, indent=2))
        
        # Stop monitoring
        await monitor.stop_realtime_monitoring()
        print("✅ Monitoring stopped")
    
    # Run demo
    asyncio.run(demo_integrity_monitoring())