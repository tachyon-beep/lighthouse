# MCP-BRIDGE SEPARATION CRISIS ASSESSMENT CERTIFICATE

**Component**: MCP Server and Bridge Architecture
**Agent**: system-architect
**Date**: 2025-08-27 00:00:00 UTC
**Certificate ID**: SA-2025-0827-MBSC-001

## REVIEW SCOPE
- MCP Server implementation at `/home/john/lighthouse/src/lighthouse/mcp_server.py`
- Bridge implementation at `/home/john/lighthouse/src/lighthouse/bridge/main_bridge.py`
- Container boundary architecture requirements
- Current architectural violations and import dependencies

## FINDINGS

### CRITICAL ARCHITECTURAL VIOLATION

The current MCP server implementation **completely violates** the container boundary architecture:

1. **Direct Python Imports**: Lines 19-22 of `mcp_server.py` directly import Bridge components:
   ```python
   from lighthouse.bridge.main_bridge import LighthouseBridge
   from lighthouse.bridge.expert_coordination.coordinator import ExpertCoordinator
   from lighthouse.bridge.security.session_security import SessionSecurityValidator
   from lighthouse.event_store import EventStore, Event, EventType
   ```

2. **In-Process Bridge Creation**: Lines 54-65 attempt to create Bridge instance in same Python process
3. **Fallback to MinimalBridge**: Lines 79-106 create a "MinimalBridge" class (forbidden pattern!)
4. **No Network Communication**: Zero HTTP/WebSocket client code to connect to remote Bridge

### ROOT CAUSE ANALYSIS

The implementation assumes all components run in the same Python process, which is **fundamentally wrong** for the container architecture where:
- MCP Server runs on HOST
- Bridge runs in CONTAINER
- They communicate over network (port 8765)

### THE CORRECT ARCHITECTURE

```
HOST MACHINE                          CONTAINER
------------                          ---------
Claude Code 1 → MCP Server 1 ─┐
Claude Code 2 → MCP Server 2 ─┼─HTTP→ Bridge Server (port 8765)
Claude Code 3 → MCP Server 3 ─┘       ├── Event Store
                                       ├── Expert Coordinator
                                       ├── Speed Layer
                                       └── FUSE Mount
```

## DECISION/OUTCOME

**Status**: REQUIRES_REMEDIATION
**Rationale**: The MCP server must be completely rewritten to act as an HTTP client to the Bridge server, not import Bridge components directly
**Conditions**: No direct Python imports from Bridge components allowed

## THE CORRECT SOLUTION

### 1. Bridge Server (Container) - HTTP API Server

The Bridge needs an HTTP API server component (missing!):

```python
# src/lighthouse/bridge/http_server.py
from aiohttp import web
from .main_bridge import LighthouseBridge

class BridgeHTTPServer:
    def __init__(self, bridge: LighthouseBridge):
        self.bridge = bridge
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        self.app.router.add_post('/session/create', self.create_session)
        self.app.router.add_post('/validate', self.validate_command)
        self.app.router.add_post('/expert/register', self.register_expert)
        self.app.router.add_post('/expert/delegate', self.delegate_command)
        self.app.router.add_post('/events/store', self.store_event)
        self.app.router.add_get('/status', self.get_status)
        # ... other endpoints
    
    async def create_session(self, request):
        data = await request.json()
        result = await self.bridge.create_session(
            data['agent_id'],
            data.get('ip_address', ''),
            data.get('user_agent', '')
        )
        return web.json_response(result)
    
    # ... implement other handlers
    
    def run(self, host='0.0.0.0', port=8765):
        web.run_app(self.app, host=host, port=port)
```

### 2. MCP Server (Host) - HTTP Client

The MCP server should be a thin HTTP client:

```python
# src/lighthouse/mcp_server.py
import aiohttp
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lighthouse-bridge")

BRIDGE_URL = "http://localhost:8765"  # Or from environment variable

async def call_bridge(endpoint: str, data: dict = None):
    """Make HTTP call to Bridge server"""
    async with aiohttp.ClientSession() as session:
        url = f"{BRIDGE_URL}/{endpoint}"
        async with session.post(url, json=data) as response:
            return await response.json()

@mcp.tool()
async def lighthouse_create_session(agent_id: str, ip_address: str = "", user_agent: str = "") -> str:
    """Create session via Bridge HTTP API"""
    result = await call_bridge('session/create', {
        'agent_id': agent_id,
        'ip_address': ip_address,
        'user_agent': user_agent
    })
    return json.dumps(result)

@mcp.tool()
async def lighthouse_validate_command(tool_name: str, tool_input: dict, agent_id: str) -> str:
    """Validate command via Bridge HTTP API"""
    result = await call_bridge('validate', {
        'tool_name': tool_name,
        'tool_input': tool_input,
        'agent_id': agent_id
    })
    return json.dumps(result)

# ... other tools as HTTP client calls

if __name__ == "__main__":
    mcp.run()
```

### 3. Container Startup Script Fix

```bash
# scripts/docker/start-bridge-pyfuse3.sh
# Start the Bridge HTTP server, NOT the MCP server
python -m lighthouse.bridge.http_server
```

## IMPLEMENTATION STEPS

1. **Create Bridge HTTP Server**:
   - New file: `src/lighthouse/bridge/http_server.py`
   - Wraps existing Bridge with HTTP endpoints
   - Runs on port 8765 in container

2. **Rewrite MCP Server as HTTP Client**:
   - Remove ALL Bridge imports
   - Replace with aiohttp client calls
   - Each tool becomes an HTTP request

3. **Fix Container Configuration**:
   - Remove MCP from requirements-pyfuse3.txt
   - Update start script to run Bridge HTTP server

4. **Environment Configuration**:
   - MCP server reads `BRIDGE_URL` from environment
   - Defaults to `http://localhost:8765`
   - Supports remote Bridge servers

## EVIDENCE

- File: `/home/john/lighthouse/src/lighthouse/mcp_server.py`, lines 19-22: Direct Bridge imports
- File: `/home/john/lighthouse/src/lighthouse/mcp_server.py`, lines 54-65: In-process Bridge creation
- File: `/home/john/lighthouse/src/lighthouse/mcp_server.py`, lines 79-106: MinimalBridge anti-pattern
- Missing: HTTP server component for Bridge
- Missing: HTTP client code in MCP server

## CRITICAL WARNINGS

1. **DO NOT** create "minimal" versions of Bridge components
2. **DO NOT** import Bridge modules in MCP server
3. **DO NOT** run MCP server in container
4. **DO NOT** mix host and container components

## SIGNATURE
Agent: system-architect
Timestamp: 2025-08-27 00:00:00 UTC
Certificate Hash: SHA256:MBSC001