#!/usr/bin/env python3
"""
Lighthouse MCP Server - HTTP Client for Bridge

This MCP server runs on the HOST and connects to the Bridge running in a CONTAINER.
All Bridge functionality is accessed via HTTP API calls to localhost:8765.

Architecture:
- MCP Server (this file): Runs on HOST, provides tools to Claude Code
- Bridge HTTP Server: Runs in CONTAINER on port 8765
- Communication: HTTP/WebSocket between MCP and Bridge
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

import aiohttp
from mcp.server.fastmcp import FastMCP

# Setup logging
logger = logging.getLogger("lighthouse.mcp")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('[MCP] %(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Create FastMCP server instance
mcp = FastMCP("lighthouse-bridge")

# Bridge HTTP API configuration
BRIDGE_URL = "http://localhost:8765"
TIMEOUT = aiohttp.ClientTimeout(total=30)

# Session management
current_session: Optional[Dict[str, str]] = None

# Connection pooling
connector = None

async def get_connector():
    """Get or create shared connection pool"""
    global connector
    if connector is None:
        connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool limit
            limit_per_host=30,  # Per-host connection limit
            ttl_dns_cache=300  # DNS cache timeout
        )
    return connector

async def http_request_with_retry(method: str, url: str, retries: int = 3, **kwargs) -> tuple[int, Any]:
    """Make HTTP request with retry logic and connection pooling
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: URL to request
        retries: Number of retry attempts
        **kwargs: Additional arguments for the request
    
    Returns:
        Tuple of (status_code, response_data)
    
    Raises:
        Last exception if all retries fail
    """
    last_error = None
    conn = await get_connector()
    
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT, connector=conn) as session:
                async with session.request(method, url, **kwargs) as resp:
                    # Read response data before context closes
                    try:
                        data = await resp.json()
                    except:
                        data = await resp.text()
                    
                    # For successful responses or client errors (4xx), return immediately
                    if resp.status < 500:
                        return resp.status, data
                    # For server errors (5xx), retry
                    last_error = f"Server error: {resp.status}"
        except aiohttp.ClientError as e:
            last_error = e
            logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
        except Exception as e:
            last_error = e
            logger.error(f"Unexpected error (attempt {attempt + 1}/{retries}): {e}")
        
        if attempt < retries - 1:
            await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
    
    raise Exception(f"All {retries} attempts failed. Last error: {last_error}")

async def ensure_session(retry_count: int = 3):
    """Ensure we have an active session with the Bridge
    
    Args:
        retry_count: Number of retries for session creation
    """
    global current_session
    
    if current_session:
        return current_session
    
    for attempt in range(retry_count):
        try:
            conn = await get_connector()
            async with aiohttp.ClientSession(timeout=TIMEOUT, connector=conn) as session:
                async with session.post(
                    f"{BRIDGE_URL}/session/create",
                    json={
                        "agent_id": "mcp_server",
                        "ip_address": "127.0.0.1",
                        "user_agent": "LighthouseMCP/1.0"
                    }
                ) as resp:
                    if resp.status == 200:
                        current_session = await resp.json()
                        logger.info(f"Created session: {current_session.get('session_id')}")
                        return current_session
                    else:
                        logger.error(f"Failed to create session: {resp.status}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        except Exception as e:
            logger.error(f"Session creation error (attempt {attempt + 1}): {e}")
            if attempt < retry_count - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
    
    return None

# MCP Tool Definitions

@mcp.tool()
async def lighthouse_get_bridge_status(request: Dict[str, Any]) -> str:
    """Get the current status of the Lighthouse Bridge"""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(f"{BRIDGE_URL}/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return f"Error: Bridge returned status {resp.status}"
    except aiohttp.ClientError as e:
        return f"Error: Could not connect to Bridge - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def lighthouse_validate_command(
    tool_name: str,
    tool_input: Dict[str, Any],
    agent_id: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Validate a command through the Bridge's speed layer"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/validate",
                json={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "agent_id": agent_id,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_create_session(
    agent_id: str,
    ip_address: str,
    user_agent: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new authenticated session with the Bridge"""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/session/create",
                json={
                    "agent_id": agent_id,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "metadata": metadata or {}
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_validate_session(
    session_token: str,
    agent_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> str:
    """Validate a session token"""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/session/validate",
                json={
                    "session_token": session_token,
                    "agent_id": agent_id,
                    "ip_address": ip_address,
                    "user_agent": user_agent
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_register_expert(
    agent_id: str,
    agent_type: str,
    capabilities: List[str],
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Register an expert agent with the Bridge"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/expert/register",
                json={
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "capabilities": capabilities,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_delegate_to_expert(
    tool_name: str,
    tool_input: Dict[str, Any],
    target_expert: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Delegate a command to an expert through the Bridge"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/expert/delegate",
                json={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "target_expert": target_expert,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_store_event(
    event_type: str,
    event_data: Dict[str, Any],
    agent_id: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Store an event in the event-sourced architecture"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/event/store",
                json={
                    "event_type": event_type,
                    "data": event_data,  # HTTP server expects 'data' not 'event_data'
                    "agent_id": agent_id,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                elif resp.status == 403:
                    # Session expired or invalid, clear it
                    global current_session
                    current_session = None
                    logger.warning("Session invalidated due to 403 response in store_event")
                    return json.dumps({"error": "Session expired, please retry"})
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_query_events(
    event_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100
) -> str:
    """Query events from the event store"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            params = {
                "event_type": event_type,
                "agent_id": agent_id,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit
            }
            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}
            
            async with client.get(
                f"{BRIDGE_URL}/event/query",
                params=params,
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_dispatch_task(
    task_description: str,
    target_agent: str,
    priority: str = "normal",
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Dispatch a task to another agent for multi-agent coordination"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/task/dispatch",
                json={
                    "task_description": task_description,
                    "target_agent": target_agent,
                    "priority": priority,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_start_collaboration(
    collaboration_type: str,
    participants: List[str],
    objective: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Start a pair programming or collaboration session between agents"""
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/collaboration/start",
                json={
                    "collaboration_type": collaboration_type,
                    "participants": participants,
                    "objective": objective,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_health_check() -> str:
    """Check health of both MCP server and Bridge connection"""
    mcp_health = "healthy"
    bridge_health = "unknown"
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(f"{BRIDGE_URL}/health") as resp:
                if resp.status == 200:
                    bridge_health = "healthy"
                else:
                    bridge_health = f"unhealthy (status {resp.status})"
    except Exception as e:
        bridge_health = f"unreachable ({str(e)})"
    
    return json.dumps({
        "mcp_server": mcp_health,
        "bridge_connection": bridge_health,
        "bridge_url": BRIDGE_URL,
        "architecture": "MCP on host, Bridge in container"
    }, indent=2)

@mcp.tool()
async def lighthouse_wait_for_messages(
    agent_id: str,
    timeout_seconds: int = 60,
    since_sequence: Optional[int] = None
) -> str:
    """
    Wait for new messages/events from other agents with long-polling.
    Returns immediately if new messages arrive, otherwise waits up to timeout_seconds.
    Supports up to 300 seconds for expert agents waiting for work.
    Perfect for avoiding fixed sleep delays in agent conversations.
    """
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        # Allow up to 300 seconds for long-running expert agents
        timeout = min(timeout_seconds, 300)
        params = {
            "agent_id": agent_id,
            "timeout_seconds": timeout,
        }
        if since_sequence is not None:
            params["since_sequence"] = since_sequence
            
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout+10)
        ) as client:
            async with client.get(
                f"{BRIDGE_URL}/event/wait",
                params=params,
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                else:
                    return json.dumps({"error": f"Bridge returned status {resp.status}"})
    except asyncio.TimeoutError:
        return json.dumps({"status": "timeout", "events": [], "count": 0})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ==================== ELICITATION TOOLS (FEATURE_PACK_0) ====================

@mcp.tool()
async def lighthouse_elicit_information(
    to_agent: str,
    message: str,
    schema: Dict[str, Any],
    timeout_seconds: int = 30,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Elicit structured information from another agent.
    
    This replaces wait_for_messages with immediate, structured communication.
    The target agent will receive the elicitation request and can respond with
    data matching the provided schema.
    
    Args:
        to_agent: Target agent to elicit information from
        message: Human-readable message explaining what's needed
        schema: JSON schema describing expected response structure
        timeout_seconds: How long to wait for response (default 30s)
        metadata: Optional metadata for the request
    
    Returns:
        Elicitation ID that can be used to check for responses
    """
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/elicitation/create",
                json={
                    "from_agent": session.get("agent_id", "mcp_server"),
                    "to_agent": to_agent,
                    "message": message,
                    "schema": schema,
                    "timeout_seconds": timeout_seconds,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                elif resp.status == 403:
                    # Session expired or invalid
                    global current_session
                    current_session = None
                    logger.warning("Session invalidated due to 403 response in elicit_information")
                    return json.dumps({"error": "Session expired, please retry"})
                else:
                    error_data = await resp.text()
                    return json.dumps({"error": f"Bridge returned status {resp.status}: {error_data}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_check_elicitations(
    agent_id: Optional[str] = None
) -> str:
    """
    Check for pending elicitation requests for this agent.
    
    Returns a list of pending elicitation requests that need responses.
    Each request includes the message, schema, and metadata from the requesting agent.
    
    Args:
        agent_id: Agent ID to check (defaults to current session agent)
    
    Returns:
        List of pending elicitation requests
    """
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    # Use provided agent_id or session agent_id
    target_agent = agent_id or session.get("agent_id", "mcp_server")
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.get(
                f"{BRIDGE_URL}/elicitation/pending",
                params={"agent_id": target_agent},
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                elif resp.status == 403:
                    # Session expired or invalid
                    global current_session
                    current_session = None
                    logger.warning("Session invalidated due to 403 response in check_elicitations")
                    return json.dumps({"error": "Session expired, please retry"})
                else:
                    error_data = await resp.text()
                    return json.dumps({"error": f"Bridge returned status {resp.status}: {error_data}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def lighthouse_respond_to_elicitation(
    elicitation_id: str,
    response_type: str,
    data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Respond to an elicitation request from another agent.
    
    Args:
        elicitation_id: ID of the elicitation to respond to
        response_type: Type of response - "accept", "decline", or "cancel"
        data: Response data (required if accepting, must match schema)
        metadata: Optional metadata for the response
    
    Returns:
        Success status of the response
    """
    session = await ensure_session()
    if not session:
        return json.dumps({"error": "Could not establish session with Bridge"})
    
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as client:
            async with client.post(
                f"{BRIDGE_URL}/elicitation/respond",
                json={
                    "elicitation_id": elicitation_id,
                    "responding_agent": session.get("agent_id", "mcp_server"),
                    "response_type": response_type,
                    "data": data,
                    "metadata": metadata or {}
                },
                headers={"Authorization": f"Bearer {session.get('session_token')}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
                elif resp.status == 403:
                    # Session expired or invalid
                    global current_session
                    current_session = None
                    logger.warning("Session invalidated due to 403 response in respond_to_elicitation")
                    return json.dumps({"error": "Session expired, please retry"})
                else:
                    error_data = await resp.text()
                    return json.dumps({"error": f"Bridge returned status {resp.status}: {error_data}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# Initialization
async def initialize():
    """Initialize MCP server and check Bridge connection"""
    logger.info("🚀 Lighthouse MCP Server (HTTP Client) starting...")
    logger.info(f"Bridge URL: {BRIDGE_URL}")
    
    # Check Bridge connection
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(f"{BRIDGE_URL}/health") as resp:
                if resp.status == 200:
                    logger.info("✅ Successfully connected to Bridge")
                else:
                    logger.warning(f"⚠️  Bridge returned status {resp.status}")
    except Exception as e:
        logger.error(f"❌ Could not connect to Bridge: {e}")
        logger.info("Bridge may not be running. Start the container first.")

# Main entry point
if __name__ == "__main__":
    # Run initialization
    asyncio.run(initialize())
    
    # Run MCP server in stdio mode
    logger.info("Starting MCP server in stdio mode...")
    mcp.run(transport="stdio")