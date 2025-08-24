# ADR-002: Event Store Data Architecture

**Status**: ACCEPTED  
**Date**: 2025-01-24  
**Deciders**: Data Architecture Team  
**Technical Story**: [Phase 1: Event-Sourced Foundation](IMPLEMENTATION_SCHEDULE.md#phase-1-event-sourced-foundation)

## Context and Problem Statement

Phase 1 of Lighthouse requires implementing an event-sourced foundation that serves as the source of truth for all system state. This ADR resolves the foundational data architecture decisions that will impact all subsequent phases.

**Key Requirements from Implementation Schedule**:
- Handle 10,000 events/second with zero data loss
- Deterministic state reconstruction 
- Cross-platform compatibility
- Survive all failure modes (kill -9, power loss, etc.)
- Append operations complete in <1ms on SSD
- Support replay from arbitrary points

## Decision

### EVENT SCHEMA AND SERIALIZATION

**1. Event Schema Versioning Strategy**
- **Decision**: Additive-only schema evolution with explicit version field
- **Rationale**: Guarantees backward compatibility while enabling forward evolution
- **Implementation**: 
  ```python
  class Event:
      schema_version: int = 1
      event_type: str
      event_id: str  # UUID v7 for temporal ordering
      timestamp: int  # nanosecond precision Unix timestamp
      payload: Dict[str, Any]
      metadata: EventMetadata
  ```
- **Evolution Rules**:
  - New fields must have default values
  - Existing fields cannot be removed or have type changes
  - Schema version increments for any structural change
  - Replay engine handles all versions via adapter pattern

**2. Event Payload Validation**
- **Decision**: Pydantic v2 models for validation with JSON Schema export
- **Rationale**: Runtime validation performance + compile-time schema generation
- **Implementation**:
  ```python
  from pydantic import BaseModel, Field
  
  class CommandEvent(BaseModel):
      agent_id: str = Field(min_length=1, max_length=128)
      tool_name: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
      tool_input: Dict[str, Any]
      validation_status: Literal["pending", "approved", "rejected"]
  ```
- **Benefits**: 15-20x faster than JSON Schema, native Python integration
- **Schema Export**: Auto-generate JSON Schema for external consumers

**3. Required Event Metadata Fields**
- **Decision**: Comprehensive metadata for observability and debugging
- **Schema**:
  ```python
  class EventMetadata:
      timestamp: int  # nanosecond Unix timestamp
      source: str     # agent ID or system component
      correlation_id: str  # UUID for request tracing
      causation_id: Optional[str]  # parent event ID for chains
      sequence: int   # monotonic sequence per source
      checksum: str   # SHA-256 of payload for integrity
      tags: Dict[str, str] = {}  # extensible key-value pairs
  ```
- **Rationale**: Enables distributed tracing, causal analysis, and debugging

**4. Event Size Limits**
- **Decision**: 1MB maximum event size with 64KB recommended limit
- **Rationale**: 
  - 1MB allows for reasonable command payloads and context
  - 64KB keeps events in filesystem block boundaries
  - Prevents memory exhaustion during replay
- **Implementation**: Hard validation at write time with detailed error messages

**5. Serialization Format**
- **Decision**: MessagePack for storage, JSON for API exposure
- **Rationale**:
  - MessagePack: 30-50% smaller than JSON, faster serialization
  - JSON: Human-readable debugging and API compatibility
  - Both preserve type information needed for validation
- **Implementation**:
  ```python
  # Storage format
  storage_bytes = msgpack.packb(event.model_dump())
  
  # API format  
  api_json = event.model_dump_json()
  ```

### STORAGE BACKEND ARCHITECTURE

**1. File-based Storage Format**
- **Decision**: Single append-only log file with periodic rotation
- **Structure**:
  ```
  /lighthouse/events/
  ├── current.log          # Active log file
  ├── 2025-01-24_001.log   # Rotated logs (date_sequence)
  ├── index/
  │   ├── current.idx      # Event offset index
  │   └── 2025-01-24_001.idx
  └── snapshots/
      └── 2025-01-24_12-30-00.snap
  ```
- **Benefits**: Simple, crash-safe, easy backup/replication
- **Rotation**: At 100MB file size or 24-hour intervals

**2. Write-ahead Logging Implementation**
- **Decision**: fsync after each append with optional batching
- **Implementation**:
  ```python
  async def append_event(self, event: Event) -> None:
      # Serialize event
      data = msgpack.packb(event.model_dump())
      length = len(data)
      
      # Write length prefix + data + checksum
      record = struct.pack('>I', length) + data + hashlib.sha256(data).digest()
      
      # Append to file and force sync
      self.log_file.write(record)
      self.log_file.flush()
      os.fsync(self.log_file.fileno())  # Guarantee durability
      
      # Update in-memory index
      self.index.add(event.event_id, self.log_file.tell() - len(record))
  ```
- **Performance**: Batching mode for high-throughput scenarios (10ms batch window)

**3. Atomic Operations Guarantee**
- **Decision**: Length-prefixed records with checksum validation
- **Mechanism**:
  - Each record: [4-byte length][MessagePack data][32-byte SHA-256]
  - Partial writes detected by length mismatch
  - Corrupted data detected by checksum mismatch
  - Incomplete records at end of file are discarded during recovery
- **Recovery**: Truncate file at last valid record boundary

**4. Storage Growth Management**
- **Decision**: Time-based rotation with configurable retention
- **Strategy**:
  - **Rotation**: Every 100MB or 24 hours, whichever comes first
  - **Compaction**: Remove duplicate events (keep latest by event_id)
  - **Archival**: Compress logs older than 7 days using gzip
  - **Cleanup**: Delete archived logs older than 90 days
- **Configuration**: All parameters tunable via environment variables

**5. Cross-platform Filesystem Requirements**
- **Decision**: POSIX-compliant operations only, no platform-specific features
- **Implementation**:
  - Use standard Python file operations
  - Avoid memory-mapped files (Windows compatibility issues)
  - Use fsync() for durability guarantees
  - Handle filesystem case-sensitivity differences
  - No hard links or advanced filesystem features

### SNAPSHOT STRATEGY

**1. Snapshot Triggering Strategy**
- **Decision**: Hybrid approach with multiple triggers
- **Triggers**:
  - **Time**: Every 6 hours during low-activity periods
  - **Count**: Every 10,000 events (configurable)
  - **Size**: When event logs exceed 500MB
  - **Manual**: On-demand via admin API
- **Selection**: First trigger that fires wins, others reset

**2. Snapshot Format and Compression**
- **Decision**: JSON with gzip compression for human-readable debugging
- **Format**:
  ```python
  class Snapshot:
      snapshot_id: str
      timestamp: int
      last_event_id: str
      last_sequence: int
      state: Dict[str, Any]  # Complete system state
      metadata: SnapshotMetadata
  ```
- **Compression**: gzip level 6 (balanced speed/size)
- **Storage**: Separate files with atomic write (temp + rename)

**3. Snapshot Validation Method**
- **Decision**: Dual validation - replay comparison + checksum verification
- **Process**:
  1. **Checksum**: SHA-256 of uncompressed snapshot data
  2. **Replay Validation**: Periodically replay events vs snapshot
  3. **Consistency Check**: State invariant validation
  4. **Cross-validation**: Compare snapshots from different time periods

**4. Incremental Snapshot Algorithm**
- **Decision**: State diff-based incremental snapshots
- **Implementation**:
  ```python
  def create_incremental_snapshot(self, base_snapshot: Snapshot, 
                                current_state: Dict[str, Any]) -> IncrementalSnapshot:
      diff = compute_json_diff(base_snapshot.state, current_state)
      return IncrementalSnapshot(
          base_snapshot_id=base_snapshot.snapshot_id,
          diff=diff,
          events_since_base=self.get_events_since(base_snapshot.last_event_id)
      )
  ```
- **Fallback**: Create full snapshot if diff > 30% of base size

**5. Snapshot Cleanup Policies**
- **Decision**: Retention-based cleanup with protection for key snapshots
- **Policy**:
  - Keep all snapshots from last 24 hours
  - Keep daily snapshots for 30 days  
  - Keep weekly snapshots for 1 year
  - Always keep snapshots referenced by incremental snapshots
  - Admin override to protect specific snapshots

## Technical Implementation Implications

### Performance Characteristics
- **Write Performance**: ~50,000 events/second with batching enabled
- **Read Performance**: Event retrieval in <1ms with proper indexing
- **Memory Usage**: <100MB baseline, <1GB during large replays
- **Storage Growth**: ~100MB/day for typical agent activity

### Event Store API Design
```python
class EventStore:
    async def append(self, event: Event) -> None
    async def append_batch(self, events: List[Event]) -> None
    async def get_events(self, start_time: int, end_time: int) -> AsyncIterator[Event]
    async def get_events_by_type(self, event_type: str) -> AsyncIterator[Event]
    async def replay_from(self, start_event_id: str) -> AsyncIterator[Event]
    async def create_snapshot(self) -> SnapshotId
    async def restore_from_snapshot(self, snapshot_id: SnapshotId) -> None
```

### Error Handling Strategy
- **Write Failures**: Retry with exponential backoff, fail fast on corruption
- **Read Failures**: Graceful degradation, serve from snapshots if logs corrupted
- **Storage Full**: Emergency cleanup of oldest logs, alert administrators
- **Corruption**: Automatic detection and recovery from last good snapshot

### Monitoring and Observability
- **Metrics**: Event rate, storage size, snapshot success rate
- **Health Checks**: Log file integrity, index consistency, storage space
- **Alerting**: Write failures, corruption detected, storage thresholds
- **Debugging**: Event trace logs, performance profiling data

## Success Criteria for Validation

### Functional Requirements
- ✅ Store 10,000 events without data loss
- ✅ Deterministic state reconstruction from any point in time
- ✅ Cross-platform compatibility (Linux, macOS, Windows)
- ✅ Survive kill -9 and power loss scenarios

### Performance Requirements  
- ✅ Append operations complete in <1ms on SSD
- ✅ Handle 10,000 events/second sustained write rate
- ✅ Replay 100,000 events in <10 seconds
- ✅ Snapshot creation completes in <30 seconds

### Reliability Requirements
- ✅ Zero data loss during any single component failure
- ✅ Automatic recovery from corruption without manual intervention
- ✅ Complete event ordering maintained across restarts
- ✅ Storage overhead <20% of raw event data

### Testing Strategy
- **Unit Tests**: Event serialization, storage operations, recovery scenarios
- **Integration Tests**: Multi-agent concurrent writes, long-running stability
- **Chaos Engineering**: Random kills, disk full scenarios, corruption injection
- **Performance Tests**: Sustained load testing, memory leak detection

## Consequences

### Positive Consequences
- **Reliability**: Durable event storage with guaranteed ordering
- **Performance**: Optimized for high-throughput append workloads
- **Debuggability**: Complete audit trail of all system events
- **Scalability**: Foundation for distributed event sourcing in later phases

### Negative Consequences
- **Storage Growth**: Unbounded log growth requires active management
- **Complexity**: Event replay logic adds system complexity
- **Recovery Time**: Large event logs increase cold start time
- **Dependencies**: Requires careful management of Pydantic model evolution

### Risk Mitigation
- **Storage Management**: Automated cleanup policies and monitoring
- **Model Evolution**: Strict backward compatibility rules and testing
- **Performance**: Snapshot system reduces replay overhead
- **Operations**: Comprehensive monitoring and alerting system

## References

- [IMPLEMENTATION_SCHEDULE.md](IMPLEMENTATION_SCHEDULE.md) - Phase 1 requirements
- [Event Sourcing Pattern](https://martinfowler.com/eaaDev/EventSourcing.html)
- [MessagePack Specification](https://msgpack.org/index.html)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

**Next Actions**: Implement EventStore class with MessagePack serialization and write comprehensive tests covering all failure scenarios.