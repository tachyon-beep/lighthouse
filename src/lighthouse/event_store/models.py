"""Event Store data models and schemas."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

import msgpack
from pydantic import BaseModel, Field, computed_field, field_validator

from .id_generator import EventID, generate_event_id


class EventType(str, Enum):
    """Standard event types for Lighthouse system."""
    
    # Bridge events
    COMMAND_RECEIVED = "command_received"
    COMMAND_VALIDATED = "command_validated"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_FAILED = "command_failed"
    
    # Agent events
    AGENT_REGISTERED = "agent_registered"
    AGENT_DISCONNECTED = "agent_disconnected"
    AGENT_HEARTBEAT = "agent_heartbeat"
    
    # Shadow filesystem events  
    SHADOW_UPDATED = "shadow_updated"
    SHADOW_CREATED = "shadow_created"
    SHADOW_DELETED = "shadow_deleted"
    
    # File operations (from Bridge)
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_MOVED = "file_moved"
    FILE_COPIED = "file_copied"
    
    # Directory operations (from Bridge)
    DIRECTORY_CREATED = "directory_created"
    DIRECTORY_DELETED = "directory_deleted"
    DIRECTORY_MOVED = "directory_moved"
    
    # Validation operations (from Bridge)
    VALIDATION_REQUEST_SUBMITTED = "validation_request_submitted"
    VALIDATION_POLICY_APPLIED = "validation_policy_applied"
    VALIDATION_ESCALATED_TO_EXPERT = "validation_escalated_to_expert"
    VALIDATION_DECISION_MADE = "validation_decision_made"
    
    # Agent session events (from Bridge)
    AGENT_SESSION_STARTED = "agent_session_started"
    AGENT_SESSION_ENDED = "agent_session_ended"
    EXPERT_AGENT_SUMMONED = "expert_agent_summoned"
    EXPERT_AGENT_RESPONDED = "expert_agent_responded"
    
    # Pair programming events (from Bridge)
    PAIR_SESSION_STARTED = "pair_session_started"
    PAIR_SESSION_ENDED = "pair_session_ended"
    PAIR_SUGGESTION_MADE = "pair_suggestion_made"
    PAIR_SUGGESTION_ACCEPTED = "pair_suggestion_accepted"
    PAIR_SUGGESTION_REJECTED = "pair_suggestion_rejected"
    
    # Shadow annotations (from Bridge)
    SHADOW_ANNOTATION_CREATED = "shadow_annotation_created"
    SHADOW_ANNOTATION_UPDATED = "shadow_annotation_updated"
    SHADOW_ANNOTATION_DELETED = "shadow_annotation_deleted"
    
    # System events
    SYSTEM_STARTED = "system_started"
    SYSTEM_SHUTDOWN = "system_shutdown"
    DEGRADATION_TRIGGERED = "degradation_triggered"
    RECOVERY_COMPLETED = "recovery_completed"
    PROJECT_INITIALIZED = "project_initialized"
    BACKUP_CREATED = "backup_created"
    
    # Snapshot events
    SNAPSHOT_CREATED = "snapshot_created"
    SNAPSHOT_RESTORED = "snapshot_restored"
    
    # Custom events for extensions
    CUSTOM = "custom"  # For feature-specific events like elicitation


class Event(BaseModel):
    """Core event model for all Lighthouse events."""
    
    # Unique identifiers
    event_id: EventID = Field(default_factory=generate_event_id)
    sequence: Optional[int] = None  # Assigned by event store
    
    # Event metadata
    event_type: EventType
    aggregate_id: str  # Entity this event relates to
    aggregate_type: str = Field(default="unknown")
    
    # Timing
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Causality and correlation
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None  # Event that caused this event
    
    # Event payload
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Source information
    source_agent: Optional[str] = None
    source_component: str = Field(default="unknown")
    
    # Schema version for evolution
    schema_version: int = Field(default=1)
    
    @field_validator('data', 'metadata')
    @classmethod
    def validate_serializable(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure data is MessagePack serializable."""
        try:
            # Test serialization
            msgpack.packb(v, use_bin_type=True)
            return v
        except (TypeError, ValueError) as e:
            raise ValueError(f"Data must be MessagePack serializable: {e}")
    
    def calculate_size_bytes(self) -> int:
        """Calculate approximate event size in bytes."""
        # Use basic string representation to avoid recursion
        basic_data = {
            "event_type": self.event_type.value,
            "aggregate_id": self.aggregate_id,
            "data": self.data,
            "metadata": self.metadata
        }
        return len(str(basic_data).encode('utf-8'))
    
    @property
    def size_bytes(self) -> int:
        """Get approximate event size in bytes."""
        return self.calculate_size_bytes()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization (Bridge compatibility)"""
        return {
            'event_id': str(self.event_id),
            'event_type': self.event_type.value,
            'aggregate_id': self.aggregate_id,
            'aggregate_type': self.aggregate_type,
            'sequence': self.sequence,
            'data': self.data,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat(),
            'source_agent': self.source_agent,
            'source_component': self.source_component,
            'correlation_id': str(self.correlation_id) if self.correlation_id else None,
            'causation_id': str(self.causation_id) if self.causation_id else None,
            'schema_version': self.schema_version
        }
    
    def is_file_operation(self) -> bool:
        """Check if this is a file operation event (Bridge compatibility)"""
        return self.event_type in [
            EventType.FILE_CREATED,
            EventType.FILE_MODIFIED,
            EventType.FILE_DELETED,
            EventType.FILE_MOVED,
            EventType.FILE_COPIED
        ]
    
    def is_validation_operation(self) -> bool:
        """Check if this is a validation operation event (Bridge compatibility)"""
        return self.event_type in [
            EventType.VALIDATION_REQUEST_SUBMITTED,
            EventType.VALIDATION_POLICY_APPLIED,
            EventType.VALIDATION_ESCALATED_TO_EXPERT,
            EventType.VALIDATION_DECISION_MADE
        ]
    
    def get_file_path(self) -> Optional[str]:
        """Get file path from file operation events (Bridge compatibility)"""
        if self.is_file_operation():
            return self.data.get('path') or self.data.get('file_path')
        return None
    
    def to_msgpack(self) -> bytes:
        """Serialize event to MessagePack for storage."""
        data = self.model_dump(exclude_unset=True)
        # Convert datetime and EventID to serializable formats
        data['timestamp'] = self.timestamp.isoformat()
        data['event_id'] = str(self.event_id)
        return msgpack.packb(data, use_bin_type=True)
    
    @classmethod  
    def from_msgpack(cls, data: bytes) -> 'Event':
        """Deserialize event from MessagePack."""
        raw_data = msgpack.unpackb(data, raw=False)
        # Convert ISO string back to datetime
        if 'timestamp' in raw_data:
            raw_data['timestamp'] = datetime.fromisoformat(raw_data['timestamp'])
        # Convert string back to EventID
        if 'event_id' in raw_data and isinstance(raw_data['event_id'], str):
            raw_data['event_id'] = EventID.from_string(raw_data['event_id'])
        return cls(**raw_data)


class EventFilter(BaseModel):
    """Filter criteria for event queries."""
    
    # Basic filters
    event_types: Optional[List[EventType]] = None
    exclude_event_types: Optional[List[EventType]] = None
    aggregate_ids: Optional[List[str]] = None
    aggregate_types: Optional[List[str]] = None
    source_agents: Optional[List[str]] = None
    source_components: Optional[List[str]] = None
    
    # Time range filters
    after_timestamp: Optional[datetime] = None
    before_timestamp: Optional[datetime] = None
    after_sequence: Optional[int] = None
    before_sequence: Optional[int] = None
    
    # Correlation filters
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None
    
    # Data filters (simple key-value matching)
    data_contains: Optional[Dict[str, Any]] = None
    metadata_contains: Optional[Dict[str, Any]] = None
    
    # Bridge compatibility filters
    agent_ids: Optional[List[str]] = None
    agent_types: Optional[List[str]] = None
    session_ids: Optional[List[str]] = None
    metadata_filter: Optional[Dict[str, Any]] = None
    correlation_ids: Optional[List[UUID]] = None
    file_paths: Optional[List[str]] = None
    file_path_patterns: Optional[List[str]] = None
    
    # Pagination
    limit: Optional[int] = None
    offset: Optional[int] = 0
    
    def matches_event(self, event: Event) -> bool:
        """Check if event matches this filter (Bridge compatibility)"""
        
        # Event type filtering
        if self.event_types and event.event_type not in self.event_types:
            return False
        
        if self.exclude_event_types and event.event_type in self.exclude_event_types:
            return False
        
        # Aggregate filtering
        if self.aggregate_ids and event.aggregate_id not in self.aggregate_ids:
            return False
        
        # Time filtering
        if self.after_timestamp and event.timestamp < self.after_timestamp:
            return False
        
        if self.before_timestamp and event.timestamp > self.before_timestamp:
            return False
        
        if self.after_sequence and (event.sequence is None or event.sequence <= self.after_sequence):
            return False
        
        if self.before_sequence and (event.sequence is None or event.sequence >= self.before_sequence):
            return False
        
        # Agent filtering (Bridge compatibility)
        agent_id = event.source_agent or event.metadata.get('agent_id')
        if self.agent_ids and agent_id not in self.agent_ids:
            return False
        
        if self.agent_types and event.metadata.get('agent_type') not in self.agent_types:
            return False
        
        session_id = event.metadata.get('session_id')
        if self.session_ids and session_id not in self.session_ids:
            return False
        
        # Metadata filtering
        if self.metadata_filter:
            for key, expected_value in self.metadata_filter.items():
                if key not in event.metadata or event.metadata[key] != expected_value:
                    return False
        
        # Correlation filtering
        if self.correlation_ids and event.correlation_id not in self.correlation_ids:
            return False
        
        # File path filtering
        if self.file_paths or self.file_path_patterns:
            file_path = event.get_file_path()
            if not file_path:
                return False
            
            if self.file_paths and file_path not in self.file_paths:
                return False
            
            if self.file_path_patterns:
                import fnmatch
                pattern_match = any(
                    fnmatch.fnmatch(file_path, pattern) 
                    for pattern in self.file_path_patterns
                )
                if not pattern_match:
                    return False
        
        return True


class EventQuery(BaseModel):
    """Query specification for retrieving events."""
    
    filter: EventFilter = Field(default_factory=EventFilter)
    
    # Pagination
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=1000, ge=1, le=10000)
    
    # Ordering
    order_by: str = Field(default="sequence")  # sequence, timestamp
    ascending: bool = Field(default=True)
    
    # Query options
    include_data: bool = Field(default=True)
    include_metadata: bool = Field(default=False)


class EventBatch(BaseModel):
    """Batch of events for atomic operations."""
    
    events: List[Event]
    batch_id: UUID = Field(default_factory=uuid4)
    correlation_id: Optional[UUID] = None
    
    @field_validator('events')
    @classmethod
    def validate_batch_size(cls, events: List[Event]) -> List[Event]:
        """Validate batch constraints."""
        if not events:
            raise ValueError("Batch cannot be empty")
        
        if len(events) > 1000:
            raise ValueError("Batch cannot exceed 1000 events")
        
        # Calculate total size
        total_size = sum(event.calculate_size_bytes() for event in events)
        if total_size > 10 * 1024 * 1024:  # 10MB
            raise ValueError(f"Batch size {total_size} exceeds 10MB limit")
        
        return events


class QueryResult(BaseModel):
    """Result of an event query."""
    
    events: List[Event]
    total_count: int
    has_more: bool
    query: EventQuery
    execution_time_ms: float


class SnapshotMetadata(BaseModel):
    """Metadata for state snapshots."""
    
    snapshot_id: UUID = Field(default_factory=uuid4)
    aggregate_type: str
    aggregate_id: Optional[str] = None  # None for global snapshots
    
    # Snapshot timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_sequence: int  # Last event included in snapshot
    event_count: int     # Total events processed
    
    # Snapshot characteristics
    format_version: int = Field(default=1)
    compression: str = Field(default="gzip")
    checksum: str        # SHA-256 hash of snapshot data
    size_bytes: int
    
    # Snapshot lifecycle
    expires_at: Optional[datetime] = None
    is_incremental: bool = Field(default=False)
    base_snapshot_id: Optional[UUID] = None  # For incremental snapshots


class SystemHealth(BaseModel):
    """System health status for monitoring."""
    
    # Event store health
    event_store_status: str  # healthy, degraded, failed
    current_sequence: int
    events_per_second: float
    
    # Storage health
    disk_usage_bytes: int
    disk_free_bytes: int
    log_file_count: int
    
    # Performance metrics
    average_append_latency_ms: float
    average_query_latency_ms: float
    
    # Error rates
    append_error_rate: float
    query_error_rate: float
    
    # Last health check
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Type aliases for convenience
AggregateID = str
SequenceNumber = int