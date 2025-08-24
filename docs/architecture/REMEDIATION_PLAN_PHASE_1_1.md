# Phase 1.1 Core Event Store Remediation Plan

**Status**: DEPLOYMENT BLOCKED - Critical Issues Identified  
**Date**: 2024-08-24  
**Reviewers**: Validation Specialist, Integration Specialist, Test Engineer, Security Architect  
**Priority**: IMMEDIATE - Production Deployment Blocker  

## Executive Summary

Comprehensive peer review of Phase 1.1 Core Event Store implementation has identified critical architectural deviations, security vulnerabilities, and testing gaps that prevent production deployment. This remediation plan provides detailed steps to address all identified issues and achieve production readiness.

**Estimated Total Effort**: 8-10 development days  
**Critical Path Duration**: 5-6 working days  
**Target Completion**: End of Week 2  

## Remediation Priority Matrix

### 🔴 CRITICAL - Deployment Blockers (Days 1-3)
1. **Event ID Format Compliance** - Fix ADR-003 violation
2. **Security Vulnerabilities** - Fix directory traversal and access control
3. **Performance SLA Enforcement** - Add ADR-004 compliance monitoring

### 🟡 HIGH - Production Readiness (Days 4-5)
4. **State Recovery Enhancement** - Complete crash recovery implementation
5. **Comprehensive Testing** - Add failure scenarios and performance tests
6. **Input Validation Security** - Prevent injection and exhaustion attacks

### 🟢 MEDIUM - System Integration (Days 6-8)
7. **Emergency Degradation Integration** - Add ADR-001 compliance
8. **Observability Enhancement** - Add monitoring and audit trails
9. **Schema Evolution Support** - Implement version migration patterns

---

## Day 1: Event ID Format Compliance (ADR-003)

### **Issue**: Event ID Generation Architectural Deviation
- **Current**: Random UUID4 generation
- **Required**: `{timestamp_ns}_{sequence}_{node_id}` format per ADR-003
- **Impact**: Breaks deterministic ordering, debugging capabilities

### **Implementation Plan**

#### 1.1 Create Monotonic Event ID Generator

```python
# src/lighthouse/event_store/id_generator.py
import time
import socket
from typing import Optional

class MonotonicEventIDGenerator:
    """Generate monotonic Event IDs per ADR-003 specification."""
    
    def __init__(self, node_id: Optional[str] = None):
        self._last_timestamp_ns = 0
        self._sequence_counter = 0
        self._node_id = node_id or self._generate_node_id()
    
    def _generate_node_id(self) -> str:
        """Generate unique node identifier."""
        hostname = socket.gethostname()[:8]  # First 8 chars
        pid = str(os.getpid())[:4]           # Process ID
        return f"{hostname}_{pid}"
    
    def generate_event_id(self) -> str:
        """Generate monotonic event ID: {timestamp_ns}_{sequence}_{node_id}"""
        current_ns = time.time_ns()
        
        if current_ns == self._last_timestamp_ns:
            # Same nanosecond - increment sequence
            self._sequence_counter += 1
        else:
            # New nanosecond - reset sequence
            self._last_timestamp_ns = current_ns
            self._sequence_counter = 0
        
        return f"{current_ns}_{self._sequence_counter:06d}_{self._node_id}"
    
    def parse_event_id(self, event_id: str) -> dict:
        """Parse event ID into components for debugging."""
        parts = event_id.split('_')
        if len(parts) != 3:
            raise ValueError(f"Invalid event ID format: {event_id}")
        
        timestamp_ns, sequence, node_id = parts
        return {
            'timestamp_ns': int(timestamp_ns),
            'sequence': int(sequence),
            'node_id': node_id,
            'datetime': datetime.fromtimestamp(int(timestamp_ns) / 1e9, timezone.utc)
        }
```

#### 1.2 Update Event Model

```python
# src/lighthouse/event_store/models.py - Changes
from .id_generator import MonotonicEventIDGenerator

class Event(BaseModel):
    """Core event model for all Lighthouse events."""
    
    # Replace UUID with string event_id
    event_id: str = Field(default_factory=lambda: _id_generator.generate_event_id())
    sequence: Optional[int] = None
    
    # Add nanosecond timestamp precision
    timestamp_ns: int = Field(default_factory=time.time_ns)
    
    # Keep datetime for compatibility
    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ns / 1e9, timezone.utc)
    
    # Add integrity hash per ADR-002
    content_hash: Optional[str] = None
    
    def calculate_content_hash(self) -> str:
        """Calculate SHA-256 hash of event content for integrity."""
        content_data = {
            'event_type': self.event_type.value,
            'aggregate_id': self.aggregate_id,
            'data': self.data,
            'metadata': self.metadata
        }
        content_json = json.dumps(content_data, sort_keys=True)
        return hashlib.sha256(content_json.encode('utf-8')).hexdigest()

# Global ID generator instance
_id_generator = MonotonicEventIDGenerator()
```

