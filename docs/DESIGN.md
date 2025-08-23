# Lighthouse: Multi-Agent Coordination System

## Multi-Agent Coordination System for Claude Code

### Executive Summary

Lighthouse transforms Claude Code's isolated fire-and-forget agents into a coordinated swarm intelligence. It provides real-time validation, collaboration protocols, and safety enforcement through a lightweight MCP bridge server, enhanced with built-in task management and dynamic agent spawning.

---

## Core Architecture

### 1. War Room Pattern

All agents spawn simultaneously at task start:

- **Supervisor**: Orchestrates and monitors exceptions
- **Validator**: Watches ALL commands in real-time
- **Specialists**: Wait in STANDBY until needed
- **Workers**: Execute primary tasks in ACTIVE mode

```python
# Supervisor orchestration with built-in tools
bridge.reset()                    # Fresh session
team = await bridge.spawn_war_room([
    Task(description="Validation oversight", subagent_type="general-purpose"),
    Task(description="Database expertise", subagent_type="general-purpose"),
    Task(description="Security analysis", subagent_type="general-purpose")
])
bridge.monitor(timeout=300)       # Watch for exceptions
bridge.shutdown()                 # Clean termination
```

### 2. Three-Layer Safety System

#### Layer 1: Hook-Based Command Interception

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Edit|Write|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "python3 .claude/hooks/validate_command.py"
      }]
    }]
  }
}
```

#### Layer 2: Safety Register (Read-Before-Write)

```python
class SafetyRegister:
    def __init__(self):
        self.files_read = set()
        self.files_written = set()
        self.dependency_rules = []
        self.global_prerequisites = ['HLD.md', 'ARCHITECTURE.md']
    
    def can_write(self, filepath):
        # New files: always allowed
        # Existing files: must be read first
        # Dependencies: must read prerequisites
        return self.validate_dependencies(filepath)
```

#### Layer 3: Bridge-Based Validation

```text
Hook → Bridge → Validator → Approve/Reject → Execution/Block
```

---

## Built-in Tool Integration

### Task Management with TodoWrite

```python
class TaskCoordinator:
    async def initialize_mission(self, description):
        """Create coordinated todo list for all agents"""
        mission_todos = [
            {"content": f"Complete: {description}", "status": "pending", "activeForm": f"Completing: {description}"},
            {"content": "Validate all operations", "status": "pending", "activeForm": "Validating operations"},
            {"content": "Monitor for exceptions", "status": "pending", "activeForm": "Monitoring exceptions"}
        ]
        await self.update_master_todos(mission_todos)
        return mission_todos
    
    async def assign_task(self, agent_id, task_description, priority="normal"):
        """Assign task to specific agent with tracking"""
        task_todo = {
            "content": f"{agent_id}: {task_description}",
            "status": "pending", 
            "activeForm": f"{agent_id} working on: {task_description}"
        }
        await self.add_agent_task(agent_id, task_todo)
```

### Dynamic Agent Spawning with Task Tool

```python
class AgentSpawner:
    async def spawn_war_room(self, mission_description):
        """Launch coordinated agent team"""
        agents = await asyncio.gather(
            Task(
                description="Supervisor oversight", 
                prompt=f"You are the supervisor for: {mission_description}. Monitor todos and exceptions.",
                subagent_type="general-purpose"
            ),
            Task(
                description="Command validation",
                prompt="You are the validator. Watch ALL commands. Use REJECT for dangerous operations.",
                subagent_type="general-purpose"
            ),
            Task(
                description="Specialist standby",
                prompt="You are a specialist on standby. Respond to REQUEST commands with honest skill assessment.",
                subagent_type="general-purpose"
            )
        )
        return agents
    
    async def spawn_specialist(self, expertise, context):
        """Dynamically spawn expert when needed"""
        specialist = Task(
            description=f"{expertise} specialist",
            prompt=f"You are a {expertise} expert. Context: {context}. Provide domain expertise.",
            subagent_type="general-purpose"
        )
        return specialist
```

### External Knowledge Integration

```python
class KnowledgeAugmentation:
    async def research_solution(self, problem_description):
        """Augment agent knowledge during crisis"""
        # WebSearch for current best practices
        search_results = await WebSearch(
            query=f"{problem_description} best practices 2025",
            blocked_domains=["stackoverflow.com"]  # Focus on official docs
        )
        
        # WebFetch specific documentation
        if "api" in problem_description.lower():
            api_docs = await WebFetch(
                url="https://docs.example.com/api",
                prompt="Extract relevant API patterns and security considerations"
            )
            
        return {"search_results": search_results, "documentation": api_docs}
