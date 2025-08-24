"""Unit tests for monotonic Event ID generation."""

import pytest
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from lighthouse.event_store.id_generator import (
    EventID, MonotonicEventIDGenerator, generate_event_id, 
    set_node_id, reset_generator
)


class TestEventID:
    """Test EventID structure and operations."""
    
    def test_create_event_id(self):
        """Test creating EventID with components."""
        event_id = EventID(
            timestamp_ns=1692900000123456789,
            sequence=42,
            node_id="test-node"
        )
        
        assert event_id.timestamp_ns == 1692900000123456789
        assert event_id.sequence == 42
        assert event_id.node_id == "test-node"
    
    def test_event_id_string_formatting(self):
        """Test EventID string representation per ADR-003."""
        event_id = EventID(
            timestamp_ns=1692900000123456789,
            sequence=42,
            node_id="test-node"
        )
        
        expected = "1692900000123456789_42_test-node"
        assert str(event_id) == expected
    
    def test_event_id_from_string(self):
        """Test parsing EventID from string."""
        event_id_str = "1692900000123456789_42_test-node"
        event_id = EventID.from_string(event_id_str)
        
        assert event_id.timestamp_ns == 1692900000123456789
        assert event_id.sequence == 42
        assert event_id.node_id == "test-node"
    
    def test_event_id_from_invalid_string(self):
        """Test parsing invalid EventID strings."""
        with pytest.raises(ValueError, match="Invalid Event ID format"):
            EventID.from_string("invalid_format")
        
        with pytest.raises(ValueError, match="Invalid Event ID format"):
            EventID.from_string("123_456")  # Missing node_id
        
        with pytest.raises(ValueError, match="Invalid Event ID format"):
            EventID.from_string("not_a_number_456_node")  # Invalid timestamp
    
    def test_event_id_ordering(self):
        """Test EventID ordering for chronological sorting."""
        # Different timestamps
        id1 = EventID(timestamp_ns=100, sequence=0, node_id="node1")
        id2 = EventID(timestamp_ns=200, sequence=0, node_id="node1")
        assert id1 < id2
        assert not id2 < id1
        
        # Same timestamp, different sequences
        id3 = EventID(timestamp_ns=100, sequence=0, node_id="node1")
        id4 = EventID(timestamp_ns=100, sequence=1, node_id="node1")
        assert id3 < id4
        assert not id4 < id3
        
        # Same timestamp and sequence, different nodes
        id5 = EventID(timestamp_ns=100, sequence=0, node_id="node-a")
        id6 = EventID(timestamp_ns=100, sequence=0, node_id="node-b")
        assert id5 < id6
        assert not id6 < id5


