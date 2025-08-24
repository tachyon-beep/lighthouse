# ADR-003: Event Store System Design for Lighthouse Foundation

**Status**: Proposed  
**Date**: 2025-08-24  
**Deciders**: system-architect  
**Context**: Phase 1 Event-Sourced Foundation implementation for Lighthouse multi-agent coordination platform

## Context and Problem Statement

Lighthouse's current architecture uses ephemeral in-memory state for command validation and agent coordination. This creates significant limitations:

- **No Durability**: System state is lost on restart, breaking agent coordination continuity
- **No Auditability**: No persistent record of command decisions and agent interactions  
- **No Recovery**: Cannot reconstruct system state after failures
- **No Analysis**: Cannot learn from historical patterns or improve validation over time

Phase 1 requires a production-ready event store that serves as the source of truth for all system state, enabling deterministic state reconstruction while preserving Lighthouse's multi-agent coordination patterns.

## Event Ordering and Concurrency Architecture

### Event Ordering Guarantees

**Decision**: **Total Ordering with Causal Metadata**

- **Primary Ordering**: Total ordering across all events using monotonic timestamps + sequence numbers
- **Causal Tracking**: Events include causal metadata for multi-agent coordination analysis
- **Stream Ordering**: Per-stream ordering preserved as subset of total ordering

**Rationale**: 
- Multi-agent coordination requires understanding global state evolution
- Command validation decisions often depend on system-wide context
- Total ordering simplifies replay and debugging while supporting causal analysis
- Causal metadata enables future optimizations without architectural changes

**Implementation**:
```python
class EventID:
    timestamp_ns: int     # Nanosecond precision monotonic timestamp
    sequence: int         # Sequence number for same-timestamp events
    node_id: str         # Node identifier for distributed scenarios

class Event:
    id: EventID
    stream_id: str       # Agent/session/component stream
    event_type: str      # CommandReceived, ValidationCompleted, etc.
    data: dict
    causality: dict      # parent_events, correlation_id, session_id
    metadata: dict       # agent_id, bridge_instance, etc.
```

### Concurrent Write Handling

**Decision**: **Single-Writer with Batching**

- **Write Model**: Single writer thread per event store instance
- **Batching**: Multiple events batched into atomic writes
- **Concurrency**: Multiple readers, single writer with optimistic coordination
- **Conflict Resolution**: Queue-based ordering with timestamp-based conflict prevention

**Rationale**:
- Eliminates write conflicts and ensures consistent ordering
- Batching provides performance while maintaining atomicity
- Matches Lighthouse's bridge coordination pattern (single coordination point)
- Simplifies implementation and reduces failure modes

**Implementation Pattern**:
```python
class EventStore:
    async def append_events(self, events: List[Event]) -> AppendResult:
        # Single writer thread processes batched events
        # Atomic write to storage with fsync
        # Update in-memory indices atomically
        pass
        
    async def append_event(self, event: Event) -> AppendResult:
        # Queue for batch processing
        return await self.append_events([event])
```

### Event ID Generation

**Decision**: **Monotonic Timestamps + Sequence Numbers**

- **Format**: `{timestamp_ns}_{sequence}_{node_id}`
- **Timestamp**: Nanosecond precision monotonic timestamp (not wall clock)
- **Sequence**: Per-timestamp sequence counter for same-timestamp events
- **Node ID**: Instance identifier for future distributed deployment

**Rationale**:
- Monotonic timestamps ensure ordering even across system restarts
- Sequence numbers handle high-frequency events (>1 per nanosecond)
- Human-readable format aids debugging and operational analysis
- Deterministic sorting enables efficient range queries

### Cross-Stream Causality Handling

**Decision**: **Event-Carried Causality with Correlation IDs**

- **Causality Fields**: `parent_events`, `correlation_id`, `session_id`, `causality_chain`
- **Correlation Strategy**: UUIDs for tracking related events across agents
- **Session Tracking**: Session-scoped causality for pair programming workflows
- **Chain Analysis**: Optional causality chain reconstruction for complex scenarios

**Implementation**:
```python
class CausalityMetadata:
    parent_events: List[str]    # Direct causal parents
    correlation_id: str         # UUID linking related events
    session_id: Optional[str]   # Pair programming session
    causality_chain: List[str]  # Full chain for complex analysis
    agent_context: dict         # Agent-specific causal context
```