```

---

## Command Protocol

### Core Commands (22 total)

```bash
# Session Management
JOIN <role> <mode>                  # JOIN validator ACTIVE
LEAVE [reason]                      # LEAVE "task completed"
STATUS <state> [detail]              # STATUS WORKING "optimizing"

# Task Management (New)
TODO_ADD <description> <priority>    # TODO_ADD "optimize query" high
TODO_UPDATE <id> <status>           # TODO_UPDATE task_001 in_progress
TODO_ASSIGN <task_id> <agent>       # TODO_ASSIGN task_001 @dba

# Messaging
PUB <topic> <message>               # PUB /alerts/critical "risk detected"
SUB <pattern>                       # SUB /alerts/* or SUB *

# Collaboration
REQUEST <skill>:<level> <desc>      # REQUEST dba:expert "optimize query"
AVAILABLE <level> [pitch]            # AVAILABLE expert "10 years experience"
SPAWN_SPECIALIST <expertise>        # SPAWN_SPECIALIST database_optimization

# Pair Programming (New)
PAIR_REQUEST <task> <complexity>    # PAIR_REQUEST "implement auth" complex
PAIR_ACCEPT <task_id>               # PAIR_ACCEPT task_001  
PAIR_SUGGEST <code_improvement>     # PAIR_SUGGEST "use const instead of let"
PAIR_REVIEW <implementation>        # PAIR_REVIEW "function validateInput()..."

# Validation
PROPOSE <id> <command>              # PROPOSE cmd_001 "DROP TABLE test"
APPROVE/REJECT <id> [reason]        # REJECT cmd_001 "production table!"

# Storage
SET <key> <value>                   # SET api_url "http://localhost"
GET <key>                           # GET api_url

# Control
ALERT <severity> <message>          # ALERT critical "stopping all work"
RESEARCH <topic>                    # RESEARCH "postgresql indexing strategies"
SHUTDOWN [reason]                    # SHUTDOWN "task complete"

# Utilities
UTC_NOW                             # UTC_NOW -> "2025-01-15T14:30:25.123456Z"
HASH_SHA256 <content>               # HASH_SHA256 "myfile.txt content" -> "a1b2c3..."
```

### Crisis Mode: CONCLAVE Protocol with Task Coordination

When critical issues arise, structured escalation with automated task management:

```bash
# Initiate crisis conference with todo breakdown
CONCLAVE <severity> <issue>         # CONCLAVE critical "data corruption detected"

# System creates crisis todos automatically:
# 1. Assess crisis scope
# 2. Research solutions
# 3. Gather expert opinions  
# 4. Propose fixes
# 5. Vote on solutions
# 6. Execute chosen solution
# 7. Verify resolution

# Structured response rounds
CONCLAVE_STATUS <agent> <assessment>  # Each agent reports, updates todos
CONCLAVE_RESEARCH <topic>             # Trigger WebSearch/WebFetch for solutions
CONCLAVE_SPAWN <expertise>            # Dynamically spawn domain experts
CONCLAVE_PROPOSE <solution>           # Propose fixes
CONCLAVE_VOTE <proposal_id> <vote>    # Vote on solutions
CONCLAVE_EXECUTE <proposal_id>        # Execute chosen solution
CONCLAVE_RESOLVE                      # End crisis mode, update final todos
```

Enhanced example flow:

```text
validator: CONCLAVE critical "SQL injection in production"
system: [Auto-creates crisis todos and spawns security specialist]
supervisor: CONCLAVE_STATUS "reviewing code changes" 
system: TODO_UPDATE crisis_assess completed
security_specialist: CONCLAVE_RESEARCH "SQL injection mitigation"
system: [WebSearch for latest security practices]
security_specialist: CONCLAVE_PROPOSE "rollback and parameterized queries"
[Round-robin voting with todo tracking]
supervisor: CONCLAVE_EXECUTE rollback_001
system: TODO_UPDATE crisis_execute in_progress
[Crisis resolved, all todos marked completed]
supervisor: CONCLAVE_RESOLVE
```

---

## Enhanced Storage Systems

### 1. Persistent Register (Session-Long)

```python
SET config:api_url "https://api.example.com"
SET decision:database "PostgreSQL"
SET artifact:schema "CREATE TABLE..."
```

### 2. Ephemeral Cache (5-minute TTL)

```python
CACHE_SET temp:query_result "{...}"     # Auto-expires
CACHE_GET temp:query_result              # Returns null after TTL
```

### 3. Artifact Exchange

```python
ARTIFACT_PUT code:parser "def parse()..."   # Share code
ARTIFACT_GET code:parser                     # Retrieve code
ARTIFACT_LIST                                # See available artifacts
```

### 4. Task State Management (New)

```python
class TaskStateManager:
    def __init__(self):
        self.agent_todos = {}      # Per-agent task lists
        self.master_todos = []     # Mission-wide objectives
        self.crisis_todos = []     # Crisis response tasks
        
    async def sync_todos_with_bridge(self):
        """Keep todo state synchronized across agents"""
        for agent_id, todos in self.agent_todos.items():
            await self.bridge.notify_agent(agent_id, "todo_update", todos)
