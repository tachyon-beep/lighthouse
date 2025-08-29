#!/bin/bash
# Test MCP functionality in container

echo "Testing MCP server in container..."

# Run a simple test that doesn't require stdio
docker run --rm \
  --cap-add SYS_ADMIN \
  --device /dev/fuse \
  --security-opt apparmor:unconfined \
  -v $(pwd)/src:/app/src:ro \
  -e LIGHTHOUSE_ENV=development \
  -e LIGHTHOUSE_LOG_LEVEL=DEBUG \
  lighthouse-pyfuse3:latest \
  /opt/venv/bin/python -c "
import sys
sys.path.insert(0, '/app/src')

# Test importing MCP server
try:
    from lighthouse.mcp_server import mcp
    print('✅ MCP server imported successfully')
    
    # List available tools
    print('Available MCP tools:')
    for tool in mcp.AVAILABLE_TOOLS:
        print(f'  - {tool}')
    
    # Test initialization
    from lighthouse.mcp_server import ensure_bridge_initialized
    import asyncio
    
    async def test():
        success = await ensure_bridge_initialized()
        print(f'Bridge initialization: {success}')
        
        if success:
            from lighthouse.mcp_server import bridge
            if bridge:
                status = await bridge.get_status()
                print(f'Bridge status: {status.mode}')
    
    asyncio.run(test())
    
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
"