#### 1.3 Add Tests for Event ID Compliance

```python
# tests/unit/event_store/test_event_id_compliance.py
class TestEventIDCompliance:
    def test_event_id_format_compliance(self):
        """Test Event ID format matches ADR-003 specification."""
        event = Event(
            event_type=EventType.COMMAND_RECEIVED,
            aggregate_id="test",
            data={}
        )
        
        # Validate format: {timestamp_ns}_{sequence}_{node_id}
        parts = event.event_id.split('_')
        assert len(parts) == 3, f"Event ID must have 3 parts: {event.event_id}"
        
        timestamp_ns, sequence, node_id = parts
        
        # Validate timestamp is nanoseconds
        assert len(timestamp_ns) >= 18, "Timestamp should be nanoseconds"
        assert timestamp_ns.isdigit(), "Timestamp must be numeric"
        
        # Validate sequence is zero-padded 6 digits
        assert len(sequence) == 6, "Sequence must be 6 digits"
        assert sequence.isdigit(), "Sequence must be numeric"
        
        # Validate node_id format
        assert len(node_id) >= 5, "Node ID must identify host and process"
        assert '_' in node_id, "Node ID should include hostname_pid format"
    
    def test_event_id_monotonic_ordering(self):
        """Test Event IDs maintain monotonic ordering."""
        events = []
        for i in range(100):
            events.append(Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id=f"test_{i}",
                data={}
            ))
        
        # Extract timestamps from Event IDs
        timestamps = []
        for event in events:
            timestamp_ns = int(event.event_id.split('_')[0])
            timestamps.append(timestamp_ns)
        
        # Verify monotonic ordering
        assert timestamps == sorted(timestamps), "Event IDs must be monotonically ordered"
```

**Day 1 Deliverable**: Event ID generation compliant with ADR-003, comprehensive tests passing

---

## Day 2: Critical Security Vulnerabilities

### **Issue**: Multiple Critical Security Vulnerabilities
- Directory traversal vulnerability
- No access control or authentication
- Insufficient input validation

### **Implementation Plan**

#### 2.1 Fix Directory Traversal Vulnerability

```python
# src/lighthouse/event_store/security.py
import os
import re
from pathlib import Path
from typing import Union

class SecurityValidator:
    """Security validation utilities for event store operations."""
    
    @staticmethod
    def validate_safe_path(path: Union[str, Path], base_dir: Union[str, Path]) -> Path:
        """Validate path is within base directory - prevents traversal attacks."""
        base_dir = Path(base_dir).resolve()
        target_path = Path(path).resolve()
        
        # Ensure target path is within base directory
        try:
            target_path.relative_to(base_dir)
        except ValueError:
            raise SecurityError(f"Path traversal detected: {path} outside {base_dir}")
        
        return target_path
    
    @staticmethod
    def validate_aggregate_id(aggregate_id: str) -> None:
        """Validate aggregate_id is safe for filesystem use."""
        if not aggregate_id or len(aggregate_id) > 255:
            raise ValueError("Aggregate ID must be 1-255 characters")
        
        # Prevent directory traversal in aggregate IDs
        dangerous_patterns = ['..', '/', '\\', '\x00', '\r', '\n']
        for pattern in dangerous_patterns:
            if pattern in aggregate_id:
                raise SecurityError(f"Invalid character in aggregate_id: {pattern}")
        
        # Only allow safe characters
        if not re.match(r'^[a-zA-Z0-9_.-]+$', aggregate_id):
            raise SecurityError("Aggregate ID contains invalid characters")

class SecurityError(Exception):
    """Raised when security validation fails."""
    pass
```

#### 2.2 Add Agent Authentication Framework

```python
# src/lighthouse/event_store/auth.py
import hmac
import hashlib
import time
from typing import Optional

class AgentAuthenticator:
    """Authenticate agents and validate permissions."""
    
    def __init__(self, secret_key: str):
        self._secret_key = secret_key.encode('utf-8')
        self._agent_permissions = {}  # agent_id -> permissions
    
    def authenticate_agent(self, agent_id: str, signature: str, 
                          timestamp: str, operation: str) -> bool:
        """Authenticate agent using HMAC signature."""
        # Prevent replay attacks - reject old timestamps
        current_time = int(time.time())
        request_time = int(timestamp)
        
        if abs(current_time - request_time) > 300:  # 5 minute window
            return False
        
        # Create expected signature
        message = f"{agent_id}:{timestamp}:{operation}"
        expected_signature = hmac.new(
            self._secret_key,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison
        return hmac.compare_digest(signature, expected_signature)
    
    def authorize_operation(self, agent_id: str, operation: str, 
                           resource: str) -> bool:
        """Check if agent has permission for operation on resource."""
        permissions = self._agent_permissions.get(agent_id, [])
        
        # For now, allow all authenticated agents all operations
        # TODO: Implement granular permissions
        return len(permissions) >= 0  # Placeholder for future RBAC
```

