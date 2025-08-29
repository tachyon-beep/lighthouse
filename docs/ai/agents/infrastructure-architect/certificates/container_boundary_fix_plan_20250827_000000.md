# CONTAINER BOUNDARY FIX PLAN CERTIFICATE

**Component**: Container Architecture Remediation
**Agent**: infrastructure-architect
**Date**: 2025-08-27 00:00:00 UTC
**Certificate ID**: container-boundary-fix-20250827

## REVIEW SCOPE
- Reviewed incorrect container configuration violating HLD architecture
- Analyzed System Architect's decision (mcp_container_boundary_architecture_decision_20250826_234500.md)
- Examined current incorrect implementation files
- Determined precise remediation steps

## FINDINGS

### Architecture Violation Summary
**What was built (WRONG):**
- Container configured to run MCP server (`python -m lighthouse.mcp_server`)
- MCP dependencies included in container (`mcp>=1.0.0` in requirements)
- Container intended to host MCP servers (violates 1:1 Claude-MCP model)

**What should be built (CORRECT per HLD):**
- Container runs Bridge server (`python -m lighthouse.bridge.main_bridge`)
- Container includes only Bridge dependencies (no MCP)
- MCP servers run on HOST, connect to Bridge at localhost:8765

### Root Cause Analysis
The fundamental misunderstanding was treating the container as hosting MCP servers, when it should exclusively host the Bridge server with FUSE mount capabilities.

## DETAILED TECHNICAL FIX PLAN

### 1. Dockerfile.pyfuse3 Changes

**CURRENT (Line 108):**
```bash
exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server
```

**CHANGE TO:**
```bash
exec "$CONTAINER_PYTHON" -m lighthouse.bridge.main_bridge
```

**Rationale**: The container must run the Bridge server, not MCP server.

### 2. requirements-pyfuse3.txt Changes

**REMOVE (Lines 33-34):**
```
# MCP support (FastMCP is included in mcp package)
mcp>=1.0.0
```

**Rationale**: MCP is a HOST-side dependency only. The Bridge doesn't need MCP libraries.

### 3. scripts/docker/start-bridge-pyfuse3.sh Changes

**Line 106-108 CURRENT:**
```bash
# For now, start the MCP server which will use the new FUSE backend
# In production, this would start the actual Bridge with pyfuse3
exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server
```

**CHANGE TO:**
```bash
# Start the Bridge server with pyfuse3 backend
exec "$CONTAINER_PYTHON" -m lighthouse.bridge.main_bridge
```

**Additionally, may need to add Bridge-specific startup parameters:**
```bash
# Start the Bridge server with configuration
exec "$CONTAINER_PYTHON" -m lighthouse.bridge.main_bridge \
    --project-id "${LIGHTHOUSE_PROJECT_ID:-default}" \
    --mount-point "${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}" \
    --port "${LIGHTHOUSE_PORT:-8765}" \
    --host "${LIGHTHOUSE_HOST:-0.0.0.0}" \
    --log-level "${LIGHTHOUSE_LOG_LEVEL:-INFO}"
```

### 4. Bridge Dependencies Analysis

**KEEP these dependencies (Bridge needs them):**
- `pyfuse3==3.4.0` - FUSE mount implementation
- `trio==0.26.0` - Async support for pyfuse3
- `fastapi>=0.115.12` - Bridge API server
- `uvicorn[standard]>=0.30.1` - ASGI server for Bridge API
- `aiofiles`, `aiohttp`, `aiosqlite` - Async I/O for Bridge
- `cryptography==42.0.8` - Security/HMAC operations
- `tree-sitter` packages - AST anchoring
- Database drivers - Event store persistence
- Monitoring packages - Observability

**REMOVE these dependencies (MCP-only):**
- `mcp>=1.0.0` - This is for Claude instances only

**ADD these dependencies (Bridge might need):**
- Consider if Bridge needs additional policy engine deps (OPA client?)
- Consider if Bridge needs specific FUSE security libraries

### 5. Container Runtime Requirements

The container needs special privileges for FUSE:
```bash
docker run \
    --cap-add SYS_ADMIN \
    --device /dev/fuse \
    -p 8765:8765 \
    lighthouse-bridge:pyfuse3
```

### 6. Verification Steps Post-Fix

