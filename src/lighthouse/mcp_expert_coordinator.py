#!/usr/bin/env python3
"""
MCP Expert Coordinator Integration

Provides enhanced multi-agent coordination specifically for MCP operations,
integrating with the Bridge's expert system for intelligent validation and
collaborative decision-making.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from lighthouse.bridge.expert_coordination.coordinator import ExpertCoordinator
from lighthouse.bridge.security.session_security import SessionInfo

logger = logging.getLogger(__name__)


class MCPOperationType(Enum):
    """Types of MCP operations requiring expert coordination"""
    HEALTH_CHECK = "health_check"
    SESSION_CREATE = "session_create"  
    EVENT_STORE = "event_store"
    EVENT_QUERY = "event_query"
    SESSION_VALIDATE = "session_validate"
    DANGEROUS_COMMAND = "dangerous_command"


@dataclass
class MCPCoordinationRequest:
    """Request for expert coordination of MCP operation"""
    operation_type: MCPOperationType
    tool_name: str
    tool_input: Dict[str, Any]
    session: SessionInfo
    context: Dict[str, Any]
    risk_level: str = "medium"


@dataclass 
class MCPCoordinationResult:
    """Result of expert coordination"""
    approved: bool
    reason: str
    experts_consulted: List[str]
    coordination_time_ms: float
    security_flags: Set[str]
    recommendations: List[str]
    escalation_required: bool = False


class MCPExpertCoordinator:
    """
    MCP Expert Coordination System
    
    Provides intelligent multi-agent coordination for MCP operations,
    routing complex decisions through expert agents while maintaining
    fast response times for simple operations.
    """
    
    def __init__(self, expert_coordinator: ExpertCoordinator):
        self.expert_coordinator = expert_coordinator
        self.coordination_cache: Dict[str, MCPCoordinationResult] = {}
        
        # Performance tracking
        self.coordination_count = 0
        self.cache_hits = 0
        self.expert_escalations = 0
    
    async def coordinate_mcp_operation(self, request: MCPCoordinationRequest) -> MCPCoordinationResult:
        """
        Coordinate MCP operation through expert agents
        
        Uses intelligent routing to balance performance with security:
        - Simple operations: Fast local validation
        - Complex operations: Full expert coordination
        - Dangerous operations: Mandatory expert review
        """
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Check cache for repeated operations
            cache_key = self._get_cache_key(request)
            if cache_key in self.coordination_cache:
                cached_result = self.coordination_cache[cache_key]
                self.cache_hits += 1
                return cached_result
            
            # Route based on operation type and risk level
            if await self._requires_expert_coordination(request):
                result = await self._coordinate_with_experts(request)
                self.expert_escalations += 1
            else:
                result = await self._fast_track_coordination(request)
            
            # Update performance tracking
            coordination_time = (asyncio.get_event_loop().time() - start_time) * 1000
            result.coordination_time_ms = coordination_time
            self.coordination_count += 1
            
            # Cache successful results for performance
            if result.approved and not result.escalation_required:
                self.coordination_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"MCP coordination error: {e}")
            return MCPCoordinationResult(
                approved=False,
                reason=f"Coordination error: {str(e)}",
                experts_consulted=[],
                coordination_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                security_flags={"coordination_error"},
                recommendations=["Retry operation", "Check expert system health"]
            )
    
    async def _requires_expert_coordination(self, request: MCPCoordinationRequest) -> bool:
        """Determine if operation requires full expert coordination"""
        
        # Always coordinate dangerous operations
        if request.operation_type == MCPOperationType.DANGEROUS_COMMAND:
            return True
        
        # Coordinate high-risk operations
        if request.risk_level in ["high", "critical"]:
            return True
        
        # Check for suspicious patterns
        if await self._detect_suspicious_patterns(request):
            return True
        
        # Fast track simple operations
        if request.operation_type in [MCPOperationType.HEALTH_CHECK, MCPOperationType.SESSION_VALIDATE]:
            return False
        
        # Default to expert coordination for security
        return True
    
    async def _coordinate_with_experts(self, request: MCPCoordinationRequest) -> MCPCoordinationResult:
        """Full expert coordination for complex operations"""
        
        # Prepare expert coordination request
        expert_request = {
            "operation_type": request.operation_type.value,
            "tool_name": request.tool_name,
            "tool_input": request.tool_input,
            "session_context": {
                "agent_id": request.session.agent_id,
                "session_id": request.session.session_id,
                "ip_address": request.session.ip_address,
                "command_count": request.session.command_count
            },
            "risk_assessment": request.risk_level,
            "context": request.context
        }
        
        # Request expert coordination
        coordination_response = await self.expert_coordinator.coordinate_experts(
            request_type="mcp_operation",
            request_data=expert_request,
            required_consensus=0.7,  # 70% expert agreement required
            timeout=30.0
        )
        
        # Extract expert recommendations
        experts_consulted = [expert.expert_id for expert in coordination_response.get("participating_experts", [])]
        consensus = coordination_response.get("consensus", {})
        
        approved = consensus.get("approved", False)
        reason = consensus.get("reasoning", "Expert coordination completed")
        recommendations = consensus.get("recommendations", [])
        security_flags = set(consensus.get("security_flags", []))
        
        return MCPCoordinationResult(
            approved=approved,
            reason=reason,
            experts_consulted=experts_consulted,
            coordination_time_ms=0.0,  # Will be set by caller
            security_flags=security_flags,
            recommendations=recommendations,
            escalation_required=consensus.get("requires_escalation", False)
        )
    
    async def _fast_track_coordination(self, request: MCPCoordinationRequest) -> MCPCoordinationResult:
        """Fast coordination for simple, low-risk operations"""
        
        # Simple validation rules
        approved = True
        reason = "Fast-track approval"
        security_flags = set()
        recommendations = []
        
        # Basic security checks
        if request.operation_type == MCPOperationType.EVENT_STORE:
            # Check for dangerous event types
            event_type = request.tool_input.get("event_type", "")
            if any(dangerous in event_type.lower() for dangerous in ["system", "admin", "root"]):
                approved = False
                reason = "Dangerous event type requires expert review"
                security_flags.add("dangerous_event_type")
        
        elif request.operation_type == MCPOperationType.EVENT_QUERY:
            # Check query parameters
            limit = request.tool_input.get("limit", 10)
            if limit > 1000:
                approved = False
                reason = "Large query limit requires expert review"
                security_flags.add("large_query_limit")
        
        return MCPCoordinationResult(
            approved=approved,
            reason=reason,
            experts_consulted=["fast_track_validator"],
            coordination_time_ms=0.0,  # Will be set by caller
            security_flags=security_flags,
            recommendations=recommendations
        )
    
    async def _detect_suspicious_patterns(self, request: MCPCoordinationRequest) -> bool:
        """Detect suspicious patterns requiring expert attention"""
        
        # Check session anomalies
        if request.session.command_count > 100:
            return True
        
        # Check for rapid operations
        if hasattr(request.session, 'last_activity'):
            time_since_last = asyncio.get_event_loop().time() - request.session.last_activity
            if time_since_last < 0.1:  # Less than 100ms between operations
                return True
        
        # Check for unusual tool combinations
        tool_name = request.tool_name.lower()
        if "admin" in tool_name or "system" in tool_name:
            return True
        
        return False
    
    def _get_cache_key(self, request: MCPCoordinationRequest) -> str:
        """Generate cache key for coordination request"""
        key_data = {
            "operation_type": request.operation_type.value,
            "tool_name": request.tool_name,
            "risk_level": request.risk_level,
            "agent_id": request.session.agent_id
        }
        return json.dumps(key_data, sort_keys=True)
    
    def get_coordination_stats(self) -> Dict[str, Any]:
        """Get coordination performance statistics"""
        cache_hit_rate = (self.cache_hits / max(self.coordination_count, 1)) * 100
        expert_escalation_rate = (self.expert_escalations / max(self.coordination_count, 1)) * 100
        
        return {
            "total_coordinations": self.coordination_count,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "expert_escalations": self.expert_escalations,
            "expert_escalation_rate": f"{expert_escalation_rate:.1f}%",
            "cached_results": len(self.coordination_cache)
        }
    
    def clear_cache(self):
        """Clear coordination cache"""
        self.coordination_cache.clear()
        logger.info("MCP coordination cache cleared")