### Clock Synchronization Requirements

**Decision**: **Hybrid Logical Clocks with NTP Fallback**

- **Primary**: Hybrid Logical Clocks (HLC) for distributed coordination
- **Fallback**: NTP synchronization for wall-clock correlation
- **Local**: Monotonic clocks for single-node ordering
- **Resolution**: Microsecond precision sufficient for coordination needs

**Rationale**:
- HLC provides causal ordering guarantees for distributed agents
- NTP fallback ensures human-meaningful timestamps
- Monotonic local clocks prevent time-travel issues during NTP adjustments
- Microsecond precision balances accuracy with performance

## API Surface Design and Client Integration

### Event Publishing API Design

**Decision**: **Hybrid Synchronous/Asynchronous with Batching**

**Core API**:
```http
POST /events                    # Single event (sync)
POST /events/batch              # Batch events (sync, atomic)  
POST /events/async              # Single event (async)
POST /events/batch/async        # Batch events (async)
```

**Response Patterns**:
- **Synchronous**: Immediate success/failure with event ID
- **Asynchronous**: Immediate acceptance with future completion tracking
- **Batch**: All-or-nothing atomic semantics

**Rationale**:
- Preserves current bridge synchronous patterns for critical validation
- Async options enable high-throughput non-critical events
- Batch operations optimize multi-event agent actions
- Hybrid approach supports different agent coordination needs

### Event Subscription Models

**Decision**: **WebSocket Streams with Filtered Subscriptions**

**Primary API**: WebSocket `/stream` with subscription filters
**Fallback API**: Server-Sent Events `/events/stream` for simple clients
**Polling API**: GET `/events` with cursor-based pagination for resilience

**Subscription Filters**:
```json
{
  "stream_ids": ["agent_1", "validation_*"],
  "event_types": ["CommandReceived", "ValidationCompleted"],
  "correlation_id": "uuid",
  "session_id": "pair_session_123",
  "since": "timestamp_or_event_id"
}
```

**Rationale**:
- WebSocket provides real-time updates essential for agent coordination
- Filtered subscriptions reduce bandwidth and processing overhead
- SSE fallback ensures broad client compatibility
- Polling provides ultimate reliability for critical processes

### Query API Design

**Decision**: **SQL-like Query Language with Predicate Optimization**

**Query API**: POST `/events/query` with structured query language

**Query Structure**:
```json
{
  "select": ["id", "event_type", "data", "metadata"],
  "where": {
    "event_type": {"in": ["CommandReceived", "ValidationCompleted"]},
    "timestamp": {"gte": "2025-08-24T00:00:00Z"},
    "data.agent": {"eq": "system-architect"},
    "correlation_id": {"eq": "uuid"}
  },
  "order_by": [{"field": "timestamp", "direction": "desc"}],
  "limit": 1000,
  "offset": 0
}
```

**Rationale**:
- SQL-like syntax familiar to developers and operations teams
- Structured format enables query optimization and caching
- Supports complex multi-agent coordination analysis queries
- Predicate pushdown enables efficient event store scanning

### Client Authentication and Authorization

**Decision**: **JWT with Agent-Scoped Permissions**

**Authentication**: JWT tokens with agent identity and capabilities
**Authorization**: Role-based permissions with agent-specific scopes

**Permission Model**:
```json
{
  "agent_id": "system-architect",
  "role": "expert_agent",
  "permissions": {
    "events.read": ["own", "validation_*", "public_*"],
    "events.write": ["own", "validation_requests"],
    "events.query": ["all"],
    "streams.subscribe": ["own", "coordination", "alerts"]
  },
  "session_permissions": {
    "pair_programming": true,
    "emergency_degradation": false
  }
}
```

**Rationale**:
- Agent identity enables proper event attribution and causality
- Scoped permissions prevent agents from interfering with others
- JWT standard enables integration with existing auth systems
- Session permissions support dynamic collaboration workflows

### Error Handling and Retry Semantics

**Decision**: **Exponential Backoff with Circuit Breaker Pattern**

