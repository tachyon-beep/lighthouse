"""
FUSE Mount Filesystem

Full POSIX filesystem implementation enabling expert agents to use standard Unix tools.
Provides a virtual filesystem interface to the project with live updates, historical views,
and shadow annotations.

Virtual Filesystem Structure:
/mnt/lighthouse/project/
├── current/          # Live project state (read-write)
├── shadows/          # AST-anchored annotations (read-write)
├── history/          # Time-travel debugging (read-only)
├── context/          # Agent context packages (read-only)
└── streams/          # Live event streams (named pipes)

Features:
- Complete POSIX operations (getattr, read, write, readdir)
- Event-sourced persistence for all modifications
- Real-time synchronization with project state
- Performance optimization for common operations
- Integration with AST anchoring system
"""

from .filesystem import LighthouseFUSE
from .operations import FUSEOperations
from .virtual_files import VirtualFileSystem
from .mount_manager import FUSEMountManager

__all__ = [
    'LighthouseFUSE',
    'FUSEOperations', 
    'VirtualFileSystem',
    'FUSEMountManager'
]