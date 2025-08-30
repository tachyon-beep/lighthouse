"""
Lighthouse Bridge - Main Integration

Central coordination hub that integrates all bridge components:
- Speed Layer for fast validation
- Event-Sourced Architecture for audit trails
- FUSE Mount for expert agent interaction
- AST Anchoring for code annotations
- Expert Coordination for complex decisions
- Pair Programming for collaborative sessions

This is the main entry point for the complete HLD Bridge implementation.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from .speed_layer import SpeedLayerDispatcher
from .event_store import ProjectAggregate, EventStream, TimeTravelDebugger

# Optional FUSE support - only import if available
try:
    from .fuse_mount import LighthouseFUSE, FUSEMountManager
    FUSE_AVAILABLE = True
except (ImportError, OSError) as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"FUSE support not available: {e}")
    LighthouseFUSE = None
    FUSEMountManager = None
    FUSE_AVAILABLE = False

from .ast_anchoring import ASTAnchorManager, TreeSitterParser
from .expert_coordination import ExpertAgentInterface, ExpertCoordinator
from .security.session_security import SessionSecurityValidator
from ..event_store import EventStore

logger = logging.getLogger(__name__)


class LighthouseBridge:
    """
    Complete Lighthouse Bridge Implementation
    
    Integrates all bridge components into a unified system providing:
    - <100ms validation for 99% of requests via Speed Layer
    - Complete audit trails via Event Sourcing
    - Expert agent integration via FUSE filesystem
    - Code annotation persistence via AST Anchoring
    - Real-time collaboration via Pair Programming Hub
    """
    
    def __init__(self,
                 project_id: str,
                 mount_point: str = "/mnt/lighthouse/project",
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize Lighthouse Bridge
        
        Args:
            project_id: Unique project identifier
            mount_point: FUSE filesystem mount point
            config: Optional configuration overrides
        """
        
        self.project_id = project_id
        self.mount_point = mount_point
        self.config = config or {}
        
        # Component initialization
        self.event_store = EventStore()
        self.project_aggregate = ProjectAggregate(project_id)
        self.event_stream = EventStream(fuse_mount_path=f"{mount_point}/streams")
        self.time_travel_debugger = TimeTravelDebugger(self.event_store)
        self.tree_sitter_parser = TreeSitterParser()
        self.ast_anchor_manager = ASTAnchorManager(self.tree_sitter_parser)
        
        # Speed layer components
        self.speed_layer_dispatcher = SpeedLayerDispatcher(
            max_memory_cache_size=self.config.get('memory_cache_size', 10000),
            policy_config_path=self.config.get('policy_config_path'),
            ml_model_path=self.config.get('ml_model_path'),
            expert_timeout=self.config.get('expert_timeout', 30.0)
        )
        
        # FUSE filesystem (only if available)
        if FUSE_AVAILABLE and LighthouseFUSE:
            self.lighthouse_fuse = LighthouseFUSE(
                project_aggregate=self.project_aggregate,
                time_travel_debugger=self.time_travel_debugger,
                event_stream=self.event_stream,
                ast_anchor_manager=self.ast_anchor_manager,
                auth_secret=self.config.get('auth_secret', 'test_secret_key'),
                mount_point=mount_point
            )
        else:
            self.lighthouse_fuse = None
            logger.info("FUSE filesystem disabled - libfuse not available")
        
        # Only create FUSE mount manager if available
        if FUSE_AVAILABLE:
            self.fuse_mount_manager = FUSEMountManager(
                event_store=self.event_store,
                project_aggregate=self.project_aggregate,
                ast_anchor_manager=self.ast_anchor_manager,
                event_stream_manager=self.event_stream,
                mount_point=mount_point,
                foreground=self.config.get('fuse_foreground', False),
                allow_other=self.config.get('fuse_allow_other', True)
            )
        else:
            self.fuse_mount_manager = None
            logger.info("FUSE mount manager disabled - libfuse not available")
        
        # Expert coordination
        self.expert_coordinator = ExpertCoordinator(self.event_store)
        
        # Session security
        auth_secret = self.config.get('auth_secret', 'test_secret_key')
        self.session_security = SessionSecurityValidator(
            secret_key=auth_secret,
            session_timeout=self.config.get('session_timeout', 3600),
            max_concurrent_sessions=self.config.get('max_concurrent_sessions', 3)
        )
        
        # Integration state
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.background_tasks: Set[asyncio.Task] = set()
        
        # Performance monitoring
        self.request_count = 0
        self.validation_count = 0
        self.expert_escalations = 0
        
        # Wire up integrations
        self._setup_integrations()
    
    def _setup_integrations(self):
        """Set up integrations between components"""
        
        # Connect project aggregate to validation bridge
        self.project_aggregate.set_validation_bridge(self.speed_layer_dispatcher)
        
        # Connect speed layer to expert coordination
        # This would involve more complex integration in a full implementation
        
        logger.info("Bridge component integrations configured")
    
    async def start(self) -> bool:
        """
        Start the Lighthouse Bridge system
        
        Returns:
            True if startup successful, False otherwise
        """
        
        if self.is_running:
            logger.warning("Bridge is already running")
            return True
        
        try:
            logger.info(f"Starting Lighthouse Bridge for project {self.project_id}")
            
            # Initialize event store first - it needs to open its log files
            logger.info("Initializing event store")
            await self.event_store.initialize()
            
            # Start core components in order
            await self._start_event_stream()
            await self._start_speed_layer()
            await self._start_fuse_filesystem()
            await self._start_expert_coordination()
            await self._start_background_tasks()
            
            self.is_running = True
            self.start_time = datetime.utcnow()
            
            logger.info("Lighthouse Bridge started successfully")
            
            # Start health monitoring
            self._start_health_monitoring()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Lighthouse Bridge: {e}")
            await self.stop()  # Cleanup on failure
            return False
    
    async def stop(self):
        """Stop the Lighthouse Bridge system"""
        
        if not self.is_running:
            return
        
        logger.info("Stopping Lighthouse Bridge")
        
        try:
            # Stop background tasks
            for task in self.background_tasks:
                task.cancel()
            
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            self.background_tasks.clear()
            
            # Stop components in reverse order
            await self._stop_expert_coordination()
            await self._stop_fuse_filesystem()
            await self._stop_speed_layer()
            await self._stop_event_stream()
            
            self.is_running = False
            self.start_time = None
            
            logger.info("Lighthouse Bridge stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Lighthouse Bridge: {e}")
    
    async def _start_event_stream(self):
        """Start event streaming system"""
        logger.info("Starting event stream")
        await self.event_stream.start()
        
        # Subscribe to project events for real-time updates
        try:
            from ..event_store.event_models import EventFilter
            project_filter = EventFilter(aggregate_ids=[self.project_id])
        except ImportError:
            # Handle missing module gracefully for now
            project_filter = None
        
        if project_filter:
            self.event_stream.subscribe(
                subscriber_id="bridge_main",
                event_filter=project_filter,
                callback=self._handle_project_event
            )
    
    async def _start_speed_layer(self):
        """Start speed layer validation system"""
        logger.info("Starting speed layer dispatcher")
        await self.speed_layer_dispatcher.start()
    
    async def _start_fuse_filesystem(self):
        """Start FUSE filesystem"""
        logger.info("Starting FUSE filesystem")
        
        if self.fuse_mount_manager:
            success = await self.fuse_mount_manager.mount()
            if not success:
                raise RuntimeError("Failed to mount FUSE filesystem")
    
    async def _start_expert_coordination(self):
        """Start expert coordination system"""
        logger.info("Starting expert coordination")
        await self.expert_coordinator.start()
    
    async def _start_background_tasks(self):
        """Start background maintenance tasks"""
        logger.info("Starting background tasks")
        
        # Performance monitoring task
        monitor_task = asyncio.create_task(self._performance_monitoring())
        self.background_tasks.add(monitor_task)
        
        # Cleanup task  
        cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self.background_tasks.add(cleanup_task)
    
    async def _stop_event_stream(self):
        """Stop event streaming system"""
        await self.event_stream.stop()
    
    async def _stop_speed_layer(self):
        """Stop speed layer system"""
        await self.speed_layer_dispatcher.stop()
    
    async def _stop_fuse_filesystem(self):
        """Stop FUSE filesystem"""
        if self.fuse_mount_manager:
            await self.fuse_mount_manager.unmount()
    
    async def _stop_expert_coordination(self):
        """Stop expert coordination system"""
        await self.expert_coordinator.stop()
    
    def _handle_project_event(self, event):
        """Handle project events for real-time updates"""
        try:
            # Update AST anchors when files are modified
            if event.is_file_operation():
                file_path = event.get_file_path()
                if file_path and event.event_type in ['FILE_MODIFIED', 'FILE_CREATED']:
                    # Trigger AST anchor update (would be async in real implementation)
                    self._update_ast_anchors_for_file(file_path, event.data.get('content', ''))
            
            # Forward validation events to expert coordination
            if event.is_validation_operation():
                self._handle_validation_event(event)
            
        except Exception as e:
            logger.error(f"Error handling project event {event.event_id}: {e}")
    
    def _update_ast_anchors_for_file(self, file_path: str, content: str):
        """Update AST anchors for a modified file"""
        try:
            # Remove old anchors
            self.ast_anchor_manager.remove_anchors_for_file(file_path)
            
            # Create new anchors
            if content.strip():  # Only if file has content
                self.ast_anchor_manager.create_anchors(file_path, content)
                
            logger.debug(f"Updated AST anchors for {file_path}")
            
        except Exception as e:
            logger.warning(f"Failed to update AST anchors for {file_path}: {e}")
    
    def _handle_validation_event(self, event):
        """Handle validation-related events"""
        if event.event_type == 'VALIDATION_REQUEST_SUBMITTED':
            self.validation_count += 1
        elif event.event_type == 'VALIDATION_ESCALATED_TO_EXPERT':
            self.expert_escalations += 1
    
    def _start_health_monitoring(self):
        """Start system health monitoring"""
        health_task = asyncio.create_task(self._health_monitoring_loop())
        self.background_tasks.add(health_task)
    
    async def _health_monitoring_loop(self):
        """Background health monitoring"""
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _perform_health_check(self):
        """Perform system health check"""
        try:
            # Check component health
            components_status = {
                'speed_layer': self.speed_layer_dispatcher.get_performance_metrics(),
                'fuse_mount': self.fuse_mount_manager.get_status() if self.fuse_mount_manager else {'status': 'disabled'},
                'event_stream': self.event_stream.get_stream_stats(),
                'ast_anchors': self.ast_anchor_manager.get_statistics()
            }
            
            # Log any issues
            for component, status in components_status.items():
                if isinstance(status, dict) and not status.get('healthy', True):
                    logger.warning(f"Component {component} health issue: {status}")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
    
    async def _performance_monitoring(self):
        """Background performance monitoring"""
        while self.is_running:
            try:
                # Update performance metrics
                self.request_count += 1
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Performance monitoring error: {e}")
                await asyncio.sleep(30)
    
    async def _periodic_cleanup(self):
        """Background cleanup tasks"""
        while self.is_running:
            try:
                # Cleanup expired cache entries
                # Compact event logs
                # Remove old temporary files
                
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
                await asyncio.sleep(300)
    
    # Public API methods
    
    async def validate_command(self, 
                             tool_name: str,
                             tool_input: Dict[str, Any],
                             agent_id: str,
                             session_id: Optional[str] = None,
                             session_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate a command through the bridge system
        
        This is the main entry point for command validation.
        """
        
        # Session security validation first
        if session_token:
            if not self.session_security.validate_session(session_token, agent_id):
                return {
                    "approved": False,
                    "reason": "Invalid or hijacked session",
                    "security_alert": "Session validation failed",
                    "request_id": None,
                    "response_time": 0.0
                }
        
        from .speed_layer.models import ValidationRequest
        
        request = ValidationRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=agent_id,
            session_id=session_id
        )
        
        # Process through speed layer
        result = await self.speed_layer_dispatcher.validate_request(request)
        
        # Log validation for audit trail
        await self.project_aggregate.handle_validation_request(
            request_id=request.request_id,
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=agent_id,
            session_id=session_id
        )
        
        return result.to_dict()
    
    async def modify_file(self,
                        file_path: str,
                        content: str,
                        agent_id: str,
                        session_id: Optional[str] = None) -> bool:
        """Modify file through the bridge system"""
        
        try:
            # Process through project aggregate
            event = await self.project_aggregate.handle_file_modification(
                path=file_path,
                content=content,
                agent_id=agent_id,
                session_id=session_id
            )
            
            # Publish event
            await self.event_stream.publish_event(event)
            
            return True
            
        except Exception as e:
            logger.error(f"File modification failed for {file_path}: {e}")
            return False
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        
        uptime = None
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            'is_running': self.is_running,
            'project_id': self.project_id,
            'mount_point': self.mount_point,
            'uptime_seconds': uptime,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            
            # Component status  
            'components': {
                'speed_layer': self.speed_layer_dispatcher.get_performance_stats(),
                'fuse_mount': self.fuse_mount_manager.get_status() if self.fuse_mount_manager else {'status': 'disabled'},
                'event_stream': self.event_stream.get_stream_stats(),
                'ast_anchors': self.ast_anchor_manager.get_statistics(),
                'project_state': self.project_aggregate.get_aggregate_stats()
            },
            
            # Performance metrics
            'performance': {
                'total_requests': self.request_count,
                'validation_requests': self.validation_count,
                'expert_escalations': self.expert_escalations,
                'background_tasks': len(self.background_tasks)
            }
        }
    
    async def create_context_package(self,
                                   package_id: str,
                                   files: List[str],
                                   description: str) -> bool:
        """Create context package for expert agents"""
        try:
            # This would integrate with context package manager
            # For now, basic implementation
            
            context_dir = Path(self.mount_point) / "context" / package_id
            context_dir.mkdir(parents=True, exist_ok=True)
            
            # Create manifest
            manifest = {
                'package_id': package_id,
                'title': package_id,
                'description': description,
                'created_at': datetime.utcnow().isoformat(),
                'files': files
            }
            
            with open(context_dir / "manifest.json", 'w') as f:
                import json
                json.dump(manifest, f, indent=2)
            
            logger.info(f"Created context package: {package_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create context package {package_id}: {e}")
            return False
    
    # Session Security Methods
    
    async def create_session(self, agent_id: str, ip_address: str = "", 
                           user_agent: str = "") -> Dict[str, Any]:
        """Create a new secure session for an agent"""
        try:
            session = self.session_security.create_session(agent_id, ip_address, user_agent)
            logger.info(f"Session created for agent {agent_id}: {session.session_id}")
            return {
                "session_id": session.session_id,
                "session_token": session.session_token,
                "created_at": session.created_at,
                "expires_at": session.created_at + self.session_security.session_timeout
            }
        except Exception as e:
            logger.error(f"Session creation failed for agent {agent_id}: {e}")
            return {"error": str(e)}
    
    async def validate_session(self, session_token: str, agent_id: str = "", 
                             ip_address: str = "", user_agent: str = "") -> Dict[str, Any]:
        """Validate session token and detect hijacking"""
        try:
            is_valid = self.session_security.validate_session(
                session_token, agent_id, ip_address, user_agent
            )
            return {"valid": is_valid}
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return {"valid": False, "error": str(e)}
    
    async def revoke_session(self, session_id: str, reason: str = "manual") -> Dict[str, Any]:
        """Revoke a session"""
        try:
            self.session_security.revoke_session(session_id, reason)
            logger.info(f"Session revoked: {session_id} (reason: {reason})")
            return {"revoked": True}
        except Exception as e:
            logger.error(f"Session revocation failed: {e}")
            return {"revoked": False, "error": str(e)}
    
    async def validate_websocket_connection(self, websocket_url: str, agent_id: str) -> Dict[str, Any]:
        """Validate WebSocket connection against hijacking"""
        try:
            is_valid = self.session_security.validate_websocket_hijacking(websocket_url, agent_id)
            return {"valid": is_valid}
        except Exception as e:
            logger.error(f"WebSocket validation error: {e}")
            return {"valid": False, "error": str(e)}
    
    async def validate_message(self, message: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Validate message against interception attacks"""
        try:
            is_valid = self.session_security.validate_message_interception(message, agent_id)
            return {"valid": is_valid}
        except Exception as e:
            logger.error(f"Message validation error: {e}")
            return {"valid": False, "error": str(e)}
    
    def get_session_security_report(self) -> Dict[str, Any]:
        """Get session security report"""
        return self.session_security.get_security_report()
    
    # Context manager support
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()