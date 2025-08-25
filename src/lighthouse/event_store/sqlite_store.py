"""
SQLite Event Store Implementation with WAL Mode

Provides persistent, high-performance event storage using SQLite with WAL
(Write-Ahead Logging) mode for improved concurrency and durability.

Features:
- WAL mode for concurrent reads during writes
- Atomic transaction guarantees
- Full-text search on event content
- Optimized indexes for common query patterns
- Event stream ordering preservation
- ACID compliance with crash recovery
"""

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set, Tuple, Any
import aiosqlite
from contextlib import asynccontextmanager

from .models import (
    Event, EventBatch, EventFilter, EventQuery, EventType,
    QueryResult, SnapshotMetadata, SystemHealth
)
from .validation import PathValidator, InputValidator, ResourceLimiter, SecurityError
from .auth import (
    SimpleAuthenticator, Authorizer, AgentIdentity, Permission,
    AuthenticationError, AuthorizationError, create_system_authenticator
)

logger = logging.getLogger(__name__)


class SQLiteEventStoreError(Exception):
    """SQLite Event Store specific errors"""
    pass


class SQLiteEventStore:
    """
    High-performance SQLite-based event store with WAL mode
    
    Provides ACID-compliant event storage with:
    - WAL mode for concurrent read/write access
    - Full-text search capabilities
    - Optimized indexing for query performance
    - Event ordering guarantees
    - Crash recovery and durability
    """
    
    def __init__(self, 
                 db_path: str = "./data/events.db",
                 auth_secret: Optional[str] = None,
                 allowed_base_dirs: Optional[List[str]] = None,
                 wal_mode: bool = True,
                 checkpoint_interval: int = 1000):
        """
        Initialize SQLite Event Store
        
        Args:
            db_path: Path to SQLite database file
            auth_secret: Secret for authentication
            allowed_base_dirs: Allowed directories for security
            wal_mode: Enable WAL mode for better concurrency
            checkpoint_interval: WAL checkpoint interval (number of transactions)
        """
        
        # Security validation
        self.path_validator = PathValidator(allowed_base_dirs)
        validated_db_path = Path(db_path)
        validated_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(validated_db_path)
        
        # Security components
        self.input_validator = InputValidator()
        self.resource_limiter = ResourceLimiter()
        self.authenticator = create_system_authenticator(auth_secret)
        self.authorizer = Authorizer(self.authenticator)
        
        # Configuration
        self.wal_mode = wal_mode
        self.checkpoint_interval = checkpoint_interval
        self.max_event_size = 1024 * 1024  # 1MB
        
        # State tracking
        self.current_sequence = 0
        self.transaction_count = 0
        
        # Database connections
        self._db_pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._max_connections = 10
        
        # Performance tracking
        self._append_times = []
        self._query_times = []
        self._error_counts = {"append": 0, "query": 0}
        
        # Health status
        self.status = "initializing"
        
        # Schema version for migrations
        self.schema_version = 1
    
    async def initialize(self) -> None:
        """Initialize SQLite database with WAL mode and optimizations"""
        try:
            self.status = "initializing"
            logger.info(f"Initializing SQLite Event Store at {self.db_path}")
            
            # Create initial connection and set up database
            await self._setup_database()
            
            # Initialize connection pool
            await self._initialize_connection_pool()
            
            # Recover sequence number
            await self._recover_sequence()
            
            self.status = "healthy-sqlite-wal"
            logger.info("SQLite Event Store initialized successfully with WAL mode")
            
        except Exception as e:
            self.status = "failed"
            logger.error(f"Failed to initialize SQLite Event Store: {e}")
            raise SQLiteEventStoreError(f"Initialization failed: {e}")
    
    async def _setup_database(self) -> None:
        """Set up database schema and optimizations"""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for better concurrency
            if self.wal_mode:
                await db.execute("PRAGMA journal_mode=WAL")
                logger.info("WAL mode enabled for concurrent access")
            
            # Performance optimizations
            await db.execute("PRAGMA synchronous=NORMAL")  # Balance durability/performance
            await db.execute("PRAGMA cache_size=10000")     # 10MB cache
            await db.execute("PRAGMA temp_store=MEMORY")    # Use memory for temp tables
            await db.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
            
            # Create events table with optimized schema
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    sequence_id INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,  -- Unix timestamp for fast sorting
                    agent_id TEXT,
                    aggregate_id TEXT,
                    aggregate_version INTEGER,
                    event_data TEXT NOT NULL,    -- JSON payload
                    metadata TEXT,               -- Additional metadata JSON
                    checksum TEXT,               -- Event integrity checksum
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
            """)
            
            # Create full-text search table for event content
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    event_id UNINDEXED,
                    event_type,
                    agent_id, 
                    content,
                    content=events,
                    content_rowid=sequence_id
                )
            """)
            
            # Create optimized indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
                "CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id)",
                "CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, aggregate_version)",
                "CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON events(event_type, timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_events_agent_timestamp ON events(agent_id, timestamp)"
            ]
            
            for index_sql in indexes:
                await db.execute(index_sql)
            
            # Create metadata table for store information
            await db.execute("""
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
            """)
            
            # Set schema version
            await db.execute(
                "INSERT OR REPLACE INTO store_metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(self.schema_version))
            )
            
            await db.commit()
            logger.info("Database schema created and optimized")
    
    async def _initialize_connection_pool(self) -> None:
        """Initialize connection pool for concurrent access"""
        async with self._pool_lock:
            for _ in range(self._max_connections):
                conn = await aiosqlite.connect(self.db_path)
                
                # Configure connection for optimal performance
                if self.wal_mode:
                    await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA cache_size=5000")
                
                self._db_pool.append(conn)
        
        logger.info(f"Connection pool initialized with {len(self._db_pool)} connections")
    
    @asynccontextmanager
    async def _get_connection(self):
        """Get connection from pool"""
        async with self._pool_lock:
            if not self._db_pool:
                # Create new connection if pool is empty
                conn = await aiosqlite.connect(self.db_path)
                if self.wal_mode:
                    await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
            else:
                conn = self._db_pool.pop()
        
        try:
            yield conn
        finally:
            async with self._pool_lock:
                self._db_pool.append(conn)
    
    async def _recover_sequence(self) -> None:
        """Recover the current sequence number from database"""
        async with self._get_connection() as db:
            cursor = await db.execute("SELECT MAX(sequence_id) FROM events")
            row = await cursor.fetchone()
            self.current_sequence = (row[0] or 0)
            logger.info(f"Recovered sequence number: {self.current_sequence}")
    
    async def append_event(self, event: Event, agent_id: AgentIdentity) -> int:
        """
        Append event to SQLite database with ACID guarantees
        
        Args:
            event: Event to append
            agent_id: Agent requesting the append
            
        Returns:
            Sequence ID of the appended event
        """
        start_time = time.perf_counter()
        
        try:
            # Security validation
            await self.authorizer.check_permission(agent_id, Permission.EVENT_WRITE)
            self.input_validator.validate_event(event)
            
            # Size validation
            event_json = json.dumps(event.model_dump())
            if len(event_json.encode('utf-8')) > self.max_event_size:
                raise SQLiteEventStoreError(f"Event too large: {len(event_json)} bytes")
            
            async with self._get_connection() as db:
                # Begin transaction
                await db.execute("BEGIN IMMEDIATE")
                
                try:
                    # Increment sequence
                    self.current_sequence += 1
                    sequence_id = self.current_sequence
                    
                    # Calculate timestamp
                    timestamp = int(event.timestamp.timestamp() * 1000000)  # Microsecond precision
                    
                    # Calculate checksum for integrity
                    checksum = self._calculate_event_checksum(event, sequence_id)
                    
                    # Insert event
                    await db.execute("""
                        INSERT INTO events (
                            sequence_id, event_id, event_type, timestamp,
                            agent_id, aggregate_id, aggregate_version,
                            event_data, metadata, checksum
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sequence_id,
                        event.event_id,
                        event.event_type.value,
                        timestamp,
                        event.agent_id,
                        event.aggregate_id,
                        event.aggregate_version,
                        event_json,
                        json.dumps(event.metadata or {}),
                        checksum
                    ))
                    
                    # Update FTS index
                    fts_content = self._extract_searchable_content(event)
                    await db.execute("""
                        INSERT INTO events_fts (event_id, event_type, agent_id, content)
                        VALUES (?, ?, ?, ?)
                    """, (event.event_id, event.event_type.value, event.agent_id, fts_content))
                    
                    # Commit transaction
                    await db.commit()
                    
                    # Track performance
                    duration = time.perf_counter() - start_time
                    self._append_times.append(duration)
                    
                    # Periodic WAL checkpoint
                    self.transaction_count += 1
                    if self.transaction_count % self.checkpoint_interval == 0:
                        await self._checkpoint_wal()
                    
                    logger.debug(f"Event {event.event_id} appended with sequence {sequence_id}")
                    return sequence_id
                    
                except Exception as e:
                    await db.rollback()
                    raise
                    
        except Exception as e:
            self._error_counts["append"] += 1
            logger.error(f"Failed to append event {event.event_id}: {e}")
            raise SQLiteEventStoreError(f"Append failed: {e}")
    
    async def query_events(self, query: EventQuery, agent_id: AgentIdentity) -> QueryResult:
        """
        Query events from SQLite with optimized performance
        
        Args:
            query: Query parameters
            agent_id: Agent requesting the query
            
        Returns:
            Query result with events and metadata
        """
        start_time = time.perf_counter()
        
        try:
            # Security validation
            await self.authorizer.check_permission(agent_id, Permission.EVENT_READ)
            self.input_validator.validate_query(query)
            
            async with self._get_connection() as db:
                # Build optimized SQL query
                sql_query, params = self._build_sql_query(query)
                
                # Execute query
                cursor = await db.execute(sql_query, params)
                rows = await cursor.fetchall()
                
                # Convert rows to events
                events = []
                for row in rows:
                    event_data = json.loads(row[7])  # event_data column
                    event = Event(**event_data)
                    events.append(event)
                
                # Get total count for pagination
                count_sql, count_params = self._build_count_query(query)
                count_cursor = await db.execute(count_sql, count_params)
                total_count = (await count_cursor.fetchone())[0]
                
                # Track performance
                duration = time.perf_counter() - start_time
                self._query_times.append(duration)
                
                result = QueryResult(
                    events=events,
                    total_count=total_count,
                    has_more=len(events) == query.limit,
                    query_time_ms=int(duration * 1000),
                    from_sequence=rows[0][0] if rows else None,  # sequence_id
                    to_sequence=rows[-1][0] if rows else None
                )
                
                logger.debug(f"Query returned {len(events)} events in {duration*1000:.2f}ms")
                return result
                
        except Exception as e:
            self._error_counts["query"] += 1
            logger.error(f"Query failed: {e}")
            raise SQLiteEventStoreError(f"Query failed: {e}")
    
    def _build_sql_query(self, query: EventQuery) -> Tuple[str, List[Any]]:
        """Build optimized SQL query from EventQuery"""
        conditions = []
        params = []
        
        # Base query with optimized ordering
        sql = """
        SELECT sequence_id, event_id, event_type, timestamp, agent_id,
               aggregate_id, aggregate_version, event_data, metadata, checksum
        FROM events
        WHERE 1=1
        """
        
        # Add conditions
        if query.event_types:
            placeholders = ','.join('?' * len(query.event_types))
            conditions.append(f"event_type IN ({placeholders})")
            params.extend([et.value for et in query.event_types])
        
        if query.agent_id:
            conditions.append("agent_id = ?")
            params.append(query.agent_id)
        
        if query.aggregate_id:
            conditions.append("aggregate_id = ?")
            params.append(query.aggregate_id)
        
        if query.from_sequence:
            conditions.append("sequence_id >= ?")
            params.append(query.from_sequence)
        
        if query.to_sequence:
            conditions.append("sequence_id <= ?")
            params.append(query.to_sequence)
        
        if query.from_timestamp:
            conditions.append("timestamp >= ?")
            params.append(int(query.from_timestamp.timestamp() * 1000000))
        
        if query.to_timestamp:
            conditions.append("timestamp <= ?")
            params.append(int(query.to_timestamp.timestamp() * 1000000))
        
        # Add conditions to query
        if conditions:
            sql += " AND " + " AND ".join(conditions)
        
        # Ordering and limits
        sql += " ORDER BY sequence_id"
        if query.limit:
            sql += f" LIMIT {query.limit}"
        
        return sql, params
    
    def _build_count_query(self, query: EventQuery) -> Tuple[str, List[Any]]:
        """Build count query for total results"""
        sql, params = self._build_sql_query(query)
        
        # Replace SELECT clause with COUNT
        count_sql = sql.replace(
            "SELECT sequence_id, event_id, event_type, timestamp, agent_id, aggregate_id, aggregate_version, event_data, metadata, checksum",
            "SELECT COUNT(*)"
        )
        
        # Remove LIMIT clause for count
        if " LIMIT " in count_sql:
            count_sql = count_sql[:count_sql.find(" LIMIT ")]
        
        return count_sql, params
    
    def _calculate_event_checksum(self, event: Event, sequence_id: int) -> str:
        """Calculate integrity checksum for event"""
        import hashlib
        content = f"{sequence_id}:{event.event_id}:{event.event_type.value}:{event.data}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]  # First 16 chars
    
    def _extract_searchable_content(self, event: Event) -> str:
        """Extract searchable content for FTS index"""
        content_parts = []
        
        # Add event data if it contains text
        if isinstance(event.data, dict):
            for key, value in event.data.items():
                if isinstance(value, str):
                    content_parts.append(value)
        elif isinstance(event.data, str):
            content_parts.append(event.data)
        
        # Add metadata
        if event.metadata:
            for key, value in event.metadata.items():
                if isinstance(value, str):
                    content_parts.append(value)
        
        return " ".join(content_parts)
    
    async def _checkpoint_wal(self) -> None:
        """Perform WAL checkpoint for durability"""
        try:
            async with self._get_connection() as db:
                await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")
    
    async def full_text_search(self, 
                             search_term: str, 
                             agent_id: AgentIdentity,
                             limit: int = 100) -> List[Event]:
        """
        Perform full-text search on event content
        
        Args:
            search_term: Text to search for
            agent_id: Agent performing search
            limit: Maximum results to return
            
        Returns:
            List of matching events
        """
        try:
            await self.authorizer.check_permission(agent_id, Permission.EVENT_READ)
            
            async with self._get_connection() as db:
                cursor = await db.execute("""
                    SELECT e.event_data 
                    FROM events e
                    JOIN events_fts fts ON e.sequence_id = fts.rowid
                    WHERE events_fts MATCH ?
                    ORDER BY bm25(events_fts)
                    LIMIT ?
                """, (search_term, limit))
                
                rows = await cursor.fetchall()
                
                events = []
                for row in rows:
                    event_data = json.loads(row[0])
                    events.append(Event(**event_data))
                
                logger.info(f"Full-text search for '{search_term}' returned {len(events)} results")
                return events
                
        except Exception as e:
            logger.error(f"Full-text search failed: {e}")
            raise SQLiteEventStoreError(f"Search failed: {e}")
    
    async def get_health(self) -> SystemHealth:
        """Get SQLite Event Store health status"""
        try:
            async with self._get_connection() as db:
                # Check database accessibility
                cursor = await db.execute("SELECT COUNT(*) FROM events")
                total_events = (await cursor.fetchone())[0]
                
                # Get WAL info
                wal_info = {}
                if self.wal_mode:
                    wal_cursor = await db.execute("PRAGMA wal_checkpoint")
                    wal_info = dict(await wal_cursor.fetchone())
            
            # Calculate performance metrics
            avg_append_time = sum(self._append_times[-100:]) / len(self._append_times[-100:]) if self._append_times else 0
            avg_query_time = sum(self._query_times[-100:]) / len(self._query_times[-100:]) if self._query_times else 0
            
            return SystemHealth(
                status=self.status,
                total_events=total_events,
                current_sequence=self.current_sequence,
                storage_type="sqlite-wal",
                performance_metrics={
                    "avg_append_time_ms": avg_append_time * 1000,
                    "avg_query_time_ms": avg_query_time * 1000,
                    "append_errors": self._error_counts["append"],
                    "query_errors": self._error_counts["query"],
                    "transaction_count": self.transaction_count,
                    "wal_info": wal_info
                },
                storage_info={
                    "database_path": self.db_path,
                    "wal_mode": self.wal_mode,
                    "connection_pool_size": len(self._db_pool),
                    "max_event_size": self.max_event_size,
                    "checkpoint_interval": self.checkpoint_interval
                }
            )
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return SystemHealth(
                status="unhealthy",
                error=str(e),
                storage_type="sqlite-wal"
            )
    
    async def shutdown(self) -> None:
        """Clean shutdown with WAL checkpoint"""
        try:
            logger.info("Shutting down SQLite Event Store...")
            
            # Final WAL checkpoint
            if self.wal_mode:
                await self._checkpoint_wal()
            
            # Close all connections
            async with self._pool_lock:
                for conn in self._db_pool:
                    await conn.close()
                self._db_pool.clear()
            
            self.status = "shutdown"
            logger.info("SQLite Event Store shutdown complete")
            
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
            raise SQLiteEventStoreError(f"Shutdown failed: {e}")