# ADR-001: Emergency Degradation Mode for Virtual Filesystem Failures

**Status**: Accepted  
**Date**: 2024-08-24  
**Authors**: System Architecture Team  
**Supersedes**: N/A  

## Context

Expert review of the Lighthouse architecture identified a critical failure mode: if the FUSE mount providing expert agents with virtual filesystem access fails, the system could fail catastrophically or continue operating in an undefined degraded state.

The original architecture assumed expert agents would gracefully fall back to API-based file access, but this creates complex dual-mode implementations and unclear system behavior.

## Decision

We will implement **Emergency Degradation Mode** - a fail-safe operating mode that prioritizes system stability and data integrity over continued functionality when the virtual filesystem becomes unavailable.

### Core Principles

1. **Real filesystem is always authoritative** - project files on disk remain the single source of truth
2. **Emergency mode blocks new work** - degraded system refuses new development tasks
3. **Complete or stop safely** - in-flight operations finish cleanly or abort safely
4. **Recovery requires explicit validation** - system must be verified healthy before resuming normal operations

## Detailed Design

### System State Machine

```yaml
Operating_States:
  NORMAL:
    description: "All capabilities available"
    accepts: "All development work"
    expert_agents: "Full file analysis via FUSE mount"
    
  EMERGENCY:  
    description: "Virtual filesystem unavailable - maintenance only"
    accepts: "System recovery operations only"
    expert_agents: "Message-bus coordination only, no file analysis"
    
  RECOVERING:
    description: "Restoring virtual filesystem capabilities"  
    accepts: "No new work accepted"
    expert_agents: "Testing restored file access"
```

### State Transitions

```yaml
NORMAL → EMERGENCY:
  Trigger: "FUSE mount failure detected"
  Actions:
    - Complete in-flight operations (30 second timeout)
    - Block all new development task requests
    - Notify expert agents of degraded capabilities
    - Alert human operators immediately
    
EMERGENCY → RECOVERING:
  Trigger: "Manual recovery process initiated"
  Actions:
    - Begin virtual filesystem restoration
    - Resync shadows from authoritative real filesystem
    - Test expert agent file access capabilities
    
RECOVERING → NORMAL:
  Trigger: "All systems verified healthy + manual approval"
  Actions:
    - Resume accepting development work
    - Restore full expert agent analysis capabilities
    - Log successful recovery completion

ANY_STATE → EMERGENCY:
  Trigger: "Critical system failure detected"
  Actions:
    - Immediate safe shutdown of affected components
    - Preserve all in-flight work safely
    - Enter emergency operations mode
```

### Emergency Mode Behavior

```yaml
Task_Assignment_Policy:
  New_Development_Tasks: "REJECTED with clear explanation"
  In_Flight_Tasks: "Complete safely and stop"
  System_Recovery_Tasks: "ACCEPTED as emergency operations"

Agent_Capabilities:
  Builder_Agents:
    - Complete current edit/file operation
    - Refuse new feature development requests
    - Accept system recovery and diagnostic commands
    - Provide clear status: "Operating in emergency mode"
    
  Expert_Agents: 
    - Complete active reviews using available context
    - Refuse new analysis requests requiring file access
    - Provide emergency guidance via message bus only
    - Report degraded capabilities clearly

User_Experience:
  Development_Request: "Add OAuth login system"
  System_Response: 
    "SYSTEM EMERGENCY MODE ACTIVE
     Virtual filesystem unavailable - expert analysis disabled
     No new development work accepted until system recovery
     Status: FUSE mount failure detected at 14:32 UTC"
     
  Recovery_Request: "Restore FUSE mount"
  System_Response:
    "EMERGENCY OPERATION ACCEPTED
     Initiating virtual filesystem recovery procedures"
```

### Recovery Process

```yaml
Virtual_Filesystem_Recovery:
  1. Detect_Real_Filesystem_State:
     - Scan authoritative project directory
     - Generate current filesystem snapshot
     - Identify changes since last known shadow state
     
  2. Rebuild_Shadow_Filesystem:
     - Create fresh shadows from real files
     - Mark shadows as "recovery sync" 
     - Invalidate stale shadow data completely
     
  3. Restore_FUSE_Mount:
     - Mount synchronized shadows at /mnt/lighthouse/
     - Verify mount accessibility and performance
     - Test basic file operations (read, readdir, stat)
     
  4. Validate_Expert_Agent_Access:
     - Confirm expert agents can access mounted filesystem
     - Run standard tool tests (grep, find, cat)
     - Verify file content matches real filesystem
     
  5. System_Health_Validation:
     - End-to-end workflow test
     - Expert analysis capability verification  
     - Performance benchmark validation
     
  6. Manual_Recovery_Approval:
     - Human operator confirms system health
     - Explicit approval to exit emergency mode
     - Documentation of recovery actions taken

Exit_Criteria:
  - FUSE mount stable and verified
  - Shadow filesystem synchronized with real files
  - Expert agents report full file access
  - End-to-end validation passes
  - Manual operator approval recorded
```

