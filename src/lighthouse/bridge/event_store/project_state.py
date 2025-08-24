"""
Project State Management

Current state reconstruction from events. Maintains the live project state
by applying events in sequence, enabling time travel and state queries.

Features:
- Immutable state transitions
- File content tracking with version history
- Directory structure management
- Agent session tracking
- Conflict detection and resolution
"""

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from lighthouse.event_store.models import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class FileVersion:
    """Version information for a file"""
    
    content: str
    content_hash: str
    size: int
    timestamp: datetime
    agent_id: str
    sequence: int
    mime_type: Optional[str] = None
    encoding: str = "utf-8"
    
    @classmethod
    def from_event(cls, event: Event) -> 'FileVersion':
        """Create file version from event"""
        return cls(
            content=event.data.get('content', ''),
            content_hash=event.data.get('content_hash', ''),
            size=event.data.get('size', 0),
            timestamp=event.timestamp,
            agent_id=event.source_agent or event.metadata.get('agent_id', 'unknown'),
            sequence=event.sequence or 0,
            mime_type=event.data.get('mime_type'),
            encoding=event.data.get('encoding', 'utf-8')
        )
    
    def get_preview(self, max_length: int = 100) -> str:
        """Get content preview for display"""
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length-3] + "..."


@dataclass
class DirectoryInfo:
    """Information about a directory"""
    
    path: str
    created_at: datetime
    created_by: str
    last_modified: datetime
    children: Set[str] = field(default_factory=set)
    
    def add_child(self, name: str):
        """Add child file/directory"""
        self.children.add(name)
    
    def remove_child(self, name: str):
        """Remove child file/directory"""
        self.children.discard(name)


@dataclass
class AgentSession:
    """Information about an agent session"""
    
    session_id: str
    agent_id: str
    agent_type: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    file_modifications: List[str] = field(default_factory=list)
    validation_requests: int = 0
    
    @property
    def is_active(self) -> bool:
        """Check if session is still active"""
        return self.ended_at is None
    
    @property
    def duration(self) -> Optional[float]:
        """Get session duration in seconds"""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None


