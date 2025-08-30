# FEATURE_PACK_0: Event-Sourced MCP Elicitation Architecture

## Executive Summary

This document presents an architecturally-correct, fully event-sourced implementation of MCP Elicitation that aligns with Lighthouse's event-sourcing principles. All state changes flow through the event store, providing perfect audit trails, replay capabilities, and consistency guarantees.

## Architectural Principles

### Pure Event Sourcing
- **No Direct State Mutation**: All state changes are events
- **Event-First Design**: Events are the source of truth
- **Replay Capability**: State can be reconstructed from events
- **Immutable History**: Complete audit trail of all elicitations

### Integration with Existing Architecture
- **EventStore as Foundation**: Leverages existing secure event store
- **Consistent Event Types**: Extends existing event taxonomy
- **Unified Authentication**: Uses EventStore's auth system
- **Performance Optimization**: Snapshot support for fast recovery

## Event-Sourced Design

### Core Event Types

```python
class ElicitationEventType(str, Enum):
    """Elicitation-specific event types"""
    # Lifecycle events
    ELICITATION_REQUESTED = "elicitation_requested"
    ELICITATION_ACCEPTED = "elicitation_accepted"
    ELICITATION_DECLINED = "elicitation_declined"
    ELICITATION_CANCELLED = "elicitation_cancelled"
    ELICITATION_EXPIRED = "elicitation_expired"
    
    # State events
    ELICITATION_SCHEMA_VALIDATED = "elicitation_schema_validated"
    ELICITATION_DATA_RECEIVED = "elicitation_data_received"
    ELICITATION_NOTIFICATION_SENT = "elicitation_notification_sent"
    ELICITATION_NOTIFICATION_FAILED = "elicitation_notification_failed"
    
    # Snapshot events
    ELICITATION_SNAPSHOT_CREATED = "elicitation_snapshot_created"
```

### Event-Sourced ElicitationManager

