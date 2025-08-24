# Lighthouse Implementation Schedule

## Phase 0: Planning (Current)

**Scope**: Complete system design and implementation planning
**End State**: Detailed work packages with clear deliverables and validation criteria

**Work Packages**:
- Architecture analysis and dependency mapping
- Implementation roadmap with phase boundaries
- Technical specifications for each phase
- Success criteria and validation requirements
- Resource and tooling requirements

**Deliverables**:
- This implementation schedule document
- Technical specifications for Phase 1
- Validation framework design
- Development environment requirements

---

## Phase 1: Event-Sourced Foundation

**Scope**: Core event store that serves as the source of truth for all system state
**End State**: Production-ready event store with deterministic state reconstruction

### Work Package 1.1: Core Event Store
**Contents**:
- Immutable append-only event log
- Event serialization and deserialization
- Event ordering and sequencing
- Basic event querying by timestamp and type
- Event compaction and cleanup policies

**Technical Specifications**:
- Events stored as JSON with schema validation
- File-based storage with write-ahead logging
- Atomic append operations with filesystem sync
- Event IDs using monotonic timestamps + sequence numbers
- Maximum event size 1MB, log rotation at 100MB

**Validation Requirements**:
- Store 10,000 events without data loss
- Append operations complete in <1ms on SSD
- Log survives kill -9 of process
- Events maintain total ordering across restarts

### Work Package 1.2: Event Replay Engine
**Contents**:
- State reconstruction from event history
- Configurable event replay from arbitrary points
- Event filtering and projection
- Replay performance optimization
- Memory-efficient streaming replay

**Technical Specifications**:
- Stateless replay functions (Event -> StateChange)
- Replay from specific timestamp or event ID
- Streaming replay for large histories
- Event type filtering during replay
- Checkpoint/resume capability for long replays

**Validation Requirements**:
- Reconstruct system state from 100,000 events in <10 seconds
- Replay produces identical state regardless of restart points
- Memory usage remains constant during streaming replay
- Filtering reduces replay time proportionally

### Work Package 1.3: Snapshot Management
**Contents**:
- Periodic state snapshots for performance
- Snapshot validation and integrity checking
- Incremental snapshots for large states
- Snapshot expiration and cleanup
- Fast state recovery from snapshots + deltas

**Technical Specifications**:
- Snapshots as compressed JSON with checksums
- Configurable snapshot intervals (time or event count)
- Snapshot verification against event replay
- Incremental snapshots using state diffs
- Automatic cleanup of expired snapshots

**Validation Requirements**:
- Snapshots reduce cold start time by 90%
- Snapshot + incremental replay completes in <1 second
- Corrupted snapshots detected and replaced automatically
- Storage overhead <20% of event log size

### Work Package 1.4: Event Store API
**Contents**:
- HTTP REST API for event publishing
- WebSocket streams for real-time event consumption
- Event querying with filtering and pagination
- Health check and metrics endpoints
- Client libraries for common languages

**Technical Specifications**:
- POST /events for single event append
- POST /events/batch for atomic multi-event append
- GET /events with query parameters for filtering
- WebSocket /stream for real-time event subscription
- Prometheus metrics on /metrics endpoint

**Validation Requirements**:
- API handles 1,000 requests/second with <50ms latency
- WebSocket streams deliver events with <100ms delay
- Batch operations are atomic (all succeed or all fail)
- Client disconnections don't lose events

**Phase 1 End State Validation**:
- Event store handles all failure modes without data loss
- Performance meets requirements under load testing
- Complete API documentation and client examples
- Automated test suite covering all failure scenarios

---

## Phase 2: Basic Bridge Server

**Scope**: Minimal viable coordination hub for multi-agent operations
**End State**: Bridge server coordinating multiple agents with command validation

### Work Package 2.1: HTTP Bridge Server
**Contents**:
- HTTP server with core coordination endpoints
- Agent registration and session management
- Request routing and response handling
- Error handling and client feedback
- Basic logging and monitoring

**Technical Specifications**:
- FastAPI or similar framework for OpenAPI docs
- JWT or similar for agent authentication
- Request/response logging with correlation IDs
- Graceful shutdown with request draining
- Health check endpoint for load balancers

**Validation Requirements**:
- Server handles 100 concurrent connections
- Requests complete with 99.9% success rate
- Graceful degradation under resource pressure
- Complete OpenAPI specification generated

