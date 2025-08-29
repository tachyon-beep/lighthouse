"""Core Event Store implementation with append-only logging."""

import asyncio
import json
import logging
import os
import secrets
import time
import hmac
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set
import gzip
import hashlib
from datetime import datetime, timezone

import aiofiles
import msgpack
from pydantic import ValidationError

logger = logging.getLogger(__name__)

from .models import (
    Event, EventBatch, EventFilter, EventQuery, EventType, 
    QueryResult, SnapshotMetadata, SystemHealth
)
from .validation import (
    PathValidator, InputValidator, ResourceLimiter, SecurityError
)
from .auth import (
    SimpleAuthenticator, Authorizer, AgentIdentity, Permission,
    AuthenticationError, AuthorizationError, create_system_authenticator
)
from .coordinated_authenticator import CoordinatedAuthenticator


class EventStoreError(Exception):
    """Base exception for event store operations."""
    pass


class EventStore:
    """High-performance file-based event store with security and atomic guarantees."""
    
    def __init__(self, data_dir: str = "./data/events", 
                 auth_secret: Optional[str] = None,
                 allowed_base_dirs: Optional[List[str]] = None,
                 external_authenticator: Optional[CoordinatedAuthenticator] = None):
        # Security validation for data directory
        self.path_validator = PathValidator(allowed_base_dirs)
        validated_data_dir = self.path_validator.validate_directory(data_dir)
        
        self.data_dir = validated_data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Security components
        self.input_validator = InputValidator()
        self.resource_limiter = ResourceLimiter()
        
        # Use external coordinated authenticator if provided, otherwise create system authenticator
        if external_authenticator:
            self.authenticator = external_authenticator._authenticator  # Access internal SimpleAuthenticator
            logger.info(f"🔐 EventStore using CoordinatedAuthenticator: {id(external_authenticator)}")
        else:
            self.authenticator = create_system_authenticator(auth_secret)
            logger.info("🔐 EventStore using standalone authenticator")
        
        self.authorizer = Authorizer(self.authenticator)
        
        # HMAC secret for event authentication
        self.hmac_secret = (auth_secret or os.environ.get('LIGHTHOUSE_EVENT_SECRET') or secrets.token_urlsafe(32)).encode('utf-8')
        
        # Configuration from ADR-002
        self.max_file_size = 100 * 1024 * 1024  # 100MB per ADR-002
        self.sync_policy = "fsync"  # fsync for durability
        self.compression_enabled = True
        self.max_event_size = 1024 * 1024  # 1MB per ADR-002
        
        # State tracking
        self.current_sequence = 0
        self.current_log_file = None
        self.current_log_path = None
        self.write_lock = asyncio.Lock()
        self._index: Dict[str, Set[int]] = {}  # Simple in-memory index
        
        # Performance tracking
        self._append_times = []
        self._query_times = []
        self._error_counts = {"append": 0, "query": 0}
        
        # Health status
        self.status = "initializing"
        
    async def initialize(self) -> None:
        """Initialize event store and recover state."""
        try:
            self.status = "initializing"
            await self._recover_state()
            await self._open_current_log_file()
            await self._rebuild_index()
            self.status = "healthy-secure"  # Indicate security is enabled
        except Exception as e:
            self.status = "failed"
            raise EventStoreError(f"Failed to initialize event store: {e}")
    
    async def shutdown(self) -> None:
        """Clean shutdown of event store."""
        try:
            async with self.write_lock:
                if self.current_log_file:
                    await self.current_log_file.close()
                    self.current_log_file = None
                    # Release file handle tracking
                    self.resource_limiter.track_file_handle(increment=False)
                self.status = "shutdown"
        except Exception as e:
            raise EventStoreError(f"Failed to shutdown cleanly: {e}")
    
    async def append(self, event: Event, agent_id: Optional[str] = None) -> None:
        """Append single event to log with security validation and atomic guarantees."""
        if event is None:
            raise EventStoreError("Cannot append None event")
        
        # Security validation
        try:
            # Validate event data for security issues
            self.input_validator.validate_event(event)
            
            # Authorize write operation
            if agent_id:
                identity = self.authorizer.authorize_write(
                    agent_id, batch_size=1, aggregate_id=event.aggregate_id
                )
                # Set source agent for traceability
                event.source_agent = agent_id
        
        except (SecurityError, AuthenticationError, AuthorizationError) as e:
            raise EventStoreError(f"Security validation failed: {e}")
        
        # Resource limits check
        event_size = event.calculate_size_bytes()
        if event_size > self.max_event_size:
            raise EventStoreError(f"Event size {event_size} exceeds limit {self.max_event_size}")
        
        try:
            self.resource_limiter.check_disk_usage(self.data_dir, event_size)
            self.resource_limiter.check_available_space(self.data_dir, event_size * 10)  # Buffer
        except SecurityError as e:
            raise EventStoreError(f"Resource limit exceeded: {e}")
        
        start_time = time.time()
        
        try:
            async with self.write_lock:
                # Assign sequence number
                self.current_sequence += 1
                event.sequence = self.current_sequence
                
                # Serialize event per ADR-002 (MessagePack for storage)
                event_data = event.to_msgpack()
                
                # Create length-prefixed record with HMAC authentication per ADR-002
                record = self._create_record(event_data)
                
                # Write to current log file
                await self.current_log_file.write(record)
                
                # Sync based on policy per ADR-002
                if self.sync_policy == "fsync":
                    await self.current_log_file.flush()
                    os.fsync(self.current_log_file.fileno())
                elif self.sync_policy == "fdatasync":
                    await self.current_log_file.flush()
                    os.fdatasync(self.current_log_file.fileno())
                
                # Update index
                self._update_index(event)
                
                # Check if rotation needed
                await self._check_rotation()
                
            # Track performance
            self._append_times.append(time.time() - start_time)
            if len(self._append_times) > 1000:
                self._append_times = self._append_times[-1000:]
                
        except Exception as e:
            self._error_counts["append"] += 1
            raise EventStoreError(f"Failed to append event: {e}")
    
    async def append_batch(self, batch: EventBatch, agent_id: Optional[str] = None) -> None:
        """Atomically append multiple events with security validation per ADR-003."""
        if not batch.events:
            raise EventStoreError("Cannot append empty batch")
        
        # Security validation
        try:
            # Validate entire batch for security issues
            self.input_validator.validate_batch(batch)
            
            # Authorize write operation
            if agent_id:
                identity = self.authorizer.authorize_write(
                    agent_id, batch_size=len(batch.events)
                )
                # Set source agent for all events in batch
                for event in batch.events:
                    if not event.source_agent:
                        event.source_agent = agent_id
        
        except (SecurityError, AuthenticationError, AuthorizationError) as e:
            raise EventStoreError(f"Security validation failed: {e}")
        
        # Resource limits check
        total_size = sum(event.calculate_size_bytes() for event in batch.events)
        try:
            self.resource_limiter.check_disk_usage(self.data_dir, total_size)
            self.resource_limiter.check_available_space(self.data_dir, total_size * 10)  # Buffer
        except SecurityError as e:
            raise EventStoreError(f"Resource limit exceeded: {e}")
        
        start_time = time.time()
        
        try:
            async with self.write_lock:
                start_sequence = self.current_sequence + 1
                
                # Additional batch size validation (already checked in security validation)
                if total_size > 10 * 1024 * 1024:  # 10MB batch limit
                    raise EventStoreError(f"Batch size {total_size} exceeds 10MB limit")
                
                # Assign sequence numbers
                for i, event in enumerate(batch.events):
                    event.sequence = start_sequence + i
                
                # Serialize all events
                records = []
                for event in batch.events:
                    event_data = event.to_msgpack()
                    record = self._create_record(event_data)
                    records.append(record)
                
                # Write all records atomically
                batch_data = b''.join(records)
                await self.current_log_file.write(batch_data)
                
                # Sync once for entire batch per ADR-003
                if self.sync_policy == "fsync":
                    await self.current_log_file.flush()
                    os.fsync(self.current_log_file.fileno())
                elif self.sync_policy == "fdatasync":
                    await self.current_log_file.flush()
                    os.fdatasync(self.current_log_file.fileno())
                
                # Update sequence and index
                self.current_sequence += len(batch.events)
                for event in batch.events:
                    self._update_index(event)
                
                await self._check_rotation()
                
            # Track performance
            self._append_times.append(time.time() - start_time)
            if len(self._append_times) > 1000:
                self._append_times = self._append_times[-1000:]
                
        except Exception as e:
            self._error_counts["append"] += 1
            raise EventStoreError(f"Failed to append batch: {e}")
    
    async def query(self, query: EventQuery, agent_id: Optional[str] = None) -> QueryResult:
        """Query events with security authorization and filtering."""
        # Security authorization
        if agent_id:
            try:
                identity = self.authorizer.authorize_query(agent_id)
                # TODO: Apply agent-specific query restrictions based on identity.allowed_aggregates
            except (AuthenticationError, AuthorizationError) as e:
                raise EventStoreError(f"Query authorization failed: {e}")
        
        start_time = time.time()
        
        try:
            events = []
            events_scanned = 0
            events_returned = 0
            
            # Get relevant log files based on index
            log_files = await self._get_log_files_for_query(query)
            
            for log_file_path in log_files:
                if events_returned >= query.limit:
                    break
                    
                async for event in self._read_log_file(log_file_path, query.filter):
                    events_scanned += 1
                    
                    # Handle offset
                    if events_scanned <= query.offset:
                        continue
                    
                    # Apply limit
                    if events_returned >= query.limit:
                        break
                    
                    events.append(event)
                    events_returned += 1
            
            # Apply ordering if needed
            if query.order_by == "timestamp":
                events.sort(key=lambda e: e.timestamp, reverse=not query.ascending)
            elif query.order_by == "sequence":
                events.sort(key=lambda e: e.sequence or 0, reverse=not query.ascending)
            
            execution_time = (time.time() - start_time) * 1000  # ms
            self._query_times.append(execution_time)
            if len(self._query_times) > 1000:
                self._query_times = self._query_times[-1000:]
            
            return QueryResult(
                events=events,
                total_count=events_scanned,  # Approximation
                has_more=events_scanned > query.offset + query.limit,
                query=query,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self._error_counts["query"] += 1
            raise EventStoreError(f"Query failed: {e}")
    
    async def get_health(self) -> SystemHealth:
        """Get current system health status."""
        try:
            # Calculate disk usage
            disk_usage = sum(f.stat().st_size for f in self.data_dir.rglob("*.log*"))
            disk_free = os.statvfs(self.data_dir).f_bavail * os.statvfs(self.data_dir).f_frsize
            
            # Calculate performance metrics
            avg_append_latency = sum(self._append_times) / len(self._append_times) * 1000 if self._append_times else 0
            avg_query_latency = sum(self._query_times) / len(self._query_times) if self._query_times else 0
            
            # Calculate error rates
            total_appends = len(self._append_times) + self._error_counts["append"]
            total_queries = len(self._query_times) + self._error_counts["query"]
            
            append_error_rate = self._error_counts["append"] / total_appends if total_appends > 0 else 0
            query_error_rate = self._error_counts["query"] / total_queries if total_queries > 0 else 0
            
            # Count log files
            log_files = list(self.data_dir.glob("*.log*"))
            
            return SystemHealth(
                event_store_status=self.status,
                current_sequence=self.current_sequence,
                events_per_second=len(self._append_times) / 60 if self._append_times else 0,  # Last minute
                disk_usage_bytes=disk_usage,
                disk_free_bytes=disk_free,
                log_file_count=len(log_files),
                average_append_latency_ms=avg_append_latency,
                average_query_latency_ms=avg_query_latency,
                append_error_rate=append_error_rate,
                query_error_rate=query_error_rate
            )
            
        except Exception as e:
            raise EventStoreError(f"Failed to get health status: {e}")
    
    # Authentication and Authorization Methods
    
    def authenticate_agent(self, agent_id: str, token: str, role: str = "agent") -> AgentIdentity:
        """Authenticate an agent for event store access.
        
        Args:
            agent_id: Unique agent identifier
            token: Authentication token
            role: Agent role (guest, agent, expert_agent, system_agent, admin)
            
        Returns:
            AgentIdentity for authenticated agent
            
        Raises:
            EventStoreError: If authentication fails
        """
        try:
            from .auth import AgentRole
            agent_role = AgentRole(role)
            return self.authenticator.authenticate(agent_id, token, agent_role)
        except (AuthenticationError, ValueError) as e:
            raise EventStoreError(f"Authentication failed: {e}")
    
    def create_agent_token(self, agent_id: str) -> str:
        """Create authentication token for agent (for testing/setup).
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Authentication token
        """
        return self.authenticator.create_token(agent_id)
    
    def revoke_agent_access(self, agent_id: str) -> None:
        """Revoke agent access to event store.
        
        Args:
            agent_id: Agent identifier to revoke
        """
        self.authenticator.revoke_authentication(agent_id)
    
    def get_agent_identity(self, agent_id: str) -> Optional[AgentIdentity]:
        """Get authenticated agent identity.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            AgentIdentity if authenticated, None otherwise
        """
        return self.authenticator.get_authenticated_agent(agent_id)
    
    # Private implementation methods
    
    def _create_record(self, event_data: bytes) -> bytes:
        """Create length-prefixed record with HMAC authentication per ADR-002."""
        # Calculate HMAC for authentication (not just integrity)
        hmac_signature = hmac.new(self.hmac_secret, event_data, hashlib.sha256).digest()
        
        # Create record: [length:4][hmac:32][data:length]
        length = len(event_data)
        record = length.to_bytes(4, 'big') + hmac_signature + event_data
        return record
    
    async def _recover_state(self) -> None:
        """Recover state from existing log files."""
        log_files = sorted(self.data_dir.glob("events_*.log"))
        
        if not log_files:
            self.current_sequence = 0
            return
        
        # Find latest sequence number
        max_sequence = 0
        for log_file in log_files:
            async for event in self._read_log_file(log_file):
                if event.sequence and event.sequence > max_sequence:
                    max_sequence = event.sequence
        
        self.current_sequence = max_sequence
    
    async def _open_current_log_file(self) -> None:
        """Open current log file for writing with security validation."""
        log_number = len(list(self.data_dir.glob("events_*.log"))) + 1
        
        # Validate log file path for security
        log_filename = f"events_{log_number:06d}.log"
        try:
            # Ensure log filename doesn't contain directory traversal
            if '/' in log_filename or '\\' in log_filename or '..' in log_filename:
                raise SecurityError(f"Invalid log filename: {log_filename}")
            
            self.current_log_path = self.data_dir / log_filename
            
            # Additional validation - ensure path is within data directory
            self.path_validator.validate_path(str(self.current_log_path))
            
        except SecurityError as e:
            raise EventStoreError(f"Log file security validation failed: {e}")
        
        # Track file handle for resource limiting
        try:
            self.resource_limiter.track_file_handle(increment=True)
        except SecurityError as e:
            raise EventStoreError(f"File handle limit exceeded: {e}")
        
        try:
            # Open in append mode with binary write
            self.current_log_file = await aiofiles.open(
                self.current_log_path, 'ab'
            )
        except Exception as e:
            # Release file handle on failure
            self.resource_limiter.track_file_handle(increment=False)
            raise
    
    async def _check_rotation(self) -> None:
        """Check if log rotation is needed per ADR-002."""
        if not self.current_log_path.exists():
            return
        
        file_size = self.current_log_path.stat().st_size
        if file_size >= self.max_file_size:
            await self._rotate_log_file()
    
    async def _rotate_log_file(self) -> None:
        """Rotate current log file."""
        # Close current file
        await self.current_log_file.close()
        # Release file handle tracking for closed file
        self.resource_limiter.track_file_handle(increment=False)
        
        # Compress if enabled
        if self.compression_enabled:
            await self._compress_log_file(self.current_log_path)
        
        # Open new log file (will increment file handle tracking)
        await self._open_current_log_file()
    
    async def _compress_log_file(self, log_path: Path) -> None:
        """Compress rotated log file per ADR-002."""
        compressed_path = log_path.with_suffix('.log.gz')
        
        with open(log_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                f_out.writelines(f_in)
        
        # Remove original
        os.unlink(log_path)
    
    async def _read_log_file(self, log_path: Path, event_filter: Optional[EventFilter] = None) -> AsyncIterator[Event]:
        """Read and parse events from log file."""
        if log_path.suffix == '.gz':
            # Decompress and read
            with gzip.open(log_path, 'rb') as f:
                content = f.read()
            async for event in self._parse_log_content(content, event_filter):
                yield event
        else:
            # Read directly
            async with aiofiles.open(log_path, 'rb') as f:
                content = await f.read()
            async for event in self._parse_log_content(content, event_filter):
                yield event
    
    async def _parse_log_content(self, content: bytes, event_filter: Optional[EventFilter] = None) -> AsyncIterator[Event]:
        """Parse log file content into events."""
        offset = 0
        
        while offset < len(content):
            if offset + 4 > len(content):
                break
            
            # Read length
            length = int.from_bytes(content[offset:offset+4], 'big')
            offset += 4
            
            if offset + 32 + length > len(content):
                break
            
            # Read checksum and data
            expected_checksum = content[offset:offset+32]
            offset += 32
            
            event_data = content[offset:offset+length]
            offset += length
            
            # Verify HMAC authentication
            expected_hmac = hmac.new(self.hmac_secret, event_data, hashlib.sha256).digest()
            if not hmac.compare_digest(expected_checksum, expected_hmac):
                continue  # Skip unauthenticated record
            
            try:
                # Deserialize event
                event = Event.from_msgpack(event_data)
                
                # Apply filter
                if event_filter is None or self._matches_filter(event, event_filter):
                    yield event
            except (ValidationError, ValueError):
                continue  # Skip invalid events
    
    def _matches_filter(self, event: Event, event_filter: EventFilter) -> bool:
        """Check if event matches filter criteria."""
        if event_filter.event_types and event.event_type not in event_filter.event_types:
            return False
        
        if event_filter.aggregate_ids and event.aggregate_id not in event_filter.aggregate_ids:
            return False
        
        if event_filter.aggregate_types and event.aggregate_type not in event_filter.aggregate_types:
            return False
        
        if event_filter.source_agents and event.source_agent not in event_filter.source_agents:
            return False
        
        if event_filter.source_components and event.source_component not in event_filter.source_components:
            return False
        
        if event_filter.after_timestamp and event.timestamp <= event_filter.after_timestamp:
            return False
        
        if event_filter.before_timestamp and event.timestamp >= event_filter.before_timestamp:
            return False
        
        if event_filter.after_sequence and (event.sequence is None or event.sequence <= event_filter.after_sequence):
            return False
        
        if event_filter.before_sequence and (event.sequence is None or event.sequence >= event_filter.before_sequence):
            return False
        
        if event_filter.correlation_id and event.correlation_id != event_filter.correlation_id:
            return False
        
        if event_filter.causation_id and event.causation_id != event_filter.causation_id:
            return False
        
        return True
    
    def _update_index(self, event: Event) -> None:
        """Update in-memory index for fast queries."""
        # Index by event type
        if event.event_type.value not in self._index:
            self._index[event.event_type.value] = set()
        self._index[event.event_type.value].add(event.sequence)
        
        # Index by aggregate
        aggregate_key = f"aggregate:{event.aggregate_type}:{event.aggregate_id}"
        if aggregate_key not in self._index:
            self._index[aggregate_key] = set()
        self._index[aggregate_key].add(event.sequence)
    
    async def _get_log_files_for_query(self, query: EventQuery) -> List[Path]:
        """Get relevant log files for query based on index."""
        # For now, return all log files
        # TODO: Implement smarter file selection based on index
        log_files = sorted(self.data_dir.glob("events_*.log*"))
        return log_files
    
    async def _rebuild_index(self) -> None:
        """Rebuild index from all log files."""
        self._index = {}
        
        log_files = sorted(self.data_dir.glob("events_*.log*"))
        for log_file in log_files:
            async for event in self._read_log_file(log_file):
                self._update_index(event)