#!/bin/bash
# Lighthouse Bridge Development Startup Script
# Development version with hot reload and debug features

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIGHTHOUSE_HOME="${LIGHTHOUSE_HOME:-/app}"
LIGHTHOUSE_ENV="${LIGHTHOUSE_ENV:-development}"

# Enable development features
export LIGHTHOUSE_DEBUG=true
export LIGHTHOUSE_LOG_LEVEL=DEBUG
export LIGHTHOUSE_FUSE_FOREGROUND=false
export LIGHTHOUSE_AUTO_RELOAD=true

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DEV: $1"
}

# Install development dependencies if not present
install_dev_deps() {
    log "Checking development dependencies..."
    
    if ! python -c "import pytest" >/dev/null 2>&1; then
        log "Installing development dependencies..."
        pip install -e ".[dev]"
    fi
}

# Start development services
start_dev_services() {
    log "Starting development services..."
    
    # Start file watcher for hot reload (if available)
    if command -v watchmedo >/dev/null 2>&1; then
        log "Starting file watcher for hot reload..."
        watchmedo auto-restart \
            --directory="$LIGHTHOUSE_HOME/src" \
            --pattern="*.py" \
            --recursive \
            -- python -m lighthouse.bridge.main_bridge &
    else
        log "File watcher not available, starting without hot reload..."
        python -m lighthouse.bridge.main_bridge \
            --log-level DEBUG \
            --env development &
    fi
    
    local bridge_pid=$!
    log "Bridge started with PID: $bridge_pid (development mode)"
    
    # Start MCP server in debug mode
    log "Starting MCP server in debug mode..."
    python -m lighthouse.mcp_server --debug &
    local mcp_pid=$!
    
    # Wait for processes
    wait $bridge_pid $mcp_pid
}

# Development health check
dev_health_check() {
    log "Development health check..."
    
    # More relaxed health check for development
    local max_attempts=10
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -s --max-time 3 http://localhost:8765/health >/dev/null 2>&1; then
            log "Development health check passed"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    
    log "Development health check failed, but continuing..."
    return 0  # Don't fail in development
}

# Main development startup
main() {
    log "Starting Lighthouse Bridge in DEVELOPMENT mode"
    
    cd "$LIGHTHOUSE_HOME"
    
    install_dev_deps
    
    log "Development environment ready"
    log "- Hot reload: ${LIGHTHOUSE_AUTO_RELOAD:-false}"
    log "- Debug logging: ${LIGHTHOUSE_LOG_LEVEL:-INFO}"
    log "- FUSE foreground: ${LIGHTHOUSE_FUSE_FOREGROUND:-false}"
    
    dev_health_check
    start_dev_services
    
    log "Development session ended"
}

# Execute
main "$@"