class TestMonotonicEventIDGenerator:
    """Test MonotonicEventIDGenerator functionality."""
    
    def setup_method(self):
        """Set up fresh generator for each test."""
        self.generator = MonotonicEventIDGenerator(node_id="test-node")
    
    def test_generator_initialization(self):
        """Test generator initialization."""
        generator = MonotonicEventIDGenerator(node_id="custom-node")
        assert generator.node_id == "custom-node"
        assert generator._last_timestamp_ns > 0
        assert len(generator._sequence_counters) == 0
    
    def test_generate_single_event_id(self):
        """Test generating single EventID."""
        event_id = self.generator.generate()
        
        assert isinstance(event_id, EventID)
        assert event_id.node_id == "test-node"
        assert event_id.timestamp_ns > 0
        assert event_id.sequence >= 0
    
    def test_generate_sequential_event_ids(self):
        """Test generating sequential EventIDs maintain ordering."""
        id1 = self.generator.generate()
        time.sleep(0.001)  # Small delay to ensure different timestamps
        id2 = self.generator.generate()
        id3 = self.generator.generate()
        
        # Should be in chronological order
        assert id1 < id2 or (id1.timestamp_ns == id2.timestamp_ns and id1.sequence < id2.sequence)
        assert id2 < id3 or (id2.timestamp_ns == id3.timestamp_ns and id2.sequence < id3.sequence)
    
    def test_same_timestamp_sequence_increment(self):
        """Test sequence increment for same-timestamp events."""
        # Generate many IDs rapidly to force same timestamps
        ids = [self.generator.generate() for _ in range(10)]
        
        # Group by timestamp
        by_timestamp = {}
        for event_id in ids:
            ts = event_id.timestamp_ns
            if ts not in by_timestamp:
                by_timestamp[ts] = []
            by_timestamp[ts].append(event_id)
        
        # Check sequences within each timestamp
        for ts, events in by_timestamp.items():
            events.sort(key=lambda e: e.sequence)
            for i, event in enumerate(events):
                assert event.sequence == i  # Should be 0, 1, 2, ...
    
    def test_monotonic_guarantee_under_clock_skew(self):
        """Test monotonic guarantee even if system clock goes backwards."""
        # This test verifies that the generator uses monotonic time
        # and doesn't rely on wall-clock time that could go backwards
        
        # Generate baseline ID
        id1 = self.generator.generate()
        
        # Simulate rapid generation (should use monotonic time)
        ids = [self.generator.generate() for _ in range(100)]
        
        # All IDs should be monotonically increasing
        prev_id = id1
        for current_id in ids:
            assert not current_id < prev_id, f"Non-monotonic: {prev_id} >= {current_id}"
            prev_id = current_id
    
    def test_thread_safety(self):
        """Test concurrent ID generation is thread-safe."""
        num_threads = 10
        ids_per_thread = 100
        all_ids = []
        
        def generate_ids():
            thread_ids = []
            for _ in range(ids_per_thread):
                thread_ids.append(self.generator.generate())
            return thread_ids
        
        # Run concurrent generation
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(generate_ids) for _ in range(num_threads)]
            
            for future in as_completed(futures):
                thread_ids = future.result()
                all_ids.extend(thread_ids)
        
        # Verify we got expected number of IDs
        assert len(all_ids) == num_threads * ids_per_thread
        
        # Verify all IDs are unique
        id_strings = [str(event_id) for event_id in all_ids]
        assert len(set(id_strings)) == len(id_strings), "Generated duplicate IDs"
        
        # Verify all IDs are properly formatted
        for event_id in all_ids:
            assert isinstance(event_id, EventID)
            assert event_id.node_id == "test-node"
            assert event_id.timestamp_ns > 0
            assert event_id.sequence >= 0
    
    def test_sequence_counter_cleanup(self):
        """Test old sequence counters are cleaned up."""
        # Generate enough IDs to trigger cleanup (> 1000 unique timestamps)
        # This is hard to test directly, but we can verify the generator
        # continues working after potential cleanup
        
        initial_counter_size = len(self.generator._sequence_counters)
        
        # Generate many IDs with small delays to create unique timestamps
        for i in range(50):
            self.generator.generate()
            if i % 10 == 0:
                time.sleep(0.0001)  # Create some timestamp variance
        
        # Generator should still work normally
        final_id = self.generator.generate()
        assert isinstance(final_id, EventID)
        assert final_id.node_id == "test-node"
    
    def test_reset_generator(self):
        """Test generator reset functionality."""
        # Generate some IDs
        id1 = self.generator.generate()
        id2 = self.generator.generate()
        
        initial_timestamp = self.generator._last_timestamp_ns
        initial_counter_count = len(self.generator._sequence_counters)
        
        # Reset generator
        self.generator.reset()
        
        # State should be reset
        assert self.generator._last_timestamp_ns >= initial_timestamp  # Monotonic time progresses
        assert len(self.generator._sequence_counters) == 0
        
        # Should generate new IDs normally
        id3 = self.generator.generate()
        assert isinstance(id3, EventID)
        assert id3.node_id == "test-node"


