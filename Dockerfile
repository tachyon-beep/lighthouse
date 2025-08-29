# Multi-stage Dockerfile for Lighthouse Bridge
# Stage 1: Builder
FROM python:3.11-slim-bookworm AS builder

# Install build dependencies - CRITICAL: fusepy needs libfuse-dev (v2), NOT libfuse3-dev
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libfuse-dev \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment in /opt/venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim-bookworm

# Install runtime dependencies - CRITICAL: fusepy needs libfuse2, NOT fuse3
RUN apt-get update && apt-get install -y --no-install-recommends \
    fuse \
    libfuse2 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (but will need capabilities for FUSE)
RUN groupadd -r lighthouse && useradd -r -g lighthouse -u 1000 lighthouse && \
    mkdir -p /home/lighthouse && \
    chown -R lighthouse:lighthouse /home/lighthouse

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# CRITICAL: Set Python to use container venv, not host paths
ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV="/opt/venv"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Set LD_LIBRARY_PATH to help fusepy find libfuse2
ENV LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# Create necessary directories
RUN mkdir -p /var/lib/lighthouse/events && \
    mkdir -p /var/lib/lighthouse/snapshots && \
    mkdir -p /var/lib/lighthouse/cache && \
    mkdir -p /mnt/lighthouse/project && \
    mkdir -p /app/logs && \
    chown -R lighthouse:lighthouse /var/lib/lighthouse && \
    chown -R lighthouse:lighthouse /mnt/lighthouse && \
    chown -R lighthouse:lighthouse /app

# Copy application code
WORKDIR /app
COPY --chown=lighthouse:lighthouse src/ src/
COPY --chown=lighthouse:lighthouse scripts/ scripts/

# Copy startup scripts
COPY --chown=lighthouse:lighthouse scripts/docker/start-bridge-simple.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start-bridge-simple.sh

# Environment variables
ENV LIGHTHOUSE_ENV=production \
    LIGHTHOUSE_PORT=8765 \
    LIGHTHOUSE_HOST=0.0.0.0 \
    LIGHTHOUSE_LOG_LEVEL=INFO \
    LIGHTHOUSE_EVENT_STORE_PATH=/var/lib/lighthouse/events \
    LIGHTHOUSE_SNAPSHOT_PATH=/var/lib/lighthouse/snapshots \
    LIGHTHOUSE_CACHE_PATH=/var/lib/lighthouse/cache \
    LIGHTHOUSE_MOUNT_POINT=/mnt/lighthouse/project \
    PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Expose Bridge API port
EXPOSE 8765

# Switch to non-root user (but container needs CAP_SYS_ADMIN for FUSE)
USER lighthouse

# Entry point
ENTRYPOINT ["/usr/local/bin/start-bridge-simple.sh"]