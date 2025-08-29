# ARCHITECTURE ASSESSMENT CERTIFICATE

**Component**: Permission System (auth.py and coordinator.py)
**Agent**: system-architect
**Date**: 2025-08-26 22:05:30 UTC
**Certificate ID**: arch-perm-20250826-220530

## REVIEW SCOPE
- HLD.md architecture document (complete 1396 lines)
- src/lighthouse/event_store/auth.py (Security Architect's additions)
- src/lighthouse/bridge/expert_coordination/coordinator.py (permission usage)
- Lighthouse multi-agent coordination architecture patterns

## FINDINGS

### Positive Aspects
1. **Comprehensive Coverage**: Permissions cover most system operations
2. **Role-Based Structure**: Clear role hierarchy with appropriate escalation
3. **Security Integration**: Proper use of HMAC authentication and rate limiting
4. **Event Store Integration**: Permissions properly integrated with event sourcing

### Critical Architectural Issue
**VIOLATION OF CORE HLD PRINCIPLE**: The permission system fails to distinguish between:
- Direct filesystem access (Builder agents only)
- FUSE shadow access (Expert agents only)

The HLD explicitly states experts have "Zero Filesystem Access" and work "exclusively on bridge-maintained shadows". The current `FILE_READ`/`FILE_WRITE` permissions conflate these fundamentally different access patterns.

### Secondary Issues
1. **Permission Granularity**: `COMMAND_EXECUTION` doesn't distinguish between direct execution (builders) vs. delegation (experts)
2. **Missing Permissions**: No explicit permissions for shadow annotations or AST-anchored intelligence
3. **Audit Gap**: `SECURITY_REVIEW` vs `SECURITY_AUDIT` distinction unclear

## DECISION/OUTCOME
**Status**: CONDITIONALLY_APPROVED
**Rationale**: The permission system is architecturally sound in structure but violates a core HLD security principle by not distinguishing shadow access from filesystem access.
**Conditions**: 
1. Refactor permissions to separate `SHADOW_*` from `FILESYSTEM_*` operations
2. Update coordinator.py to use appropriate shadow permissions for FUSE operations
3. Ensure expert agents NEVER receive `FILESYSTEM_*` permissions
4. Add `SHADOW_ANNOTATE` permission for AST-anchored annotations

## EVIDENCE
- HLD.md lines 85-89: "Zero Filesystem Access: Work exclusively on bridge-maintained shadows"
- HLD.md line 291: "Expert agents now just use standard tools [on FUSE mount]"
- auth.py lines 29-30: Current `FILE_READ`/`FILE_WRITE` don't distinguish access types
- coordinator.py line 506-510: Uses generic file permissions for FUSE operations

## ARCHITECTURAL RECOMMENDATION

### Immediate Actions Required:
1. **Split file permissions** into `SHADOW_*` (experts) and `FILESYSTEM_*` (builders)
2. **Update coordinator.py** lines 595-606 to check `SHADOW_*` permissions for FUSE
3. **Update role permissions** to ensure experts get `SHADOW_*` but NOT `FILESYSTEM_*`
4. **Add validation** to prevent experts from ever receiving filesystem permissions

### Proposed Permission Architecture:
```python
# Expert agents (via FUSE/shadows only):
SHADOW_READ, SHADOW_WRITE, SHADOW_ANNOTATE

# Builder agents (direct filesystem):
FILESYSTEM_READ, FILESYSTEM_WRITE, COMMAND_EXECUTE_DIRECT

# Both:
COMMAND_VALIDATE, EXPERT_COORDINATION, CONTEXT_SHARING
```

## RISK ASSESSMENT
**Current Risk**: MEDIUM - Security boundary violation between builders and experts
**After Fix**: LOW - Clear separation of concerns maintains security model

## SIGNATURE
Agent: system-architect
Timestamp: 2025-08-26 22:05:30 UTC
Architecture Pattern: Multi-Agent Coordination with Shadow Filesystem Isolation