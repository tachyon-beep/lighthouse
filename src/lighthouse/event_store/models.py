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
    
    # System events
    SYSTEM_STARTED = "system_started"
    SYSTEM_SHUTDOWN = "system_shutdown"
    DEGRADATION_TRIGGERED = "degradation_triggered"
    RECOVERY_COMPLETED = "recovery_completed"
    
    # Snapshot events
    SNAPSHOT_CREATED = "snapshot_created"
    SNAPSHOT_RESTORED = "snapshot_restored"


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