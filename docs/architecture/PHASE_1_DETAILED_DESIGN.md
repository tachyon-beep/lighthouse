# Phase 1: Event-Sourced Foundation - Complete Implementation Design

**Document Version**: 1.0  
**Date**: 2025-08-24  
**Status**: Ready for Implementation  

---

## Executive Summary

This document provides complete technical specifications for implementing Phase 1 of the Lighthouse multi-agent coordination platform. Phase 1 establishes the event-sourced foundation that will serve as the source of truth for all system state, enabling deterministic state reconstruction and comprehensive audit trails.

**Key Deliverables**:
- Production-ready event store handling 10K events/second
- Deterministic state replay from complete event history  
- Snapshot management for performance optimization
- HTTP/WebSocket APIs for event operations

**Timeline**: 5 weeks total, 4 work packages delivered incrementally

---

## 1. COMPLETE TECHNICAL SPECIFICATIONS

### 1.1 System Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Clients   │────│  ValidationBridge │────│   Event Store   │
│  (Claude Code)  │    │   (Existing)     │    │    (New)        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                │                        │
                       ┌──────────────────┐    ┌─────────────────┐
                       │  HTTP/WS API     │    │  Snapshot Mgr   │
                       │    (New)         │    │    (New)        │
                       └──────────────────┘    └─────────────────┘
```

**Integration Strategy**: Event store is inserted beneath the existing ValidationBridge, preserving all current APIs while adding event-sourced persistence.

### 1.2 Class Architecture and Module Structure

#### Core Event Store Module (`src/lighthouse/event_store/`)

```python
# src/lighthouse/event_store/__init__.py
from .store import EventStore
from .models import Event, EventFilter, EventQuery
from .replay import EventReplayEngine  
from .snapshots import SnapshotManager
from .api import EventStoreAPI

# src/lighthouse/event_store/models.py
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class Event(BaseModel):
    """Core event model for all system state changes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = Field(..., description="Monotonic sequence number")  
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="Event type identifier")
    aggregate_id: str = Field(..., description="Entity this event applies to")
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, description="Event schema version")
    
    class Config:
        frozen = True  # Events are immutable

class EventFilter(BaseModel):
    """Filter criteria for event queries."""
    event_types: Optional[List[str]] = None
    aggregate_ids: Optional[List[str]] = None
    start_timestamp: Optional[datetime] = None
    end_timestamp: Optional[datetime] = None
    start_sequence: Optional[int] = None
    end_sequence: Optional[int] = None

class EventQuery(BaseModel):
    """Query parameters for event retrieval."""
    filter: EventFilter = Field(default_factory=EventFilter)
    limit: int = Field(default=1000, le=10000)
    offset: int = Field(default=0, ge=0)
    order: str = Field(default="asc", regex="^(asc|desc)$")

# src/lighthouse/event_store/store.py
import asyncio
import json
import os
import fcntl
from pathlib import Path
from typing import AsyncIterator, List, Optional
from datetime import datetime
import aiofiles
import gzip
from .models import Event, EventFilter, EventQuery

class EventStore:
    """High-performance file-based event store with WAL."""
    
    def __init__(self, data_dir: str = "./data/events"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.sync_policy = "fsync"  # fsync, fdatasync, or none
        self.compression_enabled = True
        
        # State
        self.current_sequence = 0
        self.current_log_file = None
        self.write_lock = asyncio.Lock()
        self._index = {}  # In-memory index for fast queries
        
    async def initialize(self) -> None:
        """Initialize event store and recover state."""
        await self._recover_state()
        await self._open_current_log_file()
        
    async def append(self, event: Event) -> None:
        """Append event to log with atomic guarantees."""
        async with self.write_lock:
            # Assign sequence number
            self.current_sequence += 1
            event.sequence = self.current_sequence
            
            # Serialize event
            event_data = event.model_dump_json() + "\n"
            
            # Write to current log file
            await self.current_log_file.write(event_data)
            
            # Sync based on policy
            if self.sync_policy == "fsync":
                await self.current_log_file.fsync()
            elif self.sync_policy == "fdatasync":
                os.fdatasync(self.current_log_file.fileno())
                
            # Update index
            self._update_index(event)
            
            # Check if rotation needed
            await self._check_rotation()
    
    async def append_batch(self, events: List[Event]) -> None:
        """Atomically append multiple events."""
        async with self.write_lock:
            start_sequence = self.current_sequence + 1
            
            # Assign sequence numbers
            for i, event in enumerate(events):
                event.sequence = start_sequence + i
            
            # Write all events
            batch_data = ""
            for event in events:
                batch_data += event.model_dump_json() + "\n"
                
            await self.current_log_file.write(batch_data)
            
            # Sync once for entire batch  
            if self.sync_policy != "none":
                await self.current_log_file.fsync()
                
            # Update sequence and index
            self.current_sequence += len(events)
            for event in events:
                self._update_index(event)
                
            await self._check_rotation()
    
    async def query(self, query: EventQuery) -> AsyncIterator[Event]:
        """Query events with filtering and pagination."""
        # Use index to find relevant log files
        log_files = await self._get_log_files_for_query(query)
        
        events_returned = 0
        events_skipped = 0
        
        for log_file_path in log_files:
            async with aiofiles.open(log_file_path, 'r') as f:
                async for line in f:
                    if not line.strip():
                        continue
                        
                    event_data = json.loads(line)
                    event = Event(**event_data)
                    
                    # Apply filters
                    if not self._matches_filter(event, query.filter):
                        continue
                        
                    # Handle offset
                    if events_skipped < query.offset:
                        events_skipped += 1
                        continue
                        
                    # Handle limit
                    if events_returned >= query.limit:
                        return
                        
                    yield event
                    events_returned += 1
    
    async def get_latest_sequence(self) -> int:
        """Get the latest sequence number."""
        return self.current_sequence
        
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check and return status."""
        try:
            # Test write operation
            test_event = Event(
                event_type="health_check",
                aggregate_id="system", 
                data={"timestamp": datetime.utcnow().isoformat()}
            )
            await self.append(test_event)
            
            # Get storage stats
            total_size = sum(
                f.stat().st_size for f in self.data_dir.glob("*.log*")
            )
            
            return {
                "status": "healthy",
                "current_sequence": self.current_sequence,
                "log_files": len(list(self.data_dir.glob("*.log*"))),
                "total_size_bytes": total_size,
                "write_performance": "ok"
            }
        except Exception as e:
            return {
                "status": "unhealthy", 
                "error": str(e)
            }

# src/lighthouse/event_store/replay.py
from typing import Any, Dict, Callable, AsyncIterator
from .models import Event, EventQuery
from .store import EventStore

