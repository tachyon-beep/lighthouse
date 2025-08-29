#!/bin/bash
# Lighthouse Bridge Health Check Script
# Comprehensive health monitoring and diagnostics

set -euo pipefail

# Configuration
BRIDGE_URL="${BRIDGE_URL:-http://localhost:8765}"
METRICS_URL="${METRICS_URL:-http://localhost:9090}"
TIMEOUT="${TIMEOUT:-10}"
VERBOSE="${VERBOSE:-false}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-human}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    if [[ "$VERBOSE" == "true" ]] || [[ "$OUTPUT_FORMAT" == "human" ]]; then
        echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1" >&2
    fi
}

success() {
    if [[ "$OUTPUT_FORMAT" == "human" ]]; then
        echo -e "${GREEN}✅${NC} $1"
    fi
}

warning() {
    if [[ "$OUTPUT_FORMAT" == "human" ]]; then
        echo -e "${YELLOW}⚠️${NC} $1"
    fi
}

error() {
    if [[ "$OUTPUT_FORMAT" == "human" ]]; then
        echo -e "${RED}❌${NC} $1"
    fi
}

# JSON output helper
json_output() {
    local status="$1"
    local message="$2"
    local details="${3:-{}}"
    
    jq -n \
        --arg status "$status" \
        --arg message "$message" \
        --argjson details "$details" \
        --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{
            status: $status,
            message: $message,
            details: $details,
            timestamp: $timestamp
        }'
}

# Basic connectivity check
check_connectivity() {
    log "Checking Bridge connectivity..."
    
    if curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/health" >/dev/null 2>&1; then
        success "Bridge is reachable"
        return 0
    else
        error "Bridge is not reachable at $BRIDGE_URL"
        return 1
    fi
}

# Health endpoint check
check_health_endpoint() {
    log "Checking health endpoint..."
    
    local health_response
    health_response=$(curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/health" 2>/dev/null || echo "{\"error\": \"failed\"}")
    
    local health_status
    health_status=$(echo "$health_response" | jq -r '.status // "unknown"')
    
    case "$health_status" in
        "healthy"|"ok")
            success "Health status: $health_status"
            return 0
            ;;
        "degraded")
            warning "Health status: $health_status"
            return 1
            ;;
        *)
            error "Health status: $health_status"
            return 1
            ;;
    esac
}

# Detailed health check
check_detailed_health() {
    log "Checking detailed health status..."
    
    local detailed_response
    detailed_response=$(curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/health/detailed" 2>/dev/null || echo "{}")
    
    if [[ -z "$detailed_response" || "$detailed_response" == "{}" ]]; then
        error "Detailed health endpoint not responding"
        return 1
    fi
    
    local components
    components=$(echo "$detailed_response" | jq -r '.components // {}' 2>/dev/null || echo "{}")
    
    local issues=0
    
    # Check individual components
    for component in $(echo "$components" | jq -r 'keys[]' 2>/dev/null || echo ""); do
        local component_status
        component_status=$(echo "$components" | jq -r ".[\"$component\"].status // \"unknown\"")
        
        case "$component_status" in
            "healthy"|"ok")
                success "Component $component: $component_status"
                ;;
            "degraded")
                warning "Component $component: $component_status"
                ((issues++))
                ;;
            *)
                error "Component $component: $component_status"
                ((issues++))
                ;;
        esac
    done
    
    return $issues
}

# Performance metrics check
check_performance_metrics() {
    log "Checking performance metrics..."
    
    local metrics_response
    metrics_response=$(curl -sf --max-time "$TIMEOUT" "$METRICS_URL/metrics" 2>/dev/null || echo "")
    
    if [[ -z "$metrics_response" ]]; then
        error "Metrics endpoint not responding"
        return 1
    fi
    
    local issues=0
    
    # Check specific metrics
    local memory_usage
    memory_usage=$(echo "$metrics_response" | grep "lighthouse_bridge_memory_usage_percent" | tail -n1 | awk '{print $2}' || echo "0")
    
    if (( $(echo "$memory_usage > 85" | bc -l) )); then
        error "High memory usage: ${memory_usage}%"
        ((issues++))
    elif (( $(echo "$memory_usage > 70" | bc -l) )); then
        warning "Moderate memory usage: ${memory_usage}%"
    else
        success "Memory usage: ${memory_usage}%"
    fi
    
    # Check response times
    local p95_latency
    p95_latency=$(echo "$metrics_response" | grep "lighthouse_bridge_request_duration_seconds{quantile=\"0.95\"}" | tail -n1 | awk '{print $2}' || echo "0")
    
    if (( $(echo "$p95_latency > 0.5" | bc -l) )); then
        error "High P95 latency: ${p95_latency}s"
        ((issues++))
    elif (( $(echo "$p95_latency > 0.1" | bc -l) )); then
        warning "Moderate P95 latency: ${p95_latency}s"
    else
        success "P95 latency: ${p95_latency}s"
    fi
    
    # Check error rate
    local error_rate
    error_rate=$(echo "$metrics_response" | grep "lighthouse_bridge_error_rate_5m" | tail -n1 | awk '{print $2}' || echo "0")
    
    if (( $(echo "$error_rate > 0.01" | bc -l) )); then
        error "High error rate: ${error_rate}"
        ((issues++))
    elif (( $(echo "$error_rate > 0.001" | bc -l) )); then
        warning "Moderate error rate: ${error_rate}"
    else
        success "Error rate: ${error_rate}"
    fi
    
    return $issues
}

