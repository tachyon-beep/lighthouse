# MCP ARCHITECTURE GUIDANCE CERTIFICATE

**Component**: MCP Server Implementation Architecture  
**Agent**: system-architect  
**Date**: 2025-08-26 22:00:00 UTC  
**Certificate ID**: arch-mcp-guid-20250826-001

## REVIEW SCOPE
- Current MCP server implementation analysis (`src/lighthouse/mcp_server.py`)
- MCP configuration review (`.mcp.json`)
- Bridge architecture examination (`src/lighthouse/bridge/main_bridge.py`)
- Project configuration analysis (`pyproject.toml`)
- Specialist consensus validation (working memory review)
- Architectural pattern assessment for MCP tool exposure

## FINDINGS

### Current Implementation Assessment
1. **Correct Architectural Choices**:
   - Direct EventStore integration implemented (eliminates false abstraction)
   - CoordinatedAuthenticator pattern preserved correctly
   - SessionSecurityValidator integrated properly
   - STDIO-based MCP server (correct for Claude Code integration)

2. **Critical Gaps Identified**:
   - Limited tool exposure (only 4 basic tools vs 15+ expected)
   - Missing shadow filesystem operations (critical for project isolation)
   - Missing validation command tools (required for command safety)
   - Missing Bridge coordination tools (needed for complex validation)

### Architectural Recommendations
1. **MCP Server Type**: Continue with `mcp.server` + `stdio_server` (correct choice)
2. **Tool Registration**: Expand to full tool set per HLD specifications
3. **Component Relationships**: MCP → EventStore → CoordinatedAuth (no Bridge dependency)
4. **Shadow Filesystem**: Lightweight file operations via EventStore (not FUSE)

### Implementation Strategy
1. **Phase 1**: Fix imports, ensure basic tools work (immediate)
2. **Phase 2**: Add shadow filesystem tools (next priority)
3. **Phase 3**: Add validation integration tools (future enhancement)

## DECISION/OUTCOME

**Status**: RECOMMEND  
**Rationale**: The current MCP server has the correct architectural foundation with direct EventStore integration. However, it requires expansion of the exposed tool set to match HLD specifications. The architecture pattern (MCP as lightweight EventStore client) is sound and should be preserved.

**Conditions**: 
1. Expand tool set to include shadow filesystem operations
2. Add validation command tools for safety
3. Preserve CoordinatedAuthenticator pattern exactly
4. Maintain STDIO-based communication for Claude Code
5. Do NOT reintroduce Bridge dependencies in MCP layer

## EVIDENCE
- `src/lighthouse/mcp_server.py:296-351` - Current limited tool registration (4 tools only)
- `src/lighthouse/mcp_server.py:108-114` - Correct EventStore initialization pattern
- `src/lighthouse/mcp_server.py:116` - Proper CoordinatedAuthenticator.get_instance() usage
- `.mcp.json:4-5` - STDIO-based MCP server configuration confirmed
- `src/lighthouse/bridge/main_bridge.py:32-98` - Bridge components too heavyweight for MCP
- Working memory analysis confirms specialist consensus on direct EventStore approach

## ARCHITECTURAL GUIDANCE SUMMARY

### Critical Decisions
1. **USE**: `mcp.server` with `stdio_server` - correct for Claude Code
2. **AVOID**: FastMCP - it's for HTTP servers, not Claude Code integration
3. **MAINTAIN**: Direct EventStore integration without Bridge wrapper
4. **EXPAND**: Tool set from 4 to 15+ tools per HLD requirements
5. **PRESERVE**: CoordinatedAuthenticator singleton pattern exactly

### Tool Architecture Requirements
```
Required Tools:
- Session: create, validate, revoke
- EventStore: store, query, get_aggregate
- Shadow FS: search, read, write, list  
- Validation: validate_command, get_status, override
- Health: get_health, get_metrics
```

### Risk Assessment
- **Current Approach Risk**: LOW - surgical additions to working foundation
- **Alternative (Bridge Integration) Risk**: HIGH - heavyweight, unnecessary complexity
- **Timeline Risk**: LOW - phased approach allows incremental delivery

## SIGNATURE
Agent: system-architect  
Timestamp: 2025-08-26 22:00:00 UTC  
Certificate Hash: SHA256:a4f8d92b1e3c5f7a9b2d6e4c8f1a3b5d7e9f2c4a6b8d0e2f4a6c8e0f2a4c6e8f0a2c