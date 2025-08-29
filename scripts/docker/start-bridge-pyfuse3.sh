#!/bin/bash
# Lighthouse Bridge Container Startup Script - pyfuse3 version
set -e

echo "🚀 Starting Lighthouse Bridge Server with pyfuse3..."
echo "Environment: ${LIGHTHOUSE_ENV:-development}"
echo "Port: ${LIGHTHOUSE_PORT:-8765}"
echo "FUSE Backend: pyfuse3 (libfuse3)"

# Force use of container Python
CONTAINER_PYTHON="/opt/venv/bin/python"

if [[ ! -x "$CONTAINER_PYTHON" ]]; then
    echo "❌ CRITICAL: Container Python not found at $CONTAINER_PYTHON"
    exit 1
fi

echo "Python: $CONTAINER_PYTHON"
echo "Python version: $($CONTAINER_PYTHON --version)"

# Verify libfuse3 is available
echo "Checking FUSE3 library..."
if [[ -f "/usr/lib/x86_64-linux-gnu/libfuse3.so.3" ]]; then
    echo "✅ libfuse3 found at /usr/lib/x86_64-linux-gnu/libfuse3.so.3"
    ldd /usr/lib/x86_64-linux-gnu/libfuse3.so.3 | head -3
else
    echo "❌ libfuse3 not found - FUSE will not work"
    exit 1
fi

# Test pyfuse3 import and functionality
echo "Testing pyfuse3 integration..."
$CONTAINER_PYTHON -c "
import sys
print(f'Python path: {sys.executable}')

# Test pyfuse3 import
try:
    import pyfuse3
    print('✅ pyfuse3 successfully imported')
    print(f'   pyfuse3 version: {pyfuse3.__version__}')
    
    # Test trio (required by pyfuse3)
    import trio
    print('✅ trio successfully imported (required for pyfuse3 async)')
    
    # Verify FUSE3 support
    if hasattr(pyfuse3, 'FUSE_USE_VERSION'):
        print(f'   FUSE protocol version: {pyfuse3.FUSE_USE_VERSION}')
    else:
        print('   FUSE protocol: pyfuse3 ready (version check not available)')
    
except ImportError as e:
    print(f'❌ pyfuse3 import failed: {e}')
    sys.exit(1)

# Test optional packages
optional_packages = [
    ('scikit-learn', 'sklearn'),
    ('tree-sitter', 'tree_sitter'),
    ('numpy', 'numpy'),
    ('scipy', 'scipy')
]

print('\\nOptional packages:')
for name, module in optional_packages:
    try:
        exec(f'import {module}')
        print(f'  ✅ {name}')
    except ImportError:
        print(f'  ⚠️  {name} not available')

print('\\n✅ Container ready for pyfuse3 operations')
"

# Exit code check
if [ $? -ne 0 ]; then
    echo "❌ pyfuse3 validation failed"
    exit 1
fi

# Set working directory
cd /app

# Ensure PYTHONPATH includes our source
export PYTHONPATH="/app/src:${PYTHONPATH:-}"

# Create required directories
mkdir -p "${LIGHTHOUSE_EVENT_STORE_PATH:-/var/lib/lighthouse/events}"
mkdir -p "${LIGHTHOUSE_SNAPSHOT_PATH:-/var/lib/lighthouse/snapshots}"
mkdir -p "${LIGHTHOUSE_CACHE_PATH:-/var/lib/lighthouse/cache}"
mkdir -p "${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}"

# Check if /dev/fuse is available
if [[ ! -c /dev/fuse ]]; then
    echo "⚠️  Warning: /dev/fuse not available. FUSE mount will not work."
    echo "   Run container with: --cap-add SYS_ADMIN --device /dev/fuse"
fi

# Start the Bridge with pyfuse3 backend
echo ""
echo "========================================="
echo "Starting Lighthouse Bridge with pyfuse3..."
echo "========================================="

# Start the actual Bridge server (not MCP server which runs on host)
exec "$CONTAINER_PYTHON" /app/src/lighthouse/bridge/run_bridge.py