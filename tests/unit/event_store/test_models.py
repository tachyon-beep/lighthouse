"""Unit tests for event store models."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID
import msgpack

from lighthouse.event_store.models import (
    Event, EventType, EventFilter, EventQuery, EventBatch, 
    QueryResult, SnapshotMetadata
)
from lighthouse.event_store.id_generator import EventID


class TestEvent:
    """Test Event model."""
    
    def test_create_basic_event(self):
        """Test creating a basic event."""
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="test_agent_1",
            aggregate_type="agent",
            data={"command": "ls -la"}
        )
        
        assert event.event_type == EventType.COMMAND_RECEIVED
        assert event.aggregate_id == "test_agent_1"
        assert event.aggregate_type == "agent"
        assert event.data["command"] == "ls -la"
        assert isinstance(event.event_id, EventID)
        assert event.event_id.node_id == "lighthouse-01"
        assert event.event_id.timestamp_ns > 0
        assert event.event_id.sequence >= 0
        assert event.sequence is None  # Not assigned yet
        assert event.schema_version == 1
    
    def test_event_serialization_msgpack(self):
        """Test MessagePack serialization per ADR-002."""
        event = Event(
            event_type=EventType.SHADOW_UPDATED,
            aggregate_id="main.py",
            aggregate_type="file",
            data={"path": "/src/main.py", "size": 1024},
            metadata={"editor": "vim"}
        )
        
        # Serialize to MessagePack
        packed = event.to_msgpack()
        assert isinstance(packed, bytes)
        
        # Deserialize back
        restored = Event.from_msgpack(packed)
        
        assert restored.event_type == event.event_type
        assert restored.aggregate_id == event.aggregate_id
        assert restored.data == event.data
        assert restored.metadata == event.metadata
        assert restored.timestamp == event.timestamp
    
    def test_event_size_calculation(self):
        """Test event size calculation."""
        small_event = Event(
            event_type=EventType.AGENT_HEARTBEAT,
            aggregate_id="agent_1",
            data={"status": "ok"}
        )
        
        large_event = Event(
            event_type=EventType.SHADOW_UPDATED,
            aggregate_id="large_file.py",
            data={"content": "x" * 1000}
        )
        
        assert small_event.size_bytes < large_event.size_bytes
        assert large_event.size_bytes > 1000
    
    def test_event_validation_non_serializable_data(self):
        """Test validation of non-serializable data."""
        with pytest.raises(ValueError, match="must be MessagePack serializable"):
            Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id="test",
                data={"function": lambda x: x}  # Functions not serializable
            )


class TestEventFilter:
    """Test EventFilter model."""
    
    def test_empty_filter(self):
        """Test empty filter (matches all)."""
        filter = EventFilter()
        
        assert filter.event_types is None
        assert filter.aggregate_ids is None
        assert filter.after_timestamp is None
    
    def test_filter_with_criteria(self):
        """Test filter with specific criteria."""
        filter = EventFilter(
            event_types=[EventType.COMMAND_RECEIVED, EventType.COMMAND_EXECUTED],
            aggregate_ids=["agent_1", "agent_2"],
            after_sequence=100
        )
        
        assert EventType.COMMAND_RECEIVED in filter.event_types
        assert "agent_1" in filter.aggregate_ids
        assert filter.after_sequence == 100


class TestEventQuery:
    """Test EventQuery model."""
    
    def test_default_query(self):
        """Test default query parameters."""
        query = EventQuery()
        
        assert query.offset == 0
        assert query.limit == 1000
        assert query.order_by == "sequence"
        assert query.ascending is True
        assert query.include_data is True
        assert query.include_metadata is False
    
    def test_query_with_filter(self):
        """Test query with custom filter."""
        filter = EventFilter(event_types=[EventType.SHADOW_UPDATED])
        query = EventQuery(
            filter=filter,
            offset=50,
            limit=100,
            order_by="timestamp",
            ascending=False
        )
        
        assert query.filter.event_types == [EventType.SHADOW_UPDATED]
        assert query.offset == 50
        assert query.limit == 100
        assert query.order_by == "timestamp"
        assert query.ascending is False


class TestEventBatch:
    """Test EventBatch model."""
    
    def test_create_batch(self):
        """Test creating event batch."""
        events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id="1", data={}),
            Event(event_type=EventType.COMMAND_VALIDATED, aggregate_id="1", data={}),
            Event(event_type=EventType.COMMAND_EXECUTED, aggregate_id="1", data={})
        ]
        
        batch = EventBatch(events=events)
        
        assert len(batch.events) == 3
        assert isinstance(batch.batch_id, UUID)
        assert batch.correlation_id is None
    
    def test_empty_batch_validation(self):
        """Test validation of empty batch."""
        with pytest.raises(ValueError, match="Batch cannot be empty"):
            EventBatch(events=[])
    
    def test_large_batch_validation(self):
        """Test validation of oversized batch."""
        # Create batch with too many events
        events = []
        for i in range(1001):  # Exceeds 1000 limit
            events.append(Event(
                event_type=EventType.AGENT_HEARTBEAT,
                aggregate_id=f"agent_{i}",
                data={}
            ))
        
        with pytest.raises(ValueError, match="cannot exceed 1000 events"):
            EventBatch(events=events)
    
    def test_batch_size_limit(self):
        """Test batch size limit validation."""
        # Create batch that exceeds 10MB - make each event much larger
        large_data = {"content": "x" * (50 * 1024)}  # 50KB per event
        events = []
        for i in range(250):  # 250 * 50KB = ~12.5MB total
            events.append(Event(
                event_type=EventType.SHADOW_UPDATED,
                aggregate_id=f"file_{i}",
                data=large_data
            ))
        
        with pytest.raises(ValueError, match="exceeds 10MB limit"):
            EventBatch(events=events)


class TestQueryResult:
    """Test QueryResult model."""
    
    def test_query_result_creation(self):
        """Test creating query result."""
        events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id="1", data={}),
            Event(event_type=EventType.COMMAND_EXECUTED, aggregate_id="1", data={})
        ]
        
        query = EventQuery(limit=10)
        result = QueryResult(
            events=events,
            total_count=100,
            has_more=True,
            query=query,
            execution_time_ms=15.5
        )
        
        assert len(result.events) == 2
        assert result.total_count == 100
        assert result.has_more is True
        assert result.execution_time_ms == 15.5


class TestSnapshotMetadata:
    """Test SnapshotMetadata model."""
    
    def test_snapshot_metadata_creation(self):
        """Test creating snapshot metadata."""
        metadata = SnapshotMetadata(
            aggregate_type="bridge_state",
            event_sequence=12345,
            event_count=12345,
            checksum="abc123",
            size_bytes=1024 * 1024
        )
        
        assert metadata.aggregate_type == "bridge_state"
        assert metadata.event_sequence == 12345
        assert metadata.format_version == 1
        assert metadata.compression == "gzip"
        assert metadata.is_incremental is False
        assert isinstance(metadata.created_at, datetime)
    
    def test_incremental_snapshot(self):
        """Test incremental snapshot metadata."""
        base_id = uuid4()
        metadata = SnapshotMetadata(
            aggregate_type="agent_state",
            event_sequence=5000,
            event_count=1000,
            checksum="def456",
            size_bytes=512 * 1024,
            is_incremental=True,
            base_snapshot_id=base_id
        )
        
        assert metadata.is_incremental is True
        assert metadata.base_snapshot_id == base_id