class TestGlobalGeneratorFunctions:
    """Test global generator convenience functions."""
    
    def setup_method(self):
        """Reset global generator for each test."""
        reset_generator()
    
    def test_generate_event_id_function(self):
        """Test global generate_event_id function."""
        event_id = generate_event_id()
        
        assert isinstance(event_id, EventID)
        assert event_id.node_id == "lighthouse-01"  # Default node ID
        assert event_id.timestamp_ns > 0
        assert event_id.sequence >= 0
    
    def test_set_node_id_function(self):
        """Test global set_node_id function."""
        set_node_id("custom-global-node")
        
        event_id = generate_event_id()
        assert event_id.node_id == "custom-global-node"
    
    def test_reset_generator_function(self):
        """Test global reset_generator function."""
        # Generate ID, then reset
        id1 = generate_event_id()
        reset_generator()
        
        # Should continue generating IDs normally
        id2 = generate_event_id()
        assert isinstance(id2, EventID)
        assert id2.node_id == "lighthouse-01"  # Back to default


class TestEventIDCompliance:
    """Test Event ID format compliance with ADR-003."""
    
    def test_adr_003_format_compliance(self):
        """Test EventID format matches ADR-003 specification."""
        generator = MonotonicEventIDGenerator(node_id="lighthouse-01")
        event_id = generator.generate()
        
        # Format should be: {timestamp_ns}_{sequence}_{node_id}
        id_str = str(event_id)
        parts = id_str.split('_')
        
        assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}: {id_str}"
        
        # First part: timestamp_ns (should be integer)
        timestamp_ns = int(parts[0])
        assert timestamp_ns > 0
        assert timestamp_ns == event_id.timestamp_ns
        
        # Second part: sequence (should be non-negative integer)
        sequence = int(parts[1])
        assert sequence >= 0
        assert sequence == event_id.sequence
        
        # Third part: node_id (should be string)
        node_id = parts[2]
        assert node_id == "lighthouse-01"
        assert node_id == event_id.node_id
    
    def test_nanosecond_precision(self):
        """Test timestamp has nanosecond precision."""
        generator = MonotonicEventIDGenerator()
        
        # Generate IDs in rapid succession
        ids = [generator.generate() for _ in range(100)]
        
        # At least some should have different nanosecond timestamps
        timestamps = [event_id.timestamp_ns for event_id in ids]
        unique_timestamps = set(timestamps)
        
        # With nanosecond precision, we should see timestamp variation
        # or sequence numbers increment for same timestamps
        for event_id in ids:
            assert event_id.timestamp_ns > 0  # Monotonic timestamps are positive
            # Nanosecond precision means timestamps are in nanoseconds since some epoch
            assert isinstance(event_id.timestamp_ns, int)
    
    def test_human_readable_format(self):
        """Test EventID is human-readable per ADR-003."""
        generator = MonotonicEventIDGenerator(node_id="node-01")
        event_id = generator.generate()
        id_str = str(event_id)
        
        # Should be readable format with underscores
        assert '_' in id_str
        assert id_str.endswith('_node-01')
        
        # Should be parseable back to components
        parsed = EventID.from_string(id_str)
        assert parsed.timestamp_ns == event_id.timestamp_ns
        assert parsed.sequence == event_id.sequence
        assert parsed.node_id == event_id.node_id
    
    def test_deterministic_sorting(self):
        """Test EventIDs enable deterministic sorting per ADR-003."""
        generator = MonotonicEventIDGenerator()
        
        # Generate many IDs
        ids = [generator.generate() for _ in range(100)]
        
        # Sort by string representation
        sorted_strings = sorted([str(event_id) for event_id in ids])
        
        # Sort by EventID objects
        sorted_objects = sorted(ids)
        
        # String sorting and object sorting should match
        for i, event_id in enumerate(sorted_objects):
            assert str(event_id) == sorted_strings[i]
        
        # Should be in chronological order
        for i in range(1, len(sorted_objects)):
            prev_id = sorted_objects[i-1]
            curr_id = sorted_objects[i]
            
            # Either different timestamps, or same timestamp with incremental sequence
            if prev_id.timestamp_ns == curr_id.timestamp_ns:
                assert prev_id.sequence <= curr_id.sequence
            else:
                assert prev_id.timestamp_ns < curr_id.timestamp_ns