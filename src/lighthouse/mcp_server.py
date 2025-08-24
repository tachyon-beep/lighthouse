#!/usr/bin/env python3
"""
Lighthouse Event Store MCP Server

Provides MCP (Model Context Protocol) interface to the Lighthouse Event Store,
enabling Claude Code to interact with the secure event-sourced foundation.
"""

import asyncio
import json
import sys
import tempfile
import traceback
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest, 
    TextContent,
    Tool,
)

from lighthouse.event_store import (
    EventStore, Event, EventType, EventQuery, EventFilter, EventBatch,
    AgentRole, SecurityError, EventStoreError
)


class LighthouseEventStoreMCP:
    """MCP Server for Lighthouse Event Store."""
    
    def __init__(self):
        self.store: Optional[EventStore] = None
        self.temp_dir: Optional[str] = None
        self.authenticated_agent = "mcp-claude-agent"
    
    async def initialize(self):
        """Initialize the event store."""
        # Create temporary directory for demo/development
        self.temp_dir = tempfile.mkdtemp(prefix="lighthouse_mcp_")
        
        # Initialize secure event store
        self.store = EventStore(
            data_dir=self.temp_dir,
            allowed_base_dirs=[self.temp_dir, "/tmp"],
            auth_secret="lighthouse-mcp-secret-change-in-production"
        )
        await self.store.initialize()
        
        # Authenticate the MCP agent
        token = self.store.create_agent_token(self.authenticated_agent)
        self.store.authenticate_agent(self.authenticated_agent, token, "agent")
        
        print(f"✅ Lighthouse Event Store MCP initialized at {self.temp_dir}", file=sys.stderr)
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.store:
            await self.store.shutdown()
        if self.temp_dir:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def get_available_tools(self) -> List[Tool]:
        """Return list of available tools."""
        return [
            Tool(
                name="lighthouse_store_event",
                description="Store an event in the Lighthouse Event Store",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string", 
                            "enum": [
                                "COMMAND_RECEIVED", "COMMAND_VALIDATED", "COMMAND_EXECUTED", "COMMAND_FAILED",
                                "AGENT_REGISTERED", "AGENT_DISCONNECTED", "AGENT_HEARTBEAT",
                                "SHADOW_UPDATED", "SHADOW_CREATED", "SHADOW_DELETED",
                                "SYSTEM_STARTED", "SYSTEM_SHUTDOWN", "DEGRADATION_TRIGGERED", "RECOVERY_COMPLETED",
                                "SNAPSHOT_CREATED", "SNAPSHOT_RESTORED"
                            ],
                            "description": "Type of event to store"
                        },
                        "aggregate_id": {
                            "type": "string",
                            "description": "Unique identifier for the entity this event relates to"
                        },
                        "data": {
                            "type": "object",
                            "description": "Event payload data (must be JSON serializable)"
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional metadata for the event",
                            "default": {}
                        },
                        "aggregate_type": {
                            "type": "string", 
                            "description": "Type of aggregate (optional)",
                            "default": "unknown"
                        }
                    },
                    "required": ["event_type", "aggregate_id", "data"]
                }
            ),
            
            Tool(
                name="lighthouse_store_event_batch",
                description="Store multiple events atomically in the Lighthouse Event Store",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "event_type": {"type": "string"},
                                    "aggregate_id": {"type": "string"},
                                    "data": {"type": "object"},
                                    "metadata": {"type": "object", "default": {}},
                                    "aggregate_type": {"type": "string", "default": "unknown"}
                                },
                                "required": ["event_type", "aggregate_id", "data"]
                            },
                            "minItems": 1,
                            "maxItems": 100
                        }
                    },
                    "required": ["events"]
                }
            ),
            
            Tool(
                name="lighthouse_query_events", 
                description="Query events from the Lighthouse Event Store",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "event_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by event types (optional)"
                        },
                        "aggregate_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by aggregate IDs (optional)"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 1000,
                            "default": 100,
                            "description": "Maximum number of events to return"
                        },
                        "offset": {
                            "type": "integer", 
                            "minimum": 0,
                            "default": 0,
                            "description": "Number of events to skip"
                        },
                        "order_by": {
                            "type": "string",
                            "enum": ["sequence", "timestamp"],
                            "default": "sequence",
                            "description": "Field to order by"
                        },
                        "ascending": {
                            "type": "boolean",
                            "default": True,
                            "description": "Sort order"
                        }
                    }
                }
            ),
            
            Tool(
                name="lighthouse_get_health",
                description="Get Lighthouse Event Store health and statistics", 
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            
            Tool(
                name="lighthouse_get_agent_identity",
                description="Get current agent identity and permissions",
                inputSchema={
                    "type": "object", 
                    "properties": {}
                }
            )
        ]
    
    async def handle_tool_call(self, request: CallToolRequest) -> CallToolResult:
        """Handle tool calls."""
        try:
            if not self.store:
                return CallToolResult(
                    content=[TextContent(type="text", text="Error: Event store not initialized")]
                )
            
            if request.params.name == "lighthouse_store_event":
                return await self._store_event(request.params.arguments)
            
            elif request.params.name == "lighthouse_store_event_batch":
                return await self._store_event_batch(request.params.arguments)
            
            elif request.params.name == "lighthouse_query_events":
                return await self._query_events(request.params.arguments)
            
            elif request.params.name == "lighthouse_get_health":
                return await self._get_health()
            
            elif request.params.name == "lighthouse_get_agent_identity":
                return await self._get_agent_identity()
            
            else:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Unknown tool: {request.params.name}")]
                )
        
        except Exception as e:
            error_msg = f"Error in {request.params.name}: {str(e)}\n{traceback.format_exc()}"
            print(error_msg, file=sys.stderr)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")]
            )
    
    async def _store_event(self, args: Dict[str, Any]) -> CallToolResult:
        """Store a single event."""
        try:
            event_type = EventType(args["event_type"])
            event = Event(
                event_type=event_type,
                aggregate_id=args["aggregate_id"],
                aggregate_type=args.get("aggregate_type", "unknown"),
                data=args["data"],
                metadata=args.get("metadata", {})
            )
            
            await self.store.append(event, agent_id=self.authenticated_agent)
            
            return CallToolResult(
                content=[TextContent(
                    type="text", 
                    text=f"✅ Event stored successfully:\n"
                         f"  Event ID: {event.event_id}\n"
                         f"  Sequence: {event.sequence}\n"
                         f"  Type: {event.event_type.value}\n"
                         f"  Aggregate: {event.aggregate_id}"
                )]
            )
        
        except (SecurityError, EventStoreError) as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ Event store error: {str(e)}")]
            )
    
    async def _store_event_batch(self, args: Dict[str, Any]) -> CallToolResult:
        """Store a batch of events."""
        try:
            events = []
            for event_data in args["events"]:
                event_type = EventType(event_data["event_type"])
                event = Event(
                    event_type=event_type,
                    aggregate_id=event_data["aggregate_id"],
                    aggregate_type=event_data.get("aggregate_type", "unknown"),
                    data=event_data["data"],
                    metadata=event_data.get("metadata", {})
                )
                events.append(event)
            
            batch = EventBatch(events=events)
            await self.store.append_batch(batch, agent_id=self.authenticated_agent)
            
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"✅ Event batch stored successfully:\n"
                         f"  Events stored: {len(events)}\n"
                         f"  Batch ID: {batch.batch_id}\n"
                         f"  Sequence range: {events[0].sequence}-{events[-1].sequence}"
                )]
            )
        
        except (SecurityError, EventStoreError) as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ Event store error: {str(e)}")]
            )
    
    async def _query_events(self, args: Dict[str, Any]) -> CallToolResult:
        """Query events from the store."""
        try:
            # Build filter
            filter_kwargs = {}
            if "event_types" in args:
                filter_kwargs["event_types"] = [EventType(et) for et in args["event_types"]]
            if "aggregate_ids" in args:
                filter_kwargs["aggregate_ids"] = args["aggregate_ids"]
            
            event_filter = EventFilter(**filter_kwargs)
            
            # Build query
            query = EventQuery(
                filter=event_filter,
                limit=args.get("limit", 100),
                offset=args.get("offset", 0),
                order_by=args.get("order_by", "sequence"),
                ascending=args.get("ascending", True)
            )
            
            result = await self.store.query(query, agent_id=self.authenticated_agent)
            
            # Format results
            events_text = []
            for event in result.events:
                events_text.append(
                    f"🔖 Event {event.sequence}: {event.event_id}\n"
                    f"   Type: {event.event_type.value}\n"
                    f"   Aggregate: {event.aggregate_id} ({event.aggregate_type})\n"
                    f"   Timestamp: {event.timestamp.isoformat()}\n"
                    f"   Data: {json.dumps(event.data, indent=2)}\n"
                    f"   Metadata: {json.dumps(event.metadata, indent=2)}\n"
                )
            
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"📊 Query Results:\n"
                         f"  Found: {len(result.events)} events\n"
                         f"  Total: {result.total_count}\n"
                         f"  Has more: {result.has_more}\n"
                         f"  Execution time: {result.execution_time_ms:.2f}ms\n\n"
                         f"{''.join(events_text)}"
                )]
            )
        
        except Exception as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ Query error: {str(e)}")]
            )
    
    async def _get_health(self) -> CallToolResult:
        """Get event store health."""
        try:
            health = await self.store.get_health()
            
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"💊 Lighthouse Event Store Health:\n"
                         f"  Status: {health.event_store_status}\n"
                         f"  Current Sequence: {health.current_sequence}\n"
                         f"  Events/Second: {health.events_per_second:.2f}\n"
                         f"  Avg Append Latency: {health.average_append_latency_ms:.2f}ms\n"
                         f"  Avg Query Latency: {health.average_query_latency_ms:.2f}ms\n"
                         f"  Disk Usage: {health.disk_usage_bytes / 1024:.2f} KB\n"
                         f"  Disk Free: {health.disk_free_bytes / 1024 / 1024:.2f} MB\n"
                         f"  Log Files: {health.log_file_count}\n"
                         f"  Append Error Rate: {health.append_error_rate:.2%}\n"
                         f"  Query Error Rate: {health.query_error_rate:.2%}"
                )]
            )
        
        except Exception as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ Health check error: {str(e)}")]
            )
    
    async def _get_agent_identity(self) -> CallToolResult:
        """Get current agent identity."""
        try:
            identity = self.store.get_agent_identity(self.authenticated_agent)
            if not identity:
                return CallToolResult(
                    content=[TextContent(type="text", text="❌ Agent not authenticated")]
                )
            
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"👤 Agent Identity:\n"
                         f"  Agent ID: {identity.agent_id}\n"
                         f"  Role: {identity.role.value}\n"
                         f"  Permissions: {[p.value for p in identity.permissions]}\n"
                         f"  Authenticated at: {identity.authenticated_at.isoformat()}\n"
                         f"  Expires at: {identity.expires_at.isoformat() if identity.expires_at else 'Never'}\n"
                         f"  Max requests/min: {identity.max_requests_per_minute}\n"
                         f"  Max batch size: {identity.max_batch_size}"
                )]
            )
        
        except Exception as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ Identity error: {str(e)}")]
            )


async def main():
    """Main entry point for the MCP server."""
    lighthouse_mcp = LighthouseEventStoreMCP()
    
    try:
        await lighthouse_mcp.initialize()
        
        server = Server("lighthouse-event-store")
        
        @server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            return lighthouse_mcp.get_available_tools()
        
        @server.call_tool()
        async def handle_call_tool(request: CallToolRequest) -> CallToolResult:
            return await lighthouse_mcp.handle_tool_call(request)
        
        # Run the server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream, 
                InitializationOptions(
                    server_name="lighthouse-event-store",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=None,
                        experimental_capabilities=None,
                    )
                )
            )
    
    finally:
        await lighthouse_mcp.shutdown()


if __name__ == "__main__":
    asyncio.run(main())