## Implementation Requirements

### Phase 1: Event Store Foundation
- Health monitoring for virtual filesystem components
- Emergency state recording in event log
- Graceful degradation triggers and notifications

### Phase 2: Bridge Server
- System state machine implementation
- Task acceptance/rejection logic based on system state
- Emergency operation identification and routing

### Phase 3: Virtual Filesystem Implementation  
- FUSE mount health monitoring and failure detection
- Shadow filesystem rebuild from authoritative real files
- Recovery synchronization and validation procedures

### Phase 4: Expert Agent Integration
- Dual-mode operation (FUSE mount vs message-bus only)
- Graceful capability degradation and restoration
- Clear status reporting of degraded capabilities

## Testing Requirements

```yaml
Failure_Scenarios_To_Test:
  - FUSE mount suddenly becomes unresponsive
  - FUSE mount process crashes during file operation
  - Filesystem corruption detected in shadow layer
  - Expert agent loses file access mid-analysis
  - System restart while in emergency mode

Recovery_Scenarios_To_Test:
  - Recovery with no real filesystem changes during emergency
  - Recovery with significant real filesystem changes during emergency  
  - Recovery failure scenarios and error handling
  - Multiple recovery attempts and idempotence
  - Recovery validation failure and rollback

End_To_End_Scenarios:
  - Development workflow interrupted by emergency mode
  - System recovery and workflow resumption
  - Data integrity verification after recovery
  - Expert agent analysis accuracy after recovery
```

## Alternatives Considered

### Alternative 1: Dual-Mode Expert Agents
**Description**: Implement expert agents that can work with either FUSE mount or direct API calls to shadow filesystem.

**Rejected Because**: 
- Complex dual-mode implementation increases failure surface area
- Unclear system behavior - users don't know which mode they're in
- API fallback may not provide equivalent capabilities to filesystem access
- Testing complexity doubles with two code paths

### Alternative 2: Continue with Reduced Capabilities
**Description**: Allow system to continue normal operations with limited expert analysis.

**Rejected Because**:
- Creates false sense of security - users don't realize analysis is compromised
- Potential for serious issues to go undetected by degraded expert analysis
- Complex logic to determine what operations are "safe enough" with reduced analysis
- Risk of data inconsistency between real files and shadows

### Alternative 3: Immediate Complete Shutdown
**Description**: Shut down entire system when virtual filesystem fails.

**Rejected Because**:
- Too disruptive - kills all work including safe operations
- Prevents system recovery operations that might fix the issue
- Loss of coordination capabilities that don't depend on file access
- No graceful completion of in-flight operations

## Consequences

### Positive Consequences
- **Clear failure modes**: System behavior is predictable and well-defined
- **Data integrity guaranteed**: Real filesystem remains authoritative
- **Safe degradation**: No undefined or partially-working states
- **Simple implementation**: Single failure mode easier to test and validate
- **Operator clarity**: Clear system status and recovery procedures

### Negative Consequences  
- **Development interruption**: Work stops when virtual filesystem fails
- **Recovery overhead**: Manual steps required to exit emergency mode
- **Reduced availability**: System unavailable for development during recovery
- **Emergency procedures complexity**: Operators need training on recovery process

### Risk Mitigation
- **Comprehensive monitoring** to detect virtual filesystem issues early
- **Automated recovery procedures** where safely possible
- **Clear documentation** and training for emergency operations
- **Fast recovery testing** to minimize downtime duration

## Monitoring and Metrics

```yaml
Health_Metrics:
  - FUSE mount response latency and error rates
  - Shadow filesystem synchronization lag
  - Expert agent file access success rates
  - Emergency mode frequency and duration
  
Alerting_Thresholds:
  - FUSE mount response time > 1 second
  - File access error rate > 1%
  - Shadow synchronization lag > 30 seconds
  - Any transition to emergency mode (immediate alert)
  
Recovery_Metrics:
  - Mean time to recovery (MTTR) 
  - Recovery success rate on first attempt
  - Data consistency validation results
  - Post-recovery system performance
```

## Decision Rationale

This decision prioritizes **system reliability and data integrity** over **continuous availability**. For a multi-agent coordination system where expert analysis directly affects code safety and quality, it's better to have a temporarily unavailable system than a system providing compromised analysis.

The emergency degradation mode provides a clear, testable failure path that maintains system safety while enabling recovery operations. This approach reduces complexity, improves reliability, and provides clear operational procedures for failure scenarios.

The alternative approaches either introduce unacceptable complexity (dual-mode operation) or unacceptable risk (continued operation with degraded capabilities). Emergency degradation mode provides the right balance of safety, simplicity, and recoverability.