### Work Package 2.2: Command Validation Pipeline
**Contents**:
- Command parsing and validation
- Allow/block rule engine (no LLM yet)
- Validation result caching
- Command queuing for approval workflows
- Audit logging of all validation decisions

**Technical Specifications**:
- Command schema validation using JSON Schema
- Rule-based validation using simple pattern matching
- In-memory LRU cache for validation results
- Persistent queue for commands requiring approval
- Structured logging with command context

**Validation Requirements**:
- Validation completes in <100ms for cached results
- Rule engine correctly classifies 95% of test commands
- No false negatives on dangerous command patterns
- Complete audit trail of all validation decisions

### Work Package 2.3: Agent Coordination
**Contents**:
- Agent lifecycle management (connect/disconnect)
- Agent capability discovery and registration
- Basic message routing between agents
- Agent health monitoring and failure detection
- Session state management

**Technical Specifications**:
- Agent registration with capability metadata
- Heartbeat mechanism with configurable intervals
- Message queues per agent with overflow handling
- Agent failure detection and cleanup
- Session persistence across brief disconnections

**Validation Requirements**:
- System handles 10 agents connecting/disconnecting
- Message delivery has <1% loss rate
- Failed agents detected within 30 seconds
- No resource leaks from abandoned sessions

### Work Package 2.4: In-Memory Shadow Filesystem
**Contents**:
- In-memory representation of project files
- Shadow file CRUD operations
- Basic conflict detection for concurrent updates
- Shadow state serialization for debugging
- Memory usage monitoring and limits

**Technical Specifications**:
- File content stored as UTF-8 strings in memory
- Path-based indexing with O(1) lookup
- Last-writer-wins conflict resolution
- JSON serialization of entire shadow state
- Configurable memory limits with LRU eviction

**Validation Requirements**:
- Handles project with 1,000 files totaling 10MB
- Concurrent updates don't corrupt file contents
- Memory usage stays within configured limits
- Complete shadow state can be serialized/deserialized

**Phase 2 End State Validation**:
- Bridge coordinates 5 agents doing real file operations
- Command validation prevents dangerous operations
- Shadow filesystem maintains consistency under concurrent access
- System recovers gracefully from agent failures

---

## Phase 3: Policy Engine + Shadow Persistence

**Scope**: Fast policy-based validation and persistent shadow storage
**End State**: Production-ready validation with persistent shadow filesystem

### Work Package 3.1: Policy Engine Integration
**Contents**:
- OPA (Open Policy Agent) integration
- Policy rule management and hot reloading
- Policy decision caching with TTL
- Policy evaluation metrics and debugging
- Default policies for Lighthouse operations

**Technical Specifications**:
- OPA embedded as Go library or external service
- Rego policy files loaded from filesystem
- Policy decisions cached for 60 seconds
- Detailed timing metrics for policy evaluation
- Comprehensive policy test suite

**Validation Requirements**:
- Policy evaluation completes in <10ms for cached decisions
- Policy changes reload without server restart
- 95% of operations resolved by policy without escalation
- Policy coverage for all known dangerous patterns

### Work Package 3.2: Advanced Rule Cache
**Contents**:
- Multi-level caching (memory + Redis)
- Cache invalidation strategies
- Cache hit rate optimization
- Cache warming for common patterns
- Cache performance monitoring

**Technical Specifications**:
- L1 cache: In-memory LRU with 1000 entry limit
- L2 cache: Redis with 1-hour TTL
- Cache keys based on command hash + context
- Proactive cache warming on server startup
- Cache metrics exposed via Prometheus

**Validation Requirements**:
- Overall cache hit rate >90% under normal load
- Cache lookup completes in <1ms
- Cache invalidation propagates within 10 seconds
- Memory usage remains bounded under all conditions

### Work Package 3.3: Persistent Shadow Filesystem
**Contents**:
- File-based shadow storage with atomic updates
- Shadow versioning and diff computation
- Shadow merge conflict detection and resolution
- Shadow backup and recovery mechanisms
- Shadow filesystem integrity checking

**Technical Specifications**:
- Shadows stored as individual files in versioned directories
- Atomic updates using temp files + rename
- Git-like diff computation for shadow changes
- Three-way merge for concurrent updates
- Periodic integrity checks with repair capability

