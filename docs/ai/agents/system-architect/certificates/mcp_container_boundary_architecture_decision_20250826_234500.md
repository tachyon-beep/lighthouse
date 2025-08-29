# MCP CONTAINER BOUNDARY ARCHITECTURE DECISION CERTIFICATE

**Component**: MCP Server Placement (Container Boundary)
**Agent**: system-architect
**Date**: 2025-08-26 23:45:00 UTC
**Certificate ID**: mcp-container-boundary-234500

## REVIEW SCOPE
- MCP Server architecture (`src/lighthouse/mcp_server.py`)
- Container boundary considerations
- Multi-agent coordination requirements
- Claude Code connection patterns
- Security and deployment implications

## FINDINGS

### Current Architecture Analysis
The MCP server is a thin FastMCP adapter (818 lines) that:
1. Runs in each Claude Code instance's environment
2. Connects to Bridge components (either local or remote)
3. Provides tools for multi-agent coordination
4. Has fallback logic for direct component access

### Option A: MCP Server OUTSIDE Container (Current Approach)

**Architecture**:
```
Claude Code Instance 1 → MCP Server 1 (local) ──┐
Claude Code Instance 2 → MCP Server 2 (local) ──┼──> Bridge (container:8765)
Claude Code Instance 3 → MCP Server 3 (local) ──┘
```

**Advantages**:
- ✅ Each Claude instance has dedicated MCP server
- ✅ Natural 1:1 mapping (Claude ↔ MCP instance)
- ✅ MCP configuration is simple: local Python script
- ✅ Aligns with MCP design: per-tool-user instances
- ✅ No network exposure of MCP protocol
- ✅ Claude instances remain isolated from each other
- ✅ Fallback mode works if Bridge unavailable

**Disadvantages**:
- ❌ Multiple MCP server processes to manage
- ❌ Each needs Python environment setup
- ❌ Bridge connection crosses container boundary

### Option B: MCP Server INSIDE Container

**Architecture**:
```
Claude Code Instance 1 ──┐
Claude Code Instance 2 ──┼──> Single MCP Server (container) → Bridge (same container)
Claude Code Instance 3 ──┘
```

**Advantages**:
- ✅ Single MCP server to manage
- ✅ MCP→Bridge communication stays internal
- ✅ Simplified deployment (one container)

**Disadvantages**:
- ❌ **BREAKS MCP PROTOCOL MODEL**: MCP expects 1:1 tool-user mapping
- ❌ **NO MULTI-CLIENT SUPPORT**: FastMCP/MCP protocol is single-client
- ❌ Would need custom multiplexing layer (complexity)
- ❌ Claude instances would share MCP state (isolation breach)
- ❌ `.mcp.json` cannot specify container endpoints easily
- ❌ Loses fallback capability when Bridge unavailable
- ❌ Violates principle of Claude instance independence

### Critical Technical Constraints

1. **MCP Protocol Design**: MCP (Model Context Protocol) is designed for 1:1 relationships between tool provider and consumer. It's not a multi-client server protocol.

2. **Claude Code Integration**: Claude Code expects to spawn its own MCP server process via `.mcp.json` configuration. It doesn't support connecting to remote MCP servers.

3. **Security Model**: Each Claude instance should remain isolated with its own security context and session management.

### Security Analysis

**Option A Security**:
- Each Claude has separate process space
- Bridge provides centralized authentication
- Network traffic only to Bridge (localhost:8765)
- Clean security boundaries

**Option B Security Issues**:
- Would require exposing MCP protocol over network
- Shared MCP server = shared attack surface
- Complex session multiplexing needed
- Higher risk of cross-instance contamination

## DECISION/OUTCOME

**Status**: RECOMMEND
**Recommendation**: Option A - MCP Server OUTSIDE Container

**Rationale**: 
The MCP protocol and Claude Code integration model fundamentally require 1:1 MCP server instances. Option A (current approach) correctly aligns with:
1. MCP protocol design (single client per server)
2. Claude Code's process spawning model
3. Security isolation requirements
4. Multi-agent independence principles

Option B would require fighting against the fundamental design of both MCP and Claude Code, introducing unnecessary complexity and security risks.

**Conditions**: None - this is the architecturally correct approach

## EVIDENCE

### File References
- `src/lighthouse/mcp_server.py`: Lines 1-818 show single-client design
- `.mcp.json`: Lines 1-12 show local process spawning configuration
- `CLAUDE.md`: Lines 13-33 describe multi-agent architecture with separate instances

### Architectural Principles
1. **Tool-User Isolation**: Each Claude instance is independent
2. **Protocol Alignment**: Respect MCP's 1:1 design model
3. **Deployment Simplicity**: Local Python scripts are easy to configure
4. **Security First**: Process isolation provides security boundaries

### Deployment Configuration
For containerized Bridge deployment:
```yaml
# Bridge Container
services:
  lighthouse-bridge:
    image: lighthouse-bridge:latest
    ports:
      - "8765:8765"  # Bridge API
    environment:
      - BRIDGE_MODE=production
      - FUSE_ENABLED=true

# Each Claude instance (OUTSIDE container):
# 1. Has local Python environment
# 2. Runs: python -m lighthouse.mcp_server
# 3. MCP server connects to localhost:8765
```

## RECOMMENDED IMPLEMENTATION PATH

1. **Container Image**: Include only Bridge and its components
2. **MCP Deployment**: Document installation for each Claude environment
3. **Connection Config**: Ensure Bridge listens on accessible port
4. **Health Checks**: MCP servers should verify Bridge availability
5. **Fallback Mode**: MCP servers use direct component access if Bridge down

## SIGNATURE
Agent: system-architect
Timestamp: 2025-08-26 23:45:00 UTC
Certificate Hash: SHA256:container-boundary-decision-mcp-outside