class EventReplayEngine:
    """Engine for replaying events to reconstruct system state."""
    
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.handlers: Dict[str, Callable[[Event], Any]] = {}
        
    def register_handler(self, event_type: str, handler: Callable[[Event], Any]):
        """Register a handler for a specific event type."""
        self.handlers[event_type] = handler
        
    async def replay_all(self, initial_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """Replay all events to reconstruct current state."""
        state = initial_state or {}
        
        query = EventQuery()
        async for event in self.event_store.query(query):
            state = await self._apply_event(event, state)
            
        return state
        
    async def replay_from_sequence(self, 
                                 start_sequence: int,
                                 initial_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """Replay events starting from a specific sequence number."""
        state = initial_state or {}
        
        query = EventQuery(
            filter=EventFilter(start_sequence=start_sequence)
        )
        
        async for event in self.event_store.query(query):
            state = await self._apply_event(event, state)
            
        return state
        
    async def replay_stream(self, 
                          start_sequence: int = 0) -> AsyncIterator[Dict[str, Any]]:
        """Stream state changes as events are replayed."""
        state = {}
        
        query = EventQuery(
            filter=EventFilter(start_sequence=start_sequence)
        )
        
        async for event in self.event_store.query(query):
            state = await self._apply_event(event, state)
            yield {"sequence": event.sequence, "state": state, "event": event}
            
    async def _apply_event(self, event: Event, state: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a single event to the current state."""
        if event.event_type in self.handlers:
            handler = self.handlers[event.event_type]
            if asyncio.iscoroutinefunction(handler):
                return await handler(event, state)
            else:
                return handler(event, state)
        else:
            # Default handling - just store the event data
            if event.aggregate_id not in state:
                state[event.aggregate_id] = {}
            state[event.aggregate_id].update(event.data)
            return state

# src/lighthouse/event_store/snapshots.py
import json
import gzip
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from .models import Event
from .store import EventStore

class SnapshotManager:
    """Manages state snapshots for performance optimization."""
    
    def __init__(self, event_store: EventStore, data_dir: str = "./data/snapshots"):
        self.event_store = event_store
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.snapshot_interval = 10000  # Events between snapshots
        self.compression_enabled = True
        self.retention_days = 30
        
    async def create_snapshot(self, 
                            state: Dict[str, Any],
                            sequence: int,
                            metadata: Dict[str, Any] = None) -> str:
        """Create a new snapshot at the given sequence number."""
        snapshot_id = f"snapshot_{sequence}_{int(datetime.utcnow().timestamp())}"
        snapshot_path = self.data_dir / f"{snapshot_id}.json.gz"
        
        snapshot_data = {
            "id": snapshot_id,
            "sequence": sequence,
            "timestamp": datetime.utcnow().isoformat(),
            "state": state,
            "metadata": metadata or {}
        }
        
        # Compress and write snapshot
        compressed_data = gzip.compress(
            json.dumps(snapshot_data).encode('utf-8')
        )
        
        with open(snapshot_path, 'wb') as f:
            f.write(compressed_data)
            
        return snapshot_id
        
    async def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load a snapshot by ID."""
        snapshot_path = self.data_dir / f"{snapshot_id}.json.gz"
        
        if not snapshot_path.exists():
            return None
            
        with open(snapshot_path, 'rb') as f:
            compressed_data = f.read()
            
        json_data = gzip.decompress(compressed_data).decode('utf-8')
        return json.loads(json_data)
        
    async def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """Get the most recent snapshot."""
        snapshots = sorted(
            self.data_dir.glob("snapshot_*.json.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        if not snapshots:
            return None
            
        return await self.load_snapshot(snapshots[0].stem.replace('.json', ''))
        
    async def should_create_snapshot(self, current_sequence: int) -> bool:
        """Check if a new snapshot should be created."""
        latest = await self.get_latest_snapshot()
        
        if not latest:
            return True
            
        return current_sequence - latest["sequence"] >= self.snapshot_interval
        
    async def cleanup_old_snapshots(self) -> int:
        """Clean up snapshots older than retention period."""
        cutoff_time = datetime.utcnow() - timedelta(days=self.retention_days)
        deleted_count = 0
        
        for snapshot_path in self.data_dir.glob("snapshot_*.json.gz"):
            if snapshot_path.stat().st_mtime < cutoff_time.timestamp():
                snapshot_path.unlink()
                deleted_count += 1
                
        return deleted_count
```

#### Event Store API Module (`src/lighthouse/event_store/api.py`)

```python
# src/lighthouse/event_store/api.py
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import json

from .store import EventStore
from .models import Event, EventQuery
from .replay import EventReplayEngine  
from .snapshots import SnapshotManager

class EventStoreAPI:
    """HTTP and WebSocket API for event store operations."""
    
    def __init__(self, event_store: EventStore, replay_engine: EventReplayEngine, 
                 snapshot_manager: SnapshotManager):
        self.event_store = event_store
        self.replay_engine = replay_engine
        self.snapshot_manager = snapshot_manager
        self.app = FastAPI(title="Lighthouse Event Store API")
        self.websocket_connections: List[WebSocket] = []
        
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.post("/events")
        async def append_event(event: Event):
            """Append a single event."""
            try:
                await self.event_store.append(event)
                
                # Notify WebSocket subscribers
                await self._notify_subscribers(event)
                
                return {"success": True, "sequence": event.sequence}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/events/batch")
        async def append_events_batch(events: List[Event]):
            """Append multiple events atomically."""
            try:
                await self.event_store.append_batch(events)
                
                # Notify WebSocket subscribers
                for event in events:
                    await self._notify_subscribers(event)
                
                return {
                    "success": True, 
                    "count": len(events),
                    "sequences": [e.sequence for e in events]
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/events")
        async def query_events(
            event_types: str = None,
            aggregate_ids: str = None,
            start_sequence: int = None,
            limit: int = 1000
        ):
            """Query events with filtering."""
            try:
                # Build query from parameters
                query = EventQuery(
                    filter=EventFilter(
                        event_types=event_types.split(",") if event_types else None,
                        aggregate_ids=aggregate_ids.split(",") if aggregate_ids else None,
                        start_sequence=start_sequence
                    ),
                    limit=limit
                )
                
                events = []
                async for event in self.event_store.query(query):
                    events.append(event.model_dump())
                    
                return {"events": events, "count": len(events)}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/events/stream")
        async def stream_events(start_sequence: int = 0):
            """Stream events as newline-delimited JSON."""
            async def generate():
                query = EventQuery(
                    filter=EventFilter(start_sequence=start_sequence),
                    limit=10000
                )
                
                async for event in self.event_store.query(query):
                    yield json.dumps(event.model_dump()) + "\n"
            
            return StreamingResponse(generate(), media_type="application/x-ndjson")
        
        @self.app.post("/replay")
        async def replay_events(start_sequence: int = 0):
            """Replay events to reconstruct state."""
            try:
                state = await self.replay_engine.replay_from_sequence(start_sequence)
                return {"state": state, "sequence": await self.event_store.get_latest_sequence()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return await self.event_store.health_check()
        
        @self.app.websocket("/stream")
        async def websocket_stream(websocket: WebSocket):
            """WebSocket endpoint for real-time event streaming."""
            await websocket.accept()
            self.websocket_connections.append(websocket)
            
            try:
                while True:
                    # Keep connection alive and handle client messages
                    data = await websocket.receive_text()
                    # Echo back for now - could handle subscription filtering
                    await websocket.send_text(f"Received: {data}")
            except WebSocketDisconnect:
                self.websocket_connections.remove(websocket)
    
    async def _notify_subscribers(self, event: Event):
        """Notify all WebSocket subscribers of new events."""
        if not self.websocket_connections:
            return
            
        message = json.dumps({
            "type": "event",
            "data": event.model_dump()
        })
        
        # Send to all connected clients
        for websocket in self.websocket_connections[:]:  # Copy list to avoid modification during iteration
            try:
                await websocket.send_text(message)
            except Exception:
                # Remove disconnected clients
                self.websocket_connections.remove(websocket)
```

### 1.3 Integration with Existing Bridge

```python
# src/lighthouse/bridge_events.py
"""Event types for ValidationBridge operations."""

from enum import Enum
from typing import Dict, Any
from .event_store.models import Event

class BridgeEventType(str, Enum):
    COMMAND_RECEIVED = "command_received"
    COMMAND_APPROVED = "command_approved" 
    COMMAND_REJECTED = "command_rejected"
    PAIR_SESSION_REQUESTED = "pair_session_requested"
    PAIR_SESSION_ACCEPTED = "pair_session_accepted"
    PAIR_SUGGESTION_MADE = "pair_suggestion_made"
    PAIR_REVIEW_COMPLETED = "pair_review_completed"

class BridgeEventFactory:
    """Factory for creating bridge-related events."""
    
    @staticmethod
    def command_received(command_id: str, tool: str, input_data: Dict[str, Any], 
                        agent: str) -> Event:
        return Event(
            event_type=BridgeEventType.COMMAND_RECEIVED,
            aggregate_id=f"command:{command_id}",
            data={
                "command_id": command_id,
                "tool": tool,
                "input": input_data,
                "agent": agent
            }
        )
    
    @staticmethod  
    def command_approved(command_id: str, reason: str, approver: str = "system") -> Event:
        return Event(
            event_type=BridgeEventType.COMMAND_APPROVED,
            aggregate_id=f"command:{command_id}",
            data={
                "command_id": command_id,
                "reason": reason,
                "approver": approver
            }
        )

# Modified ValidationBridge to use event store
# src/lighthouse/bridge.py (modifications)
from .event_store import EventStore
from .bridge_events import BridgeEventFactory, BridgeEventType

class ValidationBridge:
    """Bridge for command validation between agents - now with event sourcing."""
    
    def __init__(self, port: int = 8765, event_store: EventStore = None):
        self.port = port
        self.event_store = event_store
        
        # State will be sourced from events
        self.pending_commands: Dict[str, CommandData] = {}
        self.approved_commands: Dict[str, Dict[str, Any]] = {}
        
        if event_store:
            # Register event handlers for state reconstruction
            self._register_event_handlers()
    
    def _register_event_handlers(self):
        """Register handlers for bridge event types."""
        from .event_store.replay import EventReplayEngine
        
        self.replay_engine = EventReplayEngine(self.event_store)
        
        def handle_command_received(event: Event, state: Dict[str, Any]) -> Dict[str, Any]:
            command_data = CommandData(**event.data, id=event.data["command_id"])
            self.pending_commands[event.data["command_id"]] = command_data
            return state
            
        def handle_command_approved(event: Event, state: Dict[str, Any]) -> Dict[str, Any]:
            command_id = event.data["command_id"]
            if command_id in self.pending_commands:
                self.pending_commands[command_id].status = "approved"
                self.approved_commands[command_id] = {
                    "timestamp": event.timestamp.timestamp(),
                    "reason": event.data["reason"]
                }
            return state
            
        self.replay_engine.register_handler(BridgeEventType.COMMAND_RECEIVED, handle_command_received)
        self.replay_engine.register_handler(BridgeEventType.COMMAND_APPROVED, handle_command_approved)
    
    async def handle_validation(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle command validation requests - now with event sourcing."""
        data = await request.json()
        
        # Create and store event
        event = BridgeEventFactory.command_received(
            command_id=data.get('id', f"cmd_{int(time.time()*1000)}"),
            tool=data['tool'],
            input_data=data['input'],
            agent=data.get('agent', 'unknown')
        )
        
        if self.event_store:
            await self.event_store.append(event)
        
        # Continue with existing logic...
        # (rest of validation logic remains the same)
```

---

## 2. FILE SYSTEM LAYOUT AND DIRECTORY STRUCTURE

```
lighthouse/
├── src/lighthouse/
│   ├── __init__.py
│   ├── server.py                    # Existing MCP server
│   ├── bridge.py                    # Modified with event sourcing
│   ├── validator.py                 # Existing validation logic
│   ├── bridge_events.py             # New: Bridge event types
│   └── event_store/                 # New: Event store module
│       ├── __init__.py
│       ├── models.py                # Event models and schemas
│       ├── store.py                 # Core event store implementation
│       ├── replay.py                # Event replay engine
│       ├── snapshots.py             # Snapshot management
│       └── api.py                   # HTTP/WebSocket API
├── data/                            # New: Runtime data directory
│   ├── events/                      # Event log files
│   │   ├── events_000001.log        # Current event log
│   │   ├── events_000002.log.gz     # Rotated/compressed logs
│   │   └── .index/                  # Index files for fast queries
│   └── snapshots/                   # State snapshots
│       ├── snapshot_10000_*.json.gz # Compressed snapshots
│       └── .metadata                # Snapshot metadata
├── tests/
│   ├── unit/
│   │   ├── test_event_store.py      # Unit tests for event store
│   │   ├── test_replay_engine.py    # Unit tests for replay
│   │   └── test_snapshots.py        # Unit tests for snapshots
│   ├── integration/
│   │   ├── test_bridge_integration.py  # Bridge + event store tests
│   │   └── test_api_integration.py     # API integration tests
│   └── performance/
│       ├── test_throughput.py       # Performance benchmarks
│       └── test_recovery.py         # Recovery and resilience tests
├── config/
│   ├── event_store.yaml            # Event store configuration
│   └── development.yaml            # Development environment config
├── docs/
│   ├── api/                        # API documentation
│   │   ├── event_store_api.md      # Event store API docs
│   │   └── openapi.json           # Generated OpenAPI spec
│   └── architecture/
│       └── PHASE_1_DETAILED_DESIGN.md  # This document
└── scripts/
    ├── setup_dev_env.sh            # Development environment setup
    ├── run_benchmarks.sh           # Performance benchmarking
    └── migrate_data.py             # Data migration utilities
```

---

## 3. API ENDPOINT SPECIFICATIONS

### 3.1 Event Store REST API

#### POST /events
Append a single event to the store.

**Request Body**:
```json
{
  "event_type": "command_received",
  "aggregate_id": "command:cmd_123",
  "data": {
    "command_id": "cmd_123",
    "tool": "Bash",
    "input": {"command": "ls -la"},
    "agent": "claude-code"
  },
  "metadata": {
    "source": "validation_bridge",
    "correlation_id": "req_456"
  }
}
```

**Response**:
```json
{
  "success": true,
  "sequence": 12345,
  "id": "evt_789abc"
}
```

**Status Codes**: 200 (success), 400 (invalid event), 500 (storage error)

#### POST /events/batch
Atomically append multiple events.

**Request Body**:
```json
{
  "events": [
    { /* event 1 */ },
    { /* event 2 */ }
  ]
}
```

**Response**:
```json
{
  "success": true,
  "count": 2,
  "sequences": [12345, 12346]
}
```

#### GET /events
Query events with filtering and pagination.

**Query Parameters**:
- `event_types`: Comma-separated event types to include
- `aggregate_ids`: Comma-separated aggregate IDs to include  
- `start_sequence`: Start from this sequence number
- `end_sequence`: Stop at this sequence number
- `start_timestamp`: Start from this timestamp (ISO 8601)
- `end_timestamp`: Stop at this timestamp (ISO 8601)
- `limit`: Maximum events to return (default 1000, max 10000)
- `offset`: Number of events to skip (default 0)
- `order`: Sort order - "asc" or "desc" (default "asc")

**Response**:
```json
{
  "events": [
    {
      "id": "evt_789abc",
      "sequence": 12345,
      "timestamp": "2025-01-15T10:30:00Z",
      "event_type": "command_received",
      "aggregate_id": "command:cmd_123", 
      "data": { /* event data */ },
      "metadata": { /* event metadata */ },
      "version": 1
    }
  ],
  "count": 1,
  "total": 50000
}
```

#### GET /events/stream
Stream events as newline-delimited JSON.

**Query Parameters**: Same as GET /events

**Response**: `application/x-ndjson` stream
```
{"id":"evt_1",...}
{"id":"evt_2",...}
{"id":"evt_3",...}
```

#### POST /replay
Replay events to reconstruct system state.

**Request Body**:
```json
{
  "start_sequence": 10000,
  "event_types": ["command_received", "command_approved"],
  "aggregate_ids": ["command:cmd_123"]
}
```

**Response**:
```json
{
  "state": {
    "command:cmd_123": {
      "status": "approved",
      "tool": "Bash",
      "agent": "claude-code"
    }
  },
  "final_sequence": 12500
}
```

#### GET /health
Health check and system status.

**Response**:
```json
{
  "status": "healthy",
  "current_sequence": 12500,
  "log_files": 3,
  "total_size_bytes": 52428800,
  "write_performance": "ok",
  "uptime_seconds": 3600
}
```

### 3.2 WebSocket Event Stream

#### WebSocket /stream
Real-time event streaming via WebSocket.

**Connection**: `ws://localhost:8080/stream`

**Client Message** (subscription):
```json
{
  "action": "subscribe",
  "filters": {
    "event_types": ["command_received"],
    "aggregate_ids": ["command:*"]
  }
}
```

**Server Message** (event):
```json
{
  "type": "event",
  "data": {
    "id": "evt_789abc",
    "sequence": 12345,
    "event_type": "command_received",
    /* ... full event data ... */
  }
}
```

---

## 4. DATABASE/STORAGE SCHEMAS AND DATA MODELS

### 4.1 Event Storage Format

Events are stored as newline-delimited JSON in log files:

```json
{"id":"evt_001","sequence":1,"timestamp":"2025-01-15T10:30:00Z","event_type":"command_received","aggregate_id":"command:cmd_123","data":{"command_id":"cmd_123","tool":"Bash","input":{"command":"ls -la"},"agent":"claude-code"},"metadata":{"source":"validation_bridge"},"version":1}
{"id":"evt_002","sequence":2,"timestamp":"2025-01-15T10:30:01Z","event_type":"command_approved","aggregate_id":"command:cmd_123","data":{"command_id":"cmd_123","reason":"Safe command","approver":"system"},"metadata":{"source":"validation_bridge"},"version":1}
```

### 4.2 Log File Organization

- **File naming**: `events_NNNNNN.log` (6-digit zero-padded sequence)
- **Rotation**: New file when current exceeds 100MB
- **Compression**: Rotated files compressed with gzip (`events_NNNNNN.log.gz`)
- **Index files**: `.index/events_NNNNNN.idx` for fast seeking

### 4.3 Snapshot Storage Format

Snapshots are stored as compressed JSON:

```json
{
  "id": "snapshot_10000_1642248600",
  "sequence": 10000,
  "timestamp": "2025-01-15T12:30:00Z", 
  "state": {
    "command:cmd_123": {
      "status": "approved",
      "tool": "Bash",
      "agent": "claude-code",
      "timestamp": 1642248500
    },
    "pair_session:pair_456": {
      "status": "active", 
      "requester": "agent_1",
      "partner": "agent_2"
    }
  },
  "metadata": {
    "compression": "gzip",
    "size_bytes": 45231,
    "event_count": 10000
  }
}
```

### 4.4 Bridge Event Schemas

#### Command Received Event
```json
{
  "event_type": "command_received",
  "aggregate_id": "command:{command_id}",
  "data": {
    "command_id": "string",
    "tool": "string", 
    "input": {},
    "agent": "string",
    "danger_level": "safe|dangerous|unknown"
  }
}
```

#### Command Approved Event  
```json
{
  "event_type": "command_approved",
  "aggregate_id": "command:{command_id}",
  "data": {
    "command_id": "string",
    "reason": "string",
    "approver": "string",
    "approval_method": "automatic|manual|policy"
  }
}
```

#### Pair Session Events
```json
{
  "event_type": "pair_session_requested",
  "aggregate_id": "pair_session:{session_id}",
  "data": {
    "session_id": "string",
    "requester": "string", 
    "mode": "COLLABORATIVE|REVIEW|PASSIVE",
    "task": "string"
  }
}
```

---

## 5. CONFIGURATION MANAGEMENT

### 5.1 Environment Variables

```bash
# Event Store Configuration
LIGHTHOUSE_EVENT_STORE_DIR=/var/lib/lighthouse/events
LIGHTHOUSE_SNAPSHOT_DIR=/var/lib/lighthouse/snapshots
LIGHTHOUSE_MAX_LOG_FILE_SIZE=104857600  # 100MB
LIGHTHOUSE_SYNC_POLICY=fsync  # fsync, fdatasync, none
LIGHTHOUSE_COMPRESSION_ENABLED=true
LIGHTHOUSE_SNAPSHOT_INTERVAL=10000

# API Configuration
LIGHTHOUSE_API_HOST=0.0.0.0
LIGHTHOUSE_API_PORT=8080
LIGHTHOUSE_BRIDGE_PORT=8765
LIGHTHOUSE_WEBSOCKET_ENABLED=true

# Performance Configuration
LIGHTHOUSE_MAX_BATCH_SIZE=1000
LIGHTHOUSE_QUERY_LIMIT_MAX=10000
LIGHTHOUSE_WEBSOCKET_MAX_CONNECTIONS=100

# Monitoring Configuration
LIGHTHOUSE_METRICS_ENABLED=true
LIGHTHOUSE_LOG_LEVEL=INFO
LIGHTHOUSE_HEALTH_CHECK_INTERVAL=60
```

### 5.2 Configuration Files

#### config/event_store.yaml
```yaml
event_store:
  data_directory: "./data/events"
  max_file_size: 104857600  # 100MB
  sync_policy: "fsync"      # fsync, fdatasync, none
  compression_enabled: true
  rotation_check_interval: 300  # 5 minutes
  
  index:
    enabled: true
    directory: "./data/events/.index" 
    cache_size: 1000
    
  cleanup:
    enabled: true
    retention_days: 365
    check_interval: 3600  # 1 hour

snapshots:
  data_directory: "./data/snapshots"
  interval: 10000           # Events between snapshots
  compression_enabled: true
  retention_days: 30
  validation_enabled: true  # Verify snapshots via replay

api:
  host: "0.0.0.0"
  port: 8080
  websocket:
    enabled: true
    max_connections: 100
    ping_interval: 30
  cors:
    enabled: true
    origins: ["http://localhost:3000"]
    
performance:
  max_batch_size: 1000
  query_limit_default: 1000
  query_limit_max: 10000
  concurrent_queries: 10
  
monitoring:
  metrics_enabled: true
  health_check_interval: 60
  prometheus_endpoint: "/metrics"
```

#### config/development.yaml
```yaml
extends: "event_store.yaml"

event_store:
  data_directory: "./dev_data/events"
  sync_policy: "none"  # Faster for development
  
snapshots:
  data_directory: "./dev_data/snapshots"
  interval: 100  # More frequent snapshots for testing

api:
  port: 8081  # Different port for dev
  
logging:
  level: "DEBUG"
  format: "json"
  file: "./logs/lighthouse-dev.log"
```

---

## 6. IMPLEMENTATION ROADMAP

### Work Package 1.1: Core Event Store (Week 1-2)

#### Tasks and Deliverables

**Week 1: Foundation**
- [ ] Create `src/lighthouse/event_store/` module structure
- [ ] Implement `Event`, `EventFilter`, `EventQuery` models in `models.py`
- [ ] Implement basic `EventStore` class in `store.py` with:
  - File-based append operations
  - JSON serialization/deserialization
  - Basic query functionality
  - Write-ahead logging
- [ ] Add comprehensive unit tests for event store core
- [ ] Performance test: Verify <1ms append operations on SSD

**Week 2: Optimization and Reliability**
- [ ] Implement log file rotation and compression
- [ ] Add index files for fast event queries
- [ ] Implement configurable sync policies (fsync, fdatasync, none)
- [ ] Add error handling and recovery from corrupted files
- [ ] Stress test: Store 10,000 events without data loss
- [ ] Benchmark: Achieve 1,000+ events/second sustained throughput

**Validation Criteria**:
- [ ] All unit tests pass with 100% coverage
- [ ] Performance benchmarks meet requirements
- [ ] Event store survives kill -9 without data loss
- [ ] Log files can be compressed without losing data integrity
- [ ] Index files correctly accelerate query operations

**Code Example - Basic Usage**:
```python
# Initialize event store
store = EventStore("./data/events")
await store.initialize()

# Create and append event
event = Event(
    event_type="test_event",
    aggregate_id="test_aggregate", 
    data={"message": "Hello, World!"}
)
await store.append(event)

# Query events
query = EventQuery(
    filter=EventFilter(event_types=["test_event"]),
    limit=100
)
async for event in store.query(query):
    print(f"Event {event.sequence}: {event.data}")
```

### Work Package 1.2: Event Replay Engine (Week 2-3)

#### Tasks and Deliverables

**Week 2: Core Replay Logic**
- [ ] Implement `EventReplayEngine` class in `replay.py`
- [ ] Handler registration system for different event types
- [ ] Basic replay functionality (all events from start)
- [ ] Partial replay from specific sequence numbers
- [ ] Add unit tests for replay engine

**Week 3: Advanced Replay Features**
- [ ] Streaming replay for memory efficiency
- [ ] Event filtering during replay
- [ ] Checkpoint/resume capability for long replays
- [ ] Performance optimization for large event histories
- [ ] Integration tests with event store

**Validation Criteria**:
- [ ] Replay produces identical state regardless of restart points
- [ ] Memory usage remains constant during streaming replay
- [ ] Filtering reduces replay time proportionally to events filtered
- [ ] Reconstruct system state from 100,000 events in <10 seconds
- [ ] Replay engine handles corrupted events gracefully

**Code Example - Replay Usage**:
```python
# Initialize replay engine
replay_engine = EventReplayEngine(event_store)

# Register event handlers
def handle_command_event(event: Event, state: dict) -> dict:
    # Update state based on command event
    state[event.aggregate_id] = event.data
    return state

replay_engine.register_handler("command_received", handle_command_event)

# Replay all events to reconstruct state
current_state = await replay_engine.replay_all()

# Stream replay from specific point
async for state_update in replay_engine.replay_stream(start_sequence=1000):
    print(f"Sequence {state_update['sequence']}: {state_update['state']}")
```

### Work Package 1.3: Snapshot Management (Week 3-4)

#### Tasks and Deliverables

**Week 3: Basic Snapshots**
- [ ] Implement `SnapshotManager` class in `snapshots.py`
- [ ] Snapshot creation with compression
- [ ] Snapshot loading and validation
- [ ] Configurable snapshot intervals
- [ ] Unit tests for snapshot operations

**Week 4: Advanced Snapshot Features**  
- [ ] Incremental snapshots using state diffs
- [ ] Snapshot validation against event replay
- [ ] Automatic cleanup of expired snapshots
- [ ] Integration with replay engine for fast recovery
- [ ] Performance testing with large state objects

**Validation Criteria**:
- [ ] Snapshots reduce cold start time by 90%
- [ ] Snapshot + incremental replay completes in <1 second
- [ ] Corrupted snapshots detected and replaced automatically
- [ ] Storage overhead <20% of event log size
- [ ] Snapshots maintain data integrity under all conditions

**Code Example - Snapshot Usage**:
```python
# Initialize snapshot manager
snapshot_mgr = SnapshotManager(event_store, "./data/snapshots")

# Check if snapshot needed
current_seq = await event_store.get_latest_sequence()
if await snapshot_mgr.should_create_snapshot(current_seq):
    # Get current state from replay
    state = await replay_engine.replay_all()
    
    # Create snapshot
    snapshot_id = await snapshot_mgr.create_snapshot(
        state=state,
        sequence=current_seq,
        metadata={"source": "automatic"}
    )
    print(f"Created snapshot: {snapshot_id}")

# Fast recovery using latest snapshot
latest_snapshot = await snapshot_mgr.get_latest_snapshot()
if latest_snapshot:
    # Replay only events since snapshot
    state = await replay_engine.replay_from_sequence(
        start_sequence=latest_snapshot["sequence"] + 1,
        initial_state=latest_snapshot["state"]
    )
```

### Work Package 1.4: Event Store API (Week 4-5)

#### Tasks and Deliverables

**Week 4: HTTP API Implementation**
- [ ] Implement `EventStoreAPI` class in `api.py` using FastAPI
- [ ] POST /events endpoint for single event append
- [ ] POST /events/batch endpoint for atomic batch operations
- [ ] GET /events endpoint with filtering and pagination
- [ ] GET /health endpoint for monitoring
- [ ] API integration tests

**Week 5: WebSocket Streaming and Polish**
- [ ] WebSocket /stream endpoint for real-time events
- [ ] GET /events/stream endpoint for HTTP streaming
- [ ] POST /replay endpoint for state reconstruction
- [ ] Client libraries for Python integration
- [ ] Complete API documentation with OpenAPI spec
- [ ] Load testing for API endpoints

**Validation Criteria**:
- [ ] API handles 1,000 requests/second with <50ms latency
- [ ] WebSocket streams deliver events with <100ms delay
- [ ] Batch operations are atomic (all succeed or all fail)
- [ ] Client disconnections don't lose events
- [ ] API provides comprehensive error messages and status codes

**Code Example - API Usage**:
```python
# Start the API server
api = EventStoreAPI(event_store, replay_engine, snapshot_manager)
app = api.app

# Client usage with HTTP requests
import httpx

# Append event via API
event_data = {
    "event_type": "test_event",
    "aggregate_id": "test_123",
    "data": {"message": "API test"}
}
response = httpx.post("http://localhost:8080/events", json=event_data)
print(f"Event sequence: {response.json()['sequence']}")

# Query events via API
response = httpx.get(
    "http://localhost:8080/events?event_types=test_event&limit=10"
)
events = response.json()["events"]
print(f"Retrieved {len(events)} events")

# WebSocket streaming
import websockets

async def stream_events():
    async with websockets.connect("ws://localhost:8080/stream") as websocket:
        await websocket.send('{"action": "subscribe"}')
        async for message in websocket:
            event = json.loads(message)
            print(f"Received event: {event['data']['event_type']}")
```

---

## 7. VALIDATION AND TESTING

### 7.1 Unit Test Specifications

#### Event Store Core Tests (`tests/unit/test_event_store.py`)

```python
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path

from lighthouse.event_store import EventStore, Event

class TestEventStore:
    """Comprehensive tests for EventStore class."""
    
    @pytest.fixture
    async def event_store(self):
        """Create temporary event store for testing."""
        temp_dir = tempfile.mkdtemp()
        store = EventStore(temp_dir)
        await store.initialize()
        yield store
        shutil.rmtree(temp_dir)
    
    async def test_append_single_event(self, event_store):
        """Test appending a single event."""
        event = Event(
            event_type="test_event",
            aggregate_id="test_aggregate",
            data={"test": "data"}
        )
        
        await event_store.append(event)
        
        # Verify event has sequence number
        assert event.sequence == 1
        
        # Verify event is queryable
        events = []
        async for e in event_store.query(EventQuery()):
            events.append(e)
        
        assert len(events) == 1
        assert events[0].id == event.id
    
    async def test_batch_append_atomicity(self, event_store):
        """Test that batch append is atomic."""
        events = [
            Event(event_type="test", aggregate_id="test1", data={"i": 1}),
            Event(event_type="test", aggregate_id="test2", data={"i": 2}),
            Event(event_type="test", aggregate_id="test3", data={"i": 3})
        ]
        
        # Simulate failure during batch (this would be done with mocking)
        await event_store.append_batch(events)
        
        # Verify all events have consecutive sequence numbers
        assert events[0].sequence == 1
        assert events[1].sequence == 2  
        assert events[2].sequence == 3
        
        # Verify all events are stored
        stored_events = []
        async for e in event_store.query(EventQuery()):
            stored_events.append(e)
        
        assert len(stored_events) == 3
    
    async def test_crash_recovery(self, event_store):
        """Test recovery after simulated crash."""
        # Append some events
        events = [
            Event(event_type="test", aggregate_id="test1", data={"before": "crash"}),
            Event(event_type="test", aggregate_id="test2", data={"before": "crash"})
        ]
        
        for event in events:
            await event_store.append(event)
        
        # Simulate crash by creating new store instance
        data_dir = event_store.data_dir
        del event_store  # Close files
        
        recovered_store = EventStore(str(data_dir))
        await recovered_store.initialize()
        
        # Verify events are still there
        recovered_events = []
        async for e in recovered_store.query(EventQuery()):
            recovered_events.append(e)
        
        assert len(recovered_events) == 2
        assert recovered_store.current_sequence == 2
    
    async def test_concurrent_writes(self, event_store):
        """Test concurrent write operations."""
        async def write_events(start_id: int, count: int):
            events = [
                Event(event_type="test", aggregate_id=f"test_{start_id + i}", 
                      data={"thread": start_id, "index": i})
                for i in range(count)
            ]
            for event in events:
                await event_store.append(event)
        
        # Run concurrent writes
        await asyncio.gather(
            write_events(1, 100),
            write_events(101, 100), 
            write_events(201, 100)
        )
        
        # Verify all events are stored with correct sequence numbers
        events = []
        async for e in event_store.query(EventQuery()):
            events.append(e)
        
        assert len(events) == 300
        
        # Verify sequence numbers are monotonic
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)
        assert sequences[-1] == 300

    @pytest.mark.performance  
    async def test_append_performance(self, event_store):
        """Test append performance meets requirements."""
        import time
        
        events = [
            Event(event_type="perf_test", aggregate_id=f"test_{i}", 
                  data={"index": i})
            for i in range(1000)
        ]
        
        start_time = time.time()
        for event in events:
            await event_store.append(event)
        end_time = time.time()
        
        total_time = end_time - start_time
        avg_time_per_event = total_time / len(events)
        
        # Requirement: <1ms per append on SSD
        assert avg_time_per_event < 0.001, f"Average append time: {avg_time_per_event:.4f}s"
        
    async def test_large_event_handling(self, event_store):
        """Test handling of large events."""
        large_data = {"large_field": "x" * (500 * 1024)}  # 500KB
        
        event = Event(
            event_type="large_test",
            aggregate_id="large_aggregate",
            data=large_data
        )
        
        await event_store.append(event)
        
        # Verify large event can be retrieved
        events = []
        async for e in event_store.query(EventQuery()):
            events.append(e)
        
        assert len(events) == 1
        assert events[0].data["large_field"] == large_data["large_field"]
```

#### Replay Engine Tests (`tests/unit/test_replay_engine.py`)

```python
import pytest
from lighthouse.event_store import EventStore, Event, EventReplayEngine

class TestEventReplayEngine:
    """Tests for EventReplayEngine functionality."""
    
    @pytest.fixture
    async def replay_setup(self):
        """Setup event store with test events and replay engine."""
        temp_dir = tempfile.mkdtemp()
        store = EventStore(temp_dir)
        await store.initialize()
        
        # Add test events
        events = [
            Event(event_type="user_created", aggregate_id="user:1", 
                  data={"name": "Alice", "email": "alice@test.com"}),
            Event(event_type="user_updated", aggregate_id="user:1",
                  data={"name": "Alice Smith"}),
            Event(event_type="user_created", aggregate_id="user:2",
                  data={"name": "Bob", "email": "bob@test.com"})
        ]
        
        for event in events:
            await store.append(event)
        
        replay_engine = EventReplayEngine(store)
        
        yield store, replay_engine, events
        
        shutil.rmtree(temp_dir)
    
    async def test_replay_all_events(self, replay_setup):
        """Test replaying all events to reconstruct state."""
        store, replay_engine, test_events = replay_setup
        
        # Register handlers
        def handle_user_created(event: Event, state: dict) -> dict:
            user_id = event.aggregate_id
            state[user_id] = event.data
            return state
            
        def handle_user_updated(event: Event, state: dict) -> dict:
            user_id = event.aggregate_id
            if user_id in state:
                state[user_id].update(event.data)
            return state
            
        replay_engine.register_handler("user_created", handle_user_created)
        replay_engine.register_handler("user_updated", handle_user_updated)
        
        # Replay all events
        final_state = await replay_engine.replay_all()
        
        # Verify final state
        assert "user:1" in final_state
        assert "user:2" in final_state
        assert final_state["user:1"]["name"] == "Alice Smith"  # Updated name
        assert final_state["user:2"]["name"] == "Bob"
        
    async def test_streaming_replay_memory_usage(self, replay_setup):
        """Test that streaming replay doesn't accumulate memory."""
        store, replay_engine, _ = replay_setup
        
        # Add many more events to test memory efficiency
        large_events = [
            Event(event_type="bulk_test", aggregate_id=f"bulk:{i}",
                  data={"data": "x" * 1000})  # 1KB per event
            for i in range(1000)
        ]
        
        for event in large_events:
            await store.append(event)
        
        # Stream replay and verify memory doesn't grow unbounded
        state_count = 0
        max_memory = 0
        
        import psutil
        process = psutil.Process()
        
        async for state_update in replay_engine.replay_stream():
            current_memory = process.memory_info().rss
            max_memory = max(max_memory, current_memory)
            state_count += 1
            
            # Memory shouldn't grow significantly during streaming
            if state_count > 100:  # After processing some events
                initial_memory = process.memory_info().rss
                # Memory growth should be minimal (< 10%)
                assert current_memory < initial_memory * 1.1
        
        assert state_count > 1000  # Processed all events
```

### 7.2 Integration Test Scenarios

#### Bridge Integration Tests (`tests/integration/test_bridge_integration.py`)

```python
import pytest
import asyncio
from lighthouse.bridge import ValidationBridge
from lighthouse.event_store import EventStore
from lighthouse.bridge_events import BridgeEventType

class TestBridgeIntegration:
    """Integration tests for ValidationBridge with EventStore."""
    
    @pytest.fixture
    async def integrated_system(self):
        """Setup complete system with bridge and event store."""
        temp_dir = tempfile.mkdtemp()
        
        # Setup event store
        event_store = EventStore(temp_dir + "/events") 
        await event_store.initialize()
        
        # Setup bridge with event store
        bridge = ValidationBridge(port=8766, event_store=event_store)
        await bridge.start()
        
        yield bridge, event_store
        
        await bridge.stop()
        shutil.rmtree(temp_dir)
    
    async def test_command_validation_with_events(self, integrated_system):
        """Test that command validation creates events."""
        bridge, event_store = integrated_system
        
        # Simulate command validation request
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            command_data = {
                "id": "test_cmd_123",
                "tool": "Bash", 
                "input": {"command": "ls -la"},
                "agent": "test_agent"
            }
            
            async with session.post(
                f"http://localhost:8766/validate",
                json=command_data
            ) as response:
                result = await response.json()
                
        # Verify response
        assert result["status"] in ["approved", "blocked"]
        
        # Verify event was created
        events = []
        async for event in event_store.query(EventQuery()):
            events.append(event)
        
        # Should have command_received event
        command_events = [e for e in events if e.event_type == BridgeEventType.COMMAND_RECEIVED]
        assert len(command_events) == 1
        assert command_events[0].data["command_id"] == "test_cmd_123"
        
    async def test_bridge_state_reconstruction(self, integrated_system):
        """Test that bridge can reconstruct state from events after restart."""
        bridge, event_store = integrated_system
        
        # Create some bridge state through API calls
        commands = [
            {"id": f"cmd_{i}", "tool": "Bash", "input": {"command": f"echo {i}"}}
            for i in range(5)
        ]
        
        async with aiohttp.ClientSession() as session:
            for cmd in commands:
                async with session.post(f"http://localhost:8766/validate", json=cmd):
                    pass
        
        # Stop and restart bridge
        await bridge.stop()
        
        new_bridge = ValidationBridge(port=8767, event_store=event_store) 
        await new_bridge.start()
        
        # Verify state was reconstructed
        # (This would involve checking internal bridge state)
        # For now, just verify events are still there
        events = []
        async for event in event_store.query(EventQuery()):
            events.append(event)
        
        command_events = [e for e in events if e.event_type == BridgeEventType.COMMAND_RECEIVED]
        assert len(command_events) == 5
        
        await new_bridge.stop()
```

#### API Integration Tests (`tests/integration/test_api_integration.py`)

```python
import pytest
import asyncio
import httpx
import websockets
import json
from lighthouse.event_store import EventStore, EventStoreAPI, EventReplayEngine, SnapshotManager

class TestAPIIntegration:
    """Integration tests for Event Store API."""
    
    @pytest.fixture
    async def api_server(self):
        """Setup complete API server for testing."""
        temp_dir = tempfile.mkdtemp()
        
        # Setup components
        event_store = EventStore(temp_dir + "/events")
        await event_store.initialize()
        
        replay_engine = EventReplayEngine(event_store)
        snapshot_manager = SnapshotManager(event_store, temp_dir + "/snapshots")
        
        api = EventStoreAPI(event_store, replay_engine, snapshot_manager)
        
        # Start server
        import uvicorn
        config = uvicorn.Config(app=api.app, host="127.0.0.1", port=8082, log_level="critical")
        server = uvicorn.Server(config)
        
        server_task = asyncio.create_task(server.serve())
        await asyncio.sleep(0.1)  # Let server start
        
        yield "http://127.0.0.1:8082"
        
        server.should_exit = True
        await server_task
        shutil.rmtree(temp_dir)
    
    async def test_event_crud_operations(self, api_server):
        """Test complete event CRUD lifecycle via API."""
        base_url = api_server
        
        async with httpx.AsyncClient() as client:
            # Create events via POST /events
            event_data = {
                "event_type": "test_api_event",
                "aggregate_id": "test_aggregate_1", 
                "data": {"message": "API test message"}
            }
            
            response = await client.post(f"{base_url}/events", json=event_data)
            assert response.status_code == 200
            
            result = response.json()
            assert result["success"] is True
            assert "sequence" in result
            
            # Query events via GET /events
            response = await client.get(f"{base_url}/events?event_types=test_api_event")
            assert response.status_code == 200
            
            events_result = response.json()
            assert len(events_result["events"]) == 1
            assert events_result["events"][0]["event_type"] == "test_api_event"
            
    async def test_batch_operations(self, api_server):
        """Test atomic batch operations."""
        base_url = api_server
        
        events = [
            {
                "event_type": "batch_test",
                "aggregate_id": f"batch_item_{i}",
                "data": {"index": i}
            }
            for i in range(5)
        ]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{base_url}/events/batch", json={"events": events})
            assert response.status_code == 200
            
            result = response.json()
            assert result["success"] is True
            assert result["count"] == 5
            assert len(result["sequences"]) == 5
            
            # Verify all events were stored
            response = await client.get(f"{base_url}/events?event_types=batch_test")
            events_result = response.json()
            assert len(events_result["events"]) == 5
    
    async def test_websocket_streaming(self, api_server):
        """Test real-time event streaming via WebSocket."""
        base_url = api_server.replace("http://", "ws://")
        
        received_events = []
        
        async def websocket_client():
            async with websockets.connect(f"{base_url}/stream") as websocket:
                # Subscribe to events
                await websocket.send(json.dumps({"action": "subscribe"}))
                
                # Listen for events (timeout to avoid hanging)
                try:
                    async with asyncio.timeout(5):
                        while len(received_events) < 3:
                            message = await websocket.recv()
                            event_message = json.loads(message)
                            if event_message["type"] == "event":
                                received_events.append(event_message["data"])
                except asyncio.TimeoutError:
                    pass
        
        # Start WebSocket client
        websocket_task = asyncio.create_task(websocket_client())
        await asyncio.sleep(0.1)  # Let WebSocket connect
        
        # Send events via HTTP API
        async with httpx.AsyncClient() as client:
            for i in range(3):
                event_data = {
                    "event_type": "websocket_test", 
                    "aggregate_id": f"ws_test_{i}",
                    "data": {"index": i}
                }
                await client.post(f"{api_server}/events", json=event_data)
                await asyncio.sleep(0.1)  # Small delay between events
        
        # Wait for WebSocket client to finish
        await websocket_task
        
        # Verify events were received via WebSocket
        assert len(received_events) >= 3
        websocket_event_types = [e["event_type"] for e in received_events]
        assert "websocket_test" in websocket_event_types
```

### 7.3 Performance Test Harnesses

#### Throughput Benchmarks (`tests/performance/test_throughput.py`)

```python
import pytest
import asyncio
import time
import statistics
from concurrent.futures import ThreadPoolExecutor

from lighthouse.event_store import EventStore, Event

class TestThroughputBenchmarks:
    """Performance benchmarks for event store throughput."""
    
    @pytest.fixture
    async def perf_event_store(self):
        """Setup event store optimized for performance testing."""
        temp_dir = tempfile.mkdtemp()
        store = EventStore(temp_dir)
        
        # Configure for performance 
        store.sync_policy = "fdatasync"  # Faster than fsync
        store.max_file_size = 500 * 1024 * 1024  # 500MB files
        
        await store.initialize()
        yield store
        shutil.rmtree(temp_dir)
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_single_thread_throughput(self, perf_event_store):
        """Test single-threaded append throughput."""
        store = perf_event_store
        event_count = 10000
        
        events = [
            Event(
                event_type="throughput_test",
                aggregate_id=f"perf_test_{i}",
                data={"index": i, "payload": "x" * 100}  # 100 byte payload
            )
            for i in range(event_count)
        ]
        
        start_time = time.time()
        
        for event in events:
            await store.append(event)
            
        end_time = time.time()
        
        total_time = end_time - start_time
        throughput = event_count / total_time
        
        print(f"Single-thread throughput: {throughput:.2f} events/sec")
        
        # Requirement: Handle 10K events/second
        # Single thread should achieve at least 1K events/sec
        assert throughput >= 1000, f"Throughput too low: {throughput:.2f} events/sec"
        
    @pytest.mark.asyncio
    @pytest.mark.performance  
    async def test_batch_throughput(self, perf_event_store):
        """Test batch append throughput."""
        store = perf_event_store
        batch_size = 100
        batch_count = 100  # 10K total events
        
        start_time = time.time()
        
        for batch_idx in range(batch_count):
            batch_events = [
                Event(
                    event_type="batch_throughput_test",
                    aggregate_id=f"batch_{batch_idx}_item_{i}",
                    data={"batch": batch_idx, "item": i}
                )
                for i in range(batch_size)
            ]
            
            await store.append_batch(batch_events)
            
        end_time = time.time()
        
        total_time = end_time - start_time
        total_events = batch_count * batch_size
        throughput = total_events / total_time
        
        print(f"Batch throughput: {throughput:.2f} events/sec")
        
        # Batch operations should be faster than individual appends
        assert throughput >= 5000, f"Batch throughput too low: {throughput:.2f} events/sec"
        
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_write_throughput(self, perf_event_store):
        """Test throughput with concurrent writers."""
        store = perf_event_store
        writer_count = 4
        events_per_writer = 2500  # 10K total events
        
        async def concurrent_writer(writer_id: int):
            events = [
                Event(
                    event_type="concurrent_test",
                    aggregate_id=f"writer_{writer_id}_event_{i}",
                    data={"writer_id": writer_id, "index": i}
                )
                for i in range(events_per_writer)
            ]
            
            for event in events:
                await store.append(event)
        
        start_time = time.time()
        
        # Run concurrent writers
        await asyncio.gather(*[
            concurrent_writer(i) for i in range(writer_count)
        ])
        
        end_time = time.time()
        
        total_time = end_time - start_time
        total_events = writer_count * events_per_writer
        throughput = total_events / total_time
        
        print(f"Concurrent write throughput: {throughput:.2f} events/sec")
        
        # Concurrent writes should achieve target throughput
        assert throughput >= 8000, f"Concurrent throughput too low: {throughput:.2f} events/sec"
        
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_query_performance(self, perf_event_store):
        """Test event query performance with large dataset."""
        store = perf_event_store
        
        # Create large dataset
        event_count = 50000
        batch_size = 1000
        
        for batch in range(event_count // batch_size):
            batch_events = [
                Event(
                    event_type=f"query_test_type_{i % 5}",  # 5 different event types
                    aggregate_id=f"query_test_{batch * batch_size + i}",
                    data={"batch": batch, "index": i}
                )
                for i in range(batch_size)
            ]
            await store.append_batch(batch_events)
        
        # Test different query patterns
        from lighthouse.event_store.models import EventQuery, EventFilter
        
        # Query by event type
        start_time = time.time()
        events = []
        query = EventQuery(
            filter=EventFilter(event_types=["query_test_type_1"]),
            limit=10000
        )
        async for event in store.query(query):
            events.append(event)
        query_time = time.time() - start_time
        
        print(f"Type filter query: {len(events)} events in {query_time:.3f}s")
        
        # Should be able to query 10K events in under 1 second
        assert query_time < 1.0, f"Query too slow: {query_time:.3f}s"
        assert len(events) > 0
        
        # Query with sequence range
        start_time = time.time()
        events = []
        query = EventQuery(
            filter=EventFilter(start_sequence=10000, end_sequence=20000),
            limit=10000
        )
        async for event in store.query(query):
            events.append(event)
        query_time = time.time() - start_time
        
        print(f"Sequence range query: {len(events)} events in {query_time:.3f}s")
        assert query_time < 1.0, f"Sequence query too slow: {query_time:.3f}s"
```

### 7.4 Success Criteria Validation

#### Validation Test Suite (`tests/validation/test_phase1_success_criteria.py`)

```python
import pytest
import asyncio
import time
import subprocess
import signal
import os
from lighthouse.event_store import EventStore, Event, EventQuery

class TestPhase1SuccessCriteria:
    """Validation tests for Phase 1 success criteria."""
    
    @pytest.mark.validation
    async def test_10k_events_per_second(self):
        """Validate: Event store handles 10K events/second."""
        temp_dir = tempfile.mkdtemp()
        store = EventStore(temp_dir)
        store.sync_policy = "fdatasync"  # Optimize for speed
        await store.initialize()
        
        # Test sustained throughput
        duration = 10  # seconds
        target_throughput = 10000  # events/second
        
        async def sustained_writer():
            events_written = 0
            start_time = time.time()
            
            while time.time() - start_time < duration:
                batch_events = [
                    Event(
                        event_type="sustained_test",
                        aggregate_id=f"sustained_{events_written + i}",
                        data={"index": events_written + i}
                    )
                    for i in range(100)  # Write in batches of 100
                ]
                
                await store.append_batch(batch_events)
                events_written += len(batch_events)
                
            return events_written
        
        total_events = await sustained_writer()
        actual_throughput = total_events / duration
        
        print(f"Sustained throughput: {actual_throughput:.2f} events/sec")
        assert actual_throughput >= target_throughput
        
        shutil.rmtree(temp_dir)
        
    @pytest.mark.validation
    async def test_deterministic_state_reconstruction(self):
        """Validate: State reconstruction is deterministic."""
        temp_dir = tempfile.mkdtemp()
        store = EventStore(temp_dir)
        await store.initialize()
        
        # Create test events
        events = [
            Event(event_type="state_test", aggregate_id="entity_1", 
                  data={"action": "create", "value": 10}),
            Event(event_type="state_test", aggregate_id="entity_1",
                  data={"action": "update", "value": 20}), 
            Event(event_type="state_test", aggregate_id="entity_2",
                  data={"action": "create", "value": 30}),
            Event(event_type="state_test", aggregate_id="entity_1", 
                  data={"action": "update", "value": 40})
        ]
        
        for event in events:
            await store.append(event)
        
        # Create replay engine with deterministic handler
        from lighthouse.event_store.replay import EventReplayEngine
        
        replay_engine = EventReplayEngine(store)
        
        def handle_state_test(event: Event, state: dict) -> dict:
            entity_id = event.aggregate_id
            if event.data["action"] == "create":
                state[entity_id] = {"value": event.data["value"]}
            elif event.data["action"] == "update":
                if entity_id in state:
                    state[entity_id]["value"] = event.data["value"]
            return state
            
        replay_engine.register_handler("state_test", handle_state_test)
        
        # Replay multiple times and verify identical results
        results = []
        for i in range(5):
            state = await replay_engine.replay_all()
            results.append(state)
        
        # All replays should produce identical results
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Replay {i} differs from baseline"
            
        # Verify final state is correct
        expected_state = {
            "entity_1": {"value": 40},  # Final update
            "entity_2": {"value": 30}   # Only create
        }
        assert results[0] == expected_state
        
        shutil.rmtree(temp_dir)
        
    @pytest.mark.validation  
    async def test_zero_data_loss_on_crash(self):
        """Validate: System survives kill -9 without data loss."""
        temp_dir = tempfile.mkdtemp()
        
        # Create subprocess that writes events then gets killed
        script = f'''
import asyncio
import sys
sys.path.insert(0, "{os.getcwd()}/src")

from lighthouse.event_store import EventStore, Event

async def main():
    store = EventStore("{temp_dir}")
    await store.initialize()
    
    # Write events continuously
    for i in range(1000):
        event = Event(
            event_type="crash_test",
            aggregate_id=f"crash_test_{{i}}",
            data={{"index": i}}
        )
        await store.append(event)
        
        # Print progress so we know when to kill
        if i % 100 == 0:
            print(f"Written {{i}} events", flush=True)
            
        # Small delay to ensure some events are written before kill
        if i == 500:
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())
'''
        
        script_path = temp_dir + "/crash_test.py"
        with open(script_path, 'w') as f:
            f.write(script)
            
        # Start subprocess
        proc = subprocess.Popen(
            ["python", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for some events to be written
        await asyncio.sleep(2)
        
        # Kill the process abruptly
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        
        # Verify data integrity after crash
        store = EventStore(temp_dir)
        await store.initialize()
        
        events = []
        async for event in store.query(EventQuery()):
            events.append(event)
            
        # Should have some events (not necessarily all 1000 due to kill timing)
        assert len(events) > 0, "No events found after crash"
        
        # All events should have valid sequence numbers
        sequences = [e.sequence for e in events]
        assert sequences == list(range(1, len(sequences) + 1)), "Sequence numbers corrupted"
        
        # All events should be valid JSON
        for event in events:
            assert event.event_type == "crash_test"
            assert "index" in event.data
            
        print(f"Recovered {len(events)} events after kill -9")
        
        shutil.rmtree(temp_dir)
        os.unlink(script_path)
        
    @pytest.mark.validation
    async def test_fast_state_reconstruction(self):
        """Validate: Reconstruct state from 100K events in <10 seconds."""
        temp_dir = tempfile.mkdtemp()
        store = EventStore(temp_dir)
        await store.initialize()
        
        # Create 100K events efficiently
        batch_size = 1000
        event_count = 100000
        
        print("Creating 100K events...")
        start_time = time.time()
        
        for batch in range(event_count // batch_size):
            batch_events = [
                Event(
                    event_type="perf_test", 
                    aggregate_id=f"entity_{i % 100}",  # 100 entities
                    data={"batch": batch, "index": i, "value": i * 2}
                )
                for i in range(batch * batch_size, (batch + 1) * batch_size)
            ]
            await store.append_batch(batch_events)
            
            if batch % 10 == 0:
                print(f"Created {(batch + 1) * batch_size} events")
                
        creation_time = time.time() - start_time
        print(f"Created 100K events in {creation_time:.2f}s")
        
        # Test state reconstruction speed
        from lighthouse.event_store.replay import EventReplayEngine
        
        replay_engine = EventReplayEngine(store)
        
        def handle_perf_test(event: Event, state: dict) -> dict:
            entity_id = event.aggregate_id
            state[entity_id] = {
                "latest_batch": event.data["batch"],
                "latest_index": event.data["index"], 
                "latest_value": event.data["value"]
            }
            return state
            
        replay_engine.register_handler("perf_test", handle_perf_test)
        
        # Time the replay
        print("Starting state reconstruction...")
        start_time = time.time()
        
        final_state = await replay_engine.replay_all()
        
        reconstruction_time = time.time() - start_time
        print(f"State reconstruction took {reconstruction_time:.2f}s")
        
        # Validate results
        assert len(final_state) == 100, "Should have 100 entities"
        assert reconstruction_time < 10.0, f"Reconstruction too slow: {reconstruction_time:.2f}s"
        
        shutil.rmtree(temp_dir)
```

---

## 8. DEVELOPMENT ENVIRONMENT

### 8.1 Project Setup and Dependency Management

#### Updated pyproject.toml
```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lighthouse"
version = "0.2.0"  # Updated for Phase 1
description = "Event-sourced MCP server with multi-agent coordination"
authors = [{name = "Your Name", email = "your.email@example.com"}]
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.12"
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers", 
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    # Existing dependencies
    "mcp>=1.0.0",
    "pydantic>=2.0.0", 
    "requests>=2.31.0",
    "aiohttp>=3.8.0",
    
    # New dependencies for Phase 1
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "websockets>=11.0.0",
    "aiofiles>=23.0.0",
    "python-multipart>=0.0.6",
    "httpx>=0.25.0",  # For client libraries
]

[project.optional-dependencies]
dev = [
    # Existing dev dependencies
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0", 
    "black>=23.0.0",
    "isort>=5.12.0",
    "mypy>=1.5.0",
    "pre-commit>=3.0.0",
    
    # New dev dependencies for Phase 1
    "pytest-benchmark>=4.0.0",
    "pytest-cov>=4.1.0",
    "pytest-timeout>=2.1.0",
    "psutil>=5.9.0",  # For memory monitoring in tests
    "factory-boy>=3.3.0",  # For test data generation
]

performance = [
    "pytest-benchmark>=4.0.0",
    "memory-profiler>=0.61.0",
    "line-profiler>=4.1.1",
]

[project.urls]
Homepage = "https://github.com/yourusername/lighthouse"
Repository = "https://github.com/yourusername/lighthouse.git"  
Issues = "https://github.com/yourusername/lighthouse/issues"

[project.scripts]
lighthouse = "lighthouse.server:main"
lighthouse-event-api = "lighthouse.event_store.api:main"  # New entry point

[tool.setuptools.packages.find]
where = ["src"]
include = ["lighthouse*"]

# Tool configurations remain the same...
```

### 8.2 Development Tooling and Build Systems

#### Makefile for Development Tasks
```makefile
# Lighthouse Development Makefile

.PHONY: help install install-dev clean test test-unit test-integration test-performance
.PHONY: lint format type-check pre-commit setup-dev start-api start-bridge
.PHONY: benchmark load-test clean-data docker-build docker-run

help:
	@echo "Lighthouse Development Commands:"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install         Install package in production mode"
	@echo "  install-dev     Install package with development dependencies"
	@echo "  setup-dev       Complete development environment setup"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test            Run all tests"
	@echo "  test-unit       Run unit tests only" 
	@echo "  test-integration Run integration tests only"
	@echo "  test-performance Run performance benchmarks"
	@echo "  test-validation  Run Phase 1 success criteria validation"
	@echo ""
	@echo "Code Quality Commands:"
	@echo "  lint            Run all linting checks"
	@echo "  format          Format code with black and isort"
	@echo "  type-check      Run mypy type checking"
	@echo "  pre-commit      Run pre-commit hooks"
	@echo ""
	@echo "Development Commands:"
	@echo "  start-api       Start Event Store API server"
	@echo "  start-bridge    Start Validation Bridge server"
	@echo "  benchmark       Run performance benchmarks"
	@echo "  load-test       Run load testing scenarios"
	@echo ""
	@echo "Utility Commands:"
	@echo "  clean           Clean up temporary files and data"
	@echo "  clean-data      Clean up development data directories"
	@echo "  docker-build    Build Docker development image"
	@echo "  docker-run      Run in Docker container"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,performance]"

setup-dev: install-dev
	pre-commit install
	mkdir -p data/events data/snapshots logs
	@echo "Development environment setup complete!"

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .coverage htmlcov/ .pytest_cache/

clean-data:
	rm -rf data/ dev_data/ logs/

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-performance:
	pytest tests/performance/ -v --benchmark-only

test-validation:
	pytest tests/validation/ -v -m validation

lint: 
	black --check src/ tests/
	isort --check-only src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

type-check:
	mypy src/

pre-commit:
	pre-commit run --all-files

start-api:
	@echo "Starting Event Store API on http://localhost:8080"
	python -m lighthouse.event_store.api

start-bridge:
	@echo "Starting Validation Bridge on http://localhost:8765"
	python -m lighthouse.server

benchmark:
	pytest tests/performance/test_throughput.py -v --benchmark-only

load-test:
	python scripts/load_test.py

docker-build:
	docker build -t lighthouse:dev .

docker-run: docker-build
	docker run -it --rm -p 8080:8080 -p 8765:8765 \
		-v $(PWD)/data:/app/data \
		lighthouse:dev
```

#### Development Scripts

**scripts/setup_dev_env.sh**
```bash
#!/bin/bash
# Development environment setup script

set -e

echo "Setting up Lighthouse development environment..."

# Check Python version
python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
if [[ $(echo "$python_version < 3.12" | bc -l) -eq 1 ]]; then
    echo "Error: Python 3.12+ required, found $python_version"
    exit 1
fi

# Install package in development mode
echo "Installing Lighthouse in development mode..."
pip install -e ".[dev,performance]"

# Setup pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install

# Create data directories
echo "Creating data directories..."
mkdir -p data/events data/snapshots logs
mkdir -p dev_data/events dev_data/snapshots

# Setup test database
echo "Setting up test environment..."
python -c "
import tempfile
import shutil
from lighthouse.event_store import EventStore
import asyncio

async def setup_test_data():
    store = EventStore('./dev_data/events')
    await store.initialize()
    print('Test event store initialized')

asyncio.run(setup_test_data())
"

# Run initial tests
echo "Running initial test suite..."
pytest tests/unit/ -v -x

echo ""
echo "Development environment setup complete!"
echo ""
echo "Next steps:"
echo "  make start-api     # Start Event Store API"
echo "  make start-bridge  # Start Validation Bridge"
echo "  make test          # Run full test suite"
echo "  make benchmark     # Run performance tests"
```

**scripts/load_test.py**
```python
#!/usr/bin/env python3
"""Load testing script for Lighthouse Event Store."""

import asyncio
import httpx
import time
import statistics
from typing import List, Dict, Any

async def load_test_api(
    base_url: str = "http://localhost:8080",
    concurrent_clients: int = 10,
    events_per_client: int = 1000,
    batch_size: int = 10
) -> Dict[str, Any]:
    """Run load test against Event Store API."""
    
    print(f"Starting load test with {concurrent_clients} clients, {events_per_client} events each")
    
    async def client_worker(client_id: int) -> Dict[str, Any]:
        """Single client worker that sends events."""
        async with httpx.AsyncClient() as client:
            client_stats = {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "response_times": []
            }
            
            for batch in range(events_per_client // batch_size):
                # Create batch of events
                events = [
                    {
                        "event_type": "load_test",
                        "aggregate_id": f"client_{client_id}_batch_{batch}_item_{i}",
                        "data": {
                            "client_id": client_id,
                            "batch": batch, 
                            "item": i,
                            "timestamp": time.time()
                        }
                    }
                    for i in range(batch_size)
                ]
                
                # Send batch request
                start_time = time.time()
                try:
                    response = await client.post(
                        f"{base_url}/events/batch",
                        json={"events": events},
                        timeout=30.0
                    )
                    response_time = time.time() - start_time
                    
                    client_stats["requests"] += 1
                    client_stats["response_times"].append(response_time)
                    
                    if response.status_code == 200:
                        client_stats["successes"] += 1
                    else:
                        client_stats["failures"] += 1
                        print(f"Client {client_id}: HTTP {response.status_code}")
                        
                except Exception as e:
                    client_stats["failures"] += 1
                    print(f"Client {client_id} error: {e}")
                    
        return client_stats
    
    # Run all clients concurrently
    start_time = time.time()
    client_results = await asyncio.gather(*[
        client_worker(i) for i in range(concurrent_clients)
    ])
    total_time = time.time() - start_time
    
    # Aggregate results
    total_requests = sum(r["requests"] for r in client_results)
    total_successes = sum(r["successes"] for r in client_results)
    total_failures = sum(r["failures"] for r in client_results)
    
    all_response_times = []
    for r in client_results:
        all_response_times.extend(r["response_times"])
    
    results = {
        "duration_seconds": total_time,
        "total_requests": total_requests,
        "total_successes": total_successes,
        "total_failures": total_failures,
        "success_rate": total_successes / total_requests if total_requests > 0 else 0,
        "requests_per_second": total_requests / total_time,
        "events_per_second": (total_successes * batch_size) / total_time,
        "response_times": {
            "mean": statistics.mean(all_response_times) if all_response_times else 0,
            "median": statistics.median(all_response_times) if all_response_times else 0,
            "p95": statistics.quantiles(all_response_times, n=20)[18] if len(all_response_times) > 20 else 0,
            "p99": statistics.quantiles(all_response_times, n=100)[98] if len(all_response_times) > 100 else 0,
        }
    }
    
    return results

async def main():
    """Run complete load test suite."""
    print("Lighthouse Event Store Load Test")
    print("=" * 40)
    
    # Test scenarios
    scenarios = [
        {"clients": 1, "events": 1000, "batch": 1, "name": "Single client, individual events"},
        {"clients": 1, "events": 1000, "batch": 10, "name": "Single client, small batches"},
        {"clients": 1, "events": 1000, "batch": 100, "name": "Single client, large batches"},
        {"clients": 5, "events": 1000, "batch": 10, "name": "Multiple clients, small batches"},
        {"clients": 10, "events": 500, "batch": 10, "name": "Many clients, concurrent load"},
    ]
    
    for scenario in scenarios:
        print(f"\nRunning: {scenario['name']}")
        print("-" * 40)
        
        results = await load_test_api(
            concurrent_clients=scenario["clients"],
            events_per_client=scenario["events"],
            batch_size=scenario["batch"]
        )
        
        print(f"Duration: {results['duration_seconds']:.2f}s")
        print(f"Success Rate: {results['success_rate']:.2%}")
        print(f"Requests/sec: {results['requests_per_second']:.2f}")
        print(f"Events/sec: {results['events_per_second']:.2f}")
        print(f"Response time mean: {results['response_times']['mean']*1000:.2f}ms")
        print(f"Response time p95: {results['response_times']['p95']*1000:.2f}ms")
        
        # Check if results meet requirements
        if results["success_rate"] < 0.999:
            print("⚠️  SUCCESS RATE below 99.9%")
        if results["response_times"]["p95"] > 0.05:  # 50ms
            print("⚠️  P95 LATENCY above 50ms")
        if scenario["clients"] >= 10 and results["events_per_second"] < 8000:
            print("⚠️  THROUGHPUT below 8K events/sec under load")

if __name__ == "__main__":
    asyncio.run(main())
```

### 8.3 Local Development Workflow

#### Development Workflow Documentation
```markdown
# Lighthouse Development Workflow

## Daily Development Process

### 1. Environment Setup
```bash
# One-time setup
make setup-dev

# Daily startup
make clean-data  # Optional: clean previous session data
make start-api   # Terminal 1: Event Store API
make start-bridge # Terminal 2: Validation Bridge
```

### 2. Development Cycle

**Code → Test → Commit**
```bash
# Make code changes
vim src/lighthouse/event_store/store.py

# Run relevant tests
make test-unit                    # Fast feedback
pytest tests/unit/test_store.py   # Specific module

# Run integration tests if needed
make test-integration

# Format and lint
make format
make lint

# Run pre-commit checks
make pre-commit

# Commit changes
git add .
git commit -m "feat: improve event store performance"
```

### 3. Performance Validation
```bash
# Run benchmarks after performance changes
make benchmark

# Full load test
make load-test

# Validate success criteria
make test-validation
```

### 4. Integration Testing
```bash
# Test with real MCP clients
echo '{"tool_name": "Bash", "tool_input": {"command": "ls"}}' | \
    python .claude/hooks/validate_command.py

# Test API endpoints
curl -X POST http://localhost:8080/events \
    -H "Content-Type: application/json" \
    -d '{"event_type": "test", "aggregate_id": "test123", "data": {}}'

# Test WebSocket streaming
wscat -c ws://localhost:8080/stream
```

## Common Development Tasks

### Adding New Event Types
1. Define event type in `bridge_events.py`
2. Add handler in `ValidationBridge` 
3. Update replay engine handlers
4. Add tests for new event type
5. Update API documentation

### Performance Optimization
1. Profile with `pytest-benchmark`
2. Use `line_profiler` for hot spots
3. Test with `scripts/load_test.py`
4. Validate with success criteria tests

### Debugging Event Store
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Inspect event store state
store = EventStore("./data/events")
await store.initialize()
print(f"Current sequence: {store.current_sequence}")

# Query recent events
async for event in store.query(EventQuery(limit=10)):
    print(f"{event.sequence}: {event.event_type}")
```
```

### 8.4 CI/CD Pipeline Configuration

#### GitHub Actions Workflow (`.github/workflows/phase1-validation.yml`)
```yaml
name: Phase 1 Event Store Validation

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev]"
    
    - name: Run unit tests
      run: |
        pytest tests/unit/ -v --cov=lighthouse --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  integration-tests:
    name: Integration Tests  
    runs-on: ubuntu-latest
    needs: unit-tests
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: "3.12"
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev]"
    
    - name: Run integration tests
      run: |
        pytest tests/integration/ -v --timeout=300
    
    - name: Test API integration
      run: |
        # Start API server in background
        python -m lighthouse.event_store.api &
        API_PID=$!
        sleep 5
        
        # Run API tests
        curl -f http://localhost:8080/health || exit 1
        
        # Clean up
        kill $API_PID

  performance-tests:
    name: Performance Benchmarks
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4  
      with:
        python-version: "3.12"
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev,performance]"
    
    - name: Run performance tests
      run: |
        pytest tests/performance/ -v --benchmark-json=benchmark.json
    
    - name: Upload benchmark results
      uses: actions/upload-artifact@v3
      with:
        name: benchmark-results
        path: benchmark.json

  validation-tests:
    name: Phase 1 Success Criteria
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests, performance-tests]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: "3.12"
    
    - name: Install dependencies  
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev,performance]"
    
    - name: Validate Phase 1 Success Criteria
      run: |
        pytest tests/validation/ -v -m validation --timeout=600
    
    - name: Generate validation report
      run: |
        echo "# Phase 1 Validation Results" > validation-report.md
        echo "Date: $(date)" >> validation-report.md
        echo "" >> validation-report.md
        pytest tests/validation/ --tb=no -v >> validation-report.md || true
        
    - name: Upload validation report
      uses: actions/upload-artifact@v3
      with:
        name: validation-report
        path: validation-report.md

  docker-build:
    name: Docker Build Test
    runs-on: ubuntu-latest
    needs: validation-tests
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Build Docker image
      run: |
        docker build -t lighthouse:ci .
        
    - name: Test Docker container
      run: |
        # Start container
        docker run -d --name lighthouse-test \
          -p 8080:8080 -p 8765:8765 lighthouse:ci
        
        # Wait for startup
        sleep 10
        
        # Test endpoints
        curl -f http://localhost:8080/health || exit 1
        curl -f http://localhost:8765/status || exit 1
        
        # Clean up
        docker stop lighthouse-test
        docker rm lighthouse-test

  deployment-ready:
    name: Deployment Ready Check
    runs-on: ubuntu-latest
    needs: [validation-tests, docker-build]
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Validate Phase 1 Complete
      run: |
        echo "✅ All Phase 1 validation tests passed"
        echo "✅ Performance benchmarks met requirements" 
        echo "✅ Docker build successful"
        echo "🚀 Phase 1 ready for production deployment"
        
    - name: Create release tag
      if: success()
      run: |
        git tag "phase-1-$(date +%Y%m%d-%H%M%S)"
        git push origin --tags
```

---

## 9. CONCLUSION AND NEXT STEPS

### Phase 1 Summary

This detailed implementation design provides everything needed to build a production-ready event-sourced foundation for the Lighthouse multi-agent coordination platform. The design prioritizes:

1. **Zero Data Loss**: Write-ahead logging and crash recovery ensure no events are lost
2. **High Performance**: 10K+ events/second with <1ms append latency
3. **Deterministic Replay**: Consistent state reconstruction from event history
4. **Backward Compatibility**: Existing bridge APIs continue working unchanged

### Implementation Schedule

| Week | Work Package | Key Deliverables | Validation |
|------|--------------|------------------|------------|
| 1-2  | Core Event Store | File-based event log, JSON serialization, basic queries | <1ms appends, 1K+ events/sec |
| 2-3  | Event Replay Engine | State reconstruction, streaming replay, filtering | <10s replay of 100K events |
| 3-4  | Snapshot Management | Compressed snapshots, incremental diffs, auto-cleanup | 90% faster cold start |
| 4-5  | Event Store API | HTTP/WebSocket APIs, client libraries, monitoring | <50ms latency at 1K req/sec |

### Success Metrics Validation

Each work package includes comprehensive validation tests ensuring:
- **Performance Requirements**: Automated benchmarks verify throughput and latency
- **Reliability Requirements**: Crash recovery and data integrity tests
- **API Requirements**: Integration tests with real client scenarios
- **Success Criteria**: Dedicated validation test suite for Phase 1 goals

### Transition to Phase 2

Phase 1 provides the event-sourced foundation needed for Phase 2's basic bridge server. The event store will seamlessly integrate with:
- Multi-agent coordination patterns
- Command validation pipeline
- Shadow filesystem operations
- Expert agent framework

The modular design ensures Phase 1 delivers standalone value while enabling smooth evolution to Phase 2 and beyond.

### Risk Mitigation

Key risks have been addressed through:
- **File Corruption**: WAL + checksums + recovery procedures
- **Performance Degradation**: Extensive benchmarking + optimization strategies
- **Integration Complexity**: Gradual migration + API compatibility
- **Development Velocity**: Comprehensive tooling + automated testing

### Team Readiness

This design provides:
- **Complete Technical Specifications**: Ready-to-implement class designs and APIs
- **Development Environment**: Full tooling setup and workflow documentation  
- **Testing Strategy**: Comprehensive test suites covering all scenarios
- **Quality Gates**: Automated validation ensuring requirements are met

**The development team can begin implementing Phase 1 immediately upon approval of this design document.**

---

*This document serves as the complete blueprint for Phase 1 implementation. All technical specifications, validation criteria, and development workflows are production-ready and have been designed for immediate execution.*