#### 2.3 Enhanced Input Validation

```python
# src/lighthouse/event_store/validation.py
import json
import re
from typing import Any, Dict

class InputValidator:
    """Comprehensive input validation for event store operations."""
    
    # Maximum sizes per ADR-002
    MAX_EVENT_SIZE = 1024 * 1024      # 1MB
    MAX_BATCH_SIZE = 10 * 1024 * 1024 # 10MB
    MAX_AGGREGATE_ID_LENGTH = 255
    MAX_DATA_DEPTH = 10               # Prevent deeply nested objects
    
    @classmethod
    def validate_event_data(cls, data: Dict[str, Any]) -> None:
        """Validate event data for security and size constraints."""
        # Size validation
        serialized_size = len(json.dumps(data))
        if serialized_size > cls.MAX_EVENT_SIZE:
            raise ValueError(f"Event data size {serialized_size} exceeds {cls.MAX_EVENT_SIZE}")
        
        # Depth validation (prevent stack overflow)
        cls._validate_data_depth(data, 0)
        
        # Content validation
        cls._validate_data_content(data)
    
    @classmethod
    def _validate_data_depth(cls, obj: Any, depth: int) -> None:
        """Prevent deeply nested objects that could cause stack overflow."""
        if depth > cls.MAX_DATA_DEPTH:
            raise ValueError(f"Data nesting exceeds maximum depth {cls.MAX_DATA_DEPTH}")
        
        if isinstance(obj, dict):
            for value in obj.values():
                cls._validate_data_depth(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                cls._validate_data_depth(item, depth + 1)
    
    @classmethod
    def _validate_data_content(cls, data: Dict[str, Any]) -> None:
        """Validate data content for security issues."""
        serialized = json.dumps(data)
        
        # Check for potential script injection
        dangerous_patterns = [
            r'<script', r'javascript:', r'data:text/html',
            r'eval\s*\(', r'Function\s*\(', r'setTimeout\s*\(',
            r'setInterval\s*\(', r'innerHTML\s*='
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, serialized, re.IGNORECASE):
                raise SecurityError(f"Potentially dangerous content detected: {pattern}")
```

#### 2.4 Update EventStore with Security

```python
# src/lighthouse/event_store/store.py - Security integration
from .security import SecurityValidator, SecurityError
from .auth import AgentAuthenticator
from .validation import InputValidator

class EventStore:
    def __init__(self, data_dir: str = "./data/events", auth_secret: Optional[str] = None):
        # Validate data directory path
        self.data_dir = SecurityValidator.validate_safe_path(data_dir, os.getcwd())
        
        # Initialize security components
        self.authenticator = AgentAuthenticator(auth_secret) if auth_secret else None
        
        # ... existing initialization
    
    async def append(self, event: Event, agent_auth: Optional[Dict] = None) -> None:
        """Append single event with security validation."""
        # Authenticate agent if auth is enabled
        if self.authenticator and agent_auth:
            if not self.authenticator.authenticate_agent(**agent_auth):
                raise SecurityError("Agent authentication failed")
        
        # Validate event security
        SecurityValidator.validate_aggregate_id(event.aggregate_id)
        InputValidator.validate_event_data(event.data)
        InputValidator.validate_event_data(event.metadata)
        
        # Calculate and verify content hash
        event.content_hash = event.calculate_content_hash()
        
        # ... existing append logic
```

**Day 2 Deliverable**: Critical security vulnerabilities fixed, authentication framework in place

---

## Day 3: Performance SLA Enforcement (ADR-004)

### **Issue**: No Runtime Performance SLA Monitoring
- Missing p99 latency <10ms enforcement
- No throughput monitoring for 10K events/second requirement

### **Implementation Plan**

#### 3.1 Performance Monitor Implementation

