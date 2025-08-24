"""
Speed Layer Dispatcher

Central coordinator for the speed layer validation system. Routes requests through
the three-tier cache system and escalates to expert layer when needed.

Architecture:
1. Memory Cache (sub-millisecond) - Hot patterns
2. Policy Cache (1-5ms) - Rule-based validation  
3. Pattern Cache (5-10ms) - ML pattern matching
4. Expert Escalation (30s timeout) - Complex cases

Performance Target: 99% of requests in <100ms
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta

from .models import (
    ValidationRequest, ValidationResult, ValidationDecision, 
    ValidationConfidence, SpeedLayerMetrics
)
from .memory_cache import MemoryRuleCache
from .policy_cache import PolicyEngineCache  
from .pattern_cache import MLPatternCache

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for external service calls"""
    
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open
    
    def can_execute(self) -> bool:
        """Check if execution is allowed"""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
                return True
            return False
        else:  # half-open
            return True
    
    def record_success(self):
        """Record successful execution"""
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = None
    
    def record_failure(self):
        """Record failed execution"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
    
    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking requests)"""
        return self.state == "open"


class SpeedLayerDispatcher:
    """Central dispatcher for speed layer validation"""
    
    def __init__(self, 
                 max_memory_cache_size: int = 10000,
                 policy_config_path: Optional[str] = None,
                 ml_model_path: Optional[str] = None,
                 expert_timeout: float = 30.0):
        """
        Initialize speed layer dispatcher
        
        Args:
            max_memory_cache_size: Maximum memory cache entries
            policy_config_path: Path to policy rule configuration
            ml_model_path: Path to ML model file
            expert_timeout: Timeout for expert validation (seconds)
        """
        
        # Initialize cache layers
        self.memory_cache = MemoryRuleCache(max_size=max_memory_cache_size)
        self.policy_cache = PolicyEngineCache(rule_config_path=policy_config_path)
        self.pattern_cache = MLPatternCache(
            model_path=ml_model_path, 
            confidence_threshold=0.8
        )
        
        # Expert escalation
        self.expert_timeout = expert_timeout
        self._expert_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._pending_expert_requests: Dict[str, asyncio.Future] = {}
        
        # Circuit breakers for each layer
        self.circuit_breakers = {
            'memory': CircuitBreaker(failure_threshold=10, reset_timeout=30),
            'policy': CircuitBreaker(failure_threshold=5, reset_timeout=60),
            'pattern': CircuitBreaker(failure_threshold=3, reset_timeout=120),
            'expert': CircuitBreaker(failure_threshold=5, reset_timeout=300)
        }
        
        # Performance metrics
        self.metrics = SpeedLayerMetrics()
        self._performance_window: List[Tuple[float, float]] = []  # (timestamp, response_time)
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        # Request rate limiting
        self._request_timestamps: List[float] = []
        self._max_requests_per_second = 1000
    
    async def start(self):
        """Start the speed layer dispatcher and background tasks"""
        logger.info("Starting Speed Layer Dispatcher...")
        
        # Start cache maintenance tasks
        memory_task = asyncio.create_task(
            self.memory_cache.periodic_cleanup(interval_seconds=60)
        )
        policy_task = asyncio.create_task(
            self.policy_cache.periodic_maintenance(interval_seconds=300)
        )
        pattern_task = asyncio.create_task(
            self.pattern_cache.periodic_maintenance(interval_seconds=600)
        )
        
        # Start metrics collection task
        metrics_task = asyncio.create_task(
            self._periodic_metrics_update(interval_seconds=30)
        )
        
        # Track background tasks
        self._background_tasks.update([
            memory_task, policy_task, pattern_task, metrics_task
        ])
        
        logger.info("Speed Layer Dispatcher started successfully")
    
    async def stop(self):
        """Stop the dispatcher and cleanup background tasks"""
        logger.info("Stopping Speed Layer Dispatcher...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        logger.info("Speed Layer Dispatcher stopped")
    
    async def validate_request(self, request: ValidationRequest) -> ValidationResult:
        """
        Main validation entry point
        
        Routes through speed layer tiers and escalates to experts as needed.
        """
        start_time = time.time()
        
        # Rate limiting check
        if not self._check_rate_limit():
            return ValidationResult(
                decision=ValidationDecision.BLOCKED,
                confidence=ValidationConfidence.HIGH,
                reason="Rate limit exceeded",
                request_id=request.request_id,
                processing_time_ms=1.0
            )
        
        self.metrics.total_requests += 1
        
        try:
            # Tier 1: Memory Cache (sub-millisecond)
            result = await self._try_memory_cache(request)
            if result:
                self.metrics.memory_cache_hits += 1
                return self._finalize_result(result, start_time)
            
            # Tier 2: Policy Cache (1-5ms)  
            result = await self._try_policy_cache(request)
            if result:
                self.metrics.policy_cache_hits += 1
                return self._finalize_result(result, start_time)
            
            # Tier 3: Pattern Cache (5-10ms)
            result = await self._try_pattern_cache(request)
            if result:
                self.metrics.pattern_cache_hits += 1
                return self._finalize_result(result, start_time)
            
            # Tier 4: Expert Escalation (up to 30s)
            result = await self._escalate_to_expert(request)
            self.metrics.expert_escalations += 1
            return self._finalize_result(result, start_time)
            
        except Exception as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            
            # Return safe default based on request type
            decision = self._get_safe_default_decision(request)
            
            return ValidationResult(
                decision=decision,
                confidence=ValidationConfidence.LOW,
                reason=f"Error in validation pipeline: {str(e)}",
                request_id=request.request_id,
                processing_time_ms=(time.time() - start_time) * 1000
            )
    
    async def _try_memory_cache(self, request: ValidationRequest) -> Optional[ValidationResult]:
        """Try memory cache layer"""
        if not self.circuit_breakers['memory'].can_execute():
            return None
        
        try:
            result = self.memory_cache.get(request.command_hash)
            if result:
                self.circuit_breakers['memory'].record_success()
                result.cache_hit = True
                result.cache_layer = "memory"
                return result
            
        except Exception as e:
            logger.warning(f"Memory cache error: {e}")
            self.circuit_breakers['memory'].record_failure()
            self.metrics.cache_errors += 1
        
        return None
    
    async def _try_policy_cache(self, request: ValidationRequest) -> Optional[ValidationResult]:
        """Try policy cache layer"""
        if not self.circuit_breakers['policy'].can_execute():
            return None
        
        try:
            result = await self.policy_cache.evaluate(request)
            if result:
                self.circuit_breakers['policy'].record_success()
                
                # Cache result in memory for future requests
                self.memory_cache.set(request.command_hash, result)
                
                return result
            
        except Exception as e:
            logger.warning(f"Policy cache error: {e}")
            self.circuit_breakers['policy'].record_failure()
            self.metrics.policy_errors += 1
        
        return None
    
    async def _try_pattern_cache(self, request: ValidationRequest) -> Optional[ValidationResult]:
        """Try ML pattern cache layer"""
        if not self.circuit_breakers['pattern'].can_execute():
            return None
        
        try:
            result = await self.pattern_cache.predict(request)
            if result:
                self.circuit_breakers['pattern'].record_success()
                
                # Cache high-confidence results in memory
                if result.confidence == ValidationConfidence.HIGH:
                    self.memory_cache.set(request.command_hash, result)
                
                return result
            
        except Exception as e:
            logger.warning(f"Pattern cache error: {e}")
            self.circuit_breakers['pattern'].record_failure()
            self.metrics.pattern_errors += 1
        
        return None
    
    async def _escalate_to_expert(self, request: ValidationRequest) -> ValidationResult:
        """Escalate to expert validation"""
        if not self.circuit_breakers['expert'].can_execute():
            # Expert circuit breaker is open - use safe default
            decision = self._get_safe_default_decision(request)
            return ValidationResult(
                decision=decision,
                confidence=ValidationConfidence.LOW,
                reason="Expert system unavailable - using safe default",
                request_id=request.request_id,
                processing_time_ms=1.0,
                expert_required=True
            )
        
        try:
            # Create future for expert response
            future = asyncio.Future()
            self._pending_expert_requests[request.request_id] = future
            
            # Queue request for expert review
            expert_context = {
                'request': request,
                'escalation_reason': 'No cache layer provided confident result',
                'speed_layer_path': ['memory_miss', 'policy_miss', 'pattern_uncertain']
            }
            
            await self._expert_queue.put({
                'request_id': request.request_id,
                'context': expert_context,
                'future': future
            })
            
            # Wait for expert response with timeout
            try:
                result = await asyncio.wait_for(future, timeout=self.expert_timeout)
                self.circuit_breakers['expert'].record_success()
                
                # Learn from expert decision
                await self._learn_from_expert_decision(request, result)
                
                return result
                
            except asyncio.TimeoutError:
                logger.warning(f"Expert timeout for request {request.request_id}")
                
                # Clean up
                future.cancel()
                self._pending_expert_requests.pop(request.request_id, None)
                
                # Return safe default
                decision = self._get_safe_default_decision(request)
                return ValidationResult(
                    decision=decision,
                    confidence=ValidationConfidence.LOW,
                    reason="Expert validation timeout - using safe default",
                    request_id=request.request_id,
                    processing_time_ms=self.expert_timeout * 1000,
                    expert_required=True
                )
            
        except Exception as e:
            logger.error(f"Expert escalation error: {e}")
            self.circuit_breakers['expert'].record_failure()
            
            decision = self._get_safe_default_decision(request)
            return ValidationResult(
                decision=decision,
                confidence=ValidationConfidence.LOW,
                reason=f"Expert escalation failed: {str(e)}",
                request_id=request.request_id,
                processing_time_ms=1.0,
                expert_required=True
            )
    
    def _get_safe_default_decision(self, request: ValidationRequest) -> ValidationDecision:
        """Get safe default decision when validation fails"""
        # Safe tools are always approved
        if request.tool_name.lower() in ['read', 'glob', 'grep', 'ls', 'webfetch', 'websearch']:
            return ValidationDecision.APPROVED
        
        # File operations and bash commands are blocked by default for safety
        if request.tool_name.lower() in ['bash', 'write', 'edit', 'multiedit']:
            return ValidationDecision.BLOCKED
        
        # Default to blocked for unknown tools
        return ValidationDecision.BLOCKED
    
    async def _learn_from_expert_decision(self, request: ValidationRequest, result: ValidationResult):
        """Learn from expert decisions to improve cache layers"""
        try:
            # Add to memory cache for future identical requests
            self.memory_cache.set(request.command_hash, result, ttl_seconds=3600)
            
            # Provide feedback to ML pattern cache
            self.pattern_cache.add_feedback(request, result.decision)
            
            # Could also create new policy rules based on expert decisions
            # This would be implemented based on specific requirements
            
        except Exception as e:
            logger.error(f"Learning from expert decision failed: {e}")
    
    async def provide_expert_response(self, request_id: str, result: ValidationResult):
        """Provide expert response for pending request"""
        if request_id in self._pending_expert_requests:
            future = self._pending_expert_requests.pop(request_id)
            if not future.done():
                future.set_result(result)
                logger.debug(f"Expert response provided for request {request_id}")
    
    def _finalize_result(self, result: ValidationResult, start_time: float) -> ValidationResult:
        """Finalize validation result with timing and metrics"""
        processing_time = (time.time() - start_time) * 1000
        result.processing_time_ms = processing_time
        
        # Update performance metrics
        self._performance_window.append((time.time(), processing_time))
        
        # Keep only recent measurements
        cutoff_time = time.time() - 300  # 5 minutes
        self._performance_window = [
            (ts, rt) for ts, rt in self._performance_window if ts > cutoff_time
        ]
        
        return result
    
    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limits"""
        current_time = time.time()
        
        # Add current request timestamp
        self._request_timestamps.append(current_time)
        
        # Remove timestamps older than 1 second
        cutoff_time = current_time - 1.0
        self._request_timestamps = [
            ts for ts in self._request_timestamps if ts > cutoff_time
        ]
        
        # Check if we're over the limit
        return len(self._request_timestamps) <= self._max_requests_per_second
    
    async def _periodic_metrics_update(self, interval_seconds: int = 30):
        """Update performance metrics periodically"""
        while not self._shutdown_event.is_set():
            try:
                if self._performance_window:
                    response_times = [rt for _, rt in self._performance_window]
                    
                    self.metrics.avg_response_time_ms = sum(response_times) / len(response_times)
                    self.metrics.p99_response_time_ms = sorted(response_times)[int(len(response_times) * 0.99)]
                    self.metrics.max_response_time_ms = max(response_times)
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics update error: {e}")
                await asyncio.sleep(interval_seconds)
    
    def get_performance_metrics(self) -> Dict[str, any]:
        """Get current performance metrics"""
        cache_stats = {
            'memory_cache': self.memory_cache.get_stats(),
            'policy_cache': self.policy_cache.get_rule_stats(),
            'pattern_cache': self.pattern_cache.get_model_stats()
        }
        
        circuit_breaker_stats = {
            name: {
                'state': cb.state,
                'failure_count': cb.failure_count,
                'is_open': cb.is_open
            }
            for name, cb in self.circuit_breakers.items()
        }
        
        return {
            'speed_layer_metrics': self.metrics.to_dict(),
            'cache_stats': cache_stats,
            'circuit_breakers': circuit_breaker_stats,
            'pending_expert_requests': len(self._pending_expert_requests),
            'expert_queue_size': self._expert_queue.qsize(),
            'performance_window_size': len(self._performance_window)
        }
    
    def debug_request(self, request: ValidationRequest) -> Dict[str, any]:
        """Get detailed debug information for a request"""
        debug_info = {
            'request': {
                'request_id': request.request_id,
                'command_hash': request.command_hash,
                'tool_name': request.tool_name,
                'agent_id': request.agent_id,
                'command_text': request.command_text[:100]  # Truncate for safety
            },
            'cache_layers': {},
            'circuit_breakers': {},
            'would_escalate': False
        }
        
        # Check each cache layer
        memory_result = self.memory_cache.get(request.command_hash)
        debug_info['cache_layers']['memory'] = {
            'hit': memory_result is not None,
            'result': memory_result.decision.value if memory_result else None
        }
        
        # Policy cache debug
        debug_info['cache_layers']['policy'] = self.policy_cache.debug_request(request)
        
        # Pattern cache debug
        debug_info['cache_layers']['pattern'] = self.pattern_cache.debug_prediction(request)
        
        # Circuit breaker states
        debug_info['circuit_breakers'] = {
            name: {
                'state': cb.state,
                'can_execute': cb.can_execute(),
                'failure_count': cb.failure_count
            }
            for name, cb in self.circuit_breakers.items()
        }
        
        # Would this request escalate to expert?
        debug_info['would_escalate'] = (
            not memory_result and 
            not debug_info['cache_layers']['policy']['would_apply'] and
            not debug_info['cache_layers']['pattern']['meets_threshold']
        )
        
        return debug_info