# Lighthouse Multi-Agent Coordination System - Complete User Manual

## Table of Contents

1. [System Overview & Architecture](#system-overview--architecture)
2. [Getting Started](#getting-started)
3. [Core Workflows](#core-workflows)
4. [Advanced Features](#advanced-features)
5. [Expert Agent Specializations](#expert-agent-specializations)
6. [Integration & Deployment](#integration--deployment)
7. [API Reference](#api-reference)
8. [Troubleshooting & Best Practices](#troubleshooting--best-practices)
9. [Production Operations](#production-operations)

---

## System Overview & Architecture

### What is Lighthouse?

Lighthouse is a revolutionary multi-agent coordination system that transforms dangerous or complex development tasks into safe, collaborative experiences. By creating a persistent bridge that maintains living shadows of project files, Lighthouse enables expert AI agents to provide real-time analysis and recommendations without filesystem access, while builder agents handle actual implementation under continuous validation.

### Core Architecture

```mermaid
graph TB
    subgraph "Builder Environment"
        BA[Builder Agent]
        BH[Pre/Post Hooks]
        BFS[Real Filesystem]
    end
    
    subgraph "Lighthouse Bridge"
        LB[Bridge Server]
        VS[Virtual Filesystem]
        PS[Project Shadows]
        TH[Time & History]
        PP[Pair Programming]
        MV[Multi-Tier Validation]
    end
    
    subgraph "Expert Environment 1"
        SE[Security Expert]
        VT1[Virtual Tools]
    end
    
    subgraph "Expert Environment 2"
        PE[Performance Expert]
        VT2[Virtual Tools]
    end
    
    subgraph "Expert Environment 3"
        AE[Architecture Expert]
        VT3[Virtual Tools]
    end
    
    BA --> BH
    BH <--> LB
    BFS --> BH
    
    LB <--> VS
    LB <--> PS
    LB <--> TH
    LB <--> PP
    LB <--> MV
    
    SE <--> VT1
    VT1 <--> LB
    
    PE <--> VT2
    VT2 <--> LB
    
    AE <--> VT3
    VT3 <--> LB
```

### Key Components

#### 1. **Builder Agent Environment**
- **Role**: Executes actual file operations and dangerous commands
- **Constraints**: Limited to implementation tasks, cannot make architectural decisions
- **Safety**: Protected by pre-tool validation hooks that consult the bridge
- **Integration**: All file operations automatically shadowed to bridge

#### 2. **Lighthouse Bridge** (The Coordination Hub)
- **Persistent Daemon**: Runs 24/7, agents check in/out dynamically
- **Project Mirror**: Maintains perfect shadows of all project files
- **Multi-Tier Validation**: Policy → Expert escalation pipeline
- **Pair Programming**: Real-time collaboration between agents
- **Time Travel**: Complete project history and snapshot management
- **Expert Coordination**: Routes insights between specialized agents

#### 3. **Expert Agent Environments**
- **Security Expert**: Vulnerability scanning, compliance checking, threat analysis
- **Performance Expert**: Bottleneck detection, optimization recommendations
- **Architecture Expert**: Design patterns, dependency analysis, refactoring guidance
- **Zero Filesystem Access**: Work exclusively on bridge-maintained shadows

### Architectural Principles

#### Speed Layer First
- **Policy-as-code** provides instant allow/deny decisions (<100ms)
- **LLM validation** only for operations flagged as risky by policy engine
- **Sub-100ms response** for common operations, expertise for dangerous ones

#### Virtual Filesystem Transparency
- **FUSE mount** exposes shadows as standard filesystem at `/mnt/lighthouse/project/`
- **Expert agents use standard tools** (grep, cat, find) on mounted shadows
- **Zero custom APIs** needed for file operations - full POSIX compatibility

#### Event-Sourced Architecture
- **All state changes are events** in an immutable log
- **Time travel** via event replay to any point in history
- **Bridge state** reconstructed from events, enabling perfect audit trails

#### AST-Anchored Intelligence
- **Annotations survive refactoring** using tree-sitter AST spans
- **Code intelligence** that adapts as code evolves
- **Persistent expertise** across development lifecycle

---

## Getting Started

### Prerequisites

- Python 3.8+
- Docker (optional, for containerized deployment)
- Network connectivity to localhost:8765 (default bridge port)

### Installation

#### Method 1: Development Installation

```bash
# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Start the MCP server with Bridge integration
python -m lighthouse.mcp_server
```

#### Method 2: Docker Deployment

```bash
# Pull and start Lighthouse with Docker Compose
curl -O https://raw.githubusercontent.com/lighthouse-ai/lighthouse/main/docker-compose.yml
docker-compose up -d
```

### System Verification

```bash
# Check bridge status
curl http://localhost:8765/status

# Expected response:
{
  "status": "healthy",
  "bridge_mode": "production",
  "active_agents": 0,
  "pending_commands": 0,
  "shadow_filesystem": "mounted",
  "uptime_seconds": 3600
}
```

### First Agent Authentication

#### Step 1: Create Your First Session

```python
# Using MCP tool
result = lighthouse_create_session(
    agent_id="your_agent_id",
    ip_address="127.0.0.1",
    user_agent="YourApp/1.0"
)

# Expected output:
✅ Session created:
  Session ID: a1b2c3d4e5f6g7h8
  Agent ID: your_agent_id
  Token: your_agent_id:a1b2c3d4e5f6g7h8:1735234567.123:abc123def456...
  Created: Mon Jan 27 10:15:32 2025
  Security: HMAC-SHA256 validated
```

#### Step 2: Store Your Session Token

```python
# Extract the complete session token
session_token = "your_agent_id:a1b2c3d4e5f6g7h8:1735234567.123:abc123def456..."

# Use for all subsequent operations
result = lighthouse_shadow_search(
    pattern="database",
    file_types=["py", "sql"],
    session_token=session_token
)
```

---

## Core Workflows

### Workflow 1: Speed Layer Validation (99% of Operations)

This workflow handles common, safe operations with sub-100ms response times.

```mermaid
sequenceDiagram
    participant BA as Builder Agent
    participant Hook as Pre-Tool Hook
    participant PE as Policy Engine
    participant Cache as Rule Cache
    
    BA->>Hook: Execute: ls -la
    Hook->>PE: Validate command
    PE->>Cache: Check rule cache
    Cache->>PE: Cache miss
    PE->>PE: Evaluate OPA rules (5ms)
    PE->>Cache: Cache result
    PE->>Hook: ALLOW - Safe operation
    Hook->>BA: Execute immediately
    BA->>BA: Command completes fast
    
    Note over BA,Cache: 99% of operations take <100ms
```

**Example Operations (Auto-Approved)**:
- File reading: `cat file.py`, `less config.json`
- Directory listing: `ls`, `find`, `tree`
- Search operations: `grep`, `ripgrep`, `ag`
- Version control: `git status`, `git diff`, `git log`

### Workflow 2: Expert Escalation (Risky Operations)

This workflow handles potentially dangerous operations requiring expert validation.

```mermaid
sequenceDiagram
    participant BA as Builder Agent
    participant Hook as Pre-Tool Hook
    participant PE as Policy Engine
    participant LB as Lighthouse Bridge
    participant SE as Security Expert
    
    BA->>Hook: Execute: sudo apt update
    Hook->>PE: Validate command
    PE->>PE: Evaluate policies
    PE->>Hook: ESCALATE - Requires expert review
    Hook->>LB: Request expert validation
    LB->>SE: Review sudo command with context
    SE->>LB: APPROVED - Package update is safe
    LB->>Hook: APPROVED with expert reasoning
    Hook->>BA: Allow execution
    BA->>BA: Execute with expert blessing
    
    Note over BA,SE: Only risky operations hit expert validation
```

**Example Escalated Operations**:
- System commands: `sudo`, `rm -rf`, `chmod 777`
- Network operations: `curl external-api`, `wget`
- File modifications in protected paths: `/etc/`, `/usr/`, `/var/`
- Database operations: `DROP TABLE`, `DELETE FROM`

### Workflow 3: Expert Analysis with FUSE Mount

Expert agents use standard Unix tools on the mounted shadow filesystem for analysis.

```mermaid
sequenceDiagram
    participant BA as Builder Agent
    participant LB as Lighthouse Bridge
    participant FUSE as FUSE Mount
    participant SE as Security Expert
    
    BA->>LB: Write: /api/auth.py (new auth system)
    LB->>LB: Create shadow + update FUSE mount
    LB->>SE: Stream event: file_changed
    
    Note over SE: Expert uses standard tools on mounted filesystem
    SE->>FUSE: grep -r "password.*=" /mnt/lighthouse/project/
    FUSE->>LB: Read shadow content
    FUSE->>SE: Return search results
    
    SE->>FUSE: cat /mnt/lighthouse/project/api/auth.py  
    FUSE->>LB: Read shadow content
    FUSE->>SE: Return file content
    
    SE->>LB: Add AST-anchored annotation: "Line 47: Use bcrypt for password hashing"
    LB->>LB: Store annotation with tree-sitter span
    
    BA->>LB: Request file with annotations
    LB->>BA: Return auth.py + expert insights
    BA->>BA: Implement bcrypt hashing
    
    Note over SE,BA: Annotations survive code refactoring via AST spans
```

**Expert Analysis Capabilities**:
- **Security Expert**: Vulnerability scanning, secret detection, compliance checking
- **Performance Expert**: N+1 query detection, memory profiling, algorithmic analysis
- **Architecture Expert**: Circular dependency detection, design pattern opportunities, coupling analysis

### Workflow 4: Pair Programming Sessions

Real-time collaboration between builder and expert agents.

```python
# Create pair programming session
session_result = lighthouse_pair_request(
    requester="builder_agent",
    task="Optimize database query performance in user analytics",
    mode="collaborative"
)

# Expected response:
{
    "session_id": "pair_abc123def456",
    "status": "created",
    "partner_matching": "in_progress",
    "estimated_match_time": "< 30 seconds"
}

# Make suggestions during the session
suggestion_result = lighthouse_pair_suggest(
    session_id="pair_abc123def456",
    agent_id="performance_expert",
    suggestion="Consider adding a composite index on (user_id, timestamp) for this query",
    file_path="/src/analytics/queries.py",
    line=42
)
```

### Workflow 5: Time Travel Debugging

Debug issues by analyzing project history and state changes.

```python
# Find when a test started failing
debug_result = lighthouse_debug_test_failure("test_user_authentication")

# Expected response:
{
    "last_passing": {
        "timestamp": 1735230000,
        "snapshot": "pre_refactor_auth",
        "git_commit": "abc123def"
    },
    "first_failing": {
        "timestamp": 1735232000,
        "snapshot": "post_refactor_auth",
        "git_commit": "def456ghi"
    },
    "suspicious_changes": [
        {
            "file_path": "/api/auth.py",
            "operation": "modify",
            "lines_changed": [47, 48, 49],
            "agent": "builder_agent"
        }
    ],
    "time_window": 2000,  # seconds
    "affected_files": ["/api/auth.py", "/tests/test_auth.py"]
}

# Restore specific file to previous state
restore_result = lighthouse_restore_snapshot(
    snapshot_name="pre_refactor_auth",
    file_paths=["/api/auth.py"]
)
```

---

## Advanced Features

### Event Sourcing & Querying

Lighthouse maintains an immutable event log of all system changes, enabling powerful querying and time travel capabilities.

#### Event Types

```python
# File operations
class ShadowUpdateEvent:
    file_path: str
    operation: str  # create, update, delete
    content_hash: str
    agent_id: str
    timestamp: float
    
# Validation events  
class ValidationEvent:
    command_id: str
    command: str
    decision: str  # allow, block, escalate
    expert_input: bool
    reasoning: str

# Expert insights
class AnnotationEvent:
    file_path: str
    line: int
    message: str
    category: str
    expert_id: str
    ast_span: dict
```

#### Querying Event History

```python
# Find all security annotations in the last 24 hours
security_events = lighthouse_query_events(
    event_type="annotation",
    filters={
        "category": "security",
        "timestamp_since": time.time() - 86400
    }
)

# Find all file changes by specific agent
agent_changes = lighthouse_query_events(
    event_type="shadow_update",
    filters={
        "agent_id": "builder_agent_123",
        "file_pattern": "*.py"
    }
)
```

### Shadow Filesystem

The shadow filesystem provides expert agents with safe access to project files without filesystem permissions.

#### FUSE Mount Structure

```
/mnt/lighthouse/project/
├── src/
│   ├── api/
│   │   ├── auth.py          # Shadow of real file
│   │   └── routes.py        # + expert annotations
│   ├── models/
│   └── utils/
├── tests/
├── config/
└── .lighthouse/
    ├── annotations/         # Expert insights by file
    ├── snapshots/          # Project snapshots
    └── metrics/            # Performance data
```

#### Expert Agent File Operations

```python
# Expert agents use standard Unix tools
class SecurityExpert:
    def analyze_project_security(self):
        mount_path = "/mnt/lighthouse/project"
        
        # Find potential SQL injection patterns
        cmd = f"grep -r -n 'execute.*+.*' {mount_path} --include='*.py'"
        sql_injection_results = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # Find hardcoded secrets
        cmd = f"grep -r -E 'password|api[_-]?key|secret.*=.*[\"'][^\"']{8,}[\"']' {mount_path} --include='*.py'"
        secret_results = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # Process results and create annotations...
```

### AST-Anchored Intelligence

Lighthouse uses tree-sitter for AST parsing to create annotations that survive code refactoring.

#### AST Span Format

```python
class ASTSpan:
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    node_type: str      # function_definition, class_definition, etc.
    node_text: str      # actual code text
    confidence: float   # how confident we are in this span
```

#### Annotation Durability

```python
# Original code with annotation
def authenticate_user(username, password):  # Line 23
    # ANNOTATION: Consider rate limiting here
    result = db.execute(f"SELECT * FROM users WHERE username='{username}'")
    return result

# After refactoring - annotation automatically updates
def authenticate_user(username: str, password: str) -> bool:  # Line 25 (moved)
    # ANNOTATION: Consider rate limiting here (automatically preserved)
    query = "SELECT * FROM users WHERE username = %s"
    result = db.execute(query, [username])  # Fixed SQL injection
    return result is not None
```

---

## Expert Agent Specializations

### Security Expert

**Capabilities**:
- SQL injection detection
- XSS vulnerability scanning
- Hardcoded secret detection
- Authentication/authorization analysis
- Compliance checking (OWASP Top 10)

**Example Security Analysis**:

```python
# Automatic security scanning results
security_insights = lighthouse_get_security_analysis()

# Response includes:
{
    "vulnerabilities": [
        {
            "type": "sql_injection",
            "file": "/api/users.py",
            "line": 47,
            "severity": "critical",
            "message": "SQL injection vulnerability - use parameterized queries",
            "suggestion": "Replace string concatenation with db.execute(query, params)"
        },
        {
            "type": "hardcoded_secret",
            "file": "/config/settings.py", 
            "line": 12,
            "severity": "high",
            "message": "API key hardcoded - use environment variables",
            "suggestion": "Replace with os.getenv('API_KEY')"
        }
    ],
    "compliance_score": 7.2,
    "recommendations": [
        "Implement rate limiting on authentication endpoints",
        "Add CSRF protection to forms",
        "Enable HTTPS-only cookies"
    ]
}
```

### Performance Expert

**Capabilities**:
- N+1 query detection
- Memory usage analysis
- Algorithmic complexity assessment
- Database indexing recommendations
- Caching opportunity identification

**Example Performance Analysis**:

```python
# Performance bottleneck detection
performance_insights = lighthouse_get_performance_analysis()

# Response includes:
{
    "bottlenecks": [
        {
            "type": "n_plus_one_query",
            "file": "/api/analytics.py",
            "line": 89,
            "severity": "medium",
            "message": "N+1 query in user analytics loop",
            "suggestion": "Use select_related or prefetch_related",
            "estimated_impact": "50-200ms per request with 100+ users"
        },
        {
            "type": "missing_index",
            "file": "/models/events.py",
            "table": "events",
            "columns": ["user_id", "timestamp"],
            "suggestion": "CREATE INDEX idx_events_user_timestamp ON events(user_id, timestamp)"
        }
    ],
    "memory_analysis": {
        "peak_usage": "256MB",
        "potential_leaks": [],
        "optimization_opportunities": 3
    }
}
```

### Architecture Expert

**Capabilities**:
- Circular dependency detection
- Design pattern identification
- Single Responsibility Principle analysis
- Coupling/cohesion assessment
- Refactoring recommendations

**Example Architecture Analysis**:

```python
# Architecture assessment
architecture_insights = lighthouse_get_architecture_analysis()

# Response includes:
{
    "circular_dependencies": [
        {
            "cycle": ["/models/user.py", "/services/auth.py", "/models/user.py"],
            "suggestion": "Extract interface or move auth logic to separate module"
        }
    ],
    "design_patterns": {
        "opportunities": [
            {
                "pattern": "Factory",
                "file": "/services/notification.py",
                "suggestion": "Complex if/else chain could benefit from Factory pattern"
            }
        ],
        "violations": [
            {
                "principle": "Single Responsibility",
                "file": "/api/users.py",
                "class": "UserController",
                "responsibilities": 5,
                "suggestion": "Split into UserController, UserValidator, UserNotifier"
            }
        ]
    },
    "coupling_score": 6.8,
    "refactoring_priority": [
        {"file": "/models/user.py", "priority": "high", "reason": "Central to multiple cycles"},
        {"file": "/services/auth.py", "priority": "medium", "reason": "Authentication concerns scattered"}
    ]
}
```

---

## Integration & Deployment

### Development Environment Setup

#### Single Machine Development

```yaml
# docker-compose.dev.yml
version: '3.8'
services:
  lighthouse-bridge:
    image: lighthouse-bridge:latest
    ports:
      - "8765:8765"
    environment:
      - BRIDGE_MODE=development
      - LOG_LEVEL=debug
    volumes:
      - ./config:/config
      - ./snapshots:/snapshots
  
  builder-agent:
    image: claude-code:latest
    environment:
      - LIGHTHOUSE_BRIDGE_URL=http://lighthouse-bridge:8765
      - AGENT_ROLE=builder
      - HOOKS_ENABLED=true
    volumes:
      - ./project:/workspace
      - ./.claude:/workspace/.claude
  
  security-expert:
    image: claude-code:latest  
    environment:
      - LIGHTHOUSE_BRIDGE_URL=http://lighthouse-bridge:8765
      - AGENT_ROLE=security_expert
      - VFS_MODE=true
    # No filesystem volumes - works on shadows only
  
  performance-expert:
    image: claude-code:latest
    environment:
      - LIGHTHOUSE_BRIDGE_URL=http://lighthouse-bridge:8765
      - AGENT_ROLE=performance_expert
      - VFS_MODE=true
```

#### Startup Commands

```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up -d

# Verify all services
curl http://localhost:8765/status
curl http://localhost:8765/mcp/health

# View logs
docker-compose logs -f lighthouse-bridge
```

### Production Deployment

#### Small Team Setup

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  lighthouse-bridge:
    image: lighthouse-bridge:latest
    ports:
      - "8765:8765"
    environment:
      - BRIDGE_MODE=production
      - DATA_PERSISTENCE=true
      - METRICS_ENABLED=true
    volumes:
      - lighthouse-data:/data
      - lighthouse-snapshots:/snapshots
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8765/status"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    restart: unless-stopped
      
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=lighthouse
      - POSTGRES_USER=lighthouse
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  lighthouse-data:
  lighthouse-snapshots:
  redis-data:
  postgres-data:
```

#### Kubernetes Deployment

```yaml
# kubernetes/lighthouse-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lighthouse-bridge
spec:
  replicas: 3
  selector:
    matchLabels:
      app: lighthouse-bridge
  template:
    metadata:
      labels:
        app: lighthouse-bridge
    spec:
      containers:
      - name: lighthouse-bridge
        image: lighthouse-bridge:latest
        ports:
        - containerPort: 8765
        env:
        - name: BRIDGE_MODE
          value: "production"
        - name: DATA_PERSISTENCE
          value: "true"
        - name: REDIS_URL
          value: "redis://redis:6379"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: lighthouse-secrets
              key: database-url
        livenessProbe:
          httpGet:
            path: /status
            port: 8765
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8765
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: lighthouse-bridge-service
spec:
  selector:
    app: lighthouse-bridge
  ports:
  - port: 8765
    targetPort: 8765
  type: LoadBalancer
```

### Configuration Management

#### Environment Variables

```bash
# Bridge Configuration
BRIDGE_MODE=development|production
LOG_LEVEL=debug|info|warning|error
DATA_PERSISTENCE=true|false
METRICS_ENABLED=true|false

# Database Configuration
DATABASE_URL=postgresql://user:pass@host:port/db
REDIS_URL=redis://host:port

# Security Configuration
HMAC_SECRET_KEY=your-secure-secret-key
SESSION_TIMEOUT=3600
MAX_SESSIONS_PER_AGENT=3

# Expert Configuration
EXPERT_TIMEOUT=300
MAX_CONCURRENT_VALIDATIONS=10
ENABLE_AUTO_PAIR_MATCHING=true

# Performance Configuration
FUSE_MOUNT_POINT=/mnt/lighthouse
EVENT_STORE_RETENTION_DAYS=30
SNAPSHOT_RETENTION_COUNT=100
```

#### Configuration Files

```yaml
# config/lighthouse.yml
bridge:
  mode: production
  bind_host: "0.0.0.0"
  bind_port: 8765
  
validation:
  policy_engine: "opa"  # or "cedar"
  expert_timeout: 300
  max_concurrent: 10
  
filesystem:
  mount_point: "/mnt/lighthouse"
  shadow_storage: "/data/shadows"
  
experts:
  auto_pair_matching: true
  specializations:
    - security
    - performance  
    - architecture
    
monitoring:
  metrics_enabled: true
  prometheus_port: 9090
  log_level: info
```

---

## API Reference

### Authentication & Session Management

#### lighthouse_create_session

Create a new authenticated session with HMAC-SHA256 validation.

**Parameters**:
- `agent_id` (required): Unique agent identifier
- `ip_address` (optional): Client IP for security tracking
- `user_agent` (optional): Client user agent string

**Response Format**:
```
✅ Session created:
  Session ID: {session_id}
  Agent ID: {agent_id}
  Token: {agent_id}:{session_id}:{timestamp}:{hmac_signature}
  Created: {iso_timestamp}
  Security: HMAC-SHA256 validated
```

**Usage**:
```python
result = lighthouse_create_session("data_engineer", "192.168.1.100", "DataBot/2.0")
```

**Security Notes**:
- Maximum 3 concurrent sessions per agent
- Sessions expire after 1 hour of inactivity
- Cross-agent access is prevented and logged

#### lighthouse_validate_session

Validate an existing session token.

**Parameters**:
- `session_token` (required): Complete session token
- `agent_id` (required): Agent ID to validate against

**Response**:
```json
{
    "valid": true,
    "session_id": "abc123def456",
    "created_at": 1735234567.123,
    "last_activity": 1735234890.456,
    "expires_at": 1735238167.123
}
```

### Shadow Filesystem Operations

#### lighthouse_shadow_search

Search across shadow filesystem files with pattern matching.

**Parameters**:
- `pattern` (required): Search pattern (regex supported)
- `file_types` (optional): File extensions to include
- `session_token` (optional): Session token for authentication

**Response**:
```json
{
    "matches": [
        {
            "file_path": "/src/api/auth.py",
            "line_number": 47,
            "line_content": "password = hash_password(raw_password)",
            "context": ["def authenticate(username, password):", "    # Validate user credentials", "    password = hash_password(raw_password)"]
        }
    ],
    "total_matches": 1,
    "search_time_ms": 45,
    "files_searched": 23
}
```

**Rate Limits**: 100 searches per minute per agent

#### lighthouse_shadow_annotate

Add expert annotations to shadow files with AST anchoring.

**Parameters**:
- `file_path` (required): Target file path
- `line` (required): Line number for annotation
- `message` (required): Annotation message
- `category` (optional): Annotation category
- `session_token` (optional): Session token

**Response**:
```json
{
    "annotation_id": "ann_abc123def456",
    "status": "created",
    "ast_span": {
        "start_line": 47,
        "end_line": 47,
        "start_column": 4,
        "end_column": 35,
        "node_type": "assignment",
        "confidence": 0.95
    }
}
```

### Pair Programming

#### lighthouse_pair_request

Create a pair programming session request.

**Parameters**:
- `requester` (required): Agent ID making the request
- `task` (required): Task description
- `mode` (optional): Collaboration mode ("collaborative", "review", "mentoring")
- `session_token` (optional): Session token

**Response**:
```json
{
    "session_id": "pair_abc123def456",
    "status": "created",
    "partner_matching": "in_progress",
    "estimated_match_time": "< 30 seconds",
    "task": "Optimize database query performance",
    "mode": "collaborative"
}
```

#### lighthouse_pair_suggest

Make suggestions during pair programming sessions.

**Parameters**:
- `session_id` (required): Pair session ID
- `agent_id` (required): Your agent ID
- `suggestion` (required): Suggestion text
- `file_path` (optional): Relevant file
- `line` (optional): Relevant line number
- `session_token` (optional): Session token

**Response**:
```json
{
    "suggestion_id": "sugg_abc123def456",
    "status": "submitted",
    "partner_notified": true,
    "timestamp": 1735234567.123
}
```

### Snapshot & Time Travel

#### lighthouse_create_snapshot

Create project snapshots for time travel debugging.

**Parameters**:
- `name` (required): Snapshot name
- `description` (optional): Snapshot description
- `session_token` (optional): Session token

**Response**:
```json
{
    "snapshot_id": "snap_abc123def456",
    "name": "pre_migration_state",
    "timestamp": 1735234567.123,
    "file_count": 245,
    "total_size": "2.4MB",
    "git_commit": "abc123def456ghi"
}
```

#### lighthouse_restore_snapshot

Restore files from a previous snapshot.

**Parameters**:
- `snapshot_name` (required): Snapshot to restore from
- `file_paths` (optional): Specific files to restore (all if not provided)
- `session_token` (optional): Session token

**Response**:
```json
{
    "restored_files": ["/api/auth.py", "/models/user.py"],
    "snapshot": "pre_migration_state",
    "timestamp": 1735234567.123,
    "git_integration": "changes_staged"
}
```

### Expert Analysis

#### lighthouse_get_security_analysis

Get comprehensive security analysis from security expert.

**Parameters**:
- `scope` (optional): Analysis scope ("full", "recent_changes", "specific_files")
- `file_paths` (optional): Specific files to analyze
- `session_token` (optional): Session token

**Response**: See [Security Expert](#security-expert) section for detailed format.

#### lighthouse_get_performance_analysis

Get performance analysis from performance expert.

**Parameters**: Same as security analysis

**Response**: See [Performance Expert](#performance-expert) section for detailed format.

#### lighthouse_get_architecture_analysis

Get architecture analysis from architecture expert.

**Parameters**: Same as security analysis

**Response**: See [Architecture Expert](#architecture-expert) section for detailed format.

---

## Troubleshooting & Best Practices

### Common Issues & Solutions

#### 1. "Security validation failed: Agent X is not authenticated"

**Root Cause**: Session token doesn't match agent ID or session is invalid.

**Solution**:
```python
# ❌ Wrong - agent ID mismatch
token = "alice:session123:timestamp:sig"
lighthouse_pair_request("bob", "task", "collaborative", token)

# ✅ Correct - matching agent IDs
bob_token = "bob:session456:timestamp:sig"
lighthouse_pair_request("bob", "task", "collaborative", bob_token)

# Best practice: Create fresh session if uncertain
result = lighthouse_create_session("bob")
token = extract_token_from_result(result)
lighthouse_pair_request("bob", "task", "collaborative", token)
```

#### 2. "Bridge connection failed" or "Connection refused"

**Root Cause**: Bridge server not running or network connectivity issues.

**Diagnosis**:
```bash
# Check if bridge is running
curl http://localhost:8765/status

# Check Docker containers
docker ps | grep lighthouse

# Check network connectivity
netstat -tlnp | grep 8765

# View bridge logs
docker logs lighthouse-bridge
```

**Solutions**:
```bash
# Start bridge if not running
docker-compose up -d lighthouse-bridge

# Restart bridge with fresh state
docker-compose restart lighthouse-bridge

# Check configuration
docker-compose config
```

#### 3. "Rate limit exceeded"

**Root Cause**: Too many requests in time window.

**Rate Limits**:
- `lighthouse_shadow_search`: 100/minute
- `lighthouse_shadow_annotate`: 50/5 minutes  
- `lighthouse_pair_suggest`: 200/5 minutes
- `lighthouse_create_snapshot`: 10/hour

**Solution**:
```python
import time
from functools import wraps

def rate_limited_retry(max_retries=3, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "rate limit" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        print(f"Rate limited, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    raise e
            return None
        return wrapper
    return decorator

@rate_limited_retry()
def search_with_retry(pattern, file_types, token):
    return lighthouse_shadow_search(pattern, file_types, token)
```

#### 4. "Expert agent unavailable" or "Validation timeout"

**Root Cause**: Expert agents not running or overloaded.

**Diagnosis**:
```bash
# Check expert agent status
curl http://localhost:8765/experts/status

# View expert agent logs
docker logs security-expert
docker logs performance-expert
```

**Solutions**:
- Start expert agents: `docker-compose up -d security-expert performance-expert`
- Scale expert agents: `docker-compose up -d --scale security-expert=2`
- Increase validation timeout in configuration

### Best Practices

#### 1. Session Management

```python
class RobustLighthouseClient:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.session_token = None
        self.session_created_at = None
        self.session_timeout = 3600  # 1 hour
    
    def ensure_authenticated(self):
        """Ensure valid session, create if needed"""
        import time
        
        if (self.session_token and self.session_created_at and 
            (time.time() - self.session_created_at) < (self.session_timeout - 300)):  # 5 min buffer
            return self.session_token
        
        # Create new session
        result = lighthouse_create_session(self.agent_id)
        self.session_token = self._extract_token(result)
        self.session_created_at = time.time()
        return self.session_token
    
    def make_request(self, tool_func, *args, **kwargs):
        """Make authenticated request with automatic retry"""
        token = self.ensure_authenticated()
        try:
            return tool_func(*args, session_token=token, **kwargs)
        except Exception as e:
            if "Invalid session" in str(e):
                # Re-authenticate and retry once
                token = self.ensure_authenticated()
                return tool_func(*args, session_token=token, **kwargs)
            raise e
```

#### 2. Error Handling

```python
def robust_lighthouse_operation(operation_func, *args, **kwargs):
    """Wrapper for robust Lighthouse operations"""
    try:
        return operation_func(*args, **kwargs)
    except Exception as e:
        error_msg = str(e).lower()
        
        if "rate limit" in error_msg:
            print("Rate limited - implement backoff strategy")
            raise RateLimitException(str(e))
        elif "invalid session" in error_msg:
            print("Session invalid - re-authenticate")
            raise AuthenticationException(str(e))
        elif "bridge connection" in error_msg:
            print("Bridge unavailable - check connection")
            raise ConnectionException(str(e))
        elif "expert unavailable" in error_msg:
            print("Expert agents unavailable - check deployment")
            raise ExpertUnavailableException(str(e))
        else:
            print(f"Unknown error: {e}")
            raise e
```

#### 3. Performance Optimization

```python
class OptimizedLighthouseClient:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.session_token = None
        self._search_cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    def cached_search(self, pattern, file_types=None):
        """Search with result caching"""
        import time
        import hashlib
        
        # Create cache key
        cache_key = hashlib.md5(f"{pattern}:{file_types}".encode()).hexdigest()
        
        # Check cache
        if cache_key in self._search_cache:
            cached_result, timestamp = self._search_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                return cached_result
        
        # Perform search
        result = lighthouse_shadow_search(pattern, file_types, self.session_token)
        
        # Cache result
        self._search_cache[cache_key] = (result, time.time())
        return result
    
    def batch_annotate_with_grouping(self, annotations):
        """Group annotations by file for efficiency"""
        from collections import defaultdict
        
        grouped = defaultdict(list)
        for ann in annotations:
            grouped[ann['file_path']].append(ann)
        
        results = []
        for file_path, file_annotations in grouped.items():
            # Process in batches of 20 to respect rate limits
            for i in range(0, len(file_annotations), 20):
                batch = file_annotations[i:i+20]
                result = lighthouse_batch_annotate(batch, self.session_token)
                results.append(result)
                
                # Add small delay between batches
                if i + 20 < len(file_annotations):
                    time.sleep(1)
        
        return results
```

#### 4. Integration Patterns

```python
class LighthouseIntegration:
    """Integration patterns for common development workflows"""
    
    def __init__(self, agent_id):
        self.client = RobustLighthouseClient(agent_id)
    
    async def pre_commit_analysis(self, changed_files):
        """Run expert analysis before commits"""
        # Create snapshot before analysis
        snapshot_name = f"pre_commit_{int(time.time())}"
        await self.client.make_request(
            lighthouse_create_snapshot,
            snapshot_name,
            "Pre-commit analysis snapshot"
        )
        
        # Run security analysis on changed files
        security_result = await self.client.make_request(
            lighthouse_get_security_analysis,
            scope="specific_files",
            file_paths=changed_files
        )
        
        # Run performance analysis
        performance_result = await self.client.make_request(
            lighthouse_get_performance_analysis,
            scope="specific_files", 
            file_paths=changed_files
        )
        
        return {
            'snapshot': snapshot_name,
            'security': security_result,
            'performance': performance_result
        }
    
    async def collaborative_debugging(self, failing_test):
        """Start collaborative debugging session"""
        # Create pair programming request
        pair_result = await self.client.make_request(
            lighthouse_pair_request,
            self.client.agent_id,
            f"Debug failing test: {failing_test}",
            "debugging"
        )
        
        # Get time travel analysis  
        debug_result = await self.client.make_request(
            lighthouse_debug_test_failure,
            failing_test
        )
        
        return {
            'pair_session': pair_result['session_id'],
            'failure_analysis': debug_result
        }
```

---

## Production Operations

### Monitoring & Observability

#### Key Metrics

Lighthouse exposes comprehensive metrics for production monitoring:

```python
# System Health Metrics
lighthouse.bridge.uptime_seconds                    # Bridge uptime
lighthouse.bridge.active_agents_total               # Currently active agents
lighthouse.bridge.session_count                     # Active sessions

# Validation Metrics  
lighthouse.validation.commands_total                # Total commands validated
lighthouse.validation.expert_escalations_total      # Commands requiring expert review
lighthouse.validation.blocked_commands_total        # Blocked dangerous commands

# Expert Agent Metrics
lighthouse.experts.insights_generated_total         # Expert insights created
lighthouse.experts.pair_sessions_total              # Pair programming sessions
lighthouse.experts.analysis_duration_seconds        # Expert analysis time

# Shadow Filesystem Metrics
lighthouse.shadows.files_tracked_total              # Files in shadow system
lighthouse.shadows.updates_total                    # Shadow file updates
lighthouse.shadows.fuse_operations_total            # FUSE mount operations

# Performance Metrics
lighthouse.performance.request_duration_seconds     # Request latency
lighthouse.performance.validation_duration_seconds  # Validation latency
lighthouse.performance.error_rate                   # Error rate percentage
```

#### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'lighthouse-bridge'
    static_configs:
      - targets: ['lighthouse-bridge:9090']
    scrape_interval: 5s
    metrics_path: /metrics
```

#### Grafana Dashboards

Key dashboards for production monitoring:

1. **System Overview**:
   - Bridge uptime and health
   - Active agents and sessions
   - Request rate and latency

2. **Expert Activity**:
   - Expert insights generated over time
   - Pair programming session activity
   - Analysis performance by expert type

3. **Security Monitoring**:
   - Blocked commands by type
   - Security vulnerabilities detected
   - Authentication failures

4. **Performance Tracking**:
   - Validation latency distribution
   - Shadow filesystem performance
   - Resource usage trends

### Health Checks

#### Bridge Health Endpoint

```bash
# Basic health check
curl http://localhost:8765/health

# Expected response:
{
    "status": "healthy",
    "checks": {
        "database": "connected",
        "redis": "connected", 
        "fuse_mount": "mounted",
        "expert_agents": "3/3 available"
    },
    "uptime_seconds": 86400,
    "version": "2.1.0"
}
```

#### Deep Health Validation

```bash
# Comprehensive health check with validation
curl http://localhost:8765/health/deep

# Response includes:
{
    "status": "healthy",
    "detailed_checks": {
        "bridge_core": {
            "event_store": "operational",
            "session_manager": "operational", 
            "validation_engine": "operational"
        },
        "expert_agents": {
            "security_expert": {
                "status": "healthy",
                "last_activity": 1735234567,
                "insights_generated_24h": 45
            },
            "performance_expert": {
                "status": "healthy",
                "last_activity": 1735234890,
                "insights_generated_24h": 32
            }
        },
        "shadow_filesystem": {
            "fuse_mount_status": "healthy",
            "files_tracked": 1247,
            "last_sync": 1735234567
        }
    }
}
```

### Backup & Recovery

#### Automated Backup Strategy

```bash
#!/bin/bash
# backup-lighthouse.sh

BACKUP_DIR="/backup/lighthouse/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

# Backup event store
docker exec lighthouse-bridge pg_dump lighthouse_events > "$BACKUP_DIR/events.sql"

# Backup shadow filesystem snapshots
docker cp lighthouse-bridge:/data/snapshots "$BACKUP_DIR/"

# Backup configuration
docker cp lighthouse-bridge:/config "$BACKUP_DIR/"

# Create compressed archive
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"

# Upload to S3 (optional)
aws s3 cp "$BACKUP_DIR.tar.gz" s3://lighthouse-backups/
```

#### Recovery Procedures

```bash
#!/bin/bash
# restore-lighthouse.sh

BACKUP_FILE="$1"
TEMP_DIR="/tmp/lighthouse-restore"

# Extract backup
mkdir -p "$TEMP_DIR"
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Stop services
docker-compose down

# Restore database
docker-compose up -d postgres
sleep 10
cat "$TEMP_DIR"/*/events.sql | docker exec -i lighthouse-postgres psql -U lighthouse

# Restore snapshots and config
docker cp "$TEMP_DIR"/*/snapshots lighthouse-bridge:/data/
docker cp "$TEMP_DIR"/*/config lighthouse-bridge:/

# Restart services
docker-compose up -d

echo "Recovery completed successfully"
```

### Security Operations

#### Security Event Monitoring

```bash
# Monitor authentication failures
curl http://localhost:8765/security/events?type=auth_failure&hours=24

# Monitor blocked commands
curl http://localhost:8765/security/events?type=blocked_command&hours=1

# Get security summary
curl http://localhost:8765/security/summary
```

#### Incident Response

```python
# security-incident-response.py
import requests
from datetime import datetime, timedelta

class LighthouseSecurityMonitor:
    def __init__(self, bridge_url="http://localhost:8765"):
        self.bridge_url = bridge_url
    
    def check_security_incidents(self):
        """Check for security incidents in last hour"""
        
        # Check for suspicious authentication patterns
        auth_failures = self.get_auth_failures(hours=1)
        if len(auth_failures) > 10:
            self.alert("Multiple authentication failures detected", auth_failures)
        
        # Check for blocked dangerous commands
        blocked_commands = self.get_blocked_commands(hours=1)
        dangerous_patterns = ['rm -rf', 'sudo rm', 'chmod 777']
        
        for command in blocked_commands:
            for pattern in dangerous_patterns:
                if pattern in command['command']:
                    self.alert(f"Dangerous command blocked: {pattern}", command)
        
        # Check expert agent availability
        expert_status = self.get_expert_status()
        unavailable_experts = [e for e in expert_status if e['status'] != 'healthy']
        
        if len(unavailable_experts) > 1:
            self.alert("Multiple expert agents unavailable", unavailable_experts)
    
    def alert(self, message, details):
        """Send security alert (implement your alerting mechanism)"""
        print(f"🚨 SECURITY ALERT: {message}")
        print(f"Details: {details}")
        # Integrate with your alerting system (PagerDuty, Slack, etc.)
```

### Performance Tuning

#### Optimization Guidelines

1. **Bridge Configuration**:
```yaml
# config/performance.yml
bridge:
  worker_threads: 4  # CPU cores
  max_concurrent_validations: 20
  validation_timeout: 30  # seconds
  
cache:
  redis_maxmemory: "256mb"
  policy_cache_ttl: 3600
  session_cache_ttl: 1800

shadow_filesystem:
  max_files_tracked: 10000
  sync_interval: 30  # seconds
  fuse_cache_timeout: 60
```

2. **Database Optimization**:
```sql
-- Optimize event store queries
CREATE INDEX CONCURRENTLY idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX CONCURRENTLY idx_events_agent_id ON events(agent_id, timestamp);
CREATE INDEX CONCURRENTLY idx_events_type ON events(event_type, timestamp);

-- Optimize session queries  
CREATE INDEX CONCURRENTLY idx_sessions_agent_id ON sessions(agent_id);
CREATE INDEX CONCURRENTLY idx_sessions_active ON sessions(active, expires_at);
```

3. **Resource Allocation**:
```yaml
# docker-compose.prod.yml resource limits
services:
  lighthouse-bridge:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
          
  security-expert:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
```

---

This comprehensive user manual provides complete coverage of the Lighthouse multi-agent coordination system, from basic authentication to advanced production operations. Each section includes practical examples, troubleshooting guidance, and best practices for successful implementation and operation.

The manual maintains the existing authentication and MCP tool documentation while significantly expanding coverage to include all architectural capabilities described in the HLD document. This ensures users have complete guidance for leveraging Lighthouse's sophisticated multi-agent coordination, expert analysis, and time travel debugging capabilities.