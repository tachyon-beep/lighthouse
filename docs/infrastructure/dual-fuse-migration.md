# Dual FUSE Backend Migration Infrastructure Guide

## Overview

This guide provides comprehensive infrastructure details for supporting both fusepy (FUSE2) and pyfuse3 (FUSE3) during the migration period.

## Container Architecture

### Multi-Stage Build Strategy

The `Dockerfile.dual-fuse` implements a 5-stage build:

1. **Builder Stage**: Compiles both FUSE backends with all dependencies
2. **Tester Stage**: Validates both backends work correctly
3. **Runtime Stage**: Production-ready image with both backends
4. **Development Stage**: Includes debugging and profiling tools
5. **Benchmark Stage**: Performance testing environment

### Image Size Optimization

During the dual-backend period, the image size will increase by approximately:
- Base image: ~150MB
- FUSE2 libraries: ~2MB
- FUSE3 libraries: ~3MB
- Python packages (both backends): ~45MB
- Total overhead: ~50MB (33% increase)

Optimization strategies:
- Multi-stage builds to exclude build dependencies
- Shared base layers between stages
- Alpine variants for smaller footprint (post-migration)
- Cleanup of unnecessary files in each stage

## Library Management

### Handling Dual FUSE Libraries

Both libfuse2 and libfuse3 can coexist:

```bash
# FUSE2 libraries
/usr/lib/x86_64-linux-gnu/libfuse.so.2
/usr/lib/x86_64-linux-gnu/libfuse.so.2.9.9

# FUSE3 libraries  
/usr/lib/x86_64-linux-gnu/libfuse3.so.3
/usr/lib/x86_64-linux-gnu/libfuse3.so.3.10.5
```

### LD_LIBRARY_PATH Configuration

```bash
# Environment variable configuration
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu:/usr/lib:$LD_LIBRARY_PATH"

# Runtime library resolution
ldconfig -p | grep fuse  # Verify both versions available
```

### Python Package Isolation

```python
# Backend selection at runtime
if os.environ.get("LIGHTHOUSE_ACTIVE_FUSE_BACKEND") == "fusepy":
    import fuse
    backend = FusePyBackend()
elif os.environ.get("LIGHTHOUSE_ACTIVE_FUSE_BACKEND") == "pyfuse3":
    import pyfuse3
    import trio
    backend = PyFuse3Backend()
```

## Runtime Configuration

### Environment Variables

```bash
# Backend Selection
LIGHTHOUSE_FUSE_BACKEND=fusepy      # Primary backend choice
LIGHTHOUSE_FUSE_FALLBACK=pyfuse3    # Fallback if primary fails

# Feature Flags
LIGHTHOUSE_FUSE_BENCHMARK=true      # Enable performance benchmarking
LIGHTHOUSE_FUSE_PARALLEL_TEST=true  # Run both backends in parallel
LIGHTHOUSE_FUSE_DEBUG=true          # Verbose FUSE logging

# Performance Tuning
LIGHTHOUSE_FUSE_MAX_READAHEAD=131072  # 128KB readahead buffer
LIGHTHOUSE_FUSE_MAX_WRITE=131072      # 128KB max write size
LIGHTHOUSE_CACHE_TTL=60               # Cache TTL in seconds
LIGHTHOUSE_CACHE_SIZE=10000           # Number of cached entries
```

### Dynamic Backend Selection Logic

```python
def select_fuse_backend():
    """Select appropriate FUSE backend based on availability"""
    
    primary = os.environ.get("LIGHTHOUSE_FUSE_BACKEND", "fusepy")
    fallback = os.environ.get("LIGHTHOUSE_FUSE_FALLBACK", "pyfuse3")
    
    # Try primary backend
    if check_backend_available(primary):
        return primary
    
    # Try fallback backend
    if check_backend_available(fallback):
        logger.warning(f"Primary backend {primary} unavailable, using {fallback}")
        return fallback
    
    # No backend available - degraded mode
    logger.error("No FUSE backend available, running in degraded mode")
    return None
```

## Testing Infrastructure

### Container-Based Testing

