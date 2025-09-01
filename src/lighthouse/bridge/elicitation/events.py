"""
Event-sourced elicitation events and projections.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Set, List
from enum import Enum
from datetime import datetime, timezone

from ...event_store import Event, EventType


class ElicitationEventType(str, Enum):
    """Elicitation-specific event types."""
    # Lifecycle events
    ELICITATION_REQUESTED = "elicitation_requested"
    ELICITATION_ACCEPTED = "elicitation_accepted"
    ELICITATION_DECLINED = "elicitation_declined"
    ELICITATION_CANCELLED = "elicitation_cancelled"
    ELICITATION_EXPIRED = "elicitation_expired"
    
    # State events
    ELICITATION_SCHEMA_VALIDATED = "elicitation_schema_validated"
    ELICITATION_DATA_RECEIVED = "elicitation_data_received"
    ELICITATION_NOTIFICATION_SENT = "elicitation_notification_sent"
    ELICITATION_NOTIFICATION_FAILED = "elicitation_notification_failed"
    
    # Security events
    ELICITATION_SIGNATURE_VERIFIED = "elicitation_signature_verified"
    ELICITATION_SECURITY_VIOLATION = "elicitation_security_violation"
    ELICITATION_RATE_LIMITED = "elicitation_rate_limited"
    
    # Snapshot events
    ELICITATION_SNAPSHOT_CREATED = "elicitation_snapshot_created"


@dataclass
class ElicitationCreatedEvent(Event):
    """Event fired when elicitation is created."""
    
    def __init__(self, request_data: Dict[str, Any]):
        super().__init__(
            event_type=EventType.CUSTOM,
            aggregate_id=request_data['id'],
            aggregate_type="elicitation",
            data={
                "elicitation_type": ElicitationEventType.ELICITATION_REQUESTED.value,
                "from_agent": request_data['from_agent'],
                "to_agent": request_data['to_agent'],
                "message": request_data['message'],
                "schema": request_data['schema'],
                "nonce": request_data['nonce'],
                "request_signature": request_data['request_signature'],
                "expected_response_key": request_data['expected_response_key'],
                "timeout_seconds": request_data['timeout_seconds'],
                "created_at": request_data['created_at'],
                "expires_at": request_data['expires_at'],
                "security_context": request_data['security_context']
            },
            source_component="elicitation_manager",
            source_agent=request_data['from_agent'],
            metadata={
                "schema_version": "1.0",
                "feature_pack": "FEATURE_PACK_0",
                "security_level": "HIGH"
            }
        )


@dataclass
class ElicitationRespondedEvent(Event):
    """Event fired when elicitation receives response."""
    
    def __init__(self, response_data: Dict[str, Any]):
        super().__init__(
            event_type=EventType.CUSTOM,
            aggregate_id=response_data['elicitation_id'],
            aggregate_type="elicitation",
            data={
                "elicitation_type": response_data['elicitation_type'],  # accepted/declined/cancelled
                "responding_agent": response_data['responding_agent'],
                "response_type": response_data['response_type'],
                "response_data": response_data.get('data'),
                "response_signature": response_data['response_signature'],
                "responded_at": response_data['responded_at'],
                "security_context": response_data.get('security_context', {})
            },
            source_component="elicitation_manager",
            source_agent=response_data['responding_agent'],
            causation_id=response_data.get('causation_id'),
            metadata={
                "schema_version": "1.0",
                "feature_pack": "FEATURE_PACK_0"
            }
        )


@dataclass
class ElicitationExpiredEvent(Event):
    """Event fired when elicitation expires."""
    
    def __init__(self, elicitation_id: str, expired_at: float):
        super().__init__(
            event_type=EventType.CUSTOM,
            aggregate_id=elicitation_id,
            aggregate_type="elicitation",
            data={
                "elicitation_type": ElicitationEventType.ELICITATION_EXPIRED.value,
                "expired_at": expired_at
            },
            source_component="elicitation_manager",
            source_agent="system",
            metadata={
                "schema_version": "1.0",
                "feature_pack": "FEATURE_PACK_0"
            }
        )


@dataclass
class ElicitationSecurityEvent(Event):
    """Event fired for security violations."""
    
    def __init__(self, violation_data: Dict[str, Any]):
        super().__init__(
            event_type=EventType.CUSTOM,
            aggregate_id=violation_data.get('elicitation_id', 'security'),
            aggregate_type="elicitation_security",
            data={
                "elicitation_type": ElicitationEventType.ELICITATION_SECURITY_VIOLATION.value,
                "violation_type": violation_data['violation_type'],
                "agent": violation_data['agent'],
                "severity": violation_data['severity'],
                "details": violation_data.get('details', {}),
                "timestamp": datetime.now(timezone.utc).timestamp()
            },
            source_component="elicitation_security",
            source_agent="security_monitor",
            metadata={
                "schema_version": "1.0",
                "feature_pack": "FEATURE_PACK_0",
                "alert_required": violation_data.get('severity') in ['HIGH', 'CRITICAL']
            }
        )


@dataclass
class ElicitationProjection:
    """Current state projection from events."""
    # Active elicitations by ID
    active_elicitations: Dict[str, Any] = field(default_factory=dict)
    
    # Completed elicitations by ID
    completed_elicitations: Dict[str, Any] = field(default_factory=dict)
    
    # Indices for fast lookup
    by_target_agent: Dict[str, Set[str]] = field(default_factory=dict)
    by_source_agent: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Security tracking
    nonces_used: Set[str] = field(default_factory=set)
    response_keys: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Metrics tracking
    total_requests: int = 0
    total_responses: int = 0
    total_timeouts: int = 0
    total_violations: int = 0
    
    # Sequence tracking
    last_sequence: int = 0
    snapshot_sequence: int = 0
    events_since_snapshot: int = 0
    
    def add_active(self, elicitation_id: str, request: Dict[str, Any]):
        """Add active elicitation to projection."""
        self.active_elicitations[elicitation_id] = request
        
        # Update indices
        to_agent = request['to_agent']
        from_agent = request['from_agent']
        
        if to_agent not in self.by_target_agent:
            self.by_target_agent[to_agent] = set()
        self.by_target_agent[to_agent].add(elicitation_id)
        
        if from_agent not in self.by_source_agent:
            self.by_source_agent[from_agent] = set()
        self.by_source_agent[from_agent].add(elicitation_id)
        
        # Track nonce and response key
        self.nonces_used.add(request['nonce'])
        self.response_keys[elicitation_id] = {
            'key': request['expected_response_key'],
            'to_agent': to_agent,
            'nonce': request['nonce']
        }
        
        self.total_requests += 1
    
    def complete_elicitation(self, elicitation_id: str, response_type: str):
        """Move elicitation to completed state."""
        if elicitation_id in self.active_elicitations:
            request = self.active_elicitations.pop(elicitation_id)
            request['status'] = response_type
            self.completed_elicitations[elicitation_id] = request
            
            # Clean up indices
            to_agent = request['to_agent']
            from_agent = request['from_agent']
            
            if to_agent in self.by_target_agent:
                self.by_target_agent[to_agent].discard(elicitation_id)
            if from_agent in self.by_source_agent:
                self.by_source_agent[from_agent].discard(elicitation_id)
            
            # Clean up security data
            if elicitation_id in self.response_keys:
                del self.response_keys[elicitation_id]
            
            if response_type in ['accepted', 'declined']:
                self.total_responses += 1
            elif response_type == 'expired':
                self.total_timeouts += 1
    
    def to_snapshot(self) -> Dict[str, Any]:
        """Convert projection to snapshot format."""
        return {
            'active_elicitations': self.active_elicitations,
            'completed_elicitations': self.completed_elicitations,
            'by_target_agent': {k: list(v) for k, v in self.by_target_agent.items()},
            'by_source_agent': {k: list(v) for k, v in self.by_source_agent.items()},
            'nonces_used': list(self.nonces_used),
            'response_keys': self.response_keys,
            'total_requests': self.total_requests,
            'total_responses': self.total_responses,
            'total_timeouts': self.total_timeouts,
            'total_violations': self.total_violations,
            'last_sequence': self.last_sequence,
            'snapshot_sequence': self.snapshot_sequence
        }
    
    @classmethod
    def from_snapshot(cls, snapshot_data: Dict[str, Any]) -> 'ElicitationProjection':
        """Restore projection from snapshot."""
        projection = cls()
        projection.active_elicitations = snapshot_data['active_elicitations']
        projection.completed_elicitations = snapshot_data['completed_elicitations']
        projection.by_target_agent = {k: set(v) for k, v in snapshot_data['by_target_agent'].items()}
        projection.by_source_agent = {k: set(v) for k, v in snapshot_data['by_source_agent'].items()}
        projection.nonces_used = set(snapshot_data['nonces_used'])
        projection.response_keys = snapshot_data['response_keys']
        projection.total_requests = snapshot_data['total_requests']
        projection.total_responses = snapshot_data['total_responses']
        projection.total_timeouts = snapshot_data['total_timeouts']
        projection.total_violations = snapshot_data['total_violations']
        projection.last_sequence = snapshot_data['last_sequence']
        projection.snapshot_sequence = snapshot_data['snapshot_sequence']
        return projection