**Validation Requirements**:
- Shadow filesystem survives server restart without data loss
- Concurrent shadow updates resolve conflicts correctly
- Shadow diffs accurately represent changes
- Integrity checks detect and repair corruption

### Work Package 3.4: Expert Agent Framework
**Contents**:
- Base expert agent class with common functionality
- Shadow analysis API for expert agents
- Expert agent registration and capability advertisement
- Basic analysis result aggregation
- Expert agent health monitoring

**Technical Specifications**:
- Python base class with shadow access methods
- REST API for shadow reading and annotation
- Agent capability metadata (specialties, analysis types)
- Result aggregation with confidence scoring
- Heartbeat and failure detection for expert agents

**Validation Requirements**:
- Expert agents can analyze shadows via API calls
- Multiple expert agents can run concurrently
- Analysis results are properly aggregated and stored
- Failed expert agents don't block system operation

**Phase 3 End State Validation**:
- Policy engine handles 90% of decisions in <10ms
- Persistent shadow filesystem maintains consistency
- Expert agents successfully analyze code via API
- System performance remains acceptable under load

---

## Phase 4: FUSE Mount + LLM Validation

**Scope**: Expert agents using standard Unix tools + LLM-powered validation
**End State**: Expert agents working with familiar tools, risky operations gated by LLM review

### Work Package 4.1: FUSE Filesystem Implementation
**Contents**:
- FUSE driver mounting shadows at `/mnt/lighthouse`
- Standard filesystem operations (read, readdir, stat)
- Real-time shadow updates reflected in mounted filesystem
- FUSE performance optimization
- Mount management and error handling

**Technical Specifications**:
- Python FUSE implementation using fusepy or similar
- Mount point: `/mnt/lighthouse/project/`
- Read-only mount with real-time shadow synchronization
- Standard POSIX file attributes and permissions
- Automatic mount/unmount on server start/stop

**Validation Requirements**:
- Standard Unix tools (grep, find, cat) work correctly
- File content matches shadow state exactly
- Mount survives network interruptions and server restarts
- Performance acceptable for normal development workflows

### Work Package 4.2: Expert Agent Unix Tools Support
**Contents**:
- Expert agent redesign to use Unix tools on FUSE mount
- Process execution and output capture
- Tool result parsing and interpretation
- Standard tool integration (grep, find, awk, sed)
- Tool execution sandboxing and resource limits

**Technical Specifications**:
- Expert agents execute tools via subprocess
- Working directory set to FUSE mount point
- Tool output captured with streaming support
- Resource limits (CPU, memory, time) for tool execution
- Tool result parsing using regex and structured formats

**Validation Requirements**:
- Expert agents successfully analyze code using grep/find/cat
- Tool execution completes within resource limits
- Tool results are correctly interpreted and processed
- Sandboxing prevents expert agents from accessing real filesystem

### Work Package 4.3: LLM Integration for Risky Operations
**Contents**:
- LLM client integration (OpenAI API or similar)
- Prompt engineering for command validation
- Context building for LLM validation requests
- LLM response parsing and decision extraction
- LLM validation caching and rate limiting

**Technical Specifications**:
- Support for multiple LLM providers (OpenAI, Anthropic, etc.)
- Structured prompts with command context and system state
- JSON-structured LLM responses with reasoning
- Response caching based on command + context hash
- Rate limiting to prevent API quota exhaustion

**Validation Requirements**:
- LLM validation accuracy >90% on test command set
- Average validation latency <5 seconds
- LLM responses include clear reasoning
- System handles LLM API failures gracefully

### Work Package 4.4: Multi-Expert Consensus
**Contents**:
- Expert routing for different command types
- Consensus algorithm for conflicting expert opinions
- Expert confidence weighting and reputation scoring
- Consensus result aggregation and explanation
- Expert disagreement handling and escalation

**Technical Specifications**:
- Command routing based on type and context
- Majority voting with confidence weighting
- Expert reputation based on historical accuracy
- Detailed explanation of consensus decision
- Human escalation for unresolved disagreements

**Validation Requirements**:
- Consensus algorithm prevents dangerous commands
- Expert routing matches commands to appropriate specialists
- Reputation scoring improves over time with feedback
- Human escalation triggers correctly for ambiguous cases

