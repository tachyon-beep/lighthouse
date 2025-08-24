# HLD Bridge Architectural Remediation

## Overview

This document addresses the critical architectural gaps identified by the system architect review, providing detailed specifications to align our implementation with the HLD vision.

## 1. Speed Layer Architecture (Critical Gap)

### Vision Alignment
**HLD Requirement**: <100ms response for 99% of operations through policy-first validation

### Detailed Architecture

#### Speed Layer Components
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   In-Memory     │    │   Policy Cache   │    │  Pattern Cache  │
│   Rule Cache    │◄──►│   (Hot Rules)    │◄──►│  (ML Patterns)  │
│   (<1ms)        │    │   (1-5ms)        │    │   (5-10ms)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ▲                        ▲                        ▲
         │                        │                        │
    ┌────▼────────────────────────▼────────────────────────▼────┐
    │               Speed Layer Dispatcher                      │
    │  Route 99% of requests in <100ms, escalate 1% to LLM    │
    └───────────────────────────────────────────────────────────┘
```

#### Implementation Strategy
1. **Hot Path Optimization**: Keep 1000 most common patterns in memory
2. **Bloom Filters**: Quick negative lookups for unknown patterns
3. **Consistent Hashing**: Distribute load across validation nodes
4. **Warming Strategy**: Pre-populate cache from historical validation data

#### Performance Specifications
- **Memory Cache**: Redis/Hazelcast with 1GB allocation
- **Cache Hit Ratio**: >95% for common operations
- **Cache Miss Penalty**: <10ms policy engine lookup
- **Refresh Strategy**: Incremental updates every 60 seconds

### Code Structure
```python
class SpeedLayerDispatcher:
    def __init__(self):
        self.memory_cache = MemoryRuleCache(max_size=10000)
        self.policy_cache = PolicyEngineCache(ttl=300)
        self.pattern_cache = MLPatternCache(model_path="/opt/patterns.pkl")
    
    async def validate_fast_path(self, request: ValidationRequest) -> ValidationResult:
        # 1. Memory cache (sub-millisecond)
        if result := self.memory_cache.get(request.command_hash):
            return result
            
        # 2. Policy cache (1-5ms)
        if result := await self.policy_cache.evaluate(request):
            self.memory_cache.set(request.command_hash, result)
            return result
            
        # 3. ML pattern cache (5-10ms)
        if confidence > 0.9:
            result = await self.pattern_cache.predict(request)
            return result
            
        # 4. Escalate to expert layer
        return await self.escalate_to_expert_layer(request)
```

## 2. Complete FUSE Mount Specification (Critical Gap)

### Vision Alignment
**HLD Requirement**: Full POSIX filesystem enabling expert agents to use standard Unix tools

### Virtual Filesystem Structure
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
│       ├── 1704454200_001.json
│       └── 1704454201_002.json
├── context/                   # Agent context packages (read-only)
│   ├── security_review_v2.1/
│   │   ├── manifest.json
│   │   ├── architectural_context/
│   │   ├── implementation_context/
│   │   └── historical_context/
│   └── performance_audit_v1.3/
└── streams/                   # Live event streams (named pipes)
    ├── validation_requests
    ├── expert_responses
    └── pair_sessions
```

### FUSE Operations Implementation
```python
class LighthouseFUSE:
    def getattr(self, path, fh=None):
        """Get file attributes - enables ls, stat, file access"""
        if path.startswith('/current/'):
            return self.get_live_file_attrs(path)
        elif path.startswith('/history/'):
            return self.get_historical_attrs(path)
        elif path.startswith('/shadows/'):
            return self.get_shadow_attrs(path)
    
    def read(self, path, length, offset, fh):
        """Read file contents - enables cat, grep, editors"""
        if path.startswith('/current/'):
            return self.read_live_file(path, length, offset)
        elif path.startswith('/history/'):
            return self.read_historical_snapshot(path, length, offset)
        elif path.startswith('/shadows/'):
            return self.read_annotations(path, length, offset)
    
    def write(self, path, buf, offset, fh):
        """Write file contents - enables editors, direct modifications"""
        if path.startswith('/current/'):
            # Event-source the write operation
            event = Event(
                event_type=EventType.FILE_MODIFIED,
                aggregate_id=path,
                data={"offset": offset, "content": buf.decode()}
            )
            await self.event_store.append(event)
            return len(buf)
    
    def readdir(self, path, fh):
        """List directory contents - enables ls, find"""
        if path == '/':
            return ['.', '..', 'current', 'shadows', 'history', 'context', 'streams']
        # Dynamic directory listing based on event store state
        return self.get_dynamic_directory_listing(path)
```

### Expert Agent Integration
```bash
# Expert agents can now use standard Unix tools:
cd /mnt/lighthouse/project/current/
find . -name "*.py" -exec grep -l "security" {} \;
cat src/main.py
vim src/main.py  # Direct editing with event-sourced persistence
diff history/2024-01-15T10:30:00Z/src/main.py current/src/main.py
```