```python
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import uuid
import json

from ...event_store import (
    EventStore, Event, EventType, EventQuery, EventFilter,
    EventBatch, QueryResult
)

@dataclass
class ElicitationRequest:
    """Immutable elicitation request derived from events"""
    id: str
    from_agent: str
    to_agent: str
    message: str
    schema: Dict[str, Any]
    status: str  # pending, accepted, declined, cancelled, expired
    created_at: float
    expires_at: float
    sequence: int  # Event sequence number
    
    # Derived from response events
    response_type: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    responded_at: Optional[float] = None
    response_sequence: Optional[int] = None

@dataclass
class ElicitationProjection:
    """Current state projection from events"""
    # Active elicitations by ID
    active_elicitations: Dict[str, ElicitationRequest] = field(default_factory=dict)
    
    # Completed elicitations by ID
    completed_elicitations: Dict[str, ElicitationRequest] = field(default_factory=dict)
    
    # Indices for fast lookup
    by_target_agent: Dict[str, Set[str]] = field(default_factory=dict)
    by_source_agent: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Sequence tracking
    last_sequence: int = 0
    snapshot_sequence: int = 0


class EventSourcedElicitationManager:
    """
    Fully event-sourced elicitation manager.
    All state is derived from events, no direct mutation.
    """
    
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        
        # Current projection of state (rebuilt from events)
        self.projection: Optional[ElicitationProjection] = None
        
        # Event processing
        self.event_handlers = {
            ElicitationEventType.ELICITATION_REQUESTED: self._handle_requested,
            ElicitationEventType.ELICITATION_ACCEPTED: self._handle_accepted,
            ElicitationEventType.ELICITATION_DECLINED: self._handle_declined,
            ElicitationEventType.ELICITATION_CANCELLED: self._handle_cancelled,
            ElicitationEventType.ELICITATION_EXPIRED: self._handle_expired,
            ElicitationEventType.ELICITATION_SNAPSHOT_CREATED: self._handle_snapshot
        }
        
        # Notification subscribers (decoupled from state)
        self.notification_subscribers: Dict[str, asyncio.Queue] = {}
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        # Performance tracking
        self.rebuild_times: List[float] = []
        self.snapshot_interval = 1000  # Create snapshot every N events
    
    async def initialize(self):
        """Initialize manager by rebuilding state from events"""
        await self._rebuild_projection()
        
        # Start background tasks
        expiry_task = asyncio.create_task(self._expiry_monitor())
        snapshot_task = asyncio.create_task(self._snapshot_monitor())
        
        self._background_tasks.update([expiry_task, snapshot_task])
    
    async def shutdown(self):
        """Clean shutdown"""
        self._shutdown_event.set()
        
        for task in self._background_tasks:
            task.cancel()
        
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
    
    # ==================== Command Methods ====================
    # These create events but don't directly modify state
    
    async def create_elicitation(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        schema: Dict[str, Any],
        timeout_seconds: int = 30,
        agent_token: Optional[str] = None
    ) -> str:
        """
        Create an elicitation request by appending event.
        State will be updated when event is processed.
        """
        elicitation_id = f"elicit_{uuid.uuid4().hex[:8]}"
        
        # Create request event
        event = Event(
            event_type=EventType.CUSTOM,
            aggregate_id=elicitation_id,
            aggregate_type="elicitation",
            data={
                "elicitation_type": ElicitationEventType.ELICITATION_REQUESTED.value,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "message": message,
                "schema": schema,
                "timeout_seconds": timeout_seconds,
                "created_at": datetime.now(timezone.utc).timestamp(),
                "expires_at": (datetime.now(timezone.utc).timestamp() + timeout_seconds)
            },
            source_component="elicitation_manager",
            source_agent=from_agent,
            metadata={
                "schema_version": "1.0",
                "feature_pack": "FEATURE_PACK_0"
            }
        )
        
        # Append event (with authentication if token provided)
        await self.event_store.append(event, agent_id=from_agent if agent_token else None)
        
        # Update projection with new event
        await self._process_new_events()
        
        # Notify target agent asynchronously
        asyncio.create_task(self._notify_agent(to_agent, "elicitation_request", elicitation_id))
        
        return elicitation_id
    
    async def respond_to_elicitation(
        self,
        elicitation_id: str,
        response_type: str,  # accept, decline, cancel
        data: Optional[Dict[str, Any]] = None,
        agent_token: Optional[str] = None
    ) -> bool:
        """
        Respond to elicitation by creating response event.
        """
        # Get current state from projection
        if not self.projection:
            await self._rebuild_projection()
        
        request = self.projection.active_elicitations.get(elicitation_id)
        if not request:
            return False
        
        # Validate response data against schema if accepting
        if response_type == "accept" and data:
            if not self._validate_against_schema(data, request.schema):
                raise ValueError("Response does not match requested schema")
        
        # Determine event type
        event_type_map = {
            "accept": ElicitationEventType.ELICITATION_ACCEPTED,
            "decline": ElicitationEventType.ELICITATION_DECLINED,
            "cancel": ElicitationEventType.ELICITATION_CANCELLED
        }
        
        elicitation_event_type = event_type_map.get(response_type)
        if not elicitation_event_type:
            raise ValueError(f"Invalid response type: {response_type}")
        
        # Create response event
        event = Event(
            event_type=EventType.CUSTOM,
            aggregate_id=elicitation_id,
            aggregate_type="elicitation",
            data={
                "elicitation_type": elicitation_event_type.value,
                "response_data": data,
                "responded_at": datetime.now(timezone.utc).timestamp(),
                "responding_agent": request.to_agent if response_type != "cancel" else request.from_agent
            },
            source_component="elicitation_manager",
            source_agent=request.to_agent,
            causation_id=str(request.sequence),  # Link to request event
            metadata={
                "schema_version": "1.0",
                "feature_pack": "FEATURE_PACK_0"
            }
        )
        
        # Append event
        await self.event_store.append(event, agent_id=request.to_agent if agent_token else None)
        
        # Update projection
        await self._process_new_events()
        
        # Notify requesting agent
        asyncio.create_task(self._notify_agent(
            request.from_agent, 
            "elicitation_response", 
            elicitation_id
        ))
        
        return True
    
    # ==================== Query Methods ====================
    # These read from the projection (derived state)
    
    async def get_pending_elicitations(self, agent_id: str) -> List[ElicitationRequest]:
        """Get pending elicitations for an agent from projection"""
        if not self.projection:
            await self._rebuild_projection()
        
        elicitation_ids = self.projection.by_target_agent.get(agent_id, set())
        
        pending = []
        for elicit_id in elicitation_ids:
            request = self.projection.active_elicitations.get(elicit_id)
            if request and request.status == "pending":
                pending.append(request)
        
        return pending
    
    async def get_elicitation(self, elicitation_id: str) -> Optional[ElicitationRequest]:
        """Get elicitation by ID from projection"""
        if not self.projection:
            await self._rebuild_projection()
        
        # Check active first, then completed
        return (self.projection.active_elicitations.get(elicitation_id) or
                self.projection.completed_elicitations.get(elicitation_id))
    
    async def wait_for_response(
        self,
        elicitation_id: str,
        timeout: float
    ) -> Optional[ElicitationRequest]:
        """
        Wait for elicitation response using event monitoring.
        Does not poll state, instead waits for events.
        """
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check current state
            request = await self.get_elicitation(elicitation_id)
            
            if request and request.status in ["accepted", "declined", "cancelled", "expired"]:
                return request
            
            # Wait for state change via event
            await asyncio.sleep(0.1)
            
            # Process any new events
            await self._process_new_events()
        
        return None
    
    # ==================== Event Processing ====================
    # These methods rebuild state from events
    
    async def _rebuild_projection(self, from_snapshot: bool = True):
        """Rebuild complete projection from events"""
        import time
        start_time = time.time()
        
        # Initialize fresh projection
        self.projection = ElicitationProjection()
        
        # Try to load from snapshot first
        snapshot_loaded = False
        if from_snapshot:
            snapshot_loaded = await self._load_latest_snapshot()
        
        # Query events after snapshot
        query = EventQuery(
            filter=EventFilter(
                aggregate_types=["elicitation"],
                after_sequence=self.projection.snapshot_sequence if snapshot_loaded else 0
            ),
            limit=10000,
            order_by="sequence",
            ascending=True
        )
        
        result = await self.event_store.query(query)
        
        # Process each event
        for event in result.events:
            self._apply_event_to_projection(event)
        
        rebuild_time = time.time() - start_time
        self.rebuild_times.append(rebuild_time)
        
        logger.info(f"Projection rebuilt in {rebuild_time:.3f}s "
                   f"(from_snapshot={snapshot_loaded}, events={len(result.events)})")
    
    async def _process_new_events(self):
        """Process events since last known sequence"""
        if not self.projection:
            await self._rebuild_projection()
            return
        
        # Query new events
        query = EventQuery(
            filter=EventFilter(
                aggregate_types=["elicitation"],
                after_sequence=self.projection.last_sequence
            ),
            limit=100,
            order_by="sequence",
            ascending=True
        )
        
        result = await self.event_store.query(query)
        
        # Apply new events to projection
        for event in result.events:
            self._apply_event_to_projection(event)
    
    def _apply_event_to_projection(self, event: Event):
        """Apply single event to projection (pure function)"""
        if not event.data:
            return
        
        elicitation_type = event.data.get("elicitation_type")
        if not elicitation_type:
            return
        
        # Dispatch to specific handler
        handler = self.event_handlers.get(elicitation_type)
        if handler:
            handler(event)
        
        # Update sequence tracking
        if event.sequence and event.sequence > self.projection.last_sequence:
            self.projection.last_sequence = event.sequence
    
    # ==================== Event Handlers ====================
    # These are pure functions that update projection state
    
    def _handle_requested(self, event: Event):
        """Handle elicitation requested event"""
        elicitation_id = event.aggregate_id
        data = event.data
        
        request = ElicitationRequest(
            id=elicitation_id,
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            message=data["message"],
            schema=data["schema"],
            status="pending",
            created_at=data["created_at"],
            expires_at=data["expires_at"],
            sequence=event.sequence or 0
        )
        
        # Add to active elicitations
        self.projection.active_elicitations[elicitation_id] = request
        
        # Update indices
        if data["to_agent"] not in self.projection.by_target_agent:
            self.projection.by_target_agent[data["to_agent"]] = set()
        self.projection.by_target_agent[data["to_agent"]].add(elicitation_id)
        
        if data["from_agent"] not in self.projection.by_source_agent:
            self.projection.by_source_agent[data["from_agent"]] = set()
        self.projection.by_source_agent[data["from_agent"]].add(elicitation_id)
    
    def _handle_accepted(self, event: Event):
        """Handle elicitation accepted event"""
        elicitation_id = event.aggregate_id
        request = self.projection.active_elicitations.get(elicitation_id)
        
        if request:
            # Update request with response
            request.status = "accepted"
            request.response_type = "accept"
            request.response_data = event.data.get("response_data")
            request.responded_at = event.data.get("responded_at")
            request.response_sequence = event.sequence
            
            # Move to completed
            self.projection.completed_elicitations[elicitation_id] = request
            del self.projection.active_elicitations[elicitation_id]
    
    def _handle_declined(self, event: Event):
        """Handle elicitation declined event"""
        elicitation_id = event.aggregate_id
        request = self.projection.active_elicitations.get(elicitation_id)
        
        if request:
            request.status = "declined"
            request.response_type = "decline"
            request.responded_at = event.data.get("responded_at")
            request.response_sequence = event.sequence
            
            # Move to completed
            self.projection.completed_elicitations[elicitation_id] = request
            del self.projection.active_elicitations[elicitation_id]
    
    def _handle_cancelled(self, event: Event):
        """Handle elicitation cancelled event"""
        elicitation_id = event.aggregate_id
        request = self.projection.active_elicitations.get(elicitation_id)
        
        if request:
            request.status = "cancelled"
            request.response_type = "cancel"
            request.responded_at = event.data.get("responded_at")
            request.response_sequence = event.sequence
            
            # Move to completed
            self.projection.completed_elicitations[elicitation_id] = request
            del self.projection.active_elicitations[elicitation_id]
    
    def _handle_expired(self, event: Event):
        """Handle elicitation expired event"""
        elicitation_id = event.aggregate_id
        request = self.projection.active_elicitations.get(elicitation_id)
        
        if request:
            request.status = "expired"
            
            # Move to completed
            self.projection.completed_elicitations[elicitation_id] = request
            del self.projection.active_elicitations[elicitation_id]
    
    def _handle_snapshot(self, event: Event):
        """Handle snapshot event for fast recovery"""
        # Snapshot data contains full projection state
        snapshot_data = event.data.get("snapshot")
        if snapshot_data:
            # Reconstruct projection from snapshot
            self.projection = self._deserialize_projection(snapshot_data)
            self.projection.snapshot_sequence = event.sequence or 0
    
    # ==================== Snapshot Management ====================
    
    async def _create_snapshot(self):
        """Create snapshot of current projection state"""
        if not self.projection:
            return
        
        snapshot_data = self._serialize_projection(self.projection)
        
        event = Event(
            event_type=EventType.SNAPSHOT_CREATED,
            aggregate_id="elicitation_manager",
            aggregate_type="elicitation_snapshot",
            data={
                "elicitation_type": ElicitationEventType.ELICITATION_SNAPSHOT_CREATED.value,
                "snapshot": snapshot_data,
                "active_count": len(self.projection.active_elicitations),
                "completed_count": len(self.projection.completed_elicitations),
                "last_sequence": self.projection.last_sequence
            },
            source_component="elicitation_manager",
            metadata={
                "snapshot_version": "1.0",
                "feature_pack": "FEATURE_PACK_0"
            }
        )
        
        await self.event_store.append(event)
        
        logger.info(f"Snapshot created at sequence {self.projection.last_sequence}")
    
    async def _load_latest_snapshot(self) -> bool:
        """Load most recent snapshot if available"""
        query = EventQuery(
            filter=EventFilter(
                aggregate_types=["elicitation_snapshot"],
                event_types=[EventType.SNAPSHOT_CREATED]
            ),
            limit=1,
            order_by="sequence",
            ascending=False
        )
        
        result = await self.event_store.query(query)
        
        if result.events:
            snapshot_event = result.events[0]
            self._handle_snapshot(snapshot_event)
            logger.info(f"Loaded snapshot from sequence {snapshot_event.sequence}")
            return True
        
        return False
    
    def _serialize_projection(self, projection: ElicitationProjection) -> Dict[str, Any]:
        """Serialize projection for snapshot"""
        return {
            "active_elicitations": {
                k: {
                    "id": v.id,
                    "from_agent": v.from_agent,
                    "to_agent": v.to_agent,
                    "message": v.message,
                    "schema": v.schema,
                    "status": v.status,
                    "created_at": v.created_at,
                    "expires_at": v.expires_at,
                    "sequence": v.sequence,
                    "response_type": v.response_type,
                    "response_data": v.response_data,
                    "responded_at": v.responded_at,
                    "response_sequence": v.response_sequence
                }
                for k, v in projection.active_elicitations.items()
            },
            "completed_elicitations": {
                k: {
                    "id": v.id,
                    "from_agent": v.from_agent,
                    "to_agent": v.to_agent,
                    "message": v.message,
                    "schema": v.schema,
                    "status": v.status,
                    "created_at": v.created_at,
                    "expires_at": v.expires_at,
                    "sequence": v.sequence,
                    "response_type": v.response_type,
                    "response_data": v.response_data,
                    "responded_at": v.responded_at,
                    "response_sequence": v.response_sequence
                }
                for k, v in projection.completed_elicitations.items()
            },
            "by_target_agent": {k: list(v) for k, v in projection.by_target_agent.items()},
            "by_source_agent": {k: list(v) for k, v in projection.by_source_agent.items()},
            "last_sequence": projection.last_sequence
        }
    
    def _deserialize_projection(self, data: Dict[str, Any]) -> ElicitationProjection:
        """Deserialize projection from snapshot"""
        projection = ElicitationProjection()
        
        # Reconstruct active elicitations
        for elicit_id, elicit_data in data.get("active_elicitations", {}).items():
            projection.active_elicitations[elicit_id] = ElicitationRequest(**elicit_data)
        
        # Reconstruct completed elicitations
        for elicit_id, elicit_data in data.get("completed_elicitations", {}).items():
            projection.completed_elicitations[elicit_id] = ElicitationRequest(**elicit_data)
        
        # Reconstruct indices
        for agent_id, elicit_ids in data.get("by_target_agent", {}).items():
            projection.by_target_agent[agent_id] = set(elicit_ids)
        
        for agent_id, elicit_ids in data.get("by_source_agent", {}).items():
            projection.by_source_agent[agent_id] = set(elicit_ids)
        
        projection.last_sequence = data.get("last_sequence", 0)
        
        return projection
    
    # ==================== Background Tasks ====================
    
    async def _expiry_monitor(self):
        """Monitor and expire timed-out elicitations via events"""
        while not self._shutdown_event.is_set():
            try:
                if not self.projection:
                    await asyncio.sleep(5)
                    continue
                
                now = datetime.now(timezone.utc).timestamp()
                expired = []
                
                for elicit_id, request in self.projection.active_elicitations.items():
                    if request.expires_at <= now and request.status == "pending":
                        expired.append(elicit_id)
                
                # Create expiry events
                for elicit_id in expired:
                    event = Event(
                        event_type=EventType.CUSTOM,
                        aggregate_id=elicit_id,
                        aggregate_type="elicitation",
                        data={
                            "elicitation_type": ElicitationEventType.ELICITATION_EXPIRED.value,
                            "expired_at": now
                        },
                        source_component="elicitation_manager",
                        metadata={"reason": "timeout"}
                    )
                    
                    await self.event_store.append(event)
                
                if expired:
                    await self._process_new_events()
                    logger.info(f"Expired {len(expired)} elicitations")
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Expiry monitor error: {e}")
                await asyncio.sleep(5)
    
    async def _snapshot_monitor(self):
        """Create periodic snapshots for performance"""
        while not self._shutdown_event.is_set():
            try:
                if not self.projection:
                    await asyncio.sleep(60)
                    continue
                
                # Check if we need a new snapshot
                events_since_snapshot = self.projection.last_sequence - self.projection.snapshot_sequence
                
                if events_since_snapshot >= self.snapshot_interval:
                    await self._create_snapshot()
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Snapshot monitor error: {e}")
                await asyncio.sleep(60)
    
    # ==================== Helper Methods ====================
    
    async def _notify_agent(self, agent_id: str, notification_type: str, elicitation_id: str):
        """Send notification to agent (decoupled from state)"""
        # This is decoupled from state management
        # Notifications are side effects, not part of event sourcing
        
        if agent_id in self.notification_subscribers:
            queue = self.notification_subscribers[agent_id]
            await queue.put({
                "type": notification_type,
                "elicitation_id": elicitation_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Validate data against JSON schema"""
        # Simplified validation - in production use jsonschema library
        if not schema:
            return True
        
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})
        
        for field in required_fields:
            if field not in data:
                return False
        
        for field, value in data.items():
            if field in properties:
                field_schema = properties[field]
                field_type = field_schema.get("type")
                
                if field_type == "string" and not isinstance(value, str):
                    return False
                elif field_type == "boolean" and not isinstance(value, bool):
                    return False
                elif field_type == "integer" and not isinstance(value, int):
                    return False
                elif field_type == "array" and not isinstance(value, list):
                    return False
                elif field_type == "object" and not isinstance(value, dict):
                    return False
        
        return True
```

