"""
Shadow File Manager - Simple Implementation

Basic shadow file management for AST annotations.
"""

import json
from typing import Any, Dict


class ShadowFileManager:
    """Simple shadow file manager"""
    
    def __init__(self, ast_anchor_manager):
        self.anchor_manager = ast_anchor_manager
        self.shadow_cache = {}
    
    def get_shadow_content(self, file_path: str) -> Dict[str, Any]:
        """Get shadow content for file"""
        # Simple implementation - returns basic structure
        return {
            'file_path': file_path,
            'annotations': {},
            'anchors': []
        }