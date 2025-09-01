"""
Elicitation data models with cryptographic security.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum


class ElicitationStatus(str, Enum):
    """Elicitation request status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class SecureElicitationRequest:
    """Cryptographically signed elicitation request."""
    id: str
    from_agent: str
    to_agent: str
    message: str
    schema: Dict[str, Any]
    nonce: str
    status: ElicitationStatus
    created_at: float
    expires_at: float
    request_signature: str
    expected_response_key: str
    security_context: Dict[str, Any]
    
    # Event sourcing metadata
    sequence: Optional[int] = None
    snapshot_sequence: Optional[int] = None
    
    # Response data (populated when responded)
    response_type: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    responded_at: Optional[float] = None
    response_sequence: Optional[int] = None


@dataclass
class SecureElicitationResponse:
    """Cryptographically signed elicitation response."""
    elicitation_id: str
    responding_agent: str
    response_type: str  # accept, decline, cancel
    data: Optional[Dict[str, Any]]
    responded_at: float
    response_signature: str
    security_context: Dict[str, Any]
    
    # Event sourcing metadata
    sequence: Optional[int] = None
    causation_id: Optional[str] = None  # Links to request event


@dataclass
class ElicitationMetrics:
    """Performance and security metrics for elicitation."""
    # Performance metrics
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    
    # Throughput metrics
    requests_per_minute: int = 0
    responses_per_minute: int = 0
    
    # Reliability metrics
    delivery_rate: float = 0.0
    timeout_rate: float = 0.0
    error_rate: float = 0.0
    
    # Security metrics
    impersonation_attempts: int = 0
    replay_attempts: int = 0
    rate_limit_violations: int = 0
    signature_failures: int = 0
    
    # Resource metrics
    active_elicitations: int = 0
    pending_elicitations: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0