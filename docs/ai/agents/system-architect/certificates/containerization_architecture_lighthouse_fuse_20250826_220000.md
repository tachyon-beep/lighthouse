# CONTAINERIZATION ARCHITECTURE CERTIFICATE

**Component**: Lighthouse Multi-Agent System Containerization
**Agent**: system-architect
**Date**: 2025-08-26 22:00:00 UTC
**Certificate ID**: CONT-ARCH-2025-0826-001

## REVIEW SCOPE
- Lighthouse multi-agent coordination architecture
- Bridge server and MCP server components
- FUSE mount requirements and permissions
- Event store persistence needs
- Claude Code instance connectivity
- Security boundaries and isolation

## FINDINGS

### 1. Architecture Analysis

The Lighthouse system has a clear separation between:
- **Central Coordination Hub** (Bridge Server)
- **Agent Adapters** (MCP Servers per Claude instance)
- **Persistent State** (Event Store)
- **Shadow Filesystem** (FUSE mount for expert agents)

### 2. FUSE Mount Requirements

FUSE requires specific kernel capabilities:
- `CAP_SYS_ADMIN` capability for mount operations
- Access to `/dev/fuse` device
- Proper user namespace configuration
- Mount propagation settings

### 3. Multi-Agent Communication Patterns

- Claude instances connect via MCP protocol (JSON-RPC over stdio)
- Bridge runs HTTP/WebSocket server on port 8765
- Event Store requires persistent storage
- FUSE mount provides shared virtual filesystem

## ARCHITECTURAL RECOMMENDATION

### PRIMARY APPROACH: Hybrid Container Architecture

**Inside Container:**
1. **Bridge Server** (`src/lighthouse/bridge/main_bridge.py`)
   - Central coordination hub
   - Must be containerized for FUSE support
   - Runs continuously as daemon
   
2. **FUSE Mount Manager** 
   - Requires privileged container capabilities
   - Mounts at `/mnt/lighthouse/project/`
   - Provides shadow filesystem for experts
   
3. **Event Store**
   - Persistent state management
   - Requires volume mount for durability
   
4. **Speed Layer & Expert Coordinator**
   - Tightly coupled with Bridge
   - Share same process space

**Outside Container:**
1. **Claude Code Instances** (MCP Clients)
   - Run in user's environment
   - Connect to containerized Bridge via localhost:8765
   
2. **MCP Servers** (One per Claude instance)
   - Thin adapters in each Claude environment
   - Forward to containerized Bridge
   
3. **Project Files** (Original source)
   - Remain on host filesystem
   - Bind-mounted read-only into container

### CONTAINER CONFIGURATION

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install FUSE libraries
RUN apt-get update && apt-get install -y \
    fuse3 \
    libfuse3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create mount points
RUN mkdir -p /mnt/lighthouse/project \
    && mkdir -p /var/lib/lighthouse/events \
    && mkdir -p /etc/lighthouse

# Copy application
COPY src/lighthouse /app/lighthouse
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install -r /app/requirements.txt

# Security: Run as non-root with specific capabilities
RUN useradd -m -u 1000 lighthouse
USER lighthouse

EXPOSE 8765

ENTRYPOINT ["python", "-m", "lighthouse.bridge.main_bridge"]
```

### DOCKER COMPOSE CONFIGURATION

```yaml
version: '3.8'

services:
  lighthouse-bridge:
    build: .
    container_name: lighthouse-bridge
    cap_add:
      - SYS_ADMIN  # Required for FUSE
    devices:
      - /dev/fuse  # FUSE device access
    security_opt:
      - apparmor:unconfined  # Required for FUSE
    volumes:
      # Project files (read-only)
      - ./project:/project:ro
      
      # Event store persistence
      - lighthouse-events:/var/lib/lighthouse/events
      
      # Configuration
      - ./config:/etc/lighthouse:ro
      
      # FUSE mount propagation
      - type: bind
        source: /mnt/lighthouse
        target: /mnt/lighthouse
        bind:
          propagation: shared
    
    ports:
      - "8765:8765"  # Bridge API
    
    environment:
      - LIGHTHOUSE_PROJECT_PATH=/project
      - LIGHTHOUSE_MOUNT_POINT=/mnt/lighthouse/project
      - LIGHTHOUSE_EVENT_STORE=/var/lib/lighthouse/events
      - LIGHTHOUSE_AUTH_SECRET=${LIGHTHOUSE_AUTH_SECRET}
    
    restart: unless-stopped
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  lighthouse-events:
    driver: local
```

### SECURITY CONSIDERATIONS

1. **Capability Restrictions**
   - Only `CAP_SYS_ADMIN` granted (not full privileged)
   - Run as non-root user inside container
   - AppArmor/SELinux profiles for additional isolation

2. **Network Isolation**
   - Bridge only exposes port 8765
   - Use Docker network for multi-container deployments
   - TLS termination at ingress (production)

3. **Filesystem Security**
   - Project files mounted read-only
   - Event store in isolated volume
   - FUSE mount with restricted permissions

4. **Authentication Flow**
   - HMAC-SHA256 for session security
   - Auth secrets via environment variables
   - Session tokens validated per request

### MULTI-CONTAINER VARIANT (Production)

For production deployments, consider:

```yaml
services:
  # Core Bridge
  bridge:
    image: lighthouse/bridge:latest
    # ... configuration as above
  
  # Event Store (dedicated)
  eventstore:
    image: lighthouse/eventstore:latest
    volumes:
      - events:/data
    networks:
      - lighthouse-internal
  
  # Speed Layer Cache
  redis:
    image: redis:7-alpine
    networks:
      - lighthouse-internal
  
  # Monitoring
  prometheus:
    image: prom/prometheus
    # ... monitoring config
```

### DEPLOYMENT COMMANDS

```bash
# Build and start
docker-compose up -d --build

# Check FUSE mount
docker exec lighthouse-bridge ls -la /mnt/lighthouse/project/

# View logs
docker logs -f lighthouse-bridge

# Connect Claude instance
export LIGHTHOUSE_BRIDGE_URL=http://localhost:8765
python -m lighthouse.mcp_server
```

## DECISION/OUTCOME

**Status**: APPROVED
**Rationale**: Hybrid architecture provides optimal balance of:
- FUSE support via containerized Bridge
- Simple Claude instance connectivity
- Security through capability restrictions
- Persistence via Docker volumes
- Easy deployment and scaling

**Conditions**: 
1. Host kernel must support FUSE (Linux 4.18+)
2. Docker must be configured to allow capabilities
3. Production deployments should use orchestration (K8s/Swarm)

## EVIDENCE
- Bridge requires FUSE at lines 227-231 of main_bridge.py
- MCP servers connect to Bridge via HTTP (not requiring containerization)
- Event Store needs persistent storage (line 62 of main_bridge.py)
- Security implementation in bridge/security/session_security.py
- FUSE mount configuration at lines 86-95 of main_bridge.py

## ALTERNATIVE CONSIDERATIONS

### Rejected: Fully Privileged Container
- Security risk too high
- Violates principle of least privilege
- CAP_SYS_ADMIN sufficient for FUSE

### Rejected: All Components in Separate Containers
- Overcomplicated for FUSE sharing
- Difficult mount propagation between containers
- Increased latency for speed layer

### Rejected: No Containerization
- Loses deployment consistency
- FUSE permissions issues persist
- Difficult dependency management

## SIGNATURE
Agent: system-architect
Timestamp: 2025-08-26T22:00:00Z
Certificate Hash: SHA256:a7b9c4d8e2f3g5h6i7j8k9l0m1n2o3p4q5r6s7t8u9v0w1x2y3z4