**Error Categories**:
- **Transient**: Network timeouts, temporary unavailability
- **Permanent**: Invalid events, permission denied, schema violations
- **System**: Event store full, corruption detected

**Retry Strategy**:
```python
class RetryPolicy:
    max_retries: int = 5
    base_delay: float = 0.1
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    
    # Circuit breaker thresholds
    failure_threshold: int = 10
    recovery_timeout: float = 60.0
```

**Rationale**:
- Exponential backoff prevents thundering herd during outages
- Circuit breaker protects event store from sustained overload
- Jitter prevents synchronized retry storms across agents
- Categorized errors enable appropriate retry strategies

## Integration with Emergency Degradation Mode

### Degradation Detection and Signaling

**Decision**: **Health Check Events with Threshold-Based Detection**

**Health Monitoring**:
- **Metrics Events**: Regular health metrics published as events
- **Threshold Detection**: Automated degradation detection via metric analysis
- **Manual Triggers**: Emergency degradation events from human operators
- **Cross-Component**: Health events propagated across bridge instances

**Detection Thresholds**:
```json
{
  "event_write_latency_ms": {"warning": 100, "critical": 1000},
  "event_backlog_size": {"warning": 1000, "critical": 10000},
  "disk_usage_percent": {"warning": 80, "critical": 95},
  "memory_usage_percent": {"warning": 85, "critical": 95},
  "agent_timeout_rate": {"warning": 0.1, "critical": 0.3}
}
```

### Available Operations During Degradation

**Decision**: **Read-Only Mode with Essential Write Operations**

**Degraded Operations**:
- **Full Read Access**: All query and subscription operations continue
- **Critical Writes**: Emergency events, degradation signals, basic validation
- **Blocked Writes**: Non-essential events, large batches, complex operations
- **Cache Mode**: Recent events served from memory cache when storage unavailable

**Implementation**:
```python
class DegradationMode:
    level: str  # "warning", "critical", "emergency"
    allowed_writes: List[str]  # Event types permitted during degradation
    cache_duration: int  # Memory cache retention during storage issues
    
    def can_write_event(self, event_type: str) -> bool:
        return event_type in self.allowed_writes
```

### State Recovery Reconciliation

**Decision**: **Event Replay with Conflict Resolution**

**Recovery Process**:
1. **Detect Inconsistency**: Compare event store state with bridge memory state
2. **Replay Events**: Reconstruct correct state from event history
3. **Resolve Conflicts**: Merge in-memory changes made during degradation
4. **Validate State**: Ensure recovered state matches expected invariants

**Conflict Resolution**:
```python
class ReconciliationStrategy:
    def resolve_conflict(self, 
                        stored_event: Event, 
                        memory_event: Event) -> Event:
        # Timestamp-based resolution with manual override capability
        if stored_event.timestamp > memory_event.timestamp:
            return stored_event
        return memory_event
```

### Degradation Event Storage

**Decision**: **Store All Degradation Events with Priority Queuing**

**Event Storage Strategy**:
- **Always Store**: Degradation events always written to event store
- **Priority Queue**: Degradation events bypass normal write throttling
- **Separate Stream**: Degradation events in dedicated stream for analysis
- **Metadata Rich**: Extensive context about degradation causes and effects

**Degradation Event Schema**:
```json
{
  "event_type": "SystemDegradationDetected",
  "data": {
    "degradation_level": "critical",
    "trigger_metrics": {"write_latency": 1500},
    "affected_components": ["event_store", "validation_bridge"],
    "mitigation_actions": ["readonly_mode", "cache_enabled"]
  }
}
```

### Cross-Component Degradation Coordination

**Decision**: **Event-Driven Degradation Propagation**

**Coordination Pattern**:
- **Degradation Events**: Components publish degradation status changes
- **Event Subscription**: All components subscribe to degradation events
- **Coordinated Response**: Components adjust behavior based on system-wide degradation
- **Recovery Coordination**: Ordered recovery process coordinated via events

**Example Coordination Flow**:
```
1. Event Store → SystemDegradationDetected(critical)
2. Bridge → DegradationResponseActivated(readonly_mode)
3. Agents → DegradationAcknowledged(reduced_operations)
4. Event Store → SystemDegradationRecovered()
5. Components → DegradationRecoveryCompleted()
```

