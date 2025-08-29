#!/bin/bash
# Simplified Lighthouse Bridge Container Startup Script
set -e

echo "🚀 Starting Lighthouse Bridge Server (Simplified)..."
echo "Environment: ${LIGHTHOUSE_ENV:-development}"
echo "Port: ${LIGHTHOUSE_PORT:-8765}"

# CRITICAL: Force use of container Python - never rely on PATH alone
CONTAINER_PYTHON="/opt/venv/bin/python"

if [[ ! -x "$CONTAINER_PYTHON" ]]; then
    echo "❌ CRITICAL: Container Python not found at $CONTAINER_PYTHON"
    exit 1
fi

echo "Python: $CONTAINER_PYTHON"
echo "Python version: $($CONTAINER_PYTHON --version)"

# Verify we have all required libraries
echo "Checking library dependencies..."
ldd_output=$(ldd /usr/lib/x86_64-linux-gnu/libfuse.so.2 2>/dev/null || echo "libfuse.so.2 not found")
echo "libfuse.so.2 dependencies: $ldd_output"

# Check if libfuse2 is properly installed
if [[ -f "/usr/lib/x86_64-linux-gnu/libfuse.so.2" ]]; then
    echo "✅ libfuse2 found at /usr/lib/x86_64-linux-gnu/libfuse.so.2"
else
    echo "⚠️  libfuse2 not found - FUSE may not work"
fi

# Verify fusepy can find libfuse
echo "Checking FUSE/Python integration..."
$CONTAINER_PYTHON -c "
import sys
print(f'Python path: {sys.executable}')
print('Testing fusepy import...')
try:
    import fuse
    print('✅ fusepy successfully imported')
    
    # Try to check FUSE version 
    try:
        version = fuse.FUSE_VERSION if hasattr(fuse, 'FUSE_VERSION') else 'unknown'
        print(f'   FUSE version: {version}')
    except:
        print('   FUSE version: unable to determine')
        
    # Test basic FUSE functionality
    try:
        from fuse import FUSE, FuseOSError, Operations
        print('✅ FUSE classes successfully imported')
    except Exception as e:
        print(f'⚠️  FUSE classes import failed: {e}')
        
except ImportError as e:
    print(f'❌ fusepy import failed: {e}')
    print('   Bridge will run in degraded mode without FUSE mount')
except Exception as e:
    print(f'⚠️  FUSE test failed: {e}')
    print('   Bridge will run in degraded mode without FUSE mount')
"

# Set working directory
cd /app

# Ensure PYTHONPATH includes our source (redundant with Dockerfile ENV but safe)
export PYTHONPATH="/app/src:${PYTHONPATH:-}"

# Create event store directory if it doesn't exist
mkdir -p "${LIGHTHOUSE_EVENT_STORE_PATH:-/var/lib/lighthouse/events}"

# Verify our MCP server module exists
if [[ ! -f "/app/src/lighthouse/mcp_server.py" ]]; then
    echo "❌ CRITICAL: MCP server module not found at /app/src/lighthouse/mcp_server.py"
    exit 1
fi

# Start the MCP server bridge (which handles FUSE fallback gracefully)
echo "Starting MCP server with Bridge integration..."
echo "Command: $CONTAINER_PYTHON -m lighthouse.mcp_server"

# Use exec to replace shell process with Python process for proper signal handling
exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server