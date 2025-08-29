# MCP TOOLS ARCHITECTURE ASSESSMENT CERTIFICATE

**Component**: MCP Server Tool Interface
**Agent**: system-architect
**Date**: 2025-08-27 12:00:00 UTC
**Certificate ID**: mcp-tools-arch-20250827-120000

## REVIEW SCOPE
- HLD architecture analysis (docs/architecture/HLD.md)
- Current MCP server implementation (src/lighthouse/mcp_server.py)
- Bridge HTTP server API (src/lighthouse/bridge/http_server.py)
- Multi-agent coordination requirements
- Container boundary architecture

## FINDINGS

### 1. Architectural Context
The Lighthouse system implements a clear architectural separation:
- **MCP Server**: Runs on HOST, provides tools to Claude Code instances
- **Bridge Server**: Runs in CONTAINER, coordinates all agents via HTTP API
- **Communication**: HTTP/WebSocket protocol between MCP (host) and Bridge (container)

### 2. Essential MCP Tools Analysis

Based on the HLD and multi-agent coordination patterns, the following tools are ESSENTIAL:

#### Core Coordination Tools (Must Have)
1. **lighthouse_get_bridge_status** ✅ (Already implemented)
   - Essential for health monitoring and system awareness
   - Maps to: GET /status

2. **lighthouse_validate_command** ✅ (Already implemented)
   - Core speed layer validation functionality
   - Maps to: POST /validate

3. **lighthouse_create_session** ✅ (Already implemented)
   - Required for authenticated agent coordination
   - Maps to: POST /session/create

4. **lighthouse_validate_session** ✅ (Already implemented)
   - Session management and security
   - Maps to: POST /session/validate

5. **lighthouse_register_expert** ✅ (Already implemented)
   - Expert agent registration for multi-agent coordination
   - Maps to: POST /expert/register

6. **lighthouse_delegate_to_expert** ✅ (Already implemented)
   - Command delegation for expert validation
   - Maps to: POST /expert/delegate

#### Missing Essential Tools
7. **lighthouse_store_event** ❌ (Missing but ESSENTIAL)
   - Required for event sourcing architecture
   - Needs Bridge endpoint: POST /event/store

8. **lighthouse_query_events** ❌ (Missing but ESSENTIAL)
   - Event history and audit trail access
   - Needs Bridge endpoint: GET /event/query

9. **lighthouse_dispatch_task** ❌ (Missing but ESSENTIAL)
   - Multi-agent task coordination
   - Needs Bridge endpoint: POST /task/dispatch

10. **lighthouse_start_collaboration** ❌ (Missing but ESSENTIAL)
    - Pair programming sessions per HLD
    - Needs Bridge endpoint: POST /collaboration/start

### 3. Non-Essential Tools Analysis

The following tools from the original set are NOT essential for the core architecture:

1. **lighthouse_broadcast_message** - Can be handled via WebSocket
2. **lighthouse_discover_experts** - Can be part of status endpoint
3. **lighthouse_request_expert_analysis** - Redundant with delegate_to_expert
4. **lighthouse_read_shadow** - Experts use FUSE mount, not MCP
5. **lighthouse_annotate_shadow** - Experts use FUSE mount, not MCP

### 4. Architectural Correctness Assessment

The current reduced set (7 tools) is INSUFFICIENT. The architecturally correct set requires:
- **10 essential tools** (6 existing + 4 missing)
- **Clear HTTP endpoint mapping** for each tool
- **Event sourcing capabilities** for audit trails
- **Task coordination** for multi-agent workflows

## DECISION/OUTCOME

**Status**: CONDITIONALLY_APPROVED
**Rationale**: The current implementation has the right architecture (MCP→HTTP→Bridge) but is missing critical tools for event sourcing and multi-agent coordination.

**Conditions**: 
1. Add the 4 missing essential MCP tools
2. Implement corresponding HTTP endpoints in Bridge
3. Maintain clear separation: MCP tools are thin HTTP clients
4. Do NOT add shadow filesystem operations (use FUSE mount instead)

## EVIDENCE

### File References
- `/home/john/lighthouse/docs/architecture/HLD.md:1150-1195` - Bridge API specification
- `/home/john/lighthouse/src/lighthouse/mcp_server.py:74-261` - Current tool implementations
- `/home/john/lighthouse/src/lighthouse/bridge/http_server.py:159-250` - HTTP endpoint mappings

### Architectural Patterns
- **Event Sourcing** (HLD:137-140) - Requires event store/query tools
- **Multi-Agent Coordination** (HLD:84-90) - Requires task dispatch tools
- **Pair Programming** (HLD:775-874) - Requires collaboration tools
- **FUSE Mount** (HLD:256-293) - Shadow operations via FUSE, not MCP

## RECOMMENDATIONS

### Immediate Actions
1. **Add Missing Tools to MCP Server**:
   ```python
   @mcp.tool()
   async def lighthouse_store_event(event_type, event_data, agent_id)
   @mcp.tool()
   async def lighthouse_query_events(filters, limit=100)
   @mcp.tool()
   async def lighthouse_dispatch_task(task_type, task_data, target_agent)
   @mcp.tool()
   async def lighthouse_start_collaboration(mode, participants, context)
   ```

2. **Add Corresponding Bridge HTTP Endpoints**:
   ```python
   @app.post("/event/store")
   @app.get("/event/query")
   @app.post("/task/dispatch")
   @app.post("/collaboration/start")
   ```

3. **Remove Shadow Operations from MCP**:
   - Shadow filesystem access happens via FUSE mount
   - Experts read/write directly to /mnt/lighthouse/project
   - No MCP tools needed for shadow operations

### Architecture Validation
The correct tool set enables:
- ✅ Speed layer validation (sub-100ms for safe operations)
- ✅ Expert escalation for risky operations
- ✅ Event sourcing for perfect audit trails
- ✅ Multi-agent task coordination
- ✅ Pair programming collaboration
- ✅ Clean separation of concerns (MCP as thin HTTP client)

## SIGNATURE
Agent: system-architect
Timestamp: 2025-08-27 12:00:00 UTC
Certificate Hash: mcp-tools-arch-assessment-final