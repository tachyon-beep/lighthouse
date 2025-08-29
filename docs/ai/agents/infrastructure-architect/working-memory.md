# Infrastructure Architect Working Memory

## CRITICAL: Container Architecture Violation Fix

**Issue Date**: 2025-08-27 00:00 UTC
**Status**: REQUIRES_IMMEDIATE_REMEDIATION
**Certificate**: container_boundary_fix_plan_20250827_000000

### URGENT: Container Boundary Violation

**THE PROBLEM**: We built a container that runs MCP server instead of Bridge server, violating the fundamental architecture where:
- Bridge (with FUSE) goes IN the container
- MCP servers stay on HOST (1:1 with Claude instances)

**CRITICAL FILES TO FIX**:
1. `scripts/docker/start-bridge-pyfuse3.sh` line 108: Running wrong module
2. `requirements-pyfuse3.txt` line 34: Has MCP dependency (should not)
3. `Dockerfile.pyfuse3`: Otherwise correct, just wrong startup command

**EXACT FIXES REQUIRED**:
```bash
# Line 108 of start-bridge-pyfuse3.sh
# WRONG: exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server
# RIGHT: exec "$CONTAINER_PYTHON" -m lighthouse.bridge.main_bridge

# Line 34 of requirements-pyfuse3.txt
# REMOVE: mcp>=1.0.0
```

### Correct Architecture
```
HOST:                          CONTAINER:
Claude Instance 1 → MCP 1 ─┐
Claude Instance 2 → MCP 2 ─┼─→ Bridge Server (:8765)
Claude Instance 3 → MCP 3 ─┘      ├── FUSE Mount
                                   ├── Event Store
                                   └── Speed Layer
```

---

## Current Project: Dual FUSE Backend Migration Infrastructure

**Implementation Date**: 2025-08-27  
**Status**: INFRASTRUCTURE_IMPLEMENTATION_COMPLETE  
**Certificate**: dual_fuse_infrastructure_implementation_20250827_113000

### Executive Summary

Implemented comprehensive container infrastructure to support both fusepy (FUSE2) and pyfuse3 (FUSE3) during the 7-week migration period. Infrastructure enables zero-downtime migration with automatic rollback capabilities.

### Implementation Deliverables

#### Container Configuration
1. **Multi-stage Dockerfile** (`Dockerfile.dual-fuse`)
   - Builder stage with both FUSE development libraries
   - Tester stage for backend validation
   - Runtime stage with dual backend support
   - Development stage with debugging tools
   - Benchmark stage for performance testing

2. **Docker Compose Configuration** (`docker-compose.dual-fuse.yml`)
   - Primary service with backend selection
   - Development environment profile
   - Benchmark environment profile
   - Migration testing profile

3. **Startup Scripts**
   - `start-bridge-dual-fuse.sh`: Intelligent backend selection
   - `validate-fuse-backend.py`: Health check validation

#### Infrastructure Characteristics

**Image Size Impact**:
- Base image: ~150MB
- Additional overhead: ~50MB (33% increase)
- Acceptable for migration safety benefits
- Will reduce post-migration

**Library Coexistence**:
- libfuse2 and libfuse3 installed side-by-side
- No conflicts due to different soname versions
- LD_LIBRARY_PATH properly configured
- Dynamic loading based on backend selection

**Resource Requirements**:
- CPU: 4.0 cores (limit), 1.0 core (reservation)
- Memory: 2GB (limit), 1GB (reservation)
- Storage: 1GB tmpfs for cache during testing
- Network: 3 exposed ports (API, shadow, metrics)

### Backend Selection Architecture

```
Environment Variables:
├── LIGHTHOUSE_FUSE_BACKEND (primary choice)
├── LIGHTHOUSE_FUSE_FALLBACK (backup option)
└── LIGHTHOUSE_ACTIVE_FUSE_BACKEND (runtime selection)

Selection Flow:
1. Check primary backend availability
2. If unavailable, check fallback
3. If both unavailable, degraded mode
4. Export LIGHTHOUSE_ACTIVE_FUSE_BACKEND
```

### Testing Infrastructure

#### Parallel Testing Mode
- Primary backend on port 8765
- Shadow backend on port 8766
- Automatic comparison of results
- Divergence metrics collected

#### Benchmark Suite
- 10 operation types tested
- 1000 iterations with 100 warmup
- Latency percentiles (P50, P95, P99)
- Throughput and IOPS metrics
- CPU/memory profiling

#### CI/CD Pipeline
- Separate test jobs for each backend
- Compatibility testing job
- Performance regression detection
- Automatic rollback triggers

### Deployment Strategy