```yaml
# GitHub Actions workflow for dual-backend testing
name: Dual FUSE Backend Tests

on: [push, pull_request]

jobs:
  test-fusepy:
    runs-on: ubuntu-latest
    container:
      image: lighthouse:dual-fuse
      options: --cap-add SYS_ADMIN --device /dev/fuse
    env:
      LIGHTHOUSE_FUSE_BACKEND: fusepy
    steps:
      - name: Run fusepy tests
        run: |
          python -m pytest tests/fuse/ -m "not pyfuse3_only"
          
  test-pyfuse3:
    runs-on: ubuntu-latest
    container:
      image: lighthouse:dual-fuse
      options: --cap-add SYS_ADMIN --device /dev/fuse
    env:
      LIGHTHOUSE_FUSE_BACKEND: pyfuse3
    steps:
      - name: Run pyfuse3 tests
        run: |
          python -m pytest tests/fuse/ -m "not fusepy_only"
          
  test-compatibility:
    runs-on: ubuntu-latest
    container:
      image: lighthouse:dual-fuse
      options: --cap-add SYS_ADMIN --device /dev/fuse
    env:
      LIGHTHOUSE_FUSE_PARALLEL_TEST: true
    steps:
      - name: Run compatibility tests
        run: |
          python -m lighthouse.migration.validate_backends
```

### Performance Benchmarking

```python
# Benchmark configuration
BENCHMARK_SUITE = {
    "operations": [
        "mount",
        "unmount", 
        "read_small",  # <4KB files
        "read_large",  # >1MB files
        "write_small",
        "write_large",
        "stat",
        "readdir",
        "concurrent_reads",
        "concurrent_writes"
    ],
    "metrics": [
        "latency_p50",
        "latency_p95",
        "latency_p99",
        "throughput_mbps",
        "iops",
        "cpu_usage",
        "memory_usage"
    ],
    "iterations": 1000,
    "warmup": 100
}
```

### Parallel Testing Architecture

```
┌─────────────────┐     ┌─────────────────┐
│  Primary FUSE   │     │  Shadow FUSE    │
│  (fusepy)       │     │  (pyfuse3)      │
│  Port: 8765     │     │  Port: 8766     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ├───────────┬───────────┤
                     │
              ┌──────▼──────┐
              │  Comparator  │
              │  Service     │
              └─────────────┘
                     │
              ┌──────▼──────┐
              │   Results    │
              │   Analysis   │
              └─────────────┘
```

## CI/CD Pipeline

### Build Pipeline

```yaml
stages:
  - build
  - test
  - benchmark
  - deploy

build:dual-fuse:
  stage: build
  script:
    - docker build -f Dockerfile.dual-fuse --target runtime -t lighthouse:dual-fuse .
    - docker build -f Dockerfile.dual-fuse --target development -t lighthouse:dual-dev .
    - docker build -f Dockerfile.dual-fuse --target benchmark -t lighthouse:dual-bench .
  artifacts:
    reports:
      container_scanning: gl-container-scanning-report.json

test:unit:
  stage: test
  image: lighthouse:dual-dev
  script:
    - pytest tests/unit/ --cov=lighthouse --cov-report=xml
  coverage: '/TOTAL.*\s+(\d+%)$/'

test:integration:
  stage: test
  image: lighthouse:dual-fuse
  services:
    - docker:dind
  script:
    - docker-compose -f docker-compose.dual-fuse.yml up -d
    - sleep 10
    - pytest tests/integration/
  
benchmark:performance:
  stage: benchmark
  image: lighthouse:dual-bench
  script:
    - python -m lighthouse.benchmarks.full_suite
    - python -m lighthouse.benchmarks.compare_results
  artifacts:
    paths:
      - benchmarks/results/
    expire_in: 30 days
  only:
    - main
    - /^perf-.*$/

deploy:staging:
  stage: deploy
  script:
    - docker tag lighthouse:dual-fuse $REGISTRY/lighthouse:staging
    - docker push $REGISTRY/lighthouse:staging
  environment:
    name: staging
  only:
    - main
```

### Deployment Strategy

#### Phase 1: Parallel Deployment (Weeks 1-3)
```yaml
# Deploy both backends, fusepy as primary
environment:
  LIGHTHOUSE_FUSE_BACKEND: fusepy
  LIGHTHOUSE_FUSE_FALLBACK: pyfuse3
  LIGHTHOUSE_FUSE_PARALLEL_TEST: true
```

#### Phase 2: Canary Deployment (Weeks 4-5)
```yaml
# 10% traffic to pyfuse3
canary:
  weight: 10
  environment:
    LIGHTHOUSE_FUSE_BACKEND: pyfuse3
    
production:
  weight: 90
  environment:
    LIGHTHOUSE_FUSE_BACKEND: fusepy
```

#### Phase 3: Progressive Rollout (Week 6)
```yaml
# Increase pyfuse3 traffic gradually
canary:
  weight: 50  # Day 1: 50%
  # weight: 75  # Day 3: 75%
  # weight: 90  # Day 5: 90%
  environment:
    LIGHTHOUSE_FUSE_BACKEND: pyfuse3
```

