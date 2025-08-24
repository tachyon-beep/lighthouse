# HLD Bridge Implementation Plan

## Overview

This document details the implementation plan for the Lighthouse Validation Bridge as specified in the High-Level Design (HLD). The bridge serves as the central coordination hub for multi-agent systems, providing event-sourced validation, expert agent coordination, and real-time pair programming capabilities.

## Architecture Components

### 1. Speed Layer Architecture (Primary Path)
**HLD Requirement**: <100ms response for 99% of operations

#### Speed Layer Components
- **Memory Cache**: Sub-millisecond lookups for hot patterns (Redis/Hazelcast)
- **Policy Cache**: 1-5ms policy engine evaluation with Bloom filters
- **Pattern Cache**: 5-10ms ML pattern matching for complex cases
- **Performance**: 99% of requests served in <100ms, 95% cache hit ratio

#### Implementation Strategy
```python
class SpeedLayerDispatcher:
    async def validate_fast_path(self, request: ValidationRequest):
        # 1. Memory cache (sub-millisecond)
        if result := self.memory_cache.get(request.command_hash):
            return result
        # 2. Policy cache (1-5ms) 
        if result := await self.policy_cache.evaluate(request):
            return result
        # 3. Escalate to expert layer (rare)
        return await self.escalate_to_expert_layer(request)
```

### 2. Event-Sourced Foundation
**Integration**: Complete event-sourced architecture with Phase 1 Event Store
- **Event-Sourced Aggregates**: ProjectAggregate with full business logic
- **Time Travel Debugging**: Rebuild any project state from event history
- **Perfect Audit Trails**: Every change tracked with agent attribution
- **Real-time Streaming**: WebSocket connections for live event streams

#### Event-Sourced Implementation
```python
class ProjectAggregate:
    def handle_file_modification(self, path: str, content: str, agent_id: str):
        # Validate change
        if not self.can_modify_file(path, agent_id):
            raise SecurityError("Agent not authorized")
        
        # Generate and apply event
        event = FileModifiedEvent(path=path, content=content, agent_id=agent_id)
        self.apply_event(event)
        self.uncommitted_events.append(event)
```

### 3. Multi-Tier Validation System (Expert Escalation)

#### Tier 1: Speed Layer (Primary - 99% of requests)
- **Memory Cache**: <1ms for hot patterns
- **Policy Engine**: <10ms for rule evaluation
- **Coverage**: 99% of validation requests

#### Tier 2: Expert LLM Validation (Escalation - <1%)
- **Trigger**: Speed layer returns UNCERTAIN or ESCALATE  
- **Expert Selection**: Context-aware routing via FUSE interface
- **Response Time**: <30 seconds with fallback to DENY
- **Learning Loop**: Expert decisions become new policy rules

#### Tier 3: Human Approval (Critical Operations)
- **Trigger**: High-risk operations (system modifications, production deployments)
- **Notification**: Real-time alerts to approved human operators
- **Timeout**: 5-minute approval window with automatic DENY

### 4. FUSE Mount Filesystem (`/mnt/lighthouse/project/`) 
**HLD Requirement**: Full POSIX filesystem enabling expert agents to use standard Unix tools

#### Complete Virtual Filesystem Structure
```
/mnt/lighthouse/project/
├── current/                    # Live project state (read-write)
│   ├── src/                   # Source code with live updates
│   ├── docs/                  # Documentation  
│   └── tests/                 # Test files
├── shadows/                   # AST-anchored annotations (read-write)
│   ├── src/
│   │   └── main.py.annotations.json    # Structured annotations
│   └── docs/
├── history/                   # Time-travel debugging (read-only)
│   ├── 2024-01-15T10:30:00Z/  # Snapshot directories
│   ├── 2024-01-15T10:31:00Z/
│   └── events/                # Raw event stream access
├── context/                   # Agent context packages (read-only)
│   ├── security_review_v2.1/
│   └── performance_audit_v1.3/
└── streams/                   # Live event streams (named pipes)
    ├── validation_requests
    ├── expert_responses
    └── pair_sessions
```

#### Expert Agent Unix Tool Integration
```bash
# Expert agents use standard Unix tools:
cd /mnt/lighthouse/project/current/
find . -name "*.py" -exec grep -l "security" {} \;
cat src/main.py
vim src/main.py  # Direct editing with event-sourced persistence
diff history/2024-01-15T10:30:00Z/src/main.py current/src/main.py
```

#### FUSE Operations Implementation
- **getattr**: Enable ls, stat, file access
- **read/write**: Enable cat, grep, editors with event-sourcing
- **readdir**: Enable ls, find with dynamic directory listing
- **Performance**: <5ms for common operations, streaming for large files