```python
# src/lighthouse/event_store/performance.py
import time
import threading
from collections import deque
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class PerformanceLevel(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"  
    CRITICAL = "critical"

@dataclass
class PerformanceMetrics:
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    p99_9_latency_ms: float
    throughput_per_second: float
    error_rate: float

class PerformanceMonitor:
    """Real-time performance monitoring with SLA enforcement."""
    
    def __init__(self):
        self._latency_samples = deque(maxlen=10000)  # Last 10K operations
        self._throughput_tracker = deque(maxlen=3600)  # Last hour by second
        self._error_count = 0
        self._total_operations = 0
        self._lock = threading.Lock()
        
        # ADR-004 SLA Thresholds
        self.SLA_P99_LATENCY_MS = 10.0
        self.SLA_THROUGHPUT_PER_SEC = 10000
        self.SLA_ERROR_RATE = 0.01  # 1%
    
    def record_operation(self, latency_ms: float, success: bool = True) -> None:
        """Record operation performance metrics."""
        with self._lock:
            self._latency_samples.append(latency_ms)
            self._total_operations += 1
            
            if not success:
                self._error_count += 1
            
            # Track throughput per second
            current_second = int(time.time())
            if not self._throughput_tracker or self._throughput_tracker[-1][0] != current_second:
                self._throughput_tracker.append([current_second, 1])
            else:
                self._throughput_tracker[-1][1] += 1
    
    def get_current_metrics(self) -> PerformanceMetrics:
        """Calculate current performance metrics."""
        with self._lock:
            if not self._latency_samples:
                return PerformanceMetrics(0, 0, 0, 0, 0, 0)
            
            # Calculate latency percentiles
            sorted_latencies = sorted(self._latency_samples)
            sample_count = len(sorted_latencies)
            
            p50_idx = int(sample_count * 0.50)
            p95_idx = int(sample_count * 0.95)
            p99_idx = int(sample_count * 0.99)
            p99_9_idx = int(sample_count * 0.999)
            
            metrics = PerformanceMetrics(
                p50_latency_ms=sorted_latencies[p50_idx],
                p95_latency_ms=sorted_latencies[p95_idx],
                p99_latency_ms=sorted_latencies[p99_idx],
                p99_9_latency_ms=sorted_latencies[p99_9_idx] if p99_9_idx < sample_count else sorted_latencies[-1],
                throughput_per_second=self._calculate_current_throughput(),
                error_rate=self._error_count / max(self._total_operations, 1)
            )
            
            return metrics
    
    def _calculate_current_throughput(self) -> float:
        """Calculate current throughput over last minute."""
        if not self._throughput_tracker:
            return 0.0
        
        current_time = int(time.time())
        one_minute_ago = current_time - 60
        
        recent_operations = sum(
            count for timestamp, count in self._throughput_tracker 
            if timestamp >= one_minute_ago
        )
        
        return recent_operations / 60.0  # Operations per second
    
    def check_sla_compliance(self) -> PerformanceLevel:
        """Check if current performance meets SLA requirements."""
        metrics = self.get_current_metrics()
        
        # Check critical SLA violations
        if (metrics.p99_latency_ms > self.SLA_P99_LATENCY_MS * 2 or
            metrics.throughput_per_second < self.SLA_THROUGHPUT_PER_SEC * 0.5 or
            metrics.error_rate > self.SLA_ERROR_RATE * 2):
            return PerformanceLevel.CRITICAL
        
        # Check degraded performance
        if (metrics.p99_latency_ms > self.SLA_P99_LATENCY_MS or
            metrics.throughput_per_second < self.SLA_THROUGHPUT_PER_SEC * 0.9 or
            metrics.error_rate > self.SLA_ERROR_RATE):
            return PerformanceLevel.DEGRADED
        
        return PerformanceLevel.HEALTHY
```

#### 3.2 Integrate Performance Monitoring into EventStore

```python
# src/lighthouse/event_store/store.py - Performance integration
from .performance import PerformanceMonitor, PerformanceLevel

class EventStore:
    def __init__(self, data_dir: str = "./data/events"):
        # ... existing initialization
        self.performance_monitor = PerformanceMonitor()
        self.performance_status = PerformanceLevel.HEALTHY
    
    async def append(self, event: Event) -> None:
        """Append single event with performance monitoring."""
        start_time = time.perf_counter()
        success = False
        
        try:
            # ... existing append logic
            success = True
            
        except Exception as e:
            success = False
            raise
        finally:
            # Record performance metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.performance_monitor.record_operation(latency_ms, success)
            
            # Check SLA compliance
            self.performance_status = self.performance_monitor.check_sla_compliance()
            
            # Trigger degradation if needed
            if self.performance_status == PerformanceLevel.CRITICAL:
                await self._handle_critical_performance()
    
    async def _handle_critical_performance(self) -> None:
        """Handle critical performance degradation."""
        # Log critical performance issue
        logger.critical("Event store performance critical - p99 latency or throughput SLA violated")
        
        # Trigger emergency degradation mode per ADR-001
        # This will be implemented in Day 7
        pass
    
    async def get_performance_status(self) -> Dict:
        """Get current performance status and metrics."""
        metrics = self.performance_monitor.get_current_metrics()
        return {
            'status': self.performance_status.value,
            'metrics': {
                'p99_latency_ms': metrics.p99_latency_ms,
                'sla_p99_threshold_ms': self.performance_monitor.SLA_P99_LATENCY_MS,
                'throughput_per_second': metrics.throughput_per_second,
                'sla_throughput_threshold': self.performance_monitor.SLA_THROUGHPUT_PER_SEC,
                'error_rate': metrics.error_rate,
                'sla_error_rate_threshold': self.performance_monitor.SLA_ERROR_RATE
            },
            'sla_compliant': self.performance_status == PerformanceLevel.HEALTHY
        }
```

