#!/bin/bash
# Lighthouse Bridge Container Startup Script
set -e

echo "🚀 Starting Lighthouse Bridge Server..."
echo "Environment: ${LIGHTHOUSE_ENV:-development}"
echo "Port: ${LIGHTHOUSE_PORT:-8765}"
echo "Mount Point: ${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}"

# Function to handle signals for graceful shutdown
shutdown() {
    echo "🛑 Received shutdown signal, stopping Bridge..."
    if [ -n "$BRIDGE_PID" ]; then
        kill -SIGTERM "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
    fi
    
    # Unmount FUSE if mounted
    if mountpoint -q "${LIGHTHOUSE_MOUNT_POINT}"; then
        echo "Unmounting FUSE filesystem..."
        fusermount3 -u "${LIGHTHOUSE_MOUNT_POINT}" 2>/dev/null || true
    fi
    
    echo "✅ Bridge stopped gracefully"
    exit 0
}

# Trap signals for graceful shutdown
trap shutdown SIGTERM SIGINT

# Ensure required directories exist
mkdir -p "${LIGHTHOUSE_EVENT_STORE_PATH:-/var/lib/lighthouse/events}"
mkdir -p "${LIGHTHOUSE_SNAPSHOT_PATH:-/var/lib/lighthouse/snapshots}"
mkdir -p "${LIGHTHOUSE_CACHE_PATH:-/var/lib/lighthouse/cache}"
mkdir -p "${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}"
mkdir -p "/app/logs"

# Check FUSE availability
if [ ! -c /dev/fuse ]; then
    echo "⚠️  Warning: /dev/fuse not available. FUSE mount will be disabled."
    export LIGHTHOUSE_DISABLE_FUSE=true
fi

# Verify Python environment
echo "Python version: $(python --version)"
echo "Python path: $(which python)"
echo "PYTHONPATH: ${PYTHONPATH}"

# Check if running in production mode
if [ "$1" == "--production" ] || [ "${LIGHTHOUSE_ENV}" == "production" ]; then
    echo "📦 Running in production mode"
    
    # Production optimizations
    export PYTHONOPTIMIZE=2
    export PYTHONDONTWRITEBYTECODE=1
    
    # Start Bridge server (simplified - actual Bridge needs proper CLI)
    exec python -c "
import asyncio
import sys
sys.path.insert(0, '/app/src')
from lighthouse.bridge.main_bridge import LighthouseBridge
from lighthouse.bridge.api_server import run_api_server

async def main():
    bridge = LighthouseBridge(
        project_id='${LIGHTHOUSE_PROJECT_ID:-default}',
        mount_point='${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}',
        config={'fuse_foreground': False}
    )
    await bridge.start()
    await run_api_server(bridge, '${LIGHTHOUSE_HOST:-0.0.0.0}', ${LIGHTHOUSE_PORT:-8765})

asyncio.run(main())
" &
    
    BRIDGE_PID=$!
    
elif [ "$1" == "--development" ] || [ "${LIGHTHOUSE_ENV}" == "development" ]; then
    echo "🔧 Running in development mode"
    
    # Development mode with debugging
    export PYTHONDONTWRITEBYTECODE=1
    export LIGHTHOUSE_DEBUG=true
    
    # Start Bridge with debug options (simplified)
    exec python -c "
import asyncio
import sys
sys.path.insert(0, '/app/src')
from lighthouse.bridge.main_bridge import LighthouseBridge
from lighthouse.bridge.api_server import run_api_server

async def main():
    bridge = LighthouseBridge(
        project_id='${LIGHTHOUSE_PROJECT_ID:-default}',
        mount_point='${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}',
        config={'fuse_foreground': False}
    )
    await bridge.start()
    await run_api_server(bridge, '${LIGHTHOUSE_HOST:-0.0.0.0}', ${LIGHTHOUSE_PORT:-8765})

asyncio.run(main())
" &
    
    BRIDGE_PID=$!
    
else
    echo "🔄 Running in default mode"
    
    # Default mode (simplified)
    exec python -c "
import asyncio
import sys
sys.path.insert(0, '/app/src')
from lighthouse.bridge.main_bridge import LighthouseBridge
from lighthouse.bridge.api_server import run_api_server

async def main():
    bridge = LighthouseBridge(
        project_id='${LIGHTHOUSE_PROJECT_ID:-default}',
        mount_point='${LIGHTHOUSE_MOUNT_POINT:-/mnt/lighthouse/project}',
        config={'fuse_foreground': False}
    )
    await bridge.start()
    await run_api_server(bridge, '${LIGHTHOUSE_HOST:-0.0.0.0}', ${LIGHTHOUSE_PORT:-8765})

asyncio.run(main())
" &
    
    BRIDGE_PID=$!
fi

# Wait for Bridge to start
echo "⏳ Waiting for Bridge to be ready..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -f -s "http://localhost:${LIGHTHOUSE_PORT:-8765}/health" > /dev/null 2>&1; then
        echo "✅ Bridge is ready!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS..."
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Bridge failed to start within timeout"
    exit 1
fi

# Display Bridge status
echo "📊 Bridge Status:"
curl -s "http://localhost:${LIGHTHOUSE_PORT:-8765}/status" | python -m json.tool 2>/dev/null || echo "  (Unable to fetch status)"

echo ""
echo "========================================="
echo "🌉 Lighthouse Bridge is running!"
echo "API: http://localhost:${LIGHTHOUSE_PORT:-8765}"
echo "Health: http://localhost:${LIGHTHOUSE_PORT:-8765}/health"
echo "========================================="
echo ""

# Keep the script running and wait for the Bridge process
wait $BRIDGE_PID