#### Phase Timeline
- **Weeks 1-3**: Parallel deployment (fusepy primary)
- **Week 4-5**: Canary deployment (10% pyfuse3)
- **Week 6**: Progressive rollout (50-90% pyfuse3)
- **Week 7**: Full migration to pyfuse3
- **Week 8**: Cleanup and optimization

#### Rollback Mechanisms
1. **Automatic Triggers**:
   - Error rate >1%
   - P99 latency >1s
   - Backend divergence >0.1%

2. **Manual Procedures**:
   - Environment variable override
   - Container restart with HUP signal
   - Full image rollback option

### Monitoring Configuration

#### Prometheus Metrics
- `lighthouse_fuse_operations_total`: Operation counts by backend
- `lighthouse_fuse_operation_duration_seconds`: Latency histograms
- `lighthouse_fuse_backend_active`: Current backend gauge
- `lighthouse_fuse_backend_divergence_total`: Comparison mismatches

#### Grafana Dashboards
- Operations by backend panel
- Latency comparison charts
- Divergence rate monitoring
- Resource utilization graphs

### Security Considerations

#### Capability Management
- Minimal SYS_ADMIN for FUSE
- All other capabilities dropped
- Seccomp profiles configured
- AppArmor unconfined (required for FUSE)

#### Runtime Security
- Non-root user (lighthouse:1000)
- Read-only root filesystem option
- Secrets via environment variables
- No embedded credentials

### Package Dependencies

#### Core Requirements
```
# Both FUSE backends
fusepy==3.0.1       # Current production
pyfuse3==3.3.0      # Migration target
trio==0.25.1        # Async for pyfuse3

# Optional but recommended
scikit-learn==1.5.0
tree-sitter==0.21.3
numpy==1.26.4
scipy==1.13.1

# Development/Testing
pytest==8.2.2
pytest-benchmark==4.0.0
black==24.4.2
mypy==1.10.0
```

### Migration Readiness Checklist

- [x] Dual-backend Dockerfile created
- [x] Docker Compose configurations ready
- [x] Startup scripts with backend selection
- [x] Health check validation scripts
- [x] Benchmark suite configured
- [x] CI/CD pipeline templates
- [x] Monitoring dashboards designed
- [x] Rollback procedures documented
- [x] Security profiles configured
- [x] Migration timeline established

## Previous Context Updates

### libfuse2 to libfuse3 Upgrade Analysis
**Date**: 2025-08-27 (earlier)
**Status**: Completed - Recommended phased migration to pyfuse3
**Next Step**: Infrastructure implementation (NOW COMPLETE)

### FUSE Containerization Fix
**Date**: 2025-08-27 (earlier)
**Status**: Resolved - Container working with libfuse2
**Learning**: fusepy requires exact libfuse2 version match

## Next Actions

### CRITICAL (TODAY):
- [ ] **FIX CONTAINER BOUNDARY VIOLATION**
  - [ ] Change startup script to run Bridge not MCP
  - [ ] Remove MCP dependency from requirements
  - [ ] Test Bridge startup in container
  - [ ] Verify Bridge API accessibility

### IMMEDIATE (This Week):
- [x] Implement dual-FUSE container infrastructure
- [ ] Deploy to staging environment
- [ ] Run initial benchmark suite
- [ ] Validate parallel testing mode
- [ ] Create migration runbook

### WEEK 1-2 (Testing Phase):
- [ ] Execute compatibility test suite
- [ ] Collect baseline performance metrics
- [ ] Identify any edge cases
- [ ] Document behavioral differences
- [ ] Refine rollback procedures

### WEEK 3-4 (Canary Phase):
- [ ] Deploy 10% traffic to pyfuse3
- [ ] Monitor divergence metrics
- [ ] Analyze performance differences
- [ ] Address any issues found
- [ ] Prepare for wider rollout

### WEEK 5-7 (Migration Phase):
- [ ] Progressive traffic increase
- [ ] Continuous monitoring
- [ ] Performance optimization
- [ ] Full production migration
- [ ] Post-migration validation

## System State

- **Bridge**: NOT RUNNING IN CONTAINER (critical issue)
- **Container**: Built but running wrong component
- **MCP**: Should be on host, incorrectly targeted for container
- **FUSE**: Properly configured but not used by Bridge
- **Testing**: Infrastructure ready but not applicable until fixed

## Infrastructure Decisions Log

1. **2025-08-27 00:00**: CRITICAL - Identified container boundary violation
2. **2025-08-27 11:30**: Implemented dual-FUSE container infrastructure
3. **2025-08-27 04:30**: Recommended phased migration to pyfuse3
4. **2025-08-27 00:00**: Fixed container to use libfuse2
5. **Previous**: Containerization with privileged mode for FUSE