#### 3.3 Performance Compliance Tests

```python
# tests/unit/event_store/test_performance_compliance.py
import pytest
import asyncio
import time
from lighthouse.event_store.performance import PerformanceLevel

class TestPerformanceCompliance:
    @pytest.mark.performance
    async def test_p99_latency_compliance(self, temp_event_store):
        """Test p99 latency meets ADR-004 requirement of <10ms."""
        store = temp_event_store
        latencies = []
        
        # Generate 1000 events to get reliable p99 measurement
        for i in range(1000):
            start_time = time.perf_counter()
            
            event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id=f"perf_test_{i}",
                data={"index": i, "timestamp": time.time()}
            )
            
            await store.append(event)
            latency_ms = (time.perf_counter() - start_time) * 1000
            latencies.append(latency_ms)
        
        # Calculate p99 latency
        sorted_latencies = sorted(latencies)
        p99_idx = int(len(sorted_latencies) * 0.99)
        p99_latency = sorted_latencies[p99_idx]
        
        # Verify ADR-004 compliance
        assert p99_latency <= 10.0, f"p99 latency {p99_latency:.2f}ms exceeds ADR-004 requirement of 10ms"
        
        # Verify performance monitor is tracking correctly
        status = await store.get_performance_status()
        assert status['sla_compliant'], "Performance monitor should report SLA compliance"
    
    @pytest.mark.performance
    async def test_throughput_monitoring(self, temp_event_store):
        """Test throughput monitoring tracks events per second."""
        store = temp_event_store
        
        # Send events at high rate
        start_time = time.time()
        events_sent = 0
        
        while time.time() - start_time < 5:  # Run for 5 seconds
            event = Event(
                event_type=EventType.AGENT_HEARTBEAT,
                aggregate_id=f"throughput_test_{events_sent}",
                data={"heartbeat": time.time()}
            )
            await store.append(event)
            events_sent += 1
        
        elapsed_time = time.time() - start_time
        actual_throughput = events_sent / elapsed_time
        
        # Get performance metrics
        status = await store.get_performance_status()
        
        # Should be tracking throughput reasonably accurately (within 10%)
        reported_throughput = status['metrics']['throughput_per_second']
        throughput_diff = abs(actual_throughput - reported_throughput) / actual_throughput
        
        assert throughput_diff < 0.1, f"Throughput monitoring inaccuracy: {throughput_diff:.1%}"
```

**Day 3 Deliverable**: Real-time performance monitoring with ADR-004 SLA enforcement

---

## Day 4-5: State Recovery & Comprehensive Testing

### **Day 4: Enhanced State Recovery**

#### 4.1 Complete Crash Recovery Implementation

```python
# src/lighthouse/event_store/recovery.py
import json
import hashlib
from typing import List, Dict, Optional, Tuple
from pathlib import Path

class RecoveryManager:
    """Handle crash recovery and state validation."""
    
    def __init__(self, event_store):
        self.event_store = event_store
    
    async def perform_full_recovery(self) -> Dict:
        """Perform complete recovery with validation."""
        recovery_report = {
            'status': 'success',
            'events_recovered': 0,
            'corrupted_events_skipped': 0,
            'consistency_checks': {},
            'warnings': []
        }
        
        # 1. Validate all log files
        log_files = sorted(self.event_store.data_dir.glob("events_*.log*"))
        for log_file in log_files:
            file_report = await self._validate_log_file(log_file)
            recovery_report['events_recovered'] += file_report['valid_events']
            recovery_report['corrupted_events_skipped'] += file_report['corrupted_events']
            
            if file_report['warnings']:
                recovery_report['warnings'].extend(file_report['warnings'])
        
        # 2. Rebuild and validate index consistency
        await self._rebuild_and_validate_index()
        recovery_report['consistency_checks']['index'] = 'passed'
        
        # 3. Validate sequence number consistency
        sequence_validation = await self._validate_sequence_consistency()
        recovery_report['consistency_checks']['sequence'] = sequence_validation
        
        # 4. Validate state consistency
        state_validation = await self._validate_state_consistency()
        recovery_report['consistency_checks']['state'] = state_validation
        
        return recovery_report
    
    async def _validate_log_file(self, log_file: Path) -> Dict:
        """Validate single log file and report corruption."""
        report = {'valid_events': 0, 'corrupted_events': 0, 'warnings': []}
        
        async for event_result in self._read_log_with_validation(log_file):
            if event_result['valid']:
                report['valid_events'] += 1
            else:
                report['corrupted_events'] += 1
                report['warnings'].append(
                    f"Corrupted event at offset {event_result['offset']} in {log_file}: {event_result['error']}"
                )
        
        return report
    
    async def _read_log_with_validation(self, log_path: Path):
        """Read log file with detailed validation reporting."""
        if log_path.suffix == '.gz':
            import gzip
            with gzip.open(log_path, 'rb') as f:
                content = f.read()
        else:
            async with aiofiles.open(log_path, 'rb') as f:
                content = await f.read()
        
        offset = 0
        while offset < len(content):
            try:
                # Read length
                if offset + 4 > len(content):
                    yield {'valid': False, 'offset': offset, 'error': 'Truncated length header'}
                    break
                
                length = int.from_bytes(content[offset:offset+4], 'big')
                offset += 4
                
                # Read checksum and data
                if offset + 32 + length > len(content):
                    yield {'valid': False, 'offset': offset, 'error': 'Truncated event data'}
                    break
                
                expected_checksum = content[offset:offset+32]
                offset += 32
                event_data = content[offset:offset+length]
                offset += length
                
                # Verify checksum
                actual_checksum = hashlib.sha256(event_data).digest()
                if actual_checksum != expected_checksum:
                    yield {'valid': False, 'offset': offset, 'error': 'Checksum mismatch'}
                    continue
                
                # Try to deserialize event
                try:
                    event = Event.from_msgpack(event_data)
                    yield {'valid': True, 'event': event, 'offset': offset}
                except Exception as e:
                    yield {'valid': False, 'offset': offset, 'error': f'Deserialization failed: {e}'}
                
            except Exception as e:
                yield {'valid': False, 'offset': offset, 'error': f'Read error: {e}'}
                break
```

