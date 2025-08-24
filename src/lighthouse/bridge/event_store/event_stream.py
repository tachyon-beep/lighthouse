"""
Event Stream Management

Real-time event streaming for live updates and subscriptions.
Enables WebSocket connections and named pipe streams for expert agents.

Features:
- Real-time event broadcasting
- Filtered subscriptions by event type, agent, or file path
- WebSocket integration for browser clients
- Named pipe streams for FUSE filesystem
- Backpressure handling and connection management
"""

import asyncio
import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

import aiofiles
from pathlib import Path

from lighthouse.event_store.models import Event, EventFilter, EventType

logger = logging.getLogger(__name__)


@dataclass
class EventSubscription:
    """Event stream subscription"""
    
    subscription_id: str
    subscriber_id: str  # Agent ID or client ID
    event_filter: EventFilter
    callback: Optional[Callable[[Event], None]] = None
    
    # Stream settings
    buffer_size: int = 1000
    backpressure_limit: int = 5000
    
    # Statistics
    events_sent: int = 0
    events_dropped: int = 0
    last_event_time: Optional[datetime] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def matches_event(self, event: Event) -> bool:
        """Check if event matches subscription filter"""
        return self.event_filter.matches_event(event)


@dataclass
class StreamStats:
    """Statistics for event streams"""
    
    total_events: int = 0
    total_subscriptions: int = 0
    active_subscriptions: int = 0
    events_per_second: float = 0.0
    average_fanout: float = 0.0
    dropped_events: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_events': self.total_events,
            'total_subscriptions': self.total_subscriptions,
            'active_subscriptions': self.active_subscriptions,
            'events_per_second': self.events_per_second,
            'average_fanout': self.average_fanout,
            'dropped_events': self.dropped_events
        }