1. **Build verification:**
   ```bash
   docker build -f Dockerfile.pyfuse3 -t lighthouse-bridge:test .
   ```

2. **Dependency verification:**
   ```bash
   docker run --rm lighthouse-bridge:test pip list | grep -i mcp
   # Should return nothing
   ```

3. **Bridge startup verification:**
   ```bash
   docker run --rm lighthouse-bridge:test python -c "from lighthouse.bridge import main_bridge; print('Bridge module OK')"
   ```

4. **Runtime verification:**
   ```bash
   docker run --cap-add SYS_ADMIN --device /dev/fuse -p 8765:8765 lighthouse-bridge:test
   # Should start Bridge server on port 8765
   ```

### 7. Host-Side MCP Configuration

After fixing the container, MCP servers run on host:
```bash
# On each Claude Code instance host
pip install mcp>=1.0.0  # Install MCP locally
python -m lighthouse.mcp_server  # Start MCP server
# MCP connects to Bridge at localhost:8765
```

## ARCHITECTURE ALIGNMENT

### Correct Component Boundaries
```
┌─────────────────────────┐         ┌──────────────────────┐
│   HOST ENVIRONMENT      │         │  DOCKER CONTAINER    │
│                         │         │                      │
│  Claude Code Instance 1 │         │                      │
│  └── MCP Server 1 ──────┼────────>│                      │
│                         │   8765  │   BRIDGE SERVER     │
│  Claude Code Instance 2 │         │   ├── Event Store   │
│  └── MCP Server 2 ──────┼────────>│   ├── Speed Layer   │
│                         │         │   ├── FUSE Mount    │
│  Claude Code Instance 3 │         │   ├── Expert Coord  │
│  └── MCP Server 3 ──────┼────────>│   └── API Server    │
│                         │         │                      │
└─────────────────────────┘         └──────────────────────┘
```

### Why This Architecture is Correct

1. **MCP Protocol Compliance**: Each Claude gets dedicated MCP server (1:1)
2. **Security Isolation**: Claude instances remain isolated
3. **Container Simplicity**: Container only runs Bridge components
4. **FUSE Requirements**: Container has necessary privileges for FUSE
5. **Network Efficiency**: Only Bridge API exposed (port 8765)
6. **Deployment Flexibility**: Easy to scale Claude instances independently

## IMPLEMENTATION PRIORITY

### Critical (Must Fix Immediately):
1. Line 108 in start-bridge-pyfuse3.sh - wrong module started
2. Remove mcp dependency from requirements-pyfuse3.txt

### Important (Fix Before Production):
1. Add proper Bridge startup parameters
2. Verify all Bridge dependencies are included
3. Document container runtime requirements

### Nice to Have:
1. Add Bridge-specific health checks
2. Optimize container size
3. Add configuration validation

## RISK ASSESSMENT

**Current Risk**: HIGH
- Container cannot function as intended
- Bridge components not being started
- MCP server has no Bridge to coordinate through

**Post-Fix Risk**: LOW
- Proper architectural alignment
- Clear component boundaries
- Correct startup sequence

## DECISION/OUTCOME

**Status**: REQUIRES_REMEDIATION
**Rationale**: Container violates fundamental architecture by attempting to run MCP servers instead of Bridge server. This is a critical architectural violation that prevents the system from functioning.
**Conditions**: Must fix startup script and remove MCP dependencies before container can work.

## EVIDENCE
- `/home/john/lighthouse/docs/architecture/HLD.md`: Lines 1226-1287 show Bridge in container
- `/home/john/lighthouse/docs/ai/agents/system-architect/certificates/mcp_container_boundary_architecture_decision_20250826_234500.md`: Confirms MCP stays on host
- `/home/john/lighthouse/Dockerfile.pyfuse3`: Builds container image
- `/home/john/lighthouse/requirements-pyfuse3.txt`: Line 34 incorrectly includes MCP
- `/home/john/lighthouse/scripts/docker/start-bridge-pyfuse3.sh`: Line 108 starts wrong component
- `/home/john/lighthouse/CLAUDE.md`: Line 59 shows correct startup command

## SIGNATURE
Agent: infrastructure-architect
Timestamp: 2025-08-27 00:00:00 UTC
Certificate Hash: SHA256:container-boundary-fix-plan-complete