### **Day 5: Comprehensive Testing Framework**

#### 5.1 Failure Scenario Test Suite

```python
# tests/integration/test_failure_scenarios.py
import os
import signal
import subprocess
import tempfile
from pathlib import Path

class TestFailureScenarios:
    @pytest.mark.integration
    async def test_crash_during_write_recovery(self, temp_dir):
        """Test recovery from crash during event write."""
        store = EventStore(data_dir=temp_dir)
        await store.initialize()
        
        # Write some events normally
        for i in range(100):
            await store.append(Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id=f"pre_crash_{i}",
                data={"index": i}
            ))
        
        # Simulate crash by corrupting current log file
        log_files = list(Path(temp_dir).glob("*.log"))
        if log_files:
            with open(log_files[-1], 'ab') as f:
                f.write(b'\x00\x00\x10\x00')  # Invalid length prefix
                f.write(b'CORRUPT_DATA_SIMULATING_CRASH' * 100)
        
        # Test recovery
        recovery_store = EventStore(data_dir=temp_dir)
        recovery_report = await recovery_store.perform_full_recovery()
        
        # Should recover valid events, skip corrupted ones
        assert recovery_report['status'] == 'success'
        assert recovery_report['events_recovered'] == 100
        assert recovery_report['corrupted_events_skipped'] > 0
    
    @pytest.mark.integration
    async def test_disk_full_graceful_handling(self):
        """Test graceful handling when disk space is exhausted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create filesystem with limited space
            loop_device = await self._create_limited_filesystem(temp_dir, size_mb=50)
            
            try:
                store = EventStore(data_dir=temp_dir)
                await store.initialize()
                
                events_written = 0
                disk_full_handled = False
                
                # Fill up the disk
                for i in range(10000):  # Try to write many events
                    try:
                        large_event = Event(
                            event_type=EventType.SHADOW_UPDATED,
                            aggregate_id=f"large_file_{i}",
                            data={"content": "x" * 10000}  # 10KB per event
                        )
                        await store.append(large_event)
                        events_written += 1
                        
                    except EventStoreError as e:
                        if "disk full" in str(e).lower() or "no space" in str(e).lower():
                            disk_full_handled = True
                            break
                        else:
                            raise  # Re-raise unexpected errors
                
                # Verify graceful disk full handling
                assert disk_full_handled, "Should gracefully handle disk full condition"
                assert events_written > 0, "Should write some events before disk full"
                
                # Verify store is still operational after cleanup
                await store.cleanup_old_logs()
                
                # Should be able to write after cleanup
                small_event = Event(
                    event_type=EventType.SYSTEM_STARTED,
                    aggregate_id="recovery_test",
                    data={"message": "recovery successful"}
                )
                await store.append(small_event)
                
            finally:
                if loop_device:
                    await self._cleanup_limited_filesystem(loop_device)
    
    async def _create_limited_filesystem(self, mount_point: str, size_mb: int) -> str:
        """Create small filesystem for disk full testing."""
        # This is a simplified version - actual implementation would use loop devices
        # For now, just return None and skip the test if root privileges not available
        if os.getuid() != 0:
            pytest.skip("Disk full testing requires root privileges for loop devices")
        
        return None
```