**Phase 4 End State Validation**:
- Expert agents successfully analyze real codebases using Unix tools
- FUSE mount performance is acceptable for development workflows
- LLM validation catches risky operations missed by policy engine
- Multi-expert consensus prevents dangerous operations while allowing safe ones

---

## Phase 5: Context-Attached History (CAH)

**Scope**: Complete decision context capture and agent self-awareness
**End State**: Agents understand their past actions and learn from mistakes

### Work Package 5.1: Complete Context Capture
**Contents**:
- Edit context recording with full decision trails
- Conversation context preservation
- Environmental state capture at decision time
- Reasoning chain documentation
- Context compression and storage optimization

**Technical Specifications**:
- EditContext data model with all decision factors
- Conversation history stored with each edit
- System state snapshot at edit time
- Structured reasoning chains with confidence scores
- Context compression using JSON + gzip

**Validation Requirements**:
- 100% of edits have complete decision context
- Context reconstruction provides full debugging information
- Storage overhead <50% of shadow filesystem size
- Context retrieval completes in <100ms

### Work Package 5.2: Agent Memory API
**Contents**:
- Agent memory querying interface
- Past action retrieval and analysis
- Pattern recognition in agent behavior
- Causal chain analysis (what caused what)
- Memory performance optimization

**Technical Specifications**:
- REST API endpoints for memory queries
- SQL-like query language for complex retrieval
- Vector similarity search for pattern matching
- Graph analysis for causal relationships
- Memory indexing for fast retrieval

**Validation Requirements**:
- Agents can retrieve their past actions within 1 second
- Pattern recognition identifies repeated failures
- Causal analysis correctly identifies edit relationships
- Memory queries scale to 10,000+ edits

### Work Package 5.3: Causal Chain Analysis
**Contents**:
- Edit impact tracking (what broke when)
- Test failure correlation with edits
- Performance impact analysis
- Dependency change tracking
- Automated root cause identification

**Technical Specifications**:
- Test result correlation with edit timestamps
- Performance metric tracking before/after edits
- Dependency graph change detection
- Machine learning for root cause prediction
- Confidence scoring for causal relationships

**Validation Requirements**:
- Causal analysis correctly identifies breaking changes
- Root cause identification has >80% accuracy
- Analysis completes within 10 seconds for typical cases
- False positive rate <5% for causal relationships

### Work Package 5.4: Agent Self-Awareness
**Contents**:
- Context injection for agents fixing their mistakes
- Agent learning from past failures
- Mistake pattern recognition and avoidance
- Self-correction capability measurement
- Cross-agent learning from shared history

**Technical Specifications**:
- Automatic context injection when agents work on previously modified files
- Pattern matching for similar failure scenarios
- Learning algorithms for mistake avoidance
- Self-correction rate tracking and metrics
- Shared memory pool for cross-agent learning

**Validation Requirements**:
- Agents successfully identify their past mistakes
- Self-correction rate improves over time
- Mistake repetition decreases by 70%
- Context injection improves fix success rate by 50%

**Phase 5 End State Validation**:
- Agents demonstrate genuine self-awareness of past actions
- Learning patterns show measurable improvement over time
- Context injection helps agents fix their own mistakes
- System builds organizational memory across all agents

---

## Phase 6: MARS + Virtual Skeuomorphism

**Scope**: Formal review workflows with intuitive physical metaphor interfaces
**End State**: Complete review system with high-quality expert sign-offs

### Work Package 6.1: Review Package System
**Contents**:
- Review package creation from change sets
- Intelligent reviewer assignment
- Review deadline management
- Package versioning and iteration
- Review package storage and retrieval

**Technical Specifications**:
- ReviewPackage data model with full change context
- Machine learning for optimal reviewer assignment
- Configurable review deadlines with escalation
- Version control for package iterations
- Efficient storage for large packages

**Validation Requirements**:
- Review packages capture all relevant changes
- Reviewer assignment matches expertise to changes
- Package creation completes in <5 seconds
- Storage scales to 1,000+ concurrent reviews

### Work Package 6.2: Multi-Agent Review Coordination
**Contents**:
- Parallel review workflow management
- Review progress tracking and status updates
- Review conflict resolution and consensus building
- Review quality metrics and scoring
- Review completion notification and routing

