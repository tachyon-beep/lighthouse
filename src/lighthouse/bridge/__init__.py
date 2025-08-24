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
from .fuse_mount.filesystem import LighthouseFUSE
from .ast_anchoring.anchor_manager import ASTAnchorManager
from .expert_coordination.interface import ExpertAgentInterface
from .pair_programming.session_manager import PairProgrammingSessionManager

__all__ = [
    'LighthouseBridge',
    'SpeedLayerDispatcher', 
    'ProjectAggregate',
    'LighthouseFUSE',
    'ASTAnchorManager',
    'ExpertAgentInterface',
    'PairProgrammingSessionManager'
]

__version__ = "2.0.0"