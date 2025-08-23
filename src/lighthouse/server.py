#!/usr/bin/env python3
"""Lighthouse MCP Server - Main server implementation."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp import types
from pydantic import BaseModel

from .bridge import ValidationBridge
from .validator import CommandValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lighthouse")

class LighthouseServer:
    """Main MCP server for Lighthouse validation system."""
    
    def __init__(self):
        self.server = Server("lighthouse")
        self.bridge = ValidationBridge()
        self.validator = CommandValidator()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up MCP server handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="validate_command",
                    description="Validate a command before execution",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "description": "Tool name"},
                            "input": {"type": "object", "description": "Tool input"},
                            "agent": {"type": "string", "description": "Agent ID"}
                        },
                        "required": ["tool", "input"]
                    }
                ),
                types.Tool(
                    name="bridge_status",
                    description="Get validation bridge status",
                    inputSchema={"type": "object", "properties": {}}
                ),
                types.Tool(
                    name="approve_command",
                    description="Pre-approve a command for execution",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command_id": {"type": "string", "description": "Command ID"},
                            "reason": {"type": "string", "description": "Approval reason"}
                        },
                        "required": ["command_id"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool calls."""
            try:
                if name == "validate_command":
                    result = await self.validator.validate_command(
                        tool=arguments["tool"],
                        tool_input=arguments["input"],
                        agent=arguments.get("agent", "unknown")
                    )
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "bridge_status":
                    status = await self.bridge.get_status()
                    return [types.TextContent(type="text", text=json.dumps(status, indent=2))]
                
                elif name == "approve_command":
                    result = await self.bridge.approve_command(
                        command_id=arguments["command_id"],
                        reason=arguments.get("reason", "Manual approval")
                    )
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                else:
                    raise ValueError(f"Unknown tool: {name}")
                    
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def start(self):
        """Start the server."""
        logger.info("Starting Lighthouse MCP Server")
        await self.bridge.start()
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="lighthouse",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=None,
                        experimental_capabilities={}
                    )
                )
            )

def main():
    """Main entry point."""
    server = LighthouseServer()
    asyncio.run(server.start())

if __name__ == "__main__":
    main()