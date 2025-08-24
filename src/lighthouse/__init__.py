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

# Legacy MCP server components (maintained for backward compatibility)
from .server import main as server_main
from .bridge import ValidationBridge
from .validator import CommandValidator

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
    # Legacy components
    "server_main", "ValidationBridge", "CommandValidator"
]