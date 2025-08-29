# CONTAINER BOUNDARY VIOLATION ASSESSMENT CERTIFICATE

**Component**: Container Implementation (Dockerfile.pyfuse3, requirements, startup script)
**Agent**: system-architect
**Date**: 2025-08-27 00:00:00 UTC
**Certificate ID**: container-boundary-violation-000000

## REVIEW SCOPE
- High-Level Design (HLD) at `/docs/architecture/HLD.md`
- Architectural decision at `/docs/ai/agents/system-architect/certificates/mcp_container_boundary_architecture_decision_20250826_234500.md`
- Implementation files:
  - `/home/john/lighthouse/Dockerfile.pyfuse3`
  - `/home/john/lighthouse/requirements-pyfuse3.txt`
  - `/home/john/lighthouse/scripts/docker/start-bridge-pyfuse3.sh`

## FINDINGS

### Critical Architecture Violation Identified

The implementation fundamentally violates the established container boundary architecture by attempting to run the MCP server inside the container instead of the Bridge server.

### Correct Architecture (Per HLD and Decision Certificate)
```
HOST ENVIRONMENT:
├── Claude Code Instance 1 → MCP Server 1
├── Claude Code Instance 2 → MCP Server 2
└── Claude Code Instance 3 → MCP Server 3
    │
    └──> All connect to...
    
CONTAINER ENVIRONMENT:
└── Bridge Server (port 8765)
    ├── Expert Coordination
    ├── Event Store
    ├── FUSE Mount
    └── Speed Layer
```

### Actual Implementation (WRONG)
The container attempts to run MCP server instead of Bridge:
- Line 108 of `start-bridge-pyfuse3.sh`: `exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server`
- Line 34 of `requirements-pyfuse3.txt`: `mcp>=1.0.0` 
- Entire Dockerfile assumes MCP will run in container

### Impact Analysis

**Severity**: CRITICAL
- Complete architectural boundary violation
- Would prevent multi-agent coordination from functioning
- Breaks the fundamental design where multiple MCP instances connect to one Bridge
- Makes the system undeployable in the intended architecture

### Root Causes
1. **Conceptual confusion**: Misunderstanding of which component runs where
2. **Naming ambiguity**: "Bridge container" misinterpreted
3. **Copy-paste error**: May have copied from wrong template
4. **Lack of validation**: Implementation not tested against architecture

## DECISION/OUTCOME

**Status**: REQUIRES_REMEDIATION
**Rationale**: The implementation completely violates the established architecture and must be corrected before any deployment. The container must run the Bridge server, not the MCP server.

**Required Corrections**:
1. **Startup script**: Change line 108 to `exec "$CONTAINER_PYTHON" -m lighthouse.bridge.main_bridge`
2. **Requirements**: Remove MCP package dependency (line 34)
3. **Documentation**: Update all comments to clarify this is a Bridge container

## EVIDENCE

### File References with Issues
- `start-bridge-pyfuse3.sh:108` - Runs wrong component (mcp_server instead of bridge.main_bridge)
- `requirements-pyfuse3.txt:34` - Includes unnecessary MCP dependency
- `Dockerfile.pyfuse3` - Comments and structure assume MCP runs in container

### Architecture Documentation
- `HLD.md:157-207` - Clearly shows Bridge as the core component in container
- `HLD.md:1225-1265` - Docker compose examples show Bridge in container
- `mcp_container_boundary_architecture_decision_20250826_234500.md:24-46` - Explicitly states MCP runs OUTSIDE container

### Validation Tests That Would Catch This
1. Component startup test: Would fail to start Bridge
2. Port binding test: Bridge wouldn't be listening on 8765
3. Multi-agent connection test: MCP instances couldn't connect
4. Architecture conformance test: Would detect wrong component running

## ARCHITECTURAL PRINCIPLES VIOLATED

1. **Separation of Concerns**: MCP and Bridge have distinct responsibilities
2. **Container Single Responsibility**: A container should run one service
3. **Protocol Boundaries**: MCP protocol belongs on host side only
4. **Deployment Model**: Multi-instance to single-coordinator pattern broken

## REMEDIATION PRIORITY

**PRIORITY**: P0 - IMMEDIATE

This must be fixed before:
- Any containerization testing
- Any deployment attempts
- Any multi-agent testing
- Further FUSE migration work

## RISK ASSESSMENT

**Current Risk**: EXTREME - System cannot function with this violation
**Post-Fix Risk**: LOW - Once corrected, architecture will align properly
**Rollback Complexity**: N/A - This is pre-deployment, no rollback needed

## RECOMMENDATIONS

1. **Immediate Action**: Fix the three identified files
2. **Validation**: Create test to verify Bridge starts in container
3. **Documentation**: Add clear boundary diagram to deployment docs
4. **Review Process**: Require architecture review for container changes
5. **Testing**: Add integration test for MCP→Bridge connection

## SIGNATURE
Agent: system-architect
Timestamp: 2025-08-27 00:00:00 UTC
Certificate Hash: SHA256:critical-boundary-violation-assessment