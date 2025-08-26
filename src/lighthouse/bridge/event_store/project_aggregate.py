"""
Project Aggregate

Business logic for project operations in the event-sourced architecture.
Handles command validation, state transitions, and event generation.

The ProjectAggregate enforces business rules and maintains consistency
while generating events that represent state changes.

Features:
- Command validation and business rule enforcement
- Event generation for all state changes
- Optimistic concurrency control
- Conflict detection and resolution
- Integration with validation bridge
"""

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from lighthouse.event_store.models import Event, EventType
from .project_state import ProjectState
from ..speed_layer.models import ValidationRequest, ValidationDecision

logger = logging.getLogger(__name__)


class BusinessRuleViolation(Exception):
    """Exception raised when business rules are violated"""
    
    def __init__(self, message: str, rule_name: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.rule_name = rule_name
        self.context = context or {}


class ConcurrencyConflict(Exception):
    """Exception raised when concurrent modifications conflict"""
    
    def __init__(self, message: str, expected_sequence: int, actual_sequence: int):
        super().__init__(message)
        self.expected_sequence = expected_sequence
        self.actual_sequence = actual_sequence


class ProjectAggregate:
    """
    Aggregate root for project operations
    
    Handles all business logic for project modifications and generates
    events for state changes. Integrates with the validation bridge
    for security enforcement.
    """
    
    def __init__(self, project_id: str):
        """
        Initialize project aggregate
        
        Args:
            project_id: Unique identifier for the project
        """
        self.project_id = project_id
        self.current_state = ProjectState(project_id)
        self.uncommitted_events: List[Event] = []
        self.version = 0
        
        # Business rules configuration
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.allowed_file_extensions = {
            '.py', '.js', '.ts', '.go', '.rs', '.java', '.cpp', '.c', '.h',
            '.html', '.css', '.md', '.txt', '.json', '.yaml', '.yml',
            '.toml', '.ini', '.cfg', '.conf', '.sh', '.bat', '.ps1'
        }
        self.protected_paths = {
            '/.git', '/node_modules', '/venv', '/env', '/dist', '/build',
            '/__pycache__', '/.pytest_cache', '/.mypy_cache'
        }
        
        # Validation bridge integration (will be injected)
        self.validation_bridge: Optional[Any] = None
    
    def set_validation_bridge(self, bridge: Any):
        """Set validation bridge for command validation"""
        self.validation_bridge = bridge
    
    def load_from_events(self, events: List[Event]):
        """
        Rebuild aggregate state from event history
        
        Args:
            events: List of events in chronological order
        """
        for event in events:
            self.current_state.apply_event(event)
            self.version = max(self.version, event.sequence)
        
        logger.info(f"Loaded aggregate {self.project_id} from {len(events)} events")
    
    def get_uncommitted_events(self) -> List[Event]:
        """Get events that haven't been persisted yet"""
        return self.uncommitted_events.copy()
    
    def mark_events_as_committed(self):
        """Mark all uncommitted events as committed"""
        self.uncommitted_events.clear()
    
    async def handle_file_modification(self, 
                                     path: str, 
                                     content: str, 
                                     agent_id: str,
                                     session_id: Optional[str] = None,
                                     expected_version: Optional[int] = None) -> Event:
        """
        Handle file modification command
        
        Args:
            path: File path to modify
            content: New file content
            agent_id: ID of the agent making the change
            session_id: Optional session ID for tracking
            expected_version: Expected aggregate version for concurrency control
            
        Returns:
            Generated event
            
        Raises:
            BusinessRuleViolation: If business rules are violated
            ConcurrencyConflict: If concurrent modification detected
        """
        
        # Concurrency check
        if expected_version is not None and expected_version != self.version:
            raise ConcurrencyConflict(
                f"Concurrent modification detected. Expected version {expected_version}, "
                f"actual version {self.version}",
                expected_version,
                self.version
            )
        
        # Validate through bridge if available
        await self._validate_file_operation(path, content, agent_id, session_id, "modify")
        
        # Apply business rules
        self._validate_file_modification_rules(path, content, agent_id)
        
        # Get previous file info for the event
        previous_hash = None
        if self.current_state.file_exists(path):
            previous_hash = self.current_state.get_file_hash(path)
        
        # Create event data with content hash
        content_bytes = content.encode('utf-8')
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        
        # Determine if this is creation or modification
        event_type = EventType.FILE_CREATED if previous_hash is None else EventType.FILE_MODIFIED
        
        # Generate event
        event = self._create_event(
            event_type=event_type,
            data={
                'path': path,
                'content': content,
                'previous_hash': previous_hash,
                'content_hash': content_hash,
                'size': len(content_bytes),
                'mime_type': None,
                'encoding': 'utf-8'
            },
            agent_id=agent_id,
            session_id=session_id,
            metadata={
                'operation': 'file_modification',
                'file_size': len(content_bytes),
                'previous_exists': previous_hash is not None
            }
        )
        
        # Apply event to current state
        self.current_state.apply_event(event)
        
        # Add to uncommitted events
        self.uncommitted_events.append(event)
        
        logger.info(f"File {event_type.value}: {path} by {agent_id}")
        
        return event
    
    async def handle_file_deletion(self,
                                 path: str,
                                 agent_id: str,
                                 session_id: Optional[str] = None,
                                 expected_version: Optional[int] = None) -> Event:
        """
        Handle file deletion command
        
        Args:
            path: File path to delete
            agent_id: ID of the agent making the change
            session_id: Optional session ID for tracking
            expected_version: Expected aggregate version for concurrency control
            
        Returns:
            Generated event
        """
        
        # Concurrency check
        if expected_version is not None and expected_version != self.version:
            raise ConcurrencyConflict(
                f"Concurrent modification detected. Expected version {expected_version}, "
                f"actual version {self.version}",
                expected_version,
                self.version
            )
        
        # Validate through bridge if available
        await self._validate_file_operation(path, None, agent_id, session_id, "delete")
        
        # Apply business rules
        self._validate_file_deletion_rules(path, agent_id)
        
        # Check that file exists
        if not self.current_state.file_exists(path):
            raise BusinessRuleViolation(
                f"Cannot delete non-existent file: {path}",
                "file_exists_check"
            )
        
        # Generate event
        event = self._create_event(
            event_type=EventType.FILE_DELETED,
            data={'path': path},
            agent_id=agent_id,
            session_id=session_id,
            metadata={
                'operation': 'file_deletion',
                'previous_hash': self.current_state.get_file_hash(path)
            }
        )
        
        # Apply event to current state
        self.current_state.apply_event(event)
        
        # Add to uncommitted events
        self.uncommitted_events.append(event)
        
        logger.info(f"File deleted: {path} by {agent_id}")
        
        return event
    
    async def handle_file_move(self,
                             old_path: str,
                             new_path: str,
                             agent_id: str,
                             session_id: Optional[str] = None,
                             expected_version: Optional[int] = None) -> Event:
        """Handle file move command"""
        
        # Concurrency check
        if expected_version is not None and expected_version != self.version:
            raise ConcurrencyConflict(
                f"Concurrent modification detected",
                expected_version,
                self.version
            )
        
        # Validate through bridge
        await self._validate_file_operation(old_path, None, agent_id, session_id, "move_from")
        await self._validate_file_operation(new_path, None, agent_id, session_id, "move_to")
        
        # Apply business rules
        self._validate_file_move_rules(old_path, new_path, agent_id)
        
        # Generate event
        event = self._create_event(
            event_type=EventType.FILE_MOVED,
            data={
                'old_path': old_path,
                'new_path': new_path
            },
            agent_id=agent_id,
            session_id=session_id,
            metadata={'operation': 'file_move'}
        )
        
        # Apply and commit
        self.current_state.apply_event(event)
        self.uncommitted_events.append(event)
        
        logger.info(f"File moved: {old_path} -> {new_path} by {agent_id}")
        
        return event
    
    async def handle_directory_creation(self,
                                      path: str,
                                      agent_id: str,
                                      session_id: Optional[str] = None,
                                      expected_version: Optional[int] = None) -> Event:
        """Handle directory creation command"""
        
        # Concurrency check
        if expected_version is not None and expected_version != self.version:
            raise ConcurrencyConflict(
                f"Concurrent modification detected",
                expected_version,
                self.version
            )
        
        # Validate through bridge
        await self._validate_file_operation(path, None, agent_id, session_id, "mkdir")
        
        # Apply business rules
        self._validate_directory_creation_rules(path, agent_id)
        
        # Generate event
        event = self._create_event(
            event_type=EventType.DIRECTORY_CREATED,
            data={'path': path},
            agent_id=agent_id,
            session_id=session_id,
            metadata={'operation': 'directory_creation'}
        )
        
        # Apply and commit
        self.current_state.apply_event(event)
        self.uncommitted_events.append(event)
        
        logger.info(f"Directory created: {path} by {agent_id}")
        
        return event
    
    async def handle_validation_request(self,
                                      request_id: str,
                                      tool_name: str,
                                      tool_input: Dict[str, Any],
                                      agent_id: str,
                                      session_id: Optional[str] = None) -> Event:
        """Handle validation request submission"""
        
        # Generate event
        event = self._create_event(
            event_type=EventType.VALIDATION_REQUEST_SUBMITTED,
            data={
                'request_id': request_id,
                'tool_name': tool_name,
                'tool_input': tool_input,
                'command_hash': self._hash_command(tool_name, tool_input)
            },
            agent_id=agent_id,
            session_id=session_id,
            metadata={
                'operation': 'validation_request',
                'tool_name': tool_name
            }
        )
        
        # Apply and commit
        self.current_state.apply_event(event)
        self.uncommitted_events.append(event)
        
        return event
    
    async def handle_validation_decision(self,
                                       request_id: str,
                                       decision: str,
                                       reason: str,
                                       validator_id: str,
                                       session_id: Optional[str] = None) -> Event:
        """Handle validation decision"""
        
        # Generate event
        event = self._create_event(
            event_type=EventType.VALIDATION_DECISION_MADE,
            data={
                'request_id': request_id,
                'decision': decision,
                'reason': reason,
                'validator_id': validator_id
            },
            agent_id=validator_id,
            session_id=session_id,
            metadata={
                'operation': 'validation_decision',
                'decision': decision
            }
        )
        
        # Apply and commit
        self.current_state.apply_event(event)
        self.uncommitted_events.append(event)
        
        return event
    
    async def start_agent_session(self,
                                agent_id: str,
                                agent_type: str = "unknown",
                                session_metadata: Optional[Dict[str, Any]] = None) -> Tuple[str, Event]:
        """Start a new agent session"""
        
        session_id = str(uuid.uuid4())
        
        # Generate event
        event = self._create_event(
            event_type=EventType.AGENT_SESSION_STARTED,
            data={
                'session_id': session_id,
                'agent_type': agent_type,
                'metadata': session_metadata or {}
            },
            agent_id=agent_id,
            session_id=session_id,
            metadata={'operation': 'session_start'}
        )
        
        # Apply and commit
        self.current_state.apply_event(event)
        self.uncommitted_events.append(event)
        
        logger.info(f"Agent session started: {session_id} for {agent_id}")
        
        return session_id, event
    
    async def end_agent_session(self,
                              session_id: str,
                              agent_id: str,
                              session_summary: Optional[Dict[str, Any]] = None) -> Event:
        """End an agent session"""
        
        # Generate event
        event = self._create_event(
            event_type=EventType.AGENT_SESSION_ENDED,
            data={
                'session_id': session_id,
                'summary': session_summary or {}
            },
            agent_id=agent_id,
            session_id=session_id,
            metadata={'operation': 'session_end'}
        )
        
        # Apply and commit
        self.current_state.apply_event(event)
        self.uncommitted_events.append(event)
        
        logger.info(f"Agent session ended: {session_id} for {agent_id}")
        
        return event
    
    def _create_event(self,
                     event_type: EventType,
                     data: Dict[str, Any],
                     agent_id: str,
                     session_id: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> Event:
        """Create a new event with proper sequencing"""
        
        self.version += 1
        
        event = Event(
            event_type=event_type,
            aggregate_id=self.project_id,
            sequence=self.version,
            data=data,
            metadata=metadata or {},
            source_agent=agent_id,
            source_component="bridge_aggregate"
        )
        
        # Add session_id to metadata if provided
        if session_id:
            event.metadata["session_id"] = session_id
            event.metadata["agent_id"] = agent_id
        
        # Generate content hash and store in metadata
        content = f"{event_type.value}:{self.project_id}:{str(sorted(data.items()))}"
        event.metadata["content_hash"] = hashlib.sha256(content.encode()).hexdigest()
        
        return event
    
    async def _validate_file_operation(self,
                                     path: str,
                                     content: Optional[str],
                                     agent_id: str,
                                     session_id: Optional[str],
                                     operation: str):
        """Validate file operation through the validation bridge"""
        
        if not self.validation_bridge:
            return  # No validation bridge configured
        
        # Create validation request
        tool_input = {'file_path': path}
        if content is not None:
            tool_input['content'] = content[:1000]  # Truncate for validation
        
        validation_request = ValidationRequest(
            tool_name="Edit" if operation in ["modify", "create"] else "Bash",
            tool_input=tool_input,
            agent_id=agent_id,
            session_id=session_id,
            context={'operation': operation, 'aggregate_id': self.project_id}
        )
        
        # Get validation result
        result = await self.validation_bridge.validate_request(validation_request)
        
        # Check result
        if result.decision == ValidationDecision.BLOCKED:
            raise BusinessRuleViolation(
                f"File operation blocked by validation: {result.reason}",
                "validation_bridge_blocked",
                {'validation_result': result.to_dict()}
            )
    
    def _validate_file_modification_rules(self, path: str, content: str, agent_id: str):
        """Apply business rules for file modifications"""
        
        # Check file size
        content_bytes = content.encode('utf-8')
        if len(content_bytes) > self.max_file_size:
            raise BusinessRuleViolation(
                f"File too large: {len(content_bytes)} bytes (max: {self.max_file_size})",
                "max_file_size",
                {'file_size': len(content_bytes), 'max_size': self.max_file_size}
            )
        
        # Check file extension
        file_path = Path(path)
        if file_path.suffix and file_path.suffix not in self.allowed_file_extensions:
            raise BusinessRuleViolation(
                f"File extension not allowed: {file_path.suffix}",
                "allowed_file_extensions",
                {'extension': file_path.suffix, 'allowed': list(self.allowed_file_extensions)}
            )
        
        # Check protected paths
        for protected_path in self.protected_paths:
            if path.startswith(protected_path):
                raise BusinessRuleViolation(
                    f"Cannot modify protected path: {path}",
                    "protected_paths",
                    {'path': path, 'protected_path': protected_path}
                )
        
        # Check for suspicious content patterns
        suspicious_patterns = [
            'rm -rf /', 'sudo rm', 'chmod 777', 'eval(', '__import__',
            'exec(', 'system(', 'shell_exec', 'passthru'
        ]
        
        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                raise BusinessRuleViolation(
                    f"Suspicious content pattern detected: {pattern}",
                    "suspicious_content",
                    {'pattern': pattern, 'path': path}
                )
    
    def _validate_file_deletion_rules(self, path: str, agent_id: str):
        """Apply business rules for file deletions"""
        
        # Check protected paths
        for protected_path in self.protected_paths:
            if path.startswith(protected_path):
                raise BusinessRuleViolation(
                    f"Cannot delete protected path: {path}",
                    "protected_paths",
                    {'path': path, 'protected_path': protected_path}
                )
        
        # Check for critical files
        critical_files = {
            'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod',
            'Dockerfile', 'docker-compose.yml', 'README.md'
        }
        
        file_name = Path(path).name
        if file_name in critical_files:
            raise BusinessRuleViolation(
                f"Cannot delete critical file: {file_name}",
                "critical_file_protection",
                {'file': file_name, 'path': path}
            )
    
    def _validate_file_move_rules(self, old_path: str, new_path: str, agent_id: str):
        """Apply business rules for file moves"""
        
        # Check source file exists
        if not self.current_state.file_exists(old_path):
            raise BusinessRuleViolation(
                f"Source file does not exist: {old_path}",
                "file_exists_check",
                {'old_path': old_path}
            )
        
        # Check destination doesn't exist
        if self.current_state.file_exists(new_path):
            raise BusinessRuleViolation(
                f"Destination file already exists: {new_path}",
                "file_exists_check",
                {'new_path': new_path}
            )
        
        # Apply path protection rules to both paths
        for protected_path in self.protected_paths:
            if old_path.startswith(protected_path) or new_path.startswith(protected_path):
                raise BusinessRuleViolation(
                    f"Cannot move to/from protected path",
                    "protected_paths",
                    {'old_path': old_path, 'new_path': new_path}
                )
    
    def _validate_directory_creation_rules(self, path: str, agent_id: str):
        """Apply business rules for directory creation"""
        
        # Check if directory already exists
        if self.current_state.directory_exists(path):
            raise BusinessRuleViolation(
                f"Directory already exists: {path}",
                "directory_exists_check",
                {'path': path}
            )
        
        # Check protected paths
        for protected_path in self.protected_paths:
            if path.startswith(protected_path) or protected_path.startswith(path):
                raise BusinessRuleViolation(
                    f"Cannot create protected directory: {path}",
                    "protected_paths",
                    {'path': path, 'protected_path': protected_path}
                )
    
    def _hash_command(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Generate hash for command validation caching"""
        content = f"{tool_name}:{str(sorted(tool_input.items()))}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def can_modify_file(self, path: str, agent_id: str) -> bool:
        """Check if agent can modify a specific file"""
        try:
            self._validate_file_modification_rules(path, "", agent_id)
            return True
        except BusinessRuleViolation:
            return False
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics"""
        return {
            'project_id': self.project_id,
            'version': self.version,
            'uncommitted_events': len(self.uncommitted_events),
            'project_stats': self.current_state.get_project_stats(),
            'agent_stats': self.current_state.get_agent_stats(),
            'business_rules': {
                'max_file_size': self.max_file_size,
                'allowed_extensions': len(self.allowed_file_extensions),
                'protected_paths': len(self.protected_paths)
            }
        }