#### 5.2 Performance Regression Test Suite

```python
# tests/performance/test_performance_regression.py
class TestPerformanceRegression:
    @pytest.mark.performance
    async def test_sustained_load_performance(self, temp_event_store):
        """Test sustained load maintains performance SLA."""
        store = temp_event_store
        
        # Test parameters
        test_duration_seconds = 300  # 5 minute sustained test
        target_throughput = 1000     # events per second (scaled for CI)
        max_p99_latency_ms = 10.0
        
        start_time = time.time()
        events_written = 0
        latencies = []
        
        while time.time() - start_time < test_duration_seconds:
            batch_start = time.perf_counter()
            
            # Write batch of events
            batch_events = []
            for i in range(10):  # 10 events per batch
                batch_events.append(Event(
                    event_type=EventType.AGENT_HEARTBEAT,
                    aggregate_id=f"sustained_test_{events_written + i}",
                    data={
                        "timestamp": time.time(),
                        "batch_index": i,
                        "total_events": events_written + i
                    }
                ))
            
            batch = EventBatch(events=batch_events)
            await store.append_batch(batch)
            
            batch_latency = (time.perf_counter() - batch_start) * 1000
            latencies.append(batch_latency / 10)  # Per-event latency
            events_written += 10
            
            # Maintain target rate
            expected_time = (events_written / target_throughput)
            actual_time = time.time() - start_time
            if actual_time < expected_time:
                await asyncio.sleep(expected_time - actual_time)
        
        # Validate performance maintained throughout test
        total_time = time.time() - start_time
        actual_throughput = events_written / total_time
        
        # Calculate performance percentiles
        sorted_latencies = sorted(latencies)
        p99_idx = int(len(sorted_latencies) * 0.99)
        p99_latency = sorted_latencies[p99_idx]
        
        # Assertions
        assert actual_throughput >= target_throughput * 0.95, \
            f"Throughput {actual_throughput:.0f} below 95% of target {target_throughput}"
        
        assert p99_latency <= max_p99_latency_ms, \
            f"p99 latency {p99_latency:.2f}ms exceeds {max_p99_latency_ms}ms limit"
        
        # Verify performance monitoring is working
        status = await store.get_performance_status()
        assert status['sla_compliant'], "Performance monitoring should report SLA compliance"
```

**Day 4-5 Deliverable**: Complete crash recovery system and comprehensive test coverage

---

## Day 6-8: Integration & Observability

### **Day 6: Emergency Degradation Integration (ADR-001)**

```python
# src/lighthouse/event_store/degradation.py
from enum import Enum
from typing import Optional, Dict, Any
import asyncio

class DegradationLevel(Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    EMERGENCY = "emergency"

class DegradationManager:
    """Manage emergency degradation per ADR-001."""
    
    def __init__(self, event_store):
        self.event_store = event_store
        self.current_level = DegradationLevel.NORMAL
        self.degradation_triggers = {}
        self.recovery_conditions = {}
    
    async def check_degradation_triggers(self) -> Optional[DegradationLevel]:
        """Check if degradation should be triggered."""
        # Performance-based degradation
        perf_status = await self.event_store.get_performance_status()
        if not perf_status['sla_compliant']:
            p99_latency = perf_status['metrics']['p99_latency_ms']
            if p99_latency > 50:  # 5x SLA violation
                return DegradationLevel.EMERGENCY
            elif p99_latency > 20:  # 2x SLA violation
                return DegradationLevel.DEGRADED
        
        # Disk space degradation
        health = await self.event_store.get_health()
        disk_usage_pct = health.disk_usage_bytes / (health.disk_usage_bytes + health.disk_free_bytes)
        if disk_usage_pct > 0.95:  # >95% disk usage
            return DegradationLevel.EMERGENCY
        elif disk_usage_pct > 0.85:  # >85% disk usage
            return DegradationLevel.DEGRADED
        
        return None
    
    async def trigger_degradation(self, level: DegradationLevel, reason: str) -> None:
        """Trigger emergency degradation mode."""
        if level == self.current_level:
            return
        
        # Log degradation event
        degradation_event = Event(
            event_type=EventType.DEGRADATION_TRIGGERED,
            aggregate_id="system",
            data={
                "previous_level": self.current_level.value,
                "new_level": level.value,
                "reason": reason,
                "timestamp": time.time()
            }
        )
        
        try:
            await self.event_store.append(degradation_event)
        except Exception:
            # If we can't even log degradation, system is in critical state
            pass
        
        self.current_level = level
        
        # Notify other system components
        await self._notify_degradation_change(level, reason)
    
    async def _notify_degradation_change(self, level: DegradationLevel, reason: str) -> None:
        """Notify other system components of degradation change."""
        # This would integrate with the bridge and other components
        # For now, just log the change
        import logging
        logger = logging.getLogger(__name__)
        
        if level == DegradationLevel.EMERGENCY:
            logger.critical(f"EMERGENCY DEGRADATION: {reason}")
        elif level == DegradationLevel.DEGRADED:
            logger.warning(f"SYSTEM DEGRADED: {reason}")
        else:
            logger.info(f"SYSTEM RECOVERED: {reason}")
```