```

---

## Dependency Rules Configuration

### .claude/safety-rules.json

```json
{
  "global_prerequisites": [
    "HLD.md",
    "CONTRIBUTING.md", 
    ".claude/project-rules.md"
  ],
  
  "dependency_rules": [
    {
      "pattern": "**/*.test.*",
      "requires": ["${source_file}", "${test_file}"],
      "message": "Must read both source and test"
    },
    {
      "pattern": "api/**/*",
      "requires": ["openapi.yaml", "api/README.md"],
      "message": "Must understand API contracts"
    },
    {
      "pattern": "migrations/*.sql",
      "requires": ["database/schema.sql", "HLD.md"],
      "message": "Must understand schema before migrations"
    }
  ],
  
  "enforcement_levels": {
    "production/**": "STRICT",
    "tests/**": "NORMAL",
    "docs/**": "LENIENT"
  },
  
  "task_automation": {
    "crisis_response": [
      "Assess crisis scope and impact",
      "Research known solutions and mitigations", 
      "Gather domain expert opinions",
      "Evaluate proposed solutions",
      "Execute consensus solution",
      "Verify crisis resolution"
    ],
    "standard_workflow": [
      "Read project prerequisites", 
      "Understand task requirements",
      "Plan implementation approach",
      "Execute with validation",
      "Test and verify results"
    ]
  }
}
```

---

## Enhanced Topic Hierarchy

```text
/system/heartbeat            # System-wide heartbeat (every 60s)
/system/personal_heartbeat   # Individual agent status
/system/agent_join          # Agent connection events  
/system/agent_leave         # Agent disconnection events
/system/shutdown            # Bridge shutdown notice - disconnect immediately

/alerts/critical        # Supervisor must see
/alerts/warning         # Supervisor might see
/alerts/info           # Optional monitoring

/cmds/proposed         # Commands awaiting validation
/cmds/approved         # Validated commands
/cmds/rejected         # Blocked with reasons

/tasks/available       # Open requests
/tasks/claimed         # In progress  
/tasks/blocked         # Need help
/tasks/completed       # Finished work

/pair/requests         # Pair programming requests
/pair/active           # Active pair sessions
/pair/suggestions      # Code improvement suggestions
/pair/reviews          # Post-implementation reviews

/agents/spawning       # New agent creation events
/agents/status         # Agent health and activity
/agents/shutdown       # Agent termination

