"""
HLD Bridge - Advanced Multi-Agent Coordination System

The Lighthouse Validation Bridge serves as the central coordination hub for multi-agent systems,
providing event-sourced validation, expert agent coordination, and real-time pair programming
capabilities through a speed-optimized, FUSE-integrated architecture.

Core Components:
- Speed Layer: <100ms response time for 99% of operations
- Event-Sourced Architecture: Complete audit trails and time travel debugging  
- FUSE Mount: Full POSIX filesystem for expert agent integration
- AST Anchoring: Refactoring-resistant code annotations
- Expert Coordination: FUSE-based agent communication
- Pair Programming Hub: Real-time collaborative sessions
"""

from .main_bridge import LighthouseBridge
from .speed_layer.dispatcher import SpeedLayerDispatcher
from .event_store.project_aggregate import ProjectAggregate

# Optional FUSE support
try:
    from .fuse_mount.filesystem import LighthouseFUSE
except (ImportError, OSError):
    LighthouseFUSE = None

from .ast_anchoring.anchor_manager import ASTAnchorManager
from .expert_coordination.interface import ExpertAgentInterface
from .pair_programming.session_manager import PairProgrammingSessionManager

# Compatibility classes
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class CommandData:
    """Legacy command data structure"""
    id: str
    tool: str
    input: Dict[str, Any]
    agent: str
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

# Backward compatibility aliases
ValidationBridge = LighthouseBridge

def get_validation_bridge():
    """Legacy compatibility function"""
    return LighthouseBridge(project_id="default_project")

__all__ = [
    'LighthouseBridge',
    'ValidationBridge',  # Compatibility alias
    'CommandData',       # Compatibility class
    'get_validation_bridge',   # Legacy compatibility
    'SpeedLayerDispatcher', 
    'ProjectAggregate',
    'ASTAnchorManager',
    'ExpertAgentInterface',
    'PairProgrammingSessionManager'
]

# Add LighthouseFUSE only if available
if LighthouseFUSE is not None:
    __all__.append('LighthouseFUSE')

__version__ = "2.0.0"