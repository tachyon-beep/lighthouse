# Lighthouse FUSE Migration Plan: fusepy → pyfuse3

## Executive Summary

This document outlines a comprehensive migration strategy for transitioning the Lighthouse Bridge FUSE implementation from fusepy (libfuse2) to pyfuse3 (libfuse3). The migration will be executed through a phased approach with parallel implementations, ensuring zero downtime and maintaining full backward compatibility during the transition.

## Current State Analysis

### Technology Stack
- **Current**: fusepy 3.0.1 with libfuse2
- **Target**: pyfuse3 with libfuse3
- **Components Affected**: Bridge FUSE mount subsystem

### Architecture Assessment
The FUSE implementation is well-contained within the Bridge architecture:
- **Primary Module**: `src/lighthouse/bridge/fuse_mount/`
- **Core Implementation**: `complete_lighthouse_fuse.py` (1,175 lines)
- **Mount Manager**: `mount_manager.py` (551 lines)
- **Authentication**: Integrated authentication system
- **Dependencies**: Event Store, AST Anchoring, Project Aggregate

### Critical Observations
1. fusepy uses a **synchronous** API model
2. pyfuse3 uses an **asynchronous** API model (asyncio-native)
3. Container currently hardcoded for libfuse2 in Dockerfile
4. FUSE operations are performance-critical (<5ms target)

## Migration Architecture Design

### 1. Abstraction Layer Strategy

Create a FUSE backend abstraction that supports both implementations:

```python
# src/lighthouse/bridge/fuse_mount/backend.py
class FUSEBackend(ABC):
    """Abstract base for FUSE implementations"""
    
    @abstractmethod
    async def mount(self, mount_point: str, options: Dict) -> bool:
        pass
    
    @abstractmethod
    async def unmount(self, mount_point: str) -> bool:
        pass
    
    @abstractmethod
    def get_operations(self) -> Any:
        pass

# src/lighthouse/bridge/fuse_mount/fusepy_backend.py
class FusepyBackend(FUSEBackend):
    """Legacy fusepy implementation"""
    
# src/lighthouse/bridge/fuse_mount/pyfuse3_backend.py  
class PyFuse3Backend(FUSEBackend):
    """Modern pyfuse3 implementation"""
```

### 2. Adapter Pattern Implementation

Create operation adapters to bridge API differences:

```python
# src/lighthouse/bridge/fuse_mount/adapters.py
class FUSEOperationsAdapter:
    """Adapts between fusepy and pyfuse3 operation signatures"""
    
    def adapt_getattr(self, fusepy_sig) -> pyfuse3_sig:
        """Convert getattr signatures"""
        
    def adapt_read(self, fusepy_sig) -> pyfuse3_sig:
        """Convert read signatures with async support"""
```

### 3. Configuration-Driven Selection

Enable runtime backend selection:

```python
# Configuration
FUSE_BACKEND = os.environ.get('LIGHTHOUSE_FUSE_BACKEND', 'fusepy')  # or 'pyfuse3'

# Factory pattern
def create_fuse_backend(config: Dict) -> FUSEBackend:
    if config['backend'] == 'pyfuse3':
        return PyFuse3Backend(config)
    return FusepyBackend(config)
```

## Component Impact Analysis

### 1. Direct FUSE Components

| Component | Risk Level | Changes Required | Migration Priority |
|-----------|------------|------------------|-------------------|
| `complete_lighthouse_fuse.py` | HIGH | Full adapter implementation | Phase 2 |
| `mount_manager.py` | MEDIUM | Backend selection logic | Phase 1 |
| `authentication.py` | LOW | No changes (abstracted) | N/A |
| `__init__.py` | LOW | Import adjustments | Phase 1 |

### 2. Bridge Integration Points

| Integration | Risk Level | Impact | Mitigation |
|-------------|------------|--------|------------|
| Event Store | LOW | None - abstracted interface | Test thoroughly |
| AST Anchoring | LOW | None - abstracted interface | Validate anchors |
| Project Aggregate | LOW | None - abstracted interface | State consistency |
| Speed Layer | MEDIUM | Performance characteristics | Benchmark both |

### 3. Container Infrastructure

| Component | Risk Level | Changes Required |
|-----------|------------|------------------|
| Dockerfile | HIGH | Multi-stage for both libs | 
| Runtime deps | HIGH | Conditional installation |
| Mount permissions | MEDIUM | Capability adjustments |

