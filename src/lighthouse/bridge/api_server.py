"""
Lighthouse Bridge HTTP API Server

Provides REST API endpoints for Bridge status, health checks, and management.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Lighthouse Bridge API",
    description="Multi-agent coordination Bridge server",
    version="1.0.0"
)

# Global reference to Bridge instance
bridge_instance: Optional[Any] = None


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    timestamp: str
    components: Dict[str, str]
    uptime_seconds: float


class StatusResponse(BaseModel):
    """Bridge status response model"""
    bridge_mode: str
    event_store_status: str
    speed_layer_status: str
    expert_coordinator_status: str
    fuse_mount_status: str
    active_agents: int
    pending_validations: int
    uptime_seconds: float


def set_bridge_instance(bridge):
    """Set the Bridge instance for API access"""
    global bridge_instance
    bridge_instance = bridge


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for container orchestration"""
    if not bridge_instance or not bridge_instance.is_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bridge not running"
        )
    
    try:
        # Get Bridge status
        bridge_status = await bridge_instance.get_status()
        
        return HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow().isoformat(),
            components={
                "event_store": bridge_status.event_store_status,
                "speed_layer": bridge_status.speed_layer_status,
                "expert_coordinator": bridge_status.expert_coordinator_status,
                "fuse_mount": bridge_status.fuse_mount_status
            },
            uptime_seconds=bridge_status.uptime_seconds
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}"
        )


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get detailed Bridge status"""
    if not bridge_instance:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bridge not initialized"
        )
    
    try:
        status = await bridge_instance.get_status()
        
        return StatusResponse(
            bridge_mode=status.mode,
            event_store_status=status.event_store_status,
            speed_layer_status=status.speed_layer_status,
            expert_coordinator_status=status.expert_coordinator_status,
            fuse_mount_status=status.fuse_mount_status,
            active_agents=len(bridge_instance.expert_coordinator.registered_experts),
            pending_validations=len(bridge_instance.pending_validations),
            uptime_seconds=status.uptime_seconds
        )
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Status check failed: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Lighthouse Bridge API",
        "version": "1.0.0",
        "status": "running" if bridge_instance and bridge_instance.is_running else "stopped",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "docs": "/docs",
            "openapi": "/openapi.json"
        }
    }


@app.on_event("startup")
async def startup_event():
    """API startup event"""
    logger.info("Bridge API server starting...")


@app.on_event("shutdown")
async def shutdown_event():
    """API shutdown event"""
    logger.info("Bridge API server shutting down...")
    if bridge_instance:
        await bridge_instance.stop()


async def run_api_server(bridge, host: str = "0.0.0.0", port: int = 8765):
    """Run the API server with the Bridge instance"""
    import uvicorn
    
    # Set Bridge instance
    set_bridge_instance(bridge)
    
    # Configure and run server
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    
    server = uvicorn.Server(config)
    await server.serve()