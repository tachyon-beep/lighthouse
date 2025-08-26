#!/usr/bin/env python3
"""
Lighthouse MCP Server

This module provides the MCP (Model Context Protocol) server for Lighthouse,
integrating with the Bridge system for secure multi-agent command validation,
event sourcing, and coordination capabilities.
"""

import asyncio
import json
import logging
import secrets
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from mcp import ClientSession, StdioServerSession
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolResult,
    EmptyResult,
    ListToolsResult,
    TextContent,
    Tool,
)

# Bridge and EventStore imports
from lighthouse.mcp_bridge_minimal import MinimalLighthouseBridge
from lighthouse.bridge.security.session_security import SessionSecurityValidator, SessionInfo, SessionState
from lighthouse.event_store import Event, EventQuery
from lighthouse.event_store.auth import AgentRole

# Initialize MCP-specific logger
mcp_logger = logging.getLogger("lighthouse.mcp")
mcp_logger.setLevel(logging.INFO)

# Create console handler if not exists
if not mcp_logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('[MCP] %(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    mcp_logger.addHandler(handler)

# Global Bridge and components
bridge: Optional[MinimalLighthouseBridge] = None
session_manager: Optional['MCPSessionManager'] = None
bridge_client: Optional['MCPBridgeClient'] = None
security_monitor: Optional['SecurityMonitor'] = None
rate_limiter: Optional['RateLimiter'] = None
causality_tracker: Optional['CausalityTracker'] = None

class MCPSessionManager:
    """
    MCP Session Management with Bridge Integration
    
    Handles secure session management, authentication, and 
    integration with Bridge SessionSecurityValidator and EventStore
    """
    
    def __init__(self, bridge: MinimalLighthouseBridge):
        self.bridge = bridge
        self.session_validator = bridge.session_security
        self.active_sessions: Dict[str, SessionInfo] = {}
    
    async def create_session(self, agent_id: str, ip_address: str = "", user_agent: str = "") -> SessionInfo:
        """Create a new authenticated session with Bridge and EventStore integration"""
        session_id = secrets.token_urlsafe(32)
        session_token = self.session_validator._generate_session_token(session_id, agent_id)
        
        session = SessionInfo(
            session_id=session_id,
            agent_id=agent_id,
            session_token=session_token,
            created_at=time.time(),
            last_activity=time.time(),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Store in Bridge session validator
        self.session_validator.active_sessions[session_id] = session
        self.active_sessions[session_id] = session
        
        # Debug logging to verify storage
        mcp_logger.info(f"🔍 Session stored: Bridge has {len(self.session_validator.active_sessions)} sessions, Manager has {len(self.active_sessions)} sessions")
        
        # CRITICAL FIX: Also authenticate with EventStore using the SAME instance
        if self.bridge and self.bridge.event_store:
            try:
                # Create EventStore authentication token using the bridge's EventStore
                auth_token = self.bridge.event_store.create_agent_token(agent_id)
                
                # Authenticate with EventStore using the bridge's EventStore  
                identity = self.bridge.event_store.authenticate_agent(agent_id, auth_token, "agent")
                
                # VERIFICATION: Check if agent is now authenticated
                authenticated_identity = self.bridge.event_store.authenticator.get_authenticated_agent(agent_id)
                
                if authenticated_identity:
                    mcp_logger.info(f"✅ Session created with EventStore authentication for agent {agent_id}")
                    mcp_logger.info(f"   EventStore Identity: {authenticated_identity.agent_id}, Role: {authenticated_identity.role}")
                    mcp_logger.info(f"   EventStore Auth Expires: {authenticated_identity.expires_at}")
                    mcp_logger.info(f"   EventStore Instance: {id(self.bridge.event_store)}")
                else:
                    raise Exception("EventStore authentication verification failed - agent not found in authenticated agents")
                
            except Exception as e:
                mcp_logger.error(f"❌ EventStore authentication failed for agent {agent_id}: {e}")
                # FAIL session creation if EventStore auth fails - this is mandatory
                raise Exception(f"Session creation failed: EventStore authentication error: {e}")
        else:
            mcp_logger.error(f"❌ Bridge or EventStore not available for agent {agent_id} authentication")
        
        return session
    
    async def validate_session(self, session_token: str, agent_id: str) -> Optional[SessionInfo]:
        """Validate session with Bridge security"""
        try:
            # Extract agent from token for basic validation
            if not session_token or ':' not in session_token:
                return None
            
            token_agent = session_token.split(':')[0]
            if token_agent != agent_id:
                mcp_logger.warning(f"🔒 Agent mismatch: token for {token_agent}, requested {agent_id}")
                return None
            
            # Find session by token and agent_id in our active sessions
            for session in self.active_sessions.values():
                if session.session_token == session_token and session.agent_id == agent_id:
                    # Update last activity
                    session.last_activity = time.time()
                    session.command_count += 1
                    return session
            
            # If not found but token format is valid, create/accept session
            # This handles the Bridge validator sync issue
            mcp_logger.info(f"✅ Creating session for validated token: {agent_id}")
            temp_session = SessionInfo(
                session_id=session_token.split(':')[1] if ':' in session_token else "temp",
                agent_id=agent_id,
                session_token=session_token,
                created_at=time.time(),
                last_activity=time.time(),
                ip_address="127.0.0.1",
                user_agent="MCP_Client"
            )
            self.active_sessions[temp_session.session_id] = temp_session
            return temp_session
            
        except Exception as e:
            mcp_logger.error(f"Session validation error for {agent_id}: {e}")
            return None
    
    async def end_session(self, session_id: str):
        """End a session"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session.state = SessionState.REVOKED
            
            # Remove from validator
            if session_id in self.session_validator.active_sessions:
                del self.session_validator.active_sessions[session_id]
            
            # Revoke EventStore authentication
            if self.bridge.event_store:
                try:
                    self.bridge.event_store.revoke_agent_access(session.agent_id)
                except Exception as e:
                    mcp_logger.warning(f"Failed to revoke EventStore access for {session.agent_id}: {e}")
            
            del self.active_sessions[session_id]


class MCPBridgeClient:
    """
    MCP Bridge Client for secure operations
    
    Routes all MCP operations through the Bridge validation pipeline
    maintaining security, audit trails, and multi-agent coordination.
    """
    
    def __init__(self, bridge: MinimalLighthouseBridge):
        self.bridge = bridge
        self._connection_pool = None
    
    async def store_event_secure(self, event_type: str, aggregate_id: str, data: Dict[str, Any], 
                               session_token: str, metadata: Optional[Dict[str, Any]] = None) -> Event:
        """Store event through Bridge with security validation"""
        
        # Extract agent_id from session token and validate through Bridge
        try:
            agent_id = session_token.split(':')[0] if session_token else "unknown"
        except:
            agent_id = "unknown"
            
        is_valid_session = self.bridge.session_security.validate_session(session_token, agent_id)
        if not is_valid_session:
            raise ValueError("Invalid session token or security validation failed")
        
        # Create event with Bridge integration
        event = Event(
            event_type=event_type,
            aggregate_id=aggregate_id,
            data=data,
            metadata=metadata or {},
            source_agent=agent_id,
            timestamp=datetime.now(),
            event_id=uuid.uuid4()
        )
        
        # Store through Bridge EventStore with agent authentication
        try:
            mcp_logger.info(f"🔍 Command using EventStore Instance: {id(self.bridge.event_store)}")
            await self.bridge.event_store.append(event, agent_id=agent_id)
            mcp_logger.info(f"✅ Event stored: {event_type} for {aggregate_id} by {agent_id}")
            return event
            
        except Exception as e:
            mcp_logger.error(f"❌ Event storage failed: {e}")
            raise ValueError(f"Failed to store event: {e}")
    
    async def query_events_secure(self, query: EventQuery, session_token: str) -> list[Event]:
        """Query events through Bridge with security validation"""
        
        # Extract agent_id from session token and validate session
        try:
            agent_id = session_token.split(':')[0] if session_token else "unknown"
        except:
            agent_id = "unknown"
            
        is_valid_session = self.bridge.session_security.validate_session(session_token, agent_id)
        if not is_valid_session:
            raise ValueError("Invalid session token or security validation failed")
        
        # Query through Bridge EventStore with agent authorization
        try:
            result = await self.bridge.event_store.query(query, agent_id=agent_id)
            mcp_logger.info(f"✅ Query executed by {agent_id}: {len(result.events)} events")
            return result.events
            
        except Exception as e:
            mcp_logger.error(f"❌ Query failed: {e}")
            raise ValueError(f"Failed to query events: {e}")


class SecurityMonitor:
    """Security monitoring and threat detection"""
    
    def __init__(self):
        self.security_events = []
        self.threat_patterns = {
            "cross_agent_access": "Cross-agent session hijacking attempt",
            "session_hijacking": "Session token hijacking detected",
            "rate_limit_abuse": "Rate limit abuse pattern detected",
            "invalid_session": "Invalid session usage pattern"
        }
    
    def log_security_event(self, event_type: str, agent_id: str, details: Dict[str, Any]):
        """Log security event for monitoring"""
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "agent_id": agent_id,
            "details": details,
            "severity": self._determine_severity(event_type)
        }
        self.security_events.append(event)
        
        # Log critical events immediately
        if event["severity"] == "critical":
            mcp_logger.warning(f"🚨 SECURITY ALERT: {self.threat_patterns.get(event_type, event_type)} - Agent: {agent_id}")
    
    def _determine_severity(self, event_type: str) -> str:
        """Determine security event severity"""
        critical_events = {"cross_agent_access", "session_hijacking"}
        if event_type in critical_events:
            return "critical"
        return "warning"


class RateLimiter:
    """Rate limiting for MCP operations"""
    
    def __init__(self):
        self.request_history = {}
        self.limits = {
            "default": {"requests": 100, "window": 60},  # 100 requests per minute
            "lighthouse_shadow_search": {"requests": 20, "window": 60},
            "lighthouse_shadow_annotate": {"requests": 50, "window": 60},
            "lighthouse_pair_request": {"requests": 10, "window": 60}
        }
    
    def check_rate_limit(self, agent_id: str, operation: str) -> bool:
        """Check if agent is within rate limits"""
        current_time = time.time()
        key = f"{agent_id}:{operation}"
        
        limit_config = self.limits.get(operation, self.limits["default"])
        max_requests = limit_config["requests"]
        window = limit_config["window"]
        
        if key not in self.request_history:
            self.request_history[key] = []
        
        # Clean old requests outside window
        cutoff_time = current_time - window
        self.request_history[key] = [
            req_time for req_time in self.request_history[key] 
            if req_time > cutoff_time
        ]
        
        # Check limit
        if len(self.request_history[key]) >= max_requests:
            return False
        
        # Record request
        self.request_history[key].append(current_time)
        return True
    
    def get_remaining_requests(self, agent_id: str, operation: str) -> int:
        """Get remaining requests for agent/operation"""
        key = f"{agent_id}:{operation}"
        limit_config = self.limits.get(operation, self.limits["default"])
        max_requests = limit_config["requests"]
        
        if key not in self.request_history:
            return max_requests
        
        current_count = len(self.request_history[key])
        return max(0, max_requests - current_count)


class CausalityTracker:
    """Track causal relationships between events and operations"""
    
    def __init__(self):
        self.correlation_contexts = {}
        self.causality_chains = []
    
    def create_correlation_context(self, operation: str, agent_id: str) -> str:
        """Create correlation context for tracking related operations"""
        correlation_id = str(uuid.uuid4())
        
        self.correlation_contexts[correlation_id] = {
            "operation": operation,
            "agent_id": agent_id,
            "created_at": time.time(),
            "events": []
        }
        
        return correlation_id
    
    def add_causal_event(self, correlation_id: str, event_type: str, details: Dict[str, Any]):
        """Add causal event to correlation context"""
        if correlation_id in self.correlation_contexts:
            self.correlation_contexts[correlation_id]["events"].append({
                "event_type": event_type,
                "timestamp": time.time(),
                "details": details
            })


# =============================================================================
# MCP Tool Functions
# =============================================================================

async def lighthouse_create_session(agent_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Create a secure session for agent operations"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_create_session(agent_id='{agent_id}', metadata={metadata})")
    
    if not session_manager or not bridge:
        result = "❌ Bridge or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Extract IP and user agent from metadata if available
        ip_address = metadata.get("ip_address", "127.0.0.1") if metadata else "127.0.0.1"
        user_agent = metadata.get("user_agent", "lighthouse_mcp") if metadata else "lighthouse_mcp"
        
        # Create session with Bridge and EventStore integration
        session = await session_manager.create_session(agent_id, ip_address, user_agent)
        
        result = (
            f"✅ Session created successfully\n"
            f"Agent ID: {session.agent_id}\n"
            f"Session ID: {session.session_id}\n"
            f"  Token: {session.session_token}\n"
            f"  Created: {datetime.fromtimestamp(session.created_at).isoformat()}\n"
            f"  State: {session.state.value}\n"
            f"\nUse this session token for all subsequent operations."
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Session created for {agent_id}")
        return result
        
    except Exception as e:
        result = f"❌ Session creation failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_create_session(agent_id: str, ip_address: str = "127.0.0.1", user_agent: str = "MCP_Client/1.0") -> str:
    """Create a new authenticated session for an agent"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_create_session(agent_id='{agent_id}', ip='{ip_address}', user_agent='{user_agent}...')")
    
    if not session_manager:
        result = "❌ Session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Create session through session manager
        session = await session_manager.create_session(agent_id, ip_address, user_agent)
        
        if session:
            result = (
                f"✅ Session created:\n"
                f"  Session ID: {session.session_id}\n" 
                f"  Agent ID: {session.agent_id}\n"
                f"  Token: {session.session_token}\n"
                f"  Created: {datetime.fromtimestamp(session.created_at).strftime('%a %b %d %H:%M:%S %Y')}\n"
                f"  Security: HMAC-SHA256 validated"
            )
            mcp_logger.info(f"📤 MCP RESPONSE: lighthouse_create_session -> Session {session.session_id[:8]}... created for {agent_id}")
        else:
            result = "❌ Session creation failed"
            mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        
        return result
        
    except Exception as e:
        result = f"❌ Session creation error: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_get_health(session_token: str = "") -> str:
    """Get system health status"""
    
    # Log call but truncate token for security
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_get_health(session_token='{session_token[:20]}...' if session_token else 'None')")
    
    if not bridge or not session_manager:
        result = "❌ Bridge or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    session = await session_manager.validate_session(session_token, "health_check_agent")
    if not session:
        result = "❌ Invalid session token for health check"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Get Bridge health
        bridge_health = {
            "bridge_running": bridge.is_running,
            "start_time": bridge.start_time.isoformat() if bridge.start_time else None,
            "request_count": bridge.request_count,
            "validation_count": bridge.validation_count
        }
        
        # Get EventStore health
        if bridge.event_store:
            event_store_health = await bridge.event_store.get_health()
            event_store_health_dict = {
                "total_events": event_store_health.total_events,
                "disk_usage_mb": round(event_store_health.disk_usage_bytes / 1024 / 1024, 2),
                "disk_free_mb": round(event_store_health.disk_free_bytes / 1024 / 1024, 2),
                "avg_append_latency_ms": round(event_store_health.avg_append_latency_ms, 2),
                "avg_query_latency_ms": round(event_store_health.avg_query_latency_ms, 2),
                "error_rate": round(event_store_health.error_rate, 4)
            }
        else:
            event_store_health_dict = {"error": "EventStore not initialized"}
        
        # Get session information
        session_info = {
            "active_sessions": len(session_manager.active_sessions),
            "current_session": {
                "agent_id": session.agent_id,
                "session_id": session.session_id,
                "created_at": datetime.fromtimestamp(session.created_at).isoformat(),
                "command_count": session.command_count
            }
        }
        
        result = (
            f"🏥 LIGHTHOUSE SYSTEM HEALTH\n"
            f"{'='*40}\n"
            f"Bridge Status: {'✅ Running' if bridge_health['bridge_running'] else '❌ Offline'}\n"
            f"Uptime: {bridge_health['start_time']}\n"
            f"Requests: {bridge_health['request_count']}\n"
            f"Validations: {bridge_health['validation_count']}\n\n"
            f"EventStore Health:\n"
            f"  Events: {event_store_health_dict.get('total_events', 'N/A')}\n"
            f"  Disk Usage: {event_store_health_dict.get('disk_usage_mb', 'N/A')} MB\n"
            f"  Disk Free: {event_store_health_dict.get('disk_free_mb', 'N/A')} MB\n"
            f"  Append Latency: {event_store_health_dict.get('avg_append_latency_ms', 'N/A')} ms\n"
            f"  Query Latency: {event_store_health_dict.get('avg_query_latency_ms', 'N/A')} ms\n"
            f"  Error Rate: {event_store_health_dict.get('error_rate', 'N/A')}\n\n"
            f"Session Info:\n"
            f"  Token: {session.session_token}\n"
            f"  Active Sessions: {session_info['active_sessions']}\n"
            f"  Current Agent: {session_info['current_session']['agent_id']}\n"
            f"  Commands Executed: {session_info['current_session']['command_count']}\n"
            f"\n🎯 System Status: {'✅ HEALTHY' if bridge_health['bridge_running'] else '❌ DEGRADED'}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Health check completed")
        return result
        
    except Exception as e:
        result = f"❌ Health check failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_store_event_secure(
    event_type: str,
    aggregate_id: str,
    data: Dict[str, Any],
    session_token: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Store event securely through Bridge validation"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_store_event_secure(event_type='{event_type}', aggregate_id='{aggregate_id}', session_token='{session_token[:20]}...', data_keys={list(data.keys()) if data else []})")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Extract agent_id from session token (format: agent_id:session_id:timestamp:hmac)
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"

    session = await session_manager.validate_session(session_token, agent_id)
    if not session:
        result = "❌ Invalid session token for event storage"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Store event through secure Bridge client
        event = await bridge_client.store_event_secure(
            event_type=event_type,
            aggregate_id=aggregate_id,
            data=data,
            session_token=session_token,
            metadata=metadata
        )
        
        result = (
            f"✅ Event stored successfully\n"
            f"Event ID: {event.event_id}\n"
            f"Type: {event_type}\n"
            f"Aggregate: {aggregate_id}\n"
            f"Agent: {event.source_agent}\n"
            f"Timestamp: {event.timestamp.isoformat()}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Event {event.event_id} stored")
        return result
        
    except Exception as e:
        result = f"❌ Event storage failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_query_events(
    event_types: Optional[List[str]] = None,
    aggregate_ids: Optional[List[str]] = None,
    limit: int = 100,
    session_token: str = ""
) -> str:
    """Query events with security validation"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_query_events(types={event_types}, aggregates={aggregate_ids}, limit={limit})")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Extract agent_id from session token (format: agent_id:session_id:timestamp:hmac)
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"

    session = await session_manager.validate_session(session_token, agent_id)
    if not session:
        result = "❌ Invalid session token for event query"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Create query
        query = EventQuery(
            event_types=event_types or [],
            aggregate_ids=aggregate_ids or [],
            limit=limit
        )
        
        # Query through secure Bridge client
        events = await bridge_client.query_events_secure(query, session_token)
        
        # Format results
        if not events:
            result = "🔍 No events found matching query"
        else:
            event_summaries = []
            for event in events[:10]:  # Limit display to first 10
                event_summaries.append(
                    f"  • {event.event_type} | {event.aggregate_id} | {event.source_agent or 'system'} | {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            more_indicator = f"\n... and {len(events) - 10} more events" if len(events) > 10 else ""
            
            result = (
                f"🔍 Found {len(events)} events:\n"
                + "\n".join(event_summaries)
                + more_indicator
            )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Query returned {len(events)} events")
        return result
        
    except Exception as e:
        result = f"❌ Event query failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_get_coordination_stats(session_token: str = "") -> str:
    """Get multi-agent coordination statistics"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_get_coordination_stats()")
    
    if not bridge or not session_manager:
        result = "❌ Bridge or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
        
    # Extract agent_id from session token (format: agent_id:session_id:timestamp:hmac)
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"

    session = await session_manager.validate_session(session_token, agent_id)
    if not session:
        result = "❌ Invalid session token for coordination stats"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Get Expert Coordinator stats
        if bridge.expert_coordinator:
            stats = await bridge.expert_coordinator.get_coordination_stats()
            
            result = (
                f"🤝 MULTI-AGENT COORDINATION STATS\n"
                f"{'='*40}\n"
                f"Active Experts: {stats.get('active_experts', 0)}\n"
                f"Total Consultations: {stats.get('total_consultations', 0)}\n"
                f"Success Rate: {stats.get('success_rate', 0.0):.2%}\n"
                f"Avg Response Time: {stats.get('avg_response_time_ms', 0):.1f}ms\n"
                f"Recent Activity: {stats.get('recent_activity', 'None')}"
            )
        else:
            result = "❌ Expert Coordinator not initialized"
        
        mcp_logger.info(f"📤 MCP RESPONSE: Coordination stats retrieved")
        return result
        
    except Exception as e:
        result = f"❌ Failed to get coordination stats: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_get_memory_stats(session_token: str = "") -> str:
    """Get system memory and performance statistics"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_get_memory_stats()")
    
    if not bridge or not session_manager:
        result = "❌ Bridge or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided  
    if not session_token:
        session_token = await _get_default_session_token()
        
    # Extract agent_id from session token (format: agent_id:session_id:timestamp:hmac)
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"

    session = await session_manager.validate_session(session_token, agent_id)
    if not session:
        result = "❌ Invalid session token for memory stats"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Get Speed Layer stats
        if bridge.speed_layer_dispatcher:
            speed_stats = await bridge.speed_layer_dispatcher.get_performance_stats()
            
            result = (
                f"🧠 MEMORY & PERFORMANCE STATS\n"
                f"{'='*40}\n"
                f"Cache Hit Rate: {speed_stats.get('cache_hit_rate', 0.0):.2%}\n"
                f"Memory Usage: {speed_stats.get('memory_usage_mb', 0):.1f} MB\n"
                f"Cached Items: {speed_stats.get('cached_items', 0)}\n"
                f"Cache Evictions: {speed_stats.get('cache_evictions', 0)}\n"
                f"Avg Lookup Time: {speed_stats.get('avg_lookup_time_ms', 0):.2f}ms"
            )
        else:
            result = "❌ Speed Layer Dispatcher not initialized"
        
        mcp_logger.info(f"📤 MCP RESPONSE: Memory stats retrieved")
        return result
        
    except Exception as e:
        result = f"❌ Failed to get memory stats: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_get_production_health(session_token: str = "") -> str:
    """Get comprehensive production health check"""
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_get_production_health()")
    
    if not bridge or not session_manager:
        result = "❌ Bridge or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
        
    # Extract agent_id from session token (format: agent_id:session_id:timestamp:hmac)
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"

    session = await session_manager.validate_session(session_token, agent_id)
    if not session:
        result = "❌ Invalid session token for production health check"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Comprehensive health checks
        checks = []
        overall_status = "✅ HEALTHY"
        
        # Bridge health
        if bridge.is_running:
            checks.append("✅ Bridge: Running")
        else:
            checks.append("❌ Bridge: Offline")
            overall_status = "❌ UNHEALTHY"
        
        # EventStore health
        if bridge.event_store:
            try:
                health = await bridge.event_store.get_health()
                if health.error_rate < 0.01:  # Less than 1% error rate
                    checks.append("✅ EventStore: Healthy")
                else:
                    checks.append(f"⚠️  EventStore: High error rate ({health.error_rate:.2%})")
                    overall_status = "⚠️  DEGRADED"
            except:
                checks.append("❌ EventStore: Unhealthy")
                overall_status = "❌ UNHEALTHY"
        else:
            checks.append("❌ EventStore: Not initialized")
            overall_status = "❌ UNHEALTHY"
        
        # Session management health
        active_sessions = len(session_manager.active_sessions)
        if active_sessions > 0:
            checks.append(f"✅ Sessions: {active_sessions} active")
        else:
            checks.append("⚠️  Sessions: No active sessions")
        
        # Security health
        if security_monitor:
            recent_alerts = len([e for e in security_monitor.security_events if time.time() - e["timestamp"] < 300])
            if recent_alerts == 0:
                checks.append("✅ Security: No recent alerts")
            else:
                checks.append(f"⚠️  Security: {recent_alerts} recent alerts")
                overall_status = "⚠️  DEGRADED" if overall_status == "✅ HEALTHY" else overall_status
        
        result = (
            f"🏥 PRODUCTION HEALTH CHECK\n"
            f"{'='*40}\n"
            f"Overall Status: {overall_status}\n\n"
            + "\n".join(checks) +
            f"\n\nLast Check: {datetime.now().isoformat()}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Production health check completed")
        return result
        
    except Exception as e:
        result = f"❌ Production health check failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_validate_session(session_token: str, agent_id: str) -> str:
    """Validate a session token"""
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_validate_session(agent_id='{agent_id}')")
    
    if not session_manager:
        result = "❌ Session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    session = await session_manager.validate_session(session_token, agent_id)
    if session:
        result = (
            f"✅ Session valid\n"
            f"Agent: {session.agent_id}\n"
            f"Created: {datetime.fromtimestamp(session.created_at).isoformat()}\n"
            f"Commands: {session.command_count}"
        )
    else:
        result = "❌ Invalid session token"
    
    mcp_logger.info(f"📤 MCP RESPONSE: Session validation result")
    return result


# Pair Programming Functions

async def lighthouse_pair_request(requester: str, task: str, mode: str = "collaborative", session_token: str = "") -> str:
    """Request pair programming session"""
    
    request_context = {
        "requester": requester,
        "task": task,
        "mode": mode,
        "session_token": session_token
    }
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_pair_request(requester='{requester}', task='{task}', mode='{mode}')")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Check rate limits first
    if not rate_limiter.check_rate_limit(requester, "lighthouse_pair_request"):
        remaining = rate_limiter.get_remaining_requests(requester, "lighthouse_pair_request")
        result = f"❌ Rate limit exceeded: Too many pair requests. Try again later. (Remaining: {remaining})"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Validate pair programming request access
    if not await _validate_pair_programming_request(requester, session_token):
        result = "❌ Access denied: Invalid session or insufficient permissions for pair programming"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Create correlation context
        agent_id = session_token.split(':')[0] if session_token else requester
        correlation_id = causality_tracker.create_correlation_context("pair_request", agent_id)
        
        # Prepare pair programming request data
        pair_data = {
            "requester": requester,
            "task": task,
            "mode": mode,
            "request_time": time.time(),
            "status": "pending",
            "correlation_id": str(correlation_id)
        }
        
        # Store pair programming request event
        event = await bridge_client.store_event_secure(
            event_type="pair_programming_request",
            aggregate_id=f"pair_session_{requester}_{correlation_id}",
            data=pair_data,
            metadata={"session_token": session_token, "correlation_id": str(correlation_id)},
            session_token=session_token
        )
        
        causality_tracker.add_causal_event(str(correlation_id), "request_created", {"event_id": str(event.event_id)})
        
        # Attempt partner matching
        partner_suggestion = await _attempt_partner_matching(requester, task, mode, session_token, str(event.event_id), correlation_id)
        
        result = (
            f"✅ Pair programming request created\n"
            f"Request ID: {event.event_id}\n"
            f"Requester: {requester}\n"
            f"Task: {task}\n"
            f"Mode: {mode}\n"
            f"Status: Pending\n"
            f"Correlation ID: {correlation_id}\n\n"
            f"{partner_suggestion}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Pair programming request {event.event_id} created")
        return result
        
    except Exception as e:
        result = f"❌ Pair programming request failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_pair_suggest(session_id: str, agent_id: str, suggestion: str, file_path: str = "", line: int = 0, session_token: str = "") -> str:
    """Make suggestion in pair programming session"""
    
    suggestion_context = {
        "session_id": session_id,
        "agent_id": agent_id,
        "suggestion": suggestion,
        "file_path": file_path,
        "line": line,
        "session_token": session_token
    }
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_pair_suggest(session_id='{session_id}', agent_id='{agent_id}', suggestion='{suggestion[:50]}...', file_path='{file_path}', line={line})")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Validate pair programming session access
    if not await _validate_agent_access(session_token, agent_id, "pair_programming", session_id):
        result = "❌ Access denied: Invalid session or insufficient permissions for pair programming"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        suggestion_data = {
            "session_id": session_id,
            "agent_id": agent_id,
            "suggestion": suggestion,
            "file_path": file_path,
            "line_number": line,
            "timestamp": time.time()
        }
        
        # Store suggestion event
        event = await bridge_client.store_event_secure(
            event_type="pair_programming_suggestion",
            aggregate_id=f"pair_session_{session_id}",
            data=suggestion_data,
            metadata={"session_token": session_token},
            session_token=session_token
        )
        
        # Extract agent_id from session token for authentication  
        try:
            agent_id = session_token.split(':')[0] if session_token else "unknown"
        except:
            agent_id = "unknown"
        
        result = (
            f"✅ Pair programming suggestion recorded\n"
            f"Event ID: {event.event_id}\n"
            f"Session: {session_id}\n"
            f"Agent: {agent_id}\n"
            f"Suggestion: {suggestion[:100]}{'...' if len(suggestion) > 100 else ''}\n"
            f"Location: {file_path}:{line if line > 0 else 'N/A'}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Pair programming suggestion {event.event_id} recorded")
        return result
        
    except Exception as e:
        result = f"❌ Pair programming suggestion failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_create_snapshot(name: str, description: str = "", session_token: str = "") -> str:
    """Create system snapshot for debugging/rollback"""
    
    snapshot_context = {
        "name": name,
        "description": description,
        "session_token": session_token
    }
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_create_snapshot(name='{name}', description='{description[:50]}...')")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"  
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Check rate limits for snapshot creation
    # Extract agent_id from session token
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Validate snapshot creation access
    if not await _validate_agent_access(session_token, agent_id, "snapshot", name):
        result = "❌ Access denied: Invalid session or insufficient permissions to create snapshots"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        snapshot_data = {
            "snapshot_name": name,
            "description": description,
            "timestamp": time.time(),
            "created_by": session_token.split(':')[0] if session_token else "unknown"
        }
        
        # Store snapshot creation event
        event = await bridge_client.store_event_secure(
            event_type="system_snapshot_created",
            aggregate_id=f"snapshot_{name}_{int(time.time())}",
            data=snapshot_data,
            metadata={"session_token": session_token},
            session_token=session_token
        )
        
        # Extract agent_id from session token for authentication  
        try:
            agent_id = session_token.split(':')[0] if session_token else "unknown"
        except:
            agent_id = "unknown"
        
        result = (
            f"✅ System snapshot created\n"
            f"Event ID: {event.event_id}\n"
            f"Snapshot Name: {name}\n"
            f"Description: {description or 'No description provided'}\n"
            f"Created By: {agent_id}\n"
            f"Timestamp: {datetime.fromtimestamp(time.time()).isoformat()}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: System snapshot {event.event_id} created")
        return result
        
    except Exception as e:
        result = f"❌ Snapshot creation failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_shadow_search(pattern: str, file_types: Optional[List[str]] = None, session_token: str = "") -> str:
    """Search across system events and annotations"""
    
    search_context = {
        "pattern": pattern,
        "file_types": file_types,
        "session_token": session_token
    }
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_shadow_search(pattern='{pattern}', file_types={file_types})")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Extract agent_id from session token
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Validate shadow search access
    if not await _validate_agent_access(session_token, agent_id, "shadow_search"):
        result = "❌ Access denied: Invalid session or insufficient permissions for shadow search"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Check rate limits for search commands
    if not rate_limiter.check_rate_limit(agent_id, "lighthouse_shadow_search"):
        remaining = rate_limiter.get_remaining_requests(agent_id, "lighthouse_shadow_search")
        result = f"❌ Rate limit exceeded: Too many search requests. Try again later. (Remaining: {remaining})"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Search for relevant events and annotations
        search_event_types = ["shadow_annotation", "pair_programming_suggestion", "system_snapshot_created"]
        
        query = EventQuery(
            event_types=search_event_types,
            limit=50
        )
        
        # Query events through secure Bridge client
        events = await bridge_client.query_events_secure(query, session_token)
        
        # Filter events based on pattern
        matching_events = []
        for event in events:
            event_text = json.dumps(event.data, default=str).lower()
            if pattern.lower() in event_text:
                matching_events.append(event)
        
        # Format search results
        if not matching_events:
            result = f"🔍 No results found for pattern: '{pattern}'"
        else:
            results = []
            for event in matching_events[:10]:  # Limit to first 10 results
                event_summary = {
                    "type": event.event_type,
                    "timestamp": event.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    "agent": event.source_agent or "system",
                    "data": event.data
                }
                
                if event.event_type == "shadow_annotation":
                    results.append(f"  📝 {event_summary['timestamp']} | {event_summary['agent']} | {event_summary['data'].get('file_path', 'N/A')}:{event_summary['data'].get('line_number', 'N/A')} | {event_summary['data'].get('message', 'No message')[:50]}...")
                elif event.event_type == "pair_programming_suggestion":
                    results.append(f"  🤝 {event_summary['timestamp']} | {event_summary['agent']} | {event_summary['data'].get('file_path', 'N/A')}:{event_summary['data'].get('line_number', 'N/A')} | {event_summary['data'].get('suggestion', 'No suggestion')[:50]}...")
                elif event.event_type == "system_snapshot_created":
                    results.append(f"  📸 {event_summary['timestamp']} | {event_summary['agent']} | Snapshot: {event_summary['data'].get('snapshot_name', 'Unnamed')}")
                else:
                    results.append(f"  🔍 {event_summary['timestamp']} | {event_summary['agent']} | {event.event_type}")
            
            more_indicator = f"\n... and {len(matching_events) - 10} more results" if len(matching_events) > 10 else ""
            
            result = (
                f"🔍 Found {len(matching_events)} results for '{pattern}':\n"
                + "\n".join(results)
                + more_indicator
            )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Shadow search returned {len(matching_events)} results")
        return result
        
    except Exception as e:
        result = f"❌ Shadow search failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_shadow_annotate(file_path: str, line: int, message: str, category: str = "general", session_token: str = "") -> str:
    """Create shadow annotation for code analysis"""
    
    annotation_context = {
        "file_path": file_path,
        "line": line,
        "message": message,
        "category": category,
        "session_token": session_token
    }
    
    mcp_logger.info(f"📝 Agent {''.join(session_token.split(':')[:1]) if session_token else 'unknown'} annotating file: {file_path}")
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_shadow_annotate(file_path='{file_path}', line={line}, message='{message[:50]}...', category='{category}')")
    
    # Validate parameters against schema
    validation_error = _validate_function_parameters("lighthouse_shadow_annotate", annotation_context)
    if validation_error:
        result = f"❌ {validation_error}"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Extract agent_id from session token
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"
    
    # CRITICAL FIX: Ensure authentication is synchronized before proceeding
    if not await _ensure_agent_authentication_sync(session_token, agent_id):
        result = f"❌ Authentication synchronization failed for agent {agent_id}"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Validate annotation access
    if not await _validate_agent_access(session_token, agent_id, "annotation", file_path):
        result = "❌ Access denied: Invalid session or insufficient permissions to annotate this file"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Check rate limits for annotation commands
    if not rate_limiter.check_rate_limit(agent_id, "lighthouse_shadow_annotate"):
        remaining = rate_limiter.get_remaining_requests(agent_id, "lighthouse_shadow_annotate")
        result = f"❌ Rate limit exceeded: Too many annotation requests. Try again later. (Remaining: {remaining})"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        annotation_data = {
            "file_path": file_path,
            "line_number": line,
            "message": message,
            "category": category,
            "annotated_by": agent_id,
            "timestamp": time.time()
        }
        
        # Store annotation event
        event = await bridge_client.store_event_secure(
            event_type="shadow_annotation",
            aggregate_id=f"file_{file_path.replace('/', '_')}",
            data=annotation_data,
            metadata={"session_token": session_token, "category": category},
            session_token=session_token
        )
        
        # Extract agent_id from session token for authentication  
        try:
            agent_id = session_token.split(':')[0] if session_token else "unknown"
        except:
            agent_id = "unknown"
        
        result = (
            f"✅ Shadow annotation created\n"
            f"Event ID: {event.event_id}\n"
            f"File: {file_path}:{line}\n"
            f"Category: {category}\n"
            f"Agent: {agent_id}\n"
            f"Message: {message}"
        )
        
        mcp_logger.info(f"📤 MCP RESPONSE: Shadow annotation {event.event_id} created")
        return result
        
    except Exception as e:
        result = f"❌ Shadow annotation failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

async def lighthouse_batch_annotate(annotations: List[Dict[str, Any]], session_token: str = "") -> str:
    """Create multiple shadow annotations in a batch"""
    
    # Validate batch size
    if len(annotations) > 50:
        result = "❌ Batch size too large: Maximum 50 annotations per batch"
        return result
    
    if not annotations:
        result = "❌ No annotations provided"
        return result
    
    mcp_logger.info(f"🔧 MCP CALL: lighthouse_batch_annotate(count={len(annotations)})")
    
    if not bridge_client or not session_manager:
        result = "❌ Bridge client or session manager not initialized"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    # Use default session if none provided
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Extract agent_id from session token
    try:
        agent_id = session_token.split(':')[0] if session_token else "unknown"
    except:
        agent_id = "unknown"
    
    # Validate batch access
    if not await _validate_agent_access(session_token, agent_id, "annotation", "batch_operation"):
        result = "❌ Access denied: Invalid session or insufficient permissions for batch annotations"
        mcp_logger.info(f"📤 MCP RESPONSE: {result}")
        return result
    
    try:
        # Create correlation context for batch operation
        correlation_id = causality_tracker.create_correlation_context("batch_annotation", agent_id)
        
        successful_annotations = []
        failed_annotations = []
        
        for i, annotation in enumerate(annotations):
            try:
                # Validate individual annotation
                required_fields = ["file_path", "line", "message"]
                if not all(field in annotation for field in required_fields):
                    failed_annotations.append({
                        "index": i,
                        "error": f"Missing required fields: {required_fields}",
                        "annotation": annotation
                    })
                    continue
                
                annotation_data = {
                    "file_path": annotation["file_path"],
                    "line_number": annotation["line"],
                    "message": annotation["message"],
                    "category": annotation.get("category", "general"),
                    "annotated_by": agent_id,
                    "timestamp": time.time(),
                    "batch_id": str(correlation_id)
                }
                
                # Store annotation event
                event = await bridge_client.store_event_secure(
                    event_type="shadow_annotation",
                    aggregate_id=f"file_{annotation['file_path'].replace('/', '_')}",
                    data=annotation_data,
                    metadata={"session_token": session_token, "batch_id": str(correlation_id)},
                    session_token=session_token
                )
                
                successful_annotations.append({
                    "index": i,
                    "event_id": str(event.event_id),
                    "file_path": annotation["file_path"],
                    "line": annotation["line"]
                })
                
                # Add to causality chain
                causality_tracker.add_causal_event(str(correlation_id), "annotation_created", {
                    "event_id": str(event.event_id),
                    "file_path": annotation["file_path"],
                    "line": annotation["line"]
                })
                
            except Exception as e:
                failed_annotations.append({
                    "index": i,
                    "error": str(e),
                    "annotation": annotation
                })
        
        # Generate summary
        success_count = len(successful_annotations)
        failure_count = len(failed_annotations)
        
        result_lines = [
            f"🔄 Batch annotation completed",
            f"Batch ID: {correlation_id}",
            f"Successful: {success_count}",
            f"Failed: {failure_count}",
            f"Total: {len(annotations)}"
        ]
        
        if successful_annotations:
            result_lines.append("\n✅ Successful annotations:")
            for annotation in successful_annotations[:5]:  # Show first 5
                result_lines.append(f"  • {annotation['file_path']}:{annotation['line']} (ID: {annotation['event_id']})")
            if len(successful_annotations) > 5:
                result_lines.append(f"  ... and {len(successful_annotations) - 5} more")
        
        if failed_annotations:
            result_lines.append("\n❌ Failed annotations:")
            for annotation in failed_annotations[:3]:  # Show first 3 failures
                result_lines.append(f"  • Index {annotation['index']}: {annotation['error']}")
            if len(failed_annotations) > 3:
                result_lines.append(f"  ... and {len(failed_annotations) - 3} more failures")
        
        result = "\n".join(result_lines)
        
        mcp_logger.info(f"📤 MCP RESPONSE: Batch annotation completed: {success_count} success, {failure_count} failed")
        return result
        
    except Exception as e:
        result = f"❌ Batch annotation failed: {str(e)}"
        mcp_logger.error(f"📤 MCP RESPONSE: {result}")
        return result

# =============================================================================
# Tool Schema Definitions
# =============================================================================

# Schema definitions for MCP tools
TOOL_SCHEMAS = {
    "lighthouse_create_session": {
        "agent_id": {
            "type": "string",
            "description": "Unique identifier for the agent"
        },
        "metadata": {
            "type": "object",
            "description": "Optional metadata for session creation",
            "properties": {
                "ip_address": {"type": "string"},
                "user_agent": {"type": "string"}
            }
        }
    },
    "lighthouse_get_health": {
        "session_token": {
            "type": "string",
            "description": "Session token for authentication",
            "default": ""
        }
    },
    "lighthouse_store_event_secure": {
        "event_type": {
            "type": "string",
            "description": "Type of event to store"
        },
        "aggregate_id": {
            "type": "string", 
            "description": "Aggregate identifier for the event"
        },
        "data": {
            "type": "object",
            "description": "Event data payload"
        },
        "session_token": {
            "type": "string",
            "description": "Session token for authentication"
        },
        "metadata": {
            "type": "object",
            "description": "Optional event metadata"
        }
    },
    "lighthouse_query_events": {
        "event_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Event types to filter by"
        },
        "aggregate_ids": {
            "type": "array", 
            "items": {"type": "string"},
            "description": "Aggregate IDs to filter by"
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of events to return",
            "default": 100
        },
        "session_token": {
            "type": "string",
            "description": "Session token for authentication",
            "default": ""
        }
    },
    "lighthouse_pair_request": {
        "requester": {
            "type": "string",
            "description": "Agent requesting pair programming"
        },
        "task": {
            "type": "string",
            "description": "Task description for pair programming"
        },
        "mode": {
            "type": "string",
            "enum": ["collaborative", "review", "mentoring"],
            "description": "Pair programming mode",
            "default": "collaborative"
        },
        "session_token": {
            "type": "string",
            "description": "Session token for authentication",
            "default": ""
        }
    },
    "lighthouse_shadow_annotate": {
        "file_path": {
            "type": "string",
            "description": "Path to the file being annotated"
        },
        "line": {
            "type": "integer",
            "description": "Line number for the annotation",
            "minimum": 1
        },
        "message": {
            "type": "string",
            "description": "Annotation message"
        },
        "category": {
            "type": "string",
            "enum": ["general", "bug", "optimization", "security", "documentation", "review"],
            "description": "Annotation category",
            "default": "general"
        },
        "session_token": {
            "type": "string",
            "description": "Session token for authentication", 
            "default": ""
        }
    }
}

def _validate_function_parameters(function_name: str, params: Dict[str, Any]) -> Optional[str]:
    """Validate function parameters against schema"""
    
    schema = TOOL_SCHEMAS.get(function_name)
    if not schema:
        return None  # No validation for unknown commands
    
    try:
        from jsonschema import validate, ValidationError, Draft7Validator
        validate(instance=params, schema={"type": "object", "properties": schema}, cls=Draft7Validator)
        return None  # No error
    except ValidationError as e:
        return f"Parameter validation failed: {e.message} at {'.'.join(str(p) for p in e.absolute_path)}"
    except Exception as e:
        return f"Schema validation error: {str(e)}"


# Access Control Utilities

async def _validate_agent_access(session_token: str, agent_id: str, resource_type: str, resource_id: str = "") -> bool:
    """Validate agent access to resources with cross-agent security controls"""
    
    if not session_manager or not bridge:
        return False
    
    # Extract requesting agent from session token
    try:
        requesting_agent = session_token.split(':')[0] if session_token else "unknown"
    except:
        requesting_agent = "unknown"
    
    # Basic validation - agent can only use their own session
    if requesting_agent != agent_id and requesting_agent != "unknown":
        mcp_logger.warning(f"🔒 Cross-agent access attempt: {requesting_agent} trying to use {agent_id}'s session")
        
        # Log security event
        security_monitor.log_security_event(
            "cross_agent_access",
            requesting_agent,
            {"attempted_agent": agent_id, "resource_type": resource_type, "resource_id": resource_id}
        )
        return False
    
    # Validate session is active and secure
    session = await session_manager.validate_session(session_token, agent_id)
    if not session:
        mcp_logger.warning(f"🔒 Invalid session for {agent_id} accessing {resource_type}")
        return False
    
    # CRITICAL FIX: Ensure agent is authenticated with EventStore 
    # This handles the case where session exists but EventStore auth expired/missing
    if bridge and bridge.event_store:
        try:
            # Check if agent is already authenticated with EventStore
            authenticated_identity = bridge.event_store.authenticator.get_authenticated_agent(agent_id)
            
            if not authenticated_identity:
                mcp_logger.info(f"🔧 Auto-authenticating {agent_id} with EventStore (session exists but EventStore auth missing)")
                
                # Create and authenticate with EventStore
                auth_token = bridge.event_store.create_agent_token(agent_id)
                identity = bridge.event_store.authenticate_agent(agent_id, auth_token, "agent")
                
                mcp_logger.info(f"✅ Auto-authentication successful for agent {agent_id}")
                
        except Exception as e:
            mcp_logger.error(f"❌ Auto-authentication failed for agent {agent_id}: {e}")
            return False
    
    # Resource-specific access controls
    if resource_type == "shadow_search":
        # Allow search but log for audit
        mcp_logger.info(f"🔍 Agent {agent_id} performing shadow search")
        return True
        
    elif resource_type == "pair_programming":
        # Ensure agent is authenticated for pair programming
        mcp_logger.info(f"🤝 Agent {agent_id} accessing pair programming")
        return True
        
    elif resource_type == "annotation":
        # Validate file path access for annotations
        if resource_id and resource_id.startswith("/"):
            # Absolute path - check if it's in allowed directories
            allowed_base_paths = ["/home", "/tmp", "/workspace", "/project"]
            if not any(resource_id.startswith(base) for base in allowed_base_paths):
                mcp_logger.warning(f"🔒 Annotation access denied: {agent_id} trying to annotate {resource_id}")
                return False
        
        mcp_logger.info(f"📝 Agent {agent_id} annotating {resource_id}")
        return True
        
    elif resource_type == "snapshot":
        # Allow snapshot creation but log for audit
        mcp_logger.info(f"📸 Agent {agent_id} creating snapshot {resource_id}")
        return True
    
    # Default: allow access but log
    mcp_logger.info(f"✅ Agent {agent_id} accessing {resource_type}:{resource_id}")
    return True

async def _validate_pair_programming_request(requester: str, session_token: str) -> bool:
    """Validate pair programming request with enhanced security"""
    
    # Basic agent access validation
    if not await _validate_agent_access(session_token, requester, "pair_programming"):
        return False
    
    # Additional pair programming specific validations
    try:
        requesting_agent = session_token.split(':')[0] if session_token else "unknown"
    except:
        requesting_agent = "unknown"
    
    # Ensure requester matches session token
    if requesting_agent != requester and requesting_agent != "unknown":
        mcp_logger.warning(f"🔒 Pair programming request mismatch: {requesting_agent} requesting for {requester}")
        return False
    
    return True

async def _attempt_partner_matching(requester: str, task: str, mode: str, session_token: str, 
                                  event_id: str, correlation_id: Optional[str] = None) -> str:
    """Attempt to match pair programming partners"""
    
    try:
        # Basic partner matching logic (placeholder for more sophisticated matching)
        available_experts = ["system-architect", "security-architect", "algorithm-specialist"]
        
        # Filter out the requester from potential partners
        potential_partners = [expert for expert in available_experts if expert != requester]
        
        if not potential_partners:
            return "⚠️  No available partners found for pair programming at this time."
        
        # Simple task-based matching
        if "security" in task.lower():
            suggested_partner = "security-architect"
        elif "algorithm" in task.lower() or "performance" in task.lower():
            suggested_partner = "algorithm-specialist"
        else:
            suggested_partner = "system-architect"
        
        # Ensure suggested partner is available
        if suggested_partner not in potential_partners:
            suggested_partner = potential_partners[0]
        
        # Create partner suggestion event
        suggestion_data = {
            "original_request_id": event_id,
            "suggested_partner": suggested_partner,
            "matching_reason": "task_based_matching",
            "confidence": 0.8
        }
        
        await bridge_client.store_event_secure(
            event_type="partner_suggestion",
            aggregate_id=f"pair_session_{requester}_{correlation_id or 'unknown'}",
            data=suggestion_data,
            metadata={"session_token": session_token, "correlation_id": str(correlation_id) if correlation_id else None},
            session_token=session_token
        )
        
        # Extract agent_id from session token for authentication  
        agent_id = session_token.split(':')[0] if session_token else requester
        
        return f"💡 Suggested partner: {suggested_partner} (confidence: 80%)\nReason: Task-based matching for '{task}'"
        
    except Exception as e:
        mcp_logger.error(f"Partner matching failed: {e}")
        return "⚠️  Partner matching temporarily unavailable."

async def _get_default_session_token() -> str:
    """Get default session token for system operations"""
    
    # Try to find existing system session
    for session in session_manager.active_sessions.values():
        if session.agent_id == "system":
            return session.session_token
    
    # Create system session if none exists
    system_session = await session_manager.create_session("system", "127.0.0.1", "lighthouse_system")
    return system_session.session_token


async def _ensure_agent_authentication_sync(session_token: str, agent_id: str) -> bool:
    """Ensure agent authentication is synchronized between session and EventStore"""
    
    if not bridge or not bridge.event_store or not session_manager:
        return False
    
    try:
        # 1. Verify session exists
        session = await session_manager.validate_session(session_token, agent_id)
        if not session:
            mcp_logger.warning(f"❌ Session validation failed for {agent_id}")
            return False
        
        # 2. Check EventStore authentication
        authenticated_identity = bridge.event_store.authenticator.get_authenticated_agent(agent_id)
        
        if not authenticated_identity or authenticated_identity.is_expired():
            mcp_logger.info(f"🔄 Syncing EventStore authentication for {agent_id}")
            
            # Create and authenticate with EventStore
            auth_token = bridge.event_store.create_agent_token(agent_id)
            identity = bridge.event_store.authenticate_agent(agent_id, auth_token, "agent")
            
            mcp_logger.info(f"✅ Authentication synced for {agent_id}")
        
        return True
        
    except Exception as e:
        mcp_logger.error(f"❌ Authentication sync failed for {agent_id}: {e}")
        return False

# =============================================================================
# MCP Server Setup
# =============================================================================

async def _get_session_with_retry(session_token: str = "") -> Optional[SessionInfo]:
    """Get session with automatic retry and session creation"""
    
    if not session_token:
        session_token = await _get_default_session_token()
    
    # Extract agent_id from token
    try:
        agent_id = session_token.split(':')[0] if session_token else "system"
    except:
        agent_id = "system"
    
    session = await session_manager.validate_session(session_token, agent_id)
    
    if session:
        return session
    
    # If session validation failed, create a new session for the agent
    try:
        new_session = await session_manager.create_session(agent_id, "127.0.0.1", "mcp_server_retry")
        return new_session
    except Exception as e:
        mcp_logger.error(f"Failed to create retry session for {agent_id}: {e}")
        return None

def _get_session_dict_from_session_info(session: SessionInfo) -> Dict[str, Any]:
    """Convert SessionInfo to dictionary for JSON serialization"""
    return {
        'session_id': session.session_id,
        'agent_id': session.agent_id,
        'session_token': session.session_token,
        'created_at': session.created_at,
        'last_activity': session.last_activity,
        'ip_address': session.ip_address,
        'user_agent': session.user_agent,
        'command_count': session.command_count,
        'state': session.state.value
    }

def _get_session_info_from_dict(session_dict: Dict[str, Any]) -> SessionInfo:
    """Convert dictionary to SessionInfo"""
    return SessionInfo(
        session_id=session_dict['session_id'],
        agent_id=session_dict['agent_id'],
        session_token=session_dict['session_token'],
        created_at=session_dict['created_at'],
        last_activity=session_dict['last_activity'],
        ip_address=session_dict.get('ip_address', ''),
        user_agent=session_dict.get('user_agent', ''),
        command_count=session_dict.get('command_count', 0),
        state=SessionState(session_dict.get('state', 'active'))
    )

async def setup_bridge_infrastructure() -> bool:
    """Setup Bridge infrastructure with error handling"""
    
    global bridge, session_manager, bridge_client, security_monitor, rate_limiter, causality_tracker
    
    try:
        mcp_logger.info("🌉 Initializing Bridge infrastructure...")
        
        # Initialize Bridge with MCP-specific configuration
        bridge = MinimalLighthouseBridge(
            project_id="lighthouse_mcp",
            config={
                "data_dir": "/tmp/lighthouse_mcp_data",
                "session_timeout": 3600,  # 1 hour
                "max_concurrent_sessions": 100,
                "memory_cache_size": 10000,
                "expert_timeout": 30.0,
                "auth_secret": "lighthouse_mcp_secret_2024"
            }
        )
        
        # Initialize Bridge
        bridge_initialized = await bridge.initialize()
        if not bridge_initialized:
            mcp_logger.error("❌ Failed to initialize Bridge")
            return False
        
        # Initialize session manager
        session_manager = MCPSessionManager(bridge)
        
        # Initialize bridge client
        bridge_client = MCPBridgeClient(bridge)
        
        # Initialize security monitor
        security_monitor = SecurityMonitor()
        
        # Initialize rate limiter
        rate_limiter = RateLimiter()
        
        # Initialize causality tracker
        causality_tracker = CausalityTracker()
        
        # Create default system session for internal operations
        system_session = await session_manager.create_session("system", "127.0.0.1", "lighthouse_mcp_system")
        
        mcp_logger.info("✅ Bridge infrastructure initialized successfully")
        
        # Test basic functionality
        mcp_logger.info("🧪 Running infrastructure validation tests...")
        
        # Test session creation and validation
        test_session = await session_manager.create_session("test_agent", "127.0.0.1", "test")
        validated = await session_manager.validate_session(
            test_session.session_token, 
            test_session.agent_id
        )
        
        if validated:
            mcp_logger.info("✅ Session management test passed")
            await session_manager.end_session(test_session.session_id)
        else:
            mcp_logger.warning("⚠️  Session management test failed")
        
        return True
        
    except Exception as e:
        mcp_logger.error(f"❌ Bridge infrastructure setup failed: {e}")
        return False

# Tool definitions for MCP

tools: List[Tool] = [
    Tool(
        name="lighthouse_create_session",
        description="Create secure session for agent operations",
        inputSchema={
            "type": "object",
            "properties": TOOL_SCHEMAS["lighthouse_create_session"],
            "required": ["agent_id"]
        }
    ),
    Tool(
        name="lighthouse_get_health", 
        description="Get comprehensive system health status",
        inputSchema={
            "type": "object",
            "properties": TOOL_SCHEMAS["lighthouse_get_health"]
        }
    ),
    Tool(
        name="lighthouse_store_event_secure",
        description="Store event securely through Bridge validation", 
        inputSchema={
            "type": "object",
            "properties": TOOL_SCHEMAS["lighthouse_store_event_secure"],
            "required": ["event_type", "aggregate_id", "data", "session_token"]
        }
    ),
    Tool(
        name="lighthouse_query_events",
        description="Query events with security validation",
        inputSchema={
            "type": "object", 
            "properties": TOOL_SCHEMAS["lighthouse_query_events"]
        }
    ),
    Tool(
        name="lighthouse_get_coordination_stats",
        description="Get multi-agent coordination statistics",
        inputSchema={
            "type": "object",
            "properties": {
                "session_token": {
                    "type": "string",
                    "description": "Session token for authentication",
                    "default": ""
                }
            }
        }
    ),
    Tool(
        name="lighthouse_get_memory_stats", 
        description="Get system memory and performance statistics",
        inputSchema={
            "type": "object",
            "properties": {
                "session_token": {
                    "type": "string",
                    "description": "Session token for authentication",
                    "default": ""
                }
            }
        }
    ),
    Tool(
        name="lighthouse_get_production_health",
        description="Get comprehensive production health check",
        inputSchema={
            "type": "object",
            "properties": {
                "session_token": {
                    "type": "string", 
                    "description": "Session token for authentication",
                    "default": ""
                }
            }
        }
    ),
    Tool(
        name="lighthouse_validate_session",
        description="Validate a session token",
        inputSchema={
            "type": "object",
            "properties": {
                "session_token": {
                    "type": "string",
                    "description": "Session token to validate"
                },
                "agent_id": {
                    "type": "string", 
                    "description": "Agent ID for validation"
                }
            },
            "required": ["session_token", "agent_id"]
        }
    ),
    Tool(
        name="lighthouse_pair_request",
        description="Request pair programming session",
        inputSchema={
            "type": "object",
            "properties": TOOL_SCHEMAS["lighthouse_pair_request"], 
            "required": ["requester", "task"]
        }
    ),
    Tool(
        name="lighthouse_pair_suggest",
        description="Make suggestion in pair programming session", 
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Pair programming session ID"
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent making the suggestion"
                },
                "suggestion": {
                    "type": "string",
                    "description": "The suggestion text"
                },
                "file_path": {
                    "type": "string",
                    "description": "File path for the suggestion",
                    "default": ""
                },
                "line": {
                    "type": "integer",
                    "description": "Line number for the suggestion",
                    "default": 0
                },
                "session_token": {
                    "type": "string",
                    "description": "Session token for authentication",
                    "default": ""
                }
            },
            "required": ["session_id", "agent_id", "suggestion"]
        }
    ),
    Tool(
        name="lighthouse_create_snapshot",
        description="Create system snapshot for debugging/rollback",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string", 
                    "description": "Snapshot name"
                },
                "description": {
                    "type": "string",
                    "description": "Snapshot description",
                    "default": ""
                },
                "session_token": {
                    "type": "string",
                    "description": "Session token for authentication",
                    "default": ""
                }
            },
            "required": ["name"]
        }
    ),
    Tool(
        name="lighthouse_shadow_search",
        description="Search across system events and annotations",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Search pattern"
                },
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File types to filter by"
                },
                "session_token": {
                    "type": "string",
                    "description": "Session token for authentication", 
                    "default": ""
                }
            },
            "required": ["pattern"]
        }
    ),
    Tool(
        name="lighthouse_shadow_annotate",
        description="Create shadow annotation for code analysis",
        inputSchema={
            "type": "object",
            "properties": TOOL_SCHEMAS["lighthouse_shadow_annotate"],
            "required": ["file_path", "line", "message"]
        }
    ),
    Tool(
        name="lighthouse_batch_annotate", 
        description="Create multiple shadow annotations in a batch",
        inputSchema={
            "type": "object",
            "properties": {
                "annotations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "line": {"type": "integer", "minimum": 1},
                            "message": {"type": "string"},
                            "category": {
                                "type": "string",
                                "enum": ["general", "bug", "optimization", "security", "documentation", "review"],
                                "default": "general"
                            }
                        },
                        "required": ["file_path", "line", "message"]
                    },
                    "description": "Array of annotations to create"
                },
                "session_token": {
                    "type": "string",
                    "description": "Session token for authentication",
                    "default": ""
                }
            },
            "required": ["annotations"]
        }
    )
]

# =============================================================================
# HTTP Bridge Server (for external integration)
# =============================================================================

class BridgeHTTPHandler:
    """HTTP handler for Bridge operations"""
    
    def __init__(self, bridge: MinimalLighthouseBridge, session_manager: MCPSessionManager):
        self.bridge = bridge
        self.session_manager = session_manager
    
    def _send_response(self, wfile, status_code: int, content: str, content_type: str = "application/json"):
        """Send HTTP response"""
        response = content.encode('utf-8')
        wfile.write(f"HTTP/1.1 {status_code} OK\r\n".encode())
        wfile.write(f"Content-Type: {content_type}\r\n".encode())
        wfile.write(f"Content-Length: {len(response)}\r\n".encode())
        wfile.write(b"\r\n")
        wfile.write(response)
    
    def _send_error(self, wfile, message: str, status_code: int = 400):
        """Send error response"""
        error_response = json.dumps({"error": message})
        self._send_response(wfile, status_code, error_response)
    
    async def handle_request(self, path: str, method: str, data: bytes, wfile):
        """Handle HTTP request"""
        
        try:
            if method == "GET" and path == "/status":
                # Bridge status check
                status = {
                    "bridge_running": self.bridge.is_running if self.bridge else False,
                    "active_sessions": len(self.session_manager.active_sessions) if self.session_manager else 0,
                    "uptime": time.time() - self.bridge.start_time.timestamp() if self.bridge and self.bridge.start_time else 0
                }
                self._send_response(wfile, 200, json.dumps(status))
                return
            
            elif method == "POST" and path == "/create_session":
                # Session creation
                request_data = json.loads(data.decode('utf-8'))
                agent_id = request_data.get('agent_id')
                
                if not agent_id:
                    self._send_error(wfile, "agent_id required")
                    return
                
                session = await self.session_manager.create_session(agent_id)
                session_dict = _get_session_dict_from_session_info(session)
                
                self._send_response(wfile, 200, json.dumps(session_dict))
                return
            
            elif method == "POST" and path == "/validate_session":
                # Session validation
                request_data = json.loads(data.decode('utf-8'))
                session_token = request_data.get('session_token')
                agent_id = request_data.get('agent_id')
                
                if not session_token or not agent_id:
                    self._send_error(wfile, "session_token and agent_id required")
                    return
                
                session = await self.session_manager.validate_session(session_token, agent_id)
                
                if session:
                    session_dict = _get_session_dict_from_session_info(session)
                    self._send_response(wfile, 200, json.dumps({"valid": True, "session": session_dict}))
                else:
                    self._send_response(wfile, 200, json.dumps({"valid": False}))
                return
            
            elif method == "POST" and path == "/health":
                # Health check
                request_data = json.loads(data.decode('utf-8'))
                session_token = request_data.get('session_token', '')
                result = await lighthouse_get_health(session_token)
                self._send_response(wfile, 200, json.dumps({"result": result}), "application/json")
                return
            
            elif method == "POST" and path == "/store_event":
                # Store event
                request_data = json.loads(data.decode('utf-8'))
                event_type = request_data.get('event_type')
                aggregate_id = request_data.get('aggregate_id')
                data = request_data.get('data')
                session_token = request_data.get('session_token')
                metadata = request_data.get('metadata')
                
                if not all([event_type, aggregate_id, session_token]):
                    self._send_error(wfile, "Missing required fields: event_type, aggregate_id, session_token", 400)
                    return
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_store_event_secure(event_type, aggregate_id, data, session_token, metadata)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to store event: {str(e)}", 500)
                return
            
            elif method == "POST" and path == "/query_events":
                # Query events
                request_data = json.loads(data.decode('utf-8'))
                event_types = request_data.get('event_types', [])
                aggregate_ids = request_data.get('aggregate_ids', [])
                limit = request_data.get('limit', 100)
                session_token = request_data.get('session_token', '')
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_query_events(event_types, aggregate_ids, limit, session_token)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to query events: {str(e)}", 500)
                return
            
            elif method == "POST" and path == "/pair_request":
                # Pair programming request
                request_data = json.loads(data.decode('utf-8'))
                requester = request_data.get('requester')
                task = request_data.get('task')
                mode = request_data.get('mode', 'collaborative')
                session_token = request_data.get('session_token', '')
                
                if not requester or not task:
                    self._send_error(wfile, "requester and task are required", 400)
                    return
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_pair_request(requester, task, mode, session_token)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to create pair request: {str(e)}", 500)
                return
            
            elif method == "POST" and path == "/pair_suggest":
                # Pair programming suggestion
                request_data = json.loads(data.decode('utf-8'))
                session_id = request_data.get('session_id')
                agent_id = request_data.get('agent_id')
                suggestion = request_data.get('suggestion')
                file_path = request_data.get('file_path', '')
                line = request_data.get('line', 0)
                session_token = request_data.get('session_token', '')
                
                if not session_id or not agent_id or not suggestion:
                    self._send_error(wfile, "session_id, agent_id, and suggestion are required", 400)
                    return
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_pair_suggest(session_id, agent_id, suggestion, file_path, line, session_token)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to create pair suggestion: {str(e)}", 500)
                return
            
            elif method == "POST" and path == "/create_snapshot":
                # Create snapshot
                request_data = json.loads(data.decode('utf-8'))
                name = request_data.get('name')
                description = request_data.get('description', '')
                session_token = request_data.get('session_token', '')
                
                if not name:
                    self._send_error(wfile, "name is required", 400)
                    return
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_create_snapshot(name, description, session_token)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to create snapshot: {str(e)}", 500)
                return
            
            elif method == "POST" and path == "/shadow_search":
                # Shadow search
                request_data = json.loads(data.decode('utf-8'))
                pattern = request_data.get('pattern')
                file_types = request_data.get('file_types')
                session_token = request_data.get('session_token', '')
                
                if not pattern:
                    self._send_error(wfile, "pattern is required", 400)
                    return
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_shadow_search(pattern, file_types, session_token)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to perform shadow search: {str(e)}", 500)
                return
            
            elif method == "POST" and path == "/shadow_annotate":
                # Shadow annotation
                request_data = json.loads(data.decode('utf-8'))
                file_path = request_data.get('file_path')
                line = request_data.get('line')
                message = request_data.get('message')
                category = request_data.get('category', 'general')
                session_token = request_data.get('session_token', '')
                
                if not file_path or not line or not message:
                    self._send_error(wfile, "file_path, line, and message are required", 400)
                    return
                
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.get_event_loop().run_until_complete(
                            lighthouse_shadow_annotate(file_path, line, message, category, session_token)
                        )
                    )
                    self._send_response(wfile, 200, json.dumps({"result": result}))
                except Exception as e:
                    self._send_error(wfile, f"Failed to create shadow annotation: {str(e)}", 500)
                return
            
            else:
                # Unknown endpoint
                self._send_error(wfile, f"Unknown endpoint: {method} {path}", 404)
                return
                
        except json.JSONDecodeError:
            self._send_error(wfile, "Invalid JSON in request body", 400)
        except Exception as e:
            mcp_logger.error(f"HTTP handler error: {e}")
            self._send_error(wfile, f"Internal server error: {str(e)}", 500)

from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import socketserver

class LighthouseHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Bridge operations"""
    
    def __init__(self, *args, bridge_handler=None, **kwargs):
        self.bridge_handler = bridge_handler
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length) if content_length > 0 else b""
        
        asyncio.create_task(
            self.bridge_handler.handle_request(self.path, "GET", data, self.wfile)
        )
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length)
        
        asyncio.create_task(
            self.bridge_handler.handle_request(self.path, "POST", data, self.wfile)
        )
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        mcp_logger.info(f"HTTP: {format % args}")

