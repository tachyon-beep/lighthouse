"""
Speed Layer Data Models

Core data structures for the speed layer validation system.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel


class ValidationDecision(str, Enum):
    """Validation decision outcomes"""
    APPROVED = "approved"
    BLOCKED = "blocked"  
    ESCALATE = "escalate"
    UNCERTAIN = "uncertain"


class ValidationConfidence(str, Enum):
    """Confidence levels for validation decisions"""
    HIGH = "high"        # >95% confidence
    MEDIUM = "medium"    # 80-95% confidence
    LOW = "low"         # 50-80% confidence
    UNKNOWN = "unknown"  # <50% confidence


@dataclass(frozen=True)
class ValidationRequest:
    """Immutable validation request structure"""
    
    # Core request data
    tool_name: str
    tool_input: Dict[str, Any]
    agent_id: str
    
    # Metadata
    request_id: str = field(default_factory=lambda: f"req_{int(time.time()*1000)}")
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Performance tracking
    command_hash: str = field(init=False)
    
    def __post_init__(self):
        """Generate command hash for caching"""
        content = f"{self.tool_name}:{str(sorted(self.tool_input.items()))}"
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
        object.__setattr__(self, 'command_hash', hash_value)
    
    @property
    def is_bash_command(self) -> bool:
        """Check if this is a bash command"""
        return self.tool_name.lower() == "bash"
    
    @property
    def is_file_operation(self) -> bool:
        """Check if this involves file operations"""
        return self.tool_name.lower() in ["write", "edit", "multiedit"]
    
    @property
    def command_text(self) -> str:
        """Get the actual command text"""
        if self.is_bash_command:
            return self.tool_input.get('command', '')
        elif self.is_file_operation:
            return self.tool_input.get('file_path', '')
        return str(self.tool_input)


@dataclass
class ValidationResult:
    """Result of validation processing"""
    
    # Core result
    decision: ValidationDecision
    confidence: ValidationConfidence
    reason: str
    
    # Metadata
    request_id: str
    processing_time_ms: float
    cache_hit: bool = False
    cache_layer: Optional[str] = None  # "memory", "policy", "pattern"
    
    # Expert escalation data
    expert_required: bool = False
    expert_context: Optional[Dict[str, Any]] = None
    
    # Security data
    risk_level: str = "low"  # low, medium, high, critical
    security_concerns: List[str] = field(default_factory=list)
    
    # Performance data
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'decision': self.decision.value,
            'confidence': self.confidence.value,
            'reason': self.reason,
            'request_id': self.request_id,
            'processing_time_ms': self.processing_time_ms,
            'cache_hit': self.cache_hit,
            'cache_layer': self.cache_layer,
            'expert_required': self.expert_required,
            'expert_context': self.expert_context,
            'risk_level': self.risk_level,
            'security_concerns': self.security_concerns,
            'timestamp': self.timestamp
        }


@dataclass
class CacheEntry:
    """Speed layer cache entry"""
    
    result: ValidationResult
    created_at: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    ttl_seconds: int = 300  # 5 minutes default
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return time.time() - self.created_at > self.ttl_seconds
    
    @property
    def is_hot(self) -> bool:
        """Check if this is a frequently accessed entry"""
        return self.access_count > 10
    
    def access(self) -> ValidationResult:
        """Mark as accessed and return result"""
        self.access_count += 1
        self.last_accessed = time.time()
        return self.result


class PolicyRule(BaseModel):
    """Policy engine rule definition"""
    
    rule_id: str
    pattern: str  # Regex or glob pattern
    decision: ValidationDecision
    confidence: ValidationConfidence
    reason: str
    
    # Rule metadata
    created_at: datetime
    created_by: str  # Agent or system that created the rule
    priority: int = 100  # Higher priority = evaluated first
    
    # Usage statistics
    match_count: int = 0
    last_matched: Optional[datetime] = None
    
    # Conditions
    tool_names: List[str] = []  # Empty = applies to all tools
    agent_patterns: List[str] = []  # Empty = applies to all agents
    
    def matches_request(self, request: ValidationRequest) -> bool:
        """Check if this rule matches the request"""
        import re
        
        # Check tool name restriction
        if self.tool_names and request.tool_name not in self.tool_names:
            return False
            
        # Check agent pattern restriction
        if self.agent_patterns:
            agent_match = any(
                re.search(pattern, request.agent_id) 
                for pattern in self.agent_patterns
            )
            if not agent_match:
                return False
        
        # Check main pattern
        text_to_match = request.command_text
        try:
            return bool(re.search(self.pattern, text_to_match, re.IGNORECASE))
        except re.error:
            # Fallback to simple string matching
            return self.pattern.lower() in text_to_match.lower()
    
    def apply_to_request(self, request: ValidationRequest) -> ValidationResult:
        """Apply this rule to generate a validation result"""
        # Update usage statistics
        self.match_count += 1
        self.last_matched = datetime.now()
        
        return ValidationResult(
            decision=self.decision,
            confidence=self.confidence,
            reason=f"Policy rule {self.rule_id}: {self.reason}",
            request_id=request.request_id,
            processing_time_ms=1.0,  # Policy rules are fast
            cache_layer="policy"
        )


@dataclass
class PatternPrediction:
    """ML pattern cache prediction"""
    
    decision: ValidationDecision
    confidence_score: float  # 0.0 to 1.0
    model_version: str
    feature_vector: List[float]
    
    # Explanation data for transparency
    top_features: List[Tuple[str, float]]  # (feature_name, importance)
    similar_examples: List[str] = field(default_factory=list)
    
    @property
    def confidence_level(self) -> ValidationConfidence:
        """Convert numeric confidence to level"""
        if self.confidence_score >= 0.95:
            return ValidationConfidence.HIGH
        elif self.confidence_score >= 0.8:
            return ValidationConfidence.MEDIUM
        elif self.confidence_score >= 0.5:
            return ValidationConfidence.LOW
        else:
            return ValidationConfidence.UNKNOWN
    
    def to_validation_result(self, request: ValidationRequest, processing_time: float) -> ValidationResult:
        """Convert to validation result"""
        # Build reason from top features
        feature_explanation = ", ".join([
            f"{name} ({weight:.2f})" 
            for name, weight in self.top_features[:3]
        ])
        
        reason = f"ML pattern match (v{self.model_version}): {feature_explanation}"
        
        return ValidationResult(
            decision=self.decision,
            confidence=self.confidence_level,
            reason=reason,
            request_id=request.request_id,
            processing_time_ms=processing_time,
            cache_layer="pattern"
        )


@dataclass
class SpeedLayerMetrics:
    """Performance metrics for speed layer"""
    
    # Request counts
    total_requests: int = 0
    memory_cache_hits: int = 0
    policy_cache_hits: int = 0
    pattern_cache_hits: int = 0
    expert_escalations: int = 0
    
    # Timing data
    avg_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    
    # Error counts
    cache_errors: int = 0
    policy_errors: int = 0
    pattern_errors: int = 0
    
    @property
    def cache_hit_ratio(self) -> float:
        """Overall cache hit ratio"""
        if self.total_requests == 0:
            return 0.0
        
        total_hits = (
            self.memory_cache_hits + 
            self.policy_cache_hits + 
            self.pattern_cache_hits
        )
        return total_hits / self.total_requests
    
    @property
    def expert_escalation_rate(self) -> float:
        """Rate of expert escalations"""
        if self.total_requests == 0:
            return 0.0
        return self.expert_escalations / self.total_requests
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting"""
        return {
            'total_requests': self.total_requests,
            'cache_hit_ratio': self.cache_hit_ratio,
            'expert_escalation_rate': self.expert_escalation_rate,
            'avg_response_time_ms': self.avg_response_time_ms,
            'p99_response_time_ms': self.p99_response_time_ms,
            'memory_cache_hits': self.memory_cache_hits,
            'policy_cache_hits': self.policy_cache_hits,
            'pattern_cache_hits': self.pattern_cache_hits,
            'expert_escalations': self.expert_escalations,
            'errors': {
                'cache_errors': self.cache_errors,
                'policy_errors': self.policy_errors,
                'pattern_errors': self.pattern_errors
            }
        }