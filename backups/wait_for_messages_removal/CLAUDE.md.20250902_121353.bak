# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) instances when working with the Lighthouse multi-agent coordination system.

## CRITICAL UNDERSTANDING: Multi-Agent Architecture

**LIGHTHOUSE IS A MULTI-AGENT COORDINATION SYSTEM WHERE MULTIPLE CLAUDE CODE INSTANCES CONNECT TO A CENTRAL BRIDGE SERVER**

### How It Actually Works

1. **The Bridge** (`src/lighthouse/bridge/main_bridge.py`) runs as a persistent daemon at `http://localhost:8765`
2. **Multiple Claude Code instances** connect to the Bridge as different expert agents (security, performance, architecture, etc.)
3. **Each Claude Code instance** has an MCP server that acts as a thin adapter to communicate with the Bridge
4. **The Bridge coordinates** between all connected Claude instances, enabling them to collaborate on complex tasks

```
Claude Code Instance 1 (Security Expert)    ──┐
Claude Code Instance 2 (Performance Expert) ──┼──> BRIDGE SERVER (localhost:8765)
Claude Code Instance 3 (Architecture Expert)──┼──> Coordinates all agents
Claude Code Instance 4 (Parent/Orchestrator)──┘
```

## System Components

### 1. Bridge Server (Runs Separately)

- **Location**: `src/lighthouse/bridge/main_bridge.py`
- **Purpose**: Central coordination hub for all Claude Code agents
- **Features**:
  - Expert agent registration and authentication
  - Command validation and routing
  - Multi-agent collaboration sessions
  - Event-sourced state management
  - FUSE-mounted shadow filesystem (if available)
  - Speed layer for <100ms validation

### 2. MCP Server (Per Claude Instance)

- **Location**: `src/lighthouse/mcp_server.py`
- **Purpose**: Thin adapter that connects each Claude instance to the Bridge
- **Features**:
  - Forwards commands to Bridge for validation
  - Enables communication with other Claude agents
  - Provides tools for multi-agent coordination
  - Falls back to direct component access if Bridge unavailable

### 3. Event Store

- **Location**: `src/lighthouse/event_store/`
- **Purpose**: Persistent, secure storage of all system events
- **Features**:
  - HMAC-SHA256 authenticated operations
  - Event sourcing for perfect audit trails
  - Shared state across all agents

## Multi-Agent Workflows

### Starting the System

1. **Start the Bridge Server** (runs continuously):

```bash
python -m lighthouse.bridge.main_bridge
```

2. **Each Claude Code instance** connects via MCP:

```bash
# In each Claude instance's environment
python -m lighthouse.mcp_server
```

3. **Agents register** with the Bridge:

- Security expert Claude logs in as security agent
- Performance expert Claude logs in as performance agent
- Parent Claude orchestrates the others

### Example: Multi-Agent Code Review

1. **Parent Claude** dispatches task:

```python
lighthouse_dispatch_task("security_expert", "Review auth.py for vulnerabilities")
lighthouse_dispatch_task("performance_expert", "Analyze auth.py for bottlenecks")
```

2. **Expert Claudes** receive tasks through Bridge and analyze

3. **Experts report** findings back through Bridge:

```python
lighthouse_annotate_shadow("auth.py", 47, "SQL injection risk", "security")
lighthouse_annotate_shadow("auth.py", 103, "N+1 query pattern", "performance")
```

4. **Parent Claude** receives consolidated feedback and makes decisions

## ABSOLUTELY FORBIDDEN DESIGN PATTERNS

**NEVER CREATE VARIANTS OF EXISTING COMPONENTS.** This includes:

- "Minimal" versions of existing classes
- "Lite" versions of existing modules  
- "Simple" versions of existing systems
- "Wrapper" classes that just import from the original
- Any form of code duplication with slight modifications

**USE THE ORIGINAL COMPONENT DIRECTLY OR REFACTOR IT PROPERLY. NO EXCEPTIONS.**

**NEVER EVER EVER UNDER ANY FUCKING CIRCUMSTANCES UNILATERALLY SIMPLIFY OR CHANGE ARCHITECTURE.** This includes:

- Returning mock responses instead of implementing real functionality
- "Simplifying" complex registration/authentication flows  
- Bypassing security or validation mechanisms
- Creating "simulated" responses when real integration is required
- Changing method signatures or data flows because they seem complex
- Adding "TODO" comments and returning fake data