class ProjectState:
    """Current project state derived from events"""
    
    def __init__(self, project_id: str):
        """
        Initialize project state
        
        Args:
            project_id: Unique project identifier
        """
        self.project_id = project_id
        
        # File system state
        self.files: Dict[str, FileVersion] = {}
        self.directories: Dict[str, DirectoryInfo] = {}
        self.deleted_files: Set[str] = set()
        self.deleted_directories: Set[str] = set()
        
        # File history tracking
        self.file_history: Dict[str, List[FileVersion]] = defaultdict(list)
        
        # Agent tracking
        self.active_sessions: Dict[str, AgentSession] = {}
        self.session_history: List[AgentSession] = []
        
        # Validation tracking
        self.validation_requests: Dict[str, Dict[str, Any]] = {}
        self.validation_decisions: Dict[str, str] = {}
        
        # State metadata
        self.last_event_sequence = 0
        self.last_updated = datetime.utcnow()
        self.version = 0
        
        # Statistics
        self.total_file_operations = 0
        self.total_validation_requests = 0
        
        # Initialize root directory
        self.directories['/'] = DirectoryInfo(
            path='/',
            created_at=datetime.utcnow(),
            created_by='system',
            last_modified=datetime.utcnow()
        )
    
    def apply_event(self, event: Event):
        """
        Apply an event to update the project state
        
        Args:
            event: Event to apply
        """
        if event.sequence is not None and event.sequence <= self.last_event_sequence:
            logger.warning(f"Event {event.event_id} is out of order or duplicate")
            return
        
        try:
            # Route event to appropriate handler
            if event.event_type == EventType.FILE_CREATED:
                self._handle_file_created(event)
            elif event.event_type == EventType.FILE_MODIFIED:
                self._handle_file_modified(event)
            elif event.event_type == EventType.FILE_DELETED:
                self._handle_file_deleted(event)
            elif event.event_type == EventType.FILE_MOVED:
                self._handle_file_moved(event)
            elif event.event_type == EventType.FILE_COPIED:
                self._handle_file_copied(event)
            elif event.event_type == EventType.DIRECTORY_CREATED:
                self._handle_directory_created(event)
            elif event.event_type == EventType.DIRECTORY_DELETED:
                self._handle_directory_deleted(event)
            elif event.event_type == EventType.DIRECTORY_MOVED:
                self._handle_directory_moved(event)
            elif event.event_type == EventType.AGENT_SESSION_STARTED:
                self._handle_agent_session_started(event)
            elif event.event_type == EventType.AGENT_SESSION_ENDED:
                self._handle_agent_session_ended(event)
            elif event.event_type == EventType.VALIDATION_REQUEST_SUBMITTED:
                self._handle_validation_request(event)
            elif event.event_type == EventType.VALIDATION_DECISION_MADE:
                self._handle_validation_decision(event)
            else:
                logger.debug(f"Unhandled event type: {event.event_type}")
            
            # Update metadata
            if event.sequence is not None:
                self.last_event_sequence = event.sequence
            self.last_updated = event.timestamp
            self.version += 1
            
        except Exception as e:
            logger.error(f"Failed to apply event {event.event_id}: {e}")
            raise
    
    def _handle_file_created(self, event: Event):
        """Handle file creation event"""
        path = event.data['path']
        
        # Create file version
        file_version = FileVersion.from_event(event)
        self.files[path] = file_version
        self.file_history[path].append(file_version)
        
        # Remove from deleted files if it was previously deleted
        self.deleted_files.discard(path)
        
        # Update directory structure
        self._update_directory_structure(path, event)
        
        # Update session tracking
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        session_id = event.metadata.get('session_id')
        self._track_file_modification(agent_id, session_id, path)
        
        self.total_file_operations += 1
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"File created: {path} by {agent_id}")
    
    def _handle_file_modified(self, event: Event):
        """Handle file modification event"""
        path = event.data['path']
        
        # Create new file version
        file_version = FileVersion.from_event(event)
        self.files[path] = file_version
        self.file_history[path].append(file_version)
        
        # Update directory structure (in case file was created)
        self._update_directory_structure(path, event)
        
        # Update session tracking
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        session_id = event.metadata.get('session_id')
        self._track_file_modification(agent_id, session_id, path)
        
        self.total_file_operations += 1
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"File modified: {path} by {agent_id}")
    
    def _handle_file_deleted(self, event: Event):
        """Handle file deletion event"""
        path = event.data['path']
        
        # Remove from current files
        if path in self.files:
            del self.files[path]
        
        # Add to deleted files
        self.deleted_files.add(path)
        
        # Update directory structure
        self._remove_from_directory_structure(path)
        
        # Update session tracking
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        session_id = event.metadata.get('session_id')
        self._track_file_modification(agent_id, session_id, path)
        
        self.total_file_operations += 1
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"File deleted: {path} by {agent_id}")
    
    def _handle_file_moved(self, event: Event):
        """Handle file move event"""
        old_path = event.data['old_path']
        new_path = event.data['new_path']
        
        # Move file data
        if old_path in self.files:
            file_version = self.files[old_path]
            del self.files[old_path]
            self.files[new_path] = file_version
            
            # Update file history
            self.file_history[new_path] = self.file_history.pop(old_path, [])
        
        # Update directory structure
        self._remove_from_directory_structure(old_path)
        self._update_directory_structure(new_path, event)
        
        self.total_file_operations += 1
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"File moved: {old_path} -> {new_path} by {agent_id}")
    
    def _handle_file_copied(self, event: Event):
        """Handle file copy event"""
        source_path = event.data['source_path']
        dest_path = event.data['dest_path']
        
        # Copy file data if source exists
        if source_path in self.files:
            source_version = self.files[source_path]
            
            # Create new file version for destination
            agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
            dest_version = FileVersion(
                content=source_version.content,
                content_hash=source_version.content_hash,
                size=source_version.size,
                timestamp=event.timestamp,
                agent_id=agent_id,
                sequence=event.sequence or 0,
                mime_type=source_version.mime_type,
                encoding=source_version.encoding
            )
            
            self.files[dest_path] = dest_version
            self.file_history[dest_path].append(dest_version)
            
            # Update directory structure
            self._update_directory_structure(dest_path, event)
        
        self.total_file_operations += 1
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"File copied: {source_path} -> {dest_path} by {agent_id}")
    
    def _handle_directory_created(self, event: Event):
        """Handle directory creation event"""
        path = event.data['path']
        
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        directory_info = DirectoryInfo(
            path=path,
            created_at=event.timestamp,
            created_by=agent_id,
            last_modified=event.timestamp
        )
        
        self.directories[path] = directory_info
        self.deleted_directories.discard(path)
        
        # Update parent directory
        parent_path = str(Path(path).parent)
        if parent_path in self.directories:
            self.directories[parent_path].add_child(Path(path).name)
        
        logger.debug(f"Directory created: {path} by {agent_id}")
    
    def _handle_directory_deleted(self, event: Event):
        """Handle directory deletion event"""
        path = event.data['path']
        
        if path in self.directories:
            del self.directories[path]
        
        self.deleted_directories.add(path)
        
        # Remove from parent directory
        parent_path = str(Path(path).parent)
        if parent_path in self.directories:
            self.directories[parent_path].remove_child(Path(path).name)
        
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"Directory deleted: {path} by {agent_id}")
    
    def _handle_directory_moved(self, event: Event):
        """Handle directory move event"""
        old_path = event.data['old_path']
        new_path = event.data['new_path']
        
        if old_path in self.directories:
            directory_info = self.directories[old_path]
            del self.directories[old_path]
            
            # Update directory info
            directory_info.path = new_path
            directory_info.last_modified = event.timestamp
            self.directories[new_path] = directory_info
            
            # Update parent directories
            old_parent = str(Path(old_path).parent)
            new_parent = str(Path(new_path).parent)
            
            if old_parent in self.directories:
                self.directories[old_parent].remove_child(Path(old_path).name)
            
            if new_parent in self.directories:
                self.directories[new_parent].add_child(Path(new_path).name)
        
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        logger.debug(f"Directory moved: {old_path} -> {new_path} by {agent_id}")
    
    def _handle_agent_session_started(self, event: Event):
        """Handle agent session start event"""
        session_id = event.data['session_id']
        
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        session = AgentSession(
            session_id=session_id,
            agent_id=agent_id,
            agent_type=event.data.get('agent_type', 'unknown'),
            started_at=event.timestamp
        )
        
        self.active_sessions[session_id] = session
        logger.debug(f"Agent session started: {session_id} for {agent_id}")
    
    def _handle_agent_session_ended(self, event: Event):
        """Handle agent session end event"""
        session_id = event.data['session_id']
        
        if session_id in self.active_sessions:
            session = self.active_sessions.pop(session_id)
            session.ended_at = event.timestamp
            self.session_history.append(session)
            
            agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
            logger.debug(f"Agent session ended: {session_id} for {agent_id}")
    
    def _handle_validation_request(self, event: Event):
        """Handle validation request event"""
        request_id = event.data['request_id']
        
        agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
        self.validation_requests[request_id] = {
            'tool_name': event.data.get('tool_name'),
            'command_hash': event.data.get('command_hash'),
            'agent_id': agent_id,
            'timestamp': event.timestamp,
            'status': 'pending'
        }
        
        # Update session validation count
        session_id = event.metadata.get('session_id')
        if session_id and session_id in self.active_sessions:
            self.active_sessions[session_id].validation_requests += 1
        
        self.total_validation_requests += 1
        logger.debug(f"Validation request: {request_id} from {agent_id}")
    
    def _handle_validation_decision(self, event: Event):
        """Handle validation decision event"""
        request_id = event.data['request_id']
        decision = event.data['decision']
        
        self.validation_decisions[request_id] = decision
        
        if request_id in self.validation_requests:
            self.validation_requests[request_id]['status'] = 'completed'
            self.validation_requests[request_id]['decision'] = decision
        
        logger.debug(f"Validation decision: {request_id} -> {decision}")
    
    def _update_directory_structure(self, file_path: str, event: Event):
        """Update directory structure for a file path"""
        path = Path(file_path)
        
        # Ensure all parent directories exist
        current_path = Path('/')
        
        for part in path.parts[1:-1]:  # Skip root and filename
            current_path = current_path / part
            current_path_str = str(current_path)
            
            if current_path_str not in self.directories:
                agent_id = event.source_agent or event.metadata.get('agent_id', 'unknown')
                self.directories[current_path_str] = DirectoryInfo(
                    path=current_path_str,
                    created_at=event.timestamp,
                    created_by=agent_id,
                    last_modified=event.timestamp
                )
            
            # Add to parent directory
            parent_path = str(current_path.parent)
            if parent_path in self.directories:
                self.directories[parent_path].add_child(current_path.name)
        
        # Add file to its parent directory
        parent_path = str(path.parent)
        if parent_path in self.directories:
            self.directories[parent_path].add_child(path.name)
            self.directories[parent_path].last_modified = event.timestamp
    
    def _remove_from_directory_structure(self, file_path: str):
        """Remove file from directory structure"""
        path = Path(file_path)
        parent_path = str(path.parent)
        
        if parent_path in self.directories:
            self.directories[parent_path].remove_child(path.name)
    
    def _track_file_modification(self, agent_id: str, session_id: Optional[str], file_path: str):
        """Track file modifications for agent sessions"""
        if session_id and session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            if file_path not in session.file_modifications:
                session.file_modifications.append(file_path)
    
    def get_file(self, path: str) -> Optional[FileVersion]:
        """Get current version of a file"""
        return self.files.get(path)
    
    def get_file_content(self, path: str) -> Optional[str]:
        """Get current content of a file"""
        file_version = self.get_file(path)
        return file_version.content if file_version else None
    
    def get_file_hash(self, path: str) -> Optional[str]:
        """Get content hash of a file"""
        file_version = self.get_file(path)
        return file_version.content_hash if file_version else None
    
    def get_file_history(self, path: str) -> List[FileVersion]:
        """Get version history for a file"""
        return self.file_history.get(path, [])
    
    def file_exists(self, path: str) -> bool:
        """Check if a file exists"""
        return path in self.files
    
    def directory_exists(self, path: str) -> bool:
        """Check if a directory exists"""
        return path in self.directories
    
    def list_files(self, directory_path: str = '/') -> List[str]:
        """List all files in the project or specific directory"""
        if directory_path == '/':
            return list(self.files.keys())
        
        # Filter files by directory
        files = []
        for file_path in self.files.keys():
            if file_path.startswith(directory_path.rstrip('/') + '/'):
                files.append(file_path)
        
        return files
    
    def list_directories(self, parent_path: str = '/') -> List[str]:
        """List directories under a parent path"""
        directories = []
        
        for dir_path in self.directories.keys():
            if dir_path == parent_path:
                continue
            
            # Check if this directory is directly under parent_path
            if str(Path(dir_path).parent) == parent_path:
                directories.append(dir_path)
        
        return directories
    
    def get_project_stats(self) -> Dict[str, Any]:
        """Get project statistics"""
        return {
            'total_files': len(self.files),
            'total_directories': len(self.directories),
            'deleted_files': len(self.deleted_files),
            'deleted_directories': len(self.deleted_directories),
            'total_file_operations': self.total_file_operations,
            'total_validation_requests': self.total_validation_requests,
            'active_sessions': len(self.active_sessions),
            'completed_sessions': len(self.session_history),
            'last_updated': self.last_updated.isoformat(),
            'version': self.version,
            'last_event_sequence': self.last_event_sequence
        }
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """Get agent activity statistics"""
        agent_stats = defaultdict(lambda: {
            'file_modifications': 0,
            'validation_requests': 0,
            'active_sessions': 0,
            'total_sessions': 0
        })
        
        # Count active sessions
        for session in self.active_sessions.values():
            agent_stats[session.agent_id]['active_sessions'] += 1
            agent_stats[session.agent_id]['file_modifications'] += len(session.file_modifications)
            agent_stats[session.agent_id]['validation_requests'] += session.validation_requests
        
        # Count completed sessions
        for session in self.session_history:
            agent_stats[session.agent_id]['total_sessions'] += 1
            agent_stats[session.agent_id]['file_modifications'] += len(session.file_modifications)
            agent_stats[session.agent_id]['validation_requests'] += session.validation_requests
        
        return dict(agent_stats)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert project state to dictionary for serialization"""
        return {
            'project_id': self.project_id,
            'files': {
                path: {
                    'content': version.content,
                    'content_hash': version.content_hash,
                    'size': version.size,
                    'timestamp': version.timestamp.isoformat(),
                    'agent_id': version.agent_id,
                    'sequence': version.sequence
                }
                for path, version in self.files.items()
            },
            'directories': {
                path: {
                    'created_at': info.created_at.isoformat(),
                    'created_by': info.created_by,
                    'last_modified': info.last_modified.isoformat(),
                    'children': list(info.children)
                }
                for path, info in self.directories.items()
            },
            'deleted_files': list(self.deleted_files),
            'deleted_directories': list(self.deleted_directories),
            'stats': self.get_project_stats()
        }