class EventStream:
    """Real-time event stream manager"""
    
    def __init__(self, 
                 fuse_mount_path: Optional[str] = "/mnt/lighthouse/project/streams",
                 websocket_port: int = 8766):
        """
        Initialize event stream
        
        Args:
            fuse_mount_path: Path for FUSE named pipe streams
            websocket_port: Port for WebSocket connections
        """
        self.fuse_mount_path = Path(fuse_mount_path) if fuse_mount_path else None
        self.websocket_port = websocket_port
        
        # Subscriptions management
        self.subscriptions: Dict[str, EventSubscription] = {}
        self.subscriber_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        # Event buffering for each subscription
        self.event_buffers: Dict[str, deque] = {}
        
        # Named pipe streams for FUSE integration
        self.named_pipes: Dict[str, asyncio.Queue] = {}
        self.pipe_tasks: Dict[str, asyncio.Task] = {}
        
        # WebSocket connections
        self.websocket_connections: Dict[str, Any] = {}  # Will store WebSocket objects
        
        # Statistics
        self.stats = StreamStats()
        self._event_timestamps = deque(maxlen=1000)  # For calculating events/second
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the event stream manager"""
        logger.info("Starting Event Stream Manager...")
        
        # Create FUSE mount directories if configured
        if self.fuse_mount_path:
            await self._setup_fuse_streams()
        
        # Start background tasks
        stats_task = asyncio.create_task(self._update_stats_periodically())
        cleanup_task = asyncio.create_task(self._cleanup_expired_subscriptions())
        
        self._background_tasks.update([stats_task, cleanup_task])
        
        logger.info("Event Stream Manager started")
    
    async def stop(self):
        """Stop the event stream manager"""
        logger.info("Stopping Event Stream Manager...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Close all named pipes
        for task in self.pipe_tasks.values():
            task.cancel()
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        logger.info("Event Stream Manager stopped")
    
    async def publish_event(self, event: Event):
        """
        Publish event to all matching subscriptions
        
        Args:
            event: Event to publish
        """
        self.stats.total_events += 1
        self._event_timestamps.append(datetime.utcnow())
        
        # Find matching subscriptions
        matching_subscriptions = []
        for subscription in self.subscriptions.values():
            if subscription.matches_event(event):
                matching_subscriptions.append(subscription)
        
        # Update fanout statistics
        if matching_subscriptions:
            self.stats.average_fanout = (
                (self.stats.average_fanout * (self.stats.total_events - 1) + 
                 len(matching_subscriptions)) / self.stats.total_events
            )
        
        # Send to matching subscriptions
        send_tasks = []
        for subscription in matching_subscriptions:
            task = asyncio.create_task(
                self._send_event_to_subscription(event, subscription)
            )
            send_tasks.append(task)
        
        # Wait for all sends to complete (with timeout to prevent blocking)
        if send_tasks:
            await asyncio.wait(send_tasks, timeout=1.0)
    
    def subscribe(self,
                 subscriber_id: str,
                 event_filter: EventFilter,
                 callback: Optional[Callable[[Event], None]] = None,
                 buffer_size: int = 1000) -> str:
        """
        Create event subscription
        
        Args:
            subscriber_id: ID of the subscriber
            event_filter: Filter for events to receive
            callback: Optional callback function for events
            buffer_size: Size of event buffer
            
        Returns:
            Subscription ID
        """
        subscription_id = str(uuid4())
        
        subscription = EventSubscription(
            subscription_id=subscription_id,
            subscriber_id=subscriber_id,
            event_filter=event_filter,
            callback=callback,
            buffer_size=buffer_size
        )
        
        # Store subscription
        self.subscriptions[subscription_id] = subscription
        self.subscriber_subscriptions[subscriber_id].add(subscription_id)
        self.event_buffers[subscription_id] = deque(maxlen=buffer_size)
        
        self.stats.total_subscriptions += 1
        self.stats.active_subscriptions += 1
        
        logger.info(f"Created subscription {subscription_id} for {subscriber_id}")
        
        return subscription_id
    
    def unsubscribe(self, subscription_id: str):
        """Remove event subscription"""
        if subscription_id in self.subscriptions:
            subscription = self.subscriptions[subscription_id]
            
            # Remove from tracking
            del self.subscriptions[subscription_id]
            self.subscriber_subscriptions[subscription.subscriber_id].discard(subscription_id)
            del self.event_buffers[subscription_id]
            
            self.stats.active_subscriptions -= 1
            
            logger.info(f"Removed subscription {subscription_id}")
    
    def unsubscribe_all(self, subscriber_id: str):
        """Remove all subscriptions for a subscriber"""
        subscription_ids = list(self.subscriber_subscriptions[subscriber_id])
        
        for subscription_id in subscription_ids:
            self.unsubscribe(subscription_id)
        
        logger.info(f"Removed all subscriptions for {subscriber_id}")
    
    async def get_buffered_events(self, subscription_id: str, limit: Optional[int] = None) -> List[Event]:
        """Get buffered events for a subscription"""
        if subscription_id not in self.event_buffers:
            return []
        
        buffer = self.event_buffers[subscription_id]
        events = list(buffer)
        
        if limit:
            events = events[-limit:]
        
        return events
    
    async def create_named_pipe_stream(self, stream_name: str) -> str:
        """
        Create named pipe stream for FUSE integration
        
        Args:
            stream_name: Name of the stream (e.g., 'validation_requests')
            
        Returns:
            Path to the named pipe
        """
        if not self.fuse_mount_path:
            raise ValueError("FUSE mount path not configured")
        
        pipe_path = self.fuse_mount_path / stream_name
        
        # Create queue for the stream
        stream_queue = asyncio.Queue(maxsize=1000)
        self.named_pipes[stream_name] = stream_queue
        
        # Start background task to write to pipe
        pipe_task = asyncio.create_task(
            self._write_to_named_pipe(pipe_path, stream_queue)
        )
        self.pipe_tasks[stream_name] = pipe_task
        
        logger.info(f"Created named pipe stream: {pipe_path}")
        
        return str(pipe_path)
    
    async def write_to_stream(self, stream_name: str, data: Dict[str, Any]):
        """Write data to a named pipe stream"""
        if stream_name in self.named_pipes:
            try:
                await self.named_pipes[stream_name].put(data)
            except asyncio.QueueFull:
                logger.warning(f"Stream {stream_name} queue is full, dropping message")
    
    async def _send_event_to_subscription(self, event: Event, subscription: EventSubscription):
        """Send event to a specific subscription"""
        try:
            # Check backpressure
            buffer = self.event_buffers[subscription.subscription_id]
            if len(buffer) >= subscription.backpressure_limit:
                # Drop oldest events
                while len(buffer) >= subscription.buffer_size:
                    buffer.popleft()
                    subscription.events_dropped += 1
                    self.stats.dropped_events += 1
            
            # Add event to buffer
            buffer.append(event)
            subscription.events_sent += 1
            subscription.last_event_time = datetime.utcnow()
            
            # Call callback if provided
            if subscription.callback:
                try:
                    subscription.callback(event)
                except Exception as e:
                    logger.error(f"Subscription callback error: {e}")
            
            # Send to WebSocket if connected
            await self._send_to_websocket(subscription.subscriber_id, event)
            
        except Exception as e:
            logger.error(f"Error sending event to subscription {subscription.subscription_id}: {e}")
    
    async def _send_to_websocket(self, subscriber_id: str, event: Event):
        """Send event to WebSocket connection if available"""
        if subscriber_id in self.websocket_connections:
            try:
                websocket = self.websocket_connections[subscriber_id]
                message = {
                    'type': 'event',
                    'event': event.to_dict()
                }
                await websocket.send(json.dumps(message))
            except Exception as e:
                logger.warning(f"WebSocket send error for {subscriber_id}: {e}")
                # Remove broken connection
                del self.websocket_connections[subscriber_id]
    
    async def _write_to_named_pipe(self, pipe_path: Path, queue: asyncio.Queue):
        """Write data from queue to named pipe"""
        try:
            # Create parent directories
            pipe_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create named pipe (FIFO)
            if not pipe_path.exists():
                import os
                os.mkfifo(str(pipe_path))
            
            # Continuously write to pipe
            while not self._shutdown_event.is_set():
                try:
                    # Get data from queue with timeout
                    data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    # Write to named pipe
                    async with aiofiles.open(pipe_path, 'w') as f:
                        await f.write(json.dumps(data) + '\n')
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error writing to pipe {pipe_path}: {e}")
                    await asyncio.sleep(1.0)
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Named pipe task error for {pipe_path}: {e}")
    
    async def _setup_fuse_streams(self):
        """Setup default FUSE stream directories"""
        if not self.fuse_mount_path:
            return
        
        # Create stream directories
        self.fuse_mount_path.mkdir(parents=True, exist_ok=True)
        
        # Create default streams
        default_streams = [
            'validation_requests',
            'expert_responses', 
            'pair_sessions',
            'file_changes',
            'agent_activities'
        ]
        
        for stream_name in default_streams:
            await self.create_named_pipe_stream(stream_name)
    
    async def _update_stats_periodically(self):
        """Update statistics periodically"""
        while not self._shutdown_event.is_set():
            try:
                # Calculate events per second
                if len(self._event_timestamps) >= 2:
                    time_span = (
                        self._event_timestamps[-1] - self._event_timestamps[0]
                    ).total_seconds()
                    
                    if time_span > 0:
                        self.stats.events_per_second = len(self._event_timestamps) / time_span
                
                await asyncio.sleep(30.0)  # Update every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stats update error: {e}")
                await asyncio.sleep(30.0)
    
    async def _cleanup_expired_subscriptions(self):
        """Clean up inactive subscriptions"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.utcnow()
                expired_subscriptions = []
                
                for subscription_id, subscription in self.subscriptions.items():
                    # Remove subscriptions inactive for more than 1 hour
                    if (subscription.last_event_time and 
                        (current_time - subscription.last_event_time).total_seconds() > 3600):
                        expired_subscriptions.append(subscription_id)
                
                for subscription_id in expired_subscriptions:
                    self.unsubscribe(subscription_id)
                
                if expired_subscriptions:
                    logger.info(f"Cleaned up {len(expired_subscriptions)} expired subscriptions")
                
                await asyncio.sleep(300.0)  # Check every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(300.0)
    
    def add_websocket_connection(self, subscriber_id: str, websocket):
        """Add WebSocket connection for a subscriber"""
        self.websocket_connections[subscriber_id] = websocket
        logger.info(f"Added WebSocket connection for {subscriber_id}")
    
    def remove_websocket_connection(self, subscriber_id: str):
        """Remove WebSocket connection for a subscriber"""
        if subscriber_id in self.websocket_connections:
            del self.websocket_connections[subscriber_id]
            logger.info(f"Removed WebSocket connection for {subscriber_id}")
    
    def get_stream_stats(self) -> Dict[str, Any]:
        """Get detailed stream statistics"""
        subscription_stats = []
        
        for subscription in self.subscriptions.values():
            subscription_stats.append({
                'subscription_id': subscription.subscription_id,
                'subscriber_id': subscription.subscriber_id,
                'events_sent': subscription.events_sent,
                'events_dropped': subscription.events_dropped,
                'buffer_size': len(self.event_buffers.get(subscription.subscription_id, [])),
                'created_at': subscription.created_at.isoformat(),
                'last_event_time': subscription.last_event_time.isoformat() if subscription.last_event_time else None
            })
        
        return {
            'overall_stats': self.stats.to_dict(),
            'subscriptions': subscription_stats,
            'named_pipes': list(self.named_pipes.keys()),
            'websocket_connections': len(self.websocket_connections)
        }