## Migration Strategy

### Phase 0: Preparation (Week 1)
1. **Create abstraction layer**
   - Design FUSEBackend interface
   - Implement factory pattern
   - Add configuration support

2. **Setup dual-library containers**
   - Modify Dockerfile for both libraries
   - Create build variants
   - Test library detection

3. **Comprehensive testing baseline**
   - Performance benchmarks with fusepy
   - Full operation coverage tests
   - Multi-agent coordination tests

### Phase 1: Parallel Implementation (Weeks 2-3)
1. **Implement pyfuse3 backend**
   - Core operations (getattr, read, readdir)
   - Write operations with event sourcing
   - Stream and debug operations

2. **Create operation adapters**
   - Sync-to-async bridges
   - Error code mapping
   - Permission translation

3. **Integration testing**
   - Side-by-side testing
   - Performance comparison
   - Expert agent workflows

### Phase 2: Staged Rollout (Weeks 4-5)
1. **Development environment**
   - Enable pyfuse3 in dev containers
   - Monitor performance/stability
   - Collect metrics

2. **Staging environment**
   - 10% traffic with feature flags
   - A/B testing infrastructure
   - Rollback procedures

3. **Production preparation**
   - Full backup procedures
   - Monitoring dashboards
   - Alert configurations

### Phase 3: Production Migration (Week 6)
1. **Canary deployment**
   - Single instance with pyfuse3
   - Monitor for 24 hours
   - Gradual rollout to 50%

2. **Full migration**
   - Switch default to pyfuse3
   - Keep fusepy as fallback
   - Monitor for 1 week

3. **Cleanup (Week 7)**
   - Remove fusepy code
   - Update documentation
   - Archive migration artifacts

## Testing Strategy

### 1. Unit Testing
```python
# Test both backends identically
@pytest.mark.parametrize("backend", ["fusepy", "pyfuse3"])
def test_fuse_operations(backend):
    fuse = create_fuse_backend({"backend": backend})
    # Test all operations
```

### 2. Integration Testing
- Mount/unmount cycles
- File operations (CRUD)
- Historical views
- Shadow annotations
- Stream operations
- Expert agent access patterns

### 3. Performance Testing
```python
# Benchmark framework
class FUSEBenchmark:
    def benchmark_operation(self, backend, operation, iterations=1000):
        # Measure latency percentiles
        # Compare memory usage
        # Test concurrent operations
```

### 4. Multi-Agent Testing
- Expert registration with both backends
- Concurrent file access
- FUSE mount sharing
- Event synchronization

## Package Requirements

### Core Migration Packages
```txt
# requirements-migration.txt

# Current (to be phased out)
fusepy==3.0.1

# Target
pyfuse3==3.5.0  # Latest stable

# Testing
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-benchmark==4.0.0

# Monitoring
prometheus-client==0.20.0
```

### Optional Enhancement Packages
```txt
# requirements-optional.txt

# ML/Analysis (infrastructure recommendation)
scikit-learn==1.5.0
numpy==1.26.4
pandas==2.2.2

# Code Analysis
tree-sitter==0.22.3
tree-sitter-python==0.21.0
tree-sitter-javascript==0.21.0
tree-sitter-typescript==0.21.0

# Development Tools
black==24.4.2
mypy==1.10.0
ruff==0.4.10

# Performance Monitoring
py-spy==0.3.14
memory-profiler==0.61.0
```

### Container Package Strategy
```dockerfile
# Multi-stage Dockerfile snippet
FROM python:3.11-slim-bookworm AS base

# Install both FUSE libraries
RUN apt-get update && apt-get install -y \
    libfuse2 libfuse-dev \      # fusepy support
    libfuse3-3 libfuse3-dev \   # pyfuse3 support
    fuse fuse3 \
    && rm -rf /var/lib/apt/lists/*

# Runtime selection based on env var
ENV LIGHTHOUSE_FUSE_BACKEND=${LIGHTHOUSE_FUSE_BACKEND:-fusepy}
```

## Risk Assessment & Mitigation

### High-Risk Areas

1. **Async/Sync Impedance**
   - **Risk**: Performance degradation from sync/async conversion
   - **Mitigation**: Use thread pools for sync operations, native async where possible
   - **Fallback**: Immediate rollback to fusepy

2. **Container Compatibility**
   - **Risk**: libfuse3 permissions/capabilities differ
   - **Mitigation**: Extensive container testing, capability analysis
   - **Fallback**: Dual-container strategy