### 5. AST Anchoring System
**HLD Requirement**: Tree-sitter AST spans ensuring annotations survive refactoring

#### Persistent AST Anchors
```python
class ASTAnchor:
    """Persistent reference to AST nodes that survives refactoring"""
    
    def __init__(self, file_path: str, node_type: str, 
                 start_point: Tuple[int, int], end_point: Tuple[int, int],
                 context_hash: str, parent_anchor: Optional['ASTAnchor'] = None):
        self.anchor_id = self._generate_stable_anchor_id()
        # Structure-based ID, not position-based
    
    def _generate_stable_anchor_id(self) -> str:
        """Generate stable anchor ID based on structure, not position"""
        context = f"{self.node_type}:{self.context_hash}"
        if self.parent_anchor:
            context = f"{self.parent_anchor.anchor_id}::{context}"
        return hashlib.sha256(context.encode()).hexdigest()[:16]
```

#### Anchor Resolution After Refactoring
- **Exact Position**: Try original position first (fast path)
- **Structural Search**: Find by AST structure and context when moved
- **Parent Relationships**: Use hierarchical anchoring for reliability
- **Context Hashing**: Hash surrounding context for stable identification

#### Shadow File Integration  
- **Transparent Files**: Virtual files in `/shadows/` directory via FUSE
- **JSON Annotations**: Structured metadata with resolved anchor positions
- **Real-time Updates**: Anchor resolution on every file access
- **Event Sourcing**: All annotations stored as events for time travel

### 6. Expert Agent Coordination via FUSE
**HLD Requirement**: Expert agents interact through FUSE as primary interface

#### FUSE-First Expert Workflow
```python
class ExpertAgentInterface:
    """Expert agents interact through FUSE mount as primary interface"""
    
    async def receive_validation_request(self) -> ValidationRequest:
        """Expert agents read from validation stream"""
        stream_path = "/mnt/lighthouse/project/streams/validation_requests"
        # Named pipe - blocks until data available
        async with aiofiles.open(stream_path, 'r') as f:
            request_json = await f.readline()
            return ValidationRequest.from_json(request_json)
    
    def get_context_package(self, package_id: str) -> ContextPackage:
        """Load context package for informed decision-making"""
        package_path = f"/mnt/lighthouse/project/context/{package_id}"
        # Standard file operations work transparently
        manifest = json.loads(Path(package_path + "/manifest.json").read_text())
```

#### Expert Discovery and Routing
- **Capability Matching**: Route based on file types, technologies, expertise
- **Historical Success**: Track expert performance for better routing  
- **Load Balancing**: Distribute requests across available experts
- **Context Packages**: Provide experts with relevant project context

### 7. Pair Programming Hub
**Real-time Collaboration**: WebSocket-based multi-agent coordination with FUSE integration
- **Session Management**: Create, join, leave sessions via FUSE streams
- **Shared Context**: Synchronized editor state through `/current/` filesystem
- **Event Sourcing**: All collaboration events stored for replay
- **FUSE Integration**: Pair sessions accessible as filesystem streams
- **Recording**: Complete session replay for learning and debugging

## Implementation Phases (Updated with HLD Alignment)

### Phase 1: Speed Layer Foundation (Week 1-2)
1. **Speed Layer Implementation**
   - Memory cache with Redis/Hazelcast (sub-millisecond)
   - Policy engine integration with Bloom filters (1-5ms)
   - ML pattern cache for complex cases (5-10ms)
   - Performance monitoring and optimization

2. **Event-Sourced Architecture**
   - ProjectAggregate with complete business logic
   - Time travel debugging capabilities
   - Perfect audit trail implementation
   - Real-time event streaming via WebSockets

3. **Basic HTTP/WebSocket Server**
   - REST endpoints optimized for speed layer
   - WebSocket handlers for real-time coordination
   - Health checks and performance monitoring

### Phase 2: Complete FUSE Implementation (Week 3-4)
1. **Full POSIX Filesystem**
   - Complete FUSE operations (getattr, read, write, readdir)
   - Virtual filesystem structure with all directories
   - Performance optimization (<5ms for common operations)
   - Integration with event store for persistence

2. **AST Anchoring System**
   - tree-sitter integration for all supported languages
   - Stable anchor ID generation based on structure
   - Anchor resolution after refactoring
   - Event-sourced annotation storage

### Phase 3: Expert Coordination (Week 5)
1. **FUSE-Based Expert Interface**
   - Named pipe streams for expert communication
   - Context package system via FUSE filesystem
   - Expert agent FUSE workflow implementation
   - Standard Unix tool integration

