#!/bin/bash
# Lighthouse Bridge Container Startup Script with Dual FUSE Support
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Lighthouse Bridge Server (Dual FUSE Mode)...${NC}"
echo "Environment: ${LIGHTHOUSE_ENV:-development}"
echo "Port: ${LIGHTHOUSE_PORT:-8765}"
echo "FUSE Backend: ${LIGHTHOUSE_FUSE_BACKEND:-fusepy}"
echo "FUSE Fallback: ${LIGHTHOUSE_FUSE_FALLBACK:-pyfuse3}"

# Force use of container Python
CONTAINER_PYTHON="/opt/venv/bin/python"

if [[ ! -x "$CONTAINER_PYTHON" ]]; then
    echo -e "${RED}❌ CRITICAL: Container Python not found at $CONTAINER_PYTHON${NC}"
    exit 1
fi

echo "Python: $CONTAINER_PYTHON"
echo "Python version: $($CONTAINER_PYTHON --version)"

# Function to check FUSE2 availability
check_fuse2() {
    echo -e "${BLUE}Checking FUSE2 (libfuse2) availability...${NC}"
    
    if [[ -f "/usr/lib/x86_64-linux-gnu/libfuse.so.2" ]]; then
        echo -e "${GREEN}✅ libfuse2 found${NC}"
        ldd /usr/lib/x86_64-linux-gnu/libfuse.so.2 2>/dev/null | head -5
        
        # Test fusepy import
        $CONTAINER_PYTHON -c "
import sys
try:
    import fuse
    print('✅ fusepy successfully imported')
    from fuse import FUSE, FuseOSError, Operations
    print('✅ FUSE2 classes available')
    sys.exit(0)
except ImportError as e:
    print(f'❌ fusepy import failed: {e}')
    sys.exit(1)
" && return 0 || return 1
    else
        echo -e "${YELLOW}⚠️  libfuse2 not found${NC}"
        return 1
    fi
}

# Function to check FUSE3 availability
check_fuse3() {
    echo -e "${BLUE}Checking FUSE3 (libfuse3) availability...${NC}"
    
    if [[ -f "/usr/lib/x86_64-linux-gnu/libfuse3.so.3" ]]; then
        echo -e "${GREEN}✅ libfuse3 found${NC}"
        ldd /usr/lib/x86_64-linux-gnu/libfuse3.so.3 2>/dev/null | head -5
        
        # Test pyfuse3 import
        $CONTAINER_PYTHON -c "
import sys
try:
    import pyfuse3
    print('✅ pyfuse3 successfully imported')
    import trio
    print('✅ trio (async runtime) available')
    sys.exit(0)
except ImportError as e:
    print(f'❌ pyfuse3 import failed: {e}')
    sys.exit(1)
" && return 0 || return 1
    else
        echo -e "${YELLOW}⚠️  libfuse3 not found${NC}"
        return 1
    fi
}

