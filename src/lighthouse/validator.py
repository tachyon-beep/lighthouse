"""
Secure Command Validator for the Lighthouse system.

Enhanced security with input sanitization, content limits, authentication, 
and comprehensive dangerous pattern detection.
"""

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import requests

# Import secure event store components for authentication
try:
    from .event_store import (
        EventStore, Event, EventType, AgentIdentity, Permission,
        AuthenticationError, SecurityError
    )
    EVENT_STORE_AVAILABLE = True
except ImportError:
    EVENT_STORE_AVAILABLE = False

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Exception raised during command validation."""
    pass


class SecureCommandValidator:
    """Secure command validator with authentication and comprehensive security checks."""
    
    def __init__(self, 
                 bridge_url: str = "http://localhost:8765",
                 event_store: Optional['EventStore'] = None,
                 max_command_size: int = 1024 * 1024,  # 1MB limit
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB limit
                 auth_required: bool = True):
        
        self.bridge_url = bridge_url
        self.event_store = event_store
        self.max_command_size = max_command_size
        self.max_file_size = max_file_size
        self.auth_required = auth_required and EVENT_STORE_AVAILABLE
        
        # Load comprehensive validation rules
        self.validation_rules = self._load_comprehensive_validation_rules()
        
        # Pair programming state
        self.pair_mode = "PASSIVE"
        self.current_session_id: Optional[str] = None
        
        # Security monitoring
        self.blocked_commands: List[Dict[str, Any]] = []
        self.suspicious_patterns: Set[str] = set()
        
        # Compile regex patterns for performance
        self._compiled_patterns = self._compile_dangerous_patterns()
    
    def _load_comprehensive_validation_rules(self) -> Dict[str, Any]:
        """Load comprehensive security validation rules."""
        return {
            "dangerous_bash_patterns": [
                # File system destruction
                r"rm\s+-rf\s+/\w*",
                r"rm\s+-rf\s+\*",
                r"rm\s+-rf\s+~",
                r"sudo\s+rm\s+-rf",
                r"rm\s+--no-preserve-root",
                
                # Privilege escalation  
                r"sudo\s+",
                r"su\s+-",
                r"chmod\s+[4-7][0-7][0-7]",
                r"chmod\s+\+s",
                r"chown\s+root",
                r"setuid",
                r"setgid",
                
                # System modification
                r"mkfs\.",
                r"fdisk\s+",
                r"parted\s+",
                r"dd\s+if=",
                r"dd\s+of=/dev",
                r"mount\s+",
                r"umount\s+",
                
                # Network and system access
                r"nc\s+-l",
                r"netcat\s+-l", 
                r"ncat\s+-l",
                r"ssh\s+",
                r"scp\s+",
                r"rsync\s+",
                r"curl\s+.*>\s*/",
                r"wget\s+.*>\s*/",
                
                # Process and system control
                r"kill\s+-9\s+1",
                r"killall\s+-9",
                r"pkill\s+-9",
                r"shutdown",
                r"reboot",
                r"halt",
                r"init\s+[06]",
                r"systemctl\s+(stop|disable|mask)",
                r"service\s+\w+\s+stop",
                
                # Device and hardware access
                r">/dev/",
                r"</dev/",
                r"/dev/sd[a-z]",
                r"/dev/nvme",
                r"/dev/mem",
                r"/dev/kmem",
                
                # Code injection and dangerous operations
                r"eval\s+",
                r"exec\s+",
                r"\$\([^)]+\)",  # Command substitution
                r"`[^`]+`",      # Backtick execution
                r";\s*rm",
                r"&&\s*rm", 
                r"\|\s*rm",
                
                # Binary and system file manipulation
                r"hexdump\s+",
                r"strings\s+/",
                r"objdump\s+",
                r"gdb\s+",
                r"strace\s+",
                r"ltrace\s+",
            ],
            
            "dangerous_file_patterns": [
                # System configuration files
                r"^/etc/passwd",
                r"^/etc/shadow", 
                r"^/etc/sudoers",
                r"^/etc/hosts",
                r"^/etc/fstab",
                r"^/etc/crontab",
                r"^/etc/ssh/",
                
                # System binaries and libraries
                r"^/usr/bin/",
                r"^/usr/sbin/",
                r"^/usr/lib/",
                r"^/lib/",
                r"^/lib64/",
                r"^/sbin/",
                r"^/bin/",
                
                # Kernel and system directories
                r"^/boot/",
                r"^/sys/",
                r"^/proc/",
                r"^/dev/",
                r"^/var/log/",
                r"^/var/run/",
                r"^/tmp/\.\./",  # Path traversal attempts
                r"\.\./",       # Any path traversal
                
                # Security-sensitive files
                r"\.ssh/",
                r"\.gnupg/",
                r"authorized_keys",
                r"id_rsa",
                r"id_ed25519",
                r"\.pem$",
                r"\.key$",
                r"\.crt$",
            ],
            
            "content_security_rules": {
                "max_line_length": 10000,
                "max_lines": 10000,
                "forbidden_content": [
                    # Embedded binaries or suspicious content
                    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\xFF]{100,}",  # Binary data
                    r"eval\s*\(",
                    r"exec\s*\(",
                    r"__import__\s*\(",
                    r"getattr\s*\(",
                    r"setattr\s*\(",
                    r"globals\s*\(",
                    r"locals\s*\(",
                    
                    # SQL injection patterns
                    r"UNION\s+SELECT",
                    r"DROP\s+TABLE",
                    r"DELETE\s+FROM",
                    r"INSERT\s+INTO.*VALUES",
                    r"UPDATE.*SET",
                    
                    # Script injection
                    r"<script",
                    r"javascript:",
                    r"data:text/html",
                    r"onclick\s*=",
                    r"onerror\s*=",
                ],
                "max_repeated_chars": 1000,
                "max_encoded_content": 50000  # Base64, hex, etc.
            },
            
            "protected_paths": [
                "/etc/", "/usr/", "/var/", "/boot/", "/sys/", "/proc/", "/dev/",
                "/lib/", "/lib64/", "/bin/", "/sbin/", "/opt/", "/root/",
                "/home/.ssh/", "/home/.gnupg/"
            ],
            
            "safe_tools": [
                "Read", "Glob", "Grep", "LS", "WebFetch", "WebSearch"
            ],
            
            "restricted_tools": {
                "Bash": {"max_command_length": 1000, "requires_auth": True},
                "Write": {"max_file_size": 1024*1024, "requires_auth": True},  
                "Edit": {"max_edit_size": 1024*1024, "requires_auth": True},
                "MultiEdit": {"max_edits": 10, "requires_auth": True},
                "Task": {"requires_auth": True, "audit_required": True}
            },
            
            "rate_limits": {
                "commands_per_minute": 60,
                "file_ops_per_hour": 100,
                "bash_commands_per_hour": 20
            }
        }
    
    def _compile_dangerous_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for performance."""
        compiled = {
            "bash_patterns": [],
            "file_patterns": [],
            "content_patterns": []
        }
        
        try:
            for pattern in self.validation_rules["dangerous_bash_patterns"]:
                compiled["bash_patterns"].append(re.compile(pattern, re.IGNORECASE | re.MULTILINE))
            
            for pattern in self.validation_rules["dangerous_file_patterns"]:
                compiled["file_patterns"].append(re.compile(pattern, re.IGNORECASE))
            
            for pattern in self.validation_rules["content_security_rules"]["forbidden_content"]:
                compiled["content_patterns"].append(re.compile(pattern, re.IGNORECASE | re.MULTILINE))
                
        except re.error as e:
            logger.error(f"Failed to compile security patterns: {e}")
            raise ValidationError(f"Security pattern compilation failed: {e}")
        
        return compiled
    
    async def validate_command(self, 
                              tool: str, 
                              tool_input: Dict[str, Any], 
                              agent: str = "unknown",
                              agent_identity: Optional[AgentIdentity] = None) -> Dict[str, Any]:
        """
        Securely validate a command with comprehensive security checks.
        
        Args:
            tool: Tool name being invoked
            tool_input: Tool input parameters
            agent: Agent identifier
            agent_identity: Authenticated agent identity (required if auth_required=True)
            
        Returns:
            Validation result with security assessment
        """
        start_time = time.time()
        
        try:
            # Initialize validation result
            validation_result = {
                "id": f"val_{int(time.time()*1000)}",
                "tool": tool,
                "agent": agent,
                "timestamp": start_time,
                "status": "blocked",  # Default to blocked for security
                "reason": "Command validation failed",
                "risk_level": "high",
                "security_checks": [],
                "warnings": [],
                "processing_time_ms": 0
            }
            
            # 1. Authentication check
            auth_result = await self._check_authentication(tool, agent, agent_identity)
            if not auth_result[0]:
                validation_result.update({
                    "status": "blocked",
                    "reason": auth_result[1],
                    "risk_level": "critical",
                    "security_violation": "authentication_failure"
                })
                await self._log_security_event("auth_failure", tool, agent, auth_result[1])
                return validation_result
            
            validation_result["security_checks"].append("authentication_passed")
            
            # 2. Input size and structure validation
            size_result = self._validate_input_size(tool_input)
            if not size_result[0]:
                validation_result.update({
                    "status": "blocked", 
                    "reason": size_result[1],
                    "risk_level": "high",
                    "security_violation": "input_size_exceeded"
                })
                return validation_result
            
            validation_result["security_checks"].append("input_size_validated")
            
            # 3. Content security validation
            content_result = self._validate_content_security(tool_input)
            if not content_result[0]:
                validation_result.update({
                    "status": "blocked",
                    "reason": content_result[1], 
                    "risk_level": "critical",
                    "security_violation": "malicious_content_detected"
                })
                await self._log_security_event("malicious_content", tool, agent, content_result[1])
                return validation_result
            
            validation_result["security_checks"].append("content_security_validated")
            
            # 4. Tool-specific validation
            if tool in self.validation_rules["safe_tools"]:
                validation_result.update({
                    "status": "approved",
                    "reason": f"Safe tool: {tool}",
                    "risk_level": "low"
                })
                
            elif tool == "Bash":
                bash_result = await self._validate_bash_command(tool_input, agent_identity)
                validation_result.update(bash_result)
                
            elif tool in ["Write", "Edit", "MultiEdit"]:
                file_result = await self._validate_file_operation(tool_input, agent_identity)
                validation_result.update(file_result)
                
            elif tool in self.validation_rules["restricted_tools"]:
                restricted_result = await self._validate_restricted_tool(tool, tool_input, agent_identity)
                validation_result.update(restricted_result)
                
            else:
                # Unknown tool - require review
                validation_result.update({
                    "status": "review_required",
                    "reason": f"Unknown tool requires manual review: {tool}",
                    "risk_level": "medium"
                })
            
            # 5. Rate limiting check
            rate_result = self._check_rate_limits(tool, agent)
            if not rate_result[0]:
                validation_result.update({
                    "status": "blocked",
                    "reason": rate_result[1],
                    "risk_level": "medium",
                    "security_violation": "rate_limit_exceeded" 
                })
                return validation_result
            
            validation_result["security_checks"].append("rate_limit_validated")
            
            # 6. Final security assessment
            validation_result["processing_time_ms"] = (time.time() - start_time) * 1000
            
            # Log successful validations for audit
            if validation_result["status"] in ["approved", "review_required"]:
                await self._log_security_event("validation_success", tool, agent, validation_result["reason"])
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            await self._log_security_event("validation_error", tool, agent, str(e))
            
            return {
                "status": "blocked",
                "reason": f"Validation system error: {str(e)[:100]}...",  # Truncate error for security
                "risk_level": "critical",
                "security_violation": "validation_system_error",
                "processing_time_ms": (time.time() - start_time) * 1000
            }
    
    async def _check_authentication(self, 
                                   tool: str, 
                                   agent: str, 
                                   agent_identity: Optional[AgentIdentity]) -> Tuple[bool, str]:
        """Check if agent is authenticated and has required permissions."""
        
        # Skip auth for safe tools if configured
        if not self.auth_required and tool in self.validation_rules["safe_tools"]:
            return True, "Authentication skipped for safe tool"
        
        # Require authentication for restricted operations
        if self.auth_required:
            if not agent_identity:
                return False, "Agent authentication required but not provided"
            
            # Check tool-specific permissions
            required_permissions = {
                "Bash": [Permission.COMMAND_EXECUTION],
                "Write": [Permission.FILE_WRITE],
                "Edit": [Permission.FILE_WRITE], 
                "MultiEdit": [Permission.FILE_WRITE],
                "Task": [Permission.AGENT_COORDINATION]
            }
            
            if tool in required_permissions:
                for perm in required_permissions[tool]:
                    if perm not in agent_identity.permissions:
                        return False, f"Missing required permission: {perm.value}"
        
        return True, "Authentication successful"
    
    def _validate_input_size(self, tool_input: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate input size to prevent DoS attacks."""
        
        # Calculate total input size
        total_size = len(str(tool_input).encode('utf-8'))
        
        if total_size > self.max_command_size:
            return False, f"Input size {total_size} exceeds maximum {self.max_command_size} bytes"
        
        # Check specific field sizes
        for key, value in tool_input.items():
            if isinstance(value, str):
                if key in ['command'] and len(value) > 10000:
                    return False, f"Command length {len(value)} exceeds maximum 10000 characters"
                elif key in ['content', 'new_string'] and len(value) > self.max_file_size:
                    return False, f"Content size {len(value)} exceeds maximum {self.max_file_size} bytes"
                elif len(value) > 100000:  # General string length limit
                    return False, f"Field '{key}' size {len(value)} exceeds maximum 100000 characters"
        
        return True, "Input size validated"
    
    def _validate_content_security(self, tool_input: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate content for malicious patterns and injection attempts."""
        
        # Check all string values in input
        for key, value in tool_input.items():
            if isinstance(value, str):
                # Check for forbidden content patterns
                for pattern in self._compiled_patterns["content_patterns"]:
                    if pattern.search(value):
                        self.suspicious_patterns.add(pattern.pattern)
                        return False, f"Malicious content pattern detected in field '{key}'"
                
                # Check for excessive repeated characters (potential DoS)
                max_repeated = self.validation_rules["content_security_rules"]["max_repeated_chars"]
                for char in set(value):
                    if value.count(char) > max_repeated:
                        return False, f"Excessive repeated character '{char}' detected in field '{key}'"
                
                # Check for potential encoded malicious content
                if self._detect_encoded_content(value):
                    return False, f"Potentially malicious encoded content detected in field '{key}'"
        
        return True, "Content security validated"
    
    def _detect_encoded_content(self, content: str) -> bool:
        """Detect potentially malicious encoded content."""
        
        # Base64 detection (loose check for large encoded blocks)
        import base64
        try:
            if len(content) > 1000 and content.replace('+', '').replace('/', '').replace('=', '').isalnum():
                # Try to decode - if it works and is large, could be malicious
                decoded = base64.b64decode(content + '==', validate=True)
                if len(decoded) > 10000:
                    return True
        except:
            pass
        
        # Hex encoding detection
        if len(content) > 1000 and all(c in '0123456789abcdefABCDEF' for c in content):
            return True
        
        # URL encoding detection
        if content.count('%') > 50:
            return True
        
        return False
    
    async def _validate_bash_command(self, 
                                    tool_input: Dict[str, Any], 
                                    agent_identity: Optional[AgentIdentity]) -> Dict[str, Any]:
        """Validate bash commands with comprehensive security checks."""
        
        command = tool_input.get("command", "")
        result = {"status": "approved", "risk_level": "low", "reason": "Bash command validated"}
        
        # Check against dangerous patterns
        for pattern in self._compiled_patterns["bash_patterns"]:
            match = pattern.search(command)
            if match:
                matched_text = match.group(0)
                self.blocked_commands.append({
                    "command": command[:100] + "..." if len(command) > 100 else command,
                    "pattern": pattern.pattern,
                    "matched_text": matched_text,
                    "timestamp": time.time()
                })
                
                return {
                    "status": "blocked",
                    "reason": f"Dangerous command pattern detected: {matched_text}",
                    "risk_level": "critical",
                    "security_violation": "dangerous_bash_pattern",
                    "concern": "This command could cause system damage or security compromise"
                }
        
        # Check for path traversal in arguments
        if '..' in command or command.count('/') > 10:
            if self._contains_path_traversal(command):
                return {
                    "status": "blocked",
                    "reason": "Path traversal attempt detected",
                    "risk_level": "high", 
                    "security_violation": "path_traversal_attempt"
                }
        
        # Check command length and complexity
        if len(command) > 1000:
            result["status"] = "review_required"
            result["reason"] = "Command exceeds length limit, requires review"
            result["risk_level"] = "medium"
        
        # Check for command chaining that could be dangerous
        dangerous_operators = ['&&', '||', '|', ';', '`', '$(',  '$()', '${']
        operator_count = sum(command.count(op) for op in dangerous_operators)
        
        if operator_count > 3:
            result["status"] = "review_required"
            result["reason"] = "Complex command chaining requires review"
            result["risk_level"] = "medium"
        
        # Check for commonly risky commands (require elevated permissions)
        risky_commands = ['sudo', 'su', 'chmod', 'chown', 'mount', 'umount', 'dd', 'fdisk']
        for risky_cmd in risky_commands:
            if risky_cmd in command.lower():
                # Allow if agent has system admin permissions
                if agent_identity and Permission.SYSTEM_ADMIN in agent_identity.permissions:
                    result["warnings"].append(f"System admin command '{risky_cmd}' allowed with proper permissions")
                else:
                    return {
                        "status": "blocked",
                        "reason": f"System command '{risky_cmd}' requires administrator permissions",
                        "risk_level": "high",
                        "security_violation": "insufficient_permissions"
                    }
        
        return result
    
    async def _validate_file_operation(self, 
                                      tool_input: Dict[str, Any], 
                                      agent_identity: Optional[AgentIdentity]) -> Dict[str, Any]:
        """Validate file operations with security checks."""
        
        file_path = tool_input.get("file_path", "")
        result = {"status": "approved", "risk_level": "low", "reason": "File operation validated"}
        
        # Normalize and validate file path
        try:
            normalized_path = str(Path(file_path).resolve())
        except Exception as e:
            return {
                "status": "blocked",
                "reason": f"Invalid file path: {e}",
                "risk_level": "high",
                "security_violation": "invalid_file_path"
            }
        
        # Check against dangerous file patterns
        for pattern in self._compiled_patterns["file_patterns"]:
            if pattern.match(normalized_path):
                return {
                    "status": "blocked", 
                    "reason": f"Access to protected file/directory: {file_path}",
                    "risk_level": "critical",
                    "security_violation": "protected_file_access",
                    "concern": "Modifying system files could compromise system security"
                }
        
        # Check for path traversal
        if self._contains_path_traversal(file_path):
            return {
                "status": "blocked",
                "reason": "Path traversal attempt detected in file path", 
                "risk_level": "high",
                "security_violation": "path_traversal_attempt"
            }
        
        # Check protected paths
        for protected_path in self.validation_rules["protected_paths"]:
            if normalized_path.startswith(protected_path):
                # Allow if agent has appropriate permissions
                if agent_identity and Permission.SYSTEM_ADMIN in agent_identity.permissions:
                    result["warnings"].append(f"System file access allowed with admin permissions: {protected_path}")
                else:
                    return {
                        "status": "blocked",
                        "reason": f"Access to protected path denied: {protected_path}",
                        "risk_level": "high",
                        "security_violation": "protected_path_access"
                    }
        
        # Check file content size for write operations
        content_fields = ['content', 'new_string']
        for field in content_fields:
            if field in tool_input:
                content = tool_input[field]
                if isinstance(content, str) and len(content) > self.max_file_size:
                    return {
                        "status": "blocked",
                        "reason": f"File content size {len(content)} exceeds limit {self.max_file_size}",
                        "risk_level": "medium",
                        "security_violation": "file_size_exceeded"
                    }
        
        # Check for suspicious file extensions
        dangerous_extensions = ['.sh', '.bat', '.exe', '.scr', '.pif', '.com', '.cmd']
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in dangerous_extensions:
            result["status"] = "review_required"
            result["reason"] = f"Executable file type requires review: {file_ext}"
            result["risk_level"] = "medium"
        
        return result
    
    async def _validate_restricted_tool(self, 
                                       tool: str, 
                                       tool_input: Dict[str, Any], 
                                       agent_identity: Optional[AgentIdentity]) -> Dict[str, Any]:
        """Validate restricted tools with specific security rules."""
        
        tool_rules = self.validation_rules["restricted_tools"].get(tool, {})
        
        # Check authentication requirement
        if tool_rules.get("requires_auth", False):
            if not agent_identity:
                return {
                    "status": "blocked",
                    "reason": f"Tool {tool} requires authentication",
                    "risk_level": "high",
                    "security_violation": "authentication_required"
                }
        
        # Apply tool-specific limits
        if "max_edits" in tool_rules and "edits" in tool_input:
            if len(tool_input["edits"]) > tool_rules["max_edits"]:
                return {
                    "status": "blocked",
                    "reason": f"Too many edits: {len(tool_input['edits'])} > {tool_rules['max_edits']}",
                    "risk_level": "medium"
                }
        
        # Audit requirement
        if tool_rules.get("audit_required", False):
            await self._log_security_event("restricted_tool_usage", tool, 
                                          agent_identity.agent_id if agent_identity else "unknown",
                                          f"Using restricted tool: {tool}")
        
        return {
            "status": "approved",
            "reason": f"Restricted tool {tool} validated with security checks",
            "risk_level": "medium"
        }
    
    def _contains_path_traversal(self, path: str) -> bool:
        """Check for path traversal attempts."""
        dangerous_sequences = ['../', '..\\', '%2e%2e%2f', '%2e%2e%5c', '..%2f', '..%5c']
        path_lower = path.lower()
        
        return any(seq in path_lower for seq in dangerous_sequences)
    
    def _check_rate_limits(self, tool: str, agent: str) -> Tuple[bool, str]:
        """Check rate limiting for commands (simplified implementation)."""
        # In a full implementation, this would track requests per agent
        # For now, just return success
        return True, "Rate limit check passed"
    
    async def _log_security_event(self, event_type: str, tool: str, agent: str, details: str):
        """Log security events to event store for audit."""
        if not self.event_store:
            return
        
        try:
            event = Event(
                event_type=EventType.SYSTEM_STARTED,  # Use appropriate event type
                aggregate_id=f"validator_{agent}",
                aggregate_type="security_validation",
                data={
                    "event_type": event_type,
                    "tool": tool,
                    "agent": agent,
                    "details": details,
                    "timestamp": time.time()
                },
                source_component="secure_validator",
                metadata={"security_event": True}
            )
            
            await self.event_store.append(event)
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Get comprehensive security statistics."""
        return {
            "validation_rules": {
                "dangerous_patterns": len(self.validation_rules["dangerous_bash_patterns"]),
                "file_patterns": len(self.validation_rules["dangerous_file_patterns"]),
                "protected_paths": len(self.validation_rules["protected_paths"])
            },
            "security_monitoring": {
                "blocked_commands": len(self.blocked_commands),
                "suspicious_patterns": len(self.suspicious_patterns),
                "auth_required": self.auth_required
            },
            "performance": {
                "compiled_patterns": sum(len(patterns) for patterns in self._compiled_patterns.values())
            },
            "recent_blocked": self.blocked_commands[-10:] if self.blocked_commands else []
        }
    
    # Legacy methods for backward compatibility
    
    async def validate_with_pair(self, tool: str, tool_input: Dict[str, Any], agent: str = "unknown") -> Dict[str, Any]:
        """Validate command with pair programming support (legacy compatibility)."""
        result = await self.validate_command(tool, tool_input, agent)
        
        # Add pair programming logic if needed
        if (self.pair_mode == "COLLABORATIVE" and 
            result["status"] == "review_required" and 
            self.current_session_id):
            
            result["pair_consultation"] = True
            result["reason"] += " - Collaborative review requested"
        
        return result
    
    def set_pair_mode(self, mode: str):
        """Set the pair programming mode."""
        if mode in ["PASSIVE", "ACTIVE", "COLLABORATIVE", "REVIEW"]:
            self.pair_mode = mode
            logger.info(f"Pair mode set to: {mode}")
        else:
            logger.warning(f"Invalid pair mode: {mode}")
    
    def end_pair_session(self):
        """End the current pair programming session."""
        if self.current_session_id:
            logger.info(f"Ending pair session: {self.current_session_id}")
            self.current_session_id = None
            self.pair_mode = "PASSIVE"


# Alias for backward compatibility
CommandValidator = SecureCommandValidator