## API Specifications and Interaction Patterns

### Core Event Store API

```yaml
# OpenAPI 3.0 specification excerpt
paths:
  /events:
    post:
      summary: Publish single event
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Event'
      responses:
        201:
          description: Event stored successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  event_id: {type: string}
                  timestamp: {type: string}
                  status: {type: string, enum: [stored]}
        400:
          description: Invalid event schema
        429:
          description: Rate limit exceeded
        503:
          description: System in degradation mode

  /events/batch:
    post:
      summary: Publish multiple events atomically
      requestBody:
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/Event'
              maxItems: 100
      responses:
        201:
          description: All events stored successfully
        400:
          description: Invalid event in batch
        413:
          description: Batch too large
        503:
          description: System in degradation mode

  /events/stream:
    get:
      summary: WebSocket event subscription
      parameters:
        - name: filter
          in: query
          schema:
            $ref: '#/components/schemas/SubscriptionFilter'
      responses:
        101:
          description: WebSocket upgrade successful
```

### Client Integration Patterns

**Bridge Integration**:
```python
class LighthouseBridge:
    def __init__(self, event_store_client: EventStoreClient):
        self.events = event_store_client
        self.state = {}
    
    async def handle_command(self, command: Command) -> ValidationResult:
        # Publish command received event
        await self.events.publish(Event(
            event_type="CommandReceived",
            stream_id=f"agent_{command.agent_id}",
            data=command.to_dict(),
            correlation_id=command.correlation_id
        ))
        
        # Process validation logic
        result = await self.validate_command(command)
        
        # Publish validation result
        await self.events.publish(Event(
            event_type="ValidationCompleted",
            stream_id=f"agent_{command.agent_id}",
            data=result.to_dict(),
            correlation_id=command.correlation_id,
            causality={
                "parent_events": [command.event_id],
                "correlation_id": command.correlation_id
            }
        ))
        
        return result
```

**Agent Integration**:
```python
class LighthouseAgent:
    def __init__(self, event_store_client: EventStoreClient):
        self.events = event_store_client
        self.agent_id = "system-architect"
    
    async def start(self):
        # Subscribe to relevant event streams
        await self.events.subscribe(
            filters=SubscriptionFilter(
                stream_ids=[f"agent_{self.agent_id}", "coordination", "alerts"],
                event_types=["CommandApproved", "ValidationRequired", "PairProgrammingRequest"]
            ),
            handler=self.handle_event
        )
    
    async def handle_event(self, event: Event):
        if event.event_type == "ValidationRequired":
            await self.perform_validation(event)
        elif event.event_type == "PairProgrammingRequest":
            await self.handle_pair_request(event)
```

## Concurrency and Consistency Guarantees

### Event Store Consistency

**Guarantees Provided**:
- **Write Consistency**: All writes are atomic and durable
- **Read Consistency**: Consistent read views of event history
- **Ordering Consistency**: Total ordering maintained across all clients
- **Causal Consistency**: Causal relationships preserved in event streams

**Implementation**:
- **Write Atomicity**: Filesystem atomic write operations with fsync
- **Read Isolation**: Snapshot-based reads prevent partial state visibility
- **Ordering**: Monotonic timestamps ensure consistent ordering
- **Durability**: Write-ahead logging with configurable sync policies

### Multi-Agent Coordination Consistency

**Agent Coordination Guarantees**:
- **Command Ordering**: Command validation requests processed in arrival order
- **State Consistency**: All agents see same event ordering
- **Session Isolation**: Pair programming sessions maintain isolation
- **Recovery Consistency**: State recovery produces consistent results

**Conflict Resolution**:
- **Command Conflicts**: First-arrival wins with explicit conflict events
- **Session Conflicts**: Session ownership prevents conflicting operations
- **Resource Conflicts**: Resource locks implemented via events
- **Recovery Conflicts**: Timestamp-based resolution with human escalation

### Performance Characteristics

**Expected Performance**:
- **Write Throughput**: 10,000+ events/second sustained
- **Write Latency**: <10ms p99 for single events, <50ms p99 for batches
- **Read Throughput**: 100,000+ events/second from cache, 10,000+ from storage
- **Query Latency**: <100ms p99 for typical queries, <1s for complex analysis
- **Storage Growth**: ~1KB average event size, with configurable compaction

