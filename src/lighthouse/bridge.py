"""
Lighthouse Bridge Integration

Complete HLD Bridge implementation providing advanced multi-agent coordination.

This module provides the main integration point for the Lighthouse Bridge system,
combining all architectural components:

- Speed Layer: <100ms validation for 99% of requests
- Event-Sourced Architecture: Complete audit trails and time travel debugging
- FUSE Mount Filesystem: Expert agent integration via standard Unix tools
- AST Anchoring System: Refactoring-resistant code annotations
- Expert Coordination: FUSE-based agent communication
- Pair Programming Hub: Real-time collaborative sessions

Usage:
    from lighthouse.bridge import LighthouseBridge
    
    async with LighthouseBridge("my_project") as bridge:
        result = await bridge.validate_command(
            tool_name="Edit",
            tool_input={"file_path": "/src/main.py", "content": "..."},
            agent_id="claude_assistant"
        )
        
        if result["decision"] == "approved":
            success = await bridge.modify_file(
                file_path="/src/main.py",
                content="...",
                agent_id="claude_assistant"
            )
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .bridge.main_bridge import LighthouseBridge as _LighthouseBridge

logger = logging.getLogger(__name__)

# Re-export main bridge class
LighthouseBridge = _LighthouseBridge

# Convenience functions for common operations

async def create_bridge(project_id: str, 
                       mount_point: str = "/mnt/lighthouse/project",
                       config: Optional[Dict[str, Any]] = None) -> LighthouseBridge:
    """
    Create and start a new Lighthouse Bridge instance
    
    Args:
        project_id: Unique project identifier
        mount_point: FUSE filesystem mount point
        config: Optional configuration overrides
        
    Returns:
        Running bridge instance
    """
    
    bridge = LighthouseBridge(
        project_id=project_id,
        mount_point=mount_point,
        config=config
    )
    
    success = await bridge.start()
    if not success:
        raise RuntimeError("Failed to start Lighthouse Bridge")
    
    return bridge


async def validate_command_simple(project_id: str,
                                tool_name: str,
                                tool_input: Dict[str, Any],
                                agent_id: str) -> Dict[str, Any]:
    """
    Simple command validation without persistent bridge
    
    Creates a temporary bridge instance for one-off validations.
    For repeated operations, use a persistent bridge instance.
    """
    
    async with LighthouseBridge(project_id) as bridge:
        return await bridge.validate_command(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=agent_id
        )


def get_bridge_status(bridge: LighthouseBridge) -> Dict[str, Any]:
    """Get comprehensive bridge system status"""
    return bridge.get_system_status()


# Legacy compatibility - maintain existing bridge interface
class ValidationBridge:
    """
    Legacy validation bridge interface
    
    Provides backwards compatibility with existing code that expects
    the simpler validation bridge interface.
    """
    
    def __init__(self, port: int = 8765):
        self.port = port
        self._bridge: Optional[LighthouseBridge] = None
        self._project_id = "default_project"
        
        logger.warning(
            "ValidationBridge is deprecated. "
            "Use LighthouseBridge for full functionality."
        )
    
    async def start(self):
        """Start the validation bridge"""
        self._bridge = await create_bridge(
            project_id=self._project_id,
            config={'legacy_mode': True}
        )
    
    async def stop(self):
        """Stop the validation bridge"""
        if self._bridge:
            await self._bridge.stop()
            self._bridge = None
    
    async def get_status(self) -> Dict[str, Any]:
        """Get bridge status"""
        if self._bridge:
            status = self._bridge.get_system_status()
            
            # Convert to legacy format
            return {
                'status': 'running' if status['is_running'] else 'stopped',
                'pending_commands': 0,  # Legacy field
                'approved_commands': 0,  # Legacy field  
                'subscribers': 0,  # Legacy field
                'uptime': status['uptime_seconds']
            }
        
        return {'status': 'stopped'}
    
    async def approve_command(self, command_id: str, reason: str = "Manual approval"):
        """Approve a command (legacy interface)"""
        # In the new architecture, this would be handled by expert agents
        logger.info(f"Legacy approval for {command_id}: {reason}")
        return {'success': True, 'id': command_id}


# Module-level convenience functions

def is_fuse_available() -> bool:
    """Check if FUSE is available for filesystem mounting"""
    try:
        import fuse
        return True
    except ImportError:
        return False


def is_tree_sitter_available() -> bool:
    """Check if tree-sitter is available for AST parsing"""
    try:
        import tree_sitter
        return True
    except ImportError:
        return False


def get_system_requirements() -> Dict[str, bool]:
    """Get system requirements status"""
    return {
        'fuse_available': is_fuse_available(),
        'tree_sitter_available': is_tree_sitter_available(),
        'python_version_ok': True,  # We're already running Python
    }


def get_recommended_config() -> Dict[str, Any]:
    """Get recommended configuration for production use"""
    return {
        'memory_cache_size': 10000,
        'expert_timeout': 30.0,
        'fuse_foreground': False,
        'fuse_allow_other': True,
        'policy_config_path': None,  # Use built-in policies
        'ml_model_path': None,       # Use simple classifier
    }


# Export key classes and functions
__all__ = [
    'LighthouseBridge',
    'ValidationBridge',  # Legacy
    'create_bridge',
    'validate_command_simple',
    'get_bridge_status',
    'is_fuse_available',
    'is_tree_sitter_available', 
    'get_system_requirements',
    'get_recommended_config'
]