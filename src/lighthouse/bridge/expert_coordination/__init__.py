"""
Expert Coordination System

FUSE-based expert agent coordination and communication.
Enables expert agents to interact through the FUSE filesystem as primary interface.

Features:
- FUSE-first expert workflow
- Named pipe streams for real-time communication
- Context package system for informed decision-making
- Expert discovery and routing
- Load balancing across available experts

Core Components:
- ExpertAgentInterface: Primary interface for expert agents
- ExpertRegistry: Discovery and capability matching
- ContextPackageManager: Context preparation for experts
- ExpertCoordinator: Orchestration and routing
"""

from .interface import ExpertAgentInterface
from .registry import ExpertRegistry, ExpertCapability
from .context_manager import ContextPackageManager, ContextPackage
from .coordinator import ExpertCoordinator

__all__ = [
    'ExpertAgentInterface',
    'ExpertRegistry',
    'ExpertCapability',
    'ContextPackageManager', 
    'ContextPackage',
    'ExpertCoordinator'
]