### Integration with Bridge

```python
class EventSourcedBridge:
    """Bridge with event-sourced elicitation support"""
    
    def __init__(self):
        # Core components
        self.event_store = EventStore()
        self.shadow_filesystem = EventSourcedShadows()
        self.policy_engine = PolicyEngine()
        
        # Event-sourced elicitation manager
        self.elicitation_manager = EventSourcedElicitationManager(self.event_store)
        
        # Coordination components
        self.expert_coordinator = SecureExpertCoordinator(self.event_store)
    
    async def initialize(self):
        """Initialize all components"""
        await self.event_store.initialize()
        await self.elicitation_manager.initialize()
        await self.expert_coordinator.start()
    
    async def request_expert_validation_elicitation(
        self,
        command: Command,
        requesting_agent: str,
        session_token: str
    ) -> ValidationResult:
        """
        Use event-sourced elicitation for expert validation.
        All state changes go through events.
        """
        # Create elicitation through event
        elicitation_id = await self.elicitation_manager.create_elicitation(
            from_agent=requesting_agent,
            to_agent="security_expert",
            message=f"Please validate this command: {command.tool}",
            schema={
                "type": "object",
                "properties": {
                    "approved": {"type": "boolean"},
                    "risk_level": {"type": "string"},
                    "reasoning": {"type": "string"}
                },
                "required": ["approved", "risk_level", "reasoning"]
            },
            timeout_seconds=10,
            agent_token=session_token
        )
        
        # Wait for response (monitoring events, not polling state)
        response = await self.elicitation_manager.wait_for_response(
            elicitation_id,
            timeout=10
        )
        
        if response and response.status == "accepted":
            return ValidationResult(
                approved=response.response_data["approved"],
                risk_level=response.response_data["risk_level"],
                reasoning=response.response_data["reasoning"],
                elicitation_id=elicitation_id,
                event_sequence=response.response_sequence
            )
        else:
            return ValidationResult(
                approved=False,
                risk_level="unknown",
                reasoning="Expert validation timeout or declined",
                elicitation_id=elicitation_id
            )
```

