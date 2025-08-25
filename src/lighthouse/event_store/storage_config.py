"""
Event Store Storage Configuration

Provides factory functions and configuration management for different
storage backends including file-based and SQLite with WAL mode.
"""

import logging
import os
import secrets
from pathlib import Path
from typing import Dict, Any, Optional, Union

from .store import EventStore
from .sqlite_store import SQLiteEventStore

logger = logging.getLogger(__name__)


class StorageConfig:
    """Configuration for event store storage backends"""
    
    # Storage type constants
    FILE_BASED = "file"
    SQLITE_WAL = "sqlite_wal"
    
    @classmethod
    def create_event_store(cls, 
                          storage_type: str = SQLITE_WAL,
                          **kwargs) -> Union[EventStore, SQLiteEventStore]:
        """
        Create event store instance based on configuration
        
        Args:
            storage_type: Type of storage backend ("file" or "sqlite_wal")
            **kwargs: Configuration parameters for the storage backend
            
        Returns:
            Configured event store instance
        """
        
        if storage_type == cls.SQLITE_WAL:
            return cls._create_sqlite_store(**kwargs)
        elif storage_type == cls.FILE_BASED:
            return cls._create_file_store(**kwargs)
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
    
    @classmethod
    def _create_sqlite_store(cls, 
                           db_path: str = "./data/events.db",
                           auth_secret: Optional[str] = None,
                           wal_mode: bool = True,
                           checkpoint_interval: int = 1000,
                           **kwargs) -> SQLiteEventStore:
        """Create SQLite-based event store with WAL mode"""
        
        logger.info(f"Creating SQLite Event Store with WAL mode at {db_path}")
        
        store = SQLiteEventStore(
            db_path=db_path,
            auth_secret=auth_secret,
            wal_mode=wal_mode,
            checkpoint_interval=checkpoint_interval,
            **kwargs
        )
        
        logger.info("SQLite Event Store created successfully")
        return store
    
    @classmethod
    def _create_file_store(cls,
                          data_dir: str = "./data/events",
                          auth_secret: Optional[str] = None,
                          **kwargs) -> EventStore:
        """Create file-based event store"""
        
        logger.info(f"Creating file-based Event Store at {data_dir}")
        
        store = EventStore(
            data_dir=data_dir,
            auth_secret=auth_secret,
            **kwargs
        )
        
        logger.info("File-based Event Store created successfully")
        return store
    
    @classmethod
    def get_recommended_config(cls, environment: str = "production") -> Dict[str, Any]:
        """
        Get recommended configuration for different environments
        
        Args:
            environment: Environment type ("development", "testing", "production")
            
        Returns:
            Dictionary with recommended configuration
        """
        
        if environment == "development":
            return {
                "storage_type": cls.SQLITE_WAL,
                "db_path": "./dev_data/events.db",
                "wal_mode": True,
                "checkpoint_interval": 100,  # More frequent checkpoints for dev
            }
        elif environment == "testing":
            return {
                "storage_type": cls.SQLITE_WAL,
                "db_path": ":memory:",  # In-memory for tests (WAL won't work)
                "wal_mode": False,      # Disable WAL for in-memory testing
                "checkpoint_interval": 10,
            }
        elif environment == "production":
            return {
                "storage_type": cls.SQLITE_WAL,
                "db_path": "/var/lib/lighthouse/events.db",
                "wal_mode": True,
                "checkpoint_interval": 1000,
                "allowed_base_dirs": ["/var/lib/lighthouse", "./data"],
            }
        else:
            raise ValueError(f"Unknown environment: {environment}")
    
    @classmethod
    def create_for_environment(cls, environment: str = "production", **overrides) -> Union[EventStore, SQLiteEventStore]:
        """
        Create event store with recommended configuration for environment
        
        Args:
            environment: Environment type
            **overrides: Configuration overrides
            
        Returns:
            Configured event store instance
        """
        
        config = cls.get_recommended_config(environment)
        config.update(overrides)
        
        return cls.create_event_store(**config)


