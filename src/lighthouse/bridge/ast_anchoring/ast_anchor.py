"""
AST Anchor Data Models

Core data structures for AST anchoring system.
Provides persistent references to code structures that survive refactoring.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from pydantic import BaseModel


class AnchorType(str, Enum):
    """Types of AST anchors"""
    FUNCTION_DEFINITION = "function_definition"
    CLASS_DEFINITION = "class_definition"
    METHOD_DEFINITION = "method_definition"
    VARIABLE_DECLARATION = "variable_declaration"
    IMPORT_STATEMENT = "import_statement"
    COMMENT_BLOCK = "comment_block"
    EXPRESSION = "expression"
    STATEMENT = "statement"
    BLOCK = "block"
    PARAMETER = "parameter"
    RETURN_STATEMENT = "return_statement"


class AnchorConfidence(str, Enum):
    """Confidence levels for anchor resolution"""
    EXACT = "exact"        # Exact position match
    HIGH = "high"         # Structure match with minor changes
    MEDIUM = "medium"     # Structure match with moderate changes
    LOW = "low"          # Partial match, may be incorrect
    LOST = "lost"        # Could not resolve anchor


@dataclass
class ASTPosition:
    """Position information for AST nodes"""
    
    start_row: int
    start_col: int
    end_row: int
    end_col: int
    start_byte: int = 0
    end_byte: int = 0
    
    def __post_init__(self):
        """Validate position data"""
        if self.start_row < 0 or self.start_col < 0:
            raise ValueError("Start position cannot be negative")
        if self.end_row < self.start_row:
            raise ValueError("End row cannot be before start row")
        if self.end_row == self.start_row and self.end_col < self.start_col:
            raise ValueError("End col cannot be before start col on same row")
    
    @classmethod
    def from_tree_sitter_node(cls, node) -> 'ASTPosition':
        """Create position from tree-sitter node"""
        return cls(
            start_row=node.start_point[0],
            start_col=node.start_point[1], 
            end_row=node.end_point[0],
            end_col=node.end_point[1],
            start_byte=node.start_byte,
            end_byte=node.end_byte
        )
    
    def contains(self, other: 'ASTPosition') -> bool:
        """Check if this position contains another position"""
        if other.start_row < self.start_row or other.end_row > self.end_row:
            return False
        
        if other.start_row == self.start_row and other.start_col < self.start_col:
            return False
            
        if other.end_row == self.end_row and other.end_col > self.end_col:
            return False
        
        return True
    
    def overlaps(self, other: 'ASTPosition') -> bool:
        """Check if this position overlaps with another position"""
        return not (
            self.end_row < other.start_row or
            other.end_row < self.start_row or
            (self.end_row == other.start_row and self.end_col < other.start_col) or
            (other.end_row == self.start_row and other.end_col < self.start_col)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'start_row': self.start_row,
            'start_col': self.start_col,
            'end_row': self.end_row,
            'end_col': self.end_col,
            'start_byte': self.start_byte,
            'end_byte': self.end_byte
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ASTPosition':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class ContextualInfo:
    """Contextual information for anchor resolution"""
    
    # Code context
    preceding_text: str = ""
    following_text: str = ""
    parent_text: str = ""
    
    # Structural context
    node_name: Optional[str] = None
    parameter_names: List[str] = field(default_factory=list)
    local_variables: List[str] = field(default_factory=list)
    
    # Metadata
    docstring: Optional[str] = None
    comments: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    
    def get_signature_hash(self) -> str:
        """Get hash of structural signature for matching"""
        signature_parts = [
            self.node_name or "",
            "|".join(sorted(self.parameter_names)),
            "|".join(sorted(self.local_variables)),
            "|".join(sorted(self.decorators))
        ]
        
        signature = "::".join(signature_parts)
        return hashlib.sha256(signature.encode()).hexdigest()[:16]


class ASTAnchor(BaseModel):
    """
    Persistent reference to AST nodes that survives refactoring
    
    Uses structure-based identification rather than position-based
    to remain valid through code changes.
    """
    
    # Core identification
    anchor_id: str
    file_path: str
    anchor_type: AnchorType
    
    # Position information (may become stale)
    original_position: ASTPosition
    current_position: Optional[ASTPosition] = None
    
    # Structural information for resolution
    contextual_info: ContextualInfo
    structure_hash: str
    
    # Hierarchy information
    parent_anchor_id: Optional[str] = None
    child_anchor_ids: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_resolved: Optional[datetime] = None
    language: str = "unknown"
    
    # Resolution tracking
    resolution_attempts: int = 0
    last_confidence: AnchorConfidence = AnchorConfidence.EXACT
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.anchor_id:
            self.anchor_id = self._generate_anchor_id()
    
    def _generate_anchor_id(self) -> str:
        """Generate stable anchor ID based on structure"""
        # Include file path, type, and structural signature
        id_components = [
            self.file_path,
            self.anchor_type.value,
            self.contextual_info.get_signature_hash(),
            str(self.original_position.start_row),
            str(self.original_position.start_col)
        ]
        
        # Include parent for hierarchical uniqueness
        if self.parent_anchor_id:
            id_components.append(self.parent_anchor_id)
        
        content = "::".join(id_components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    @classmethod
    def from_tree_sitter_node(cls,
                            file_path: str,
                            node,
                            source_code: str,
                            language: str = "unknown",
                            parent_anchor: Optional['ASTAnchor'] = None) -> 'ASTAnchor':
        """Create anchor from tree-sitter node"""
        
        # Determine anchor type from node type
        anchor_type = cls._map_node_type_to_anchor_type(node.type)
        
        # Extract position
        position = ASTPosition.from_tree_sitter_node(node)
        
        # Extract contextual information
        contextual_info = cls._extract_contextual_info(node, source_code)
        
        # Generate structure hash
        structure_hash = cls._generate_structure_hash(node, contextual_info)
        
        return cls(
            anchor_id="",  # Will be generated in __init__
            file_path=file_path,
            anchor_type=anchor_type,
            original_position=position,
            current_position=position,
            contextual_info=contextual_info,
            structure_hash=structure_hash,
            parent_anchor_id=parent_anchor.anchor_id if parent_anchor else None,
            language=language
        )
    
    @staticmethod
    def _map_node_type_to_anchor_type(node_type: str) -> AnchorType:
        """Map tree-sitter node type to anchor type"""
        mapping = {
            # Python
            'function_definition': AnchorType.FUNCTION_DEFINITION,
            'async_function_definition': AnchorType.FUNCTION_DEFINITION,
            'class_definition': AnchorType.CLASS_DEFINITION,
            'import_statement': AnchorType.IMPORT_STATEMENT,
            'import_from_statement': AnchorType.IMPORT_STATEMENT,
            'assignment': AnchorType.VARIABLE_DECLARATION,
            'comment': AnchorType.COMMENT_BLOCK,
            'return_statement': AnchorType.RETURN_STATEMENT,
            
            # JavaScript
            'function_declaration': AnchorType.FUNCTION_DEFINITION,
            'arrow_function': AnchorType.FUNCTION_DEFINITION,
            'method_definition': AnchorType.METHOD_DEFINITION,
            'class_declaration': AnchorType.CLASS_DEFINITION,
            'variable_declaration': AnchorType.VARIABLE_DECLARATION,
            'import_statement': AnchorType.IMPORT_STATEMENT,
            
            # Go
            'function_declaration': AnchorType.FUNCTION_DEFINITION,
            'method_declaration': AnchorType.METHOD_DEFINITION,
            'type_declaration': AnchorType.CLASS_DEFINITION,
            'var_declaration': AnchorType.VARIABLE_DECLARATION,
            'const_declaration': AnchorType.VARIABLE_DECLARATION,
            
            # Default
            'block': AnchorType.BLOCK,
            'expression_statement': AnchorType.EXPRESSION,
        }
        
        return mapping.get(node_type, AnchorType.STATEMENT)
    
    @staticmethod
    def _extract_contextual_info(node, source_code: str) -> ContextualInfo:
        """Extract contextual information from node"""
        lines = source_code.splitlines()
        
        # Get node text
        start_row, start_col = node.start_point
        end_row, end_col = node.end_point
        
        # Extract surrounding context
        preceding_text = ""
        following_text = ""
        
        if start_row > 0:
            preceding_text = lines[start_row - 1] if start_row - 1 < len(lines) else ""
        
        if end_row < len(lines) - 1:
            following_text = lines[end_row + 1] if end_row + 1 < len(lines) else ""
        
        # Extract node name if available
        node_name = None
        if hasattr(node, 'child_by_field_name'):
            name_node = node.child_by_field_name('name')
            if name_node:
                node_name = source_code[name_node.start_byte:name_node.end_byte]
        
        # Extract parameters for functions
        parameter_names = []
        if node.type in ['function_definition', 'function_declaration', 'method_definition']:
            params_node = node.child_by_field_name('parameters')
            if params_node:
                parameter_names = ASTAnchor._extract_parameter_names(params_node, source_code)
        
        # Extract parent text (if parent exists)
        parent_text = ""
        if node.parent:
            parent_start = node.parent.start_byte
            parent_end = min(node.parent.end_byte, parent_start + 200)  # Limit size
            parent_text = source_code[parent_start:parent_end]
        
        return ContextualInfo(
            preceding_text=preceding_text.strip(),
            following_text=following_text.strip(),
            parent_text=parent_text,
            node_name=node_name
        )
    
    @staticmethod
    def _extract_parameter_names(params_node, source_code: str) -> List[str]:
        """Extract parameter names from parameters node"""
        parameter_names = []
        
        for child in params_node.children:
            if child.type in ['identifier', 'parameter', 'typed_parameter']:
                # Get the identifier part
                if child.type == 'identifier':
                    name = source_code[child.start_byte:child.end_byte]
                    parameter_names.append(name)
                else:
                    # Look for identifier child
                    for grandchild in child.children:
                        if grandchild.type == 'identifier':
                            name = source_code[grandchild.start_byte:grandchild.end_byte]
                            parameter_names.append(name)
                            break
        
        return parameter_names
    
    @staticmethod
    def _generate_structure_hash(node, contextual_info: ContextualInfo) -> str:
        """Generate hash representing the structural signature"""
        structure_elements = [
            node.type,
            contextual_info.node_name or "",
            "|".join(contextual_info.parameter_names),
            contextual_info.preceding_text[:50],  # First 50 chars
            contextual_info.following_text[:50]
        ]
        
        structure_string = "::".join(structure_elements)
        return hashlib.sha256(structure_string.encode()).hexdigest()
    
    def update_position(self, new_position: ASTPosition, confidence: AnchorConfidence):
        """Update current position with new resolution"""
        self.current_position = new_position
        self.last_resolved = datetime.utcnow()
        self.last_confidence = confidence
        self.resolution_attempts += 1
    
    def is_stale(self, current_code_hash: str) -> bool:
        """Check if anchor may be stale based on code changes"""
        # Simple heuristic - if it's been a while since last resolution
        # and we don't have exact confidence, consider it potentially stale
        if not self.last_resolved:
            return True
        
        time_since_resolution = datetime.utcnow() - self.last_resolved
        
        if time_since_resolution.total_seconds() > 300:  # 5 minutes
            return self.last_confidence not in [AnchorConfidence.EXACT, AnchorConfidence.HIGH]
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'anchor_id': self.anchor_id,
            'file_path': self.file_path,
            'anchor_type': self.anchor_type.value,
            'original_position': self.original_position.to_dict(),
            'current_position': self.current_position.to_dict() if self.current_position else None,
            'contextual_info': {
                'preceding_text': self.contextual_info.preceding_text,
                'following_text': self.contextual_info.following_text,
                'parent_text': self.contextual_info.parent_text,
                'node_name': self.contextual_info.node_name,
                'parameter_names': self.contextual_info.parameter_names,
                'signature_hash': self.contextual_info.get_signature_hash()
            },
            'structure_hash': self.structure_hash,
            'parent_anchor_id': self.parent_anchor_id,
            'child_anchor_ids': self.child_anchor_ids,
            'created_at': self.created_at.isoformat(),
            'last_resolved': self.last_resolved.isoformat() if self.last_resolved else None,
            'language': self.language,
            'resolution_attempts': self.resolution_attempts,
            'last_confidence': self.last_confidence.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ASTAnchor':
        """Create from dictionary"""
        # Parse datetime fields
        if data.get('created_at'):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        
        if data.get('last_resolved'):
            data['last_resolved'] = datetime.fromisoformat(data['last_resolved'])
        
        # Parse positions
        if data.get('original_position'):
            data['original_position'] = ASTPosition.from_dict(data['original_position'])
        
        if data.get('current_position'):
            data['current_position'] = ASTPosition.from_dict(data['current_position'])
        
        # Parse contextual info
        if data.get('contextual_info'):
            ctx_data = data['contextual_info']
            data['contextual_info'] = ContextualInfo(
                preceding_text=ctx_data.get('preceding_text', ''),
                following_text=ctx_data.get('following_text', ''),
                parent_text=ctx_data.get('parent_text', ''),
                node_name=ctx_data.get('node_name'),
                parameter_names=ctx_data.get('parameter_names', [])
            )
        
        # Parse enums
        if data.get('anchor_type'):
            data['anchor_type'] = AnchorType(data['anchor_type'])
        
        if data.get('last_confidence'):
            data['last_confidence'] = AnchorConfidence(data['last_confidence'])
        
        return cls(**data)


@dataclass
class ASTAnchorResolution:
    """Result of anchor resolution attempt"""
    
    anchor: ASTAnchor
    confidence: AnchorConfidence
    new_position: Optional[ASTPosition]
    resolution_method: str
    
    # Diagnostic information
    candidates_found: int = 0
    resolution_time_ms: float = 0.0
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if resolution was successful"""
        return self.confidence != AnchorConfidence.LOST and self.new_position is not None