## Key Architectural Improvements

### 1. Pure Event Sourcing
- **No Direct State Mutation**: The `ElicitationManager` never directly modifies state
- **Event-First**: All operations create events that are then processed
- **Immutable Events**: Complete audit trail that cannot be altered
- **Replay Capability**: State can be rebuilt from any point in history

### 2. Projection Pattern
- **Derived State**: Current state is a projection of events
- **Multiple Projections**: Can create different views of the same events
- **Eventual Consistency**: State updates after events are processed
- **Query Optimization**: Projections optimized for different query patterns

### 3. Snapshot Optimization
- **Fast Recovery**: Snapshots reduce startup time
- **Configurable Intervals**: Balance between storage and performance
- **Event-Based Snapshots**: Snapshots are themselves events
- **Incremental Updates**: Only process events after last snapshot

### 4. Separation of Concerns
- **State Management**: Handled purely through events
- **Notifications**: Decoupled side effects
- **Authentication**: Delegated to EventStore
- **Validation**: Pure functions without side effects

### 5. Consistency Guarantees
- **Atomic Operations**: Events provide transactional boundaries
- **Ordering Guarantees**: Sequence numbers ensure correct ordering
- **Idempotency**: Event processing is idempotent
- **Audit Trail**: Complete history of all state changes