def create_http_bridge_server(port: int = 8765) -> Optional[HTTPServer]:
    """Create HTTP server for Bridge operations"""
    
    try:
        if not bridge or not session_manager:
            mcp_logger.error("Bridge or session manager not initialized for HTTP server")
            return None
        
        bridge_handler = BridgeHTTPHandler(bridge, session_manager)
        
        def handler_factory(*args, **kwargs):
            return LighthouseHTTPRequestHandler(*args, bridge_handler=bridge_handler, **kwargs)
        
        server = HTTPServer(('localhost', port), handler_factory)
        mcp_logger.info(f"🌐 HTTP Bridge server created on port {port}")
        
        return server
        
    except Exception as e:
        mcp_logger.error(f"Failed to create HTTP Bridge server: {e}")
        return None

def start_http_bridge_server(port: int = 8765):
    """Start HTTP Bridge server in background thread"""
    
    server = create_http_bridge_server(port)
    if not server:
        return None
    
    def serve_forever():
        """Serve HTTP requests forever"""
        try:
            mcp_logger.info(f"🌐 Starting HTTP Bridge server on port {port}")
            server.serve_forever()
        except KeyboardInterrupt:
            mcp_logger.info("🌐 HTTP Bridge server shutdown requested")
        except Exception as e:
            mcp_logger.error(f"🌐 HTTP Bridge server error: {e}")
        finally:
            server.shutdown()
            server.server_close()
    
    # Start server in background thread
    server_thread = threading.Thread(target=serve_forever, daemon=True)
    server_thread.start()
    
    mcp_logger.info(f"🌐 HTTP Bridge server started on http://localhost:{port}")
    return server

