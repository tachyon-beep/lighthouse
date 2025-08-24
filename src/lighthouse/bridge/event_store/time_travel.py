"""
Time Travel Debugging

Historical state reconstruction and session replay capabilities.
Enables debugging by reconstructing project state at any point in history.

Features:
- Point-in-time state reconstruction
- File history tracking and diff generation
- Session replay with complete audit trails
- Event correlation and causality tracking
- Performance-optimized snapshot and rebuild
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from lighthouse.event_store.models import Event, EventFilter, EventType
from .project_state import ProjectState, FileVersion
# Note: event_store will be injected via constructor

logger = logging.getLogger(__name__)


@dataclass
class SessionReplay:
    """Complete replay data for a session"""
    
    session_id: str
    events: List[Event]
    initial_state: ProjectState
    final_state: ProjectState
    agent_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    
    # Analysis data
    files_modified: List[str]
    validation_requests: int
    decisions_made: Dict[str, str]
    operation_summary: Dict[str, int]
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Get session duration"""
        if self.ended_at:
            return self.ended_at - self.started_at
        return None
    
    def get_file_changes(self, file_path: str) -> List[Tuple[Event, str, str]]:
        """Get all changes to a specific file during session"""
        changes = []
        
        for event in self.events:
            if (event.is_file_operation() and 
                event.get_file_path() == file_path):
                
                # Get before and after content
                before_content = ""
                after_content = ""
                
                if event.event_type in [EventType.FILE_MODIFIED, EventType.FILE_CREATED]:
                    after_content = event.data.get('content', '')
                    
                    # Find previous content from event history
                    if event.data.get('previous_hash'):
                        # Would lookup previous content by hash
                        before_content = "[Previous version]"
                
                changes.append((event, before_content, after_content))
        
        return changes


@dataclass
class FileHistoryEntry:
    """Entry in file change history"""
    
    timestamp: datetime
    event: Event
    content: str
    content_hash: str
    agent_id: str
    operation: str  # created, modified, deleted, moved
    size: int
    
    def get_diff_summary(self, previous: Optional['FileHistoryEntry'] = None) -> str:
        """Get summary of changes from previous version"""
        if not previous:
            return f"File created ({self.size} bytes)"
        
        if self.operation == "deleted":
            return "File deleted"
        
        if self.operation == "moved":
            old_path = previous.event.data.get('old_path', 'unknown')
            new_path = self.event.data.get('new_path', 'unknown') 
            return f"File moved: {old_path} -> {new_path}"
        
        size_diff = self.size - previous.size
        size_change = f"+{size_diff}" if size_diff > 0 else str(size_diff)
        
        return f"Modified ({size_change} bytes)"