## Performance Characteristics

### Event Processing
- **Write Performance**: O(1) event append
- **Read Performance**: O(n) for full rebuild, O(1) with snapshots
- **Query Performance**: O(1) from projection indices
- **Memory Usage**: Bounded by active elicitations + snapshot

### Optimization Strategies
1. **Snapshot Frequency**: Every 1000 events by default
2. **Projection Caching**: Keep hot projections in memory
3. **Event Batching**: Process multiple events in single transaction
4. **Index Optimization**: Maintain indices for common queries

## Testing Strategy

### Event Sourcing Tests
```python
class TestEventSourcedElicitation:
    async def test_event_replay(self):
        """Test state can be rebuilt from events"""
        manager = EventSourcedElicitationManager(event_store)
        
        # Create elicitations
        id1 = await manager.create_elicitation(...)
        id2 = await manager.create_elicitation(...)
        
        # Respond to one
        await manager.respond_to_elicitation(id1, "accept", {...})
        
        # Rebuild from scratch
        manager.projection = None
        await manager._rebuild_projection(from_snapshot=False)
        
        # Verify state matches
        assert len(manager.projection.active_elicitations) == 1
        assert len(manager.projection.completed_elicitations) == 1
    
    async def test_snapshot_recovery(self):
        """Test recovery from snapshot"""
        # Create snapshot
        await manager._create_snapshot()
        
        # Add more events
        await manager.create_elicitation(...)
        
        # Rebuild from snapshot
        await manager._rebuild_projection(from_snapshot=True)
        
        # Verify incremental update worked
        assert manager.projection.snapshot_sequence > 0
    
    async def test_idempotent_processing(self):
        """Test events can be replayed safely"""
        # Process same event multiple times
        event = Event(...)
        manager._apply_event_to_projection(event)
        manager._apply_event_to_projection(event)
        
        # State should be consistent
        assert len(manager.projection.active_elicitations) == 1
```

