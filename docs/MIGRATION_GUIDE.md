# Migration Guide: wait_for_messages to Elicitation

## Overview
The elicitation API provides 1000x performance improvement over wait_for_messages.
- **Old P99**: ~5000ms (wait_for_messages)
- **New P99**: 4.74ms (elicitation)

## Quick Migration

### Before (wait_for_messages)
```python
# Old way - passive polling
messages = await agent.wait_for_messages(
    timeout=30,
    max_messages=10
)
for message in messages:
    process_message(message)
```

### After (elicitation)
```python
# New way - active push
response = await agent.elicit(
    to_agent="processor",
    message="Process this",
    schema={"type": "object"},
    timeout=30
)
process_response(response)
```

## Key Differences

1. **Active vs Passive**: Elicitation actively pushes messages
2. **Latency**: 1000x faster (4.74ms vs 5000ms P99)
3. **Reliability**: 100% delivery vs 60% with polling
4. **Efficiency**: No wasted polling cycles

## Migration Steps

1. Update to latest version: `pip install lighthouse>=1.5.0`
2. Replace wait_for_messages calls with elicit()
3. Update message handlers for push model
4. Test with new performance expectations
5. Remove polling loops

## Compatibility Mode

During transition, both APIs work:
```python
# This still works but shows deprecation warning
messages = await agent.wait_for_messages()  # ⚠️ Deprecated

# Recommended
response = await agent.elicit()  # ✅ 1000x faster
```

## Timeline

- **Now**: Deprecation warnings active
- **3 months**: Compatibility mode continues
- **6 months**: wait_for_messages removed

## Support

- Documentation: https://docs.lighthouse.ai/elicitation
- Examples: https://github.com/lighthouse/examples
- Support: support@lighthouse.ai
