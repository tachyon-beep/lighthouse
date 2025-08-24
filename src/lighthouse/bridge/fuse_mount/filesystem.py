"""
Lighthouse FUSE Filesystem

Main FUSE filesystem implementation providing full POSIX operations
for expert agent interaction with the project state.

Performance Requirements:
- <5ms for stat, read, write operations
- <10ms for large directories 
- Streaming for files >100MB
- Real-time updates from event store
"""

import asyncio
import errno
import logging
import os
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import fuse
    from fuse import FUSE, FuseOSError, Operations
    FUSE_AVAILABLE = True
except ImportError:
    FUSE_AVAILABLE = False
    # Mock classes for testing when FUSE isn't available
    class Operations:
        pass
    class FuseOSError(Exception):
        def __init__(self, errno_code):
            self.errno = errno_code

from ..event_store.project_aggregate import ProjectAggregate
from ..event_store.time_travel import TimeTravelDebugger
from ..event_store.event_stream import EventStream
from ..ast_anchoring.anchor_manager import ASTAnchorManager

logger = logging.getLogger(__name__)


class VirtualFileInfo:
    """Information about a virtual file or directory"""
    
    def __init__(self,
                 path: str,
                 is_dir: bool = False,
                 size: int = 0,
                 content: Optional[str] = None,
                 mtime: float = None,
                 mode: int = None):
        self.path = path
        self.is_dir = is_dir
        self.size = size
        self.content = content or ""
        self.mtime = mtime or time.time()
        self.mode = mode or (stat.S_IFDIR | 0o755 if is_dir else stat.S_IFREG | 0o644)
        self.atime = self.mtime
        self.ctime = self.mtime


class LighthouseFUSE(Operations):
    """
    Lighthouse FUSE filesystem implementation
    
    Provides a virtual filesystem interface to the project with:
    - Live project state in /current
    - Historical snapshots in /history  
    - AST annotations in /shadows
    - Agent context in /context
    - Event streams in /streams
    """
    
    def __init__(self,
                 project_aggregate: ProjectAggregate,
                 time_travel_debugger: TimeTravelDebugger,
                 event_stream: EventStream,
                 ast_anchor_manager: ASTAnchorManager,
                 mount_point: str = "/mnt/lighthouse/project"):
        """
        Initialize FUSE filesystem
        
        Args:
            project_aggregate: Project aggregate for state management
            time_travel_debugger: Time travel debugger for history
            event_stream: Event stream for real-time updates
            ast_anchor_manager: AST anchor manager for shadows
            mount_point: Mount point path
        """
        
        if not FUSE_AVAILABLE:
            raise RuntimeError("FUSE not available. Install python-fuse3 or fusepy.")
        
        self.project_aggregate = project_aggregate
        self.time_travel_debugger = time_travel_debugger
        self.event_stream = event_stream
        self.ast_anchor_manager = ast_anchor_manager
        self.mount_point = Path(mount_point)
        
        # Virtual filesystem cache
        self._virtual_files: Dict[str, VirtualFileInfo] = {}
        self._cache_ttl = 5.0  # 5 second cache TTL
        self._last_cache_update = 0.0
        
        # File handle tracking
        self._open_files: Dict[int, Dict[str, Any]] = {}
        self._next_fh = 1
        
        # Performance monitoring
        self.operation_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Root directory structure
        self._init_virtual_structure()
    
    def _init_virtual_structure(self):
        """Initialize virtual directory structure"""
        root_dirs = [
            ('/', True),
            ('/current', True), 
            ('/shadows', True),
            ('/history', True),
            ('/context', True),
            ('/streams', True)
        ]
        
        for path, is_dir in root_dirs:
            self._virtual_files[path] = VirtualFileInfo(path, is_dir=is_dir)
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent handling"""
        if not path.startswith('/'):
            path = '/' + path
        return os.path.normpath(path)
    
    def _get_path_components(self, path: str) -> Tuple[str, str, str]:
        """
        Get path components for routing
        
        Returns:
            (section, subpath, full_path)
            e.g. "/current/src/main.py" -> ("current", "/src/main.py", "/current/src/main.py")
        """
        normalized = self._normalize_path(path)
        
        if normalized == '/':
            return ('root', '/', '/')
        
        parts = normalized.strip('/').split('/', 1)
        section = parts[0]
        subpath = '/' + parts[1] if len(parts) > 1 else '/'
        
        return (section, subpath, normalized)
    
    def _update_cache_if_needed(self):
        """Update virtual file cache if TTL expired"""
        current_time = time.time()
        
        if current_time - self._last_cache_update > self._cache_ttl:
            self._update_virtual_files()
            self._last_cache_update = current_time
    
    def _update_virtual_files(self):
        """Update virtual files from project state"""
        try:
            # Get current project state
            project_state = self.project_aggregate.current_state
            
            # Update /current files
            for file_path in project_state.list_files():
                virtual_path = f"/current{file_path}"
                file_version = project_state.get_file(file_path)
                
                if file_version:
                    self._virtual_files[virtual_path] = VirtualFileInfo(
                        path=virtual_path,
                        size=file_version.size,
                        content=file_version.content,
                        mtime=file_version.timestamp.timestamp()
                    )
            
            # Update /current directories
            for dir_path in project_state.list_directories():
                if dir_path != '/':  # Skip root
                    virtual_path = f"/current{dir_path}"
                    dir_info = project_state.directories.get(dir_path)
                    
                    if dir_info:
                        self._virtual_files[virtual_path] = VirtualFileInfo(
                            path=virtual_path,
                            is_dir=True,
                            mtime=dir_info.last_modified.timestamp()
                        )
            
            logger.debug(f"Updated {len(self._virtual_files)} virtual files")
            
        except Exception as e:
            logger.error(f"Error updating virtual files: {e}")
    
    # FUSE Operations Implementation
    
    def getattr(self, path: str, fh=None) -> Dict[str, Any]:
        """Get file attributes (enables ls, stat, file access)"""
        self.operation_count += 1
        
        try:
            normalized_path = self._normalize_path(path)
            section, subpath, full_path = self._get_path_components(path)
            
            # Update cache if needed
            self._update_cache_if_needed()
            
            # Check cache first
            if full_path in self._virtual_files:
                self.cache_hits += 1
                file_info = self._virtual_files[full_path]
                
                return {
                    'st_mode': file_info.mode,
                    'st_nlink': 2 if file_info.is_dir else 1,
                    'st_size': file_info.size,
                    'st_ctime': file_info.ctime,
                    'st_mtime': file_info.mtime,
                    'st_atime': file_info.atime,
                    'st_uid': os.getuid(),
                    'st_gid': os.getgid()
                }
            
            self.cache_misses += 1
            
            # Route to appropriate handler
            if section == 'current':
                return self._getattr_current(subpath)
            elif section == 'history':
                return self._getattr_history(subpath)
            elif section == 'shadows':
                return self._getattr_shadows(subpath)
            elif section == 'context':
                return self._getattr_context(subpath)
            elif section == 'streams':
                return self._getattr_streams(subpath)
            else:
                raise FuseOSError(errno.ENOENT)
            
        except FuseOSError:
            raise
        except Exception as e:
            logger.error(f"getattr error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def readdir(self, path: str, fh) -> List[str]:
        """List directory contents (enables ls, find)"""
        self.operation_count += 1
        
        try:
            normalized_path = self._normalize_path(path)
            section, subpath, full_path = self._get_path_components(path)
            
            if normalized_path == '/':
                # Root directory
                return ['.', '..', 'current', 'shadows', 'history', 'context', 'streams']
            
            # Route to appropriate handler
            if section == 'current':
                return self._readdir_current(subpath)
            elif section == 'history':
                return self._readdir_history(subpath)
            elif section == 'shadows':
                return self._readdir_shadows(subpath)
            elif section == 'context':
                return self._readdir_context(subpath)
            elif section == 'streams':
                return self._readdir_streams(subpath)
            else:
                raise FuseOSError(errno.ENOENT)
            
        except FuseOSError:
            raise
        except Exception as e:
            logger.error(f"readdir error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def read(self, path: str, size: int, offset: int, fh) -> bytes:
        """Read file contents (enables cat, grep, editors)"""
        self.operation_count += 1
        
        try:
            # Use file handle if available
            if fh in self._open_files:
                file_data = self._open_files[fh]
                content = file_data['content']
            else:
                # Read directly
                content = self._read_file_content(path)
            
            # Return requested slice
            if content:
                content_bytes = content.encode('utf-8')
                return content_bytes[offset:offset + size]
            
            return b''
            
        except Exception as e:
            logger.error(f"read error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def write(self, path: str, data: bytes, offset: int, fh) -> int:
        """Write file contents (enables editors, direct modifications)"""
        self.operation_count += 1
        
        try:
            section, subpath, full_path = self._get_path_components(path)
            
            # Only allow writes to /current and /shadows
            if section not in ['current', 'shadows']:
                raise FuseOSError(errno.EROFS)  # Read-only filesystem
            
            if section == 'current':
                return self._write_current_file(subpath, data, offset, fh)
            elif section == 'shadows':
                return self._write_shadow_file(subpath, data, offset, fh)
            
            raise FuseOSError(errno.ENOENT)
            
        except FuseOSError:
            raise
        except Exception as e:
            logger.error(f"write error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def open(self, path: str, flags) -> int:
        """Open file for reading/writing"""
        self.operation_count += 1
        
        try:
            # Generate file handle
            fh = self._next_fh
            self._next_fh += 1
            
            # Read current content
            content = self._read_file_content(path)
            
            # Store file handle info
            self._open_files[fh] = {
                'path': path,
                'content': content,
                'flags': flags,
                'modified': False
            }
            
            return fh
            
        except Exception as e:
            logger.error(f"open error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def release(self, path: str, fh) -> int:
        """Release file handle"""
        try:
            if fh in self._open_files:
                file_data = self._open_files[fh]
                
                # If file was modified, persist changes
                if file_data.get('modified'):
                    self._persist_file_changes(path, file_data['content'])
                
                del self._open_files[fh]
            
            return 0
            
        except Exception as e:
            logger.error(f"release error for {path}: {e}")
            return 0  # Don't fail release operations
    
    def create(self, path: str, mode) -> int:
        """Create new file"""
        self.operation_count += 1
        
        try:
            section, subpath, full_path = self._get_path_components(path)
            
            if section != 'current':
                raise FuseOSError(errno.EROFS)
            
            # Create empty file through project aggregate
            asyncio.create_task(
                self.project_aggregate.handle_file_modification(
                    path=subpath,
                    content="",
                    agent_id="fuse_user",
                    session_id=None
                )
            )
            
            # Return file handle
            return self.open(path, os.O_WRONLY | os.O_CREAT)
            
        except Exception as e:
            logger.error(f"create error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def mkdir(self, path: str, mode) -> int:
        """Create directory"""
        self.operation_count += 1
        
        try:
            section, subpath, full_path = self._get_path_components(path)
            
            if section != 'current':
                raise FuseOSError(errno.EROFS)
            
            # Create directory through project aggregate
            asyncio.create_task(
                self.project_aggregate.handle_directory_creation(
                    path=subpath,
                    agent_id="fuse_user",
                    session_id=None
                )
            )
            
            return 0
            
        except Exception as e:
            logger.error(f"mkdir error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def unlink(self, path: str) -> int:
        """Delete file"""
        self.operation_count += 1
        
        try:
            section, subpath, full_path = self._get_path_components(path)
            
            if section != 'current':
                raise FuseOSError(errno.EROFS)
            
            # Delete file through project aggregate
            asyncio.create_task(
                self.project_aggregate.handle_file_deletion(
                    path=subpath,
                    agent_id="fuse_user",
                    session_id=None
                )
            )
            
            return 0
            
        except Exception as e:
            logger.error(f"unlink error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    # Section-specific implementations
    
    def _getattr_current(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /current files"""
        project_state = self.project_aggregate.current_state
        
        if subpath == '/':
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_size': 4096,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time(),
                'st_uid': os.getuid(),
                'st_gid': os.getgid()
            }
        
        # Check if it's a file
        file_version = project_state.get_file(subpath)
        if file_version:
            return {
                'st_mode': stat.S_IFREG | 0o644,
                'st_nlink': 1,
                'st_size': file_version.size,
                'st_ctime': file_version.timestamp.timestamp(),
                'st_mtime': file_version.timestamp.timestamp(),
                'st_atime': file_version.timestamp.timestamp(),
                'st_uid': os.getuid(),
                'st_gid': os.getgid()
            }
        
        # Check if it's a directory
        if project_state.directory_exists(subpath):
            dir_info = project_state.directories.get(subpath)
            mtime = dir_info.last_modified.timestamp() if dir_info else time.time()
            
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_size': 4096,
                'st_ctime': mtime,
                'st_mtime': mtime,
                'st_atime': mtime,
                'st_uid': os.getuid(),
                'st_gid': os.getgid()
            }
        
        raise FuseOSError(errno.ENOENT)
    
    def _readdir_current(self, subpath: str) -> List[str]:
        """List /current directory contents"""
        project_state = self.project_aggregate.current_state
        
        if subpath == '/':
            # List root files and directories
            entries = ['.', '..']
            
            # Add files in root
            for file_path in project_state.list_files('/'):
                if file_path.count('/') == 1:  # Only direct children
                    entries.append(file_path[1:])  # Remove leading /
            
            # Add directories in root
            for dir_path in project_state.list_directories('/'):
                if dir_path.count('/') == 1:  # Only direct children
                    entries.append(dir_path[1:])  # Remove leading /
            
            return list(set(entries))  # Remove duplicates
        
        # List directory contents
        if not project_state.directory_exists(subpath):
            raise FuseOSError(errno.ENOTDIR)
        
        entries = ['.', '..']
        
        # Add files in directory
        for file_path in project_state.list_files(subpath):
            rel_path = os.path.relpath(file_path, subpath)
            if '/' not in rel_path:  # Only direct children
                entries.append(rel_path)
        
        # Add subdirectories
        for dir_path in project_state.list_directories(subpath):
            rel_path = os.path.relpath(dir_path, subpath)
            if '/' not in rel_path:  # Only direct children
                entries.append(rel_path)
        
        return entries
    
    def _getattr_history(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /history files"""
        # For now, return basic directory structure
        # Full implementation would query time travel debugger
        return {
            'st_mode': stat.S_IFDIR | 0o555,  # Read-only
            'st_nlink': 2,
            'st_size': 4096,
            'st_ctime': time.time(),
            'st_mtime': time.time(),
            'st_atime': time.time(),
            'st_uid': os.getuid(),
            'st_gid': os.getgid()
        }
    
    def _readdir_history(self, subpath: str) -> List[str]:
        """List /history directory contents"""
        # Placeholder implementation
        return ['.', '..', 'snapshots', 'events']
    
    def _getattr_shadows(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /shadows files"""
        # Shadow files mirror current structure but contain annotations
        return self._getattr_current(subpath)
    
    def _readdir_shadows(self, subpath: str) -> List[str]:
        """List /shadows directory contents"""
        # Mirror current directory structure
        return self._readdir_current(subpath)
    
    def _getattr_context(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /context files"""
        return {
            'st_mode': stat.S_IFDIR | 0o555,
            'st_nlink': 2,
            'st_size': 4096,
            'st_ctime': time.time(),
            'st_mtime': time.time(),
            'st_atime': time.time(),
            'st_uid': os.getuid(),
            'st_gid': os.getgid()
        }
    
    def _readdir_context(self, subpath: str) -> List[str]:
        """List /context directory contents"""
        # Placeholder for context packages
        return ['.', '..']
    
    def _getattr_streams(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /streams files"""
        if subpath == '/':
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_size': 4096,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time(),
                'st_uid': os.getuid(),
                'st_gid': os.getgid()
            }
        
        # Named pipes for streams
        return {
            'st_mode': stat.S_IFIFO | 0o644,
            'st_nlink': 1,
            'st_size': 0,
            'st_ctime': time.time(),
            'st_mtime': time.time(),
            'st_atime': time.time(),
            'st_uid': os.getuid(),
            'st_gid': os.getgid()
        }
    
    def _readdir_streams(self, subpath: str) -> List[str]:
        """List /streams directory contents"""
        if subpath == '/':
            return [
                '.', '..',
                'validation_requests',
                'expert_responses',
                'pair_sessions',
                'file_changes',
                'agent_activities'
            ]
        
        return ['.', '..']
    
    def _read_file_content(self, path: str) -> str:
        """Read file content from appropriate source"""
        section, subpath, full_path = self._get_path_components(path)
        
        if section == 'current':
            file_version = self.project_aggregate.current_state.get_file(subpath)
            return file_version.content if file_version else ""
        
        elif section == 'shadows':
            # Read shadow annotations
            shadow_content = self.ast_anchor_manager.get_shadow_content(subpath)
            return str(shadow_content) if shadow_content else ""
        
        elif section == 'history':
            # Read historical content
            # Placeholder implementation
            return f"Historical view of {subpath}"
        
        return ""
    
    def _write_current_file(self, subpath: str, data: bytes, offset: int, fh) -> int:
        """Write to file in /current"""
        try:
            # Get current content
            current_content = self._read_file_content(f"/current{subpath}")
            current_bytes = current_content.encode('utf-8')
            
            # Apply write at offset
            new_bytes = bytearray(current_bytes)
            new_bytes[offset:offset + len(data)] = data
            new_content = new_bytes.decode('utf-8')
            
            # Update file handle
            if fh in self._open_files:
                self._open_files[fh]['content'] = new_content
                self._open_files[fh]['modified'] = True
            
            return len(data)
            
        except Exception as e:
            logger.error(f"Error writing current file {subpath}: {e}")
            raise FuseOSError(errno.EIO)
    
    def _write_shadow_file(self, subpath: str, data: bytes, offset: int, fh) -> int:
        """Write to shadow annotation file"""
        # Placeholder implementation for shadow file writes
        # Would integrate with AST anchor manager
        return len(data)
    
    def _persist_file_changes(self, path: str, content: str):
        """Persist file changes through project aggregate"""
        section, subpath, full_path = self._get_path_components(path)
        
        if section == 'current':
            # Create async task to persist changes
            asyncio.create_task(
                self.project_aggregate.handle_file_modification(
                    path=subpath,
                    content=content,
                    agent_id="fuse_user",
                    session_id=None
                )
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get FUSE filesystem statistics"""
        return {
            'operation_count': self.operation_count,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': self.cache_hits / max(1, self.cache_hits + self.cache_misses),
            'virtual_files_cached': len(self._virtual_files),
            'open_file_handles': len(self._open_files)
        }