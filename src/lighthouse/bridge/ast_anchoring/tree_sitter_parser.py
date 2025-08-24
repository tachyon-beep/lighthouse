"""
Tree-Sitter Parser Integration

Multi-language AST parsing using tree-sitter.
Provides unified interface for parsing different programming languages.

Supported Languages:
- Python
- JavaScript/TypeScript  
- Go
- Rust
- Java
- C/C++
- HTML/CSS
- JSON/YAML
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import tree_sitter
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    
    # Mock tree_sitter for when it's not available
    class tree_sitter:
        class Language:
            pass
        class Parser:
            def set_language(self, lang): pass
            def parse(self, content): 
                return MockNode()
        class Node:
            pass

class MockNode:
    """Mock node for when tree-sitter is not available"""
    def __init__(self):
        self.type = "unknown"
        self.start_point = (0, 0)
        self.end_point = (0, 0)
        self.start_byte = 0
        self.end_byte = 0
        self.children = []
        self.parent = None
    
    def child_by_field_name(self, name):
        return None

logger = logging.getLogger(__name__)


class LanguageSupport(str, Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    C = "c"
    CPP = "cpp"
    HTML = "html"
    CSS = "css"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    BASH = "bash"
    SQL = "sql"
    UNKNOWN = "unknown"


@dataclass
class ParseResult:
    """Result of parsing operation"""
    
    success: bool
    language: LanguageSupport
    root_node: Any  # tree_sitter.Node
    source_code: str
    parse_time_ms: float
    error_message: Optional[str] = None
    
    @property
    def node_count(self) -> int:
        """Count total nodes in the tree"""
        if not self.success or not self.root_node:
            return 0
        return self._count_nodes(self.root_node)
    
    def _count_nodes(self, node) -> int:
        """Recursively count nodes"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count