# Convenience factory functions
def create_sqlite_event_store(db_path: str = "./data/events.db", 
                             auth_secret: Optional[str] = None,
                             **kwargs) -> SQLiteEventStore:
    """Create SQLite event store with sensible defaults"""
    return StorageConfig.create_event_store(
        storage_type=StorageConfig.SQLITE_WAL,
        db_path=db_path,
        auth_secret=auth_secret,
        **kwargs
    )


def create_file_event_store(data_dir: str = "./data/events",
                           auth_secret: Optional[str] = None,
                           **kwargs) -> EventStore:
    """Create file-based event store with sensible defaults"""
    return StorageConfig.create_event_store(
        storage_type=StorageConfig.FILE_BASED,
        data_dir=data_dir,
        auth_secret=auth_secret,
        **kwargs
    )


def create_production_event_store(auth_secret: str,
                                 db_path: str = "/var/lib/lighthouse/events.db") -> SQLiteEventStore:
    """Create production-ready SQLite event store"""
    return StorageConfig.create_for_environment(
        environment="production",
        auth_secret=auth_secret,
        db_path=db_path
    )


def create_development_event_store(auth_secret: Optional[str] = None) -> SQLiteEventStore:
    """Create development SQLite event store"""
    return StorageConfig.create_for_environment(
        environment="development",
        auth_secret=auth_secret or os.environ.get('LIGHTHOUSE_DEV_SECRET') or secrets.token_urlsafe(32)
    )


# Configuration validation
def validate_storage_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize storage configuration
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Validated and normalized configuration
    """
    
    validated = config.copy()
    
    # Ensure storage_type is valid
    storage_type = validated.get("storage_type", StorageConfig.SQLITE_WAL)
    if storage_type not in [StorageConfig.FILE_BASED, StorageConfig.SQLITE_WAL]:
        raise ValueError(f"Invalid storage_type: {storage_type}")
    
    # Set defaults based on storage type
    if storage_type == StorageConfig.SQLITE_WAL:
        validated.setdefault("db_path", "./data/events.db")
        validated.setdefault("wal_mode", True)
        validated.setdefault("checkpoint_interval", 1000)
    elif storage_type == StorageConfig.FILE_BASED:
        validated.setdefault("data_dir", "./data/events")
    
    # Validate paths (but don't create directories that require elevated permissions)
    if "db_path" in validated and validated["db_path"] != ":memory:":
        db_path = Path(validated["db_path"])
        # Only create directory if we have permission (not system directories)
        if not str(db_path.parent).startswith('/var/') and not str(db_path.parent).startswith('/usr/'):
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                logger.warning(f"Cannot create directory {db_path.parent} due to permissions")
    
    if "data_dir" in validated:
        data_dir = Path(validated["data_dir"])
        # Only create directory if we have permission
        if not str(data_dir).startswith('/var/') and not str(data_dir).startswith('/usr/'):
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                logger.warning(f"Cannot create directory {data_dir} due to permissions")
    
    return validated


# Migration helper
def migrate_file_to_sqlite(file_store: EventStore, 
                          sqlite_store: SQLiteEventStore,
                          batch_size: int = 1000) -> int:
    """
    Migrate events from file-based store to SQLite store
    
    Args:
        file_store: Source file-based event store
        sqlite_store: Target SQLite event store  
        batch_size: Number of events to migrate per batch
        
    Returns:
        Number of events migrated
    """
    
    logger.info("Starting migration from file-based to SQLite storage...")
    
    # This would need to be implemented based on the file store's query interface
    # For now, this is a placeholder for the migration logic
    
    migrated_count = 0
    
    # TODO: Implement actual migration logic
    # - Query all events from file store
    # - Batch insert into SQLite store
    # - Verify integrity
    # - Handle errors gracefully
    
    logger.info(f"Migration completed: {migrated_count} events migrated")
    return migrated_count