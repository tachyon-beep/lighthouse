"""
FUSE Mount Manager for Lighthouse Bridge

Manages the complete FUSE filesystem mount lifecycle, integration with Bridge components,
and ensures proper Unix tool access for expert agents.

HLD Requirements:
- FUSE Mount at /mnt/lighthouse/project/
- Full POSIX filesystem enabling expert agents to use standard Unix tools
- Performance: <5ms for common operations, <10ms for large directories
- Integration with Event Store, ProjectAggregate, AST anchoring
"""

import asyncio
import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import fuse
    from fuse import FUSE
    FUSE_AVAILABLE = True
except ImportError:
    FUSE_AVAILABLE = False

from .complete_lighthouse_fuse import CompleteLighthouseFUSE
from ..event_store.project_aggregate import ProjectAggregate
from ..ast_anchoring.anchor_manager import ASTAnchorManager
from ..event_store.event_stream import EventStream
from ...event_store import EventStore
from ..event_store.time_travel import TimeTravelDebugger

logger = logging.getLogger(__name__)


class MountError(Exception):
    """Exception raised when mount operations fail"""
    pass


class FUSEMountManager:
    """Manager for complete FUSE filesystem mounting and Bridge integration"""
    
    def __init__(self, 
                 event_store: EventStore,
                 project_aggregate: ProjectAggregate,
                 ast_anchor_manager: ASTAnchorManager,
                 event_stream_manager: EventStream,
                 mount_point: str = "/mnt/lighthouse/project",
                 foreground: bool = False,
                 allow_other: bool = True):
        """
        Initialize FUSE mount manager with Bridge integration
        
        Args:
            event_store: Main Event Store for persistence
            project_aggregate: Project state management
            ast_anchor_manager: AST anchoring system
            event_stream_manager: Real-time event streaming
            mount_point: Directory to mount filesystem
            foreground: Run FUSE in foreground (useful for debugging)
            allow_other: Allow other users to access filesystem
        """
        
        if not FUSE_AVAILABLE:
            raise MountError("FUSE not available. Install python-fuse3 or fusepy.")
        
        # Bridge components
        self.event_store = event_store
        self.project_aggregate = project_aggregate
        self.ast_anchor_manager = ast_anchor_manager
        self.event_stream_manager = event_stream_manager
        
        # Initialize time travel debugger
        self.time_travel_debugger = TimeTravelDebugger(event_store)
        
        # Create complete FUSE filesystem with authentication
        import secrets
        auth_secret = secrets.token_hex(32)  # Generate secure auth secret
        self.filesystem = CompleteLighthouseFUSE(
            project_aggregate=project_aggregate,
            time_travel_debugger=self.time_travel_debugger,
            event_stream=event_stream_manager,
            ast_anchor_manager=ast_anchor_manager,
            auth_secret=auth_secret
        )
        
        self.mount_point = Path(mount_point)
        self.foreground = foreground
        self.allow_other = allow_other
        
        # Mount state
        self.is_mounted = False
        self.fuse_process: Optional[Any] = None
        self.mount_task: Optional[asyncio.Task] = None
        
        # Health monitoring
        self.health_check_interval = 30.0  # seconds
        self.health_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.mount_time: Optional[float] = None
        self.mount_errors = 0
        self.health_checks = 0
        self.health_failures = 0
    
    async def mount(self) -> bool:
        """
        Mount the FUSE filesystem
        
        Returns:
            True if mount successful, False otherwise
        """
        if self.is_mounted:
            logger.warning("Filesystem already mounted")
            return True
        
        try:
            # Create mount point if it doesn't exist
            await self._create_mount_point()
            
            # Check if mount point is already in use
            if await self._is_mount_point_busy():
                raise MountError(f"Mount point {self.mount_point} is already in use")
            
            # Prepare FUSE options
            fuse_options = self._get_fuse_options()
            
            # Start FUSE filesystem
            logger.info(f"Mounting FUSE filesystem at {self.mount_point}")
            
            if self.foreground:
                # Run in foreground (blocking)
                FUSE(
                    self.filesystem,
                    str(self.mount_point),
                    **fuse_options
                )
                self.is_mounted = True
            else:
                # Run in background
                self.mount_task = asyncio.create_task(
                    self._run_fuse_background(fuse_options)
                )
                
                # Wait a moment and check if mount succeeded
                await asyncio.sleep(1.0)
                
                if await self._verify_mount():
                    self.is_mounted = True
                    self.mount_time = asyncio.get_event_loop().time()
                    
                    # Start health monitoring
                    self.health_task = asyncio.create_task(self._monitor_health())
                    
                    logger.info(f"FUSE filesystem mounted successfully at {self.mount_point}")
                    logger.info("Expert agents can now use standard Unix tools:")
                    logger.info(f"  cd {self.mount_point}/current/")
                    logger.info(f"  find {self.mount_point} -name '*.py'")
                    logger.info(f"  cat {self.mount_point}/current/src/main.py")
                    logger.info(f"  grep -r 'TODO' {self.mount_point}/current/")
                else:
                    raise MountError("Mount verification failed")
            
            return True
            
        except Exception as e:
            self.mount_errors += 1
            logger.error(f"Failed to mount FUSE filesystem: {e}")
            
            # Cleanup on failure
            await self._cleanup_failed_mount()
            
            return False
    
    async def unmount(self, force: bool = False) -> bool:
        """
        Unmount the FUSE filesystem
        
        Args:
            force: Force unmount even if filesystem is busy
            
        Returns:
            True if unmount successful, False otherwise
        """
        if not self.is_mounted:
            logger.warning("Filesystem not mounted")
            return True
        
        try:
            logger.info(f"Unmounting FUSE filesystem at {self.mount_point}")
            
            # Stop health monitoring
            if self.health_task:
                self.health_task.cancel()
                self.health_task = None
            
            # Try graceful unmount first
            success = await self._graceful_unmount()
            
            # Force unmount if needed and requested
            if not success and force:
                success = await self._force_unmount()
            
            if success:
                self.is_mounted = False
                self.mount_time = None
                
                # Cancel mount task if running
                if self.mount_task:
                    self.mount_task.cancel()
                    self.mount_task = None
                
                logger.info("FUSE filesystem unmounted successfully")
            else:
                logger.error("Failed to unmount FUSE filesystem")
            
            return success
            
        except Exception as e:
            logger.error(f"Error during unmount: {e}")
            return False
    
    async def remount(self) -> bool:
        """Remount the filesystem (unmount + mount)"""
        logger.info("Remounting FUSE filesystem")
        
        if self.is_mounted:
            if not await self.unmount():
                logger.error("Failed to unmount for remount")
                return False
        
        # Wait a moment for cleanup
        await asyncio.sleep(1.0)
        
        return await self.mount()
    
    async def _create_mount_point(self):
        """Create mount point directory if it doesn't exist"""
        try:
            self.mount_point.mkdir(parents=True, exist_ok=True)
            
            # Set appropriate permissions
            os.chmod(self.mount_point, 0o755)
            
            logger.debug(f"Created mount point: {self.mount_point}")
            
        except Exception as e:
            raise MountError(f"Failed to create mount point {self.mount_point}: {e}")
    
    async def _is_mount_point_busy(self) -> bool:
        """Check if mount point is already in use"""
        try:
            # Check if directory is a mount point
            result = subprocess.run(
                ['mountpoint', str(self.mount_point)],
                capture_output=True,
                text=True
            )
            
            return result.returncode == 0
            
        except Exception:
            # If mountpoint command is not available, assume not busy
            return False
    
    def _get_fuse_options(self) -> Dict[str, Any]:
        """Get FUSE mount options"""
        options = {
            'nothreads': False,  # Enable multi-threading
            'allow_other': self.allow_other,
            'default_permissions': True,
            'foreground': self.foreground,
        }
        
        # Add debug options if in foreground mode
        if self.foreground:
            options['debug'] = True
        
        return options
    
    async def _run_fuse_background(self, fuse_options: Dict[str, Any]):
        """Run FUSE in background task"""
        try:
            # Run FUSE in executor to avoid blocking
            loop = asyncio.get_event_loop()
            
            await loop.run_in_executor(
                None,
                lambda: FUSE(
                    self.filesystem,
                    str(self.mount_point),
                    **fuse_options
                )
            )
            
        except asyncio.CancelledError:
            logger.info("FUSE background task cancelled")
        except Exception as e:
            logger.error(f"FUSE background task error: {e}")
            self.mount_errors += 1
    
    async def _verify_mount(self) -> bool:
        """Verify that filesystem is properly mounted"""
        try:
            # Check if mount point is accessible
            if not self.mount_point.exists():
                return False
            
            # Try to list root directory  
            root_contents = list(self.mount_point.iterdir())
            expected_dirs = {'current', 'shadows', 'history', 'context', 'streams', 'debug'}
            actual_dirs = {path.name for path in root_contents if path.is_dir()}
            
            # Check if expected directories are present
            return expected_dirs.issubset(actual_dirs)
            
        except Exception as e:
            logger.warning(f"Mount verification failed: {e}")
            return False
    
    async def _graceful_unmount(self) -> bool:
        """Attempt graceful unmount"""
        try:
            # Use fusermount to unmount
            result = subprocess.run(
                ['fusermount', '-u', str(self.mount_point)],
                capture_output=True,
                text=True,
                timeout=10.0
            )
            
            if result.returncode == 0:
                logger.debug("Graceful unmount successful")
                return True
            else:
                logger.warning(f"Graceful unmount failed: {result.stderr}")
                return False
            
        except subprocess.TimeoutExpired:
            logger.warning("Graceful unmount timed out")
            return False
        except Exception as e:
            logger.warning(f"Graceful unmount error: {e}")
            return False
    
    async def _force_unmount(self) -> bool:
        """Force unmount using system calls"""
        try:
            # Try lazy unmount
            result = subprocess.run(
                ['fusermount', '-u', '-z', str(self.mount_point)],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            
            if result.returncode == 0:
                logger.debug("Force unmount successful")
                return True
            
            # Try umount as fallback
            result = subprocess.run(
                ['umount', '-l', str(self.mount_point)],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Force unmount error: {e}")
            return False
    
    async def _cleanup_failed_mount(self):
        """Clean up after failed mount attempt"""
        try:
            # Cancel mount task if running
            if self.mount_task and not self.mount_task.done():
                self.mount_task.cancel()
                self.mount_task = None
            
            # Try to unmount if partially mounted
            await self._graceful_unmount()
            
        except Exception as e:
            logger.warning(f"Cleanup after failed mount error: {e}")
    
    async def _monitor_health(self):
        """Monitor filesystem health periodically"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                self.health_checks += 1
                
                # Check if filesystem is still responsive
                if not await self._verify_mount():
                    self.health_failures += 1
                    logger.warning("Filesystem health check failed")
                    
                    # Try to remount if too many failures
                    if self.health_failures >= 3:
                        logger.error("Too many health check failures, attempting remount")
                        await self.remount()
                        self.health_failures = 0
                else:
                    # Reset failure count on successful check
                    self.health_failures = 0
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    def get_status(self) -> Dict[str, Any]:
        """Get mount manager status"""
        uptime = None
        if self.mount_time:
            uptime = asyncio.get_event_loop().time() - self.mount_time
        
        status = {
            'is_mounted': self.is_mounted,
            'mount_point': str(self.mount_point),
            'uptime_seconds': uptime,
            'mount_errors': self.mount_errors,
            'health_checks': self.health_checks,
            'health_failures': self.health_failures,
        }
        
        if self.is_mounted and hasattr(self.filesystem, 'get_performance_stats'):
            status['filesystem_stats'] = self.filesystem.get_performance_stats()
        
        return status
    
    async def shutdown(self):
        """Shutdown mount manager and cleanup"""
        logger.info("Shutting down FUSE mount manager")
        
        if self.is_mounted:
            await self.unmount(force=True)
        
        # Cancel any remaining tasks
        if self.health_task:
            self.health_task.cancel()
        
        if self.mount_task:
            self.mount_task.cancel()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        asyncio.create_task(self.shutdown())
    
    async def reload_project_state(self) -> bool:
        """Reload project state from Event Store"""
        try:
            if not self.is_mounted:
                logger.error("FUSE not mounted, cannot reload state")
                return False
            
            logger.info("Reloading project state from Event Store...")
            
            # Trigger cache invalidation and reload
            if hasattr(self.filesystem, 'invalidate_caches'):
                await self.filesystem.invalidate_caches()
            
            # Refresh project aggregate state
            if hasattr(self.project_aggregate, 'refresh_from_events'):
                await self.project_aggregate.refresh_from_events()
            
            logger.info("Project state reloaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reload project state: {e}")
            return False
    
    async def create_expert_context_package(self, 
                                          package_id: str, 
                                          context_data: dict) -> bool:
        """Create context package for expert agents"""
        try:
            if not self.is_mounted:
                logger.error("FUSE not mounted, cannot create context package")
                return False
            
            logger.info(f"Creating expert context package: {package_id}")
            
            # Context packages are handled by the FUSE filesystem
            if hasattr(self.filesystem, 'create_context_package'):
                success = await self.filesystem.create_context_package(package_id, context_data)
                if success:
                    logger.info(f"Context package created: {self.mount_point}/context/{package_id}")
                return success
            else:
                logger.warning("Filesystem does not support context packages")
                return False
            
        except Exception as e:
            logger.error(f"Failed to create context package {package_id}: {e}")
            return False
    
    async def get_expert_usage_stats(self) -> dict:
        """Get statistics on expert agent usage of the filesystem"""
        if hasattr(self.filesystem, 'get_expert_usage_stats'):
            return self.filesystem.get_expert_usage_stats()
        return {}


# Integration helper functions for Bridge initialization
async def initialize_fuse_mount(bridge_components: dict) -> FUSEMountManager:
    """Initialize FUSE mount manager with Bridge components"""
    mount_manager = FUSEMountManager(
        event_store=bridge_components['event_store'],
        project_aggregate=bridge_components['project_aggregate'],
        ast_anchor_manager=bridge_components['ast_anchor_manager'],
        event_stream_manager=bridge_components['event_stream']
    )
    
    return mount_manager


async def start_fuse_filesystem(mount_manager: FUSEMountManager) -> bool:
    """Start the FUSE filesystem with error handling"""
    try:
        success = await mount_manager.mount()
        
        if success:
            logger.info("🚀 FUSE filesystem ready for expert agents")
            logger.info("Expert agents can now use standard Unix tools:")
            logger.info("  ls /mnt/lighthouse/project/current/")
            logger.info("  find /mnt/lighthouse/project -name '*.py' -exec grep -l 'TODO' {} \\;")
            logger.info("  vim /mnt/lighthouse/project/current/src/main.py")
            logger.info("  diff /mnt/lighthouse/project/history/2024-01-15T10:30:00Z/main.py /mnt/lighthouse/project/current/src/main.py")
        else:
            logger.error("❌ FUSE filesystem failed to start")
        
        return success
        
    except Exception as e:
        logger.error(f"Failed to start FUSE filesystem: {e}")
        return False