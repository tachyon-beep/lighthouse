"""Lighthouse Event Store - Secure, high-performance event sourcing foundation."""

from .store import EventStore, EventStoreError
from .sqlite_store import SQLiteEventStore, SQLiteEventStoreError
from .models import (
    Event, EventType, EventBatch, EventFilter, EventQuery,
    QueryResult, SystemHealth, SnapshotMetadata
)
from .id_generator import EventID, generate_event_id, set_node_id, reset_generator
from .auth import (
    SimpleAuthenticator, Authorizer, AgentIdentity, AgentRole, Permission,
    AuthenticationError, AuthorizationError, create_system_authenticator
)
from .validation import (
    PathValidator, InputValidator, ResourceLimiter, SecurityError
)
from .api import EventStoreAPI, create_api_server, run_server
from .replay import EventReplayEngine, ReplayError, reconstruct_aggregate_state, get_historical_snapshot
from .snapshots import SnapshotManager, SnapshotError, AutoSnapshotManager

__all__ = [
    # Core event store
    "EventStore", "EventStoreError", "SQLiteEventStore", "SQLiteEventStoreError",
    # Event models
    "Event", "EventType", "EventBatch", "EventFilter", "EventQuery", 
    "QueryResult", "SystemHealth", "SnapshotMetadata",
    # Event ID generation
    "EventID", "generate_event_id", "set_node_id", "reset_generator",
    # Authentication & Authorization
    "SimpleAuthenticator", "Authorizer", "AgentIdentity", "AgentRole", "Permission",
    "AuthenticationError", "AuthorizationError", "create_system_authenticator",
    # Security & Validation
    "PathValidator", "InputValidator", "ResourceLimiter", "SecurityError",
    # HTTP/WebSocket API
    "EventStoreAPI", "create_api_server", "run_server",
    # Event Replay
    "EventReplayEngine", "ReplayError", "reconstruct_aggregate_state", "get_historical_snapshot",
    # Snapshot Management
    "SnapshotManager", "SnapshotError", "AutoSnapshotManager"
]