"""
Secure Path Validation Utility

Centralized secure path validation to prevent path traversal attacks
across the entire Lighthouse system.
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Set


class PathSecurityError(Exception):
    """Path security violation detected."""
    pass


class SecurePathValidator:
    """
    Enterprise-grade path validation to prevent all forms of path traversal attacks.
    
    This replaces all regex-based path validation with OS-level resolution
    and strict containment checking.
    """
    
    # Known dangerous path patterns
    DANGEROUS_PATTERNS = {
        r'\.\.[\\/]',           # Directory traversal sequences
        r'[\\/]\.\.[\\/]',      # Embedded traversal
        r'^\.\.[\\/]',          # Leading traversal
        r'[\\/]\.\.$',          # Trailing traversal  
        r'[\\/]etc[\\/]',       # System directories
        r'[\\/]usr[\\/]',
        r'[\\/]var[\\/]',
        r'[\\/]boot[\\/]',
        r'[\\/]sys[\\/]',
        r'[\\/]proc[\\/]',
        r'[\\/]dev[\\/]',
        r'^[a-zA-Z]:[\\\/]',    # Windows absolute paths
        # Unix absolute paths validated against allowed bases - not blanket blocked
        r'%[0-9a-fA-F]{2}',     # URL encoded sequences
        r'\\[x|u][0-9a-fA-F]',  # Hex/Unicode escapes
    }
    
    # System directories that should never be accessed directly
    FORBIDDEN_DIRECTORIES = {
        '/etc', '/usr', '/var', '/boot', '/sys', '/proc', '/dev',
        '/root', '/home', '/var/tmp', '/opt',
        'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)',
        'C:\\Users', 'C:\\System Volume Information',
    }
    
    # Allow these directories for temporary/working files
    ALLOWED_SYSTEM_DIRS = {
        '/tmp'
    }
    
    def __init__(self, allowed_base_paths: List[str]):
        """
        Initialize secure path validator.
        
        Args:
            allowed_base_paths: List of base paths that are allowed for access
        """
        self.allowed_base_paths = self._normalize_base_paths(allowed_base_paths)
    
    def _normalize_base_paths(self, base_paths: List[str]) -> List[str]:
        """Normalize and validate base paths."""
        normalized = []
        for path in base_paths:
            try:
                # Resolve to absolute path and follow symlinks
                normalized_path = os.path.realpath(os.path.abspath(path))
                normalized.append(normalized_path)
            except (OSError, ValueError) as e:
                raise PathSecurityError(f"Invalid base path: {path}") from e
        return normalized
    
    def validate_path(self, path: str, allow_creation: bool = False) -> Path:
        """
        Validate path for security and return safe Path object.
        
        Args:
            path: Path to validate
            allow_creation: Whether to allow paths that don't exist yet
            
        Returns:
            Validated Path object
            
        Raises:
            PathSecurityError: If path is unsafe
        """
        if not path or not isinstance(path, str):
            raise PathSecurityError("Path must be a non-empty string")
        
        # Quick pattern-based screening
        self._check_dangerous_patterns(path)
        
        # Resolve path completely (critical security step)
        try:
            resolved_path = os.path.realpath(os.path.abspath(path))
        except (OSError, ValueError) as e:
            raise PathSecurityError(f"Cannot resolve path: {path}") from e
        
        # Check containment within allowed base paths
        if not self._is_path_contained(resolved_path):
            raise PathSecurityError(
                f"Path traversal blocked: {path} resolves to {resolved_path}"
            )
        
        # Check for forbidden system directories
        self._check_forbidden_directories(resolved_path)
        
        # Validate existence if required
        if not allow_creation and not os.path.exists(resolved_path):
            raise PathSecurityError(f"Path does not exist: {resolved_path}")
        
        return Path(resolved_path)
    
    def _check_dangerous_patterns(self, path: str) -> None:
        """Check for known dangerous path patterns."""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                raise PathSecurityError(
                    f"Dangerous path pattern detected: {path} matches {pattern}"
                )
    
    def _is_path_contained(self, resolved_path: str) -> bool:
        """Check if resolved path is within allowed base paths."""
        for base_path in self.allowed_base_paths:
            try:
                # Use os.path.commonpath for robust containment check
                common = os.path.commonpath([resolved_path, base_path])
                if common == base_path:
                    return True
            except ValueError:
                # Different drives on Windows or other path issues
                continue
        return False
    
    def _check_forbidden_directories(self, resolved_path: str) -> None:
        """Check if path attempts to access forbidden system directories."""
        path_lower = resolved_path.lower()
        
        # Check if it's in an allowed system directory first
        for allowed in self.ALLOWED_SYSTEM_DIRS:
            allowed_lower = allowed.lower()
            if path_lower.startswith(allowed_lower):
                if (path_lower == allowed_lower or 
                    path_lower.startswith(allowed_lower + os.sep)):
                    return  # Allowed, don't check forbidden list
        
        # Check forbidden directories
        for forbidden in self.FORBIDDEN_DIRECTORIES:
            forbidden_lower = forbidden.lower()
            if path_lower.startswith(forbidden_lower):
                # Make sure it's actually the directory, not just a prefix
                if (path_lower == forbidden_lower or 
                    path_lower.startswith(forbidden_lower + os.sep)):
                    raise PathSecurityError(
                        f"Access to system directory forbidden: {resolved_path}"
                    )
    
    def create_safe_subpath(self, base_path: str, *path_components: str) -> Path:
        """
        Create a safe path by joining components under a base path.
        
        Args:
            base_path: Base path (must be in allowed bases)
            path_components: Path components to join
            
        Returns:
            Safe Path object
        """
        # Validate base path first
        safe_base = self.validate_path(base_path, allow_creation=True)
        
        # Join components safely
        joined_path = safe_base
        for component in path_components:
            if not component or not isinstance(component, str):
                raise PathSecurityError(f"Invalid path component: {component}")
            
            # Check component for dangerous patterns
            self._check_dangerous_patterns(component)
            
            # Join and validate result
            joined_path = joined_path / component
            
        # Final validation of complete path
        return self.validate_path(str(joined_path), allow_creation=True)


# Global validator instances for different system components
_project_validator: Optional[SecurePathValidator] = None
_fuse_validator: Optional[SecurePathValidator] = None
_event_store_validator: Optional[SecurePathValidator] = None


def get_project_path_validator() -> SecurePathValidator:
    """Get path validator for project files."""
    global _project_validator
    if _project_validator is None:
        project_root = os.environ.get('LIGHTHOUSE_PROJECT_ROOT', os.getcwd())
        _project_validator = SecurePathValidator([project_root])
    return _project_validator


def get_fuse_path_validator() -> SecurePathValidator:
    """Get path validator for FUSE mount operations."""
    global _fuse_validator
    if _fuse_validator is None:
        fuse_root = os.environ.get('LIGHTHOUSE_FUSE_ROOT', '/tmp/lighthouse')
        _fuse_validator = SecurePathValidator([fuse_root])
    return _fuse_validator


def get_event_store_validator() -> SecurePathValidator:
    """Get path validator for event store operations."""
    global _event_store_validator
    if _event_store_validator is None:
        store_root = os.environ.get('LIGHTHOUSE_DATA_DIR', './data')
        _event_store_validator = SecurePathValidator([store_root])
    return _event_store_validator


def validate_project_path(path: str, allow_creation: bool = False) -> Path:
    """Validate path for project file access."""
    return get_project_path_validator().validate_path(path, allow_creation)


def validate_fuse_path(path: str, allow_creation: bool = False) -> Path:
    """Validate path for FUSE mount access."""
    return get_fuse_path_validator().validate_path(path, allow_creation)


def validate_event_store_path(path: str, allow_creation: bool = False) -> Path:
    """Validate path for event store access."""
    return get_event_store_validator().validate_path(path, allow_creation)