**Scalability Limits**:
- **Single Node**: 1M events/day sustained, 10M events/day burst
- **Storage**: Multi-TB event logs with automated archival
- **Clients**: 1,000+ concurrent connections with connection pooling
- **Queries**: Complex queries may require dedicated analytics systems

## Decision Rationale

### Why Event Sourcing for Lighthouse?

**Multi-Agent Coordination Benefits**:
1. **Complete Auditability**: Every decision and interaction permanently recorded
2. **State Reconstruction**: Can replay system state for debugging and analysis
3. **Temporal Queries**: Can analyze system behavior over time
4. **Causal Analysis**: Understanding why decisions were made
5. **Learning**: Historical data enables improving validation accuracy

**Technical Benefits**:
1. **Reliability**: Append-only design eliminates many failure modes
2. **Scalability**: Event streams naturally partition and scale
3. **Integration**: Event-driven architecture supports loose coupling
4. **Evolution**: Event schema evolution enables system growth
5. **Observability**: Complete system observability built-in

### Why These Specific Design Choices?

**Total Ordering**: Multi-agent coordination requires understanding global system state evolution. Per-stream ordering would make cross-agent analysis complex.

**Single Writer**: Eliminates write conflicts and ensures deterministic ordering. Matches current bridge architecture pattern.

**Hybrid API**: Different agent coordination scenarios have different latency/consistency requirements. Synchronous for critical validation, asynchronous for monitoring.

**WebSocket Subscriptions**: Real-time agent coordination requires push-based updates. Polling introduces unacceptable latency for multi-agent workflows.

**JWT Authentication**: Standard approach that integrates with existing systems while providing agent-specific authorization.

**Event-Driven Degradation**: Degradation coordination must use the same reliable mechanism as normal operations to ensure system-wide consistency.

## Implementation Timeline

**Phase 1.1: Core Event Store** (2 weeks)
- Basic event append and read operations
- File-based storage with atomic writes
- Event ID generation and ordering
- Basic HTTP API for append/query

**Phase 1.2: Event Replay Engine** (2 weeks)  
- State reconstruction from event history
- Streaming replay for large histories
- Event filtering and projection
- Performance optimization

**Phase 1.3: Advanced API** (2 weeks)
- WebSocket subscription system
- Batch operations and async API
- Query API with filtering
- Authentication and authorization

**Phase 1.4: Degradation Integration** (1 week)
- Health monitoring events
- Degradation mode implementation
- State recovery reconciliation
- Cross-component coordination

**Total Phase 1 Duration**: 7 weeks with validation and testing

## Risks and Mitigations

**Risk: Event Store Corruption**
- Mitigation: Checksums, write-ahead logging, automated backup
- Recovery: Event replay from last known good state

**Risk: Performance Degradation Under Load**
- Mitigation: Batching, caching, query optimization
- Monitoring: Real-time performance metrics with alerting

**Risk: Storage Growth**
- Mitigation: Event compaction, archival policies, retention limits
- Monitoring: Storage usage tracking with proactive alerts

**Risk: Complex Recovery Scenarios**
- Mitigation: Extensive testing, documented procedures, manual override capability
- Training: Operational runbooks for common failure scenarios

## Success Criteria

**Functional Requirements**:
- [ ] Event store handles 10,000 events/second with zero data loss
- [ ] State reconstruction is deterministic and correct
- [ ] All API operations complete within SLA requirements
- [ ] Emergency degradation works correctly under failure conditions

**Non-Functional Requirements**:
- [ ] System survives kill -9 of processes without data loss
- [ ] Event ordering is maintained across all restarts
- [ ] Performance remains acceptable under sustained load
- [ ] Recovery procedures complete within defined time limits

**Integration Requirements**:
- [ ] Current bridge functionality preserved
- [ ] Agent coordination patterns work correctly
- [ ] Pair programming workflows function normally
- [ ] Emergency degradation coordinates properly across components

---

**Implementation Authority**: system-architect
**Review Required**: technical-lead, infrastructure-architect  
**Next Actions**: Begin Phase 1.1 implementation with core event store