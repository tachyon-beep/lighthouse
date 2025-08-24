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

# Legacy components available via lazy import to avoid broken dependencies
def get_server_main():
    """Lazy import of server main to avoid broken dependencies"""
    from .server import main
    return main

def get_validation_bridge():
    """Lazy import of ValidationBridge to avoid broken dependencies"""
    from .bridge import ValidationBridge
    return ValidationBridge

def get_command_validator():
    """Lazy import of CommandValidator to avoid broken dependencies"""
    from .validator import CommandValidator
    return CommandValidator

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
    # Legacy component access
    "get_server_main", "get_validation_bridge", "get_command_validator"
]