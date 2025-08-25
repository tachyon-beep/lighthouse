"""
Expert Registry for Lighthouse Bridge

Manages expert agent discovery, capability matching, and registration
for the FUSE-based expert coordination system.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class ExpertCapability(str, Enum):
    """Expert agent capabilities"""
    
    # Code analysis and manipulation
    CODE_ANALYSIS = "code_analysis"
    CODE_GENERATION = "code_generation"
    CODE_REFACTORING = "refactoring"
    
    # Security and validation
    SECURITY_AUDIT = "security_audit"
    VULNERABILITY_ASSESSMENT = "vulnerability_assessment"
    CODE_REVIEW = "code_review"
    
    # Architecture and design
    SYSTEM_ARCHITECTURE = "system_architecture"
    DATABASE_DESIGN = "database_design"
    API_DESIGN = "api_design"
    
    # Testing and quality
    TEST_GENERATION = "test_generation"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    QUALITY_ASSURANCE = "quality_assurance"
    
    # Infrastructure and deployment
    DEVOPS = "devops"
    INFRASTRUCTURE = "infrastructure"
    DEPLOYMENT = "deployment"
    
    # Documentation and communication
    DOCUMENTATION = "documentation"
    TECHNICAL_WRITING = "technical_writing"
    
    # General capabilities
    PROBLEM_SOLVING = "problem_solving"
    COORDINATION = "coordination"
    MONITORING = "monitoring"


@dataclass
class ExpertMetrics:
    """Performance metrics for expert agents"""
    
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0.0
    last_active: Optional[datetime] = None
    
    # Load and availability
    current_load: int = 0
    max_concurrent: int = 10
    
    # Quality metrics
    success_rate: float = 0.0
    user_satisfaction: float = 0.0
    
    def update_success(self, response_time_ms: float):
        """Update metrics on successful request"""
        self.total_requests += 1
        self.successful_requests += 1
        self.last_active = datetime.utcnow()
        
        # Update average response time (exponential moving average)
        alpha = 0.1
        self.avg_response_time_ms = (
            alpha * response_time_ms + (1 - alpha) * self.avg_response_time_ms
        )
        
        self.success_rate = self.successful_requests / self.total_requests
    
    def update_failure(self):
        """Update metrics on failed request"""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_active = datetime.utcnow()
        
        self.success_rate = self.successful_requests / self.total_requests


@dataclass
class ExpertProfile:
    """Profile information for registered expert agent"""
    
    # Identity
    agent_id: str
    agent_name: str
    agent_type: str  # "human", "ai", "hybrid"
    
    # Capabilities
    capabilities: Set[ExpertCapability] = field(default_factory=set)
    specializations: List[str] = field(default_factory=list)
    
    # Status
    status: str = "available"  # "available", "busy", "offline"
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    
    # Configuration
    max_concurrent_requests: int = 5
    preferred_work_types: List[str] = field(default_factory=list)
    availability_hours: Optional[Dict[str, Any]] = None
    
    # Authentication
    session_id: Optional[str] = None
    authentication_level: str = "basic"
    
    # Performance
    metrics: ExpertMetrics = field(default_factory=ExpertMetrics)
    
    def is_available(self) -> bool:
        """Check if expert is available for new work"""
        if self.status != "available":
            return False
        
        if self.metrics.current_load >= self.max_concurrent_requests:
            return False
        
        # Check if heartbeat is recent (within 5 minutes)
        if datetime.utcnow() - self.last_heartbeat > timedelta(minutes=5):
            return False
        
        return True
    
    def can_handle(self, capability: ExpertCapability) -> bool:
        """Check if expert can handle specific capability"""
        return capability in self.capabilities
    
    def update_heartbeat(self):
        """Update last heartbeat timestamp"""
        self.last_heartbeat = datetime.utcnow()


class ExpertRegistry:
    """
    Registry for managing expert agents in the Bridge system
    
    Provides discovery, capability matching, and load balancing
    for expert agents coordinating through the FUSE filesystem.
    """
    
    def __init__(self):
        self.experts: Dict[str, ExpertProfile] = {}
        self.capability_index: Dict[ExpertCapability, Set[str]] = {
            capability: set() for capability in ExpertCapability
        }
        
        # Registry management
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 300  # 5 minutes
        
        # Statistics
        self.total_registrations = 0
        self.total_requests = 0
        self.successful_matches = 0
    
    async def start(self):
        """Start the expert registry"""
        logger.info("Starting Expert Registry...")
        
        # Start heartbeat monitoring
        self._heartbeat_task = asyncio.create_task(self._monitor_heartbeats())
        
        logger.info("Expert Registry started successfully")
    
    async def shutdown(self):
        """Shutdown the expert registry"""
        logger.info("Shutting down Expert Registry...")
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Expert Registry shutdown complete")
    
    async def register_expert(self, 
                            agent_id: str,
                            agent_name: str,
                            capabilities: Set[ExpertCapability],
                            agent_type: str = "ai",
                            session_id: Optional[str] = None,
                            **kwargs) -> bool:
        """
        Register expert agent with the registry
        
        Args:
            agent_id: Unique identifier for the expert
            agent_name: Display name for the expert
            capabilities: Set of capabilities the expert provides
            agent_type: Type of expert ("human", "ai", "hybrid")
            session_id: Authentication session ID
            **kwargs: Additional profile configuration
            
        Returns:
            True if registration successful
        """
        async with self._lock:
            try:
                # Create or update expert profile
                if agent_id in self.experts:
                    logger.info(f"Updating existing expert: {agent_id}")
                    expert = self.experts[agent_id]
                    expert.capabilities = capabilities
                    expert.agent_name = agent_name
                    expert.session_id = session_id
                    expert.update_heartbeat()
                else:
                    logger.info(f"Registering new expert: {agent_id}")
                    expert = ExpertProfile(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        agent_type=agent_type,
                        capabilities=capabilities,
                        session_id=session_id,
                        **kwargs
                    )
                    self.experts[agent_id] = expert
                    self.total_registrations += 1
                
                # Update capability index
                for capability in capabilities:
                    self.capability_index[capability].add(agent_id)
                
                logger.info(f"Expert {agent_id} registered with capabilities: {[c.value for c in capabilities]}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to register expert {agent_id}: {e}")
                return False
    
    async def unregister_expert(self, agent_id: str) -> bool:
        """
        Unregister expert from the registry
        
        Args:
            agent_id: Expert to unregister
            
        Returns:
            True if unregistration successful
        """
        async with self._lock:
            try:
                if agent_id not in self.experts:
                    logger.warning(f"Attempted to unregister unknown expert: {agent_id}")
                    return False
                
                expert = self.experts[agent_id]
                
                # Remove from capability index
                for capability in expert.capabilities:
                    self.capability_index[capability].discard(agent_id)
                
                # Remove from registry
                del self.experts[agent_id]
                
                logger.info(f"Expert {agent_id} unregistered successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to unregister expert {agent_id}: {e}")
                return False
    
    async def find_experts(self, 
                          capability: ExpertCapability,
                          max_results: int = 10,
                          prefer_available: bool = True) -> List[ExpertProfile]:
        """
        Find experts with specific capability
        
        Args:
            capability: Required capability
            max_results: Maximum number of experts to return
            prefer_available: Prioritize available experts
            
        Returns:
            List of matching expert profiles
        """
        async with self._lock:
            candidate_ids = self.capability_index[capability].copy()
            candidates = [
                self.experts[agent_id] for agent_id in candidate_ids 
                if agent_id in self.experts
            ]
            
            # Filter and sort candidates
            if prefer_available:
                # Available experts first, then by success rate and response time
                candidates.sort(key=lambda e: (
                    not e.is_available(),
                    -e.metrics.success_rate,
                    e.metrics.avg_response_time_ms,
                    e.metrics.current_load
                ))
            else:
                # Sort by capability match and performance
                candidates.sort(key=lambda e: (
                    -e.metrics.success_rate,
                    e.metrics.avg_response_time_ms
                ))
            
            return candidates[:max_results]
    
    async def get_best_expert(self, capability: ExpertCapability) -> Optional[ExpertProfile]:
        """
        Get the best available expert for a capability
        
        Args:
            capability: Required capability
            
        Returns:
            Best matching expert profile or None
        """
        experts = await self.find_experts(capability, max_results=1, prefer_available=True)
        return experts[0] if experts else None
    
    async def update_heartbeat(self, agent_id: str) -> bool:
        """
        Update expert heartbeat
        
        Args:
            agent_id: Expert agent ID
            
        Returns:
            True if heartbeat updated
        """
        async with self._lock:
            if agent_id in self.experts:
                self.experts[agent_id].update_heartbeat()
                return True
            return False
    
    async def update_expert_status(self, 
                                 agent_id: str, 
                                 status: str,
                                 current_load: Optional[int] = None) -> bool:
        """
        Update expert status and load
        
        Args:
            agent_id: Expert agent ID
            status: New status ("available", "busy", "offline")
            current_load: Current number of active requests
            
        Returns:
            True if status updated
        """
        async with self._lock:
            if agent_id in self.experts:
                expert = self.experts[agent_id]
                expert.status = status
                expert.update_heartbeat()
                
                if current_load is not None:
                    expert.metrics.current_load = current_load
                
                logger.debug(f"Expert {agent_id} status updated to {status}")
                return True
            return False
    
    async def record_request_success(self, 
                                   agent_id: str,
                                   response_time_ms: float) -> bool:
        """
        Record successful request completion
        
        Args:
            agent_id: Expert agent ID
            response_time_ms: Request response time in milliseconds
            
        Returns:
            True if metrics updated
        """
        async with self._lock:
            if agent_id in self.experts:
                self.experts[agent_id].metrics.update_success(response_time_ms)
                self.total_requests += 1
                self.successful_matches += 1
                return True
            return False
    
    async def record_request_failure(self, agent_id: str) -> bool:
        """
        Record failed request
        
        Args:
            agent_id: Expert agent ID
            
        Returns:
            True if metrics updated
        """
        async with self._lock:
            if agent_id in self.experts:
                self.experts[agent_id].metrics.update_failure()
                self.total_requests += 1
                return True
            return False
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        async with self._lock:
            available_count = sum(1 for e in self.experts.values() if e.is_available())
            capability_counts = {
                cap.value: len(agents) 
                for cap, agents in self.capability_index.items() 
                if agents
            }
            
            return {
                "total_experts": len(self.experts),
                "available_experts": available_count,
                "total_registrations": self.total_registrations,
                "total_requests": self.total_requests,
                "successful_matches": self.successful_matches,
                "match_success_rate": (
                    self.successful_matches / self.total_requests 
                    if self.total_requests > 0 else 0.0
                ),
                "capabilities": capability_counts,
                "experts": {
                    agent_id: {
                        "name": expert.agent_name,
                        "status": expert.status,
                        "capabilities": [c.value for c in expert.capabilities],
                        "success_rate": expert.metrics.success_rate,
                        "current_load": expert.metrics.current_load
                    }
                    for agent_id, expert in self.experts.items()
                }
            }
    
    async def _monitor_heartbeats(self):
        """Monitor expert heartbeats and cleanup stale entries"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                
                current_time = datetime.utcnow()
                stale_experts = []
                
                async with self._lock:
                    for agent_id, expert in self.experts.items():
                        # Mark as offline if no heartbeat for 10 minutes
                        if current_time - expert.last_heartbeat > timedelta(minutes=10):
                            if expert.status != "offline":
                                logger.warning(f"Expert {agent_id} marked as offline (stale heartbeat)")
                                expert.status = "offline"
                        
                        # Remove completely if offline for 1 hour
                        if (current_time - expert.last_heartbeat > timedelta(hours=1) and 
                            expert.status == "offline"):
                            stale_experts.append(agent_id)
                
                # Remove stale experts
                for agent_id in stale_experts:
                    await self.unregister_expert(agent_id)
                    logger.info(f"Removed stale expert: {agent_id}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitoring: {e}")
                await asyncio.sleep(60)  # Wait before retrying