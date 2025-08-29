"""Lighthouse: Multi-Agent Coordination Platform with Event-Sourced Foundation."""

__version__ = "1.0.0"

# Note: Bridge components are in the container, not on host
# MCP server on host doesn't need these imports
# They cause circular dependencies and require FUSE libraries

# Export main event store functionality (if needed)
# Commented out to prevent circular imports when loading MCP server
# from .event_store.store import EventStore, EventStoreError
# from .event_store.models import (
#     Event, EventType, EventBatch, EventFilter, EventQuery, 
#     QueryResult, SystemHealth, SnapshotMetadata
# )
# from .event_store.id_generator import EventID, generate_event_id, set_node_id
# from .event_store.auth import AgentRole, Permission, AgentIdentity
# from .event_store.validation import SecurityError

# Bridge runs in container, not imported on host
# from .bridge.main_bridge import LighthouseBridge

# Legacy compatibility - point to new architecture
def get_lighthouse_bridge(project_id: str, config: dict = None):
    """Get the main Lighthouse Bridge instance - runs in container"""
    raise NotImplementedError("Bridge runs in container, access via HTTP API at localhost:8765")

__all__ = [
    # Minimal exports to prevent circular imports
    "get_lighthouse_bridge",
    "__version__"
]