"""Lighthouse: Multi-Agent Coordination Platform with Event-Sourced Foundation."""

__version__ = "1.0.0"

# Export main event store functionality
from .event_store.store import EventStore, EventStoreError
from .event_store.models import (
    Event, EventType, EventBatch, EventFilter, EventQuery, 
    QueryResult, SystemHealth, SnapshotMetadata
)
from .event_store.id_generator import EventID, generate_event_id, set_node_id
from .event_store.auth import AgentRole, Permission, AgentIdentity
from .event_store.validation import SecurityError

# Import the new HLD Bridge architecture directly
from .bridge.main_bridge import LighthouseBridge

# Legacy compatibility - point to new architecture
def get_lighthouse_bridge(project_id: str, config: dict = None):
    """Get the main Lighthouse Bridge instance"""
    return LighthouseBridge(project_id, config or {})

__all__ = [
    # Core event store
    "EventStore", "EventStoreError", 
    # Event models
    "Event", "EventType", "EventBatch", "EventFilter", "EventQuery",
    "QueryResult", "SystemHealth", "SnapshotMetadata",
    # Event IDs
    "EventID", "generate_event_id", "set_node_id", 
    # Security
    "AgentRole", "Permission", "AgentIdentity", "SecurityError",
    # Main Bridge architecture
    "LighthouseBridge", "get_lighthouse_bridge"
]