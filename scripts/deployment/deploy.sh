#!/bin/bash
# Lighthouse Bridge Deployment Script
# Handles container deployment with health checks and rollback

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
DEPLOYMENT_ENV="${1:-development}"
IMAGE_TAG="${2:-latest}"
REGISTRY="${REGISTRY:-ghcr.io/lighthouse/lighthouse-bridge}"
COMPOSE_PROJECT="${DEPLOYMENT_ENV}-lighthouse"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ✅ $1"
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ⚠️  $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ❌ $1" >&2
}

# Trap for cleanup
cleanup() {
    log "Performing cleanup..."
    if [[ -n "${BACKUP_COMPOSE_FILE:-}" && -f "$BACKUP_COMPOSE_FILE" ]]; then
        log "Restoring previous deployment state..."
        cp "$BACKUP_COMPOSE_FILE" docker-compose.yml
        rm -f "$BACKUP_COMPOSE_FILE"
    fi
}
trap cleanup EXIT

# Validate environment
validate_environment() {
    log "Validating deployment environment: $DEPLOYMENT_ENV"
    
    case "$DEPLOYMENT_ENV" in
        development|dev)
            COMPOSE_FILE="docker-compose.yml"
            HEALTH_TIMEOUT=120
            ;;
        staging|stage)
            COMPOSE_FILE="docker-compose.staging.yml"
            HEALTH_TIMEOUT=180
            ;;
        production|prod)
            COMPOSE_FILE="docker-compose.prod.yml"
            HEALTH_TIMEOUT=300
            ;;
        *)
            error "Invalid environment: $DEPLOYMENT_ENV. Must be one of: development, staging, production"
            exit 1
            ;;
    esac
    
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    # Check required tools
    local required_tools=("docker" "docker-compose" "curl" "jq")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            error "Required tool not found: $tool"
            exit 1
        fi
    done
    
    success "Environment validation completed"
}

# Pre-deployment checks
pre_deployment_checks() {
    log "Running pre-deployment checks..."
    
    # Check Docker daemon
    if ! docker info >/dev/null 2>&1; then
        error "Docker daemon not available"
        exit 1
    fi
    
    # Check image availability
    log "Checking image: $REGISTRY:$IMAGE_TAG"
    if ! docker pull "$REGISTRY:$IMAGE_TAG"; then
        error "Failed to pull image: $REGISTRY:$IMAGE_TAG"
        exit 1
    fi
    
    # Validate image security
    log "Running security scan on image..."
    if command -v trivy >/dev/null 2>&1; then
        if ! trivy image --exit-code 0 --severity HIGH,CRITICAL "$REGISTRY:$IMAGE_TAG"; then
            warning "Security vulnerabilities found in image"
        fi
    else
        warning "Trivy not available, skipping security scan"
    fi
    
    # Check system resources
    local available_memory=$(free -m | awk 'NR==2{printf "%.0f", $7}')
    local available_disk=$(df . | awk 'NR==2{print int($4/1024)}')
    
    if [[ $available_memory -lt 512 ]]; then
        error "Insufficient memory: ${available_memory}MB available, 512MB required"
        exit 1
    fi
    
    if [[ $available_disk -lt 2048 ]]; then
        error "Insufficient disk space: ${available_disk}MB available, 2GB required"
        exit 1
    fi
    
    success "Pre-deployment checks passed"
}

# Backup current deployment
backup_current_deployment() {
    log "Creating backup of current deployment..."
    
    if [[ -f "docker-compose.yml" ]]; then
        BACKUP_COMPOSE_FILE="docker-compose.backup.$(date +%Y%m%d_%H%M%S).yml"
        cp docker-compose.yml "$BACKUP_COMPOSE_FILE"
        log "Backup created: $BACKUP_COMPOSE_FILE"
    fi
    
    # Export current container state
    if docker-compose ps | grep -q "Up"; then
        log "Exporting current container configuration..."
        docker-compose config > "deployment-backup-$(date +%Y%m%d_%H%M%S).yml"
    fi
    
    success "Current deployment backed up"
}

# Deploy new version
deploy() {
    log "Starting deployment of $REGISTRY:$IMAGE_TAG to $DEPLOYMENT_ENV environment..."
    
    # Set environment variables
    export LIGHTHOUSE_IMAGE="$REGISTRY:$IMAGE_TAG"
    export COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT"
    export LIGHTHOUSE_ENV="$DEPLOYMENT_ENV"
    
    # Update compose file with new image
    if [[ "$COMPOSE_FILE" != "docker-compose.yml" ]]; then
        cp "$COMPOSE_FILE" docker-compose.yml
    fi
    
    # Pull latest images
    log "Pulling latest images..."
    docker-compose pull
    
    # Start services
    log "Starting services..."
    docker-compose up -d
    
    success "Services started"
}

