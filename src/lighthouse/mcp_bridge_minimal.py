#!/usr/bin/env python3
"""
Minimal Bridge Integration for MCP Server

This provides only the essential Bridge components needed for MCP:
- EventStore for data persistence
- SessionSecurityValidator for security
- SpeedLayerDispatcher for fast validation
- ExpertCoordinator for multi-agent coordination

Excludes FUSE, AST anchoring, and other filesystem-specific components.
"""

import asyncio
import logging
import os
import secrets
from datetime import datetime
from typing import Any, Dict, Optional, Set

from lighthouse.bridge.security.session_security import SessionSecurityValidator
from lighthouse.bridge.speed_layer.optimized_dispatcher import OptimizedSpeedLayerDispatcher
from lighthouse.bridge.expert_coordination.coordinator import ExpertCoordinator
from lighthouse.bridge.event_store.project_aggregate import ProjectAggregate
from lighthouse.event_store import EventStore

logger = logging.getLogger(__name__)


class EventStoreSingleton:
    """Singleton wrapper for EventStore to ensure only one instance exists"""
    _instance: Optional[EventStore] = None
    _initialized = False
    
    @classmethod
    def get_instance(cls, data_dir: str = None, allowed_base_dirs = None, auth_secret: str = None) -> EventStore:
        """Get the singleton EventStore instance"""
        if cls._instance is None:
            if data_dir is None:
                data_dir = "/tmp/lighthouse_eventstore_singleton"
            if allowed_base_dirs is None:
                allowed_base_dirs = [data_dir, "/tmp", "/home"]
            if auth_secret is None:
                auth_secret = secrets.token_urlsafe(32)
            
            cls._instance = EventStore(
                data_dir=data_dir,
                allowed_base_dirs=allowed_base_dirs,
                auth_secret=auth_secret
            )
            logger.info(f"🏗️  Created singleton EventStore instance: {id(cls._instance)}")
        
        return cls._instance