class TimeTravelDebugger:
    """Time travel debugging and historical analysis"""
    
    def __init__(self, event_store):
        """
        Initialize time travel debugger
        
        Args:
            event_store: Event store instance for querying events
        """
        self.event_store = event_store
        
        # Caching for performance
        self._snapshot_cache: Dict[str, Tuple[datetime, ProjectState]] = {}
        self._file_history_cache: Dict[str, List[FileHistoryEntry]] = {}
        
        # Performance settings
        self.snapshot_interval = timedelta(hours=1)  # Create snapshots every hour
        self.cache_ttl = timedelta(minutes=30)  # Cache TTL
        
    async def rebuild_at_timestamp(self, 
                                 timestamp: datetime,
                                 project_id: str) -> ProjectState:
        """
        Rebuild project state at specific timestamp
        
        Args:
            timestamp: Point in time to rebuild state
            project_id: Project identifier
            
        Returns:
            Project state at the specified timestamp
        """
        
        # Check cache first
        cache_key = f"{project_id}:{timestamp.isoformat()}"
        if cache_key in self._snapshot_cache:
            cached_time, cached_state = self._snapshot_cache[cache_key]
            if datetime.utcnow() - cached_time < self.cache_ttl:
                logger.debug(f"Using cached state for {timestamp}")
                return cached_state
        
        # Find the best starting snapshot
        snapshot_state, snapshot_time = await self._find_best_snapshot(
            project_id, timestamp
        )
        
        # Get events from snapshot time to target time
        event_filter = EventFilter(
            aggregate_ids=[project_id],
            after_timestamp=snapshot_time,
            before_timestamp=timestamp
        )
        
        events = await self.event_store.query_events(event_filter)
        
        # Rebuild state from snapshot
        state = snapshot_state or ProjectState(project_id)
        
        for event in events:
            state.apply_event(event)
        
        # Cache the result
        self._snapshot_cache[cache_key] = (datetime.utcnow(), state)
        
        # Limit cache size
        if len(self._snapshot_cache) > 100:
            # Remove oldest entries
            sorted_items = sorted(
                self._snapshot_cache.items(),
                key=lambda x: x[1][0]  # Sort by cached time
            )
            self._snapshot_cache = dict(sorted_items[-80:])
        
        logger.info(f"Rebuilt state for {project_id} at {timestamp}")
        
        return state
    
    async def get_file_history(self, 
                             file_path: str,
                             project_id: str,
                             limit: Optional[int] = None) -> List[FileHistoryEntry]:
        """
        Get complete history of a file
        
        Args:
            file_path: Path to the file
            project_id: Project identifier
            limit: Maximum number of entries to return
            
        Returns:
            List of file history entries in chronological order
        """
        
        # Check cache
        cache_key = f"{project_id}:{file_path}"
        if (cache_key in self._file_history_cache and 
            limit is None):  # Only cache complete histories
            return self._file_history_cache[cache_key]
        
        # Query file events
        event_filter = EventFilter(
            aggregate_ids=[project_id],
            event_types=[
                EventType.FILE_CREATED,
                EventType.FILE_MODIFIED,
                EventType.FILE_DELETED,
                EventType.FILE_MOVED,
                EventType.FILE_COPIED
            ],
            file_paths=[file_path],
            limit=limit
        )
        
        events = await self.event_store.query_events(event_filter)
        
        # Convert events to history entries
        history = []
        for event in events:
            operation = self._get_operation_from_event_type(event.event_type)
            
            entry = FileHistoryEntry(
                timestamp=event.timestamp,
                event=event,
                content=event.data.get('content', ''),
                content_hash=event.data.get('content_hash', ''),
                agent_id=event.source_agent or event.metadata.get('agent_id', 'unknown'),
                operation=operation,
                size=event.data.get('size', 0)
            )
            
            history.append(entry)
        
        # Cache complete histories
        if limit is None:
            self._file_history_cache[cache_key] = history
        
        return history
    
    async def replay_session(self, 
                           session_id: str,
                           project_id: str) -> SessionReplay:
        """
        Replay entire session with complete context
        
        Args:
            session_id: Session identifier to replay
            project_id: Project identifier
            
        Returns:
            Complete session replay data
        """
        
        # Get all session events
        event_filter = EventFilter(
            aggregate_ids=[project_id],
            session_ids=[session_id]
        )
        
        session_events = await self.event_store.query_events(event_filter)
        
        if not session_events:
            raise ValueError(f"No events found for session {session_id}")
        
        # Find session start and end events
        start_event = None
        end_event = None
        
        for event in session_events:
            if event.event_type == EventType.AGENT_SESSION_STARTED:
                start_event = event
            elif event.event_type == EventType.AGENT_SESSION_ENDED:
                end_event = event
        
        if not start_event:
            raise ValueError(f"Session start event not found for {session_id}")
        
        # Get initial state (just before session start)
        initial_state = await self.rebuild_at_timestamp(
            start_event.timestamp - timedelta(microseconds=1),
            project_id
        )
        
        # Get final state
        end_time = end_event.timestamp if end_event else session_events[-1].timestamp
        final_state = await self.rebuild_at_timestamp(end_time, project_id)
        
        # Analyze session
        files_modified = []
        validation_requests = 0
        decisions_made = {}
        operation_summary = defaultdict(int)
        
        for event in session_events:
            # Track file modifications
            if event.is_file_operation():
                file_path = event.get_file_path()
                if file_path and file_path not in files_modified:
                    files_modified.append(file_path)
            
            # Track validations
            if event.event_type == EventType.VALIDATION_REQUEST_SUBMITTED:
                validation_requests += 1
            elif event.event_type == EventType.VALIDATION_DECISION_MADE:
                request_id = event.data.get('request_id')
                decision = event.data.get('decision')
                if request_id and decision:
                    decisions_made[request_id] = decision
            
            # Track operations
            operation_summary[event.event_type.value] += 1
        
        return SessionReplay(
            session_id=session_id,
            events=session_events,
            initial_state=initial_state,
            final_state=final_state,
            agent_id=start_event.source_agent or start_event.metadata.get('agent_id', 'unknown'),
            started_at=start_event.timestamp,
            ended_at=end_event.timestamp if end_event else None,
            files_modified=files_modified,
            validation_requests=validation_requests,
            decisions_made=decisions_made,
            operation_summary=dict(operation_summary)
        )
    
    async def get_project_timeline(self,
                                 project_id: str,
                                 start_time: Optional[datetime] = None,
                                 end_time: Optional[datetime] = None,
                                 event_types: Optional[List[EventType]] = None) -> List[Event]:
        """
        Get project timeline with optional filtering
        
        Args:
            project_id: Project identifier
            start_time: Optional start time filter
            end_time: Optional end time filter
            event_types: Optional event type filter
            
        Returns:
            Chronological list of events
        """
        
        event_filter = EventFilter(
            aggregate_ids=[project_id],
            after_timestamp=start_time,
            before_timestamp=end_time,
            event_types=event_types
        )
        
        return await self.event_store.query_events(event_filter)
    
    async def analyze_concurrency_conflicts(self,
                                          project_id: str,
                                          time_window: timedelta = timedelta(minutes=5)) -> List[Dict[str, Any]]:
        """
        Analyze potential concurrency conflicts
        
        Args:
            project_id: Project identifier
            time_window: Time window to look for concurrent operations
            
        Returns:
            List of potential conflict scenarios
        """
        
        # Get recent file operations
        recent_time = datetime.utcnow() - time_window
        event_filter = EventFilter(
            aggregate_ids=[project_id],
            after_timestamp=recent_time,
            event_types=[
                EventType.FILE_CREATED,
                EventType.FILE_MODIFIED,
                EventType.FILE_DELETED,
                EventType.FILE_MOVED
            ]
        )
        
        events = await self.event_store.query_events(event_filter)
        
        # Group events by file path
        file_events = defaultdict(list)
        for event in events:
            file_path = event.get_file_path()
            if file_path:
                file_events[file_path].append(event)
        
        # Look for potential conflicts
        conflicts = []
        for file_path, file_event_list in file_events.items():
            if len(file_event_list) > 1:
                # Check for concurrent modifications
                agents = set(event.source_agent or event.metadata.get('agent_id', 'unknown') for event in file_event_list)
                
                if len(agents) > 1:
                    # Multiple agents modified same file
                    conflicts.append({
                        'type': 'concurrent_modification',
                        'file_path': file_path,
                        'agents': list(agents),
                        'events': len(file_event_list),
                        'time_span': (
                            file_event_list[-1].timestamp - file_event_list[0].timestamp
                        ).total_seconds()
                    })
        
        return conflicts
    
    async def generate_diff(self,
                          file_path: str,
                          project_id: str,
                          from_time: datetime,
                          to_time: datetime) -> Dict[str, Any]:
        """
        Generate diff for a file between two points in time
        
        Args:
            file_path: Path to the file
            project_id: Project identifier
            from_time: Starting time
            to_time: Ending time
            
        Returns:
            Diff information
        """
        
        # Get states at both times
        from_state = await self.rebuild_at_timestamp(from_time, project_id)
        to_state = await self.rebuild_at_timestamp(to_time, project_id)
        
        # Get file content at both times
        from_content = from_state.get_file_content(file_path) or ""
        to_content = to_state.get_file_content(file_path) or ""
        
        # Simple diff calculation (could use difflib for more sophisticated diffs)
        from_lines = from_content.splitlines()
        to_lines = to_content.splitlines()
        
        import difflib
        diff = list(difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"{file_path} @ {from_time.isoformat()}",
            tofile=f"{file_path} @ {to_time.isoformat()}",
            lineterm=""
        ))
        
        return {
            'file_path': file_path,
            'from_time': from_time.isoformat(),
            'to_time': to_time.isoformat(),
            'from_size': len(from_content),
            'to_size': len(to_content),
            'lines_added': len([line for line in diff if line.startswith('+')]),
            'lines_removed': len([line for line in diff if line.startswith('-')]),
            'unified_diff': diff
        }
    
    async def _find_best_snapshot(self,
                                project_id: str,
                                target_time: datetime) -> Tuple[Optional[ProjectState], datetime]:
        """
        Find the best snapshot to start rebuilding from
        
        Returns:
            Tuple of (snapshot_state, snapshot_time)
        """
        
        # For now, always rebuild from beginning
        # In a production system, this would look for stored snapshots
        return None, datetime.min
    
    def _get_operation_from_event_type(self, event_type: EventType) -> str:
        """Convert event type to operation string"""
        mapping = {
            EventType.FILE_CREATED: "created",
            EventType.FILE_MODIFIED: "modified", 
            EventType.FILE_DELETED: "deleted",
            EventType.FILE_MOVED: "moved",
            EventType.FILE_COPIED: "copied"
        }
        return mapping.get(event_type, "unknown")
    
    def clear_cache(self):
        """Clear all caches"""
        self._snapshot_cache.clear()
        self._file_history_cache.clear()
        logger.info("Time travel debugger cache cleared")