#### Phase 4: Full Migration (Week 7)
```yaml
# All traffic to pyfuse3
environment:
  LIGHTHOUSE_FUSE_BACKEND: pyfuse3
  # Remove fusepy from image in next release
```

## Monitoring and Observability

### Metrics Collection

```python
# Prometheus metrics for dual-backend monitoring
from prometheus_client import Counter, Histogram, Gauge

# Backend-specific metrics
fuse_operations = Counter(
    'lighthouse_fuse_operations_total',
    'Total FUSE operations',
    ['backend', 'operation', 'status']
)

fuse_latency = Histogram(
    'lighthouse_fuse_operation_duration_seconds',
    'FUSE operation latency',
    ['backend', 'operation'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

fuse_backend_active = Gauge(
    'lighthouse_fuse_backend_active',
    'Currently active FUSE backend',
    ['backend']
)

# Comparison metrics
backend_divergence = Counter(
    'lighthouse_fuse_backend_divergence_total',
    'Operations where backends produced different results',
    ['operation', 'primary', 'shadow']
)
```

### Grafana Dashboards

```json
{
  "dashboard": {
    "title": "FUSE Backend Migration",
    "panels": [
      {
        "title": "Operations by Backend",
        "targets": [
          {
            "expr": "rate(lighthouse_fuse_operations_total[5m])"
          }
        ]
      },
      {
        "title": "Latency Comparison",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, lighthouse_fuse_operation_duration_seconds)"
          }
        ]
      },
      {
        "title": "Backend Divergence",
        "targets": [
          {
            "expr": "rate(lighthouse_fuse_backend_divergence_total[5m])"
          }
        ]
      }
    ]
  }
}
```

## Rollback Strategy

### Automatic Rollback Triggers

```python
# Health check with automatic rollback
def health_check():
    metrics = collect_metrics()
    
    # Rollback conditions
    if metrics['error_rate'] > 0.01:  # >1% errors
        return rollback_to_fusepy()
    
    if metrics['p99_latency'] > 1.0:  # >1s P99 latency
        return rollback_to_fusepy()
    
    if metrics['divergence_rate'] > 0.001:  # >0.1% divergence
        return rollback_to_fusepy()
    
    return "healthy"

def rollback_to_fusepy():
    os.environ['LIGHTHOUSE_FUSE_BACKEND'] = 'fusepy'
    restart_fuse_mount()
    alert_oncall("Rolled back to fusepy due to performance degradation")
    return "rollback"
```

### Manual Rollback Procedure

```bash
# Quick rollback via environment variable
docker exec lighthouse-bridge sh -c "
  export LIGHTHOUSE_FUSE_BACKEND=fusepy
  kill -HUP 1
"

# Full rollback with image swap
docker-compose down
docker-compose -f docker-compose.yml up -d  # Original fusepy-only compose
```

## Security Considerations

### Capability Management

```dockerfile
# Minimal capabilities for FUSE operation
RUN setcap cap_sys_admin+ep /opt/venv/bin/python

# Or at runtime
docker run --cap-drop=ALL --cap-add=SYS_ADMIN lighthouse:dual-fuse
```

### Seccomp Profiles

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "syscalls": [
    {
      "names": ["mount", "umount2"],
      "action": "SCMP_ACT_ALLOW",
      "args": [
        {
          "index": 2,
          "value": "fuse",
          "op": "SCMP_CMP_EQ"
        }
      ]
    }
  ]
}
```

## Post-Migration Cleanup

### Week 8 Tasks

1. Remove fusepy dependencies:
```dockerfile
# Remove from requirements
# fusepy==3.0.1  # REMOVED

# Remove FUSE2 libraries
RUN apt-get remove --purge libfuse2 fuse
```

2. Simplify Dockerfile:
```dockerfile
# Single-backend Dockerfile
FROM python:3.11-slim-bookworm
RUN apt-get install -y libfuse3-3 fuse3
# ... rest of simplified build
```

3. Update CI/CD:
```yaml
# Remove dual-backend tests
# Keep only pyfuse3 tests
```

4. Archive migration code:
```bash
git tag pre-pyfuse3-migration
git rm -r src/lighthouse/fuse/backends/fusepy/
git rm scripts/migration/
```

## Conclusion

This dual-FUSE infrastructure supports a safe, monitored migration from fusepy to pyfuse3 with:
- Zero-downtime deployment
- Automatic rollback on regression
- Comprehensive performance monitoring
- Parallel testing capabilities
- Gradual traffic shifting

The 50MB image size increase during migration is acceptable for the safety and validation benefits provided.