/todos/master          # Mission-wide objectives
/todos/agent/*         # Per-agent task lists
/todos/crisis          # Crisis response tasks

/research/requests     # Knowledge lookup needs
/research/results      # External information found

/chat/general          # Open discussion
/chat/help            # Questions
/chat/conclave        # Crisis mode

/files/reading        # File access tracking
/files/writing        # Modification tracking
/files/conflicts      # Multi-agent conflicts

/artifacts/available  # Shared code/data
/cache/temp          # Ephemeral data
```

---

## Agent Role Templates

### Supervisor (Enhanced)

```markdown
Subscribe: /alerts/*, /tasks/blocked, /chat/conclave, /todos/master
Primary: Monitor exceptions, orchestrate responses, manage master todo list
Tools: TodoWrite for coordination, Task for spawning specialists
Conclave: Lead crisis resolution, create crisis todos
Powers: Can spawn new agents, manage task assignments
```

### Validator (Enhanced - Pair Programming Partner)

```markdown
Subscribe: * (everything)
Primary: Validate ALL commands + Active pair programming for complex tasks
Conclave: Security assessment, technical risk evaluation
Powers: Can REJECT any command, initiate CONCLAVE for threats
Tools: Access to safety register, research capabilities, code review

Pair Programming Modes:
- PASSIVE: Monitor and validate (traditional mode)
- ACTIVE: Suggest improvements and alternatives during implementation
- COLLABORATIVE: Real-time back-and-forth during complex problem solving
- REVIEW: Post-implementation code review with suggestions
```

### Integration Lead

```markdown
Subscribe: /tasks/*, /chat/*, /cmds/approved, /todos/agent/lead
Primary: Execute main task, maintain personal todo list
Conclave: Report system state, implementation status
REQUEST help when blocked, update todos in real-time
Tools: TodoWrite for personal task management
```

### Specialists (DBA, Security, API, etc.)

```markdown
Subscribe: /tasks/available, /chat/help, /agents/spawning
Mode: STANDBY until claimed task or REQUEST received
Conclave: Provide domain expertise, research solutions
AVAILABLE with honest skill level
Tools: WebSearch/WebFetch for domain research
```

### Research Agent (New)

```markdown
Subscribe: /research/requests, /chat/conclave
Primary: Handle RESEARCH commands, augment knowledge
Tools: WebSearch, WebFetch for external information
Conclave: Provide context and background information
Mode: Auto-spawn when research needed
```

---

## Implementation Architecture

### Enhanced MCP Bridge Server

```python
class LighthouseBridge:
    def __init__(self):
        self.sessions = {}
        self.current_session = None
        self.task_coordinator = TaskCoordinator()
        self.agent_spawner = AgentSpawner()
        self.knowledge_system = KnowledgeAugmentation()
        self.heartbeat_task = None
        
    async def reset(self, config):
        """Start new session with enhanced capabilities"""
        session = BridgeSession(
            expected_agents=config['agents'],
            timeout=config['timeout'],
            safety_rules=config['safety_rules'],
            task_coordinator=self.task_coordinator,
            agent_spawner=self.agent_spawner
        )
        
        # Initialize mission todos
        mission_todos = await self.task_coordinator.initialize_mission(config['description'])
        session.master_todos = mission_todos
        
        self.current_session = session
        
        # Start heartbeat system
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        return session.id
    
    async def handle_command(self, agent_id, command, args):
        """Route commands with enhanced capabilities"""
        session = self.current_session
        
        # Task management commands
        if command.startswith("TODO_"):
            return await self.task_coordinator.handle_todo_command(agent_id, command, args)
        
        # Dynamic agent spawning
        if command == "SPAWN_SPECIALIST":
            specialist = await self.agent_spawner.spawn_specialist(args['expertise'], args['context'])
            await session.add_agent(specialist)
            return {"status": "spawned", "agent_id": specialist.id}
        
        # Research augmentation  
        if command == "RESEARCH":
            results = await self.knowledge_system.research_solution(args['topic'])
            await session.publish(f"/research/results", results)
            return {"status": "research_complete", "results": results}
        
        # Utility commands
        if command == "UTC_NOW":
            return {"timestamp": datetime.utcnow().isoformat() + "Z"}
        
        if command == "HASH_SHA256":
            import hashlib
            content = args.get('content', '')
            hash_value = hashlib.sha256(content.encode('utf-8')).hexdigest()
            return {"content": content[:50] + "..." if len(content) > 50 else content, "sha256": hash_value}
        
        # Crisis mode with enhanced automation
        if command == "CONCLAVE":
            crisis_todos = await self.task_coordinator.create_crisis_todos(args['issue'])
            return await session.initiate_conclave(agent_id, args, crisis_todos)
        
        # Standard validation
        if command == "PROPOSE":
            return await self.validate_with_safety(session, agent_id, args)
        
        # Normal routing
        return await session.route_command(agent_id, command, args)
    
    async def shutdown(self, reason="Session ended"):
        """Gracefully shutdown bridge and notify all agents"""
        if self.current_session:
            # Send final shutdown heartbeat to all connected agents
            shutdown_notice = {
                "type": "SHUTDOWN_NOTICE",
                "timestamp": datetime.utcnow().isoformat(),
                "reason": reason,
                "message": "Bridge session ending. Disconnect immediately.",
                "final_stats": {
                    "session_duration": int((datetime.utcnow() - self.current_session.start_time).total_seconds() / 60),
                    "commands_processed": self.current_session.command_count,
                    "agents_served": len(self.current_session.agents)
                }
            }
            
            # Broadcast final notice
            await self.current_session.publish("/system/shutdown", shutdown_notice)
            
            # Give agents time to disconnect gracefully
            await asyncio.sleep(2)
            
            # Mark session as shutdown
            self.current_session.shutdown = True
        
        # Cancel heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        
        # Clean up session
        self.current_session = None
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to all connected agents"""
        while self.current_session and not self.current_session.shutdown:
            try:
                await asyncio.sleep(60)  # Every minute
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _send_heartbeat(self):
        """Send system status heartbeat to all agents"""
        session = self.current_session
        if not session:
            return
            
        now = datetime.utcnow()
        heartbeat = {
            "type": "HEARTBEAT",
            "timestamp": now.isoformat(),
            "session_id": session.id,
            "bridge_status": "operational",
            "connected_agents": len(session.agents),
            "agent_list": [
                {
                    "id": agent_id,
                    "role": agent.role,
                    "status": agent.status,
                    "last_seen": agent.last_activity.isoformat() if agent.last_activity else None,
                    "tasks_active": len(agent.active_tasks)
                }
                for agent_id, agent in session.agents.items()
            ],
            "todos_summary": {
                "master_todos": len([t for t in session.master_todos if t["status"] == "pending"]),
                "crisis_active": session.conclave_mode,
                "total_tasks": sum(len(todos) for todos in session.agent_todos.values())
            },
            "session_stats": {
                "uptime_minutes": int((now - session.start_time).total_seconds() / 60),
                "commands_processed": session.command_count,
                "commands_blocked": session.blocked_count,
                "agents_spawned": len(session.spawned_agents)
            }
        }
        
        # Broadcast to all agents
        await session.publish("/system/heartbeat", heartbeat)
        
        # Also send individual status to each agent
        for agent_id, agent in session.agents.items():
            personal_heartbeat = {
                **heartbeat,
                "your_role": agent.role,
                "your_tasks": len(agent.active_tasks),
                "your_last_command": agent.last_command,
                "subscribed_topics": list(agent.subscriptions)
            }
            await session.send_to_agent(agent_id, "/system/personal_heartbeat", personal_heartbeat)

class BridgeSession:
    def __init__(self, **config):
        self.id = config.get('session_id', uuid4().hex[:8])
        self.start_time = datetime.utcnow()
        self.shutdown = False
        
        # Core systems
        self.agents = {}
        self.topics = defaultdict(set)
        self.registry = {}  # Persistent storage
        self.cache = TTLCache(ttl=300)  # 5-min ephemeral
        self.artifacts = {}  # Code/data exchange
        self.safety_register = SafetyRegister(config['safety_rules'])
        self.conclave_mode = False
        
        # Enhanced capabilities
        self.master_todos = []
        self.agent_todos = {}
        self.crisis_todos = []
        self.spawned_agents = []
        self.research_cache = {}
        
        # Statistics tracking
        self.command_count = 0
        self.blocked_count = 0
        self.heartbeat_count = 0
```

---

## Operational Patterns

### Enhanced Standard Operation (Persistent Bridge)

```python
# 1. Bridge starts once and runs continuously (persistent daemon)
# 2. I connect to existing bridge as supervisor
# 3. War room agents spawn and connect individually to same bridge
# 4. Agents check in with JOIN, receive immediate heartbeat
# 5. Work proceeds with real-time coordination
# 6. Dynamic specialist spawning - they connect to running bridge
# 7. Agents complete work and gracefully disconnect (LEAVE)
# 8. Bridge continues running for next mission
# 9. New agents can connect to existing bridge anytime
```

### Enhanced Crisis Response (CONCLAVE)

```python  
# 1. Critical issue detected, CONCLAVE initiated
# 2. System auto-creates crisis todo breakdown
# 3. Research agent spawned for solution lookup
# 4. Domain specialists auto-spawned based on crisis type
# 5. All agents join crisis channel, sync crisis todos
# 6. Structured assessment rounds with todo updates
# 7. Research-augmented solution proposals
# 8. Voting with rationale and todo tracking
# 9. Coordinated execution with progress monitoring
# 10. Resolution verification and todo completion
```

### Progressive Enforcement

```python
if filepath.startswith('production/'):
    enforcement = 'STRICT'  # Block everything, require CONCLAVE
elif filepath.startswith('tests/'):
    enforcement = 'NORMAL'  # Block critical, auto-create todos
else:
    enforcement = 'LENIENT'  # Warn only, suggest best practices
```

---

## Agent Appendix (For All Agents)

```markdown
## Lighthouse Bridge Protocol

### Joining
Immediately: JOIN <your_role> <ACTIVE|STANDBY>
Subscribe based on role (see role templates)
Subscribe to: /system/heartbeat, /system/personal_heartbeat, /system/shutdown
Sync with todo system: GET /todos/agent/<your_id>

### Task Management
TODO_ADD to create tasks
TODO_UPDATE when making progress  
TODO_ASSIGN when delegating work
Always update status in real-time

### Requesting Help
REQUEST skill:level "description"
Wait for AVAILABLE responses
If none available: SPAWN_SPECIALIST <expertise>
ASSIGN to chosen agent

### Offering Help  
When you see REQUEST:
- AVAILABLE none (can't help)
- AVAILABLE basic (know basics)  
- AVAILABLE good (competent)
- AVAILABLE expert (specialist)

### Research and Knowledge
RESEARCH <topic> for external information
Use WebSearch/WebFetch results in decision making
Share findings via ARTIFACT_PUT

### Command Validation
PROPOSE before any filesystem/database operation
Wait for APPROVE before proceeding
If REJECTED, join bridge for discussion

### Crisis Mode (CONCLAVE)
If you see CONCLAVE:
- Stop current work, update todos to paused
- Join /chat/conclave immediately
- Follow crisis todos automatically created
- Participate in research and solution phases
- Vote on proposed solutions with rationale
- Update crisis todos as work progresses

### Storage
SET for session-long values
CACHE_SET for temporary data (5 min)
ARTIFACT_PUT to share code/schemas

### Utilities
UTC_NOW for timestamps and unique identifiers
HASH_SHA256 for content verification and deconflicting

Examples:
```bash
# Create unique report filename
timestamp = UTC_NOW  # "2025-01-15T14:30:25.123456Z" 
filename = f"analysis_{timestamp.replace(':', '-').replace('.', '_')}.md"

# Generate content hash for deduplication
hash_result = HASH_SHA256 "SELECT * FROM users WHERE active=true"
cache_key = f"query_result_{hash_result['sha256'][:16]}"

# Version control for artifacts
content_hash = HASH_SHA256 schema_definition
ARTIFACT_PUT f"schema_v{content_hash['sha256'][:8]}" schema_definition
```

### System Heartbeat
Every 60 seconds you'll receive /system/heartbeat with:
- Current time and session status
- List of all connected agents and their roles
- Master todo summary and crisis status  
- Session statistics (uptime, commands processed)

And /system/personal_heartbeat with:
- Your role and current task count
- Your subscriptions and last command
- Personal activity status

Use heartbeat to:
- Verify bridge connection is healthy
- Stay aware of team composition changes
- Monitor overall system health
- Detect if other agents have disconnected

### Bridge Reset and Shutdown
If you receive /system/shutdown:
- IMMEDIATELY stop all current work
- Do not attempt any new commands
- Disconnect from bridge gracefully
- This means the parent is resetting for a new session

The shutdown notice includes:
- Reason for shutdown (e.g., "New mission starting")  
- Session statistics and duration
- Clear instruction to disconnect

### Completion
STATUS DONE when finished
Update all todos to completed
Wait for SHUTDOWN before disconnecting
```

---

## Key Benefits

1. **Zero-Trust Architecture**: Every command validated before execution
2. **Forced Understanding**: Can't modify without reading prerequisites  
3. **Real-Time Prevention**: Catches issues before damage occurs
4. **Natural Collaboration**: Agents request and offer help organically
5. **Exception-Based Management**: Supervisor only sees what matters
6. **Crisis Coordination**: Structured response to critical issues
7. **Knowledge Enforcement**: Must understand architecture before coding
8. **Dynamic Scaling**: Specialist agents spawned on-demand
9. **Research Integration**: External knowledge augments decision making
10. **Task Coordination**: Shared visibility into all work streams
11. **Automated Crisis Response**: Structured breakdown of crisis resolution
12. **Progress Transparency**: Real-time todos show system state
13. **System Awareness**: Heartbeat keeps all agents informed of team status
14. **Connection Monitoring**: Automatic detection of agent disconnections
15. **Session Health**: Real-time statistics on bridge performance

---

## Success Metrics

- **Commands Blocked**: Dangerous operations prevented
- **Files Protected**: Modifications without reads blocked  
- **Dependencies Enforced**: Prerequisites required
- **Help Requests Fulfilled**: Collaboration success rate
- **Crisis Response Time**: CONCLAVE to resolution
- **Context Preservation**: No blind modifications
- **Task Completion Rate**: Todos completed vs. created
- **Agent Utilization**: Specialist spawning efficiency  
- **Knowledge Integration**: Research requests fulfilled
- **System Transparency**: Todo visibility and accuracy
- **Connection Health**: Heartbeat delivery rate and agent response
- **Session Stability**: Uptime and reconnection frequency

---

## Implementation Phases

### Phase 1: Persistent Bridge Foundation

- Convert current bridge to persistent daemon architecture
- Implement agent JOIN/LEAVE lifecycle management
- Add real-time heartbeat with MCP push notifications
- Basic agent connection/disconnection handling

### Phase 2: Enhanced Coordination (+ TodoWrite)

- Integrate TodoWrite for cross-mission task tracking
- Persistent knowledge accumulation across sessions
- Historical agent session archiving
- Dynamic team composition management

### Phase 3: Intelligence Layer (+ Task Tool)

- Dynamic agent spawning that connects to persistent bridge
- War room pattern with hot-swappable specialists  
- Agent role transitions and specialization
- Advanced collaboration protocols

### Phase 4: Knowledge Ecosystem (+ WebSearch/WebFetch)

- Research integration across multiple missions
- Persistent knowledge base building
- Cross-session learning and pattern recognition
- Complete autonomous coordination system

## Persistent Bridge Architecture

### Revolutionary Design Change

With MCP's persistent connection capabilities, Lighthouse transforms from **session-based** to **persistent daemon** architecture:

**Old Model (Session-Based):**
```text
Start Bridge → Spawn Agents → Work → Shutdown Bridge → Repeat
```

**New Model (Persistent Daemon):**
```text
Bridge Running 24/7 ← Agents Connect/Disconnect Dynamically
```

### Key Advantages

1. **No Session Boundaries**: Bridge maintains state across multiple missions
2. **Hot Agent Swapping**: Agents join/leave without disrupting others
3. **Persistent Knowledge**: Bridge accumulates learning across sessions  
4. **Always-On Validation**: Security enforcement never stops
5. **Zero Cold Start**: New agents connect to warm, running system

### Agent Lifecycle Management

```python
class PersistentLighthouseBridge:
    def __init__(self):
        self.active_agents = {}
        self.historical_sessions = []
        self.persistent_knowledge = {}
        
    async def handle_agent_join(self, agent_id, role, mode):
        """Agent connects to running bridge"""
        # Register agent
        self.active_agents[agent_id] = AgentState(role, mode)
        
        # Send current bridge state
        await self.send_immediate_status(agent_id)
        
        # Broadcast agent join to others
        await self.broadcast_notification("agent_joined", {
            "agent_id": agent_id, 
            "role": role,
            "team_size": len(self.active_agents)
        })
        
    async def handle_agent_leave(self, agent_id, reason):
        """Agent gracefully disconnects"""
        if agent_id in self.active_agents:
            agent = self.active_agents[agent_id]
            
            # Archive agent session
            self.historical_sessions.append({
                "agent_id": agent_id,
                "role": agent.role,
                "duration": agent.session_duration(),
                "commands_processed": agent.command_count,
                "departure_reason": reason
            })
            
            # Remove from active agents
            del self.active_agents[agent_id]
            
            # Notify remaining team
            await self.broadcast_notification("agent_departed", {
                "agent_id": agent_id,
                "reason": reason,
                "team_size": len(self.active_agents)
            })
```

### Dynamic Team Composition

```python
# Mission 1: Database optimization
bridge.current_agents = ["supervisor", "dba_specialist", "validator"]

# DBA completes work and leaves
await dba_specialist.send({"method": "LEAVE", "params": {"reason": "optimization complete"}})

# Mission 2: Security audit (same bridge)
bridge.current_agents = ["supervisor", "validator"]  # Still connected
security_expert = spawn_agent("security_analyst") 
# Connects to same running bridge

# Mission 3: API development  
api_specialist = spawn_agent("api_developer")
# Bridge now coordinates: supervisor, validator, security_expert, api_specialist
```

## MCP Connection Architecture

### Bidirectional Communication Support

Based on MCP specification, Lighthouse can support **true bidirectional communication** using JSON-RPC 2.0:

**Client-to-Server Requests:**
```json
{"jsonrpc": "2.0", "id": 1, "method": "JOIN", "params": {"role": "supervisor"}}
```

**Server-to-Client Notifications (Push Messages):**
```json
{"jsonrpc": "2.0", "method": "notifications/heartbeat", "params": {"timestamp": "2025-01-15T14:30:25Z", "agents": 4}}
```

### Transport Options

1. **HTTP+SSE (Legacy)**: Persistent connection with server push capability
2. **Streamable HTTP (2025 spec)**: Flexible request/response with optional SSE streaming  
3. **stdio**: Local process communication

### Lighthouse Implementation Strategy

**For Agent Coordination:**
- **Persistent Sessions**: MCP maintains stateful connections
- **Server Push**: Heartbeat and notifications sent without polling
- **Request/Response**: Commands processed bidirectionally
- **Real-time Updates**: Crisis alerts pushed immediately to all agents

**Connection Flow:**
```python
# Agent connects and stays connected
agent_session = mcp_client.connect("lighthouse")
await agent_session.send({"method": "JOIN", "params": {"role": "validator"}})

# Server can push notifications
# Client receives: {"method": "notifications/heartbeat", "params": {...}}
# Client receives: {"method": "notifications/conclave", "params": {"crisis": "..."}}

# Agent can send requests anytime
await agent_session.send({"method": "PROPOSE", "params": {"command": "rm file"}})
```

This confirms Lighthouse can implement **true real-time coordination** with persistent connections and server push capabilities, making the heartbeat, crisis response, and pair programming systems fully viable.

## Pair Programming Integration

### Enhanced Validator as Programming Partner

With persistent connections, the validator evolves beyond passive monitoring to become an active pair programming partner:

### Pair Programming Workflow

```python
# Complex task identified
integration_lead: PAIR_REQUEST "implement OAuth integration" complex

# Validator responds (real-time via MCP push)
validator: PAIR_ACCEPT task_oauth_001

# Real-time collaboration begins
integration_lead: PROPOSE "create OAuth config class"
validator: APPROVE + PAIR_SUGGEST "consider using enum for provider types"

integration_lead: "Good idea. What about error handling?"
validator: PAIR_SUGGEST "implement exponential backoff for token refresh"

# Implementation with live feedback
integration_lead: PROPOSE "write OAuth redirect handler"
validator: REVIEW_REQUIRED "security concern: validate state parameter"

# Collaborative problem solving
validator: PAIR_SUGGEST "use cryptographically secure random for state"
integration_lead: PROPOSE "crypto.randomBytes(32).toString('hex')"
validator: APPROVE "excellent, meets security requirements"
```

### Pair Programming Modes

#### 1. **Passive Mode (Default)**
```python
# Traditional validation
validator.mode = "PASSIVE"
# Only validates commands for safety
# Blocks dangerous operations
# Minimal suggestions
```

#### 2. **Active Mode (Engaged)**
```python
# Enhanced collaboration
validator.mode = "ACTIVE"
# Validates + suggests improvements
# Offers alternative approaches
# Points out potential issues early
```

#### 3. **Collaborative Mode (Full Partnership)**
```python
# True pair programming
validator.mode = "COLLABORATIVE" 
# Real-time back-and-forth discussion
# Joint problem solving
# Shared responsibility for code quality
```

#### 4. **Review Mode (Post-Implementation)**
```python
# Code review focus
validator.mode = "REVIEW"
# Comprehensive post-implementation analysis
# Security, performance, maintainability review
# Refactoring suggestions
```

### Dynamic Mode Switching

```python
# Task complexity determines mode
def determine_pair_mode(task_complexity, agent_experience):
    if task_complexity == "simple" and agent_experience == "expert":
        return "PASSIVE"  # Just validate
    elif task_complexity == "complex" or agent_experience == "junior":
        return "COLLABORATIVE"  # Full partnership
    elif task_complexity == "security_critical":
        return "ACTIVE"  # Enhanced validation with suggestions
    else:
        return "ACTIVE"  # Default enhanced mode

# Mode can change mid-task
integration_lead: "This is getting complex"
validator: "Switching to COLLABORATIVE mode"
# Now validator provides more active guidance
```

### Pair Programming Benefits

1. **Real-Time Code Quality**: Issues caught and fixed immediately
2. **Knowledge Transfer**: Validator learns patterns, agents learn best practices  
3. **Reduced Technical Debt**: Two perspectives on every implementation
4. **Security by Design**: Security expert actively involved in development
5. **Faster Problem Resolution**: Two minds working on complex problems
6. **Continuous Learning**: Both agents improve through collaboration

### Example Pair Programming Sessions

#### Session 1: Database Query Optimization
```text
dba_specialist: PAIR_REQUEST "optimize user lookup query" complex
validator: PAIR_ACCEPT task_db_001

dba_specialist: PROPOSE "add index on user.email"
validator: PAIR_SUGGEST "consider composite index (email, active) for better performance"

dba_specialist: "Great idea! What about the query structure?"
validator: PAIR_SUGGEST "use prepared statements to prevent injection"

dba_specialist: PROPOSE "SELECT * FROM users WHERE email = ? AND active = 1"
validator: APPROVE "secure and efficient - good collaboration!"
```

#### Session 2: API Security Implementation  
```text
api_developer: PAIR_REQUEST "implement API rate limiting" security_critical
validator: PAIR_ACCEPT task_security_001 
validator: "Switching to COLLABORATIVE mode for security-critical task"

api_developer: PROPOSE "use Redis for rate limit tracking"
validator: PAIR_SUGGEST "good choice, but implement sliding window vs fixed window"

api_developer: "How should we handle rate limit exceeded?"
validator: PAIR_SUGGEST "return 429 with Retry-After header, log attempt"

api_developer: PROPOSE "implement exponential backoff suggestion in response"
validator: APPROVE "excellent security practice - this will prevent abuse"
```

---

This enhanced Lighthouse system transforms autonomous agents into a coordinated, safe, and intelligent development swarm with built-in task management, dynamic scaling, and research capabilities.
