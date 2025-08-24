"""
AST Anchoring System

Tree-sitter based AST spans ensuring annotations survive refactoring.
Provides persistent references to code structures that remain valid
even when code is moved or modified.

Features:
- Structure-based anchor IDs (not position-based)
- Multi-language support via tree-sitter
- Anchor resolution after refactoring
- Shadow filesystem integration
- Event-sourced annotation storage

Core Components:
- ASTAnchor: Persistent reference to AST nodes
- ASTAnchorManager: Management and resolution of anchors
- ShadowFileManager: Integration with FUSE shadow filesystem
- TreeSitterParser: Multi-language AST parsing
"""

from .ast_anchor import ASTAnchor, ASTAnchorResolution
from .anchor_manager import ASTAnchorManager
from .shadow_manager import ShadowFileManager
from .tree_sitter_parser import TreeSitterParser, LanguageSupport

__all__ = [
    'ASTAnchor',
    'ASTAnchorResolution', 
    'ASTAnchorManager',
    'ShadowFileManager',
    'TreeSitterParser',
    'LanguageSupport'
]