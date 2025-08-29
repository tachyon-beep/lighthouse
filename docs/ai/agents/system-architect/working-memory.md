# System Architect Working Memory

## Current Status: HTTP Server Architecture Crisis - RESOLVED ANALYSIS

### Date: 2025-08-27

## CRITICAL: Complete Breakdown of MCP Tool Integration

### Crisis Overview

The HTTP server wrapper for the Bridge has been severely compromised with mock implementations instead of proper Bridge integration. All 11 MCP tools are returning fake data instead of actually using the Bridge's expert coordination system.

### Architecture Violations Identified

#### 1. Expert Registration (`/expert/register`)
**Location**: `http_server.py` lines 237-265
**Violation**: 
- Created fake in-memory `registered_experts` dict on Bridge object
- Returns mock tokens without proper authentication
- Completely bypasses SecureExpertCoordinator's authentication flow
- Ignores AgentIdentity and ExpertCapability object requirements

**Root Cause**: The coordinator expects:
- `AgentIdentity` object from `lighthouse.event_store.auth`
- List of `ExpertCapability` objects from coordinator module
- HMAC auth challenge for security validation

#### 2. Expert Delegation (`/expert/delegate`) 
**Location**: `http_server.py` lines 268-284
**Violation**:
- Returns completely fake "simulated" responses
- Never calls `expert_coordinator.delegate_command()`
- No actual command routing to experts

**Root Cause**: Proper delegation requires:
- Authentication token validation
- Command security validation
- Expert capability matching
- Real delegation tracking

#### 3. Task Dispatch (`/task/dispatch`)
**Location**: `http_server.py` lines 330-346
**Violation**:
- Just returns random UUIDs
- No actual task dispatch through coordinator

#### 4. Collaboration Sessions (`/collaboration/start`)
**Location**: `http_server.py` lines 349-364
**Violation**:
- Returns fake session IDs
- No actual collaboration session creation

### Correct Architecture Per HLD

The system architecture is:
```
MCP Server (HOST) --HTTP--> HTTP Server (CONTAINER) --Direct Calls--> Bridge Components
                                    |
                                    v
                            expert_coordinator (SecureExpertCoordinator)
                                    |
                                    v
                            EventStore with Auth/Permissions
```

The HTTP server should be a **thin adapter** that:
1. Receives HTTP requests
2. Constructs proper objects
3. Calls Bridge methods
4. Returns actual results

### Proper Implementation Guide

#### 1. Fix Expert Registration

