"""
AST Anchor Manager

Core management system for AST anchors with resolution and caching.
Handles anchor creation, resolution after refactoring, and performance optimization.
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .ast_anchor import ASTAnchor, ASTAnchorResolution, AnchorConfidence, AnchorType
from .tree_sitter_parser import TreeSitterParser, LanguageSupport, ParseResult

logger = logging.getLogger(__name__)


class ASTAnchorManager:
    """Manager for AST anchors with intelligent resolution"""
    
    def __init__(self, parser: Optional[TreeSitterParser] = None):
        """Initialize anchor manager"""
        self.parser = parser or TreeSitterParser()
        
        # Anchor storage
        self.anchors: Dict[str, ASTAnchor] = {}
        self.anchors_by_file: Dict[str, Set[str]] = defaultdict(set)
        
        # Resolution cache
        self.resolution_cache: Dict[str, ASTAnchorResolution] = {}
        self.cache_ttl = 300.0  # 5 minutes
        
        # Performance tracking
        self.resolution_stats = {
            'total_resolutions': 0,
            'successful_resolutions': 0,
            'cache_hits': 0,
            'resolution_times': []
        }
    
    def create_anchors(self, file_path: str, content: str) -> List[ASTAnchor]:
        """Create AST anchors for all significant nodes in a file"""
        
        # Parse the file
        parse_result = self.parser.parse(file_path, content)
        
        if not parse_result.success:
            logger.warning(f"Failed to parse {file_path}: {parse_result.error_message}")
            return []
        
        anchors = []
        
        # Traverse tree and create anchors for significant nodes
        anchors.extend(
            self._traverse_and_create_anchors(
                parse_result.root_node,
                file_path,
                content,
                parse_result.language.value
            )
        )
        
        # Store anchors
        for anchor in anchors:
            self.anchors[anchor.anchor_id] = anchor
            self.anchors_by_file[file_path].add(anchor.anchor_id)
        
        logger.info(f"Created {len(anchors)} AST anchors for {file_path}")
        
        return anchors
    
    def _traverse_and_create_anchors(self,
                                   node,
                                   file_path: str,
                                   content: str,
                                   language: str,
                                   parent_anchor: Optional[ASTAnchor] = None) -> List[ASTAnchor]:
        """Recursively traverse AST and create anchors for significant nodes"""
        
        anchors = []
        
        # Check if this node type should have an anchor
        if self._should_create_anchor(node):
            try:
                anchor = ASTAnchor.from_tree_sitter_node(
                    file_path=file_path,
                    node=node,
                    source_code=content,
                    language=language,
                    parent_anchor=parent_anchor
                )
                anchors.append(anchor)
                parent_anchor = anchor  # Use this as parent for children
                
            except Exception as e:
                logger.warning(f"Failed to create anchor for node {node.type}: {e}")
        
        # Recursively process children
        for child in node.children:
            child_anchors = self._traverse_and_create_anchors(
                child, file_path, content, language, parent_anchor
            )
            anchors.extend(child_anchors)
        
        return anchors
    
    def _should_create_anchor(self, node) -> bool:
        """Determine if a node should have an anchor"""
        # Create anchors for significant structural elements
        significant_types = {
            # Python
            'function_definition', 'async_function_definition', 'class_definition',
            'import_statement', 'import_from_statement', 'assignment',
            
            # JavaScript
            'function_declaration', 'arrow_function', 'method_definition',
            'class_declaration', 'variable_declaration', 'import_statement',
            
            # Go
            'function_declaration', 'method_declaration', 'type_declaration',
            'var_declaration', 'const_declaration',
            
            # General
            'comment', 'return_statement'
        }
        
        return node.type in significant_types
    
    async def resolve_anchor(self, 
                           anchor_id: str,
                           current_content: str,
                           force_refresh: bool = False) -> ASTAnchorResolution:
        """
        Resolve anchor position in current code
        
        Args:
            anchor_id: ID of anchor to resolve
            current_content: Current file content
            force_refresh: Skip cache and force fresh resolution
        """
        
        start_time = time.time()
        self.resolution_stats['total_resolutions'] += 1
        
        # Check cache first
        if not force_refresh:
            cached_resolution = self._get_cached_resolution(anchor_id)
            if cached_resolution:
                self.resolution_stats['cache_hits'] += 1
                return cached_resolution
        
        # Get anchor
        if anchor_id not in self.anchors:
            return ASTAnchorResolution(
                anchor=None,
                confidence=AnchorConfidence.LOST,
                new_position=None,
                resolution_method="anchor_not_found",
                error_message=f"Anchor {anchor_id} not found"
            )
        
        anchor = self.anchors[anchor_id]
        
        try:
            # Try different resolution strategies in order of preference
            resolution = None
            
            # Strategy 1: Exact position match
            resolution = await self._try_exact_position_resolution(anchor, current_content)
            if resolution and resolution.confidence in [AnchorConfidence.EXACT, AnchorConfidence.HIGH]:
                resolution.resolution_method = "exact_position"
            
            # Strategy 2: Structural search
            if not resolution or resolution.confidence == AnchorConfidence.LOST:
                resolution = await self._try_structural_resolution(anchor, current_content)
                if resolution:
                    resolution.resolution_method = "structural_search"
            
            # Strategy 3: Fuzzy matching
            if not resolution or resolution.confidence == AnchorConfidence.LOST:
                resolution = await self._try_fuzzy_resolution(anchor, current_content)
                if resolution:
                    resolution.resolution_method = "fuzzy_matching"
            
            # Fallback: Mark as lost
            if not resolution:
                resolution = ASTAnchorResolution(
                    anchor=anchor,
                    confidence=AnchorConfidence.LOST,
                    new_position=None,
                    resolution_method="all_strategies_failed"
                )
            
            # Update statistics and cache
            resolution.resolution_time_ms = (time.time() - start_time) * 1000
            
            if resolution.success:
                self.resolution_stats['successful_resolutions'] += 1
                
                # Update anchor with new position
                anchor.update_position(resolution.new_position, resolution.confidence)
            
            # Cache the result
            self._cache_resolution(anchor_id, resolution)
            
            return resolution
            
        except Exception as e:
            logger.error(f"Error resolving anchor {anchor_id}: {e}")
            
            return ASTAnchorResolution(
                anchor=anchor,
                confidence=AnchorConfidence.LOST,
                new_position=None,
                resolution_method="error",
                error_message=str(e)
            )
    
    async def _try_exact_position_resolution(self,
                                           anchor: ASTAnchor,
                                           current_content: str) -> Optional[ASTAnchorResolution]:
        """Try to resolve anchor at exact original position"""
        
        if not anchor.original_position:
            return None
        
        # Parse current content
        parse_result = self.parser.parse(anchor.file_path, current_content)
        
        if not parse_result.success:
            return None
        
        # Try to find node at exact position
        target_node = self._find_node_at_position(
            parse_result.root_node,
            anchor.original_position.start_row,
            anchor.original_position.start_col
        )
        
        if not target_node:
            return None
        
        # Verify it matches our expected structure
        confidence = self._calculate_structure_confidence(anchor, target_node, current_content)
        
        if confidence in [AnchorConfidence.EXACT, AnchorConfidence.HIGH]:
            return ASTAnchorResolution(
                anchor=anchor,
                confidence=confidence,
                new_position=anchor.original_position,  # Same position
                resolution_method="exact_position"
            )
        
        return None
    
    async def _try_structural_resolution(self,
                                       anchor: ASTAnchor,
                                       current_content: str) -> Optional[ASTAnchorResolution]:
        """Try to resolve anchor using structural matching"""
        
        # Parse current content
        parse_result = self.parser.parse(anchor.file_path, current_content)
        
        if not parse_result.success:
            return None
        
        # Find all nodes of the same type
        candidates = self._find_nodes_by_type(parse_result.root_node, anchor.anchor_type)
        
        if not candidates:
            return None
        
        # Score candidates based on structural similarity
        best_candidate = None
        best_confidence = AnchorConfidence.LOST
        
        for candidate_node in candidates:
            confidence = self._calculate_structure_confidence(anchor, candidate_node, current_content)
            
            if confidence.value > best_confidence.value:
                best_candidate = candidate_node
                best_confidence = confidence
        
        if best_candidate and best_confidence != AnchorConfidence.LOST:
            from .ast_anchor import ASTPosition
            new_position = ASTPosition.from_tree_sitter_node(best_candidate)
            
            return ASTAnchorResolution(
                anchor=anchor,
                confidence=best_confidence,
                new_position=new_position,
                resolution_method="structural_search",
                candidates_found=len(candidates)
            )
        
        return None
    
    async def _try_fuzzy_resolution(self,
                                  anchor: ASTAnchor,
                                  current_content: str) -> Optional[ASTAnchorResolution]:
        """Try fuzzy matching for anchor resolution"""
        
        # Simple fuzzy matching based on node name and context
        if not anchor.contextual_info.node_name:
            return None
        
        # Parse current content
        parse_result = self.parser.parse(anchor.file_path, current_content)
        
        if not parse_result.success:
            return None
        
        # Look for nodes with matching names
        candidates = self._find_nodes_by_name(
            parse_result.root_node,
            anchor.contextual_info.node_name,
            current_content
        )
        
        if candidates:
            # Use first match with medium confidence
            from .ast_anchor import ASTPosition
            new_position = ASTPosition.from_tree_sitter_node(candidates[0])
            
            return ASTAnchorResolution(
                anchor=anchor,
                confidence=AnchorConfidence.MEDIUM,
                new_position=new_position,
                resolution_method="fuzzy_matching",
                candidates_found=len(candidates)
            )
        
        return None
    
    def _find_node_at_position(self, root_node, target_row: int, target_col: int):
        """Find node at specific position"""
        
        for node in self._traverse_nodes(root_node):
            start_row, start_col = node.start_point
            end_row, end_col = node.end_point
            
            # Check if position is within this node
            if (start_row <= target_row <= end_row and
                (start_row < target_row or start_col <= target_col) and
                (end_row > target_row or end_col >= target_col)):
                
                return node
        
        return None
    
    def _find_nodes_by_type(self, root_node, anchor_type: AnchorType) -> List[Any]:
        """Find all nodes of a specific anchor type"""
        
        # Map anchor type back to tree-sitter node types
        type_mapping = {
            AnchorType.FUNCTION_DEFINITION: [
                'function_definition', 'async_function_definition', 
                'function_declaration', 'arrow_function'
            ],
            AnchorType.CLASS_DEFINITION: [
                'class_definition', 'class_declaration', 'type_declaration'
            ],
            AnchorType.METHOD_DEFINITION: [
                'method_definition', 'method_declaration'
            ],
            AnchorType.VARIABLE_DECLARATION: [
                'assignment', 'variable_declaration', 'var_declaration', 'const_declaration'
            ],
            AnchorType.IMPORT_STATEMENT: [
                'import_statement', 'import_from_statement'
            ]
        }
        
        target_types = type_mapping.get(anchor_type, [anchor_type.value])
        
        candidates = []
        for node in self._traverse_nodes(root_node):
            if node.type in target_types:
                candidates.append(node)
        
        return candidates
    
    def _find_nodes_by_name(self, root_node, target_name: str, content: str) -> List[Any]:
        """Find nodes by name"""
        candidates = []
        
        for node in self._traverse_nodes(root_node):
            # Extract name from node if available
            if hasattr(node, 'child_by_field_name'):
                name_node = node.child_by_field_name('name')
                if name_node:
                    node_name = content[name_node.start_byte:name_node.end_byte]
                    if node_name == target_name:
                        candidates.append(node)
        
        return candidates
    
    def _traverse_nodes(self, root_node):
        """Generator to traverse all nodes in AST"""
        yield root_node
        for child in root_node.children:
            yield from self._traverse_nodes(child)
    
    def _calculate_structure_confidence(self,
                                      anchor: ASTAnchor,
                                      candidate_node,
                                      current_content: str) -> AnchorConfidence:
        """Calculate confidence that candidate matches anchor"""
        
        # Extract contextual info from candidate
        from .ast_anchor import ASTAnchor as ASTAnchorClass
        candidate_context = ASTAnchorClass._extract_contextual_info(candidate_node, current_content)
        
        # Compare signatures
        original_signature = anchor.contextual_info.get_signature_hash()
        candidate_signature = candidate_context.get_signature_hash()
        
        if original_signature == candidate_signature:
            return AnchorConfidence.EXACT
        
        # Compare individual elements
        matches = 0
        total_comparisons = 0
        
        # Node name
        if anchor.contextual_info.node_name and candidate_context.node_name:
            total_comparisons += 1
            if anchor.contextual_info.node_name == candidate_context.node_name:
                matches += 1
        
        # Parameters
        if anchor.contextual_info.parameter_names or candidate_context.parameter_names:
            total_comparisons += 1
            if anchor.contextual_info.parameter_names == candidate_context.parameter_names:
                matches += 1
        
        # Context text similarity
        if anchor.contextual_info.preceding_text or candidate_context.preceding_text:
            total_comparisons += 1
            if anchor.contextual_info.preceding_text == candidate_context.preceding_text:
                matches += 1
        
        if total_comparisons == 0:
            return AnchorConfidence.LOW
        
        # Calculate confidence based on match ratio
        match_ratio = matches / total_comparisons
        
        if match_ratio >= 0.9:
            return AnchorConfidence.HIGH
        elif match_ratio >= 0.7:
            return AnchorConfidence.MEDIUM
        elif match_ratio >= 0.3:
            return AnchorConfidence.LOW
        else:
            return AnchorConfidence.LOST
    
    def _get_cached_resolution(self, anchor_id: str) -> Optional[ASTAnchorResolution]:
        """Get cached resolution if available and not expired"""
        
        if anchor_id not in self.resolution_cache:
            return None
        
        resolution = self.resolution_cache[anchor_id]
        
        # Check if cache entry is expired (simple time-based)
        # In a real implementation, this would be more sophisticated
        return resolution
    
    def _cache_resolution(self, anchor_id: str, resolution: ASTAnchorResolution):
        """Cache resolution result"""
        self.resolution_cache[anchor_id] = resolution
        
        # Limit cache size
        if len(self.resolution_cache) > 1000:
            # Remove oldest entries
            # Simple implementation - would use LRU in production
            oldest_keys = list(self.resolution_cache.keys())[:100]
            for key in oldest_keys:
                del self.resolution_cache[key]
    
    def get_anchors_for_file(self, file_path: str) -> List[ASTAnchor]:
        """Get all anchors for a specific file"""
        anchor_ids = self.anchors_by_file.get(file_path, set())
        return [self.anchors[anchor_id] for anchor_id in anchor_ids]
    
    def remove_anchors_for_file(self, file_path: str):
        """Remove all anchors for a specific file"""
        anchor_ids = self.anchors_by_file.get(file_path, set()).copy()
        
        for anchor_id in anchor_ids:
            if anchor_id in self.anchors:
                del self.anchors[anchor_id]
            if anchor_id in self.resolution_cache:
                del self.resolution_cache[anchor_id]
        
        if file_path in self.anchors_by_file:
            del self.anchors_by_file[file_path]
        
        logger.info(f"Removed {len(anchor_ids)} anchors for {file_path}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get anchor manager statistics"""
        return {
            'total_anchors': len(self.anchors),
            'files_with_anchors': len(self.anchors_by_file),
            'cached_resolutions': len(self.resolution_cache),
            'resolution_stats': self.resolution_stats.copy(),
            'parser_stats': self.parser.get_statistics()
        }