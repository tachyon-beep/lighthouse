"""
Event-Sourced Architecture

Complete event-sourced design with time travel debugging and perfect audit trails.
All project state is derived from an immutable event log, enabling:

- Complete audit trails with agent attribution
- Time travel debugging to any point in history  
- Perfect reproducibility of project states
- Real-time event streaming for live updates
- Conflict-free collaborative editing

Core Components:
- ProjectAggregate: Business logic for project operations
- EventStore: Persistence and querying of events
- ProjectState: Current state reconstruction from events
- TimeTravelDebugger: Historical state reconstruction
"""

from .project_aggregate import ProjectAggregate
from lighthouse.event_store.models import Event, EventType, EventFilter
from .project_state import ProjectState, FileVersion
from .time_travel import TimeTravelDebugger, SessionReplay
from .event_stream import EventStream, EventSubscription

__all__ = [
    'ProjectAggregate',
    'Event', 
    'EventType',
    'EventFilter',
    'ProjectState',
    'FileVersion', 
    'TimeTravelDebugger',
    'SessionReplay',
    'EventStream',
    'EventSubscription'
]