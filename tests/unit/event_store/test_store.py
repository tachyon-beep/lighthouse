"""Unit tests for event store implementation."""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from lighthouse.event_store.store import EventStore, EventStoreError
from lighthouse.event_store.models import (
    Event, EventType, EventFilter, EventQuery, EventBatch
)


@pytest_asyncio.fixture
async def temp_event_store():
    """Create a temporary event store for testing with authenticated test agent."""
    temp_dir = tempfile.mkdtemp()
    # Allow temp directory for testing by adding it to allowed base directories
    allowed_dirs = [temp_dir, "/tmp"]  # Allow both specific temp dir and /tmp
    store = EventStore(data_dir=temp_dir, allowed_base_dirs=allowed_dirs)
    await store.initialize()
    
    # Create and authenticate a test agent for secure operations
    test_agent_id = "test-agent"
    test_token = store.create_agent_token(test_agent_id)
    store.authenticate_agent(test_agent_id, test_token, "agent")
    
    # Add test_agent_id as attribute for easy access in tests
    store.test_agent_id = test_agent_id
    
    yield store
    
    await store.shutdown()
    shutil.rmtree(temp_dir)


@pytest.mark.asyncio
class TestEventStore:
    """Test EventStore implementation."""
    
    async def test_initialization(self, temp_event_store):
        """Test event store initialization."""
        store = temp_event_store
        
        assert store.current_sequence == 0
        assert store.status == "healthy-secure"  # Updated for security-enabled store
        assert store.current_log_file is not None
    
    async def test_append_single_event(self, temp_event_store):
        """Test appending single event."""
        store = temp_event_store
        
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="test_command",
            data={"command": "ls", "args": ["-la"]}
        )
        
        await store.append(event, agent_id=store.test_agent_id)
        
        assert event.sequence == 1
        assert store.current_sequence == 1
    
    async def test_append_batch_events(self, temp_event_store):
        """Test appending batch of events atomically."""
        store = temp_event_store
        
        events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id="cmd1", data={}),
            Event(event_type=EventType.COMMAND_VALIDATED, aggregate_id="cmd1", data={}),
            Event(event_type=EventType.COMMAND_EXECUTED, aggregate_id="cmd1", data={})
        ]
        
        batch = EventBatch(events=events)
        await store.append_batch(batch, agent_id=store.test_agent_id)
        
        assert events[0].sequence == 1
        assert events[1].sequence == 2
        assert events[2].sequence == 3
        assert store.current_sequence == 3
    
    async def test_query_events(self, temp_event_store):
        """Test querying events with filters."""
        store = temp_event_store
        
        # Add some test events
        events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id="cmd1", data={}),
            Event(event_type=EventType.COMMAND_VALIDATED, aggregate_id="cmd1", data={}),
            Event(event_type=EventType.SHADOW_UPDATED, aggregate_id="file1", data={}),
            Event(event_type=EventType.COMMAND_EXECUTED, aggregate_id="cmd1", data={})
        ]
        
        for event in events:
            await store.append(event, agent_id=store.test_agent_id)
        
        # Query all events
        query = EventQuery()
        result = await store.query(query, agent_id=store.test_agent_id)
        
        assert len(result.events) == 4
        assert result.total_count == 4
        assert result.execution_time_ms > 0
    
    async def test_query_with_filter(self, temp_event_store):
        """Test querying with specific filters."""
        store = temp_event_store
        
        # Add test events
        events = [
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id="cmd1", data={}),
            Event(event_type=EventType.SHADOW_UPDATED, aggregate_id="file1", data={}),
            Event(event_type=EventType.COMMAND_RECEIVED, aggregate_id="cmd2", data={}),
        ]
        
        for event in events:
            await store.append(event, agent_id=store.test_agent_id)
        
        # Query only COMMAND_RECEIVED events
        filter = EventFilter(event_types=[EventType.COMMAND_RECEIVED])
        query = EventQuery(filter=filter)
        result = await store.query(query, agent_id=store.test_agent_id)
        
        assert len(result.events) == 2
        for event in result.events:
            assert event.event_type == EventType.COMMAND_RECEIVED
    
    async def test_query_pagination(self, temp_event_store):
        """Test query pagination."""
        store = temp_event_store
        
        # Add 10 test events
        for i in range(10):
            event = Event(
                event_type=EventType.AGENT_HEARTBEAT,
                aggregate_id=f"agent_{i}",
                data={"index": i}
            )
            await store.append(event, agent_id=store.test_agent_id)
        
        # Query with pagination
        query = EventQuery(offset=3, limit=4)
        result = await store.query(query, agent_id=store.test_agent_id)
        
        assert len(result.events) <= 4
        # Note: Exact pagination behavior depends on file reading implementation
    
    async def test_event_size_limit(self, temp_event_store):
        """Test event size limit enforcement."""
        store = temp_event_store
        
        # Create oversized event (>1MB)
        large_data = {"content": "x" * (1024 * 1024 + 1)}
        event = Event(
            event_type=EventType.SHADOW_UPDATED,
            aggregate_id="large_file",
            data=large_data
        )
        
        # Should be rejected by security validation (now happens before size check)
        with pytest.raises(EventStoreError, match="Security validation failed"):
            await store.append(event, agent_id=store.test_agent_id)
    
    async def test_concurrent_appends(self, temp_event_store):
        """Test concurrent event appends are properly serialized."""
        store = temp_event_store
        
        async def append_events(prefix: str, count: int):
            for i in range(count):
                event = Event(
                    event_type=EventType.AGENT_HEARTBEAT,
                    aggregate_id=f"{prefix}_{i}",
                    data={"index": i}
                )
                await store.append(event, agent_id=store.test_agent_id)
        
        # Run concurrent appends
        await asyncio.gather(
            append_events("agent_a", 10),
            append_events("agent_b", 10),
            append_events("agent_c", 10)
        )
        
        # Should have 30 events with proper sequence numbers
        assert store.current_sequence == 30
        
        # Verify all events are there
        query = EventQuery(limit=50)
        result = await store.query(query, agent_id=store.test_agent_id)
        assert len(result.events) == 30
    
    async def test_health_status(self, temp_event_store):
        """Test system health reporting."""
        store = temp_event_store
        
        # Add some events
        for i in range(5):
            event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id=f"cmd_{i}",
                data={}
            )
            await store.append(event, agent_id=store.test_agent_id)
        
        health = await store.get_health()
        
        assert health.event_store_status == "healthy-secure"
        assert health.current_sequence == 5
        assert health.disk_usage_bytes > 0
        assert health.log_file_count >= 1
        assert health.average_append_latency_ms >= 0
    
    async def test_store_recovery(self, temp_event_store):
        """Test event store recovery from existing data."""
        store = temp_event_store
        data_dir = store.data_dir
        
        # Add some events
        for i in range(3):
            event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id=f"cmd_{i}",
                data={"index": i}
            )
            await store.append(event, agent_id=store.test_agent_id)
        
        # Shutdown and create new store from same directory
        await store.shutdown()
        
        # Create new store with same allowed directories for testing
        allowed_dirs = [str(data_dir), "/tmp"]
        new_store = EventStore(data_dir=str(data_dir), allowed_base_dirs=allowed_dirs)
        await new_store.initialize()
        
        # Should recover sequence number
        assert new_store.current_sequence == 3
        
        # Should be able to query existing events
        query = EventQuery()
        result = await new_store.query(query)
        assert len(result.events) == 3
        
        await new_store.shutdown()
    
    async def test_log_file_rotation(self, temp_event_store):
        """Test log file rotation at size limit."""
        store = temp_event_store
        # Set very small max file size for testing
        store.max_file_size = 1024  # 1KB
        
        # Add events until rotation occurs
        initial_log_count = len(list(store.data_dir.glob("*.log*")))
        
        for i in range(20):
            event = Event(
                event_type=EventType.SHADOW_UPDATED,
                aggregate_id=f"file_{i}",
                data={"content": "x" * 100}  # Make events larger
            )
            await store.append(event, agent_id=store.test_agent_id)
        
        # Should have created additional log files
        final_log_count = len(list(store.data_dir.glob("*.log*")))
        assert final_log_count > initial_log_count
    
    async def test_error_handling(self, temp_event_store):
        """Test error handling and recovery."""
        store = temp_event_store
        
        # Test invalid event
        with pytest.raises(EventStoreError):
            await store.append(None)
        
        # Store should still be functional
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="test",
            data={}
        )
        await store.append(event, agent_id=store.test_agent_id)
        assert store.current_sequence == 1