**Technical Specifications**:
- State machine for review workflow states
- Real-time progress updates via WebSocket
- Consensus algorithms for conflicting reviews
- Review quality scoring based on thoroughness
- Notification system for review events

**Validation Requirements**:
- Reviews complete within configured deadlines
- Consensus algorithm resolves conflicts correctly
- Review quality scores correlate with defect detection
- Notification system has <1% message loss

### Work Package 6.3: Immutable Sign-off Records
**Contents**:
- Cryptographic sign-off signatures
- Sign-off chain verification
- Sign-off expiration and renewal
- Audit trail generation and compliance reporting
- Sign-off accountability and blame tracking

**Technical Specifications**:
- Digital signatures using standard cryptographic libraries
- Blockchain-like sign-off chains with hash verification
- Configurable sign-off expiration policies
- Compliance reports for regulatory requirements
- Immutable audit logs with tamper detection

**Validation Requirements**:
- Sign-offs are cryptographically verifiable
- Sign-off chains detect tampering attempts
- Compliance reports meet regulatory standards
- Audit trails survive all system failures

### Work Package 6.4: Virtual Skeuomorphic Interfaces
**Contents**:
- Walkie-talkie interface for agent communication
- Filing cabinet interface for history access
- Drafting table interface for shadow manipulation
- Desk organizer interface for review workflows
- Control panel interface for system monitoring

**Technical Specifications**:
- Physical metaphor API wrappers for abstract operations
- Natural language processing for physical action recognition
- Consistent physical constraints across all interfaces
- Visual feedback for physical state changes
- Help system using physical metaphor language

**Validation Requirements**:
- Skeuomorphic interfaces improve agent communication reliability by 50%
- Physical metaphors reduce agent API confusion
- Natural language recognition accuracy >90%
- Agent task completion rates improve with physical interfaces

**Phase 6 End State Validation**:
- Complete review workflow from package creation to sign-off
- Review system catches issues missed by automated validation
- Skeuomorphic interfaces demonstrably improve agent effectiveness
- System provides full audit trail for compliance requirements

---

## Success Criteria Summary

### Phase 1: Event-Sourced Foundation
- Event store handles 10K events/second with zero data loss
- State reconstruction is deterministic and performant
- System survives all failure modes gracefully

### Phase 2: Basic Bridge Server
- Coordinates 5+ agents with <100ms command validation
- Shadow filesystem maintains consistency under concurrent access
- System recovers from agent failures without data loss

### Phase 3: Policy Engine + Shadow Persistence
- 95% of operations resolved by policy in <10ms
- Persistent shadows survive server restarts
- Expert agents successfully analyze code via API

### Phase 4: FUSE Mount + LLM Validation
- Expert agents work effectively with standard Unix tools
- LLM validation catches risky operations with >90% accuracy
- Multi-expert consensus prevents dangerous operations

### Phase 5: Context-Attached History
- Agents demonstrate self-awareness and learn from mistakes
- Mistake repetition decreases by 70% over time
- Context injection improves fix success rates

### Phase 6: MARS + Virtual Skeuomorphism
- Review system catches defects missed by automation
- Skeuomorphic interfaces improve agent reliability
- Complete audit trail for compliance requirements

---

## Implementation Notes

### Technology Stack Requirements
- **Language**: Python 3.11+ for rapid prototyping and LLM integration
- **Event Store**: Initially file-based, migrate to PostgreSQL if needed
- **Policy Engine**: Open Policy Agent (OPA) with Rego policies
- **FUSE**: Python fusepy or similar FUSE binding
- **LLM Integration**: OpenAI API, Anthropic Claude API
- **Web Framework**: FastAPI for automatic OpenAPI documentation
- **Testing**: pytest with comprehensive integration tests

### Development Environment
- **Container Strategy**: Docker for reproducible builds
- **CI/CD**: GitHub Actions for automated testing and deployment
- **Monitoring**: Prometheus metrics with Grafana dashboards
- **Logging**: Structured JSON logging with correlation IDs
- **Documentation**: Automatic API docs + architectural decision records

### Quality Gates
Each phase must pass comprehensive validation before proceeding to the next phase. No exceptions for timeline pressure - technical debt in foundation phases will compound exponentially.

The key to success: **Build less, validate more**. Each phase delivers a complete, working system that provides value even if subsequent phases are never built.