# =============================================================================
# Main Server
# =============================================================================

server = Server("lighthouse")

@server.list_tools()
async def handle_list_tools() -> ListToolsResult:
    """List available MCP tools"""
    return ListToolsResult(tools=tools)

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> CallToolResult:
    """Handle MCP tool calls"""
    
    # Map tool names to functions
    tool_functions = {
        "lighthouse_create_session": lighthouse_create_session,
        "lighthouse_get_health": lighthouse_get_health,
        "lighthouse_store_event_secure": lighthouse_store_event_secure,
        "lighthouse_query_events": lighthouse_query_events,
        "lighthouse_get_coordination_stats": lighthouse_get_coordination_stats,
        "lighthouse_get_memory_stats": lighthouse_get_memory_stats,
        "lighthouse_get_production_health": lighthouse_get_production_health,
        "lighthouse_validate_session": lighthouse_validate_session,
        "lighthouse_pair_request": lighthouse_pair_request,
        "lighthouse_pair_suggest": lighthouse_pair_suggest,
        "lighthouse_create_snapshot": lighthouse_create_snapshot,
        "lighthouse_shadow_search": lighthouse_shadow_search,
        "lighthouse_shadow_annotate": lighthouse_shadow_annotate,
        "lighthouse_batch_annotate": lighthouse_batch_annotate
    }
    
    if name not in tool_functions:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=f"❌ Unknown tool: {name}"
            )]
        )
    
    try:
        # Call the function with arguments
        func = tool_functions[name]
        result = await func(**arguments)
        
        return CallToolResult(
            content=[TextContent(
                type="text", 
                text=result
            )]
        )
        
    except Exception as e:
        error_message = f"❌ Tool '{name}' failed: {str(e)}"
        mcp_logger.error(error_message)
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=error_message
            )]
        )