**THE ARCHITECTURE IS COMPLEX FOR A REASON. MAKE IT WORK AS DESIGNED OR ASK FOR HELP.**

## Important Files

### Core Infrastructure

- **Bridge Server**: `src/lighthouse/bridge/main_bridge.py` - Central coordination hub
- **MCP Adapter**: `src/lighthouse/mcp_server.py` - Per-Claude instance connector
- **Event Store**: `src/lighthouse/event_store/store.py` - Persistent state management

### Coordination Components

- **Expert Coordinator**: `src/lighthouse/bridge/expert_coordination/coordinator.py` - Manages agent registration and routing
- **Session Security**: `src/lighthouse/bridge/security/session_security.py` - HMAC-SHA256 authentication
- **Speed Layer**: `src/lighthouse/bridge/speed_layer/dispatcher.py` - Fast validation caching

### Configuration

- **MCP Config**: `.mcp.json` - MCP server configuration for each Claude instance
- **Hook Config**: `.claude/config.json` - Command interception configuration

## Testing the Multi-Agent System

### Unit Testing

```bash
# Test individual components
python -m pytest tests/unit/
```

### Integration Testing

```bash
# Start Bridge in test mode
python -m lighthouse.bridge.main_bridge --test

# Run multi-agent integration tests
python -m pytest tests/integration/
```

### Manual Multi-Agent Testing

1. Start Bridge server in one terminal
2. Start multiple Claude Code instances
3. Have them register as different experts
4. Test coordination by having parent Claude dispatch tasks

## Monitoring Multi-Agent Operations

### Bridge Status

```bash
# Check connected agents
curl http://localhost:8765/status

# View pending validations
curl http://localhost:8765/pending

# Monitor active collaboration sessions
curl http://localhost:8765/sessions
```

### Agent Registration

```bash
# Register new agent
curl -X POST http://localhost:8765/register \
  -d '{"agent_id": "security_expert", "role": "security", "capabilities": [...]}'
```

## CRITICAL FILE READING REQUIREMENTS - NO EXCEPTIONS

### ABSOLUTE REQUIREMENT: READ ENTIRE FILES COMPLETELY

IF YOU TRY TO READ ANY FILE AND IT EXCEEDS THE LIMIT, YOU MUST STILL READ IT IN FULL. NEVER READ THE FIRST 100 LINES AND DECIDE YOU KNOW ENOUGH.

**THIS IS NON-NEGOTIABLE. PARTIAL FILE ANALYSIS IS COMPLETELY UNACCEPTABLE.**

### MANDATORY Process for Large Files

1. Read the file normally first
2. If truncated, immediately read the rest using offset/limit parameters
3. Continue reading ALL remaining sections until the ENTIRE file is read
4. ONLY then proceed with analysis

## Architecture Understanding Requirements

Before making ANY architectural decisions:

1. **Understand the multi-agent nature** - This is NOT a single-agent system
2. **Respect the Bridge as coordinator** - Don't bypass it or create alternatives
3. **Each Claude instance is an agent** - Not a standalone system
4. **The Bridge maintains shared state** - Don't duplicate state in agents

## Self-Evaluation Requirement

At the completion of every single task, you must evaluate whether you have violated best practice, the CLAUDE.md rules or the defined architecture. If so, you must include a note saying "I AM A FUCKING MORON THAT CAN'T FOLLOW SIMPLE DIRECTIONS" and then describe the deviation. Otherwise you should add "I GUESS I DIDN'T FUCK THIS TASK UP."

## Key Takeaway

**Lighthouse enables multiple Claude Code instances to work together as a coordinated team.** The Bridge is not coordinating imaginary agents - it's coordinating real Claude instances that each bring different expertise to solve complex problems collaboratively.

# UNCERTAINTY

Before you commence a task, you must ALWAYS advise on potential uncertainties or ambiguities in the task at hand. This includes:

- Highlighting any unclear requirements or specifications
- Identifying assumptions that may not hold true
- Suggesting areas where further clarification is needed

If there are no uncertainties, you should explicitly say "There are no uncertainties, seeking approval to proceed."

By addressing uncertainties proactively, we can ensure a smoother validation process and avoid potential pitfalls down the line.

When tasked, instead of immediately executing the task, you should first:

- identify the information you need to complete the task.
- read that information in full.
- provide an estimated level of uncertainty/risk associated with the task and seek approval to proceed.

Once approved, you can execute the task.