# Component status checks
check_components() {
    log "Checking individual components..."
    
    local status_response
    status_response=$(curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/status" 2>/dev/null || echo "{}")
    
    if [[ -z "$status_response" || "$status_response" == "{}" ]]; then
        error "Status endpoint not responding"
        return 1
    fi
    
    local issues=0
    
    # FUSE mount status
    local fuse_status
    fuse_status=$(echo "$status_response" | jq -r '.components.fuse_mount // "unknown"')
    case "$fuse_status" in
        "operational"|"mounted")
            success "FUSE mount: $fuse_status"
            ;;
        "unavailable")
            warning "FUSE mount: $fuse_status (degraded mode)"
            ;;
        *)
            error "FUSE mount: $fuse_status"
            ((issues++))
            ;;
    esac
    
    # Speed Layer status
    local speed_layer_status
    speed_layer_status=$(echo "$status_response" | jq -r '.components.speed_layer // "unknown"')
    if [[ "$speed_layer_status" == "operational" ]]; then
        success "Speed Layer: $speed_layer_status"
    else
        error "Speed Layer: $speed_layer_status"
        ((issues++))
    fi
    
    # Expert Coordinator status
    local expert_status
    expert_status=$(echo "$status_response" | jq -r '.components.expert_coordinator // "unknown"')
    if [[ "$expert_status" == "operational" ]]; then
        success "Expert Coordinator: $expert_status"
    else
        error "Expert Coordinator: $expert_status"
        ((issues++))
    fi
    
    # Event Store status
    local event_store_status
    event_store_status=$(echo "$status_response" | jq -r '.components.event_store // "unknown"')
    if [[ "$event_store_status" == "operational" ]]; then
        success "Event Store: $event_store_status"
    else
        error "Event Store: $event_store_status"
        ((issues++))
    fi
    
    return $issues
}

