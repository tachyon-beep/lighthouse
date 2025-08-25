"""Input validation and security controls for Event Store."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from .models import Event, EventBatch


class SecurityError(Exception):
    """Security-related validation error."""
    pass


class PathValidator:
    """Secure path validation to prevent directory traversal attacks."""
    
    def __init__(self, allowed_base_dirs: Optional[List[str]] = None):
        """Initialize with allowed base directories.
        
        Args:
            allowed_base_dirs: List of allowed base directory paths. 
                              Defaults to current working directory.
        """
        if allowed_base_dirs is None:
            allowed_base_dirs = [os.getcwd()]
        
        # Convert to absolute paths and normalize
        self.allowed_base_dirs = []
        for base_dir in allowed_base_dirs:
            abs_path = os.path.abspath(base_dir)
            self.allowed_base_dirs.append(abs_path)
    
    def validate_path(self, path: str) -> Path:
        """Validate and normalize a file path to prevent directory traversal.
        
        Args:
            path: Path to validate
            
        Returns:
            Validated and normalized Path object
            
        Raises:
            SecurityError: If path is unsafe or outside allowed directories
        """
        if not path or not isinstance(path, str):
            raise SecurityError("Path must be a non-empty string")
        
        # Check for obviously malicious patterns
        dangerous_patterns = [
            r'\.\./',       # Directory traversal
            r'\.\.\\',      # Windows directory traversal  
            r'/\.\./',      # Absolute directory traversal
            r'\\\.\.\\',    # Windows absolute directory traversal
            r'^\.\./',      # Leading directory traversal
            r'^\.\.\\',     # Windows leading directory traversal
            r'/etc/',       # System directories
            r'/usr/',
            r'/var/',
            r'/boot/',
            r'/sys/',
            r'/proc/',
            r'/dev/',
            r'file://',     # File URLs
            r'ftp://',      # FTP URLs
            r'http://',     # HTTP URLs
            r'https://',    # HTTPS URLs
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                raise SecurityError(f"Dangerous path pattern detected: {path}")
        
        # Convert to absolute path and resolve all symbolic links to prevent symlink attacks
        try:
            abs_path = os.path.abspath(path)
            # Critical security fix: resolve symbolic links to prevent bypass
            resolved_path = os.path.realpath(abs_path)
        except (OSError, ValueError) as e:
            raise SecurityError(f"Invalid path: {path}") from e
        
        # Check if resolved path is within allowed base directories
        path_is_allowed = False
        for allowed_base in self.allowed_base_dirs:
            try:
                # Resolve the base directory as well to prevent symlink bypass
                resolved_base = os.path.realpath(allowed_base)
                # Use os.path.commonpath to check containment
                common = os.path.commonpath([resolved_path, resolved_base])
                if common == resolved_base:
                    path_is_allowed = True
                    break
            except ValueError:
                # Paths are on different drives (Windows) or other issues
                continue
        
        if not path_is_allowed:
            raise SecurityError(f"Path traversal attempt blocked: {path} resolves to {resolved_path}")
        
        # Return the resolved path to prevent symlink attacks
        return Path(resolved_path)
    
    def validate_directory(self, path: str) -> Path:
        """Validate directory path and ensure it exists or can be created safely.
        
        Args:
            path: Directory path to validate
            
        Returns:
            Validated Path object
            
        Raises:
            SecurityError: If directory path is unsafe
        """
        validated_path = self.validate_path(path)
        
        # If directory doesn't exist, validate that parent directories are safe
        if not validated_path.exists():
            parent = validated_path.parent
            while not parent.exists() and parent != parent.parent:
                # Validate each parent directory
                self.validate_path(str(parent))
                parent = parent.parent
        
        return validated_path


class InputValidator:
    """Comprehensive input validation for Event Store operations."""
    
    # Maximum sizes to prevent resource exhaustion
    MAX_STRING_LENGTH = 1024 * 1024  # 1MB
    MAX_DICT_SIZE = 1000  # Maximum number of keys
    MAX_NESTED_DEPTH = 10  # Maximum nesting depth
    MAX_AGGREGATE_ID_LENGTH = 256
    MAX_SOURCE_COMPONENT_LENGTH = 256
    MAX_SOURCE_AGENT_LENGTH = 256
    
    # Forbidden patterns in string data
    FORBIDDEN_PATTERNS = [
        r'<script[^>]*>',           # Script tags
        r'javascript:',             # JavaScript URLs
        r'data:text/html',          # Data URLs
        r'vbscript:',              # VBScript URLs
        r'on\w+\s*=',              # Event handlers
        r'eval\s*\(',              # Eval calls
        r'Function\s*\(',          # Function constructor
        r'setTimeout\s*\(',        # setTimeout
        r'setInterval\s*\(',       # setInterval
        r'\\x[0-9a-f]{2}',         # Hex encoded characters
        r'\\u[0-9a-f]{4}',         # Unicode encoded characters
    ]
    
    def __init__(self):
        """Initialize input validator."""
        pass
    
    def validate_event(self, event: Event) -> None:
        """Validate event data for security issues.
        
        Args:
            event: Event to validate
            
        Raises:
            SecurityError: If event contains unsafe data
        """
        if not event:
            raise SecurityError("Event cannot be None")
        
        # Validate string fields
        self._validate_string(event.aggregate_id, "aggregate_id", self.MAX_AGGREGATE_ID_LENGTH)
        self._validate_string(event.aggregate_type, "aggregate_type", self.MAX_AGGREGATE_ID_LENGTH)
        
        if event.source_agent:
            self._validate_string(event.source_agent, "source_agent", self.MAX_SOURCE_AGENT_LENGTH)
        
        self._validate_string(event.source_component, "source_component", self.MAX_SOURCE_COMPONENT_LENGTH)
        
        # Validate data payload
        self._validate_dict(event.data, "event.data")
        
        # Validate metadata
        self._validate_dict(event.metadata, "event.metadata")
        
        # Check event size
        event_size = event.calculate_size_bytes()
        if event_size > 1024 * 1024:  # 1MB limit
            raise SecurityError(f"Event size {event_size} exceeds 1MB limit")
    
    def validate_batch(self, batch: EventBatch) -> None:
        """Validate event batch for security issues.
        
        Args:
            batch: Event batch to validate
            
        Raises:
            SecurityError: If batch contains unsafe data
        """
        if not batch or not batch.events:
            raise SecurityError("Event batch cannot be empty")
        
        if len(batch.events) > 1000:
            raise SecurityError(f"Batch size {len(batch.events)} exceeds 1000 event limit")
        
        # Validate each event
        total_size = 0
        for i, event in enumerate(batch.events):
            try:
                self.validate_event(event)
                total_size += event.calculate_size_bytes()
            except SecurityError as e:
                raise SecurityError(f"Event {i} in batch failed validation: {e}")
        
        # Check total batch size
        if total_size > 10 * 1024 * 1024:  # 10MB limit
            raise SecurityError(f"Batch total size {total_size} exceeds 10MB limit")
    
    def _validate_string(self, value: str, field_name: str, max_length: int) -> None:
        """Validate string field for security issues.
        
        Args:
            value: String value to validate
            field_name: Name of field being validated  
            max_length: Maximum allowed length
            
        Raises:
            SecurityError: If string contains dangerous content
        """
        if not isinstance(value, str):
            raise SecurityError(f"{field_name} must be a string")
        
        if len(value) > max_length:
            raise SecurityError(f"{field_name} length {len(value)} exceeds limit {max_length}")
        
        # Check for dangerous patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                raise SecurityError(f"Dangerous pattern detected in {field_name}: {pattern}")
        
        # Check for null bytes and control characters
        if '\x00' in value:
            raise SecurityError(f"Null byte detected in {field_name}")
        
        # Check for excessive control characters
        control_chars = sum(1 for c in value if ord(c) < 32 and c not in '\t\n\r')
        if control_chars > len(value) * 0.1:  # More than 10% control characters
            raise SecurityError(f"Excessive control characters in {field_name}")
    
    def _validate_dict(self, data: Dict[str, Any], field_name: str, depth: int = 0) -> None:
        """Validate dictionary for security issues.
        
        Args:
            data: Dictionary to validate
            field_name: Name of field being validated
            depth: Current nesting depth
            
        Raises:
            SecurityError: If dictionary contains unsafe data
        """
        if not isinstance(data, dict):
            raise SecurityError(f"{field_name} must be a dictionary")
        
        if depth > self.MAX_NESTED_DEPTH:
            raise SecurityError(f"Dictionary nesting too deep in {field_name}: {depth}")
        
        if len(data) > self.MAX_DICT_SIZE:
            raise SecurityError(f"Dictionary size {len(data)} exceeds limit {self.MAX_DICT_SIZE} in {field_name}")
        
        for key, value in data.items():
            # Validate key
            if not isinstance(key, str):
                raise SecurityError(f"Dictionary key must be string in {field_name}: {type(key)}")
            
            self._validate_string(key, f"{field_name}.key", 256)
            
            # Validate value based on type
            if isinstance(value, str):
                self._validate_string(value, f"{field_name}.{key}", self.MAX_STRING_LENGTH)
            elif isinstance(value, dict):
                self._validate_dict(value, f"{field_name}.{key}", depth + 1)
            elif isinstance(value, list):
                self._validate_list(value, f"{field_name}.{key}", depth)
            elif isinstance(value, (int, float, bool, type(None))):
                # Safe primitive types
                continue
            else:
                raise SecurityError(f"Unsupported data type in {field_name}.{key}: {type(value)}")
    
    def _validate_list(self, data: List[Any], field_name: str, depth: int = 0) -> None:
        """Validate list for security issues.
        
        Args:
            data: List to validate
            field_name: Name of field being validated
            depth: Current nesting depth
            
        Raises:
            SecurityError: If list contains unsafe data
        """
        if not isinstance(data, list):
            raise SecurityError(f"{field_name} must be a list")
        
        if len(data) > 10000:  # Reasonable limit
            raise SecurityError(f"List size {len(data)} exceeds limit 10000 in {field_name}")
        
        for i, item in enumerate(data):
            if isinstance(item, str):
                self._validate_string(item, f"{field_name}[{i}]", self.MAX_STRING_LENGTH)
            elif isinstance(item, dict):
                self._validate_dict(item, f"{field_name}[{i}]", depth + 1)
            elif isinstance(item, list):
                self._validate_list(item, f"{field_name}[{i}]", depth + 1)
            elif isinstance(item, (int, float, bool, type(None))):
                # Safe primitive types
                continue
            else:
                raise SecurityError(f"Unsupported data type in {field_name}[{i}]: {type(item)}")


class ResourceLimiter:
    """Resource exhaustion protection for Event Store operations."""
    
    def __init__(self, 
                 max_disk_usage_bytes: int = 50 * 1024 * 1024 * 1024,  # 50GB
                 max_memory_usage_bytes: int = 1024 * 1024 * 1024,      # 1GB
                 max_open_files: int = 1000):
        """Initialize resource limiter.
        
        Args:
            max_disk_usage_bytes: Maximum disk usage allowed
            max_memory_usage_bytes: Maximum memory usage allowed  
            max_open_files: Maximum open file handles allowed
        """
        self.max_disk_usage_bytes = max_disk_usage_bytes
        self.max_memory_usage_bytes = max_memory_usage_bytes
        self.max_open_files = max_open_files
        self._open_file_count = 0
    
    def check_disk_usage(self, data_dir: Path, new_data_size: int = 0) -> None:
        """Check if disk usage is within limits.
        
        Args:
            data_dir: Event store data directory
            new_data_size: Size of new data being added
            
        Raises:
            SecurityError: If disk usage would exceed limits
        """
        try:
            # Calculate current usage
            current_usage = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
            
            # Check if adding new data would exceed limit
            if current_usage + new_data_size > self.max_disk_usage_bytes:
                raise SecurityError(f"Disk usage would exceed limit: {current_usage + new_data_size} > {self.max_disk_usage_bytes}")
        
        except OSError as e:
            raise SecurityError(f"Failed to check disk usage: {e}")
    
    def check_available_space(self, data_dir: Path, required_space: int) -> None:
        """Check if sufficient disk space is available.
        
        Args:
            data_dir: Event store data directory
            required_space: Required space in bytes
            
        Raises:
            SecurityError: If insufficient space available
        """
        try:
            stat = os.statvfs(data_dir)
            available_space = stat.f_bavail * stat.f_frsize
            
            if available_space < required_space * 2:  # Keep 50% buffer
                raise SecurityError(f"Insufficient disk space: {available_space} < {required_space * 2} (with buffer)")
        
        except OSError as e:
            raise SecurityError(f"Failed to check available space: {e}")
    
    def track_file_handle(self, increment: bool = True) -> None:
        """Track open file handle count.
        
        Args:
            increment: True to increment, False to decrement
            
        Raises:
            SecurityError: If too many files would be open
        """
        if increment:
            if self._open_file_count >= self.max_open_files:
                raise SecurityError(f"Too many open files: {self._open_file_count} >= {self.max_open_files}")
            self._open_file_count += 1
        else:
            self._open_file_count = max(0, self._open_file_count - 1)
    
    def get_file_handle_count(self) -> int:
        """Get current open file handle count."""
        return self._open_file_count