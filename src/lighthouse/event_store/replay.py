"""Event Replay Engine for reconstructing system state."""

import asyncio
import logging
from typing import Any, Dict, Callable, AsyncIterator, Optional, List, Set
from collections import defaultdict

from .store import EventStore, EventStoreError
from .models import Event, EventQuery, EventFilter, QueryResult

logger = logging.getLogger(__name__)


class ReplayError(Exception):
    """Exception raised during event replay operations."""
    pass


class EventReplayEngine:
    """Engine for replaying events to reconstruct system state."""
    
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.handlers: Dict[str, Callable] = {}
        self.aggregate_handlers: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        
    def register_handler(self, event_type: str, handler: Callable):
        """
        Register a handler for a specific event type.
        
        Handler signature: handler(event: Event, state: Dict[str, Any]) -> Dict[str, Any]
        """
        self.handlers[event_type] = handler
        
    def register_aggregate_handler(self, aggregate_type: str, event_type: str, handler: Callable):
        """
        Register a handler for a specific event type on a specific aggregate type.
        
        This provides more granular control over event handling.
        """
        self.aggregate_handlers[aggregate_type][event_type] = handler
        
    async def replay_all(self, initial_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Replay all events to reconstruct current state.
        
        Args:
            initial_state: Starting state (defaults to empty dict)
            
        Returns:
            Final reconstructed state
        """
        state = initial_state or {}
        offset = 0
        batch_size = 10000  # Max limit per Phase 1 spec
        
        try:
            while True:
                # Query batch of events
                query = EventQuery(limit=batch_size, offset=offset)
                result = await self.event_store.query(query)
                
                if not result.events:
                    # No more events
                    break
                
                # Process batch
                for event in result.events:
                    state = await self._apply_event(event, state)
                
                # Check if we have more events
                if not result.has_more:
                    break
                    
                offset += len(result.events)
                
            return state
            
        except EventStoreError as e:
            raise ReplayError(f"Failed to replay events: {e}")
        
    async def replay_from_sequence(
        self,
        start_sequence: int,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Replay events starting from a specific sequence number.
        
        Args:
            start_sequence: Sequence number to start from
            initial_state: Starting state (defaults to empty dict)
            
        Returns:
            Final reconstructed state
        """
        state = initial_state or {}
        offset = 0
        batch_size = 10000
        
        try:
            while True:
                # Query batch of events from sequence
                event_filter = EventFilter(start_sequence=start_sequence)
                query = EventQuery(filter=event_filter, limit=batch_size, offset=offset)
                result = await self.event_store.query(query)
                
                if not result.events:
                    break
                
                for event in result.events:
                    state = await self._apply_event(event, state)
                
                if not result.has_more:
                    break
                    
                offset += len(result.events)
                
            return state
            
        except EventStoreError as e:
            raise ReplayError(f"Failed to replay events from sequence {start_sequence}: {e}")
    
    async def replay_for_aggregate(
        self,
        aggregate_id: str,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Replay events for a specific aggregate.
        
        Args:
            aggregate_id: ID of the aggregate to replay
            initial_state: Starting state (defaults to empty dict)
            
        Returns:
            Final reconstructed state for the aggregate
        """
        state = initial_state or {}
        
        # Query events for specific aggregate
        event_filter = EventFilter(aggregate_ids=[aggregate_id])
        query = EventQuery(filter=event_filter, limit=10000)
        
        try:
            result = await self.event_store.query(query)
            
            for event in result.events:
                state = await self._apply_event(event, state)
                
            return state
            
        except EventStoreError as e:
            raise ReplayError(f"Failed to replay events for aggregate {aggregate_id}: {e}")
    
    async def replay_stream(
        self,
        start_sequence: int = 0,
        batch_size: int = 1000
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream state changes as events are replayed.
        
        This is memory-efficient for large event histories.
        
        Args:
            start_sequence: Sequence number to start from
            batch_size: Number of events to process in each batch
            
        Yields:
            State update dictionaries: {"sequence": int, "state": dict, "event": Event}
        """
        state = {}
        offset = 0
        
        while True:
            # Query batch of events
            event_filter = EventFilter(start_sequence=start_sequence)
            query = EventQuery(
                filter=event_filter,
                limit=batch_size,
                offset=offset
            )
            
            try:
                result = await self.event_store.query(query)
                
                if not result.events:
                    # No more events
                    break
                
                # Process batch
                for event in result.events:
                    state = await self._apply_event(event, state)
                    yield {
                        "sequence": event.sequence,
                        "state": state.copy(),  # Copy to prevent mutation
                        "event": event
                    }
                
                # Check if we have more events
                if not result.has_more:
                    break
                    
                offset += len(result.events)
                
            except EventStoreError as e:
                logger.error(f"Error during streaming replay: {e}")
                break
    
    async def replay_with_filter(
        self,
        event_filter: EventFilter,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Replay events matching a specific filter.
        
        Args:
            event_filter: Filter to apply to events
            initial_state: Starting state (defaults to empty dict)
            
        Returns:
            Final reconstructed state
        """
        state = initial_state or {}
        
        query = EventQuery(filter=event_filter, limit=10000)
        
        try:
            result = await self.event_store.query(query)
            
            for event in result.events:
                state = await self._apply_event(event, state)
                
            return state
            
        except EventStoreError as e:
            raise ReplayError(f"Failed to replay filtered events: {e}")
    
    async def get_state_at_sequence(
        self,
        target_sequence: int,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get system state as it was at a specific sequence number.
        
        This is useful for time-travel debugging.
        
        Args:
            target_sequence: Target sequence number
            initial_state: Starting state (defaults to empty dict)
            
        Returns:
            State as it was at the target sequence
        """
        state = initial_state or {}
        
        # Query events up to target sequence
        event_filter = EventFilter(end_sequence=target_sequence)
        query = EventQuery(filter=event_filter, limit=10000)
        
        try:
            result = await self.event_store.query(query)
            
            for event in result.events:
                if event.sequence <= target_sequence:
                    state = await self._apply_event(event, state)
                else:
                    break
                    
            return state
            
        except EventStoreError as e:
            raise ReplayError(f"Failed to get state at sequence {target_sequence}: {e}")
    
    async def validate_state_consistency(
        self,
        checkpoint_sequences: List[int],
        validator: Callable[[Dict[str, Any]], bool]
    ) -> Dict[str, bool]:
        """
        Validate state consistency at multiple checkpoint sequences.
        
        Args:
            checkpoint_sequences: Sequence numbers to check
            validator: Function to validate state consistency
            
        Returns:
            Dictionary mapping sequence numbers to validation results
        """
        results = {}
        
        for sequence in sorted(checkpoint_sequences):
            try:
                state = await self.get_state_at_sequence(sequence)
                results[sequence] = validator(state)
            except Exception as e:
                logger.error(f"Validation failed at sequence {sequence}: {e}")
                results[sequence] = False
        
        return results
    
    async def _apply_event(self, event: Event, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a single event to the current state.
        
        Args:
            event: Event to apply
            state: Current state
            
        Returns:
            Updated state
        """
        # Try aggregate-specific handler first
        if event.aggregate_type in self.aggregate_handlers:
            aggregate_handlers = self.aggregate_handlers[event.aggregate_type]
            if event.event_type.value in aggregate_handlers:
                handler = aggregate_handlers[event.event_type.value]
                if asyncio.iscoroutinefunction(handler):
                    return await handler(event, state)
                else:
                    return handler(event, state)
        
        # Try general event type handler
        if event.event_type.value in self.handlers:
            handler = self.handlers[event.event_type.value]
            if asyncio.iscoroutinefunction(handler):
                return await handler(event, state)
            else:
                return handler(event, state)
        
        # Default handling - just store the event data
        if event.aggregate_id not in state:
            state[event.aggregate_id] = {}
        
        # Merge event data into aggregate state
        if isinstance(state[event.aggregate_id], dict):
            state[event.aggregate_id].update(event.data)
        else:
            # If not a dict, replace with event data
            state[event.aggregate_id] = event.data.copy()
        
        return state
    
    def get_registered_handlers(self) -> Dict[str, List[str]]:
        """Get information about registered handlers."""
        return {
            "event_handlers": list(self.handlers.keys()),
            "aggregate_handlers": {
                agg_type: list(handlers.keys())
                for agg_type, handlers in self.aggregate_handlers.items()
            }
        }
    
    def clear_handlers(self):
        """Clear all registered handlers."""
        self.handlers.clear()
        self.aggregate_handlers.clear()


# Utility functions for common replay patterns
async def reconstruct_aggregate_state(
    event_store: EventStore,
    aggregate_id: str,
    handlers: Dict[str, Callable]
) -> Dict[str, Any]:
    """
    Utility function to reconstruct state for a single aggregate.
    
    Args:
        event_store: EventStore instance
        aggregate_id: ID of aggregate to reconstruct
        handlers: Map of event_type -> handler function
        
    Returns:
        Reconstructed aggregate state
    """
    replay_engine = EventReplayEngine(event_store)
    
    # Register handlers
    for event_type, handler in handlers.items():
        replay_engine.register_handler(event_type, handler)
    
    # Replay events for aggregate
    state = await replay_engine.replay_for_aggregate(aggregate_id)
    
    return state.get(aggregate_id, {})


async def get_historical_snapshot(
    event_store: EventStore,
    target_sequence: int,
    handlers: Dict[str, Callable]
) -> Dict[str, Any]:
    """
    Utility function to get a historical snapshot of system state.
    
    Args:
        event_store: EventStore instance
        target_sequence: Sequence number for the snapshot
        handlers: Map of event_type -> handler function
        
    Returns:
        System state at target sequence
    """
    replay_engine = EventReplayEngine(event_store)
    
    # Register handlers
    for event_type, handler in handlers.items():
        replay_engine.register_handler(event_type, handler)
    
    # Get state at sequence
    return await replay_engine.get_state_at_sequence(target_sequence)