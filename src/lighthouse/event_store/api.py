"""HTTP and WebSocket API for event store operations."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
import uvicorn

from .store import EventStore, EventStoreError
from .models import Event, EventType, EventQuery, EventFilter, EventBatch, QueryResult
from .auth import AgentIdentity, Permission, AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

# Request/Response models
class EventRequest(BaseModel):
    """Request model for creating events"""
    event_type: EventType
    aggregate_id: str
    aggregate_type: str = "unknown"
    data: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    source_agent: Optional[str] = None
    source_component: str = "api"

class EventResponse(BaseModel):
    """Response model for event operations"""
    success: bool
    event_id: Optional[str] = None
    sequence: Optional[int] = None
    message: Optional[str] = None

class BatchRequest(BaseModel):
    """Request model for batch operations"""
    events: List[EventRequest]

class BatchResponse(BaseModel):
    """Response model for batch operations"""
    success: bool
    count: int
    event_ids: List[str] = []
    sequences: List[int] = []
    message: Optional[str] = None

class QueryRequest(BaseModel):
    """Request model for event queries"""
    event_types: Optional[List[str]] = None
    aggregate_ids: Optional[List[str]] = None
    start_sequence: Optional[int] = None
    end_sequence: Optional[int] = None
    limit: int = 1000
    offset: int = 0

class ReplayRequest(BaseModel):
    """Request model for state replay"""
    start_sequence: int = 0
    event_types: Optional[List[str]] = None
    aggregate_ids: Optional[List[str]] = None

class EventStoreAPI:
    """HTTP and WebSocket API for event store operations."""
    
    def __init__(self, event_store: EventStore, title: str = "Lighthouse Event Store API"):
        self.event_store = event_store
        self.app = FastAPI(
            title=title,
            description="High-performance event store with security and atomic guarantees",
            version="1.0.0"
        )
        self.websocket_connections: Set[WebSocket] = set()
        
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.post("/events", response_model=EventResponse)
        async def create_event(
            request: EventRequest,
            agent_id: str = None
        ):
            """Create a single event."""
            try:
                # Convert request to Event model
                event = Event(
                    event_type=request.event_type,
                    aggregate_id=request.aggregate_id,
                    aggregate_type=request.aggregate_type,
                    data=request.data,
                    metadata=request.metadata,
                    source_agent=request.source_agent or agent_id,
                    source_component=request.source_component
                )
                
                # Append to store
                await self.event_store.append(event, agent_id=agent_id)
                
                # Notify WebSocket subscribers
                await self._notify_websocket_subscribers(event)
                
                return EventResponse(
                    success=True,
                    event_id=str(event.event_id),
                    sequence=event.sequence,
                    message="Event created successfully"
                )
                
            except EventStoreError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except (AuthenticationError, AuthorizationError) as e:
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.error(f"Unexpected error creating event: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.post("/events/batch", response_model=BatchResponse)
        async def create_events_batch(
            request: BatchRequest,
            agent_id: str = None
        ):
            """Create multiple events atomically."""
            try:
                # Convert requests to Event models
                events = []
                for event_req in request.events:
                    event = Event(
                        event_type=event_req.event_type,
                        aggregate_id=event_req.aggregate_id,
                        aggregate_type=event_req.aggregate_type,
                        data=event_req.data,
                        metadata=event_req.metadata,
                        source_agent=event_req.source_agent or agent_id,
                        source_component=event_req.source_component
                    )
                    events.append(event)
                
                # Create batch and append
                batch = EventBatch(events=events)
                await self.event_store.append_batch(batch, agent_id=agent_id)
                
                # Notify WebSocket subscribers for each event
                for event in events:
                    await self._notify_websocket_subscribers(event)
                
                return BatchResponse(
                    success=True,
                    count=len(events),
                    event_ids=[str(e.event_id) for e in events],
                    sequences=[e.sequence for e in events],
                    message=f"Batch of {len(events)} events created successfully"
                )
                
            except EventStoreError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except (AuthenticationError, AuthorizationError) as e:
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.error(f"Unexpected error creating batch: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.get("/events")
        async def query_events(
            event_types: Optional[str] = None,
            aggregate_ids: Optional[str] = None,
            start_sequence: Optional[int] = None,
            end_sequence: Optional[int] = None,
            limit: int = 1000,
            offset: int = 0,
            agent_id: str = None
        ):
            """Query events with filtering and pagination."""
            try:
                # Build query
                event_filter = EventFilter(
                    event_types=[EventType(t) for t in event_types.split(",")] if event_types else None,
                    aggregate_ids=aggregate_ids.split(",") if aggregate_ids else None,
                    start_sequence=start_sequence,
                    end_sequence=end_sequence
                )
                
                query = EventQuery(
                    filter=event_filter,
                    limit=min(limit, 10000),  # Cap at 10K as per design
                    offset=offset
                )
                
                # Execute query
                result = await self.event_store.query(query, agent_id=agent_id)
                
                # Convert to dict format
                return {
                    "events": [event.model_dump() for event in result.events],
                    "count": len(result.events),
                    "total": result.total_count,
                    "has_more": result.has_more
                }
                
            except EventStoreError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except (AuthenticationError, AuthorizationError) as e:
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.error(f"Unexpected error querying events: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.get("/events/stream")
        async def stream_events(
            start_sequence: int = 0,
            event_types: Optional[str] = None,
            aggregate_ids: Optional[str] = None,
            limit: int = 10000,
            agent_id: str = None
        ):
            """Stream events as newline-delimited JSON."""
            try:
                async def generate_events():
                    event_filter = EventFilter(
                        start_sequence=start_sequence,
                        event_types=[EventType(t) for t in event_types.split(",")] if event_types else None,
                        aggregate_ids=aggregate_ids.split(",") if aggregate_ids else None
                    )
                    
                    query = EventQuery(filter=event_filter, limit=limit)
                    result = await self.event_store.query(query, agent_id=agent_id)
                    
                    for event in result.events:
                        yield json.dumps(event.model_dump()) + "\n"
                
                return StreamingResponse(
                    generate_events(),
                    media_type="application/x-ndjson"
                )
                
            except EventStoreError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except (AuthenticationError, AuthorizationError) as e:
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.error(f"Unexpected error streaming events: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            try:
                health = await self.event_store.get_health()
                return health.model_dump()
            except Exception as e:
                logger.error(f"Health check error: {e}")
                return {"status": "unhealthy", "error": str(e)}
        
        @self.app.websocket("/stream")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time event streaming."""
            await websocket.accept()
            self.websocket_connections.add(websocket)
            
            try:
                while True:
                    # Keep connection alive and handle client messages
                    try:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        
                        # Handle subscription requests
                        if data.get("action") == "subscribe":
                            await websocket.send_text(json.dumps({
                                "type": "subscribed",
                                "message": "Successfully subscribed to event stream"
                            }))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "echo",
                                "data": data
                            }))
                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        await websocket.send_text(json.dumps({"type": "ping"}))
                        
            except WebSocketDisconnect:
                pass
            finally:
                self.websocket_connections.discard(websocket)
    
    async def _notify_websocket_subscribers(self, event: Event):
        """Notify all WebSocket subscribers of new events."""
        if not self.websocket_connections:
            return
            
        message = json.dumps({
            "type": "event",
            "data": event.model_dump()
        })
        
        # Send to all connected clients
        disconnected = set()
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(message)
            except Exception:
                # Mark for removal
                disconnected.add(websocket)
        
        # Remove disconnected clients
        self.websocket_connections -= disconnected
    
    def get_app(self) -> FastAPI:
        """Get the FastAPI application."""
        return self.app


async def create_api_server(
    event_store: EventStore,
    host: str = "0.0.0.0",
    port: int = 8080
) -> EventStoreAPI:
    """Create and configure the API server."""
    api = EventStoreAPI(event_store)
    return api


async def run_server(
    event_store: EventStore,
    host: str = "0.0.0.0",
    port: int = 8080
):
    """Run the event store API server."""
    api = await create_api_server(event_store, host, port)
    
    config = uvicorn.Config(
        app=api.get_app(),
        host=host,
        port=port,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    await server.serve()


# CLI entry point
async def main():
    """Main entry point for running the API server."""
    import os
    
    # Initialize event store
    data_dir = os.getenv("LIGHTHOUSE_EVENT_STORE_DIR", "./data/events")
    event_store = EventStore(data_dir=data_dir)
    await event_store.initialize()
    
    # Run server
    host = os.getenv("LIGHTHOUSE_API_HOST", "0.0.0.0")
    port = int(os.getenv("LIGHTHOUSE_API_PORT", "8080"))
    
    logger.info(f"Starting Lighthouse Event Store API on {host}:{port}")
    await run_server(event_store, host, port)


if __name__ == "__main__":
    asyncio.run(main())