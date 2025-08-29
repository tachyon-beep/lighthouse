# CONTAINER CONFIGURATION CRISIS OPERATIONAL REVIEW CERTIFICATE

**Component**: Container configuration and deployment strategy
**Agent**: devops-engineer
**Date**: 2025-08-27 00:00:00 UTC
**Certificate ID**: devops-crisis-20250827-000000

## REVIEW SCOPE
- Dockerfile.pyfuse3 container build strategy
- requirements-pyfuse3.txt dependency management
- start-bridge-pyfuse3.sh startup orchestration
- Container architecture alignment with system design
- Operational implications of configuration errors
- Production deployment risks and concerns

## FINDINGS

### Critical Architectural Misalignment
1. **Wrong Service Running**: Container runs MCP server (`lighthouse.mcp_server`) instead of Bridge server (`lighthouse.bridge.main_bridge`)
   - Line 108 in start-bridge-pyfuse3.sh: `exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server`
   - Should be: `exec "$CONTAINER_PYTHON" -m lighthouse.bridge.main_bridge`

2. **Invalid Dependency**: MCP dependency included in container requirements
   - Line 34-35 in requirements-pyfuse3.txt: `mcp>=1.0.0`
   - MCP should remain on host for Claude Code instances, not in Bridge container

3. **Port Exposure Mismatch**: Health check expects Bridge API but container runs MCP server
   - Health check on line 92: `CMD curl -f http://localhost:8765/health`
   - MCP server doesn't expose Bridge API endpoints

### Operational Impact Assessment

#### 1. **Service Discovery Failures**
- External Claude Code instances expect Bridge API at `localhost:8765`
- Container exposes MCP server instead, causing connection failures
- No fallback mechanism for service discovery failures

#### 2. **Health Check False Positives/Negatives**
- Health check endpoint `/health` won't exist if MCP server runs
- Container will appear unhealthy even when MCP server is functioning
- Orchestration systems will continuously restart healthy containers

#### 3. **FUSE Mount Operational Issues**
- Container expects FUSE privileges (`CAP_SYS_ADMIN`) for Bridge filesystem
- MCP server doesn't use FUSE, making these privileges unnecessary security risk
- FUSE mount point `/mnt/lighthouse/project` unused by wrong service

#### 4. **Resource Allocation Problems**
- Container sized for Bridge workload (memory, CPU)
- MCP server has different resource profile
- Over-provisioning leads to resource waste

#### 5. **Logging and Monitoring Confusion**
- Log analysis expecting Bridge-specific log patterns
- MCP server logs different format/content
- Monitoring dashboards show incorrect metrics

### Additional DevOps Concerns

#### Security Issues
1. **Unnecessary Privileges**: Running with `CAP_SYS_ADMIN` for FUSE when not needed
2. **Attack Surface**: MCP dependencies increase container attack surface unnecessarily
3. **Service Confusion**: Wrong service running creates potential for security misconfiguration

#### Deployment Risks
1. **Silent Failures**: Container starts successfully but provides wrong service
2. **Client Timeouts**: Claude Code instances will timeout waiting for Bridge API
3. **Cascade Failures**: Dependent services fail when Bridge unavailable

#### Operational Complexity
1. **Debugging Difficulties**: Logs show MCP activity when Bridge problems expected
2. **Port Conflicts**: MCP server may use different ports than expected 8765
3. **Configuration Drift**: Container env vars for Bridge unused by MCP server

## DECISION/OUTCOME
**Status**: EMERGENCY_STOP
**Rationale**: Container configuration fundamentally broken - runs wrong service with incompatible dependencies and security posture. Will cause complete system failure in production.
**Conditions**: Must fix all identified issues before any deployment

## EVIDENCE
- `/home/john/lighthouse/scripts/docker/start-bridge-pyfuse3.sh:108` - Wrong Python module invocation
- `/home/john/lighthouse/requirements-pyfuse3.txt:34-35` - Invalid MCP dependency
- `/home/john/lighthouse/Dockerfile.pyfuse3:92` - Health check expects Bridge API
- `/home/john/lighthouse/docs/architecture/HLD.md:76-82` - Bridge specification shows correct service

## ENHANCED FIX PLAN

### Immediate Fixes (Identified by Architects)
1. **Line 108 Fix**: Change `lighthouse.mcp_server` to `lighthouse.bridge.main_bridge`
2. **Remove MCP Dependency**: Remove `mcp>=1.0.0` from requirements-pyfuse3.txt
3. **Port Exposure**: Ensure Bridge API properly exposed on 8765

### Additional DevOps Requirements

#### 4. **Health Check Enhancement**
Update health check to verify Bridge-specific functionality:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8765/health && \
        curl -f http://localhost:8765/status || exit 1
```

#### 5. **Resource Right-Sizing**
Adjust resource limits for Bridge workload:
```dockerfile
# Add resource constraints
LABEL resource.memory="1GB"
LABEL resource.cpu="0.5"
```

#### 6. **Security Hardening**
Only grant FUSE privileges when actually needed:
```dockerfile
# Document required capabilities
LABEL security.capabilities="SYS_ADMIN"
LABEL security.reason="FUSE mount for shadow filesystem"
```

#### 7. **Environment Variable Validation**
Add startup validation for Bridge-specific env vars:
```bash
# Validate Bridge configuration
if [[ -z "$LIGHTHOUSE_EVENT_STORE_PATH" ]]; then
    echo "❌ LIGHTHOUSE_EVENT_STORE_PATH required for Bridge"
    exit 1
fi
```

#### 8. **Startup Logging Enhancement**
Add Bridge-specific startup logging:
```bash
echo "Bridge Event Store: ${LIGHTHOUSE_EVENT_STORE_PATH}"
echo "Bridge Snapshot Path: ${LIGHTHOUSE_SNAPSHOT_PATH}"
echo "FUSE Mount Point: ${LIGHTHOUSE_MOUNT_POINT}"
```

#### 9. **Graceful Shutdown Support**
Add signal handling for clean Bridge shutdown:
```bash
# Handle SIGTERM for graceful shutdown
trap 'echo "Shutting down Bridge..."; kill $BRIDGE_PID; wait $BRIDGE_PID' TERM
```

#### 10. **Container Labels for Operations**
Add operational metadata:
```dockerfile
LABEL maintainer="lighthouse-devops"
LABEL service="lighthouse-bridge" 
LABEL version="pyfuse3"
LABEL component="coordination-hub"
```

### Production Deployment Considerations

#### Container Orchestration
- **Kubernetes**: Requires `privileged: true` or specific capability grants
- **Docker Compose**: Needs `cap_add: [SYS_ADMIN]` and `/dev/fuse` device
- **Docker Swarm**: FUSE support limitations in swarm mode

#### Monitoring Integration
- Bridge-specific metrics collection
- FUSE mount health monitoring
- Event store performance tracking

#### Backup Strategy
- Event store data persistence
- Snapshot data backup
- Container state recovery procedures

## SIGNATURE
Agent: devops-engineer
Timestamp: 2025-08-27 00:00:00 UTC
Certificate Hash: devops-crisis-emergency-stop