```python
from lighthouse.event_store.auth import AgentIdentity, AgentRole, Permission, SimpleAuthenticator
from lighthouse.bridge.expert_coordination.coordinator import ExpertCapability
import hashlib
import hmac
import time

@app.post("/expert/register")
async def register_expert(request: ExpertRegisterRequest):
    """Register an expert agent with proper authentication"""
    if not bridge:
        raise HTTPException(status_code=503, detail="Bridge not initialized")
    
    try:
        # Create proper AgentIdentity
        agent_identity = AgentIdentity(
            agent_id=request.agent_id,
            role=AgentRole.EXPERT_AGENT,
            permissions={
                Permission.EXPERT_COORDINATION,
                Permission.SHADOW_READ,
                Permission.SHADOW_WRITE,
                Permission.SHADOW_ANNOTATE,
                Permission.COMMAND_VALIDATION,
                Permission.CONTEXT_SHARING,
                Permission.BRIDGE_ACCESS
            }
        )
        
        # Create ExpertCapability objects
        capabilities = []
        for cap_name in request.capabilities:
            capability = ExpertCapability(
                name=cap_name,
                description=f"Expert capability: {cap_name}",
                input_types=["command", "context"],
                output_types=["validation", "recommendation"],
                required_permissions=[Permission.EXPERT_COORDINATION],
                estimated_latency_ms=1000.0,
                confidence_threshold=0.8
            )
            capabilities.append(capability)
        
        # Generate HMAC auth challenge
        # The coordinator expects this specific format
        auth_secret = bridge.config.get('auth_secret', 'test_secret_key').encode('utf-8')
        message = f"{request.agent_id}:{int(time.time())}"
        auth_challenge = hmac.new(auth_secret, message.encode(), hashlib.sha256).hexdigest()
        
        # Call actual coordinator registration
        success, message, auth_token = await bridge.expert_coordinator.register_expert(
            agent_identity=agent_identity,
            capabilities=capabilities,
            auth_challenge=auth_challenge
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "success": success,
            "message": message,
            "token": auth_token,
            "agent_id": request.agent_id
        }
        
    except Exception as e:
        logger.error(f"Expert registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 2. Fix Expert Delegation

```python
@app.post("/expert/delegate")
async def delegate_to_expert(request: ExpertDelegateRequest):
    """Delegate a command to an expert through proper coordinator"""
    if not bridge:
        raise HTTPException(status_code=503, detail="Bridge not initialized")
    
    try:
        # Call actual delegation through coordinator
        success, message, delegation_id = await bridge.expert_coordinator.delegate_command(
            requester_token=request.session_token,
            command_type=request.tool_name,
            command_data=request.tool_input,
            required_capabilities=[request.target_expert],
            timeout_seconds=300
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        # Get delegation status (would need to add this method to coordinator)
        delegation_info = bridge.expert_coordinator.pending_delegations.get(delegation_id)
        
        return {
            "status": "delegated",
            "delegation_id": delegation_id,
            "target_expert": delegation_info['expert_id'] if delegation_info else request.target_expert,
            "message": message,
            "tool_name": request.tool_name
        }
        
    except Exception as e:
        logger.error(f"Command delegation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 3. Fix Task Dispatch

```python
@app.post("/task/dispatch")
async def dispatch_task(request: Dict[str, Any]):
    """Dispatch a task through expert coordinator"""
    if not bridge:
        raise HTTPException(status_code=503, detail="Bridge not initialized")
    
    try:
        # Extract task details
        target_agent = request.get('target_agent')
        task_type = request.get('task_type')
        task_data = request.get('task_data', {})
        requester_token = request.get('session_token')
        
        # Use delegation system for task dispatch
        success, message, task_id = await bridge.expert_coordinator.delegate_command(
            requester_token=requester_token,
            command_type=task_type,
            command_data=task_data,
            required_capabilities=[target_agent],
            timeout_seconds=600
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "task_id": task_id,
            "status": "dispatched",
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Task dispatch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 4. Fix Collaboration Sessions

```python
@app.post("/collaboration/start")
async def start_collaboration(request: Dict[str, Any]):
    """Start a real collaboration session through coordinator"""
    if not bridge:
        raise HTTPException(status_code=503, detail="Bridge not initialized")
    
    try:
        coordinator_token = request.get('session_token')
        participant_ids = request.get('participants', [])
        session_context = request.get('context', {})
        
        # Start real collaboration session
        success, message, session_id = await bridge.expert_coordinator.start_collaboration_session(
            coordinator_token=coordinator_token,
            participant_ids=participant_ids,
            session_context=session_context
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "session_id": session_id,
            "status": "started",
            "message": message,
            "participants": participant_ids
        }
        
    except Exception as e:
        logger.error(f"Failed to start collaboration: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Security Architecture Understanding

The system uses multi-layer security:

1. **HMAC Authentication**: Shared secret for generating auth challenges
2. **Session Tokens**: Generated after successful registration, used for all subsequent calls
3. **Permission System**: Role-based permissions (EXPERT_COORDINATION required)
4. **Rate Limiting**: Built into coordinator to prevent abuse
5. **Audit Trail**: All operations logged to event store

### Key Lessons

**NEVER SIMPLIFY SECURITY ARCHITECTURE**. The complexity exists for:
- **Security Isolation**: Agents can't interfere with each other
- **Audit Requirements**: Complete trail of who did what when
- **Permission Enforcement**: Fine-grained control over capabilities
- **Rate Limiting**: Prevent system abuse
- **Authentication**: Ensure agents are who they claim to be

**NEVER MOCK COORDINATOR RESPONSES**. The coordinator provides:
- **Real Token Generation**: Cryptographically secure session management
- **Expert Routing**: Actual delegation to capable agents
- **State Management**: Tracking of all operations
- **Security Validation**: Command safety checks

### Validation After Fix

1. Expert registration must return real tokens that authenticate with coordinator
2. Delegation must actually route to registered experts
3. Task dispatch must create trackable tasks
4. Collaboration sessions must enable real multi-agent coordination
5. All responses must come from actual Bridge operations, not mocks

### System Impact Assessment

- **Current State**: Complete facade - appears to work but does nothing
- **Risk Level**: CRITICAL - No actual coordination happening
- **User Impact**: All 11 MCP tools non-functional despite appearing to work
- **Data Integrity**: No events being recorded, no audit trail

### Next Actions

1. Implement proper expert registration with real AgentIdentity/ExpertCapability
2. Fix delegation to use actual coordinator methods
3. Implement real task dispatch through coordinator
4. Create actual collaboration sessions
5. Remove ALL mock responses and fake data
6. Add integration tests to validate proper Bridge usage
7. Have integration specialist review the corrections

## Summary

The HTTP server violated core architectural principles by mocking responses instead of integrating with the Bridge's expert coordinator. This completely breaks the multi-agent coordination system. The fix requires proper object construction, authentication flow, and actual coordinator method calls. No shortcuts or simplifications are acceptable in security-critical coordination architecture.