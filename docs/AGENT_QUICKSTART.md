# Lighthouse Agent Quick Start

## You Are an Agent in a Multi-Agent System

You're connected to other AI agents through the Lighthouse Bridge. Communication is 1000x faster than traditional methods using the elicitation protocol.

## Essential Commands

### 1. Initialize Yourself
```python
# Register your expertise
await lighthouse_register_expert(
    agent_id="your_specialty_expert",  # e.g., "security_expert"
    agent_type="your_specialty",        # e.g., "security"
    capabilities=["skill1", "skill2"]   # e.g., ["vulnerability_analysis", "threat_modeling"]
)
```

### 2. Communicate with Other Agents (ALWAYS use this, not wait_for_messages)
```python
# Ask another agent for information
response = await lighthouse_elicit_information(
    to_agent="security_expert",
    message="Analyze this code for vulnerabilities",
    schema={
        "type": "object",
        "properties": {
            "vulnerabilities": {"type": "array"},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]}
        }
    },
    timeout_seconds=30
)
```

### 3. Check and Respond to Requests
```python
# Check if other agents need your expertise
pending = await lighthouse_check_elicitations()

# Respond to requests
for request in pending["elicitations"]:
    await lighthouse_respond_to_elicitation(
        elicitation_id=request["id"],
        response_type="accept",
        data={
            "vulnerabilities": [],
            "risk_level": "low"
        }
    )
```

### 4. Store Important Events
```python
# Record actions in the shared event store
await lighthouse_store_event(
    event_type="ANALYSIS_COMPLETED",
    event_data={"result": "secure", "confidence": 0.95},
    agent_id="security_expert"
)
```

### 5. Validate Dangerous Commands
```python
# Check before running risky operations
validation = await lighthouse_validate_command(
    tool_name="Bash",
    tool_input={"command": "rm -rf /path"},
    agent_id="your_agent_id"
)

if not validation["approved"]:
    print(f"Command blocked: {validation['reasoning']}")
```

## Key Performance Metrics
- **Response Time**: 4.74ms P99 (was 5000ms with polling)
- **Reliability**: 100% message delivery
- **Concurrency**: Supports 100-500 agents
- **Rate Limits**: 10 req/min, 20 resp/min per agent

## Common Agent Types

### Security Expert
```python
capabilities = ["vulnerability_analysis", "threat_modeling", "security_review", "penetration_testing"]
```

### Performance Expert
```python
capabilities = ["performance_analysis", "optimization", "profiling", "scalability_assessment"]
```

### Architecture Expert
```python
capabilities = ["system_design", "pattern_recommendation", "scalability_planning", "api_design"]
```

### DevOps Expert
```python
capabilities = ["deployment", "monitoring", "infrastructure", "ci_cd", "containerization"]
```

### Test Engineer
```python
capabilities = ["test_design", "test_automation", "quality_assurance", "coverage_analysis"]
```

## Quick Troubleshooting

| Error | Solution |
|-------|----------|
| "Agent not authenticated" | Run `lighthouse_create_session()` first |
| "Rate limit exceeded" | Wait 60s (limit: 10 req/min) |
| "Elicitation timeout" | Target agent may be offline, increase timeout |
| "Bridge not available" | Check if Bridge is running at localhost:8765 |

## Three Golden Rules

1. **NEVER use wait_for_messages** - It's been removed. Always use `lighthouse_elicit_information`
2. **ALWAYS validate dangerous commands** - Use `lighthouse_validate_command` before risky operations
3. **COMMUNICATE efficiently** - The system is 1000x faster, use it for real-time collaboration

## Example: Complete Agent Workflow

```python
# 1. Register yourself
await lighthouse_register_expert(
    agent_id="code_reviewer",
    agent_type="review",
    capabilities=["code_review", "best_practices", "refactoring"]
)

# 2. Wait for work
pending = await lighthouse_check_elicitations()
print(f"You have {pending['count']} requests waiting")

# 3. Get help from other experts
security_check = await lighthouse_elicit_information(
    to_agent="security_expert",
    message="Is this SQL query safe from injection?",
    schema={"type": "object", "properties": {"safe": {"type": "boolean"}}}
)

# 4. Complete your work
await lighthouse_store_event(
    event_type="REVIEW_COMPLETED",
    event_data={"files_reviewed": 5, "issues_found": 2},
    agent_id="code_reviewer"
)

# 5. Collaborate with others
await lighthouse_start_collaboration(
    collaboration_type="pair_programming",
    participants=["code_reviewer", "test_engineer"],
    objective="Implement comprehensive test suite"
)
```

## Remember

- You're part of a team of specialized AI agents
- Communication is instant (4.74ms) - use it liberally
- Every action is recorded in the event store
- Security is enforced at every level
- The Bridge at localhost:8765 coordinates everything

Start with `lighthouse_register_expert()` and you're ready to collaborate!