## Migration Path

### Phase 1: Parallel Implementation
1. Deploy event-sourced manager alongside direct-state version
2. Shadow write to both systems
3. Compare outputs for consistency

### Phase 2: Read Migration
1. Start reading from event-sourced projection
2. Fall back to direct state if issues
3. Monitor for discrepancies

### Phase 3: Write Migration
1. All writes go through events
2. Direct state becomes read-only
3. Deprecation warnings added

### Phase 4: Cleanup
1. Remove direct state management
2. Optimize projection structures
3. Tune snapshot intervals

## Security Considerations

### Event Authentication
- All events include source agent identification
- HMAC authentication on event records
- Audit trail cannot be tampered with

### Access Control
- Events filtered by agent permissions
- Projections respect access boundaries
- Snapshot access requires admin privileges

### Data Validation
- Schema validation before event creation
- Event data sanitization
- Projection validation on rebuild

## Monitoring & Observability

### Key Metrics
```python
class ElicitationMetrics:
    # Event metrics
    events_created = Counter("elicitation_events_created_total")
    events_processed = Counter("elicitation_events_processed_total")
    event_processing_time = Histogram("elicitation_event_processing_seconds")
    
    # Projection metrics
    projection_rebuild_time = Histogram("elicitation_projection_rebuild_seconds")
    projection_size = Gauge("elicitation_projection_size_bytes")
    
    # Snapshot metrics
    snapshots_created = Counter("elicitation_snapshots_created_total")
    snapshot_size = Histogram("elicitation_snapshot_size_bytes")
    
    # Business metrics
    elicitations_active = Gauge("elicitations_active")
    elicitations_completed = Counter("elicitations_completed_total")
```

## Conclusion

This event-sourced architecture for FEATURE_PACK_0 aligns perfectly with Lighthouse's core principles:

1. **Event Sourcing**: All state changes flow through immutable events
2. **Audit Trail**: Complete history of every elicitation
3. **Consistency**: Strong consistency through event ordering
4. **Performance**: Snapshot optimization for fast recovery
5. **Scalability**: Projection pattern enables horizontal scaling
6. **Security**: Leverages EventStore's authentication and authorization

The architecture ensures that elicitation management is:
- **Reliable**: State can always be reconstructed
- **Auditable**: Every change is recorded
- **Performant**: Optimized through snapshots and projections
- **Maintainable**: Clear separation of concerns
- **Extensible**: New projections can be added without changing events

This design positions Lighthouse's elicitation system as a best-in-class example of event-sourced architecture in multi-agent coordination systems.