# Dependency checks
check_dependencies() {
    log "Checking external dependencies..."
    
    local issues=0
    
    # Redis check
    local redis_status
    redis_status=$(curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/health/dependencies" 2>/dev/null | jq -r '.redis.status // "unknown"' || echo "unknown")
    
    if [[ "$redis_status" == "connected" ]]; then
        success "Redis: connected"
    else
        error "Redis: $redis_status"
        ((issues++))
    fi
    
    # PostgreSQL check
    local postgres_status
    postgres_status=$(curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/health/dependencies" 2>/dev/null | jq -r '.postgres.status // "unknown"' || echo "unknown")
    
    if [[ "$postgres_status" == "connected" ]]; then
        success "PostgreSQL: connected"
    else
        error "PostgreSQL: $postgres_status"
        ((issues++))
    fi
    
    return $issues
}

# Container resource check
check_container_resources() {
    if ! command -v docker >/dev/null 2>&1; then
        log "Docker not available, skipping container checks"
        return 0
    fi
    
    log "Checking container resources..."
    
    local container_name="lighthouse-bridge"
    local issues=0
    
    # Get container stats
    local stats
    stats=$(docker stats "$container_name" --no-stream --format "{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" 2>/dev/null || echo "")
    
    if [[ -z "$stats" ]]; then
        error "Container $container_name not found or not running"
        return 1
    fi
    
    local cpu_usage
    cpu_usage=$(echo "$stats" | cut -f1 | sed 's/%//')
    
    if (( $(echo "$cpu_usage > 80" | bc -l) )); then
        error "High CPU usage: ${cpu_usage}%"
        ((issues++))
    elif (( $(echo "$cpu_usage > 60" | bc -l) )); then
        warning "Moderate CPU usage: ${cpu_usage}%"
    else
        success "CPU usage: ${cpu_usage}%"
    fi
    
    return $issues
}

# Functional tests
run_functional_tests() {
    log "Running functional tests..."
    
    local issues=0
    
    # Test 1: Session creation
    local session_response
    session_response=$(curl -sf --max-time "$TIMEOUT" -X POST "$BRIDGE_URL/api/sessions" \
        -H "Content-Type: application/json" \
        -d '{"agent_id": "health-check-test"}' 2>/dev/null || echo "{}")
    
    local session_id
    session_id=$(echo "$session_response" | jq -r '.session_id // null')
    
    if [[ "$session_id" != "null" && -n "$session_id" ]]; then
        success "Session creation: working"
        
        # Test 2: Session validation
        if curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/api/sessions/$session_id/validate" >/dev/null 2>&1; then
            success "Session validation: working"
        else
            error "Session validation: failed"
            ((issues++))
        fi
    else
        error "Session creation: failed"
        ((issues++))
    fi
    
    # Test 3: Bridge status API
    if curl -sf --max-time "$TIMEOUT" "$BRIDGE_URL/status" | jq -e '.status' >/dev/null 2>&1; then
        success "Status API: working"
    else
        error "Status API: failed"
        ((issues++))
    fi
    
    return $issues
}

# Generate comprehensive report
generate_report() {
    local overall_status="$1"
    local details="$2"
    
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        json_output "$overall_status" "Health check completed" "$details"
    else
        echo
        echo "========================================"
        echo "LIGHTHOUSE BRIDGE HEALTH CHECK REPORT"
        echo "========================================"
        echo "Timestamp: $(date)"
        echo "Bridge URL: $BRIDGE_URL"
        echo "Overall Status: $overall_status"
        echo "========================================"
        
        if [[ "$overall_status" != "healthy" ]]; then
            echo
            echo "Issues detected. Check individual component status above."
            echo "For detailed diagnostics, run with VERBOSE=true"
        fi
    fi
}

# Main health check function
main() {
    local total_issues=0
    local check_details="{}"
    
    # Run all checks
    check_connectivity || ((total_issues++))
    check_health_endpoint || ((total_issues++))
    check_detailed_health || ((total_issues++))
    check_performance_metrics || ((total_issues++))
    check_components || ((total_issues++))
    check_dependencies || ((total_issues++))
    check_container_resources || ((total_issues++))
    run_functional_tests || ((total_issues++))
    
    # Determine overall status
    local overall_status
    if [[ $total_issues -eq 0 ]]; then
        overall_status="healthy"
    elif [[ $total_issues -le 2 ]]; then
        overall_status="degraded"
    else
        overall_status="unhealthy"
    fi
    
    # Generate report
    check_details="{\"total_issues\": $total_issues, \"bridge_url\": \"$BRIDGE_URL\"}"
    generate_report "$overall_status" "$check_details"
    
    # Exit with appropriate code
    case "$overall_status" in
        "healthy")
            exit 0
            ;;
        "degraded")
            exit 1
            ;;
        *)
            exit 2
            ;;
    esac
}

# Help message
show_help() {
    cat << EOF
Lighthouse Bridge Health Check Script

Usage: $0 [OPTIONS]

Options:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -j, --json          Output in JSON format
    -t, --timeout SEC   Set timeout for checks (default: 10)
    -u, --url URL       Bridge URL (default: http://localhost:8765)
    -m, --metrics URL   Metrics URL (default: http://localhost:9090)

Environment Variables:
    BRIDGE_URL          Override bridge URL
    METRICS_URL         Override metrics URL
    TIMEOUT             Override timeout value
    VERBOSE             Enable verbose mode (true/false)
    OUTPUT_FORMAT       Set output format (human/json)

Exit Codes:
    0                   All checks passed (healthy)
    1                   Minor issues detected (degraded)
    2                   Major issues detected (unhealthy)

Examples:
    $0                                    # Basic health check
    $0 --verbose                          # Detailed output
    $0 --json                            # JSON output
    $0 --url http://bridge.example.com   # Custom URL
    VERBOSE=true $0                      # Environment variable
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -j|--json)
            OUTPUT_FORMAT=json
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -u|--url)
            BRIDGE_URL="$2"
            shift 2
            ;;
        -m|--metrics)
            METRICS_URL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 1
            ;;
    esac
done

# Run main function
main