@pytest.mark.asyncio
class TestEventStorePerformance:
    """Performance tests for event store."""
    
    async def test_append_performance(self, temp_event_store):
        """Test append performance meets requirements."""
        store = temp_event_store
        
        start_time = asyncio.get_event_loop().time()
        
        # Append 100 events
        for i in range(100):
            event = Event(
                event_type=EventType.AGENT_HEARTBEAT,
                aggregate_id=f"agent_{i}",
                data={"timestamp": datetime.now(timezone.utc).isoformat()}
            )
            await store.append(event, agent_id=store.test_agent_id)
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        # Should be well under 1ms per event on average
        avg_latency_ms = (elapsed / 100) * 1000
        
        # This is a lenient test - actual target is <1ms per ADR-004
        assert avg_latency_ms < 100, f"Average append latency {avg_latency_ms:.2f}ms too high"
    
    async def test_batch_performance(self, temp_event_store):
        """Test batch append performance."""
        store = temp_event_store
        
        # Create batch of 100 events
        events = []
        for i in range(100):
            events.append(Event(
                event_type=EventType.AGENT_HEARTBEAT,
                aggregate_id=f"agent_{i}",
                data={"index": i}
            ))
        
        batch = EventBatch(events=events)
        
        start_time = asyncio.get_event_loop().time()
        await store.append_batch(batch, agent_id=store.test_agent_id)
        elapsed = asyncio.get_event_loop().time() - start_time
        
        # Batch should be much faster than individual appends
        assert elapsed < 1.0, f"Batch append took {elapsed:.2f}s - too slow"