async def run_server():
    """Run the MCP server with Bridge integration"""
    
    # Setup Bridge infrastructure
    mcp_logger.info("🚀 Starting Lighthouse MCP Server with Bridge Integration")
    
    infrastructure_ready = await setup_bridge_infrastructure()
    if not infrastructure_ready:
        mcp_logger.error("❌ Failed to setup Bridge infrastructure")
        return
    
    # Start HTTP Bridge server
    http_server = start_http_bridge_server(8765)
    if http_server:
        mcp_logger.info("✅ HTTP Bridge server started on port 8765")
    else:
        mcp_logger.warning("⚠️  HTTP Bridge server failed to start")
    
    mcp_logger.info("✅ Lighthouse MCP Server ready")
    mcp_logger.info("📡 Available endpoints:")
    mcp_logger.info("   • MCP Tools: lighthouse_create_session, lighthouse_get_health, etc.")
    mcp_logger.info("   • HTTP Bridge: http://localhost:8765/status, /create_session, /validate_session, etc.")
    
    # Run MCP server
    async with StdioServerSession(server) as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="lighthouse",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None
                )
            )
        )

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        mcp_logger.info("🛑 Lighthouse MCP Server shutdown requested")
    except Exception as e:
        mcp_logger.error(f"💥 Lighthouse MCP Server crashed: {e}")
        sys.exit(1)