## 3. Full Event-Sourcing Patterns (Critical Gap)

### Vision Alignment
**HLD Requirement**: Complete event-sourced design with time travel debugging and perfect audit trails

### Event-Sourced Aggregates
```python
class ProjectAggregate:
    """Represents the entire project state as an event-sourced aggregate"""
    
    def __init__(self):
        self.current_state = ProjectState()
        self.version = 0
        self.uncommitted_events = []
    
    def handle_file_modification(self, path: str, content: str, agent_id: str):
        """Business logic for file modifications"""
        # Validate the change
        if not self.can_modify_file(path, agent_id):
            raise SecurityError("Agent not authorized to modify this file")
        
        # Generate event
        event = FileModifiedEvent(
            aggregate_id=self.aggregate_id,
            path=path,
            content=content,
            previous_hash=self.current_state.get_file_hash(path),
            agent_id=agent_id
        )
        
        # Apply event to state
        self.apply_event(event)
        self.uncommitted_events.append(event)
    
    def apply_event(self, event: Event):
        """Apply event to current state - enables time travel"""
        if isinstance(event, FileModifiedEvent):
            self.current_state.update_file(event.path, event.content)
        elif isinstance(event, FileDeletedEvent):
            self.current_state.delete_file(event.path)
        # ... more event handlers
        
        self.version += 1

class ProjectStateRebuilder:
    """Rebuild project state at any point in time"""
    
    async def rebuild_at_timestamp(self, timestamp: datetime) -> ProjectState:
        """Time travel debugging - rebuild state at specific time"""
        events = await self.event_store.query(
            filter=EventFilter(before_timestamp=timestamp),
            order_by="sequence"
        )
        
        aggregate = ProjectAggregate()
        for event in events:
            aggregate.apply_event(event)
        
        return aggregate.current_state
```

### Time Travel Operations
```python
class TimeTravelDebugger:
    async def get_file_history(self, path: str) -> List[FileVersion]:
        """Get complete history of a file"""
        events = await self.event_store.query(
            filter=EventFilter(
                event_types=[EventType.FILE_MODIFIED, EventType.FILE_CREATED],
                aggregate_ids=[path]
            )
        )
        
        versions = []
        for event in events:
            versions.append(FileVersion(
                content=event.data["content"],
                timestamp=event.timestamp,
                agent_id=event.metadata.get("agent_id"),
                change_reason=event.metadata.get("reason")
            ))
        
        return versions
    
    async def replay_session(self, session_id: str) -> SessionReplay:
        """Replay entire pair programming session"""
        session_events = await self.event_store.query(
            filter=EventFilter(
                metadata_filter={"session_id": session_id}
            )
        )
        
        return SessionReplay(
            events=session_events,
            initial_state=await self.rebuild_at_timestamp(session_events[0].timestamp),
            final_state=await self.rebuild_at_timestamp(session_events[-1].timestamp)
        )
```

## 4. AST Anchoring System (Critical Gap)

### Vision Alignment
**HLD Requirement**: Tree-sitter AST spans ensuring annotations survive refactoring

### AST Anchor Implementation
```python
class ASTAnchor:
    """Persistent reference to AST nodes that survives refactoring"""
    
    def __init__(self, file_path: str, node_type: str, 
                 start_point: Tuple[int, int], end_point: Tuple[int, int],
                 context_hash: str, parent_anchor: Optional['ASTAnchor'] = None):
        self.file_path = file_path
        self.node_type = node_type  # function_definition, class_definition, etc.
        self.start_point = start_point  # (row, col)
        self.end_point = end_point
        self.context_hash = context_hash  # Hash of surrounding context
        self.parent_anchor = parent_anchor
        self.anchor_id = self._generate_anchor_id()
    
    def _generate_anchor_id(self) -> str:
        """Generate stable anchor ID based on structure, not position"""
        context = f"{self.node_type}:{self.context_hash}"
        if self.parent_anchor:
            context = f"{self.parent_anchor.anchor_id}::{context}"
        return hashlib.sha256(context.encode()).hexdigest()[:16]

class ASTAnchorManager:
    def __init__(self):
        self.parser = tree_sitter.Parser()
        # Load language parsers
        self.parsers = {
            '.py': tree_sitter.Language(tree_sitter_python.language()),
            '.js': tree_sitter.Language(tree_sitter_javascript.language()),
            '.go': tree_sitter.Language(tree_sitter_go.language()),
        }
    
    def create_anchors(self, file_path: str, content: str) -> List[ASTAnchor]:
        """Create AST anchors for all significant nodes"""
        ext = Path(file_path).suffix
        if ext not in self.parsers:
            return []
        
        self.parser.set_language(self.parsers[ext])
        tree = self.parser.parse(content.encode())
        
        anchors = []
        self._traverse_tree(tree.root_node, file_path, content, anchors)
        return anchors
    
    def _traverse_tree(self, node, file_path: str, content: str, 
                      anchors: List[ASTAnchor], parent_anchor=None):
        """Recursively create anchors for significant nodes"""
        if node.type in ['function_definition', 'class_definition', 'method_definition']:
            # Get context for stable hashing
            context = self._get_node_context(node, content)
            context_hash = hashlib.sha256(context.encode()).hexdigest()
            
            anchor = ASTAnchor(
                file_path=file_path,
                node_type=node.type,
                start_point=node.start_point,
                end_point=node.end_point,
                context_hash=context_hash,
                parent_anchor=parent_anchor
            )
            anchors.append(anchor)
            parent_anchor = anchor
        
        # Recurse to children
        for child in node.children:
            self._traverse_tree(child, file_path, content, anchors, parent_anchor)
    
    def resolve_anchor(self, anchor: ASTAnchor, current_content: str) -> Optional[ASTAnchor]:
        """Find anchor in modified code - handles refactoring"""
        # Try exact position first (fast path)
        if self._anchor_matches_position(anchor, current_content):
            return anchor
        
        # Fall back to structural search
        return self._find_by_structure(anchor, current_content)
```