# Health check
health_check() {
    log "Performing health checks..."
    
    local max_attempts=$((HEALTH_TIMEOUT / 10))
    local attempt=1
    local bridge_healthy=false
    
    while [[ $attempt -le $max_attempts ]]; do
        log "Health check attempt $attempt/$max_attempts..."
        
        # Check Bridge health
        if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
            bridge_healthy=true
            break
        fi
        
        # Check container status
        local unhealthy_containers=$(docker-compose ps | grep -v "Up (healthy)" | grep "Up" | wc -l)
        if [[ $unhealthy_containers -gt 0 ]]; then
            warning "$unhealthy_containers containers are not healthy yet"
        fi
        
        sleep 10
        ((attempt++))
    done
    
    if [[ "$bridge_healthy" != "true" ]]; then
        error "Health check failed after $max_attempts attempts"
        return 1
    fi
    
    # Extended health checks
    log "Running extended health checks..."
    
    # Check API endpoints
    local api_check=$(curl -s http://localhost:8765/health | jq -r '.status // "unknown"')
    if [[ "$api_check" != "healthy" ]]; then
        error "API health check failed: $api_check"
        return 1
    fi
    
    # Check metrics endpoint
    if ! curl -sf http://localhost:9090/metrics >/dev/null 2>&1; then
        warning "Metrics endpoint not responding"
    fi
    
    # Check database connectivity
    local db_status=$(curl -s http://localhost:8765/health/detailed | jq -r '.components.database.status // "unknown"')
    if [[ "$db_status" != "healthy" ]]; then
        warning "Database connection check failed: $db_status"
    fi
    
    success "Health checks passed"
}

# Smoke tests
smoke_tests() {
    log "Running smoke tests..."
    
    # Test basic API functionality
    local test_results=""
    
    # Test 1: Basic connectivity
    if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
        test_results+="✅ Basic connectivity\n"
    else
        test_results+="❌ Basic connectivity\n"
        return 1
    fi
    
    # Test 2: Session creation
    local session_response=$(curl -s -X POST http://localhost:8765/api/sessions \
        -H "Content-Type: application/json" \
        -d '{"agent_id": "smoke-test"}' 2>/dev/null || echo "failed")
    
    if echo "$session_response" | jq -e '.session_id' >/dev/null 2>&1; then
        test_results+="✅ Session creation\n"
        local session_id=$(echo "$session_response" | jq -r '.session_id')
        
        # Test 3: Session validation
        if curl -sf "http://localhost:8765/api/sessions/$session_id/validate" >/dev/null 2>&1; then
            test_results+="✅ Session validation\n"
        else
            test_results+="❌ Session validation\n"
        fi
    else
        test_results+="❌ Session creation\n"
    fi
    
    # Test 4: Metrics collection
    if curl -sf http://localhost:9090/metrics | grep -q "lighthouse_bridge"; then
        test_results+="✅ Metrics collection\n"
    else
        test_results+="⚠️  Metrics collection\n"
    fi
    
    echo -e "\n${BLUE}Smoke Test Results:${NC}"
    echo -e "$test_results"
    
    success "Smoke tests completed"
}

# Rollback function
rollback() {
    error "Deployment failed, initiating rollback..."
    
    if [[ -n "${BACKUP_COMPOSE_FILE:-}" && -f "$BACKUP_COMPOSE_FILE" ]]; then
        log "Rolling back to previous deployment..."
        
        # Stop current services
        docker-compose down
        
        # Restore backup
        cp "$BACKUP_COMPOSE_FILE" docker-compose.yml
        
        # Start previous version
        docker-compose up -d
        
        # Brief health check for rollback
        sleep 30
        if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
            success "Rollback completed successfully"
        else
            error "Rollback failed - manual intervention required"
        fi
    else
        error "No backup available for rollback"
    fi
}

# Cleanup old containers and images
cleanup_old_deployments() {
    log "Cleaning up old deployments..."
    
    # Remove old containers
    docker container prune -f
    
    # Remove old images (keep last 3 versions)
    docker image ls "$REGISTRY" --format "{{.Tag}} {{.ID}}" | \
        tail -n +4 | \
        awk '{print $2}' | \
        xargs -r docker image rm
    
    # Remove old volumes
    docker volume prune -f
    
    success "Cleanup completed"
}

# Display deployment status
show_status() {
    log "Deployment Status Summary:"
    echo "========================"
    
    # Service status
    echo -e "${BLUE}Services:${NC}"
    docker-compose ps
    echo
    
    # Resource usage
    echo -e "${BLUE}Resource Usage:${NC}"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
    echo
    
    # Health status
    echo -e "${BLUE}Health Status:${NC}"
    local health_status=$(curl -s http://localhost:8765/health | jq -r '.status // "unknown"')
    echo "Bridge Health: $health_status"
    
    # URLs
    echo -e "${BLUE}Access URLs:${NC}"
    echo "Bridge API: http://localhost:8765"
    echo "Prometheus: http://localhost:9091"
    echo "Grafana: http://localhost:3000 (admin:lighthouse-dev)"
    echo "Jaeger: http://localhost:16686"
}

# Main deployment flow
main() {
    log "Starting Lighthouse Bridge deployment process..."
    
    validate_environment
    pre_deployment_checks
    backup_current_deployment
    
    if deploy && health_check && smoke_tests; then
        success "Deployment completed successfully!"
        cleanup_old_deployments
        show_status
    else
        rollback
        exit 1
    fi
}

# Help message
show_help() {
    echo "Lighthouse Bridge Deployment Script"
    echo
    echo "Usage: $0 [environment] [image_tag]"
    echo
    echo "Arguments:"
    echo "  environment   Target environment (development|staging|production) [default: development]"
    echo "  image_tag     Docker image tag to deploy [default: latest]"
    echo
    echo "Environment Variables:"
    echo "  REGISTRY      Container registry URL [default: ghcr.io/lighthouse/lighthouse-bridge]"
    echo
    echo "Examples:"
    echo "  $0 development latest"
    echo "  $0 production v1.2.3"
    echo "  REGISTRY=my-registry.com/lighthouse $0 staging main"
}

# Command line handling
case "${1:-}" in
    -h|--help)
        show_help
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac