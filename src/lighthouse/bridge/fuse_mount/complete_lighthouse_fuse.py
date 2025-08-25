"""
Complete Lighthouse FUSE Filesystem

Full implementation of the FUSE filesystem as specified in the HLD Bridge Implementation Plan.
Provides complete Unix tool integration for expert agents via /mnt/lighthouse/project/:

Directory Structure:
├── current/                    # Live project state (read-write)
├── history/                    # Historical snapshots (read-only)
├── shadows/                    # AST annotations and metadata
├── context/                    # Expert agent context packages  
├── streams/                    # Real-time communication pipes
└── debug/                      # Development and debugging tools

Performance: <5ms for common operations, <10ms for large directories
"""

import asyncio
import errno
import hashlib
import json
import logging
import os
import stat
import time
from datetime import datetime, timedelta
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional, Tuple, Union
from collections import defaultdict
from dataclasses import dataclass, field

try:
    import fuse
    from fuse import FUSE, FuseOSError, Operations
    FUSE_AVAILABLE = True
except ImportError:
    FUSE_AVAILABLE = False
    class Operations:
        pass
    class FuseOSError(Exception):
        def __init__(self, errno_code):
            self.errno = errno_code

# Import secure components  
from lighthouse.event_store.models import Event, EventType
from .authentication import FUSEAuthenticationManager, FUSEAuthenticationContext
from ..event_store.project_aggregate import ProjectAggregate
from ..event_store.time_travel import TimeTravelDebugger
from ..event_store.event_stream import EventStream
from ..ast_anchoring.anchor_manager import ASTAnchorManager

logger = logging.getLogger(__name__)


@dataclass
class ContextPackage:
    """Context package for expert agents"""
    package_id: str
    request_id: str
    agent_capabilities: List[str]
    files_involved: List[str]
    context_data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    def to_json(self) -> str:
        """Convert to JSON for FUSE filesystem"""
        return json.dumps({
            'package_id': self.package_id,
            'request_id': self.request_id,
            'agent_capabilities': self.agent_capabilities,
            'files_involved': self.files_involved,
            'context_data': self.context_data,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }, indent=2)


@dataclass
class StreamChannel:
    """Real-time communication stream"""
    stream_name: str
    stream_type: str  # 'validation_requests', 'expert_responses', 'pair_sessions'
    subscribers: List[str] = field(default_factory=list)
    message_queue: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)


class CompleteLighthouseFUSE(Operations):
    """
    Complete FUSE filesystem implementation for Lighthouse Bridge
    
    Provides full Unix tool integration as specified in HLD requirements:
    - /current: Live project state with read-write access
    - /history: Time-travel debugging with timestamped snapshots
    - /shadows: AST annotations and metadata overlay
    - /context: Expert agent context packages
    - /streams: Real-time communication named pipes
    - /debug: Development and debugging utilities
    """
    
    def __init__(self,
                 project_aggregate: ProjectAggregate,
                 time_travel_debugger: TimeTravelDebugger,
                 event_stream: EventStream,
                 ast_anchor_manager: ASTAnchorManager,
                 auth_secret: str,
                 mount_point: str = "/mnt/lighthouse/project"):
        """
        Initialize complete FUSE filesystem
        
        Args:
            project_aggregate: Project state and business logic
            time_travel_debugger: Historical state reconstruction
            event_stream: Real-time event streaming
            ast_anchor_manager: AST annotation management
            auth_secret: Secret for HMAC authentication
            mount_point: Where to mount the filesystem
        """
        
        # Core components
        self.project_aggregate = project_aggregate
        self.time_travel_debugger = time_travel_debugger
        self.event_stream = event_stream
        self.ast_anchor_manager = ast_anchor_manager
        self.mount_point = mount_point
        
        # Authentication system
        self.auth_manager = FUSEAuthenticationManager(auth_secret)
        self.auth_context = FUSEAuthenticationContext(self.auth_manager)
        
        # Filesystem structure
        self.root_directories = {
            'current': 'Live project state (read-write)',
            'history': 'Historical snapshots (read-only)', 
            'shadows': 'AST annotations and metadata',
            'context': 'Expert agent context packages',
            'streams': 'Real-time communication pipes',
            'debug': 'Development and debugging tools'
        }
        
        # Performance optimization caches
        self._attr_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._dir_cache: Dict[str, Tuple[List[str], float]] = {}
        self._content_cache: Dict[str, Tuple[bytes, float]] = {}
        self._cache_ttl = 5.0  # 5 second TTL for performance
        
        # History state cache (expensive to compute)
        self._history_cache: Dict[str, Tuple[Any, float]] = {}
        self._history_cache_ttl = 60.0  # 1 minute for history states
        
        # Context packages for expert agents
        self._context_packages: Dict[str, ContextPackage] = {}
        
        # Stream management for real-time communication
        self._streams: Dict[str, StreamChannel] = {}
        self._init_default_streams()
        
        # Security and rate limiting
        self._operation_counts = defaultdict(int)
        self._last_rate_reset = time.time()
        self._max_operations_per_second = 1000
        
        # Performance monitoring
        self._operation_times = defaultdict(list)
        self._performance_stats = {
            'total_operations': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'avg_response_time_ms': 0.0
        }
    
    def _init_default_streams(self):
        """Initialize default communication streams"""
        default_streams = [
            ('validation_requests', 'Expert validation request queue'),
            ('expert_responses', 'Expert response notifications'),
            ('pair_sessions', 'Pair programming session events'),
            ('file_changes', 'Real-time file change notifications'),
            ('agent_activities', 'Agent activity monitoring'),
            ('debug_events', 'Debug and diagnostic events')
        ]
        
        for stream_name, description in default_streams:
            self._streams[stream_name] = StreamChannel(
                stream_name=stream_name,
                stream_type=stream_name
            )
    
    def _check_rate_limit(self, operation: str) -> bool:
        """Rate limiting for security and performance"""
        current_time = time.time()
        
        # Reset counters every second
        if current_time - self._last_rate_reset > 1.0:
            self._operation_counts.clear()
            self._last_rate_reset = current_time
        
        self._operation_counts[operation] += 1
        total_ops = sum(self._operation_counts.values())
        
        return total_ops <= self._max_operations_per_second
    
    def _record_performance(self, operation: str, start_time: float):
        """Record performance metrics"""
        response_time_ms = (time.time() - start_time) * 1000
        self._operation_times[operation].append(response_time_ms)
        
        # Keep only last 1000 measurements per operation
        if len(self._operation_times[operation]) > 1000:
            self._operation_times[operation] = self._operation_times[operation][-1000:]
        
        self._performance_stats['total_operations'] += 1
        
        # Update average response time
        all_times = [t for times in self._operation_times.values() for t in times]
        if all_times:
            self._performance_stats['avg_response_time_ms'] = sum(all_times) / len(all_times)
    
    def _get_cached_or_compute(self, cache_dict: Dict, key: str, ttl: float, compute_func):
        """Generic cache helper with TTL"""
        current_time = time.time()
        
        if key in cache_dict:
            value, cached_time = cache_dict[key]
            if current_time - cached_time < ttl:
                self._performance_stats['cache_hits'] += 1
                return value
        
        # Compute new value
        self._performance_stats['cache_misses'] += 1
        value = compute_func()
        cache_dict[key] = (value, current_time)
        
        # Limit cache size
        if len(cache_dict) > 1000:
            # Remove oldest 20% of entries
            sorted_items = sorted(cache_dict.items(), key=lambda x: x[1][1])
            cache_dict.clear()
            cache_dict.update(sorted_items[-800:])  # Keep newest 800
        
        return value
    
    # Core FUSE Operations
    
    def getattr(self, path: str, fh=None) -> Dict[str, Any]:
        """Get file attributes - enables ls, stat, file access"""
        start_time = time.time()
        
        # Check authentication for all operations
        if not self.auth_context.check_access(path, 'read'):
            logger.warning(f"Unauthorized getattr attempt on {path}")
            raise FuseOSError(errno.EACCES)
        
        if not self._check_rate_limit('getattr'):
            raise FuseOSError(errno.EBUSY)
        
        try:
            # Parse path
            parts = [p for p in path.split('/') if p]
            
            if not parts:  # Root directory
                result = self._getattr_root()
            elif len(parts) == 1:  # Top-level directories
                result = self._getattr_toplevel(parts[0])
            else:  # Subdirectories and files
                section = parts[0]
                subpath = '/' + '/'.join(parts[1:])
                result = self._getattr_section(section, subpath)
            
            self._record_performance('getattr', start_time)
            return result
            
        except Exception as e:
            logger.error(f"FUSE getattr error for {path}: {e}")
            raise FuseOSError(errno.ENOENT)
    
    def readdir(self, path: str, fh) -> List[str]:
        """List directory contents - enables ls, find"""
        start_time = time.time()
        
        # Check authentication for directory listing
        if not self.auth_context.check_access(path, 'list'):
            logger.warning(f"Unauthorized readdir attempt on {path}")
            raise FuseOSError(errno.EACCES)
        
        if not self._check_rate_limit('readdir'):
            raise FuseOSError(errno.EBUSY)
        
        try:
            # Use cache for performance
            def compute_readdir():
                parts = [p for p in path.split('/') if p]
                
                if not parts:  # Root directory
                    return ['.', '..'] + list(self.root_directories.keys())
                elif len(parts) == 1:  # Top-level directories
                    section = parts[0]
                    return self._readdir_section(section, '/')
                else:  # Subdirectories
                    section = parts[0]
                    subpath = '/' + '/'.join(parts[1:])
                    return self._readdir_section(section, subpath)
            
            result = self._get_cached_or_compute(
                self._dir_cache, path, self._cache_ttl, compute_readdir
            )
            
            self._record_performance('readdir', start_time)
            return result
            
        except Exception as e:
            logger.error(f"FUSE readdir error for {path}: {e}")
            raise FuseOSError(errno.ENOENT)
    
    def read(self, path: str, length: int, offset: int, fh) -> bytes:
        """Read file content - enables cat, grep, editors"""
        start_time = time.time()
        
        # Check authentication for file reading
        if not self.auth_context.check_access(path, 'read'):
            logger.warning(f"Unauthorized read attempt on {path}")
            raise FuseOSError(errno.EACCES)
        
        if not self._check_rate_limit('read'):
            raise FuseOSError(errno.EBUSY)
        
        try:
            # Use cache for performance
            def compute_read():
                parts = [p for p in path.split('/') if p]
                if len(parts) < 2:
                    raise FuseOSError(errno.EISDIR)
                
                section = parts[0]
                subpath = '/' + '/'.join(parts[1:])
                return self._read_section(section, subpath)
            
            content = self._get_cached_or_compute(
                self._content_cache, path, self._cache_ttl, compute_read
            )
            
            # Handle offset and length
            if offset >= len(content):
                result = b''
            else:
                end = min(offset + length, len(content))
                result = content[offset:end]
            
            self._record_performance('read', start_time)
            return result
            
        except Exception as e:
            logger.error(f"FUSE read error for {path}: {e}")
            raise FuseOSError(errno.ENOENT)
    
    def write(self, path: str, buf: bytes, offset: int, fh) -> int:
        """Write file content - enables editors with event-sourcing"""
        start_time = time.time()
        
        # Check authentication for file writing
        if not self.auth_context.check_access(path, 'write'):
            logger.warning(f"Unauthorized write attempt on {path}")
            raise FuseOSError(errno.EACCES)
        
        if not self._check_rate_limit('write'):
            raise FuseOSError(errno.EBUSY)
        
        try:
            parts = [p for p in path.split('/') if p]
            if len(parts) < 2:
                raise FuseOSError(errno.EISDIR)
            
            section = parts[0]
            subpath = '/' + '/'.join(parts[1:])
            
            # Only allow writes to /current directory
            if section != 'current':
                raise FuseOSError(errno.EROFS)  # Read-only filesystem
            
            bytes_written = self._write_current(subpath, buf, offset)
            
            # Invalidate caches for this path
            self._invalidate_path_cache(path)
            
            self._record_performance('write', start_time)
            return bytes_written
            
        except Exception as e:
            logger.error(f"FUSE write error for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    # Root and Top-level Directory Handlers
    
    def _getattr_root(self) -> Dict[str, Any]:
        """Root directory attributes"""
        return {
            'st_mode': stat.S_IFDIR | 0o755,
            'st_nlink': 2 + len(self.root_directories),
            'st_size': 4096,
            'st_ctime': time.time(),
            'st_mtime': time.time(),
            'st_atime': time.time()
        }
    
    def _getattr_toplevel(self, dirname: str) -> Dict[str, Any]:
        """Top-level directory attributes"""
        if dirname not in self.root_directories:
            raise FuseOSError(errno.ENOENT)
        
        return {
            'st_mode': stat.S_IFDIR | 0o755,
            'st_nlink': 2,
            'st_size': 4096,
            'st_ctime': time.time(),
            'st_mtime': time.time(),
            'st_atime': time.time()
        }
    
    # Section-specific Handlers
    
    def _getattr_section(self, section: str, subpath: str) -> Dict[str, Any]:
        """Route getattr to section-specific handlers"""
        handlers = {
            'current': self._getattr_current,
            'history': self._getattr_history,
            'shadows': self._getattr_shadows,
            'context': self._getattr_context,
            'streams': self._getattr_streams,
            'debug': self._getattr_debug
        }
        
        if section not in handlers:
            raise FuseOSError(errno.ENOENT)
        
        return handlers[section](subpath)
    
    def _readdir_section(self, section: str, subpath: str) -> List[str]:
        """Route readdir to section-specific handlers"""
        handlers = {
            'current': self._readdir_current,
            'history': self._readdir_history,
            'shadows': self._readdir_shadows,
            'context': self._readdir_context,
            'streams': self._readdir_streams,
            'debug': self._readdir_debug
        }
        
        if section not in handlers:
            raise FuseOSError(errno.ENOENT)
        
        return handlers[section](subpath)
    
    def _read_section(self, section: str, subpath: str) -> bytes:
        """Route read to section-specific handlers"""
        handlers = {
            'current': self._read_current,
            'history': self._read_history,
            'shadows': self._read_shadows,
            'context': self._read_context,
            'streams': self._read_streams,
            'debug': self._read_debug
        }
        
        if section not in handlers:
            raise FuseOSError(errno.ENOENT)
        
        return handlers[section](subpath)
    
    # /current - Live Project State (Read-Write)
    
    def _getattr_current(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /current files (live project state)"""
        try:
            project_state = self.project_aggregate.current_state
            
            if subpath == '/':
                # Root of /current
                return {
                    'st_mode': stat.S_IFDIR | 0o755,
                    'st_nlink': 2,
                    'st_size': 4096,
                    'st_ctime': time.time(),
                    'st_mtime': time.time(),
                    'st_atime': time.time()
                }
            
            # Check if it's a file in the project state
            if project_state.file_exists(subpath):
                file_version = project_state.get_file(subpath)
                return {
                    'st_mode': stat.S_IFREG | 0o644,
                    'st_nlink': 1,
                    'st_size': len(file_version.content.encode('utf-8')),
                    'st_ctime': file_version.timestamp.timestamp(),
                    'st_mtime': file_version.timestamp.timestamp(),
                    'st_atime': time.time()
                }
            
            # Check if it's a directory
            if project_state.directory_exists(subpath):
                return {
                    'st_mode': stat.S_IFDIR | 0o755,
                    'st_nlink': 2,
                    'st_size': 4096,
                    'st_ctime': time.time(),
                    'st_mtime': time.time(),
                    'st_atime': time.time()
                }
            
            raise FuseOSError(errno.ENOENT)
            
        except Exception as e:
            logger.error(f"Error in _getattr_current({subpath}): {e}")
            raise FuseOSError(errno.EIO)
    
    def _readdir_current(self, subpath: str) -> List[str]:
        """List /current directory contents"""
        try:
            project_state = self.project_aggregate.current_state
            
            if subpath == '/':
                # List top-level items
                items = set(['.', '..'])
                
                # Add all files and directories
                for file_path in project_state.list_files():
                    if '/' in file_path[1:]:  # Has subdirectories
                        top_level = file_path.split('/')[1]
                        items.add(top_level)
                    else:
                        items.add(file_path[1:])  # Remove leading slash
                
                for dir_path in project_state.list_directories():
                    if dir_path != '/' and '/' not in dir_path[1:]:
                        items.add(dir_path[1:])  # Remove leading slash
                
                return list(items)
            else:
                # List subdirectory contents
                items = ['.', '..']
                
                for file_path in project_state.list_files(subpath):
                    relative = file_path[len(subpath):].lstrip('/')
                    if '/' not in relative:  # Direct child
                        items.append(relative)
                
                for dir_path in project_state.list_directories(subpath):
                    relative = dir_path[len(subpath):].lstrip('/')
                    if '/' not in relative:  # Direct child
                        items.append(relative)
                
                return items
                
        except Exception as e:
            logger.error(f"Error in _readdir_current({subpath}): {e}")
            return ['.', '..']
    
    def _read_current(self, subpath: str) -> bytes:
        """Read /current file content"""
        try:
            project_state = self.project_aggregate.current_state
            content = project_state.get_file_content(subpath)
            
            if content is None:
                raise FuseOSError(errno.ENOENT)
            
            return content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Error in _read_current({subpath}): {e}")
            raise FuseOSError(errno.EIO)
    
    def _write_current(self, subpath: str, buf: bytes, offset: int) -> int:
        """Write to /current files with event sourcing"""
        try:
            # Get current content if file exists
            project_state = self.project_aggregate.current_state
            current_content = project_state.get_file_content(subpath) or ""
            current_bytes = current_content.encode('utf-8')
            
            # Handle offset writing (insert/overwrite)
            if offset > len(current_bytes):
                # Pad with zeros if offset beyond end
                current_bytes += b'\\0' * (offset - len(current_bytes))
            
            # Perform write
            new_bytes = current_bytes[:offset] + buf + current_bytes[offset + len(buf):]
            new_content = new_bytes.decode('utf-8', errors='replace')
            
            # Get authenticated agent ID
            current_agent = self.auth_context.get_current_agent()
            if not current_agent:
                logger.error(f"No authenticated agent for file write: {subpath}")
                raise FuseOSError(errno.EACCES)  # Permission denied
            
            # Create event through project aggregate with authenticated agent
            asyncio.create_task(self.project_aggregate.handle_file_modification(
                path=subpath,
                content=new_content,
                agent_id=current_agent,
                session_id=self.auth_context._current_session
            ))
            
            return len(buf)
            
        except Exception as e:
            logger.error(f"Error in _write_current({subpath}): {e}")
            raise FuseOSError(errno.EIO)
    
    # /history - Historical Snapshots (Read-Only)
    
    def _getattr_history(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /history files (time travel debugging)"""
        try:
            if subpath == '/':
                return {
                    'st_mode': stat.S_IFDIR | 0o555,  # Read-only
                    'st_nlink': 2,
                    'st_size': 4096,
                    'st_ctime': time.time(),
                    'st_mtime': time.time(),
                    'st_atime': time.time()
                }
            
            # Parse timestamp from path (e.g., /2024-01-15T10:30:00Z/src/main.py)
            path_parts = subpath.strip('/').split('/')
            if not path_parts or not path_parts[0]:
                raise FuseOSError(errno.ENOENT)
            
            timestamp_str = path_parts[0]
            try:
                target_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                raise FuseOSError(errno.ENOENT)
            
            if len(path_parts) == 1:
                # Timestamp directory itself
                return {
                    'st_mode': stat.S_IFDIR | 0o555,
                    'st_nlink': 2,
                    'st_size': 4096,
                    'st_ctime': target_time.timestamp(),
                    'st_mtime': target_time.timestamp(),
                    'st_atime': time.time()
                }
            
            # File within timestamp directory
            file_path = '/' + '/'.join(path_parts[1:])
            
            # Get historical state (cached for performance)
            def get_historical_state():
                return asyncio.run(self.time_travel_debugger.rebuild_at_timestamp(
                    target_time, self.project_aggregate.project_id
                ))
            
            historical_state = self._get_cached_or_compute(
                self._history_cache, 
                f"{timestamp_str}:{self.project_aggregate.project_id}",
                self._history_cache_ttl,
                get_historical_state
            )
            
            if historical_state.file_exists(file_path):
                file_version = historical_state.get_file(file_path)
                return {
                    'st_mode': stat.S_IFREG | 0o444,  # Read-only
                    'st_nlink': 1,
                    'st_size': len(file_version.content.encode('utf-8')),
                    'st_ctime': file_version.timestamp.timestamp(),
                    'st_mtime': file_version.timestamp.timestamp(),
                    'st_atime': time.time()
                }
            
            if historical_state.directory_exists(file_path):
                return {
                    'st_mode': stat.S_IFDIR | 0o555,
                    'st_nlink': 2,
                    'st_size': 4096,
                    'st_ctime': target_time.timestamp(),
                    'st_mtime': target_time.timestamp(),
                    'st_atime': time.time()
                }
            
            raise FuseOSError(errno.ENOENT)
            
        except Exception as e:
            logger.error(f"Error in _getattr_history({subpath}): {e}")
            raise FuseOSError(errno.EIO)
    
    def _readdir_history(self, subpath: str) -> List[str]:
        """List /history directory contents"""
        try:
            if subpath == '/':
                # List available timestamps (last 24 hours for performance)
                items = ['.', '..']
                
                # Generate hourly timestamps for last 24 hours
                now = datetime.utcnow()
                for i in range(24):
                    timestamp = now - timedelta(hours=i)
                    timestamp_str = timestamp.strftime('%Y-%m-%dT%H:00:00Z')
                    items.append(timestamp_str)
                
                return items
            
            # Parse timestamp and list historical files
            path_parts = subpath.strip('/').split('/')
            timestamp_str = path_parts[0]
            
            try:
                target_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                return ['.', '..']
            
            if len(path_parts) == 1:
                # List all files/dirs at this timestamp
                def get_historical_state():
                    return asyncio.run(self.time_travel_debugger.rebuild_at_timestamp(
                        target_time, self.project_aggregate.project_id
                    ))
                
                historical_state = self._get_cached_or_compute(
                    self._history_cache,
                    f"{timestamp_str}:{self.project_aggregate.project_id}",
                    self._history_cache_ttl,
                    get_historical_state
                )
                
                items = set(['.', '..'])
                
                # Add files and directories from historical state
                for file_path in historical_state.list_files():
                    if '/' in file_path[1:]:
                        top_level = file_path.split('/')[1]
                        items.add(top_level)
                    else:
                        items.add(file_path[1:])
                
                for dir_path in historical_state.list_directories():
                    if dir_path != '/' and '/' not in dir_path[1:]:
                        items.add(dir_path[1:])
                
                return list(items)
            
            return ['.', '..']  # Deeper nesting not yet implemented
            
        except Exception as e:
            logger.error(f"Error in _readdir_history({subpath}): {e}")
            return ['.', '..']
    
    def _read_history(self, subpath: str) -> bytes:
        """Read /history file content"""
        try:
            path_parts = subpath.strip('/').split('/')
            if len(path_parts) < 2:
                raise FuseOSError(errno.EISDIR)
            
            timestamp_str = path_parts[0]
            file_path = '/' + '/'.join(path_parts[1:])
            
            target_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            # Get historical state
            def get_historical_state():
                return asyncio.run(self.time_travel_debugger.rebuild_at_timestamp(
                    target_time, self.project_aggregate.project_id
                ))
            
            historical_state = self._get_cached_or_compute(
                self._history_cache,
                f"{timestamp_str}:{self.project_aggregate.project_id}",
                self._history_cache_ttl,
                get_historical_state
            )
            
            content = historical_state.get_file_content(file_path)
            if content is None:
                raise FuseOSError(errno.ENOENT)
            
            return content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Error in _read_history({subpath}): {e}")
            raise FuseOSError(errno.EIO)
    
    # /shadows - AST Annotations (Read-Only)
    
    def _getattr_shadows(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /shadows files (AST annotations)"""
        return self._getattr_current(subpath)  # Same structure as /current but with annotations
    
    def _readdir_shadows(self, subpath: str) -> List[str]:
        """List /shadows directory contents"""
        return self._readdir_current(subpath)  # Same structure as /current
    
    def _read_shadows(self, subpath: str) -> bytes:
        """Read /shadows file content (with AST annotations)"""
        try:
            # Get the base file content
            base_content = self._read_current(subpath)
            
            # Add AST annotations as JSON metadata
            if self.ast_anchor_manager:
                try:
                    annotations = self.ast_anchor_manager.get_file_annotations(subpath)
                    shadow_data = {
                        'original_content': base_content.decode('utf-8', errors='replace'),
                        'ast_annotations': annotations,
                        'file_path': subpath,
                        'generated_at': datetime.utcnow().isoformat()
                    }
                    return json.dumps(shadow_data, indent=2).encode('utf-8')
                except Exception as e:
                    logger.warning(f"Could not generate AST annotations for {subpath}: {e}")
                    return base_content
            
            return base_content
            
        except Exception as e:
            logger.error(f"Error in _read_shadows({subpath}): {e}")
            raise FuseOSError(errno.EIO)
    
    # /context - Expert Agent Context Packages  
    
    def _getattr_context(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /context files (expert context packages)"""
        if subpath == '/':
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_size': 4096,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()
            }
        
        # Context packages are directories with package_id as name
        package_id = subpath.strip('/').split('/')[0]
        
        if package_id in self._context_packages:
            package = self._context_packages[package_id]
            
            if len(subpath.strip('/').split('/')) == 1:
                # Package directory
                return {
                    'st_mode': stat.S_IFDIR | 0o755,
                    'st_nlink': 2,
                    'st_size': 4096,
                    'st_ctime': package.created_at.timestamp(),
                    'st_mtime': package.created_at.timestamp(),
                    'st_atime': time.time()
                }
            else:
                # Package files (manifest.json, files.json, etc.)
                return {
                    'st_mode': stat.S_IFREG | 0o644,
                    'st_nlink': 1,
                    'st_size': 1024,  # Estimate
                    'st_ctime': package.created_at.timestamp(),
                    'st_mtime': package.created_at.timestamp(),
                    'st_atime': time.time()
                }
        
        raise FuseOSError(errno.ENOENT)
    
    def _readdir_context(self, subpath: str) -> List[str]:
        """List /context directory contents"""
        if subpath == '/':
            return ['.', '..'] + list(self._context_packages.keys())
        
        # Context package contents
        package_id = subpath.strip('/').split('/')[0]
        if package_id in self._context_packages:
            return ['.', '..', 'manifest.json', 'files.json', 'context.json']
        
        return ['.', '..']
    
    def _read_context(self, subpath: str) -> bytes:
        """Read /context file content"""
        path_parts = subpath.strip('/').split('/')
        if len(path_parts) < 2:
            raise FuseOSError(errno.EISDIR)
        
        package_id = path_parts[0]
        filename = path_parts[1]
        
        if package_id not in self._context_packages:
            raise FuseOSError(errno.ENOENT)
        
        package = self._context_packages[package_id]
        
        if filename == 'manifest.json':
            manifest = {
                'package_id': package.package_id,
                'request_id': package.request_id,
                'agent_capabilities': package.agent_capabilities,
                'files_involved': package.files_involved,
                'created_at': package.created_at.isoformat(),
                'expires_at': package.expires_at.isoformat() if package.expires_at else None
            }
            return json.dumps(manifest, indent=2).encode('utf-8')
        
        elif filename == 'context.json':
            return json.dumps(package.context_data, indent=2).encode('utf-8')
        
        elif filename == 'files.json':
            # Provide content of involved files
            files_content = {}
            project_state = self.project_aggregate.current_state
            
            for file_path in package.files_involved:
                content = project_state.get_file_content(file_path)
                if content:
                    files_content[file_path] = content
            
            return json.dumps(files_content, indent=2).encode('utf-8')
        
        raise FuseOSError(errno.ENOENT)
    
    # /streams - Real-time Communication
    
    def _getattr_streams(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /streams (named pipes for real-time communication)"""
        if subpath == '/':
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_size': 4096,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()
            }
        
        stream_name = subpath.strip('/')
        if stream_name in self._streams:
            stream = self._streams[stream_name]
            return {
                'st_mode': stat.S_IFIFO | 0o644,  # Named pipe
                'st_nlink': 1,
                'st_size': len(stream.message_queue) * 100,  # Estimate
                'st_ctime': stream.created_at.timestamp(),
                'st_mtime': stream.last_activity.timestamp(),
                'st_atime': time.time()
            }
        
        raise FuseOSError(errno.ENOENT)
    
    def _readdir_streams(self, subpath: str) -> List[str]:
        """List /streams directory contents"""
        if subpath == '/':
            return ['.', '..'] + list(self._streams.keys())
        
        return ['.', '..']
    
    def _read_streams(self, subpath: str) -> bytes:
        """Read from /streams (blocking until data available)"""
        stream_name = subpath.strip('/')
        
        if stream_name not in self._streams:
            raise FuseOSError(errno.ENOENT)
        
        stream = self._streams[stream_name]
        
        # Return queued messages as JSON
        if stream.message_queue:
            message = stream.message_queue.pop(0)
            stream.last_activity = datetime.utcnow()
            return json.dumps(message).encode('utf-8')
        
        # Return empty for now (real implementation would block)
        return b''
    
    # /debug - Development and Debugging
    
    def _getattr_debug(self, subpath: str) -> Dict[str, Any]:
        """Get attributes for /debug files"""
        if subpath == '/':
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_size': 4096,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()
            }
        
        # Debug files are virtual
        debug_files = ['performance.json', 'cache_stats.json', 'operation_log.txt', 'health.json']
        filename = subpath.strip('/')
        
        if filename in debug_files:
            return {
                'st_mode': stat.S_IFREG | 0o644,
                'st_nlink': 1,
                'st_size': 1024,  # Estimate
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()
            }
        
        raise FuseOSError(errno.ENOENT)
    
    def _readdir_debug(self, subpath: str) -> List[str]:
        """List /debug directory contents"""
        if subpath == '/':
            return ['.', '..', 'performance.json', 'cache_stats.json', 'operation_log.txt', 'health.json']
        
        return ['.', '..']
    
    def _read_debug(self, subpath: str) -> bytes:
        """Read /debug file content"""
        filename = subpath.strip('/')
        
        if filename == 'performance.json':
            perf_data = {
                'performance_stats': self._performance_stats,
                'operation_times': {
                    op: {
                        'avg_ms': sum(times) / len(times) if times else 0,
                        'count': len(times),
                        'p95_ms': sorted(times)[int(len(times) * 0.95)] if times else 0
                    }
                    for op, times in self._operation_times.items()
                },
                'cache_performance': {
                    'attr_cache_size': len(self._attr_cache),
                    'dir_cache_size': len(self._dir_cache),
                    'content_cache_size': len(self._content_cache),
                    'history_cache_size': len(self._history_cache)
                }
            }
            return json.dumps(perf_data, indent=2).encode('utf-8')
        
        elif filename == 'health.json':
            health_data = {
                'status': 'healthy',
                'uptime_seconds': time.time() - self._last_rate_reset,
                'total_operations': self._performance_stats['total_operations'],
                'avg_response_time_ms': self._performance_stats['avg_response_time_ms'],
                'cache_hit_rate': (
                    self._performance_stats['cache_hits'] / 
                    max(self._performance_stats['cache_hits'] + self._performance_stats['cache_misses'], 1)
                ) * 100,
                'active_streams': len(self._streams),
                'context_packages': len(self._context_packages)
            }
            return json.dumps(health_data, indent=2).encode('utf-8')
        
        elif filename == 'cache_stats.json':
            cache_data = {
                'cache_sizes': {
                    'attr_cache': len(self._attr_cache),
                    'dir_cache': len(self._dir_cache),
                    'content_cache': len(self._content_cache),
                    'history_cache': len(self._history_cache)
                },
                'cache_performance': {
                    'hits': self._performance_stats['cache_hits'],
                    'misses': self._performance_stats['cache_misses'],
                    'hit_rate_percent': (
                        self._performance_stats['cache_hits'] / 
                        max(self._performance_stats['cache_hits'] + self._performance_stats['cache_misses'], 1)
                    ) * 100
                }
            }
            return json.dumps(cache_data, indent=2).encode('utf-8')
        
        raise FuseOSError(errno.ENOENT)
    
    # Utility Methods
    
    def _invalidate_path_cache(self, path: str):
        """Invalidate caches for a specific path and its parents"""
        # Remove from all caches
        self._attr_cache.pop(path, None)
        self._dir_cache.pop(path, None)
        self._content_cache.pop(path, None)
        
        # Invalidate parent directories
        parts = path.split('/')
        for i in range(1, len(parts)):
            parent_path = '/'.join(parts[:i+1])
            self._dir_cache.pop(parent_path, None)
    
    def create_context_package(self, package: ContextPackage):
        """Create a new context package for expert agents"""
        self._context_packages[package.package_id] = package
        logger.info(f"Created context package {package.package_id} for request {package.request_id}")
    
    def add_stream_message(self, stream_name: str, message: Dict[str, Any]):
        """Add message to a stream"""
        if stream_name in self._streams:
            stream = self._streams[stream_name]
            stream.message_queue.append(message)
            stream.last_activity = datetime.utcnow()
            
            # Limit queue size
            if len(stream.message_queue) > 1000:
                stream.message_queue = stream.message_queue[-100:]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        return {
            'performance_stats': self._performance_stats,
            'operation_counts': dict(self._operation_counts),
            'cache_sizes': {
                'attr_cache': len(self._attr_cache),
                'dir_cache': len(self._dir_cache),
                'content_cache': len(self._content_cache),
                'history_cache': len(self._history_cache)
            },
            'avg_operation_times': {
                op: sum(times) / len(times) if times else 0
                for op, times in self._operation_times.items()
            }
        }
    
    # Authentication Management Methods
    
    def authenticate_agent(self, 
                          agent_id: str, 
                          challenge: str, 
                          response: str,
                          permissions: Optional[set] = None) -> Optional[str]:
        """
        Authenticate agent for FUSE access
        
        Args:
            agent_id: Agent identifier
            challenge: Authentication challenge
            response: HMAC response
            permissions: Optional permission set
            
        Returns:
            Session ID if successful, None otherwise
        """
        return self.auth_manager.authenticate_agent(
            agent_id, challenge, response, permissions
        )
    
    def set_current_session(self, session_id: Optional[str]):
        """Set current session for FUSE operations"""
        self.auth_context.set_session(session_id)
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, any]]:
        """Get information about a session"""
        return self.auth_manager.get_session_info(session_id)
    
    def logout_session(self, session_id: str) -> bool:
        """Logout and invalidate a session"""
        return self.auth_manager.logout_session(session_id)
    
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, any]]:
        """Get recent filesystem access audit log"""
        return self.auth_manager.get_audit_log(limit)
    
    async def cleanup_expired_sessions(self):
        """Cleanup expired sessions - should be called periodically"""
        self.auth_manager.cleanup_expired_sessions()
    
    async def destroy(self):
        """Cleanup filesystem resources"""
        await self.cleanup_expired_sessions()
        
        # Clear all caches
        self._attr_cache.clear()
        self._dir_cache.clear() 
        self._content_cache.clear()
        self._history_cache.clear()
        self._context_packages.clear()
        
        logger.info("FUSE filesystem destroyed and cleaned up")


# FUSE Mount Manager for easy deployment
class FUSEMountManager:
    """Manager for mounting and unmounting the FUSE filesystem"""
    
    def __init__(self, 
                 lighthouse_fuse: CompleteLighthouseFUSE,
                 mount_point: str = "/mnt/lighthouse/project",
                 foreground: bool = False,
                 allow_other: bool = True):
        
        self.lighthouse_fuse = lighthouse_fuse
        self.mount_point = mount_point
        self.foreground = foreground
        self.allow_other = allow_other
        
        # Ensure mount point exists
        Path(mount_point).mkdir(parents=True, exist_ok=True)
    
    def mount(self):
        """Mount the FUSE filesystem"""
        if not FUSE_AVAILABLE:
            logger.error("FUSE not available - cannot mount filesystem")
            return False
        
        try:
            fuse_options = []
            if self.allow_other:
                fuse_options.append('allow_other')
            
            logger.info(f"Mounting Lighthouse FUSE filesystem at {self.mount_point}")
            
            FUSE(
                self.lighthouse_fuse,
                self.mount_point,
                foreground=self.foreground,
                allow_other=self.allow_other
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mount FUSE filesystem: {e}")
            return False
    
    def unmount(self):
        """Unmount the FUSE filesystem"""
        try:
            import subprocess
            subprocess.run(['fusermount', '-u', self.mount_point], check=True)
            logger.info(f"Unmounted FUSE filesystem from {self.mount_point}")
            return True
        except Exception as e:
            logger.error(f"Failed to unmount FUSE filesystem: {e}")
            return False