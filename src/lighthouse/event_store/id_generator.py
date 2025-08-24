"""Monotonic Event ID generation for Lighthouse event store."""

import time
import threading
from typing import Dict
from dataclasses import dataclass


@dataclass
class EventID:
    """Structured Event ID with monotonic timestamp, sequence, and node components."""
    
    timestamp_ns: int
    sequence: int
    node_id: str
    
    def __str__(self) -> str:
        """Format as string: timestamp_ns_sequence_node_id"""
        return f"{self.timestamp_ns}_{self.sequence}_{self.node_id}"
    
    @classmethod
    def from_string(cls, event_id_str: str) -> 'EventID':
        """Parse Event ID from string format."""
        try:
            parts = event_id_str.split('_')
            if len(parts) != 3:
                raise ValueError(f"Invalid Event ID format: {event_id_str}")
            
            return cls(
                timestamp_ns=int(parts[0]),
                sequence=int(parts[1]),
                node_id=parts[2]
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid Event ID format: {event_id_str}") from e
    
    def __lt__(self, other: 'EventID') -> bool:
        """Compare Event IDs for ordering."""
        if self.timestamp_ns != other.timestamp_ns:
            return self.timestamp_ns < other.timestamp_ns
        if self.sequence != other.sequence:
            return self.sequence < other.sequence
        return self.node_id < other.node_id


class MonotonicEventIDGenerator:
    """Thread-safe monotonic Event ID generator.
    
    Generates Event IDs with format: {timestamp_ns}_{sequence}_{node_id}
    - Uses monotonic clock to prevent time travel during system clock adjustments
    - Maintains per-timestamp sequence counters for same-timestamp events
    - Thread-safe for concurrent ID generation
    """
    
    def __init__(self, node_id: str = "lighthouse-01"):
        """Initialize generator with node identifier.
        
        Args:
            node_id: Unique identifier for this node (for future distributed deployment)
        """
        self.node_id = node_id
        self._lock = threading.Lock()
        self._last_timestamp_ns = 0
        self._sequence_counters: Dict[int, int] = {}
        
        # Initialize with current monotonic time
        self._last_timestamp_ns = self._get_monotonic_timestamp_ns()
    
    def _get_monotonic_timestamp_ns(self) -> int:
        """Get monotonic timestamp in nanoseconds.
        
        Uses time.monotonic_ns() to prevent backwards time movement
        during NTP adjustments or system clock changes.
        """
        return time.monotonic_ns()
    
    def generate(self) -> EventID:
        """Generate next Event ID with monotonic ordering guarantee.
        
        Returns:
            EventID with monotonic timestamp, sequence number, and node ID
        """
        with self._lock:
            current_timestamp_ns = self._get_monotonic_timestamp_ns()
            
            # Ensure monotonic progress - never go backwards
            if current_timestamp_ns <= self._last_timestamp_ns:
                current_timestamp_ns = self._last_timestamp_ns + 1
            
            # Get or initialize sequence for this timestamp
            if current_timestamp_ns not in self._sequence_counters:
                self._sequence_counters[current_timestamp_ns] = 0
            else:
                self._sequence_counters[current_timestamp_ns] += 1
            
            sequence = self._sequence_counters[current_timestamp_ns]
            
            # Clean up old sequence counters to prevent memory growth
            # Keep only recent timestamps (last 1000 unique timestamps)
            if len(self._sequence_counters) > 1000:
                old_timestamps = sorted(self._sequence_counters.keys())[:-1000]
                for old_ts in old_timestamps:
                    del self._sequence_counters[old_ts]
            
            self._last_timestamp_ns = current_timestamp_ns
            
            return EventID(
                timestamp_ns=current_timestamp_ns,
                sequence=sequence,
                node_id=self.node_id
            )
    
    def reset(self) -> None:
        """Reset generator state (primarily for testing)."""
        with self._lock:
            self._last_timestamp_ns = self._get_monotonic_timestamp_ns()
            self._sequence_counters.clear()


# Global generator instance - can be overridden for testing or distributed deployment
_default_generator = MonotonicEventIDGenerator()


def generate_event_id() -> EventID:
    """Generate Event ID using default generator."""
    return _default_generator.generate()


def set_node_id(node_id: str) -> None:
    """Set node ID for default generator."""
    global _default_generator
    _default_generator = MonotonicEventIDGenerator(node_id)


def reset_generator() -> None:
    """Reset default generator (primarily for testing)."""
    global _default_generator
    _default_generator = MonotonicEventIDGenerator()