# Check availability of both backends
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}Validating FUSE Backend Availability${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

FUSE2_AVAILABLE=false
FUSE3_AVAILABLE=false

if check_fuse2; then
    FUSE2_AVAILABLE=true
fi

if check_fuse3; then
    FUSE3_AVAILABLE=true
fi

# Determine which backend to use
SELECTED_BACKEND=""

if [[ "$LIGHTHOUSE_FUSE_BACKEND" == "fusepy" ]] && [[ "$FUSE2_AVAILABLE" == "true" ]]; then
    SELECTED_BACKEND="fusepy"
    echo -e "${GREEN}✅ Using primary backend: fusepy (FUSE2)${NC}"
elif [[ "$LIGHTHOUSE_FUSE_BACKEND" == "pyfuse3" ]] && [[ "$FUSE3_AVAILABLE" == "true" ]]; then
    SELECTED_BACKEND="pyfuse3"
    echo -e "${GREEN}✅ Using primary backend: pyfuse3 (FUSE3)${NC}"
elif [[ "$LIGHTHOUSE_FUSE_FALLBACK" == "fusepy" ]] && [[ "$FUSE2_AVAILABLE" == "true" ]]; then
    SELECTED_BACKEND="fusepy"
    echo -e "${YELLOW}⚠️  Primary backend unavailable, using fallback: fusepy (FUSE2)${NC}"
elif [[ "$LIGHTHOUSE_FUSE_FALLBACK" == "pyfuse3" ]] && [[ "$FUSE3_AVAILABLE" == "true" ]]; then
    SELECTED_BACKEND="pyfuse3"
    echo -e "${YELLOW}⚠️  Primary backend unavailable, using fallback: pyfuse3 (FUSE3)${NC}"
else
    echo -e "${RED}❌ No FUSE backend available!${NC}"
    echo -e "${YELLOW}Bridge will run in degraded mode without FUSE mount${NC}"
    SELECTED_BACKEND="none"
fi

# Export selected backend for the application
export LIGHTHOUSE_ACTIVE_FUSE_BACKEND="$SELECTED_BACKEND"

# Performance benchmarking if enabled
if [[ "${LIGHTHOUSE_FUSE_BENCHMARK}" == "true" ]] && [[ "$SELECTED_BACKEND" != "none" ]]; then
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}Running FUSE Backend Benchmarks${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    
    if [[ "$FUSE2_AVAILABLE" == "true" ]]; then
        echo -e "${BLUE}Benchmarking fusepy...${NC}"
        $CONTAINER_PYTHON -m lighthouse.benchmarks.fuse_benchmark --backend fusepy --output /app/benchmarks/results/fusepy_bench.json
    fi
    
    if [[ "$FUSE3_AVAILABLE" == "true" ]]; then
        echo -e "${BLUE}Benchmarking pyfuse3...${NC}"
        $CONTAINER_PYTHON -m lighthouse.benchmarks.fuse_benchmark --backend pyfuse3 --output /app/benchmarks/results/pyfuse3_bench.json
    fi
    
    # Compare results if both are available
    if [[ "$FUSE2_AVAILABLE" == "true" ]] && [[ "$FUSE3_AVAILABLE" == "true" ]]; then
        echo -e "${BLUE}Comparing benchmark results...${NC}"
        $CONTAINER_PYTHON -m lighthouse.benchmarks.compare_results \
            --fusepy /app/benchmarks/results/fusepy_bench.json \
            --pyfuse3 /app/benchmarks/results/pyfuse3_bench.json \
            --output /app/benchmarks/results/comparison.html
    fi
fi

# Parallel testing if enabled (run both backends simultaneously)
if [[ "${LIGHTHOUSE_FUSE_PARALLEL_TEST}" == "true" ]] && \
   [[ "$FUSE2_AVAILABLE" == "true" ]] && \
   [[ "$FUSE3_AVAILABLE" == "true" ]]; then
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}Starting Parallel Backend Testing${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    
    # Start secondary backend in background for comparison
    if [[ "$SELECTED_BACKEND" == "fusepy" ]]; then
        echo -e "${BLUE}Starting pyfuse3 shadow instance for comparison...${NC}"
        LIGHTHOUSE_ACTIVE_FUSE_BACKEND="pyfuse3" \
        LIGHTHOUSE_PORT=8766 \
        LIGHTHOUSE_MOUNT_POINT=/mnt/lighthouse/shadow \
        $CONTAINER_PYTHON -m lighthouse.shadow_instance &
        SHADOW_PID=$!
        echo "Shadow instance PID: $SHADOW_PID"
    elif [[ "$SELECTED_BACKEND" == "pyfuse3" ]]; then
        echo -e "${BLUE}Starting fusepy shadow instance for comparison...${NC}"
        LIGHTHOUSE_ACTIVE_FUSE_BACKEND="fusepy" \
        LIGHTHOUSE_PORT=8766 \
        LIGHTHOUSE_MOUNT_POINT=/mnt/lighthouse/shadow \
        $CONTAINER_PYTHON -m lighthouse.shadow_instance &
        SHADOW_PID=$!
        echo "Shadow instance PID: $SHADOW_PID"
    fi
fi

# Set working directory
cd /app

# Ensure PYTHONPATH includes our source
export PYTHONPATH="/app/src:${PYTHONPATH:-}"

# Create event store directory if it doesn't exist
mkdir -p "${LIGHTHOUSE_EVENT_STORE_PATH:-/var/lib/lighthouse/events}"

# Verify our MCP server module exists
if [[ ! -f "/app/src/lighthouse/mcp_server.py" ]]; then
    echo -e "${RED}❌ CRITICAL: MCP server module not found${NC}"
    exit 1
fi

# Function to cleanup on exit
cleanup() {
    echo -e "${YELLOW}Shutting down...${NC}"
    
    # Kill shadow instance if running
    if [[ -n "${SHADOW_PID}" ]] && kill -0 ${SHADOW_PID} 2>/dev/null; then
        echo "Stopping shadow instance..."
        kill ${SHADOW_PID}
    fi
    
    # Unmount FUSE filesystems
    if mountpoint -q /mnt/lighthouse/project; then
        fusermount -u /mnt/lighthouse/project || true
    fi
    if mountpoint -q /mnt/lighthouse/shadow; then
        fusermount -u /mnt/lighthouse/shadow || true
    fi
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Log startup configuration
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}Final Configuration${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo "Active FUSE Backend: ${LIGHTHOUSE_ACTIVE_FUSE_BACKEND}"
echo "Event Store Path: ${LIGHTHOUSE_EVENT_STORE_PATH}"
echo "Mount Point: ${LIGHTHOUSE_MOUNT_POINT}"
echo "Cache Path: ${LIGHTHOUSE_CACHE_PATH}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Start the MCP server bridge
echo -e "${GREEN}Starting MCP server with Bridge integration...${NC}"
echo "Command: $CONTAINER_PYTHON -m lighthouse.mcp_server"

# Use exec to replace shell process with Python process for proper signal handling
exec "$CONTAINER_PYTHON" -m lighthouse.mcp_server