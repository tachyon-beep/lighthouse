"""
Context Package Manager - Simple Implementation

Basic context package management for experts.
"""

from typing import Any, Dict


class ContextPackage:
    """Context package for expert agents"""
    
    def __init__(self,
                 package_id: str,
                 title: str = "",
                 description: str = "",
                 architectural_context: Dict[str, str] = None,
                 implementation_context: Dict[str, str] = None,
                 historical_context: Dict[str, Any] = None,
                 metadata: Dict[str, Any] = None):
        self.package_id = package_id
        self.title = title
        self.description = description
        self.architectural_context = architectural_context or {}
        self.implementation_context = implementation_context or {}
        self.historical_context = historical_context or {}
        self.metadata = metadata or {}


class ContextPackageManager:
    """Simple context package manager"""
    
    def __init__(self):
        self.packages = {}
    
    def create_package(self, package_id: str, **kwargs) -> ContextPackage:
        """Create context package"""
        package = ContextPackage(package_id, **kwargs)
        self.packages[package_id] = package
        return package