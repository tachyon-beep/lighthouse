# Integration Specialist Working Memory

## Current Task: Permission System Finalization
Date: 2025-08-26

### Critical Integration Requirements

#### From HLD Architecture (Lines 70-89):
- **Builder Agents**: Direct filesystem access, execute commands directly
- **Expert Agents**: NO filesystem access, only FUSE shadow access via `/mnt/lighthouse/project/`
- **Bridge**: Persistent daemon maintaining project mirrors
- **Authentication**: HMAC-SHA256 based

#### From auth.py Analysis:
Current permissions defined:
- Event Store: READ_EVENTS, WRITE_EVENTS, QUERY_EVENTS, ADMIN_ACCESS, HEALTH_CHECK
- Expert: EXPERT_COORDINATION
- File: FILE_READ, FILE_WRITE (ambiguous - needs clarification)
- Command: COMMAND_EXECUTION, COMMAND_VALIDATION
- System: SYSTEM_ADMIN, SYSTEM_CONFIG
- Agent: BRIDGE_ACCESS, CONTEXT_SHARING, SESSION_MANAGEMENT
- Security: AUDIT_ACCESS, SECURITY_REVIEW

#### From coordinator.py Requirements (Lines 241-243):
Required permissions check:
```python
required_perms = [Permission.EXPERT_COORDINATION, Permission.COMMAND_EXECUTION]
```

Also checks in validation (Lines 595-605):
- FILE_WRITE permissions
- FILE_READ permissions
- COMMAND_EXECUTION permissions
- SYSTEM_ADMIN for sensitive paths

#### From mcp_server.py Integration (Lines 398-402):
Expert registration creates EXPERT_AGENT role with:
- Configurable permissions list
- Expert-specific capabilities
- Virtual filesystem access mode

### Critical Issues to Resolve

1. **Ambiguous FILE_READ/FILE_WRITE permissions**:
   - Currently used for both real filesystem AND shadow filesystem
   - HLD specifies experts should ONLY have shadow access
   - Need separate permissions: SHADOW_READ, SHADOW_WRITE vs FILESYSTEM_READ, FILESYSTEM_WRITE

2. **Missing Builder Agent Permissions**:
   - No clear distinction between builder and expert filesystem access
   - Builders need direct filesystem permissions
   - Experts need shadow-only permissions

3. **Coordinator Validation Gaps**:
   - Lines 595-605 check FILE_WRITE but doesn't distinguish shadow vs real
   - Sensitive path checks assume filesystem access

### Proposed Solution

#### New Permission Structure:
```python
# Shadow Filesystem (for Experts via FUSE)
SHADOW_READ = "shadow:read"        # Read from /mnt/lighthouse/project/
SHADOW_WRITE = "shadow:write"      # Write to shadow filesystem
SHADOW_ANNOTATE = "shadow:annotate" # Add annotations to shadows

# Direct Filesystem (for Builders ONLY)
FILESYSTEM_READ = "filesystem:read"   # Direct filesystem read
FILESYSTEM_WRITE = "filesystem:write" # Direct filesystem write
FILESYSTEM_EXECUTE = "filesystem:execute" # Execute filesystem commands

# Keep existing Event Store, Command, System permissions
```

#### Role Permission Updates:
- **GUEST**: SHADOW_READ only
- **AGENT (Builder)**: FILESYSTEM_*, COMMAND_*, EVENT_*
- **EXPERT_AGENT**: SHADOW_*, EXPERT_COORDINATION, no FILESYSTEM_*
- **SYSTEM_AGENT**: Both SHADOW_* and FILESYSTEM_*
- **ADMIN**: Everything

### Integration Points Requiring Updates

1. **auth.py (Lines 136-204)**: Update role_permissions dict
2. **auth.py (Lines 490-522)**: Update authorize_file_access method
3. **coordinator.py (Lines 595-605)**: Update validation to check shadow vs filesystem
4. **mcp_server.py (Lines 398-402)**: Ensure experts get SHADOW_* not FILE_*

### Next Actions
1. Finalize permission names and structure
2. Update auth.py with new permissions
3. Update coordinator validation logic
4. Test with MCP server integration
5. Document permission model clearly

## Historical Context

### Previous Issues
- MCP server authentication crisis (resolved)
- Direct EventStore integration without proper auth
- Confusion between shadow and real filesystem access

### Decisions Made
- Use HMAC-SHA256 for session security
- EventStore as central audit log
- FUSE mount at /mnt/lighthouse/project/ for experts
- Separate Builder vs Expert agent roles

### Current System State
- Bridge components working
- Event store operational
- Expert coordinator functional
- Permission system needs clarity on filesystem vs shadow access

## Previous Integration Work

### MCP Direct EventStore Integration (Completed Earlier Today)
- **Status**: APPROVED and implemented
- **Pattern**: Direct EventStore with CoordinatedAuthenticator preservation
- **Certificate**: `mcp_direct_eventstore_integration_validation_lighthouse_coordination_20250826_042400.md`
- **Result**: MCP server now works with direct EventStore access