2. **Validation Escalation System** 
   - Speed layer to expert escalation logic
   - Context-aware expert routing
   - Response aggregation and learning loop
   - Performance monitoring and optimization

### Phase 4: Advanced Features (Week 6-7)
1. **Pair Programming Hub**
   - FUSE-integrated session management
   - Real-time state synchronization via `/current/`
   - Event-sourced collaboration protocols
   - Complete session replay capabilities

2. **Time Travel Debugging**
   - Historical state reconstruction from events
   - `/history/` directory with timestamped snapshots
   - Event replay through FUSE interface
   - Integration with shadow filesystem annotations

## Technical Specifications

### API Endpoints
```
POST   /validate              # Submit validation request
GET    /validate/{id}         # Get validation status
POST   /agents/register       # Register expert agent
GET    /agents/discover       # Find suitable experts
POST   /sessions/pair         # Start pair programming session
WS     /stream/events         # Real-time event stream
WS     /sessions/{id}         # Pair programming WebSocket
GET    /health                # System health check
```

### Event Types
```python
# Bridge-specific events
VALIDATION_REQUEST_SUBMITTED
VALIDATION_POLICY_APPLIED
VALIDATION_ESCALATED_TO_EXPERT
VALIDATION_DECISION_MADE
EXPERT_AGENT_SUMMONED
EXPERT_AGENT_RESPONDED
PAIR_SESSION_STARTED
PAIR_SESSION_ENDED
SHADOW_ANNOTATION_CREATED
SHADOW_ANNOTATION_UPDATED
```

### Performance Requirements (HLD-Aligned)
- **Speed Layer**: <100ms for 99% of operations, 95% cache hit ratio
- **Memory Cache**: <1ms response time, 99.9% availability
- **Policy Engine**: <10ms evaluation, Bloom filter optimization
- **Event Store Throughput**: >10,000 events/second sustained
- **FUSE Operations**: <5ms for stat/read/write, <10ms for large directories
- **Time Travel Queries**: <100ms for typical historical reconstructions
- **WebSocket Connections**: Support 100+ concurrent agents
- **Memory Usage**: <2GB baseline, <100MB per active session

### Security Considerations
- **Authentication**: Extend Phase 1 HMAC token system
- **Authorization**: Role-based access with capability restrictions
- **Input Validation**: Comprehensive sanitization for all inputs
- **Rate Limiting**: Per-agent request limits and quotas
- **Audit Logging**: All validation decisions logged to event store

## Integration Points

### With Phase 1 Event Store
- **Event Production**: Bridge generates validation and coordination events
- **Event Consumption**: Bridge subscribes to relevant event streams
- **Authentication**: Uses existing HMAC token system
- **Persistence**: All bridge state stored as events

### With External Tools
- **Policy Engine**: OPA/Cedar for rule evaluation
- **tree-sitter**: AST parsing for shadow filesystem
- **FUSE**: Filesystem interface for expert agents
- **WebSocket**: Real-time communication protocol

### With Claude Code
- **MCP Integration**: Expose bridge functionality as MCP tools
- **Hook Integration**: Existing validation hooks route through bridge
- **Status Reporting**: Bridge health visible in Claude Code interface

## Success Metrics
1. **Validation Accuracy**: >95% correct decisions
2. **Response Time**: 90th percentile <30 seconds
3. **Expert Utilization**: Balanced load across available agents
4. **System Uptime**: >99.9% availability
5. **Learning Rate**: New policy rules reduce escalation over time

## Risk Mitigation
1. **Bridge Failure**: Graceful degradation to basic validation
2. **Expert Unavailability**: Fallback to policy-only decisions
3. **Performance Issues**: Circuit breakers and request queuing
4. **Security Breaches**: Comprehensive input validation and audit trails

## Next Steps
1. **System Architect Approval**: ✅ Completed - Critical gaps addressed
2. **Speed Layer Implementation**: Begin Phase 1 with performance-first approach
3. **FUSE Mount Development**: Complete POSIX filesystem with expert tool integration
4. **AST Anchoring System**: Implement refactoring-resistant annotation system
5. **Integration Testing**: Verify all components work together seamlessly

## HLD Alignment Status
- **Speed Layer Architecture**: ✅ Fully specified
- **Event-Sourced Foundation**: ✅ Complete with time travel
- **FUSE Mount Filesystem**: ✅ Full POSIX with Unix tool support
- **AST Anchoring System**: ✅ Refactoring-resistant annotations
- **Expert Coordination**: ✅ FUSE-first interface design
- **Performance Requirements**: ✅ HLD-compliant specifications

**Total Implementation Time**: ~14 weeks for complete HLD-aligned bridge