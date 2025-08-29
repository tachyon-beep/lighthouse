#!/bin/bash
# Production deployment script for Lighthouse Bridge container
set -e

echo "🚀 Deploying Lighthouse Bridge to Production"
echo "============================================"

# Configuration
CONTAINER_NAME="lighthouse-bridge"
IMAGE_NAME="lighthouse-bridge:latest"
HOST_PORT="8765"
CONTAINER_PORT="8765"

# Data directories (create if they don't exist)
DATA_DIR="/opt/lighthouse"
EVENTS_DIR="$DATA_DIR/events"
SNAPSHOTS_DIR="$DATA_DIR/snapshots" 
CACHE_DIR="$DATA_DIR/cache"
MOUNT_DIR="$DATA_DIR/project"

echo "Creating data directories..."
sudo mkdir -p "$EVENTS_DIR" "$SNAPSHOTS_DIR" "$CACHE_DIR" "$MOUNT_DIR"
sudo chown -R 1000:1000 "$DATA_DIR"  # lighthouse user in container

# Stop existing container if running
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "Stopping existing container..."
    docker stop "$CONTAINER_NAME"
    docker rm "$CONTAINER_NAME"
fi

# Build latest image
echo "Building container image..."
docker build -t "$IMAGE_NAME" .

# Deploy with proper FUSE capabilities
echo "Starting Lighthouse Bridge container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "$HOST_PORT:$CONTAINER_PORT" \
    --cap-add SYS_ADMIN \
    --device /dev/fuse \
    --security-opt apparmor:unconfined \
    -v "$EVENTS_DIR:/var/lib/lighthouse/events:rw" \
    -v "$SNAPSHOTS_DIR:/var/lib/lighthouse/snapshots:rw" \
    -v "$CACHE_DIR:/var/lib/lighthouse/cache:rw" \
    -v "$MOUNT_DIR:/mnt/lighthouse/project:rshared" \
    -e LIGHTHOUSE_ENV=production \
    -e LIGHTHOUSE_LOG_LEVEL=INFO \
    "$IMAGE_NAME"

# Wait for container to start
echo "Waiting for container to start..."
sleep 10

# Check if container is running
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "✅ Container is running"
    
    # Test health endpoint
    if curl -f http://localhost:$HOST_PORT/health 2>/dev/null; then
        echo "✅ Health endpoint is responding"
        echo "🎉 Deployment successful!"
        echo ""
        echo "Service URLs:"
        echo "  Health: http://localhost:$HOST_PORT/health"
        echo "  Bridge API: http://localhost:$HOST_PORT/"
        echo ""
        echo "Container logs: docker logs $CONTAINER_NAME"
        echo "Container shell: docker exec -it $CONTAINER_NAME /bin/bash"
    else
        echo "⚠️  Container started but health endpoint not responding"
        echo "Check logs: docker logs $CONTAINER_NAME"
    fi
else
    echo "❌ Container failed to start"
    echo "Check logs: docker logs $CONTAINER_NAME"
    exit 1
fi