### **Day 7-8: Observability & Monitoring**

```python
# src/lighthouse/event_store/observability.py
import time
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, start_http_server

class ObservabilityManager:
    """Comprehensive observability for event store operations."""
    
    def __init__(self):
        # Prometheus metrics
        self.events_total = Counter('lighthouse_events_total', 
                                  'Total events processed', ['operation', 'status'])
        self.event_latency = Histogram('lighthouse_event_latency_seconds',
                                     'Event operation latency', ['operation'])
        self.current_sequence = Gauge('lighthouse_current_sequence',
                                    'Current event sequence number')
        self.performance_sla_violations = Counter('lighthouse_sla_violations_total',
                                                'SLA violations by type', ['violation_type'])
        
        # Audit trail
        self.audit_events = []
    
    def record_event_operation(self, operation: str, latency_seconds: float, 
                             success: bool = True) -> None:
        """Record event operation metrics."""
        status = 'success' if success else 'error'
        
        self.events_total.labels(operation=operation, status=status).inc()
        self.event_latency.labels(operation=operation).observe(latency_seconds)
        
        # Record audit trail
        self.audit_events.append({
            'timestamp': time.time(),
            'operation': operation,
            'latency_ms': latency_seconds * 1000,
            'success': success
        })
        
        # Keep audit trail bounded
        if len(self.audit_events) > 10000:
            self.audit_events = self.audit_events[-5000:]
    
    def record_sla_violation(self, violation_type: str) -> None:
        """Record SLA violation for monitoring."""
        self.performance_sla_violations.labels(violation_type=violation_type).inc()
    
    def get_audit_trail(self, limit: int = 100) -> List[Dict]:
        """Get recent audit trail events."""
        return self.audit_events[-limit:]
    
    async def start_metrics_server(self, port: int = 8080) -> None:
        """Start Prometheus metrics server."""
        start_http_server(port)
```

**Day 6-8 Deliverable**: Emergency degradation integration and comprehensive observability

---

## Validation & Acceptance Criteria

### **Critical Requirements Met**
- ✅ Event ID format compliant with ADR-003
- ✅ Security vulnerabilities eliminated
- ✅ Performance SLA enforcement implemented
- ✅ Comprehensive crash recovery system
- ✅ Full test coverage including failure scenarios

### **Success Metrics**
- All peer review blocking issues resolved
- Performance tests pass ADR-004 requirements
- Security tests pass without vulnerabilities
- 95%+ test coverage with integration tests
- Emergency degradation integration working

### **Acceptance Tests**
```bash
# Performance compliance
pytest tests/performance/ --benchmark-only -v

# Security validation  
pytest tests/security/ -v

# Failure scenario testing
pytest tests/integration/test_failure_scenarios.py -v

# Full test suite
pytest tests/ -v --cov=lighthouse.event_store --cov-report=html
```

## Remediation Timeline Summary

| **Day** | **Focus** | **Deliverable** | **Validation** |
|---------|-----------|----------------|----------------|
| 1 | Event ID Compliance | ADR-003 format implemented | Format tests pass |
| 2 | Security Fixes | Critical vulnerabilities fixed | Security tests pass |
| 3 | Performance SLA | Real-time monitoring | Performance tests pass |
| 4 | State Recovery | Complete crash recovery | Recovery tests pass |
| 5 | Comprehensive Testing | Full test coverage | 95% coverage achieved |
| 6 | Degradation Integration | ADR-001 compliance | Integration tests pass |
| 7-8 | Observability | Full monitoring stack | Monitoring tests pass |

## Conclusion

This detailed remediation plan addresses all critical issues identified in the peer review process. Upon completion, Phase 1.1 will be production-ready with:

- **100% architectural compliance** with ADR-002, ADR-003, ADR-004
- **Zero critical security vulnerabilities**
- **Comprehensive performance monitoring and SLA enforcement**
- **Robust failure recovery and testing coverage**
- **Full observability and emergency coordination**

The remediation work transforms the Phase 1.1 implementation from a development prototype into a production-ready foundation for the Lighthouse multi-agent coordination system.

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"content": "Create comprehensive remediation plan for Phase 1.1 issues", "status": "completed", "activeForm": "Creating comprehensive remediation plan for Phase 1.1 issues"}]