"""
LLM Response Security Validation Framework

Validates all LLM responses for security threats before they reach the user.
Part of Plan Charlie Phase 2 implementation.

Security checks include:
- Malicious code injection detection
- Information disclosure prevention
- Social engineering attack detection
- Prompt injection attack detection
- Output sanitization and safe rendering
"""

import ast
import json
import re
import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple, Union
import urllib.parse

logger = logging.getLogger(__name__)


class SecurityThreatType(Enum):
    """Types of security threats in LLM responses."""
    MALICIOUS_CODE = "malicious_code"
    INFORMATION_DISCLOSURE = "information_disclosure"
    SOCIAL_ENGINEERING = "social_engineering"
    PROMPT_INJECTION = "prompt_injection"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    SCRIPT_INJECTION = "script_injection"
    CREDENTIAL_EXPOSURE = "credential_exposure"
    UNSAFE_URL = "unsafe_url"
    UNSAFE_FILE_OPERATION = "unsafe_file_operation"


class ValidationSeverity(Enum):
    """Severity levels for validation findings."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ValidationAction(Enum):
    """Actions to take on validation findings."""
    ALLOW = "allow"
    SANITIZE = "sanitize"
    BLOCK = "block"
    ESCALATE = "escalate"


@dataclass
class SecurityFinding:
    """Represents a security finding in an LLM response."""
    threat_type: SecurityThreatType
    severity: ValidationSeverity
    confidence: float  # 0.0 to 1.0
    description: str
    location: str  # Where in the response the threat was found
    suggested_action: ValidationAction
    context: Dict[str, Any]
    finding_id: str
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['threat_type'] = self.threat_type.value
        data['severity'] = self.severity.value
        data['suggested_action'] = self.suggested_action.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class ValidationResult:
    """Result of LLM response validation."""
    response_id: str
    original_response: str
    sanitized_response: Optional[str]
    is_safe: bool
    findings: List[SecurityFinding]
    overall_risk_score: float  # 0.0 to 1.0
    recommended_action: ValidationAction
    validation_timestamp: datetime
    processing_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['findings'] = [f.to_dict() for f in self.findings]
        data['recommended_action'] = self.recommended_action.value
        data['validation_timestamp'] = self.validation_timestamp.isoformat()
        return data


class MaliciousCodeDetector:
    """Detects potentially malicious code in LLM responses."""
    
    def __init__(self):
        """Initialize malicious code detector."""
        self.dangerous_functions = {
            # File system operations  
            'os.remove', 'os.rmdir', 'os.unlink', 'shutil.rmtree',
            '__import__', 'exec', 'eval', 'compile',
            
            # Network operations
            'socket.socket', 'urllib.request', 'requests.get', 'requests.post',
            'http.client', 'subprocess.call', 'subprocess.run',
            
            # System operations
            'os.system', 'os.popen', 'commands.getoutput',
            'platform.system', 'getpass.getpass',
            
            # Dangerous builtins
            '__builtins__', '__globals__', '__locals__',
            'globals', 'locals', 'vars', 'dir'
        }
        
        # Context-sensitive dangerous patterns - these need additional context checking
        self.context_dangerous_functions = {
            'open': ['/etc/passwd', '/etc/shadow', '/etc/hosts', '.ssh', 'System32']
        }
        
        # Safe functions that should be excluded from dangerous detection
        self.safe_functions = {
            'print', 'len', 'str', 'int', 'float', 'bool', 'list', 'dict',
            'range', 'enumerate', 'zip', 'map', 'filter', 'sorted'
        }
        
        self.dangerous_patterns = [            
            # Path traversal
            r'\.\.[\\/]',
            r'[\\/]\.\.[\\/]',
            
            # Command execution
            r'sudo\s+',
            r'rm\s+-rf',
            r'chmod\s+777',
            r'dd\s+if=',
            
            # Network requests
            r'curl\s+',
            r'wget\s+',
            r'nc\s+',
            r'netcat\s+',
            
            # Shell injection (more specific patterns)
            r';\s*rm\s+',
            r'&&\s*rm\s+',
            r'\|\s*rm\s+',
            r'`[^`]*rm[^`]*`',
            r'\$\([^)]*rm[^)]*\)',
        ]
        
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.dangerous_patterns]
    
    def detect(self, text: str) -> List[SecurityFinding]:
        """Detect malicious code patterns in text."""
        findings = []
        
        # Check for dangerous function calls (but exclude safe functions)
        for func in self.dangerous_functions:
            if func in text:
                # Check if it's actually a safe function call
                func_name = func.split('.')[-1]  # Get function name without module
                if func_name not in self.safe_functions:
                    findings.append(SecurityFinding(
                        threat_type=SecurityThreatType.MALICIOUS_CODE,
                        severity=ValidationSeverity.HIGH,
                        confidence=0.8,
                        description=f"Potentially dangerous function call: {func}",
                        location=f"Function: {func}",
                        suggested_action=ValidationAction.SANITIZE,
                        context={'function': func, 'pattern_type': 'dangerous_function'},
                        finding_id=hashlib.md5(f"dangerous_func_{func}_{text[:100]}".encode()).hexdigest()[:16],
                        timestamp=datetime.utcnow()
                    ))
        
        # Check context-sensitive dangerous functions
        for func, dangerous_contexts in self.context_dangerous_functions.items():
            if func in text:
                for context in dangerous_contexts:
                    if context in text:
                        findings.append(SecurityFinding(
                            threat_type=SecurityThreatType.MALICIOUS_CODE,
                            severity=ValidationSeverity.HIGH,
                            confidence=0.9,
                            description=f"Dangerous {func} call with sensitive path: {context}",
                            location=f"Function: {func}, Context: {context}",
                            suggested_action=ValidationAction.SANITIZE,
                            context={'function': func, 'dangerous_context': context, 'pattern_type': 'context_dangerous'},
                            finding_id=hashlib.md5(f"context_func_{func}_{context}_{text[:50]}".encode()).hexdigest()[:16],
                            timestamp=datetime.utcnow()
                        ))
                        break  # Only report once per function
        
        # Check for dangerous patterns
        for i, pattern in enumerate(self.compiled_patterns):
            matches = pattern.finditer(text)
            for match in matches:
                findings.append(SecurityFinding(
                    threat_type=SecurityThreatType.MALICIOUS_CODE,
                    severity=ValidationSeverity.MEDIUM,
                    confidence=0.6,
                    description=f"Suspicious pattern detected: {match.group()}",
                    location=f"Position: {match.start()}-{match.end()}",
                    suggested_action=ValidationAction.SANITIZE,
                    context={'pattern': self.dangerous_patterns[i], 'match': match.group()},
                    finding_id=hashlib.md5(f"pattern_{i}_{match.group()}".encode()).hexdigest()[:16],
                    timestamp=datetime.utcnow()
                ))
        
        # Try to parse as Python code and analyze AST
        try:
            tree = ast.parse(text)
            ast_findings = self._analyze_ast(tree)
            findings.extend(ast_findings)
        except SyntaxError:
            # Not valid Python, which is fine
            pass
        except Exception as e:
            logger.debug(f"AST analysis failed: {str(e)}")
        
        return findings
    
    def _analyze_ast(self, tree: ast.AST) -> List[SecurityFinding]:
        """Analyze Python AST for dangerous operations."""
        findings = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check function calls
                if hasattr(node.func, 'id') and node.func.id in ['exec', 'eval', 'compile']:
                    findings.append(SecurityFinding(
                        threat_type=SecurityThreatType.MALICIOUS_CODE,
                        severity=ValidationSeverity.CRITICAL,
                        confidence=0.95,
                        description=f"Dangerous Python function: {node.func.id}",
                        location=f"Line: {getattr(node, 'lineno', 'unknown')}",
                        suggested_action=ValidationAction.BLOCK,
                        context={'function': node.func.id, 'analysis': 'ast'},
                        finding_id=hashlib.md5(f"ast_call_{node.func.id}".encode()).hexdigest()[:16],
                        timestamp=datetime.utcnow()
                    ))
                
                # Check attribute calls like os.system
                elif hasattr(node.func, 'attr'):
                    func_name = f"{getattr(node.func.value, 'id', 'unknown')}.{node.func.attr}"
                    if func_name in self.dangerous_functions:
                        findings.append(SecurityFinding(
                            threat_type=SecurityThreatType.MALICIOUS_CODE,
                            severity=ValidationSeverity.HIGH,
                            confidence=0.9,
                            description=f"Dangerous method call: {func_name}",
                            location=f"Line: {getattr(node, 'lineno', 'unknown')}",
                            suggested_action=ValidationAction.SANITIZE,
                            context={'function': func_name, 'analysis': 'ast'},
                            finding_id=hashlib.md5(f"ast_attr_{func_name}".encode()).hexdigest()[:16],
                            timestamp=datetime.utcnow()
                        ))
            
            elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                # Check dangerous imports
                module_names = []
                if isinstance(node, ast.Import):
                    module_names = [alias.name for alias in node.names]
                else:  # ImportFrom
                    if node.module:
                        module_names = [node.module]
                
                dangerous_modules = ['os', 'subprocess', 'socket', 'urllib', 'requests', 'shutil']
                for module in module_names:
                    if any(module.startswith(dm) for dm in dangerous_modules):
                        findings.append(SecurityFinding(
                            threat_type=SecurityThreatType.MALICIOUS_CODE,
                            severity=ValidationSeverity.MEDIUM,
                            confidence=0.7,
                            description=f"Potentially dangerous import: {module}",
                            location=f"Line: {getattr(node, 'lineno', 'unknown')}",
                            suggested_action=ValidationAction.SANITIZE,
                            context={'module': module, 'analysis': 'ast'},
                            finding_id=hashlib.md5(f"ast_import_{module}".encode()).hexdigest()[:16],
                            timestamp=datetime.utcnow()
                        ))
        
        return findings


class InformationDisclosureDetector:
    """Detects potential information disclosure in LLM responses."""
    
    def __init__(self):
        """Initialize information disclosure detector."""
        self.sensitive_patterns = [
            # Credentials
            (r'password\s*[:=]\s*["\']?([^"\'\s]+)', 'password', ValidationSeverity.CRITICAL),
            (r'api[_\-]?key\s*[:=]\s*["\']?([\w\-\.]{10,})', 'api_key', ValidationSeverity.CRITICAL),  # Reduced minimum length
            (r'token\s*[:=]\s*["\']?([\w\-\.]{15,})', 'token', ValidationSeverity.CRITICAL),  # Reduced minimum length
            (r'secret\s*[:=]\s*["\']?([^"\'\s]{8,})', 'secret', ValidationSeverity.HIGH),
            
            # File paths
            (r'(/etc/passwd|/etc/shadow|/etc/hosts)', 'system_file', ValidationSeverity.HIGH),
            (r'C:\\\\?Windows\\\\?System32', 'windows_system', ValidationSeverity.MEDIUM),  # Fixed pattern
            (r'/home/[^/\s]+/\.ssh/', 'ssh_directory', ValidationSeverity.HIGH),
            
            # Network information
            (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', 'ip_address', ValidationSeverity.LOW),
            (r'https?://[^\s]+', 'url', ValidationSeverity.LOW),
            
            # Database connections
            (r'mongodb://[^"\'\s]+', 'mongodb_connection', ValidationSeverity.MEDIUM),
            (r'postgresql://[^"\'\s]+', 'postgres_connection', ValidationSeverity.MEDIUM),
            (r'mysql://[^"\'\s]+', 'mysql_connection', ValidationSeverity.MEDIUM),
        ]
        
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), info_type, severity)
            for pattern, info_type, severity in self.sensitive_patterns
        ]
    
    def detect(self, text: str) -> List[SecurityFinding]:
        """Detect information disclosure patterns in text."""
        findings = []
        
        for pattern, info_type, severity in self.compiled_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                findings.append(SecurityFinding(
                    threat_type=SecurityThreatType.INFORMATION_DISCLOSURE,
                    severity=severity,
                    confidence=0.8,
                    description=f"Potential {info_type} disclosure: {match.group()[:50]}...",
                    location=f"Position: {match.start()}-{match.end()}",
                    suggested_action=ValidationAction.SANITIZE if severity != ValidationSeverity.CRITICAL else ValidationAction.BLOCK,
                    context={'info_type': info_type, 'matched_text': match.group()},
                    finding_id=hashlib.md5(f"disclosure_{info_type}_{match.group()}".encode()).hexdigest()[:16],
                    timestamp=datetime.utcnow()
                ))
        
        return findings


class PromptInjectionDetector:
    """Detects prompt injection attacks in LLM responses."""
    
    def __init__(self):
        """Initialize prompt injection detector."""
        self.injection_patterns = [
            # Direct injection attempts
            r'ignore\s+(?:previous|all)\s+instructions?',
            r'forget\s+(?:everything|all)\s+(?:before|above)',
            r'disregard\s+(?:previous|all|prior)\s+(?:instructions?|commands?)',
            r'new\s+instructions?:\s*',
            r'system:\s*',
            r'assistant:\s*',
            r'user:\s*',
            
            # Role manipulation
            r'you\s+are\s+now\s+',
            r'act\s+as\s+(?:if\s+you\s+are\s+)?(?:a\s+)?(?:different|another)',
            r'pretend\s+(?:to\s+be\s+)?(?:that\s+you\s+are)?',
            r'roleplay\s+as',
            
            # Instruction override
            r'override\s+(?:previous|all)\s+',
            r'replace\s+(?:previous|all)\s+',
            r'update\s+(?:your|the)\s+instructions?',
            
            # Jailbreak attempts
            r'jailbreak\s*mode',
            r'developer\s*mode',
            r'bypass\s+(?:safety|security|restrictions?)',
            r'unrestricted\s+(?:mode|access)',
        ]
        
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.injection_patterns]
    
    def detect(self, text: str) -> List[SecurityFinding]:
        """Detect prompt injection patterns in text."""
        findings = []
        
        for i, pattern in enumerate(self.compiled_patterns):
            matches = pattern.finditer(text)
            for match in matches:
                findings.append(SecurityFinding(
                    threat_type=SecurityThreatType.PROMPT_INJECTION,
                    severity=ValidationSeverity.HIGH,
                    confidence=0.85,
                    description=f"Potential prompt injection: {match.group()[:50]}...",
                    location=f"Position: {match.start()}-{match.end()}",
                    suggested_action=ValidationAction.BLOCK,
                    context={'pattern': self.injection_patterns[i], 'matched_text': match.group()},
                    finding_id=hashlib.md5(f"injection_{i}_{match.group()}".encode()).hexdigest()[:16],
                    timestamp=datetime.utcnow()
                ))
        
        return findings


class ResponseSanitizer:
    """Sanitizes LLM responses to remove security threats."""
    
    def __init__(self):
        """Initialize response sanitizer."""
        self.sanitization_rules = {
            # Remove dangerous function calls
            SecurityThreatType.MALICIOUS_CODE: self._sanitize_malicious_code,
            SecurityThreatType.INFORMATION_DISCLOSURE: self._sanitize_information_disclosure,
            SecurityThreatType.PROMPT_INJECTION: self._sanitize_prompt_injection,
            SecurityThreatType.CREDENTIAL_EXPOSURE: self._sanitize_credentials,
        }
    
    def sanitize(self, text: str, findings: List[SecurityFinding]) -> str:
        """Sanitize text based on security findings."""
        sanitized_text = text
        
        # Group findings by threat type
        findings_by_type = {}
        for finding in findings:
            if finding.threat_type not in findings_by_type:
                findings_by_type[finding.threat_type] = []
            findings_by_type[finding.threat_type].append(finding)
        
        # Apply sanitization rules
        for threat_type, threat_findings in findings_by_type.items():
            if threat_type in self.sanitization_rules:
                sanitized_text = self.sanitization_rules[threat_type](sanitized_text, threat_findings)
        
        return sanitized_text
    
    def _sanitize_malicious_code(self, text: str, findings: List[SecurityFinding]) -> str:
        """Sanitize malicious code patterns."""
        sanitized = text
        
        for finding in findings:
            if 'function' in finding.context:
                func_name = finding.context['function']
                # Replace dangerous functions with safe alternatives
                sanitized = re.sub(
                    rf'\b{re.escape(func_name)}\b',
                    f'[SANITIZED: {func_name}]',
                    sanitized,
                    flags=re.IGNORECASE
                )
            elif 'matched_text' in finding.context:
                matched = finding.context['matched_text']
                sanitized = sanitized.replace(matched, '[SANITIZED: suspicious_pattern]')
        
        return sanitized
    
    def _sanitize_information_disclosure(self, text: str, findings: List[SecurityFinding]) -> str:
        """Sanitize information disclosure patterns."""
        sanitized = text
        
        for finding in findings:
            if 'matched_text' in finding.context:
                matched = finding.context['matched_text']
                info_type = finding.context.get('info_type', 'sensitive_info')
                sanitized = sanitized.replace(matched, f'[REDACTED: {info_type}]')
        
        return sanitized
    
    def _sanitize_prompt_injection(self, text: str, findings: List[SecurityFinding]) -> str:
        """Sanitize prompt injection attempts."""
        sanitized = text
        
        for finding in findings:
            if 'matched_text' in finding.context:
                matched = finding.context['matched_text']
                sanitized = sanitized.replace(matched, '[REMOVED: potential_injection]')
        
        return sanitized
    
    def _sanitize_credentials(self, text: str, findings: List[SecurityFinding]) -> str:
        """Sanitize credential exposure."""
        sanitized = text
        
        for finding in findings:
            if 'matched_text' in finding.context:
                matched = finding.context['matched_text']
                sanitized = sanitized.replace(matched, '[REDACTED: credentials]')
        
        return sanitized


class LLMResponseValidator:
    """Main LLM response security validation system."""
    
    def __init__(self):
        """Initialize LLM response validator."""
        self.code_detector = MaliciousCodeDetector()
        self.disclosure_detector = InformationDisclosureDetector()
        self.injection_detector = PromptInjectionDetector()
        self.sanitizer = ResponseSanitizer()
        
        # Risk scoring weights
        self.severity_weights = {
            ValidationSeverity.LOW: 0.2,
            ValidationSeverity.MEDIUM: 0.5,
            ValidationSeverity.HIGH: 0.8,
            ValidationSeverity.CRITICAL: 1.0
        }
        
        # Action thresholds
        self.risk_thresholds = {
            'block': 0.7,      # Block if risk score >= 0.7
            'sanitize': 0.15,  # Sanitize if risk score >= 0.15
            'escalate': 0.8    # Escalate if risk score >= 0.8
        }
    
    async def validate_response(self, response_text: str, response_id: Optional[str] = None) -> ValidationResult:
        """
        Validate LLM response for security threats.
        
        Args:
            response_text: LLM response text to validate
            response_id: Optional response identifier
            
        Returns:
            Validation result with findings and recommendations
        """
        start_time = datetime.utcnow()
        
        if not response_id:
            response_id = hashlib.md5(f"{response_text[:100]}_{start_time}".encode()).hexdigest()[:16]
        
        logger.debug(f"Validating LLM response {response_id}")
        
        # Run all detectors
        all_findings = []
        
        # Detect malicious code
        code_findings = self.code_detector.detect(response_text)
        all_findings.extend(code_findings)
        
        # Detect information disclosure
        disclosure_findings = self.disclosure_detector.detect(response_text)
        all_findings.extend(disclosure_findings)
        
        # Detect prompt injection
        injection_findings = self.injection_detector.detect(response_text)
        all_findings.extend(injection_findings)
        
        # Calculate overall risk score
        risk_score = self._calculate_risk_score(all_findings)
        
        # Determine recommended action
        recommended_action = self._determine_action(risk_score, all_findings)
        
        # Sanitize response if needed
        sanitized_response = None
        if recommended_action in [ValidationAction.SANITIZE, ValidationAction.BLOCK]:
            sanitized_response = self.sanitizer.sanitize(response_text, all_findings)
        
        # Determine if response is safe
        is_safe = risk_score < self.risk_thresholds['sanitize'] and recommended_action == ValidationAction.ALLOW
        
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds() * 1000
        
        result = ValidationResult(
            response_id=response_id,
            original_response=response_text,
            sanitized_response=sanitized_response,
            is_safe=is_safe,
            findings=all_findings,
            overall_risk_score=risk_score,
            recommended_action=recommended_action,
            validation_timestamp=end_time,
            processing_time_ms=processing_time
        )
        
        logger.info(f"Response {response_id} validation complete: risk={risk_score:.2f}, action={recommended_action.value}, findings={len(all_findings)}")
        
        return result
    
    def _calculate_risk_score(self, findings: List[SecurityFinding]) -> float:
        """Calculate overall risk score from findings."""
        if not findings:
            return 0.0
        
        # Weight findings by severity and confidence
        total_risk = 0.0
        for finding in findings:
            severity_weight = self.severity_weights[finding.severity]
            risk_contribution = severity_weight * finding.confidence
            total_risk += risk_contribution
        
        # Normalize to 0-1 range (cap at 1.0)
        return min(total_risk / len(findings), 1.0)
    
    def _determine_action(self, risk_score: float, findings: List[SecurityFinding]) -> ValidationAction:
        """Determine recommended action based on risk score and findings."""
        # Check for critical findings that should always be blocked
        critical_findings = [f for f in findings if f.severity == ValidationSeverity.CRITICAL]
        if critical_findings:
            return ValidationAction.BLOCK
        
        # Check for findings that suggest escalation
        if risk_score >= self.risk_thresholds['escalate']:
            return ValidationAction.ESCALATE
        
        # Check for findings that require blocking
        if risk_score >= self.risk_thresholds['block']:
            return ValidationAction.BLOCK
        
        # Check for findings that require sanitization
        if risk_score >= self.risk_thresholds['sanitize']:
            return ValidationAction.SANITIZE
        
        # Default to allow
        return ValidationAction.ALLOW


# Global validator instance
_global_validator: Optional[LLMResponseValidator] = None


def get_llm_response_validator() -> LLMResponseValidator:
    """Get global LLM response validator instance."""
    global _global_validator
    if _global_validator is None:
        _global_validator = LLMResponseValidator()
    return _global_validator


async def validate_llm_response(response_text: str, response_id: Optional[str] = None) -> ValidationResult:
    """Convenience function to validate LLM response."""
    validator = get_llm_response_validator()
    return await validator.validate_response(response_text, response_id)