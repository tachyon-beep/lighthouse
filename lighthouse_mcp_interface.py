#!/usr/bin/env python3
"""
Lighthouse MCP Interface - Thin Proxy for Claude Code Integration

This script serves as the thin interface layer between Claude Code's MCP client
and the persistent Lighthouse MCP server. It handles:

1. Server lifecycle management (auto-start, health checks)
2. HTTP proxy to persistent server REST API
3. MCP protocol translation and error handling
4. Connection pooling and performance optimization

Architecture:
  Claude Code MCP Client -> This Script -> HTTP REST -> Persistent Lighthouse Server

Usage:
  - Configure .mcp.json to point to this script
  - Script automatically starts persistent server if not running
  - All MCP tool calls are proxied to the persistent server
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import requests
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[MCP-INTERFACE] %(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('/tmp/lighthouse_mcp_interface.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class LighthouseMCPInterface:
    """Thin MCP interface proxy for Claude Code integration"""
    
    def __init__(self):
        self.server_url = "http://localhost:8765"
        self.server_process: Optional[subprocess.Popen] = None
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.project_root = Path(__file__).parent
        
        # Configure connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('http://', adapter)
    
    def is_server_running(self) -> bool:
        """Check if persistent Lighthouse server is running"""
        try:
            response = self.session.get(f"{self.server_url}/status", timeout=2)
            return response.status_code == 200 and response.json().get("status") == "running"
        except:
            return False
    
    def start_persistent_server(self) -> bool:
        """Start the persistent Lighthouse MCP server"""
        try:
            logger.info("Starting persistent Lighthouse MCP server...")
            
            # Path to the server daemon  
            server_script = self.project_root / "lighthouse_server_daemon.py"
            if not server_script.exists():
                logger.error(f"Server script not found: {server_script}")
                return False
            
            # Set up environment
            env = os.environ.copy()
            env['PYTHONPATH'] = str(self.project_root / "src")
            
            # Start server process
            self.server_process = subprocess.Popen(
                [sys.executable, str(server_script)],
                env=env,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            # Wait for server to start with timeout
            max_attempts = 30  # 30 seconds
            for attempt in range(max_attempts):
                time.sleep(1)
                if self.is_server_running():
                    logger.info("✅ Persistent Lighthouse MCP server started successfully")
                    return True
                
                # Check if process died
                if self.server_process.poll() is not None:
                    stdout, stderr = self.server_process.communicate()
                    logger.error(f"Server process died: stdout={stdout.decode()[:500]}, stderr={stderr.decode()[:500]}")
                    return False
            
            logger.error("❌ Server failed to start within timeout")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to start persistent server: {e}")
            return False
    
    def ensure_server_running(self) -> bool:
        """Ensure persistent server is running, start if needed"""
        if self.is_server_running():
            logger.debug("Persistent server already running")
            return True
        
        logger.info("Persistent server not running, starting...")
        return self.start_persistent_server()
    
    def proxy_mcp_call(self, tool_name: str, **kwargs) -> str:
        """Proxy MCP tool call to persistent server"""
        try:
            # Ensure server is running
            if not self.ensure_server_running():
                return json.dumps({
                    "error": "Failed to start persistent Lighthouse MCP server",
                    "status": "server_unavailable"
                })
            
            # Map tool name to REST endpoint
            endpoint = f"/mcp/{tool_name}"
            
            logger.info(f"🔧 Proxying MCP call: {tool_name}({', '.join(f'{k}={repr(v)[:50]}' for k, v in kwargs.items())})")
            
            # Make HTTP request to persistent server
            response = self.session.post(
                f"{self.server_url}{endpoint}",
                json=kwargs,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    logger.info(f"✅ MCP call successful: {tool_name}")
                    return result.get("result", "")
                else:
                    logger.error(f"❌ MCP call failed: {result}")
                    return json.dumps(result)
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"❌ HTTP error for {tool_name}: {error_msg}")
                return json.dumps({
                    "error": error_msg,
                    "status": "http_error",
                    "status_code": response.status_code
                })
                
        except requests.RequestException as e:
            logger.error(f"❌ Request error for {tool_name}: {e}")
            return json.dumps({
                "error": str(e),
                "status": "request_error"
            })
        except Exception as e:
            logger.error(f"❌ Unexpected error for {tool_name}: {e}")
            return json.dumps({
                "error": str(e),
                "status": "unexpected_error"
            })
    
    def health_check(self) -> str:
        """Health check for the interface"""
        try:
            if not self.ensure_server_running():
                return json.dumps({
                    "status": "unhealthy",
                    "message": "Persistent server failed to start"
                })
            
            # Test server health
            response = self.session.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                server_health = response.json()
                return json.dumps({
                    "status": "healthy",
                    "interface": "lighthouse_mcp_interface",
                    "server": server_health,
                    "proxy_active": True
                })
            else:
                return json.dumps({
                    "status": "unhealthy",
                    "message": f"Server health check failed: HTTP {response.status_code}"
                })
                
        except Exception as e:
            return json.dumps({
                "status": "unhealthy",
                "error": str(e)
            })

# Global interface instance
interface = LighthouseMCPInterface()

# =====================================
# MCP TOOL FUNCTIONS (FastMCP Format)
# =====================================

def lighthouse_get_health(session_token: str = "") -> str:
    """Get Lighthouse Bridge health with session validation"""
    return interface.proxy_mcp_call("lighthouse_get_health", session_token=session_token)

def lighthouse_create_session(agent_id: str, ip_address: str = "", user_agent: str = "") -> str:
    """Create a new authenticated session"""
    return interface.proxy_mcp_call("lighthouse_create_session", 
                                   agent_id=agent_id, 
                                   ip_address=ip_address, 
                                   user_agent=user_agent)

def lighthouse_store_event_secure(event_type: str, aggregate_id: str, data: Dict[str, Any], 
                                 metadata: Optional[Dict[str, Any]] = None, 
                                 session_token: str = "") -> str:
    """Store an event with full Bridge security validation"""
    return interface.proxy_mcp_call("lighthouse_store_event_secure",
                                   event_type=event_type,
                                   aggregate_id=aggregate_id,
                                   data=data,
                                   metadata=metadata,
                                   session_token=session_token)

def lighthouse_query_events(aggregate_ids: Optional[List[str]] = None,
                           event_types: Optional[List[str]] = None,
                           limit: int = 10,
                           session_token: str = "") -> str:
    """Query events with session validation"""
    return interface.proxy_mcp_call("lighthouse_query_events",
                                   aggregate_ids=aggregate_ids,
                                   event_types=event_types,
                                   limit=limit,
                                   session_token=session_token)

def lighthouse_validate_session(session_token: str, agent_id: str) -> str:
    """Validate a session token"""
    return interface.proxy_mcp_call("lighthouse_validate_session",
                                   session_token=session_token,
                                   agent_id=agent_id)

def lighthouse_get_coordination_stats(session_token: str = "") -> str:
    """Get expert coordination statistics"""
    return interface.proxy_mcp_call("lighthouse_get_coordination_stats",
                                   session_token=session_token)

def lighthouse_get_memory_stats(session_token: str = "") -> str:
    """Get memory usage statistics"""
    return interface.proxy_mcp_call("lighthouse_get_memory_stats",
                                   session_token=session_token)

def lighthouse_get_production_health(session_token: str = "") -> str:
    """Get comprehensive production health status"""
    return interface.proxy_mcp_call("lighthouse_get_production_health",
                                   session_token=session_token)

def lighthouse_pair_request(requester: str, task: str, mode: str = "collaborative", session_token: str = "") -> str:
    """Create a pair programming session request"""
    return interface.proxy_mcp_call("lighthouse_pair_request",
                                   requester=requester,
                                   task=task,
                                   mode=mode,
                                   session_token=session_token)

def lighthouse_pair_suggest(session_id: str, agent_id: str, suggestion: str, file_path: str = "", line: int = 0, session_token: str = "") -> str:
    """Make a suggestion during pair programming"""
    return interface.proxy_mcp_call("lighthouse_pair_suggest",
                                   session_id=session_id,
                                   agent_id=agent_id,
                                   suggestion=suggestion,
                                   file_path=file_path,
                                   line=line,
                                   session_token=session_token)

def lighthouse_create_snapshot(name: str, description: str = "", session_token: str = "") -> str:
    """Create a project snapshot for time travel debugging"""
    return interface.proxy_mcp_call("lighthouse_create_snapshot",
                                   name=name,
                                   description=description,
                                   session_token=session_token)

def lighthouse_shadow_search(pattern: str, file_types: Optional[List[str]] = None, session_token: str = "") -> str:
    """Search across shadow filesystem files"""
    return interface.proxy_mcp_call("lighthouse_shadow_search",
                                   pattern=pattern,
                                   file_types=file_types,
                                   session_token=session_token)

def lighthouse_shadow_annotate(file_path: str, line: int, message: str, category: str = "general", session_token: str = "") -> str:
    """Add an expert annotation to a shadow file"""
    return interface.proxy_mcp_call("lighthouse_shadow_annotate",
                                   file_path=file_path,
                                   line=line,
                                   message=message,
                                   category=category,
                                   session_token=session_token)

# Health check endpoint for interface
def interface_health_check() -> str:
    """Health check for the MCP interface proxy"""
    return interface.health_check()

# =====================================
# FASTMCP INTEGRATION
# =====================================

if __name__ == "__main__":
    try:
        # Import FastMCP if available
        from fastmcp import FastMCP
        
        # Create FastMCP server with all tools
        mcp = FastMCP("Lighthouse MCP Interface")
        
        # Register MCP tools using decorator pattern
        @mcp.tool
        def lighthouse_get_health(session_token: str = "") -> str:
            """Get Lighthouse Bridge health with session validation"""
            return interface.proxy_mcp_call("lighthouse_get_health", session_token=session_token)
        
        @mcp.tool
        def lighthouse_create_session(agent_id: str, ip_address: str = "", user_agent: str = "") -> str:
            """Create a new authenticated session"""
            return interface.proxy_mcp_call("lighthouse_create_session", 
                                           agent_id=agent_id, 
                                           ip_address=ip_address, 
                                           user_agent=user_agent)
        
        @mcp.tool
        def lighthouse_store_event_secure(event_type: str, aggregate_id: str, data: Dict[str, Any], 
                                         metadata: Optional[Dict[str, Any]] = None, 
                                         session_token: str = "") -> str:
            """Store an event with full Bridge security validation"""
            return interface.proxy_mcp_call("lighthouse_store_event_secure",
                                           event_type=event_type,
                                           aggregate_id=aggregate_id,
                                           data=data,
                                           metadata=metadata,
                                           session_token=session_token)
        
        @mcp.tool
        def lighthouse_query_events(aggregate_ids: Optional[List[str]] = None,
                                   event_types: Optional[List[str]] = None,
                                   limit: int = 10,
                                   session_token: str = "") -> str:
            """Query events with session validation"""
            return interface.proxy_mcp_call("lighthouse_query_events",
                                           aggregate_ids=aggregate_ids,
                                           event_types=event_types,
                                           limit=limit,
                                           session_token=session_token)
        
        @mcp.tool
        def lighthouse_pair_request(requester: str, task: str, mode: str = "collaborative", session_token: str = "") -> str:
            """Create a pair programming session request"""
            return interface.proxy_mcp_call("lighthouse_pair_request",
                                           requester=requester,
                                           task=task,
                                           mode=mode,
                                           session_token=session_token)
        
        @mcp.tool
        def lighthouse_pair_suggest(session_id: str, agent_id: str, suggestion: str, file_path: str = "", line: int = 0, session_token: str = "") -> str:
            """Make a suggestion during pair programming"""
            return interface.proxy_mcp_call("lighthouse_pair_suggest",
                                           session_id=session_id,
                                           agent_id=agent_id,
                                           suggestion=suggestion,
                                           file_path=file_path,
                                           line=line,
                                           session_token=session_token)
        
        @mcp.tool
        def lighthouse_create_snapshot(name: str, description: str = "", session_token: str = "") -> str:
            """Create a project snapshot for time travel debugging"""
            return interface.proxy_mcp_call("lighthouse_create_snapshot",
                                           name=name,
                                           description=description,
                                           session_token=session_token)
        
        @mcp.tool
        def lighthouse_shadow_search(pattern: str, file_types: Optional[List[str]] = None, session_token: str = "") -> str:
            """Search across shadow filesystem files"""
            return interface.proxy_mcp_call("lighthouse_shadow_search",
                                           pattern=pattern,
                                           file_types=file_types,
                                           session_token=session_token)
        
        @mcp.tool
        def lighthouse_shadow_annotate(file_path: str, line: int, message: str, category: str = "general", session_token: str = "") -> str:
            """Add an expert annotation to a shadow file"""
            return interface.proxy_mcp_call("lighthouse_shadow_annotate",
                                           file_path=file_path,
                                           line=line,
                                           message=message,
                                           category=category,
                                           session_token=session_token)
        
        @mcp.tool
        def interface_health_check() -> str:
            """Health check for the MCP interface proxy"""
            return interface.health_check()
        
        logger.info("🚀 Starting Lighthouse MCP Interface Proxy")
        logger.info("   Architecture: Claude Code -> Thin Interface -> HTTP -> Persistent Server")
        logger.info("   Server URL: http://localhost:8765")
        logger.info("   Interface Log: /tmp/lighthouse_mcp_interface.log")
        
        # Ensure server is running before starting interface
        if interface.ensure_server_running():
            logger.info("✅ Persistent Lighthouse server is ready")
            logger.info("🎯 Starting MCP interface proxy...")
            mcp.run()
        else:
            logger.error("❌ Failed to start persistent server, exiting")
            sys.exit(1)
            
    except ImportError:
        logger.error("❌ FastMCP not available, please install: pip install fastmcp")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start MCP interface: {e}")
        sys.exit(1)