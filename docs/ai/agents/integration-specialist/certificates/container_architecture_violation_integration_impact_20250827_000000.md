# INTEGRATION IMPACT ANALYSIS CERTIFICATE

**Component**: Container startup configuration - MCP vs Bridge  
**Agent**: integration-specialist
**Date**: 2025-08-27 00:00:00 UTC
**Certificate ID**: cert-integ-20250827-container-violation

## REVIEW SCOPE
- Container configuration running wrong component (MCP instead of Bridge)
- Multi-agent coordination pattern violations
- Event flow and integration breakage analysis
- Shadow filesystem integration impact
- Partial work confusion scenarios

## FINDINGS

### Critical Integration Failures
1. **Complete Inversion of Architecture**
   - Container runs MCP adapter instead of Bridge server
   - MCP is meant to run on HOST connecting TO Bridge
   - Bridge should be in container as central coordinator

2. **Multi-Agent Coordination Destroyed**
   - Multiple Claude instances cannot connect to MCP adapter
   - Port 8765 occupied by wrong component (MCP not Bridge)
   - Protocol mismatch: MCP expects Bridge, not other MCPs

3. **Event Flow Completely Broken**
   - No Bridge means no validation pipeline
   - No expert coordination possible
   - Events stored but never propagated to agents

4. **Shadow Filesystem Non-Existent**
   - FUSE mount requires Bridge's VirtualFilesystemMount
   - MCP has no FUSE capability
   - Expert agents have zero file access

5. **Deceptive Partial Functionality**
   - MinimalBridge fallback creates illusion of working system
   - Status returns "operational" but nothing coordinates
   - Diagnostic nightmare: looks degraded, actually dead

### Integration Points Affected
- **Port 8765**: Wrong service listening
- **MCP Configuration**: Claude instances can't find their adapters
- **Event Propagation**: Complete failure
- **Expert Registration**: Non-functional
- **Command Validation**: Returns errors for everything
- **Shadow Filesystem**: Completely absent
- **AST Anchoring**: Non-functional

## DECISION/OUTCOME
**Status**: EMERGENCY_STOP
**Rationale**: This is a complete architectural inversion that breaks every integration point in the multi-agent system. The container runs the wrong component entirely, making multi-agent coordination impossible.
**Conditions**: Must change container to run `lighthouse.bridge.main_bridge` instead of `lighthouse.mcp_server`

## EVIDENCE
- HLD.md lines 14-66: Clear architecture showing Bridge as central hub
- mcp_server.py lines 43-120: MCP requires Bridge to function
- mcp_server.py line 203: Returns error without Bridge
- HLD lines 256-293: FUSE mount requires Bridge component
- CLAUDE.md: States Bridge runs at localhost:8765, not MCP

## SIGNATURE
Agent: integration-specialist
Timestamp: 2025-08-27 00:00:00 UTC
Certificate Hash: sha256:container-violation-emergency