class MinimalLighthouseBridge:
    """
    Minimal Bridge for MCP Integration
    
    Provides essential Bridge functionality without filesystem dependencies:
    - Secure session management
    - Fast command validation  
    - Event sourcing and audit trails
    - Multi-agent coordination
    """
    
    def __init__(self, 
                 project_id: str,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize minimal Bridge"""
        
        self.project_id = project_id
        self.config = config or {}
        
        # Core components only
        self.event_store: Optional[EventStore] = None
        self.project_aggregate: Optional[ProjectAggregate] = None
        self.session_security: Optional[SessionSecurityValidator] = None
        self.speed_layer_dispatcher: Optional[OptimizedSpeedLayerDispatcher] = None
        self.expert_coordinator: Optional[ExpertCoordinator] = None
        
        # State
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.background_tasks: Set[asyncio.Task] = set()
        
        # Performance monitoring
        self.request_count = 0
        self.validation_count = 0
    
    async def initialize(self) -> bool:
        """Initialize Bridge components"""
        
        if self.is_running:
            logger.warning("Bridge is already initialized")
            return True
        
        try:
            logger.info(f"Initializing minimal Bridge for project {self.project_id}")
            
            # Initialize EventStore with persistent storage - SINGLETON PATTERN
            data_dir = self.config.get('data_dir') or f"/tmp/lighthouse_bridge_{self.project_id}"
            os.makedirs(data_dir, exist_ok=True)
            
            # Use singleton EventStore to ensure authentication persistence
            self.event_store = EventStoreSingleton.get_instance(
                data_dir=data_dir,
                allowed_base_dirs=[data_dir, "/tmp", "/home"],
                auth_secret=self.config.get('auth_secret') or secrets.token_urlsafe(32)
            )
            await self.event_store.initialize()
            
            # Initialize ProjectAggregate
            self.project_aggregate = ProjectAggregate(self.project_id)
            
            # Initialize SessionSecurity
            auth_secret = self.config.get('auth_secret') or secrets.token_urlsafe(32)
            self.session_security = SessionSecurityValidator(
                secret_key=auth_secret,
                session_timeout=self.config.get('session_timeout', 3600),
                max_concurrent_sessions=self.config.get('max_concurrent_sessions', 100)
            )
            
            # Initialize SpeedLayer (simplified)
            self.speed_layer_dispatcher = OptimizedSpeedLayerDispatcher(
                max_memory_cache_size=self.config.get('memory_cache_size', 10000),
                expert_timeout=self.config.get('expert_timeout', 30.0)
            )
            await self.speed_layer_dispatcher.start()
            
            # Initialize ExpertCoordinator
            self.expert_coordinator = ExpertCoordinator(self.event_store)
            await self.expert_coordinator.start()
            
            self.is_running = True
            self.start_time = datetime.now()
            
            logger.info("✅ Minimal Bridge initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Bridge initialization failed: {e}")
            return False
    
    async def validate_command(self, 
                             tool_name: str,
                             tool_input: Dict[str, Any],
                             agent_id: str,
                             session_id: Optional[str] = None,
                             session_token: Optional[str] = None) -> Dict[str, Any]:
        """Validate command through minimal Bridge"""
        
        if not self.is_running:
            return {
                "approved": False,
                "reason": "Bridge not running",
                "security_alert": "Bridge offline",
                "request_id": None,
                "response_time": 0.0
            }
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Session validation
            if session_token and self.session_security:
                is_valid = self.session_security.validate_session(session_token, agent_id)
                if not is_valid:
                    return {
                        "approved": False,
                        "reason": "Invalid or hijacked session",
                        "security_alert": "Session validation failed",
                        "request_id": None,
                        "response_time": (asyncio.get_event_loop().time() - start_time) * 1000
                    }
            
            # Simple validation through speed layer
            from lighthouse.bridge.speed_layer.models import ValidationRequest
            
            request = ValidationRequest(
                tool_name=tool_name,
                tool_input=tool_input,
                agent_id=agent_id,
                session_id=session_id
            )
            
            result = await self.speed_layer_dispatcher.validate_request(request)
            self.validation_count += 1
            
            # Log to project aggregate for audit
            if self.project_aggregate:
                await self.project_aggregate.handle_validation_request(
                    request_id=request.request_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    agent_id=agent_id,
                    session_id=session_id
                )
            
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            result_dict = result.to_dict()
            result_dict["response_time"] = response_time
            
            return result_dict
            
        except Exception as e:
            logger.error(f"Command validation error: {e}")
            return {
                "approved": False,
                "reason": f"Validation error: {str(e)}",
                "security_alert": "Validation pipeline error",
                "request_id": None,
                "response_time": (asyncio.get_event_loop().time() - start_time) * 1000
            }
    
    async def stop(self) -> bool:
        """Stop Bridge components"""
        
        if not self.is_running:
            return True
        
        try:
            logger.info("Stopping minimal Bridge")
            
            # Stop background tasks
            for task in self.background_tasks:
                task.cancel()
            
            # Stop components
            if self.expert_coordinator:
                await self.expert_coordinator.stop()
            
            if self.speed_layer_dispatcher:
                await self.speed_layer_dispatcher.stop()
            
            if self.event_store:
                await self.event_store.shutdown()
            
            self.is_running = False
            logger.info("✅ Bridge stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Bridge shutdown error: {e}")
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get Bridge health status"""
        return {
            "bridge_status": "running" if self.is_running else "stopped",
            "project_id": self.project_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "request_count": self.request_count,
            "validation_count": self.validation_count,
            "active_sessions": len(self.session_security.active_sessions) if self.session_security else 0,
            "components": {
                "event_store": self.event_store is not None,
                "session_security": self.session_security is not None,
                "speed_layer": self.speed_layer_dispatcher is not None,
                "expert_coordinator": self.expert_coordinator is not None
            }
        }