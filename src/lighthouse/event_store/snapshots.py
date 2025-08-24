"""Snapshot Management for performance optimization."""

import asyncio
import gzip
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

from .store import EventStore, EventStoreError
from .replay import EventReplayEngine, ReplayError
from .models import SnapshotMetadata

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """Exception raised during snapshot operations."""
    pass


class SnapshotManager:
    """Manages state snapshots for performance optimization."""
    
    def __init__(
        self,
        event_store: EventStore,
        replay_engine: EventReplayEngine,
        data_dir: str = "./data/snapshots"
    ):
        self.event_store = event_store
        self.replay_engine = replay_engine
        
        # Setup data directory
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration from Phase 1 design
        self.snapshot_interval = 10000  # Events between snapshots
        self.compression_enabled = True
        self.retention_days = 30
        self.max_snapshots = 100  # Limit total snapshots
        
        # Validation settings
        self.validation_enabled = True
        self.validation_sample_size = 1000  # Events to validate against
        
    async def create_snapshot(
        self,
        state: Dict[str, Any],
        sequence: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new snapshot at the given sequence number.
        
        Args:
            state: System state to snapshot
            sequence: Event sequence number for this snapshot
            metadata: Optional metadata to include
            
        Returns:
            Snapshot ID
        """
        try:
            # Generate snapshot ID  
            from uuid import uuid4
            snapshot_uuid = uuid4()
            snapshot_id = str(snapshot_uuid)
            
            # Create snapshot data
            snapshot_data = {
                "id": snapshot_id,
                "sequence": sequence,
                "timestamp": datetime.utcnow().isoformat(),
                "state": state,
                "metadata": metadata or {},
                "version": 1,
                "created_by": "snapshot_manager"
            }
            
            # Calculate statistics
            state_size = len(json.dumps(state).encode('utf-8'))
            event_count = sequence
            
            # Write snapshot
            if self.compression_enabled:
                snapshot_path = self.data_dir / f"{snapshot_id}.json.gz"
                await self._write_compressed_snapshot(snapshot_path, snapshot_data)
            else:
                snapshot_path = self.data_dir / f"{snapshot_id}.json"
                await self._write_uncompressed_snapshot(snapshot_path, snapshot_data)
            
            # Calculate checksum
            import hashlib
            checksum = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
            
            # Create metadata record
            snapshot_metadata = SnapshotMetadata(
                aggregate_type="global",  # Global snapshot
                aggregate_id=None,
                event_sequence=sequence,
                event_count=event_count,
                checksum=checksum,
                size_bytes=state_size
            )
            
            # Store metadata
            await self._store_metadata(snapshot_metadata)
            
            logger.info(f"Created snapshot {snapshot_id} at sequence {sequence} ({state_size} bytes)")
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            raise SnapshotError(f"Failed to create snapshot: {e}")
    
    async def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a snapshot by ID.
        
        Args:
            snapshot_id: ID of snapshot to load
            
        Returns:
            Snapshot data or None if not found
        """
        try:
            # Try compressed first
            compressed_path = self.data_dir / f"{snapshot_id}.json.gz"
            if compressed_path.exists():
                return await self._read_compressed_snapshot(compressed_path)
            
            # Try uncompressed
            uncompressed_path = self.data_dir / f"{snapshot_id}.json"
            if uncompressed_path.exists():
                return await self._read_uncompressed_snapshot(uncompressed_path)
            
            logger.warning(f"Snapshot {snapshot_id} not found")
            return None
            
        except Exception as e:
            logger.error(f"Failed to load snapshot {snapshot_id}: {e}")
            raise SnapshotError(f"Failed to load snapshot {snapshot_id}: {e}")
    
    async def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent snapshot.
        
        Returns:
            Latest snapshot data or None if no snapshots exist
        """
        try:
            # Find all snapshot files
            snapshot_files = list(self.data_dir.glob("snapshot_*.json*"))
            
            if not snapshot_files:
                return None
            
            # Sort by modification time (most recent first)
            snapshot_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            # Load the most recent
            latest_file = snapshot_files[0]
            snapshot_id = latest_file.stem
            if snapshot_id.endswith('.json'):
                snapshot_id = snapshot_id[:-5]  # Remove .json extension
            
            return await self.load_snapshot(snapshot_id)
            
        except Exception as e:
            logger.error(f"Failed to get latest snapshot: {e}")
            return None
    
    async def get_snapshot_at_sequence(self, target_sequence: int) -> Optional[Dict[str, Any]]:
        """
        Get the snapshot closest to but not exceeding the target sequence.
        
        Args:
            target_sequence: Target sequence number
            
        Returns:
            Snapshot data or None if no suitable snapshot found
        """
        try:
            # Get all snapshot metadata
            metadata_list = await self._get_all_metadata()
            
            # Filter snapshots at or before target sequence
            suitable_snapshots = [
                meta for meta in metadata_list
                if meta.sequence <= target_sequence
            ]
            
            if not suitable_snapshots:
                return None
            
            # Get the one with highest sequence
            best_snapshot = max(suitable_snapshots, key=lambda x: x.sequence)
            
            return await self.load_snapshot(best_snapshot.snapshot_id)
            
        except Exception as e:
            logger.error(f"Failed to get snapshot at sequence {target_sequence}: {e}")
            return None
    
    async def should_create_snapshot(self, current_sequence: int) -> bool:
        """
        Check if a new snapshot should be created.
        
        Args:
            current_sequence: Current event sequence number
            
        Returns:
            True if snapshot should be created
        """
        try:
            latest = await self.get_latest_snapshot()
            
            if not latest:
                # No snapshots exist, create first one
                return True
            
            # Check if enough events have passed
            last_sequence = latest.get("sequence", 0)
            return current_sequence - last_sequence >= self.snapshot_interval
            
        except Exception as e:
            logger.error(f"Error checking snapshot creation: {e}")
            return False
    
    async def validate_snapshot(
        self,
        snapshot_id: str,
        sample_size: Optional[int] = None
    ) -> bool:
        """
        Validate snapshot by comparing against event replay.
        
        Args:
            snapshot_id: ID of snapshot to validate
            sample_size: Number of events to validate (defaults to configured size)
            
        Returns:
            True if snapshot is valid
        """
        try:
            # Load snapshot
            snapshot_data = await self.load_snapshot(snapshot_id)
            if not snapshot_data:
                return False
            
            snapshot_sequence = snapshot_data.get("sequence", 0)
            snapshot_state = snapshot_data.get("state", {})
            
            # Replay events up to snapshot sequence
            replayed_state = await self.replay_engine.get_state_at_sequence(snapshot_sequence)
            
            # Compare states
            validation_passed = self._compare_states(snapshot_state, replayed_state)
            
            if validation_passed:
                logger.info(f"Snapshot {snapshot_id} validation passed")
            else:
                logger.error(f"Snapshot {snapshot_id} validation failed")
            
            return validation_passed
            
        except Exception as e:
            logger.error(f"Snapshot validation error for {snapshot_id}: {e}")
            return False
    
    async def cleanup_old_snapshots(self) -> int:
        """
        Clean up snapshots older than retention period.
        
        Returns:
            Number of snapshots deleted
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=self.retention_days)
            deleted_count = 0
            
            # Get all snapshot files
            snapshot_files = list(self.data_dir.glob("snapshot_*.json*"))
            
            for snapshot_file in snapshot_files:
                file_time = datetime.fromtimestamp(snapshot_file.stat().st_mtime)
                
                if file_time < cutoff_time:
                    try:
                        snapshot_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old snapshot: {snapshot_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {snapshot_file}: {e}")
            
            # Also clean up metadata files
            metadata_files = list(self.data_dir.glob("*.metadata.json"))
            for metadata_file in metadata_files:
                file_time = datetime.fromtimestamp(metadata_file.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        metadata_file.unlink()
                        logger.debug(f"Deleted old metadata: {metadata_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete metadata {metadata_file}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old snapshots")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Snapshot cleanup error: {e}")
            return 0
    
    async def get_snapshot_statistics(self) -> Dict[str, Any]:
        """Get statistics about snapshots."""
        try:
            snapshot_files = list(self.data_dir.glob("snapshot_*.json*"))
            
            if not snapshot_files:
                return {
                    "total_snapshots": 0,
                    "total_size_bytes": 0,
                    "oldest_snapshot": None,
                    "newest_snapshot": None,
                    "compression_ratio": 0.0
                }
            
            # Calculate statistics
            total_size = sum(f.stat().st_size for f in snapshot_files)
            oldest_file = min(snapshot_files, key=lambda p: p.stat().st_mtime)
            newest_file = max(snapshot_files, key=lambda p: p.stat().st_mtime)
            
            # Get compression statistics
            compressed_files = [f for f in snapshot_files if f.suffix == '.gz']
            compression_ratio = len(compressed_files) / len(snapshot_files) if snapshot_files else 0
            
            return {
                "total_snapshots": len(snapshot_files),
                "total_size_bytes": total_size,
                "oldest_snapshot": oldest_file.stem.replace('.json', ''),
                "newest_snapshot": newest_file.stem.replace('.json', ''),
                "compression_enabled": self.compression_enabled,
                "compression_ratio": compression_ratio,
                "retention_days": self.retention_days,
                "snapshot_interval": self.snapshot_interval
            }
            
        except Exception as e:
            logger.error(f"Error getting snapshot statistics: {e}")
            return {"error": str(e)}
    
    async def _write_compressed_snapshot(self, path: Path, data: Dict[str, Any]):
        """Write compressed snapshot to disk."""
        json_data = json.dumps(data, indent=2).encode('utf-8')
        compressed_data = gzip.compress(json_data)
        
        with open(path, 'wb') as f:
            f.write(compressed_data)
    
    async def _write_uncompressed_snapshot(self, path: Path, data: Dict[str, Any]):
        """Write uncompressed snapshot to disk."""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    async def _read_compressed_snapshot(self, path: Path) -> Dict[str, Any]:
        """Read compressed snapshot from disk."""
        with open(path, 'rb') as f:
            compressed_data = f.read()
        
        json_data = gzip.decompress(compressed_data).decode('utf-8')
        return json.loads(json_data)
    
    async def _read_uncompressed_snapshot(self, path: Path) -> Dict[str, Any]:
        """Read uncompressed snapshot from disk."""
        with open(path, 'r') as f:
            return json.load(f)
    
    async def _store_metadata(self, metadata: SnapshotMetadata):
        """Store snapshot metadata."""
        metadata_path = self.data_dir / f"{metadata.snapshot_id}.metadata.json"
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata.model_dump(), f, indent=2, default=str)
    
    async def _get_all_metadata(self) -> List[SnapshotMetadata]:
        """Get all snapshot metadata."""
        metadata_files = list(self.data_dir.glob("*.metadata.json"))
        metadata_list = []
        
        for metadata_file in metadata_files:
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                    metadata = SnapshotMetadata(**data)
                    metadata_list.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to read metadata {metadata_file}: {e}")
        
        return metadata_list
    
    def _compare_states(self, state1: Dict[str, Any], state2: Dict[str, Any]) -> bool:
        """Compare two states for equality."""
        try:
            # Simple deep comparison
            return json.dumps(state1, sort_keys=True) == json.dumps(state2, sort_keys=True)
        except Exception:
            # Fallback to basic comparison
            return state1 == state2


# Background snapshot management
class AutoSnapshotManager:
    """Automatic snapshot management with background tasks."""
    
    def __init__(self, snapshot_manager: SnapshotManager):
        self.snapshot_manager = snapshot_manager
        self.running = False
        self._background_tasks: set = set()
    
    async def start(self):
        """Start automatic snapshot management."""
        if self.running:
            return
        
        self.running = True
        
        # Start background tasks
        cleanup_task = asyncio.create_task(self._periodic_cleanup())
        validation_task = asyncio.create_task(self._periodic_validation())
        
        self._background_tasks.update([cleanup_task, validation_task])
        
        logger.info("AutoSnapshotManager started")
    
    async def stop(self):
        """Stop automatic snapshot management."""
        self.running = False
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
        logger.info("AutoSnapshotManager stopped")
    
    async def _periodic_cleanup(self):
        """Periodic cleanup task."""
        while self.running:
            try:
                await self.snapshot_manager.cleanup_old_snapshots()
                await asyncio.sleep(3600)  # Run every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")
                await asyncio.sleep(3600)
    
    async def _periodic_validation(self):
        """Periodic validation task."""
        while self.running:
            try:
                # Validate latest snapshot
                latest = await self.snapshot_manager.get_latest_snapshot()
                if latest:
                    snapshot_id = latest.get("id")
                    if snapshot_id:
                        await self.snapshot_manager.validate_snapshot(snapshot_id)
                
                await asyncio.sleep(7200)  # Run every 2 hours
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic validation error: {e}")
                await asyncio.sleep(7200)