### Shadow File Integration
```python
class ShadowFileManager:
    def __init__(self, ast_anchor_manager: ASTAnchorManager):
        self.anchor_manager = ast_anchor_manager
    
    def get_shadow_content(self, file_path: str) -> Dict[str, Any]:
        """Get structured annotations for a file"""
        shadow_path = f"{file_path}.annotations.json"
        
        # Load existing annotations
        annotations = self.load_annotations(shadow_path)
        
        # Resolve all anchors to current positions
        resolved_annotations = {}
        current_content = self.read_file(file_path)
        
        for anchor_id, annotation in annotations.items():
            anchor = ASTAnchor.from_dict(annotation["anchor"])
            resolved_anchor = self.anchor_manager.resolve_anchor(anchor, current_content)
            
            if resolved_anchor:
                resolved_annotations[anchor_id] = {
                    "anchor": resolved_anchor.to_dict(),
                    "content": annotation["content"],
                    "metadata": annotation["metadata"]
                }
        
        return resolved_annotations
```

## 5. Expert Coordination FUSE Integration

### Vision Alignment
**HLD Requirement**: Expert agents interact through FUSE as primary interface

### Expert Agent Workflow
```python
class ExpertAgentInterface:
    """Expert agents interact through FUSE mount as primary interface"""
    
    def __init__(self, mount_point: str = "/mnt/lighthouse/project"):
        self.mount_point = Path(mount_point)
        self.context_dir = self.mount_point / "context"
        self.streams_dir = self.mount_point / "streams"
    
    async def receive_validation_request(self) -> ValidationRequest:
        """Expert agents read from validation stream"""
        stream_path = self.streams_dir / "validation_requests"
        
        # Named pipe - blocks until data available
        async with aiofiles.open(stream_path, 'r') as f:
            request_json = await f.readline()
            return ValidationRequest.from_json(request_json)
    
    async def submit_expert_response(self, response: ExpertResponse):
        """Expert agents write to response stream"""
        stream_path = self.streams_dir / "expert_responses"
        
        async with aiofiles.open(stream_path, 'a') as f:
            await f.write(response.to_json() + '\n')
    
    def get_context_package(self, package_id: str) -> ContextPackage:
        """Load context package for informed decision-making"""
        package_path = self.context_dir / package_id
        manifest = json.loads((package_path / "manifest.json").read_text())
        
        return ContextPackage(
            package_id=package_id,
            architectural_context=self._load_adrs(package_path / "architectural_context"),
            implementation_context=self._load_source_files(package_path / "implementation_context"),
            historical_context=self._load_event_ranges(package_path / "historical_context")
        )
```

## Performance & Scalability Specifications

### Speed Layer Performance
- **Memory Cache**: <1ms response time, 99.9% availability
- **Policy Engine**: <10ms response time, >95% cache hit ratio
- **ML Patterns**: <100ms response time for complex pattern matching

### FUSE Mount Performance  
- **File Operations**: <5ms for stat, read, write operations
- **Directory Listing**: <10ms for directories with <1000 entries
- **Large File Handling**: Streaming for files >100MB

### Event Store Integration
- **Throughput**: >10,000 events/second sustained
- **Query Performance**: <100ms for typical time-travel queries
- **Storage Efficiency**: <1GB storage per 1M events

## Next Steps for Implementation

1. **Speed Layer Implementation** - 3 weeks
2. **FUSE Mount Development** - 4 weeks  
3. **AST Anchoring System** - 3 weeks
4. **Expert Coordination Integration** - 2 weeks
5. **Performance Optimization** - 2 weeks

Total: ~14 weeks for complete HLD-aligned bridge implementation