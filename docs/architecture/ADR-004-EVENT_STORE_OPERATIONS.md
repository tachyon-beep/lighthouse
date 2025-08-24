# ADR-004: Event Store Operations and Performance Architecture

**Status**: PROPOSED  
**Date**: 2025-01-24  
**Deciders**: infrastructure-architect  
**Technical Story**: [Phase 1: Event-Sourced Foundation](IMPLEMENTATION_SCHEDULE.md#phase-1-event-sourced-foundation)  
**Builds On**: [ADR-002](ADR-002-EVENT_STORE_DATA_ARCHITECTURE.md), [ADR-003](ADR-003-EVENT_STORE_SYSTEM_DESIGN.md), [ADR-001](ADR-001-EMERGENCY_DEGRADATION_MODE.md)

## Context and Problem Statement

Building on the foundational data architecture (ADR-002) and system design (ADR-003) decisions, Phase 1 implementation requires concrete operational and performance specifications. The event-sourced foundation must deliver production-ready performance, comprehensive failure handling, robust development infrastructure, and complete observability to serve as the bedrock for all subsequent Lighthouse phases.

**Critical Requirements**:
- Handle 10,000 events/second sustained with deterministic performance
- Comprehensive failure classification and automatic recovery procedures
- Production-ready development and testing infrastructure
- Complete observability with actionable alerting
- Integration with emergency degradation mode operational procedures

This ADR resolves all operational decisions needed to begin Phase 1 implementation with confidence.

---

## Performance Requirements and Validation Criteria

### Latency Requirements Per Operation

**Event Append Operations**:
- **p50 (median)**: ≤2ms per single event on SSD storage
- **p95**: ≤5ms per single event under normal load
- **p99**: ≤10ms per single event, ≤50ms for batch operations
- **p99.9**: ≤100ms (degradation threshold - triggers alerting)

**Event Query Operations**:
- **Single Event by ID**: p99 ≤1ms (index lookup)
- **Time Range Query**: p99 ≤100ms for 1,000 events
- **Complex Filter Query**: p99 ≤500ms for 10,000 events
- **Subscription Stream**: First event delivery ≤100ms after publication

**Event Replay Operations**:
- **Simple Replay**: 100,000 events replayed in ≤10 seconds
- **Filtered Replay**: Proportional performance based on filter selectivity
- **Streaming Replay**: Constant memory usage regardless of replay size
- **Checkpoint Resume**: Resume from checkpoint within ≤1 second

**Rationale**: These targets ensure Lighthouse coordination remains responsive under all anticipated load conditions. p99.9 thresholds provide early warning before user-visible degradation.

### Throughput Scaling Targets

**Events Per Second Per Core**:
- **Baseline Performance**: 2,500 events/sec/core (single-threaded writer)
- **Batch Performance**: 10,000 events/sec/core (optimal batch size ~100 events)
- **Read Performance**: 50,000 events/sec/core (memory cache hits)
- **Concurrent Reads**: Linear scaling with reader threads up to storage bandwidth

**Memory Usage Per 1000 Events**:
- **Event Storage**: ≤1MB average (1KB average event size)
- **Index Overhead**: ≤100KB (10% of event data)
- **Cache Memory**: ≤2MB (recent events + index cache)
- **Replay Memory**: ≤10MB maximum during streaming replay

**Storage Scaling**:
- **Growth Rate**: 100MB/day for typical agent activity (100K events/day)
- **Compression**: 60% reduction with gzip on archived logs
- **Compaction**: 30% size reduction with duplicate event removal
- **Total Overhead**: ≤25% including indices, snapshots, and metadata

**Validation Methodology**:
```python
# Performance test framework
async def test_throughput_scaling(core_count: int):
    # Start N writer threads
    # Measure sustained write rate for 10 minutes
    # Verify linear scaling up to storage limits
    # Confirm no memory leaks or resource exhaustion
    pass

async def test_memory_scaling(event_count: int):
    # Generate realistic event stream
    # Measure memory usage at intervals
    # Verify constant memory for streaming operations
    # Test memory cleanup after operations complete
    pass
```

### Load Testing Scenarios

**Single Agent Load Profile**:
- **Event Rate**: 100 events/minute steady state, 1,000 events/minute burst
- **Event Types**: 70% command validation, 20% state updates, 10% monitoring
- **Pattern**: Business hours (8-18h) activity with overnight quiet periods
- **Duration**: 72-hour sustained test with failure injection

**Multi-Agent Load Profile**:
- **Agent Count**: 5 concurrent agents (Phase 1 target)
- **Coordination Events**: 500 inter-agent events/hour
- **Peak Load**: 5,000 events/minute system-wide during active development
- **Stress Test**: 10 agents, 20,000 events/minute for 1 hour

**Burst vs Sustained Testing**:
- **Sustained Load**: Target rate maintained for 24 hours minimum
- **Burst Handling**: 10x normal rate for 5 minutes without data loss
- **Recovery Time**: Return to baseline performance within 30 seconds
- **Backpressure**: Graceful degradation under sustained overload

**Read vs Write Heavy Scenarios**:
- **Write Heavy**: 80% append operations, 20% queries (normal development)
- **Read Heavy**: 20% append operations, 80% queries (analysis/debugging)
- **Mixed Workload**: Realistic production ratios with subscription streams
- **Pathological**: All operations hitting worst-case performance paths

**Load Generation Framework**:
```python
class LoadGenerator:
    def generate_realistic_events(self, agent_count: int, duration: int):
        # Generate realistic event patterns
        # Business hours activity patterns
        # Burst and sustained load profiles
        # Coordinated multi-agent scenarios
        pass
    
    def validate_performance(self, results: LoadTestResults):
        # Verify all SLA requirements met
        # Check resource usage stays within bounds
        # Confirm no performance regressions
        pass
```

### Performance Regression Detection

**Automated Benchmark Suite**:
- **Benchmark Frequency**: Every commit to main branch
- **Test Suite Duration**: ≤10 minutes for CI integration
- **Performance Baseline**: Rolling 30-day average with seasonal adjustment
- **Regression Threshold**: 5% degradation triggers investigation, 15% blocks deployment

**CI/CD Integration**:
- **Pre-commit**: Synthetic load test (1 minute duration)
- **Post-merge**: Full benchmark suite in staging environment
- **Nightly**: Complete load test suite including failure scenarios
- **Release Gate**: Performance validation required for production deployment

**Benchmark Implementation**:
```yaml
performance_tests:
  - name: "single_event_append_latency"
    target_p99: "10ms"
    regression_threshold: "5%"
    test_duration: "60s"
    
  - name: "batch_throughput_scaling" 
    target_throughput: "10000/sec"
    regression_threshold: "10%"
    test_duration: "300s"
    
  - name: "query_response_time"
    target_p95: "100ms"
    regression_threshold: "15%"
    sample_queries: 100
```

**Regression Analysis**:
- **Statistical Significance**: 95% confidence interval for regression detection
- **Performance Attribution**: Git bisection for regression source identification
- **Resource Correlation**: CPU/memory usage correlation with performance changes
- **Alert Integration**: Automatic Slack/email alerts for confirmed regressions

### Resource Usage Monitoring

**Memory Leak Detection**:
- **Heap Growth**: Monitor RSS and heap size over extended runs
- **Detection Threshold**: >1% growth per hour under steady load
- **Memory Profiling**: Automatic heap dump on memory growth detection
- **Leak Prevention**: Mandatory weak references for event subscriptions

**File Descriptor Monitoring**:
- **FD Tracking**: Monitor open files, sockets, and database connections
- **Limit Management**: Stay below 75% of OS limits (ulimit -n)
- **Leak Detection**: Track FD lifecycle and detect unclosed resources
- **Resource Cleanup**: Automatic resource cleanup on component shutdown

**Storage Space Management**:
- **Disk Usage Alerts**: Warning at 80%, critical at 90% full
- **Growth Prediction**: Alert when current growth rate leads to full disk in 7 days
- **Automatic Cleanup**: Age-based log cleanup triggered by disk pressure
- **Archive Management**: Automatic compression and archive to secondary storage

**Resource Monitoring Implementation**:
```python
class ResourceMonitor:
    def __init__(self):
        self.metrics = MetricsCollector()
        
    async def monitor_memory(self):
        # Track RSS, heap, and object counts
        # Detect memory leaks via trend analysis
        # Generate heap dumps for investigation
        pass
        
    async def monitor_file_descriptors(self):
        # Track open files and sockets
        # Alert on resource leaks
        # Provide resource usage reports
        pass
        
    async def monitor_storage(self):
        # Track disk usage and growth rates
        # Predict storage exhaustion
        # Trigger automatic cleanup when needed
        pass
```

---

## Error Handling and Failure Mode Design

### Failure Classification System

**Recoverable Failures (Automatic Recovery)**:
- **Network Timeouts**: Temporary connection issues, retry with exponential backoff
- **Disk Full**: Automatic log cleanup and compaction, alert operators
- **Lock Contention**: Brief file system lock conflicts, retry with jitter
- **Validation Errors**: Schema validation failures, reject operation with detailed error
- **Rate Limiting**: Client throttling, implement backpressure signaling

**Human Intervention Required**:
- **Configuration Errors**: Invalid settings requiring admin correction
- **Permission Errors**: Filesystem permission issues requiring manual fix
- **Schema Migration**: Event schema evolution requiring careful migration
- **Capacity Planning**: Hardware resource exhaustion requiring scaling decisions
- **Security Incidents**: Authentication or authorization failures requiring investigation

**Restart Required (Critical Failures)**:
- **Memory Exhaustion**: Out-of-memory conditions that cannot be recovered
- **Corruption Detection**: Event log corruption requiring recovery from backup
- **System Resource Exhaustion**: OS-level resource limits exceeded
- **Deadlock Detection**: Thread deadlock requiring process restart
- **Critical Dependency Failure**: Core dependencies (filesystem, OS) failure

**Failure Classification Logic**:
```python
class FailureClassifier:
    def classify_error(self, error: Exception, context: dict) -> FailureClass:
        if isinstance(error, NetworkError) and error.is_temporary:
            return FailureClass.RECOVERABLE
        elif isinstance(error, PermissionError):
            return FailureClass.HUMAN_INTERVENTION
        elif isinstance(error, OutOfMemoryError):
            return FailureClass.RESTART_REQUIRED
        else:
            return self._analyze_error_context(error, context)
```

### Data Corruption Detection and Recovery

**Checksum Strategy**:
- **Event Checksums**: SHA-256 hash of each event payload
- **Block Checksums**: Rolling CRC32 for each 4KB file block
- **File Integrity**: Overall file hash computed during log rotation
- **Cross-validation**: Periodic verification of event checksums during reads

**Validation Frequency**:
- **Write-time**: Immediate checksum validation on every append
- **Read-time**: Checksum verification for events older than 24 hours
- **Background**: Complete log file validation during low-activity periods
- **Startup**: Fast integrity check of current log file on system startup

**Auto-repair Mechanisms**:
- **Single Event Corruption**: Skip corrupted event, continue reading
- **Block Corruption**: Attempt recovery from redundant metadata
- **Log File Corruption**: Truncate at last known good event
- **Index Corruption**: Rebuild index from event log contents

**Corruption Detection Implementation**:
```python
class IntegrityManager:
    async def validate_event(self, event_data: bytes) -> ValidationResult:
        # Verify event checksum
        # Check event structure and schema
        # Validate against sequence numbers
        return ValidationResult(is_valid=True, errors=[])
    
    async def repair_corruption(self, corruption: CorruptionReport):
        # Attempt automatic repair based on corruption type
        # Fall back to recovery from last good state
        # Generate detailed recovery report
        pass
```

### Network Partition Handling

**Split-brain Prevention**:
- **Single Writer**: Only one event store writer per deployment
- **Leadership Election**: Raft consensus for distributed deployments (future)
- **Fencing**: Automatic fencing of old leaders via file system locks
- **Client Validation**: Clients verify they're talking to current leader

**Quorum Requirements**:
- **Phase 1**: Single node deployment, no quorum needed
- **Future Phases**: 3-node minimum for distributed deployment
- **Write Quorum**: Majority (2/3) nodes must acknowledge writes
- **Read Quorum**: Single node for reads, majority for linearizable reads

**Conflict Resolution**:
- **Last Writer Wins**: Simple conflict resolution based on timestamps
- **Causal Ordering**: Vector clocks for distributed event ordering
- **Manual Resolution**: Human intervention for complex conflict scenarios
- **Rollback Capability**: Ability to roll back to pre-conflict state

**Network Partition Handling**:
```python
class PartitionManager:
    def detect_partition(self) -> PartitionStatus:
        # Monitor network connectivity
        # Detect loss of quorum
        # Identify partition boundaries
        pass
        
    def handle_split_brain(self, partition_info: PartitionInfo):
        # Fence minority partitions
        # Preserve data integrity
        # Plan recovery strategy
        pass
```

### Storage Failure Scenarios

**Disk Full Handling**:
- **Early Warning**: Alert at 80% disk usage
- **Emergency Cleanup**: Automatic cleanup of oldest archived logs
- **Write Blocking**: Block new writes when disk >95% full
- **Recovery**: Resume normal operation when disk <90% full

**Permission Errors**:
- **Detection**: Monitor for EPERM/EACCES errors
- **Diagnosis**: Report exact files and required permissions
- **Recovery**: Provide admin scripts for permission repair
- **Monitoring**: Track permission-related failures

**Filesystem Corruption**:
- **Detection**: Monitor for EIO errors and filesystem consistency
- **Isolation**: Isolate corrupted files from healthy data
- **Recovery**: Attempt recovery from backups or replicas
- **Fallback**: Operate from memory cache during filesystem repair

**Network Storage Issues**:
- **Timeout Handling**: Aggressive timeouts for network storage operations
- **Retry Logic**: Exponential backoff with maximum retry limits
- **Local Caching**: Cache frequently accessed data locally
- **Degradation**: Graceful degradation to read-only mode during network issues

**Storage Failure Recovery**:
```python
class StorageManager:
    def handle_disk_full(self):
        # Emergency log cleanup
        # Notify administrators
        # Enable write blocking
        pass
        
    def recover_from_corruption(self, corruption_info: CorruptionInfo):
        # Isolate corrupted data
        # Restore from backup
        # Validate recovery success
        pass
```

### Process Crash Recovery

**In-flight Operation Tracking**:
- **Operation Journal**: Log all operations before execution
- **Transaction Log**: Record operation start and completion
- **Recovery Log**: Track incomplete operations at startup
- **Cleanup Logic**: Clean up abandoned operations during recovery

**Partial Write Detection**:
- **Length Prefixing**: Every event record includes length header
- **Atomic Boundaries**: Detect partial writes by length mismatch
- **Recovery Strategy**: Truncate file at last complete record
- **Validation**: Verify recovered data integrity

**State Reconstruction Process**:
- **Event Replay**: Rebuild state from complete event history
- **Snapshot Recovery**: Start from latest snapshot, apply subsequent events
- **Consistency Checks**: Verify state consistency after reconstruction
- **Recovery Validation**: Test all operations after state recovery

**Crash Recovery Implementation**:
```python
class RecoveryManager:
    async def recover_from_crash(self):
        # Detect incomplete operations
        # Replay events from last checkpoint
        # Verify state consistency
        # Resume normal operation
        pass
        
    def cleanup_partial_writes(self, log_file_path: str):
        # Scan for incomplete records
        # Truncate at last valid record
        # Update indices accordingly
        pass
```

---

## Development and Testing Infrastructure

### Test Data Generation for Realistic Event Streams

**Realistic Event Pattern Generation**:
- **Agent Activity Simulation**: Model real agent work patterns and coordination
- **Command Validation Streams**: Realistic dangerous/safe command distributions
- **Temporal Patterns**: Business hours, timezone effects, seasonal variations
- **Event Type Distribution**: Representative mix of validation, coordination, monitoring events

**Scale Testing Data**:
- **Volume Generation**: Generate millions of events for performance testing
- **Historical Simulation**: Generate months of historical data for replay testing
- **Burst Pattern Simulation**: Create realistic traffic spikes and quiet periods
- **Multi-agent Coordination**: Generate complex inter-agent event sequences

**Event Generation Framework**:
```python
class EventDataGenerator:
    def generate_agent_session(self, agent_type: str, duration: timedelta) -> List[Event]:
        # Generate realistic agent activity patterns
        # Include coordination events, validation requests, status updates
        # Model real-world timing and dependencies
        pass
    
    def generate_validation_stream(self, danger_ratio: float) -> Iterator[Event]:
        # Generate realistic command validation requests
        # Mix of safe operations and dangerous patterns
        # Include edge cases and boundary conditions
        pass
        
    def generate_historical_data(self, months: int) -> EventStream:
        # Generate months of historical event data
        # Include system evolution over time
        # Model changing agent behaviors and system growth
        pass
```

**Data Characteristics**:
- **Event Size Distribution**: Realistic payload sizes (100B-10KB typical, some up to 1MB)
- **Timestamp Accuracy**: Microsecond precision with realistic clock skew
- **Correlation Patterns**: Proper event correlation IDs and causality chains
- **Error Scenarios**: Include invalid events for error handling testing

### Integration Test Strategy

**Docker-based Integration**:
- **Primary Strategy**: Full system testing in Docker containers
- **Benefits**: Complete isolation, reproducible environments, CI/CD integration
- **Components**: Event store, bridge server, mock agents, monitoring stack
- **Networking**: Realistic network latency and partition simulation

**Embedded Testing (Secondary)**:
- **Use Cases**: Fast unit tests, development iteration
- **In-memory Storage**: SQLite or in-memory event store for speed
- **Mock Services**: Lightweight mocks for external dependencies
- **Limitations**: Cannot test deployment-specific issues

**External Service Testing (Minimal)**:
- **Use Cases**: End-to-end validation, performance benchmarking
- **Real Infrastructure**: Testing against actual databases, file systems
- **Cost Management**: Minimal usage due to resource costs
- **Security**: Isolated test environments with no production data

**Integration Test Framework**:
```python
class IntegrationTestEnvironment:
    def __init__(self, strategy: TestStrategy):
        self.strategy = strategy
        
    async def setup_environment(self):
        if self.strategy == TestStrategy.DOCKER:
            await self.start_docker_compose()
        elif self.strategy == TestStrategy.EMBEDDED:
            await self.start_embedded_services()
        # Configure test environment
        pass
        
    async def run_test_suite(self, test_config: TestConfig):
        # Execute integration tests
        # Collect results and metrics
        # Clean up resources
        pass
```

**Test Environment Configurations**:
- **Development**: Fast startup, in-memory components, basic monitoring
- **CI/CD**: Full Docker stack, automated cleanup, result reporting
- **Staging**: Production-like environment, real persistence, full monitoring
- **Performance**: Optimized for benchmarking, detailed profiling enabled

### Performance Test Automation

**Load Generation Infrastructure**:
- **Multi-threaded Clients**: Concurrent load generation from multiple threads/processes
- **Realistic Workloads**: Load patterns matching production usage
- **Gradual Ramp-up**: Smooth load increases to find breaking points
- **Coordinated Testing**: Multiple load generators for distributed testing

**Regression CI/CD Pipeline**:
- **Automated Trigger**: Performance tests run on every main branch push
- **Baseline Comparison**: Compare results against historical performance
- **Regression Detection**: Statistical analysis to identify performance regressions
- **Failure Handling**: Block deployments on significant performance degradation

**Benchmark Storage and Analysis**:
- **Time Series Storage**: Store benchmark results with full context
- **Trend Analysis**: Identify long-term performance trends and capacity needs
- **Regression Attribution**: Link performance changes to specific code changes
- **Reporting**: Automated performance reports and dashboards

**Performance Test Pipeline**:
```yaml
performance_pipeline:
  triggers:
    - main_branch_push
    - nightly_schedule
    - release_candidate
    
  stages:
    - name: "quick_smoke_test"
      duration: "2min"
      blocking: true
      
    - name: "full_load_test" 
      duration: "30min"
      blocking: false
      
    - name: "endurance_test"
      duration: "4hours"
      schedule: "nightly"
      
  analysis:
    - regression_detection
    - capacity_planning
    - trend_analysis
```

### Mock and Stub Strategies

**Test-time Dependencies**:
- **File System**: In-memory filesystem for fast test execution
- **Network Services**: HTTP mocks for external API dependencies
- **Time Control**: Controllable time sources for timing-dependent tests
- **Agent Behavior**: Configurable agent simulators for coordination testing

**Production-like Fakes**:
- **Embedded Databases**: SQLite with same schema as production PostgreSQL
- **Memory Storage**: In-memory event store with identical API surface
- **Network Simulation**: Realistic latency and failure injection
- **Resource Limits**: Configurable resource constraints matching production

**Mock Framework**:
```python
class MockingFramework:
    def create_mock_agent(self, agent_type: str, behavior: AgentBehavior):
        # Create agent simulator with configurable behavior
        # Support realistic timing and failure patterns
        # Enable coordination testing scenarios
        pass
        
    def mock_external_service(self, service_name: str, responses: ResponsePattern):
        # Create HTTP mock with configured response patterns
        # Support failure injection and latency simulation
        # Track requests for verification
        pass
```

**Testing Without External Dependencies**:
- **Database Layer**: Abstract interface with in-memory and persistent implementations
- **File System**: Virtual file system for testing file operations
- **Network Calls**: Dependency injection for all external HTTP calls
- **Configuration**: Environment-based config with test overrides

### Development Environment Setup

**Local Development (Primary)**:
- **Docker Compose**: Complete local stack with one command startup
- **Hot Reloading**: Automatic code reload during development
- **Debug Support**: Integrated debugging with IDE support
- **Resource Efficiency**: Optimized for laptop development

**Shared Development (Secondary)**:
- **Remote Environments**: Cloud-based development environments
- **Resource Sharing**: Multiple developers sharing infrastructure costs
- **Consistency**: Identical environments across development team
- **Collaboration**: Easy sharing of development environments

**Ephemeral Instances (Specialized)**:
- **Feature Branches**: Temporary environments for feature development
- **PR Testing**: Automatic environment creation for pull request testing  
- **Load Testing**: Dedicated instances for performance testing
- **Cleanup**: Automatic destruction after use

**Development Environment Specification**:
```yaml
# docker-compose.dev.yml
version: '3.8'
services:
  event-store:
    build: .
    environment:
      - LOG_LEVEL=DEBUG
      - STORAGE_PATH=/tmp/events
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
    ports:
      - "8765:8765"
      
  monitoring:
    image: prom/prometheus
    ports:
      - "9090:9090"
      
  metrics:
    image: grafana/grafana
    ports:
      - "3000:3000"
```

**Environment Provisioning**:
- **Automated Setup**: Single script setup of complete development environment
- **Dependency Management**: Automatic installation of required tools and libraries
- **Configuration Management**: Environment-specific configuration management
- **Documentation**: Comprehensive setup documentation with troubleshooting

---

## Operational Monitoring and Observability

### Metrics Collection Strategy

**Primary: Prometheus with Custom Metrics**:
- **Rationale**: Industry standard, excellent alerting integration, powerful query language
- **Event Store Metrics**: Write latency, read throughput, error rates, queue depths
- **System Metrics**: CPU, memory, disk I/O, network utilization
- **Business Metrics**: Event types, agent activity, validation decisions

**Secondary: Built-in Metrics Collection**:
- **Application Metrics**: Custom performance counters and gauges
- **Health Metrics**: Component health status, dependency availability
- **Operational Metrics**: Configuration changes, admin actions, system events
- **Integration**: Export built-in metrics to Prometheus via /metrics endpoint

**Metrics Implementation**:
```python
from prometheus_client import Counter, Histogram, Gauge

# Event store metrics
events_appended = Counter('lighthouse_events_appended_total', 'Total events appended', ['agent_id', 'event_type'])
append_duration = Histogram('lighthouse_append_duration_seconds', 'Event append latency')
active_connections = Gauge('lighthouse_active_connections', 'Number of active client connections')
disk_usage = Gauge('lighthouse_disk_usage_bytes', 'Event log disk usage')

class MetricsCollector:
    def record_event_append(self, event: Event, duration: float):
        events_appended.labels(agent_id=event.agent_id, event_type=event.event_type).inc()
        append_duration.observe(duration)
        
    def update_system_metrics(self):
        active_connections.set(self.get_active_connection_count())
        disk_usage.set(self.get_disk_usage())
```

**Metric Categories**:
- **RED Metrics**: Request rate, Error rate, Duration
- **USE Metrics**: Utilization, Saturation, Errors for resources
- **SLI Metrics**: Service Level Indicators for availability and performance
- **Business Metrics**: Agent coordination success rates, validation accuracy

### Logging Format and Structured Data

**Primary Format: Structured JSON Logging**:
- **Benefits**: Machine parseable, searchable, rich context capture
- **Standard Fields**: timestamp, level, component, correlation_id, message
- **Context Fields**: agent_id, session_id, event_id, operation_type
- **Performance**: Minimal performance impact, efficient serialization

**Log Levels and Usage**:
- **ERROR**: System failures, data corruption, critical operational issues
- **WARN**: Recoverable failures, performance degradation, configuration issues
- **INFO**: Normal operations, state changes, important business events
- **DEBUG**: Detailed operation tracing, performance debugging

**Structured Logging Implementation**:
```python
import structlog

logger = structlog.get_logger("lighthouse.event_store")

class EventStoreLogger:
    def log_event_append(self, event: Event, result: AppendResult):
        logger.info(
            "event_appended",
            event_id=event.id,
            event_type=event.event_type,
            agent_id=event.agent_id,
            correlation_id=event.correlation_id,
            duration_ms=result.duration_ms,
            storage_size_bytes=result.storage_size
        )
        
    def log_error(self, error: Exception, context: dict):
        logger.error(
            "operation_failed",
            error_type=type(error).__name__,
            error_message=str(error),
            **context
        )
```

**Context Propagation**:
- **Correlation IDs**: Unique request identifiers propagated through all operations
- **Session Context**: Agent session information attached to all related logs
- **Operation Context**: Current operation type and parameters
- **Performance Context**: Timing information and resource usage

### Tracing Integration

**Primary: OpenTelemetry with W3C Trace Context**:
- **Standards Compliance**: W3C Trace Context for header propagation
- **Distributed Tracing**: Full request tracing across component boundaries
- **Performance Monitoring**: Detailed performance analysis with span timing
- **Integration**: Works with Jaeger, Zipkin, or cloud tracing services

**Sampling Strategy**:
- **Head-based Sampling**: Sample 10% of normal operations, 100% of errors
- **Adaptive Sampling**: Increase sampling during performance issues
- **Debug Sampling**: 100% sampling for specific agents or operations
- **Cost Management**: Balance observability with storage costs

**Correlation ID Propagation**:
- **HTTP Headers**: Automatic propagation via HTTP request headers
- **Event Metadata**: Correlation IDs embedded in event metadata
- **Log Context**: All logs include correlation ID for trace reconstruction
- **Cross-component**: Propagation across all Lighthouse components

**Tracing Implementation**:
```python
from opentelemetry import trace
from opentelemetry.propagate import extract, inject

tracer = trace.get_tracer("lighthouse.event_store")

class TracingEventStore:
    async def append_event(self, event: Event, headers: dict = None):
        # Extract trace context from incoming request
        context = extract(headers or {})
        
        with tracer.start_as_current_span("event_store.append", context=context) as span:
            span.set_attributes({
                "event.id": event.id,
                "event.type": event.event_type,
                "event.size": len(event.payload)
            })
            
            # Perform operation
            result = await self._append_event_impl(event)
            
            span.set_attributes({
                "operation.duration_ms": result.duration_ms,
                "operation.success": result.success
            })
            
            return result
```

### Health Check Endpoints Definition

**Primary Health Check: /health**:
- **Response Format**: JSON with component status and details
- **Check Types**: Basic connectivity, dependency availability, resource health
- **Response Time**: ≤100ms under normal conditions
- **Load Balancer Integration**: Standard HTTP 200/503 responses

**Detailed Health Check: /health/detailed**:
- **Extended Checks**: Performance validation, data consistency checks
- **Dependency Status**: Status of all external dependencies
- **Resource Metrics**: Current resource usage and capacity
- **Historical Health**: Recent health check history

**Component-Specific Checks: /health/{component}**:
- **Event Store**: Log file accessibility, index consistency, write performance
- **Storage**: Disk space, file permissions, I/O performance
- **Network**: Connectivity to dependencies, bandwidth availability
- **Memory**: Memory usage, leak detection, garbage collection health

**Health Check Implementation**:
```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

class HealthChecker:
    async def check_event_store(self) -> HealthStatus:
        # Test event append operation
        # Check log file accessibility  
        # Verify index consistency
        return HealthStatus(
            component="event_store",
            status="healthy",
            last_check=datetime.now(),
            details={"write_latency_ms": 2.3, "disk_usage_percent": 45}
        )

@app.get("/health")
async def health_check():
    checker = HealthChecker()
    
    # Run all health checks
    checks = await asyncio.gather(
        checker.check_event_store(),
        checker.check_storage(),
        checker.check_dependencies()
    )
    
    # Determine overall health
    overall_status = "healthy" if all(c.status == "healthy" for c in checks) else "unhealthy"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "checks": [c.dict() for c in checks]
    }
```

### Alerting Integration and Escalation

**Primary: PagerDuty Integration**:
- **Critical Alerts**: Data loss, service unavailable, security incidents
- **Escalation Policy**: Immediate page → 15min escalation → Manager escalation
- **Alert Correlation**: Group related alerts to prevent alert storms
- **Runbook Integration**: Link alerts to specific troubleshooting procedures

**Secondary: Slack Integration**:
- **Warning Alerts**: Performance degradation, resource pressure, configuration issues
- **Team Channels**: Route alerts to appropriate team channels
- **Context**: Rich alert messages with links to dashboards and logs
- **Threading**: Thread related alerts to reduce channel noise

**Alert Fatigue Prevention**:
- **Alert Tuning**: Regular review and adjustment of alert thresholds
- **Smart Grouping**: Group related alerts by root cause
- **Suppression**: Automatic suppression of downstream alerts
- **Snoozing**: Temporary suppression for known maintenance

**Escalation Implementation**:
```python
class AlertManager:
    def __init__(self):
        self.pagerduty_client = PagerDutyClient()
        self.slack_client = SlackClient()
        
    async def send_critical_alert(self, alert: Alert):
        # Send to PagerDuty immediately
        await self.pagerduty_client.trigger_incident(
            summary=alert.summary,
            severity="critical",
            details=alert.details,
            dedup_key=alert.dedup_key
        )
        
        # Also send to Slack for team awareness
        await self.slack_client.send_message(
            channel="#lighthouse-alerts",
            message=f"🚨 CRITICAL: {alert.summary}",
            thread_ts=alert.correlation_id
        )
    
    async def send_warning_alert(self, alert: Alert):
        # Send only to Slack for warnings
        await self.slack_client.send_message(
            channel="#lighthouse-warnings", 
            message=f"⚠️ WARNING: {alert.summary}\nDetails: {alert.details}"
        )
```

**Alert Categories**:
- **P1 Critical**: Service down, data loss, security breach (immediate page)
- **P2 High**: Performance degradation, partial outage (15min delay)
- **P3 Medium**: Resource pressure, configuration drift (1 hour delay)
- **P4 Low**: Information only, trend alerts (daily digest)

---

## Integration with Emergency Degradation Mode

### Degradation Detection through Event Store Health

**Health Metric Thresholds**:
- **Write Latency**: p99 >100ms triggers warning, >1000ms triggers degradation
- **Error Rate**: >1% write failures triggers warning, >5% triggers degradation
- **Storage Space**: >90% full triggers warning, >95% triggers degradation
- **Memory Usage**: >90% triggers warning, >95% triggers degradation

**Detection Implementation**:
```python
class DegradationDetector:
    def __init__(self):
        self.thresholds = {
            'write_latency_p99_ms': {'warning': 100, 'critical': 1000},
            'write_error_rate': {'warning': 0.01, 'critical': 0.05},
            'storage_usage_percent': {'warning': 90, 'critical': 95},
            'memory_usage_percent': {'warning': 90, 'critical': 95}
        }
    
    async def check_degradation_triggers(self) -> DegradationStatus:
        metrics = await self.collect_current_metrics()
        
        for metric_name, value in metrics.items():
            threshold = self.thresholds.get(metric_name)
            if threshold and value > threshold['critical']:
                return DegradationStatus.EMERGENCY_REQUIRED
            elif threshold and value > threshold['warning']:
                return DegradationStatus.WARNING
                
        return DegradationStatus.HEALTHY
```

**Automated Degradation Triggers**:
- **Performance Degradation**: Automatic degradation when SLAs are consistently missed
- **Resource Exhaustion**: Immediate degradation when system resources are critically low
- **Data Integrity**: Emergency degradation if data corruption is detected
- **Dependency Failure**: Degradation when critical dependencies are unavailable

### Event Store Operations During Degradation

**Degraded Mode Operations**:
- **Critical Writes Only**: Only emergency events and degradation state changes
- **Read-Only Mode**: All query operations continue normally
- **Cache Fallback**: Recent events served from memory cache
- **Simplified Validation**: Reduced validation complexity to save resources

**Operation Restrictions**:
```python
class DegradedEventStore:
    def __init__(self, degradation_level: DegradationLevel):
        self.degradation_level = degradation_level
        self.allowed_event_types = self._get_allowed_event_types()
    
    async def append_event(self, event: Event) -> AppendResult:
        if self.degradation_level >= DegradationLevel.EMERGENCY:
            if event.event_type not in self.allowed_event_types:
                raise DegradationError(f"Event type {event.event_type} blocked during degradation")
        
        # Proceed with simplified append process
        return await self._degraded_append(event)
    
    def _get_allowed_event_types(self) -> Set[str]:
        if self.degradation_level >= DegradationLevel.EMERGENCY:
            return {"SystemDegradationDetected", "DegradationRecovery", "EmergencyOperation"}
        return set()  # No restrictions for warning level
```

**Performance During Degradation**:
- **Reduced Batch Sizes**: Smaller batch sizes to reduce memory pressure
- **Simplified Indexing**: Disable complex indices during degradation
- **Cache Limits**: Reduced cache sizes to free memory
- **Background Tasks**: Suspend non-essential background processing

### Recovery State Synchronization

**State Reconciliation Process**:
1. **Compare States**: Compare event store state with bridge server memory state
2. **Identify Conflicts**: Find events that differ between systems
3. **Resolve Conflicts**: Apply conflict resolution rules (timestamp-based)
4. **Validate Consistency**: Ensure recovered state meets invariants

**Recovery Implementation**:
```python
class RecoveryManager:
    async def reconcile_degradation_state(self, 
                                        stored_events: List[Event],
                                        memory_events: List[Event]) -> ReconciliationResult:
        # Find events that exist in memory but not in storage
        memory_only = self._find_memory_only_events(stored_events, memory_events)
        
        # Find conflicting events (same ID, different content)
        conflicts = self._find_conflicting_events(stored_events, memory_events)
        
        # Apply conflict resolution
        resolved_events = []
        for conflict in conflicts:
            resolved = self._resolve_conflict(conflict.stored, conflict.memory)
            resolved_events.append(resolved)
        
        # Append missing events to storage
        for event in memory_only:
            await self.event_store.append_event(event)
        
        return ReconciliationResult(
            conflicts_resolved=len(conflicts),
            events_recovered=len(memory_only),
            success=True
        )
    
    def _resolve_conflict(self, stored_event: Event, memory_event: Event) -> Event:
        # Timestamp-based resolution with manual override capability
        if stored_event.timestamp > memory_event.timestamp:
            return stored_event
        return memory_event
```

**Consistency Validation**:
- **Invariant Checks**: Verify system invariants after recovery
- **Cross-Reference Validation**: Ensure event correlations are maintained
- **Agent State Validation**: Verify agent states are consistent with events
- **Performance Validation**: Confirm system performance after recovery

### Degradation Event Recording

**Degradation Event Schema**:
```python
class DegradationEvent(Event):
    event_type: Literal["SystemDegradation"] = "SystemDegradation"
    
    class DegradationData(BaseModel):
        degradation_level: str  # "warning", "critical", "emergency"
        trigger_reason: str     # "write_latency", "disk_full", "memory_exhaustion"
        trigger_metrics: dict   # Actual metric values that triggered degradation
        affected_components: List[str]  # Components affected by degradation
        mitigation_actions: List[str]   # Actions taken to mitigate
        estimated_recovery_time: Optional[int]  # Estimated recovery time in seconds
        
    data: DegradationData
```

**Priority Event Handling**:
- **Bypass Normal Queue**: Degradation events skip normal event processing queue
- **Immediate Write**: Force immediate write to storage with fsync
- **Replication**: Replicate degradation events to all monitoring systems
- **Notification**: Immediate notification to all monitoring endpoints

**Recovery Event Tracking**:
```python
class RecoveryEventManager:
    async def record_degradation_start(self, trigger: DegradationTrigger):
        event = DegradationEvent(
            event_id=generate_event_id(),
            timestamp=time.time_ns(),
            data=DegradationData(
                degradation_level="emergency",
                trigger_reason=trigger.reason,
                trigger_metrics=trigger.metrics,
                affected_components=trigger.affected_components,
                mitigation_actions=["readonly_mode", "cache_enabled"]
            )
        )
        
        # High-priority write that bypasses normal processing
        await self.event_store.append_priority_event(event)
    
    async def record_recovery_complete(self, recovery_info: RecoveryInfo):
        event = DegradationEvent(
            event_type="SystemRecovery",
            data=RecoveryData(
                recovery_duration_seconds=recovery_info.duration,
                events_recovered=recovery_info.events_recovered,
                conflicts_resolved=recovery_info.conflicts_resolved,
                final_state="operational"
            )
        )
        
        await self.event_store.append_event(event)
```

---

## Implementation Validation and Success Criteria

### Phase 1 Validation Framework

**Performance Validation**:
- [ ] Sustained 10,000 events/second for 1 hour with zero data loss
- [ ] p99 append latency ≤10ms under normal load
- [ ] p99 query latency ≤100ms for 1,000 event ranges
- [ ] Replay 100,000 events in ≤10 seconds
- [ ] Memory usage remains stable during extended operation

**Failure Mode Validation**:
- [ ] System survives kill -9 without data loss or corruption
- [ ] Automatic recovery from disk full conditions
- [ ] Graceful handling of network partitions and timeouts
- [ ] Corruption detection and automatic repair
- [ ] Process crash recovery maintains event ordering

**Operations Validation**:
- [ ] Complete observability with <2% monitoring overhead
- [ ] Alert fatigue rate <5% false positives
- [ ] Health checks respond in ≤100ms
- [ ] Degradation mode activates within 30 seconds of trigger
- [ ] Recovery procedures complete within documented time limits

**Integration Validation**:
- [ ] Current bridge functionality preserved
- [ ] Agent coordination patterns work correctly
- [ ] Emergency degradation coordinates across components
- [ ] Development environment setup in ≤10 minutes

### Acceptance Testing Strategy

**Functional Acceptance**:
```python
class AcceptanceTestSuite:
    async def test_event_sourcing_foundation(self):
        # Test complete event sourcing workflow
        # Validate state reconstruction accuracy
        # Confirm deterministic replay behavior
        pass
    
    async def test_multi_agent_coordination(self):
        # Test 5 agents coordinating through event store
        # Validate event ordering across agents
        # Confirm coordination patterns work correctly
        pass
    
    async def test_failure_recovery(self):
        # Test all failure modes and recovery procedures
        # Validate data integrity after failures
        # Confirm recovery time limits met
        pass
```

**Performance Acceptance**:
- **Load Testing**: Sustained production load for 24 hours
- **Stress Testing**: 10x normal load until breaking point identified
- **Endurance Testing**: 72-hour continuous operation
- **Recovery Testing**: Recovery time validation for all failure modes

**Operational Acceptance**:
- **Monitoring Validation**: All metrics collected and alerts functional
- **Documentation Validation**: Complete operational documentation
- **Training Validation**: Operations team successfully completes emergency procedures
- **Automation Validation**: All deployment and recovery procedures automated

### Deployment Readiness Checklist

**Infrastructure Readiness**:
- [ ] Production environment provisioned and tested
- [ ] Monitoring stack deployed and configured
- [ ] Backup and recovery procedures tested
- [ ] Security configuration validated
- [ ] Performance baseline established

**Operational Readiness**:
- [ ] Operations team trained on all procedures
- [ ] Emergency contact procedures established
- [ ] Runbooks complete and tested
- [ ] Change management procedures defined
- [ ] Rollback procedures tested

**Code Quality**:
- [ ] 95% test coverage for all critical paths
- [ ] Security review completed
- [ ] Performance review completed
- [ ] Documentation review completed
- [ ] Code review by senior engineers

---

## Consequences and Next Actions

### Positive Consequences

**Operational Excellence**:
- Production-ready performance and reliability from Phase 1 deployment
- Complete observability enabling proactive issue detection and resolution
- Comprehensive failure handling reducing operational burden
- Automated testing preventing performance regressions

**Development Velocity**:
- Robust development infrastructure enabling rapid iteration
- Comprehensive test coverage providing confidence in changes
- Clear operational procedures reducing deployment risks
- Performance validation preventing scalability issues

**System Reliability**:
- Multiple layers of failure detection and recovery
- Integration with emergency degradation mode ensuring system stability
- Resource monitoring preventing resource exhaustion issues
- Data integrity guarantees preserving system consistency

### Implementation Risks and Mitigation

**Performance Risk: Real-world Performance Differs from Testing**:
- **Mitigation**: Comprehensive load testing with realistic data patterns
- **Monitoring**: Continuous performance monitoring in production
- **Response**: Performance regression detection and rollback capability

**Operational Risk: Complex Failure Scenarios Not Covered**:
- **Mitigation**: Chaos engineering testing and failure injection
- **Documentation**: Comprehensive failure mode documentation and procedures
- **Training**: Regular failure scenario drills for operations team

**Development Risk: Testing Infrastructure Becomes Bottleneck**:
- **Mitigation**: Parallel test execution and resource optimization
- **Monitoring**: Test execution time tracking and optimization
- **Scaling**: On-demand test environment provisioning

### Next Actions for Implementation

**Immediate Actions (Week 1)**:
1. **Create Performance Test Framework**: Implement load generation and benchmarking
2. **Design Error Classification System**: Define failure categories and recovery procedures  
3. **Setup Development Environment**: Docker compose with complete monitoring stack
4. **Initialize Monitoring Infrastructure**: Prometheus, Grafana, and alerting setup

**Phase 1.1 Actions (Weeks 2-3)**:
1. **Implement Core Event Store**: Basic append and read operations with performance targets
2. **Add Failure Detection**: Error classification and automatic recovery logic
3. **Create Health Checks**: Comprehensive health monitoring endpoints
4. **Setup CI/CD Pipeline**: Automated testing with performance regression detection

**Phase 1.2 Actions (Weeks 4-5)**:
1. **Build Replay Engine**: State reconstruction with performance optimization
2. **Add Degradation Integration**: Emergency mode detection and handling
3. **Implement Observability**: Complete metrics, logging, and tracing
4. **Performance Optimization**: Achieve all performance targets under load

**Phase 1.3 Actions (Weeks 6-7)**:
1. **Complete API Surface**: WebSocket subscriptions and query API
2. **Finalize Testing**: Complete integration and performance test suite
3. **Documentation**: Operational runbooks and troubleshooting guides
4. **Deployment Readiness**: Production deployment validation and procedures

---

**Decision Authority**: infrastructure-architect  
**Implementation Timeline**: 7 weeks with parallel development and testing  
**Success Validation**: All performance and operational criteria met before Phase 2 begins

This ADR provides the complete operational foundation for Phase 1 implementation, ensuring production-ready performance, comprehensive failure handling, and operational excellence from the first deployment.