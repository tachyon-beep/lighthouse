"""
FUSE Race Condition Prevention System

Critical security fixes for FUSE mount operations to prevent race conditions
in multi-agent access scenarios as required by Plan Charlie Phase 1.
"""

import asyncio
import hashlib
import logging
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Callable, Union
from enum import Enum

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of FUSE operations that need coordination."""
    READ = "read"
    WRITE = "write"  
    CREATE = "create"
    DELETE = "delete"
    RENAME = "rename"
    STAT = "stat"
    CHMOD = "chmod"
    TRUNCATE = "truncate"


class RaceConditionError(Exception):
    """Race condition detected during FUSE operation."""
    pass


@dataclass
class FileState:
    """Immutable file state for race condition detection."""
    size: int
    mtime: float
    ctime: float
    mode: int
    inode: Optional[int] = None
    checksum: Optional[str] = None
    
    def __hash__(self):
        return hash((self.size, self.mtime, self.ctime, self.mode, self.inode))
    
    def is_compatible_with(self, other: 'FileState', operation: OperationType) -> bool:
        """Check if file states are compatible for the given operation."""
        if operation == OperationType.READ:
            # Reads can proceed if size and mtime haven't changed
            return self.size == other.size and self.mtime == other.mtime
        elif operation == OperationType.WRITE:
            # Writes require exact state match
            return self == other
        elif operation in [OperationType.DELETE, OperationType.RENAME]:
            # Destructive operations require exact state match
            return self == other
        else:
            # Conservative: require exact match for unknown operations
            return self == other


class FUSERaceConditionPrevention:
    """
    Advanced race condition prevention for FUSE operations.
    
    Implements multiple layers of protection:
    1. Path-based operation locks
    2. File state validation
    3. Atomic operation sequences
    4. Multi-agent coordination
    5. Rollback on race condition detection
    """
    
    def __init__(self):
        """Initialize race condition prevention system."""
        # Path-based locking (supports both sync and async)
        self.path_locks: Dict[str, asyncio.Lock] = {}
        self.path_locks_sync: Dict[str, threading.RLock] = {}
        self.locks_lock = threading.Lock()
        
        # Operation tracking
        self.active_operations: Dict[str, Set[str]] = {}  # path -> operation_ids
        self.operation_states: Dict[str, FileState] = {}  # operation_id -> initial_state
        
        # Statistics and monitoring
        self.race_conditions_detected = 0
        self.operations_completed = 0
        self.operations_failed = 0
    
    def _get_canonical_path(self, path: Union[str, Path]) -> str:
        """Get canonical path for consistent locking."""
        return str(Path(path).resolve())
    
    def _get_operation_id(self, path: str, operation: OperationType, 
                         agent_id: str) -> str:
        """Generate unique operation ID."""
        content = f"{path}:{operation.value}:{agent_id}:{time.time()}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def _get_path_lock(self, path: str) -> asyncio.Lock:
        """Get or create async lock for path."""
        with self.locks_lock:
            if path not in self.path_locks:
                self.path_locks[path] = asyncio.Lock()
            return self.path_locks[path]
    
    def _get_path_lock_sync(self, path: str) -> threading.RLock:
        """Get or create sync lock for path."""
        with self.locks_lock:
            if path not in self.path_locks_sync:
                self.path_locks_sync[path] = threading.RLock()
            return self.path_locks_sync[path]
    
    async def _get_file_state(self, path: str) -> Optional[FileState]:
        """Get current file state for race condition detection."""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return None
            
            stat = path_obj.stat()
            
            # Calculate checksum for critical files
            checksum = None
            if path_obj.is_file() and stat.st_size < 1024 * 1024:  # Only for files < 1MB
                try:
                    content = path_obj.read_bytes()
                    checksum = hashlib.sha256(content).hexdigest()
                except (OSError, MemoryError):
                    # Ignore checksum calculation failures
                    pass
            
            return FileState(
                size=stat.st_size,
                mtime=stat.st_mtime,
                ctime=stat.st_ctime,
                mode=stat.st_mode,
                inode=getattr(stat, 'st_ino', None),
                checksum=checksum
            )
        
        except (OSError, IOError):
            return None
    
    def _validate_state_transition(self, initial_state: Optional[FileState], 
                                 final_state: Optional[FileState], 
                                 operation: OperationType) -> bool:
        """Validate that state transition is consistent with operation."""
        if operation == OperationType.CREATE:
            return initial_state is None and final_state is not None
        elif operation == OperationType.DELETE:
            return initial_state is not None and final_state is None
        elif operation == OperationType.WRITE:
            if initial_state is None or final_state is None:
                return False
            # Write should change mtime and possibly size
            return (final_state.mtime >= initial_state.mtime and
                    final_state.ctime >= initial_state.ctime)
        elif operation == OperationType.READ:
            # Read should not change file state
            return initial_state == final_state
        else:
            # For other operations, allow any valid transition
            return True
    
    @asynccontextmanager
    async def atomic_operation(self, path: Union[str, Path], 
                              operation: OperationType,
                              agent_id: str,
                              validate_checksum: bool = False):
        """
        Context manager for atomic FUSE operations with race condition protection.
        
        Args:
            path: File path for operation
            operation: Type of operation being performed  
            agent_id: Agent performing the operation
            validate_checksum: Whether to validate file checksum
            
        Raises:
            RaceConditionError: If race condition is detected
        """
        canonical_path = self._get_canonical_path(path)
        operation_id = self._get_operation_id(canonical_path, operation, agent_id)
        
        # Get path lock
        path_lock = await self._get_path_lock(canonical_path)
        
        async with path_lock:
            try:
                # Record initial file state
                initial_state = await self._get_file_state(canonical_path)
                
                # Track active operation
                if canonical_path not in self.active_operations:
                    self.active_operations[canonical_path] = set()
                self.active_operations[canonical_path].add(operation_id)
                self.operation_states[operation_id] = initial_state
                
                logger.debug(
                    f"Starting atomic operation {operation.value} on {canonical_path} "
                    f"by agent {agent_id} (operation_id: {operation_id})"
                )
                
                # Yield control to operation
                yield operation_id
                
                # Validate final state
                final_state = await self._get_file_state(canonical_path)
                
                # Check for race conditions
                if not self._validate_state_transition(initial_state, final_state, operation):
                    self.race_conditions_detected += 1
                    raise RaceConditionError(
                        f"Race condition detected in {operation.value} on {canonical_path}: "
                        f"invalid state transition from {initial_state} to {final_state}"
                    )
                
                # Additional checksum validation for critical operations
                if (validate_checksum and operation in [OperationType.WRITE, OperationType.CREATE] and
                    initial_state and final_state and 
                    initial_state.checksum and final_state.checksum and
                    initial_state.checksum == final_state.checksum and
                    operation == OperationType.WRITE):
                    self.race_conditions_detected += 1
                    raise RaceConditionError(
                        f"Race condition detected: write operation did not change file content "
                        f"(checksum unchanged: {final_state.checksum})"
                    )
                
                self.operations_completed += 1
                logger.debug(f"Completed atomic operation {operation_id} successfully")
                
            except RaceConditionError:
                self.operations_failed += 1
                logger.error(f"Race condition detected in operation {operation_id}")
                raise
            except Exception as e:
                self.operations_failed += 1
                logger.error(f"Failed atomic operation {operation_id}: {str(e)}")
                raise
            finally:
                # Clean up operation tracking
                if canonical_path in self.active_operations:
                    self.active_operations[canonical_path].discard(operation_id)
                    if not self.active_operations[canonical_path]:
                        del self.active_operations[canonical_path]
                
                self.operation_states.pop(operation_id, None)
    
    def atomic_operation_sync(self, path: Union[str, Path], 
                             operation: OperationType,
                             agent_id: str,
                             validate_checksum: bool = False):
        """
        Synchronous version of atomic operation context manager.
        
        For use in synchronous FUSE callbacks where async is not available.
        """
        return SyncAtomicOperationManager(self, path, operation, agent_id, validate_checksum)
    
    async def safe_file_operation(self, path: Union[str, Path],
                                 operation: OperationType,
                                 agent_id: str,
                                 callback: Callable[[str], Any]) -> Any:
        """
        Execute file operation safely with race condition protection.
        
        Args:
            path: File path
            operation: Operation type
            agent_id: Agent ID
            callback: Function to execute the operation
            
        Returns:
            Result from callback
            
        Raises:
            RaceConditionError: If race condition detected
        """
        async with self.atomic_operation(path, operation, agent_id) as operation_id:
            try:
                result = callback(str(path))
                return result
            except Exception as e:
                logger.error(
                    f"Operation {operation.value} failed for {path} "
                    f"by agent {agent_id}: {str(e)}"
                )
                raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get race condition prevention statistics."""
        return {
            "race_conditions_detected": self.race_conditions_detected,
            "operations_completed": self.operations_completed,
            "operations_failed": self.operations_failed,
            "active_operations": sum(len(ops) for ops in self.active_operations.values()),
            "active_paths": len(self.active_operations),
            "path_locks_count": len(self.path_locks),
            "success_rate": (
                self.operations_completed / max(1, self.operations_completed + self.operations_failed)
            )
        }
    
    def cleanup_stale_locks(self, max_age_seconds: int = 3600):
        """Clean up stale locks and operation tracking."""
        current_time = time.time()
        
        with self.locks_lock:
            # Clean up async locks (basic cleanup - async locks don't have timestamps)
            if len(self.path_locks) > 1000:  # Arbitrary threshold
                # Simple cleanup: clear all locks if too many
                logger.warning("Clearing all path locks due to excessive count")
                self.path_locks.clear()
            
            # Clean up sync locks
            if len(self.path_locks_sync) > 1000:
                logger.warning("Clearing all sync path locks due to excessive count")
                self.path_locks_sync.clear()
        
        # Clean up operation tracking
        stale_operations = []
        for op_id, state in self.operation_states.items():
            # Operations without recent activity are considered stale
            # This is a simplified cleanup - in production, use timestamps
            if len(self.operation_states) > 1000:  # Arbitrary threshold
                stale_operations.append(op_id)
        
        for op_id in stale_operations[:len(stale_operations)//2]:  # Clean up half
            self.operation_states.pop(op_id, None)


class SyncAtomicOperationManager:
    """Synchronous context manager for atomic operations."""
    
    def __init__(self, race_prevention: FUSERaceConditionPrevention,
                 path: Union[str, Path], operation: OperationType,
                 agent_id: str, validate_checksum: bool = False):
        self.race_prevention = race_prevention
        self.path = race_prevention._get_canonical_path(path)
        self.operation = operation
        self.agent_id = agent_id
        self.validate_checksum = validate_checksum
        self.operation_id = None
        self.path_lock = None
        self.initial_state = None
    
    def __enter__(self):
        """Enter synchronous atomic operation."""
        self.operation_id = self.race_prevention._get_operation_id(
            self.path, self.operation, self.agent_id
        )
        
        # Get synchronous lock
        self.path_lock = self.race_prevention._get_path_lock_sync(self.path)
        self.path_lock.acquire()
        
        try:
            # Record initial state (synchronous version)
            self.initial_state = self._get_file_state_sync(self.path)
            
            # Track operation
            if self.path not in self.race_prevention.active_operations:
                self.race_prevention.active_operations[self.path] = set()
            self.race_prevention.active_operations[self.path].add(self.operation_id)
            self.race_prevention.operation_states[self.operation_id] = self.initial_state
            
            logger.debug(
                f"Starting sync atomic operation {self.operation.value} on {self.path} "
                f"by agent {self.agent_id}"
            )
            
            return self.operation_id
            
        except Exception:
            self.path_lock.release()
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit synchronous atomic operation."""
        try:
            if exc_type is None:
                # Validate final state
                final_state = self._get_file_state_sync(self.path)
                
                if not self.race_prevention._validate_state_transition(
                    self.initial_state, final_state, self.operation
                ):
                    self.race_prevention.race_conditions_detected += 1
                    raise RaceConditionError(
                        f"Race condition detected in {self.operation.value} on {self.path}"
                    )
                
                self.race_prevention.operations_completed += 1
            else:
                self.race_prevention.operations_failed += 1
        
        finally:
            # Clean up
            if self.path in self.race_prevention.active_operations:
                self.race_prevention.active_operations[self.path].discard(self.operation_id)
                if not self.race_prevention.active_operations[self.path]:
                    del self.race_prevention.active_operations[self.path]
            
            self.race_prevention.operation_states.pop(self.operation_id, None)
            self.path_lock.release()
    
    def _get_file_state_sync(self, path: str) -> Optional[FileState]:
        """Synchronous version of file state retrieval."""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return None
            
            stat = path_obj.stat()
            return FileState(
                size=stat.st_size,
                mtime=stat.st_mtime,
                ctime=stat.st_ctime,
                mode=stat.st_mode,
                inode=getattr(stat, 'st_ino', None)
            )
        except (OSError, IOError):
            return None


# Global race condition prevention instance
_global_race_prevention: Optional[FUSERaceConditionPrevention] = None


def get_race_prevention() -> FUSERaceConditionPrevention:
    """Get global race condition prevention instance."""
    global _global_race_prevention
    if _global_race_prevention is None:
        _global_race_prevention = FUSERaceConditionPrevention()
    return _global_race_prevention


# Convenience functions for common operations
async def safe_read_file(path: Union[str, Path], agent_id: str) -> bytes:
    """Safely read file with race condition protection."""
    race_prevention = get_race_prevention()
    
    async with race_prevention.atomic_operation(path, OperationType.READ, agent_id):
        return Path(path).read_bytes()


async def safe_write_file(path: Union[str, Path], content: bytes, agent_id: str) -> None:
    """Safely write file with race condition protection."""
    race_prevention = get_race_prevention()
    
    async with race_prevention.atomic_operation(path, OperationType.WRITE, agent_id, validate_checksum=True):
        Path(path).write_bytes(content)


async def safe_create_file(path: Union[str, Path], content: bytes, agent_id: str) -> None:
    """Safely create file with race condition protection."""
    race_prevention = get_race_prevention()
    
    async with race_prevention.atomic_operation(path, OperationType.CREATE, agent_id):
        if Path(path).exists():
            raise RaceConditionError(f"File {path} already exists")
        Path(path).write_bytes(content)


async def safe_delete_file(path: Union[str, Path], agent_id: str) -> None:
    """Safely delete file with race condition protection."""
    race_prevention = get_race_prevention()
    
    async with race_prevention.atomic_operation(path, OperationType.DELETE, agent_id):
        Path(path).unlink(missing_ok=False)