class TreeSitterParser:
    """Multi-language AST parser using tree-sitter"""
    
    def __init__(self):
        """Initialize parser with language support"""
        
        if not TREE_SITTER_AVAILABLE:
            logger.warning("tree-sitter not available. AST parsing will be limited.")
            self._languages = {}
            self._parsers = {}
            return
        
        # Language mapping
        self._language_extensions = {
            '.py': LanguageSupport.PYTHON,
            '.js': LanguageSupport.JAVASCRIPT,
            '.mjs': LanguageSupport.JAVASCRIPT,
            '.jsx': LanguageSupport.JAVASCRIPT,
            '.ts': LanguageSupport.TYPESCRIPT,
            '.tsx': LanguageSupport.TYPESCRIPT,
            '.go': LanguageSupport.GO,
            '.rs': LanguageSupport.RUST,
            '.java': LanguageSupport.JAVA,
            '.c': LanguageSupport.C,
            '.h': LanguageSupport.C,
            '.cpp': LanguageSupport.CPP,
            '.cxx': LanguageSupport.CPP,
            '.cc': LanguageSupport.CPP,
            '.hpp': LanguageSupport.CPP,
            '.html': LanguageSupport.HTML,
            '.htm': LanguageSupport.HTML,
            '.css': LanguageSupport.CSS,
            '.json': LanguageSupport.JSON,
            '.yaml': LanguageSupport.YAML,
            '.yml': LanguageSupport.YAML,
            '.md': LanguageSupport.MARKDOWN,
            '.sh': LanguageSupport.BASH,
            '.bash': LanguageSupport.BASH,
            '.sql': LanguageSupport.SQL
        }
        
        # Initialize languages and parsers
        self._languages: Dict[LanguageSupport, Any] = {}
        self._parsers: Dict[LanguageSupport, tree_sitter.Parser] = {}
        
        self._load_languages()
    
    def _load_languages(self):
        """Load available tree-sitter languages"""
        language_loaders = {
            LanguageSupport.PYTHON: self._load_python,
            LanguageSupport.JAVASCRIPT: self._load_javascript,
            LanguageSupport.TYPESCRIPT: self._load_typescript,
            LanguageSupport.GO: self._load_go,
            LanguageSupport.RUST: self._load_rust,
            LanguageSupport.JAVA: self._load_java,
            LanguageSupport.C: self._load_c,
            LanguageSupport.CPP: self._load_cpp,
            LanguageSupport.HTML: self._load_html,
            LanguageSupport.CSS: self._load_css,
            LanguageSupport.JSON: self._load_json,
            LanguageSupport.YAML: self._load_yaml,
            LanguageSupport.MARKDOWN: self._load_markdown,
            LanguageSupport.BASH: self._load_bash,
            LanguageSupport.SQL: self._load_sql
        }
        
        for lang, loader in language_loaders.items():
            try:
                language_obj = loader()
                if language_obj:
                    self._languages[lang] = language_obj
                    
                    # Create parser for this language
                    parser = tree_sitter.Parser()
                    parser.set_language(language_obj)
                    self._parsers[lang] = parser
                    
                    logger.debug(f"Loaded tree-sitter language: {lang.value}")
            
            except Exception as e:
                logger.warning(f"Failed to load language {lang.value}: {e}")
        
        logger.info(f"Loaded {len(self._languages)} tree-sitter languages")
    
    def _load_python(self):
        """Load Python language"""
        try:
            import tree_sitter_python
            return tree_sitter.Language(tree_sitter_python.language())
        except ImportError:
            logger.debug("tree-sitter-python not available")
            return None
    
    def _load_javascript(self):
        """Load JavaScript language"""
        try:
            import tree_sitter_javascript
            return tree_sitter.Language(tree_sitter_javascript.language())
        except ImportError:
            logger.debug("tree-sitter-javascript not available")
            return None
    
    def _load_typescript(self):
        """Load TypeScript language"""
        try:
            import tree_sitter_typescript
            return tree_sitter.Language(tree_sitter_typescript.language_typescript())
        except ImportError:
            logger.debug("tree-sitter-typescript not available")
            return None
    
    def _load_go(self):
        """Load Go language"""
        try:
            import tree_sitter_go
            return tree_sitter.Language(tree_sitter_go.language())
        except ImportError:
            logger.debug("tree-sitter-go not available")
            return None
    
    def _load_rust(self):
        """Load Rust language"""
        try:
            import tree_sitter_rust
            return tree_sitter.Language(tree_sitter_rust.language())
        except ImportError:
            logger.debug("tree-sitter-rust not available")
            return None
    
    def _load_java(self):
        """Load Java language"""
        try:
            import tree_sitter_java
            return tree_sitter.Language(tree_sitter_java.language())
        except ImportError:
            logger.debug("tree-sitter-java not available")
            return None
    
    def _load_c(self):
        """Load C language"""
        try:
            import tree_sitter_c
            return tree_sitter.Language(tree_sitter_c.language())
        except ImportError:
            logger.debug("tree-sitter-c not available")
            return None
    
    def _load_cpp(self):
        """Load C++ language"""
        try:
            import tree_sitter_cpp
            return tree_sitter.Language(tree_sitter_cpp.language())
        except ImportError:
            logger.debug("tree-sitter-cpp not available")
            return None
    
    def _load_html(self):
        """Load HTML language"""
        try:
            import tree_sitter_html
            return tree_sitter.Language(tree_sitter_html.language())
        except ImportError:
            logger.debug("tree-sitter-html not available")
            return None
    
    def _load_css(self):
        """Load CSS language"""
        try:
            import tree_sitter_css
            return tree_sitter.Language(tree_sitter_css.language())
        except ImportError:
            logger.debug("tree-sitter-css not available")
            return None
    
    def _load_json(self):
        """Load JSON language"""
        try:
            import tree_sitter_json
            return tree_sitter.Language(tree_sitter_json.language())
        except ImportError:
            logger.debug("tree-sitter-json not available")
            return None
    
    def _load_yaml(self):
        """Load YAML language"""
        try:
            import tree_sitter_yaml
            return tree_sitter.Language(tree_sitter_yaml.language())
        except ImportError:
            logger.debug("tree-sitter-yaml not available")
            return None
    
    def _load_markdown(self):
        """Load Markdown language"""
        try:
            import tree_sitter_markdown
            return tree_sitter.Language(tree_sitter_markdown.language())
        except ImportError:
            logger.debug("tree-sitter-markdown not available")
            return None
    
    def _load_bash(self):
        """Load Bash language"""
        try:
            import tree_sitter_bash
            return tree_sitter.Language(tree_sitter_bash.language())
        except ImportError:
            logger.debug("tree-sitter-bash not available")
            return None
    
    def _load_sql(self):
        """Load SQL language"""
        try:
            import tree_sitter_sql
            return tree_sitter.Language(tree_sitter_sql.language())
        except ImportError:
            logger.debug("tree-sitter-sql not available")
            return None
    
    def detect_language(self, file_path: str, content: Optional[str] = None) -> LanguageSupport:
        """
        Detect programming language from file path or content
        
        Args:
            file_path: Path to the file
            content: Optional file content for better detection
            
        Returns:
            Detected language
        """
        # Try extension-based detection first
        path_obj = Path(file_path)
        extension = path_obj.suffix.lower()
        
        if extension in self._language_extensions:
            return self._language_extensions[extension]
        
        # Try filename-based detection
        filename = path_obj.name.lower()
        filename_mapping = {
            'dockerfile': LanguageSupport.BASH,
            'makefile': LanguageSupport.BASH,
            'cmakelists.txt': LanguageSupport.C,
            'package.json': LanguageSupport.JSON,
            'tsconfig.json': LanguageSupport.JSON,
            'cargo.toml': LanguageSupport.YAML,
            'pyproject.toml': LanguageSupport.YAML
        }
        
        if filename in filename_mapping:
            return filename_mapping[filename]
        
        # Try content-based detection if available
        if content:
            return self._detect_language_from_content(content)
        
        return LanguageSupport.UNKNOWN
    
    def _detect_language_from_content(self, content: str) -> LanguageSupport:
        """Detect language from content patterns"""
        content_lower = content.lower().strip()
        
        # Check for shebangs
        if content_lower.startswith('#!/'):
            first_line = content.split('\n')[0].lower()
            if 'python' in first_line:
                return LanguageSupport.PYTHON
            elif 'bash' in first_line or 'sh' in first_line:
                return LanguageSupport.BASH
            elif 'node' in first_line:
                return LanguageSupport.JAVASCRIPT
        
        # Check for language-specific patterns
        patterns = {
            LanguageSupport.PYTHON: ['def ', 'import ', 'from ', '__name__'],
            LanguageSupport.JAVASCRIPT: ['function ', 'const ', 'let ', 'var ', '=>', 'console.log'],
            LanguageSupport.GO: ['package ', 'func ', 'import ', 'type '],
            LanguageSupport.RUST: ['fn ', 'let ', 'use ', 'impl ', 'struct '],
            LanguageSupport.JAVA: ['public class', 'private ', 'public ', 'static '],
            LanguageSupport.C: ['#include', 'int main', 'printf', 'malloc'],
            LanguageSupport.CPP: ['#include', 'std::', 'namespace ', 'cout'],
            LanguageSupport.HTML: ['<html', '<body', '<div', '<!doctype'],
            LanguageSupport.CSS: ['{', '}', ':', ';', 'margin', 'padding'],
            LanguageSupport.JSON: ['{', '}', '":', '",'],
            LanguageSupport.YAML: ['---', ':', '- '],
            LanguageSupport.SQL: ['select ', 'insert ', 'update ', 'delete ']
        }
        
        # Score languages based on pattern matches
        scores = {}
        for lang, lang_patterns in patterns.items():
            score = sum(1 for pattern in lang_patterns if pattern in content_lower)
            if score > 0:
                scores[lang] = score
        
        if scores:
            # Return language with highest score
            return max(scores.keys(), key=lambda k: scores[k])
        
        return LanguageSupport.UNKNOWN
    
    def parse(self, 
             file_path: str, 
             content: str,
             language: Optional[LanguageSupport] = None) -> ParseResult:
        """
        Parse source code and return AST
        
        Args:
            file_path: Path to the file
            content: Source code content
            language: Optional language override
            
        Returns:
            Parse result with AST
        """
        import time
        
        start_time = time.time()
        
        # Detect language if not provided
        if language is None:
            language = self.detect_language(file_path, content)
        
        # Check if we have parser for this language
        if language not in self._parsers:
            return ParseResult(
                success=False,
                language=language,
                root_node=None,
                source_code=content,
                parse_time_ms=0.0,
                error_message=f"No parser available for language: {language.value}"
            )
        
        try:
            # Parse the code
            parser = self._parsers[language]
            tree = parser.parse(content.encode('utf-8'))
            
            parse_time_ms = (time.time() - start_time) * 1000
            
            if tree.root_node.has_error:
                logger.warning(f"Parse errors in {file_path}")
            
            return ParseResult(
                success=True,
                language=language,
                root_node=tree.root_node,
                source_code=content,
                parse_time_ms=parse_time_ms
            )
            
        except Exception as e:
            parse_time_ms = (time.time() - start_time) * 1000
            
            return ParseResult(
                success=False,
                language=language,
                root_node=None,
                source_code=content,
                parse_time_ms=parse_time_ms,
                error_message=str(e)
            )
    
    def get_supported_languages(self) -> List[LanguageSupport]:
        """Get list of supported languages"""
        return list(self._languages.keys())
    
    def is_language_supported(self, language: LanguageSupport) -> bool:
        """Check if language is supported"""
        return language in self._languages
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get parser statistics"""
        return {
            'tree_sitter_available': TREE_SITTER_AVAILABLE,
            'supported_languages': len(self._languages),
            'available_parsers': len(self._parsers),
            'language_list': [lang.value for lang in self._languages.keys()]
        }