3. **Memory Model Differences**
   - **Risk**: pyfuse3 may have different memory characteristics
   - **Mitigation**: Memory profiling, leak detection
   - **Fallback**: Resource limits and monitoring

### Medium-Risk Areas

1. **Performance Characteristics**
   - Different caching behaviors
   - Threading vs async models
   - System call overhead

2. **Error Handling**
   - Different error codes
   - Exception hierarchies
   - Recovery patterns

### Low-Risk Areas

1. **Authentication** - Fully abstracted
2. **Event Store** - No direct interaction
3. **Business Logic** - Unchanged

## Rollback Strategy

### Immediate Rollback (< 5 minutes)
```bash
# Environment variable switch
export LIGHTHOUSE_FUSE_BACKEND=fusepy
# Restart containers
docker-compose restart bridge
```

### Feature Flag Rollback
```python
# Runtime switching without restart
if feature_flags.get('use_pyfuse3', False):
    backend = PyFuse3Backend()
else:
    backend = FusepyBackend()
```

### Data Recovery
- No data migration required (same underlying storage)
- Event store maintains consistency
- Replay events if needed

## Success Criteria

### Performance Metrics
- ✅ Maintain <5ms for common operations
- ✅ <10ms for large directory listings
- ✅ No increase in memory usage >10%
- ✅ CPU usage within 5% of baseline

### Functional Criteria
- ✅ All FUSE operations working
- ✅ Expert agents can access files
- ✅ Time-travel debugging functional
- ✅ Shadow annotations preserved
- ✅ Stream operations working

### Stability Criteria
- ✅ 99.9% uptime maintained
- ✅ No data loss incidents
- ✅ Graceful degradation on errors
- ✅ Clean unmount on shutdown

## Timeline & Milestones

| Week | Phase | Milestone | Success Criteria |
|------|-------|-----------|------------------|
| 1 | Preparation | Abstraction layer complete | Tests pass with fusepy |
| 2-3 | Implementation | pyfuse3 backend working | Feature parity achieved |
| 4 | Testing | Full test coverage | Both backends pass all tests |
| 5 | Staging | Staged rollout | 50% traffic on pyfuse3 |
| 6 | Production | Full migration | 100% on pyfuse3, stable |
| 7 | Cleanup | Legacy removal | fusepy code archived |

## Monitoring & Observability

### Key Metrics to Track
```python
# Metrics collection
metrics = {
    'fuse_operation_latency': Histogram(),
    'fuse_operation_errors': Counter(),
    'fuse_cache_hit_rate': Gauge(),
    'fuse_memory_usage': Gauge(),
    'fuse_backend_type': Info(),
}
```

### Dashboards Required
1. **Performance Dashboard**
   - Operation latency percentiles
   - Throughput by operation type
   - Cache effectiveness

2. **Health Dashboard**
   - Mount status
   - Error rates
   - Backend selection

3. **Comparison Dashboard**
   - Side-by-side backend metrics
   - A/B test results
   - Resource usage

## Documentation Requirements

1. **Migration Guide** - Step-by-step for operators
2. **API Differences** - For developers
3. **Troubleshooting Guide** - Common issues and solutions
4. **Performance Tuning** - Backend-specific optimizations

## Recommendations

### Immediate Actions
1. ✅ Create feature branch for migration work
2. ✅ Setup dual-library test containers
3. ✅ Implement abstraction layer
4. ✅ Create comprehensive test suite

### Strategic Considerations
1. Consider keeping dual-backend support permanently for flexibility
2. Use this migration to improve observability
3. Document patterns for future subsystem migrations
4. Consider contributing improvements back to pyfuse3

### Risk Management
- **Approved Risk Level**: MEDIUM (with mitigations in place)
- **Fallback Time**: < 5 minutes
- **Data Loss Risk**: NONE (event-sourced architecture)
- **Performance Risk**: LOW (with proper testing)

## Conclusion

The migration from fusepy to pyfuse3 is architecturally sound and achievable through the phased approach outlined. The abstraction layer pattern ensures we can maintain both implementations during transition, providing a safe rollback path. The async-native nature of pyfuse3 actually aligns better with Lighthouse's async architecture, potentially offering performance improvements once fully migrated.

The key to success will be thorough testing at each phase and maintaining the ability to quickly rollback if issues arise. With proper monitoring and the staged approach, this migration can be completed with minimal risk to the production system.