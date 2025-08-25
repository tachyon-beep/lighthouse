# Remediation Plan Charlie - Open Source AI Agent Implementation

**Document Version**: 2.0 - REVISED FOR AI AGENT IMPLEMENTATION  
**Created**: 2025-08-24  
**Status**: APPROVED - READY FOR IMPLEMENTATION  
**Classification**: OPEN SOURCE TECHNICAL EXCELLENCE PLAN  

---

## Executive Summary

This comprehensive remediation plan addresses all critical security vulnerabilities, implementation gaps, and system deficiencies identified by our multi-agent review team. Plan Charlie transforms the Lighthouse system from its current **EMERGENCY STOP** status to a production-ready, open source multi-agent coordination platform through systematic technical excellence.

**Current System Status**: CRITICAL - Multiple blocking issues prevent any deployment  
**Target System Status**: PRODUCTION READY - Open source multi-agent coordination platform  
**Implementation Approach**: AI agent-driven development with focus on technical correctness  
**Quality Standard**: Production-grade open source software  

---

## 🚨 Phase 1: Critical Security Remediation

**PRIORITY**: CRITICAL - SYSTEM SECURITY EMERGENCY  
**OBJECTIVE**: Eliminate all critical security vulnerabilities  

### 1.1 Hard-Coded Secret Elimination (**CRITICAL**)
**Issue**: Production system contains default secrets  
**Solution**: Environment-based configuration with secure defaults

```python
# Current vulnerable implementation:
auth_secret = "lighthouse-default-secret"

# Fixed implementation:
import secrets
import os

def get_secure_secret(env_var: str, description: str) -> str:
    """Get secret from environment or generate secure default"""
    secret = os.environ.get(env_var)
    if not secret:
        # Generate cryptographically secure default
        secret = secrets.token_urlsafe(32)
        logger.warning(f"Using generated secret for {description}. Set {env_var} environment variable for production.")
    return secret

auth_secret = get_secure_secret('LIGHTHOUSE_AUTH_SECRET', 'authentication')
system_secret = get_secure_secret('LIGHTHOUSE_SYSTEM_SECRET', 'system operations')
```

**Files to Update**:
- `src/lighthouse/event_store/store.py:56`
- `src/lighthouse/event_store/auth.py:47`
- `src/lighthouse/bridge/fuse_mount/authentication.py:89`
- `src/lighthouse/validator.py` (any default secrets)

### 1.2 Authentication Token Security Enhancement (**CRITICAL**)
**Issue**: Predictable timestamp-based tokens enable attacks  
**Solution**: Cryptographically secure random nonces with proper HMAC

```python
class SecureTokenGenerator:
    """Cryptographically secure token generation"""
    
    def __init__(self, secret: str):
        self.secret = secret.encode('utf-8')
    
    def generate_token(self, agent_id: str, additional_data: str = "") -> str:
        """Generate secure authentication token"""
        # Use cryptographically secure random nonce
        nonce = secrets.token_bytes(16)  # 128-bit nonce
        timestamp = int(time.time())
        
        # Create token payload
        payload = f"{agent_id}:{nonce.hex()}:{timestamp}:{additional_data}"
        
        # Generate HMAC
        token = hmac.new(
            self.secret,
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"{token}:{nonce.hex()}:{timestamp}"
    
    def verify_token(self, token: str, agent_id: str, max_age_seconds: int = 3600) -> bool:
        """Verify token authenticity and freshness"""
        try:
            token_hash, nonce_hex, timestamp_str = token.split(':')
            timestamp = int(timestamp_str)
            
            # Check token age
            if time.time() - timestamp > max_age_seconds:
                return False
            
            # Reconstruct payload and verify HMAC
            payload = f"{agent_id}:{nonce_hex}:{timestamp}:"
            expected_token = hmac.new(
                self.secret,
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(token_hash, expected_token)
            
        except (ValueError, TypeError):
            return False
```

### 1.3 Path Traversal Prevention (**CRITICAL**)
**Issue**: Regex-based validation can be bypassed  
**Solution**: OS-level path resolution and validation

```python
import os
from pathlib import Path

class SecurePathValidator:
    """Secure path validation using OS-level resolution"""
    
    def __init__(self, allowed_base_paths: List[str]):
        # Resolve and normalize allowed base paths
        self.allowed_base_paths = [
            os.path.realpath(path) for path in allowed_base_paths
        ]
    
    def validate_path(self, requested_path: str) -> str:
        """Validate and resolve path securely"""
        try:
            # Resolve the full path (resolves .., symlinks, etc.)
            resolved_path = os.path.realpath(requested_path)
            
            # Check if path is within allowed bases
            for allowed_base in self.allowed_base_paths:
                if resolved_path.startswith(allowed_base + os.sep) or resolved_path == allowed_base:
                    return resolved_path
            
            raise SecurityError(f"Path traversal attempt blocked: {requested_path} -> {resolved_path}")
            
        except (OSError, ValueError) as e:
            raise SecurityError(f"Invalid path: {requested_path} - {e}")

# Usage in FUSE mount
path_validator = SecurePathValidator([
    "/mnt/lighthouse/project/current",
    "/mnt/lighthouse/project/history", 
    "/mnt/lighthouse/project/context",
    "/mnt/lighthouse/project/streams"
])
```

### 1.4 Race Condition Elimination (**CRITICAL**)
**Issue**: Async file operations not properly synchronized  
**Solution**: Proper async locking with atomic operations

```python
import asyncio
from contextlib import asynccontextmanager

class AtomicFileOperations:
    """Thread-safe file operations for FUSE mount"""
    
    def __init__(self):
        self._file_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
    
    @asynccontextmanager
    async def file_lock(self, file_path: str):
        """Acquire exclusive lock for file operations"""
        # Get or create lock for specific file
        async with self._global_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = asyncio.Lock()
            file_lock = self._file_locks[file_path]
        
        # Acquire file-specific lock
        async with file_lock:
            yield
    
    async def atomic_write(self, file_path: str, content: str, agent_id: str) -> bool:
        """Atomically write file content"""
        async with self.file_lock(file_path):
            try:
                # Write to temporary file first
                temp_path = f"{file_path}.tmp.{secrets.token_hex(8)}"
                
                async with aiofiles.open(temp_path, 'w') as f:
                    await f.write(content)
                    await f.flush()
                    await f.fsync()  # Force to disk
                
                # Atomic rename
                os.rename(temp_path, file_path)
                
                # Log the operation
                logger.info(f"Atomic write completed: {file_path} by {agent_id}")
                return True
                
            except Exception as e:
                # Cleanup temp file on error
                try:
                    os.unlink(temp_path)
                except:
                    pass
                logger.error(f"Atomic write failed: {file_path} by {agent_id} - {e}")
                return False
```

### 1.5 Comprehensive Rate Limiting
**Issue**: System vulnerable to DoS attacks  
**Solution**: Multi-tier rate limiting with backoff

```python
class ComprehensiveRateLimiter:
    """Multi-tier rate limiting with adaptive backoff"""
    
    def __init__(self):
        # Per-agent rate limits
        self.agent_limits = {
            'requests_per_minute': 100,
            'requests_per_hour': 1000,
            'concurrent_requests': 10
        }
        
        # Global rate limits
        self.global_limits = {
            'requests_per_minute': 1000,
            'concurrent_requests': 100
        }
        
        # Tracking
        self.agent_history = defaultdict(lambda: {
            'requests': deque(),
            'active_requests': 0,
            'backoff_until': 0
        })
        
        self.global_history = {
            'requests': deque(),
            'active_requests': 0
        }
    
    async def check_rate_limit(self, agent_id: str) -> bool:
        """Check if request is allowed under rate limits"""
        now = time.time()
        
        # Check agent-specific backoff
        agent_data = self.agent_history[agent_id]
        if now < agent_data['backoff_until']:
            raise RateLimitExceeded(f"Agent {agent_id} in backoff period")
        
        # Clean old requests
        self._cleanup_old_requests(agent_data['requests'], now - 3600)  # 1 hour
        self._cleanup_old_requests(self.global_history['requests'], now - 60)  # 1 minute
        
        # Check concurrent requests
        if agent_data['active_requests'] >= self.agent_limits['concurrent_requests']:
            self._apply_backoff(agent_id)
            raise RateLimitExceeded(f"Too many concurrent requests for {agent_id}")
        
        if self.global_history['active_requests'] >= self.global_limits['concurrent_requests']:
            raise RateLimitExceeded("Global concurrent request limit exceeded")
        
        # Check rate limits
        recent_requests = sum(1 for t in agent_data['requests'] if t > now - 60)
        if recent_requests >= self.agent_limits['requests_per_minute']:
            self._apply_backoff(agent_id)
            raise RateLimitExceeded(f"Rate limit exceeded for {agent_id}")
        
        # Record request
        agent_data['requests'].append(now)
        agent_data['active_requests'] += 1
        self.global_history['requests'].append(now)
        self.global_history['active_requests'] += 1
        
        return True
    
    def release_request(self, agent_id: str):
        """Release active request slot"""
        self.agent_history[agent_id]['active_requests'] -= 1
        self.global_history['active_requests'] -= 1
```

**Phase 1 Acceptance Criteria**:
- [ ] All hard-coded secrets replaced with secure generation/environment variables
- [ ] Authentication tokens use cryptographically secure randomness with proper verification
- [ ] Path traversal vulnerabilities eliminated using OS-level validation
- [ ] Race conditions in file operations eliminated with proper async locking
- [ ] Comprehensive rate limiting active with adaptive backoff
- [ ] Security event monitoring operational
- [ ] All changes tested with security regression tests

---

## 🔧 Phase 2: Core Component Implementation

**PRIORITY**: CRITICAL - SYSTEM FUNCTIONALITY  
**OBJECTIVE**: Implement all missing core components with production quality  

### 2.1 Expert LLM Integration

**Location**: `src/lighthouse/bridge/expert_coordination/llm_client.py`

```python
class ExpertLLMClient:
    """Production-grade LLM client for expert validation"""
    
    def __init__(self, 
                 provider: str = "openai",
                 model: str = "gpt-4",
                 api_key: Optional[str] = None,
                 enable_caching: bool = True):
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._get_api_key()
        
        # Request caching for performance
        if enable_caching:
            self.request_cache = TTLCache(maxsize=10000, ttl=300)  # 5-minute cache
        else:
            self.request_cache = None
            
        # Request validation and sanitization
        self.input_validator = InputValidator()
        self.response_validator = LLMResponseValidator()
        
        # Performance tracking
        self.request_stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'avg_response_time': 0.0,
            'error_count': 0
        }
    
    async def validate_command(self, 
                             command: str, 
                             context: Dict[str, Any],
                             risk_assessment: Dict[str, Any]) -> ExpertDecision:
        """Request expert validation with comprehensive safety checks"""
        
        # Validate inputs
        self._validate_inputs(command, context, risk_assessment)
        
        # Check cache first
        cache_key = self._generate_cache_key(command, context, risk_assessment)
        if self.request_cache and cache_key in self.request_cache:
            self.request_stats['cache_hits'] += 1
            return self.request_cache[cache_key]
        
        start_time = time.perf_counter()
        try:
            # Build expert prompt with safety constraints
            prompt = self._build_expert_prompt(command, context, risk_assessment)
            
            # Make LLM request with timeout and retries
            response = await self._make_llm_request_with_retry(prompt)
            
            # Validate LLM response for safety
            decision = self._parse_and_validate_response(response)
            
            # Cache result if valid
            if self.request_cache:
                self.request_cache[cache_key] = decision
            
            # Update statistics
            response_time = time.perf_counter() - start_time
            self._update_stats(response_time, success=True)
            
            return decision
            
        except Exception as e:
            self._update_stats(time.perf_counter() - start_time, success=False)
            logger.error(f"LLM validation failed: {e}")
            
            # Return safe default on LLM failure
            return ExpertDecision(
                decision=ValidationDecision.BLOCKED,
                confidence=0.0,
                reasoning=f"LLM validation failed: {str(e)}",
                concerns=["llm_unavailable"],
                response_time_ms=(time.perf_counter() - start_time) * 1000
            )
    
    def _build_expert_prompt(self, command: str, context: Dict, risk: Dict) -> str:
        """Build expert prompt with security constraints"""
        return f"""You are a cybersecurity expert reviewing commands for execution safety.

CRITICAL SAFETY RULES:
- NEVER recommend executing dangerous commands
- NEVER provide instructions for harmful activities  
- Always err on the side of caution
- If uncertain, recommend blocking or requesting human review

COMMAND TO REVIEW: {command}

EXECUTION CONTEXT:
{json.dumps(context, indent=2)}

RISK ASSESSMENT:
{json.dumps(risk, indent=2)}

Respond with valid JSON in this exact format:
{{
  "decision": "APPROVE|BLOCK|MODIFY|ESCALATE",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<detailed explanation>",
  "concerns": ["<list of specific concerns>"],
  "suggestions": ["<alternative approaches if blocking>"]
}}

Remember: When in doubt, BLOCK the command. System security is paramount."""

class LLMResponseValidator:
    """Validates LLM responses for safety and correctness"""
    
    def validate_response(self, response_data: Dict[str, Any]) -> bool:
        """Validate LLM response is safe and well-formed"""
        
        # Check required fields
        required_fields = ['decision', 'confidence', 'reasoning', 'concerns']
        for field in required_fields:
            if field not in response_data:
                raise ValidationError(f"Missing required field: {field}")
        
        # Validate decision value
        valid_decisions = ['APPROVE', 'BLOCK', 'MODIFY', 'ESCALATE']
        if response_data['decision'] not in valid_decisions:
            raise ValidationError(f"Invalid decision: {response_data['decision']}")
        
        # Validate confidence range
        confidence = response_data['confidence']
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            raise ValidationError(f"Invalid confidence value: {confidence}")
        
        # Check for dangerous recommendations
        reasoning = response_data['reasoning'].lower()
        dangerous_phrases = [
            'delete everything',
            'rm -rf /',
            'format drive',
            'remove all files',
            'shutdown system',
            'disable security'
        ]
        
        for phrase in dangerous_phrases:
            if phrase in reasoning and response_data['decision'] == 'APPROVE':
                raise SecurityError(f"LLM recommended dangerous action: {phrase}")
        
        # Validate suggestions don't contain harmful commands
        suggestions = response_data.get('suggestions', [])
        for suggestion in suggestions:
            if self._contains_dangerous_command(suggestion):
                raise SecurityError(f"LLM suggested dangerous command: {suggestion}")
        
        return True
    
    def _contains_dangerous_command(self, text: str) -> bool:
        """Check if text contains dangerous command patterns"""
        dangerous_patterns = [
            r'rm\s+-rf\s+/',
            r'sudo\s+rm',
            r'chmod\s+777',
            r'dd\s+if=.*of=/dev/',
            r'mkfs\.',
            r'fdisk.*delete'
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
```

### 2.2 Policy Engine Integration

**Location**: `src/lighthouse/bridge/speed_layer/policy_engine.py`

```python
class ProductionPolicyEngine:
    """Production-grade policy engine with OPA integration"""
    
    def __init__(self, opa_url: str = "http://localhost:8181"):
        self.opa_url = opa_url
        self.policy_cache = TTLCache(maxsize=100000, ttl=300)  # 5-minute cache
        self.rule_compiler = PolicyRuleCompiler()
        self.health_monitor = PolicyEngineHealthMonitor()
        
        # Fallback rules for when OPA is unavailable
        self.fallback_rules = self._load_fallback_rules()
        
    async def evaluate_policy(self, request: ValidationRequest) -> PolicyDecision:
        """Evaluate request against comprehensive policy rules"""
        
        cache_key = self._generate_policy_cache_key(request)
        if cache_key in self.policy_cache:
            return self.policy_cache[cache_key]
        
        try:
            # Try OPA evaluation first
            decision = await self._evaluate_with_opa(request)
            self.health_monitor.record_success()
            
        except Exception as e:
            logger.warning(f"OPA evaluation failed, using fallback rules: {e}")
            decision = await self._evaluate_with_fallback(request)
            self.health_monitor.record_failure()
        
        # Cache successful evaluation
        self.policy_cache[cache_key] = decision
        return decision
    
    async def _evaluate_with_opa(self, request: ValidationRequest) -> PolicyDecision:
        """Evaluate using Open Policy Agent"""
        
        # Build comprehensive OPA input
        opa_input = {
            "tool_name": request.tool_name,
            "command": request.command_text,
            "agent_id": request.agent_id,
            "context": request.context,
            "timestamp": request.timestamp,
            "session_id": request.session_id,
            
            # Enhanced context
            "environment": self._determine_environment(),
            "time_of_day": datetime.now().hour,
            "day_of_week": datetime.now().weekday(),
            "request_source": self._analyze_request_source(request)
        }
        
        # Query OPA with timeout
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
            async with session.post(
                f"{self.opa_url}/v1/data/lighthouse/validation",
                json={"input": opa_input},
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    raise PolicyEngineError(f"OPA returned status {response.status}")
                
                result = await response.json()
                
                if "result" not in result:
                    raise PolicyEngineError("OPA response missing result field")
        
        return self._parse_opa_result(result["result"], request)
    
    async def _evaluate_with_fallback(self, request: ValidationRequest) -> PolicyDecision:
        """Evaluate using fallback rules when OPA unavailable"""
        
        # Safe fallback: block dangerous patterns, allow safe operations
        command = request.command_text.lower()
        
        # Immediate block patterns
        dangerous_patterns = [
            r'rm\s+-rf\s+/',
            r'sudo\s+rm\s+',
            r'chmod\s+777',
            r'dd\s+if=.*of=/dev/',
            r'mkfs\.',
            r'fdisk',
            r'wget.*\|.*bash',
            r'curl.*\|.*sh',
            r'>(.*)/dev/',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, command):
                return PolicyDecision(
                    decision=ValidationDecision.BLOCKED,
                    confidence=ValidationConfidence.HIGH,
                    reason=f"Blocked by fallback rule: dangerous pattern '{pattern}'",
                    matched_rules=["fallback_dangerous_pattern"],
                    rule_source="fallback_rules"
                )
        
        # Safe operations (read-only tools)
        safe_tools = ["Read", "Glob", "Grep", "LS", "cat", "ls", "find", "grep"]
        if request.tool_name in safe_tools:
            return PolicyDecision(
                decision=ValidationDecision.APPROVED,
                confidence=ValidationConfidence.HIGH,
                reason=f"Safe read-only operation: {request.tool_name}",
                matched_rules=["fallback_safe_operations"],
                rule_source="fallback_rules"
            )
        
        # Default: escalate for human review
        return PolicyDecision(
            decision=ValidationDecision.ESCALATE,
            confidence=ValidationConfidence.MEDIUM,
            reason="Escalated due to OPA unavailability and unknown command pattern",
            matched_rules=["fallback_default_escalate"],
            rule_source="fallback_rules"
        )
    
    def _load_fallback_rules(self) -> List[PolicyRule]:
        """Load comprehensive fallback rules"""
        
        return [
            PolicyRule(
                rule_id="dangerous_rm_rf",
                pattern=r'rm\s+-rf\s+/',
                decision=ValidationDecision.BLOCKED,
                confidence=ValidationConfidence.HIGH,
                reason="Recursive deletion of root filesystem",
                priority=1000
            ),
            PolicyRule(
                rule_id="safe_read_operations", 
                pattern=r'^(cat|ls|find|grep|head|tail)\s+',
                decision=ValidationDecision.APPROVED,
                confidence=ValidationConfidence.HIGH,
                reason="Safe read-only operation",
                priority=100
            ),
            # Add more comprehensive fallback rules...
        ]
```

### 2.3 Expert Coordination System

**Location**: `src/lighthouse/bridge/expert_coordination/coordinator.py`

Replace the 29-line stub with a complete implementation:

```python
class ProductionExpertCoordinator:
    """Production-grade expert coordination with consensus algorithms"""
    
    def __init__(self, expert_registry: ExpertRegistry):
        self.expert_registry = expert_registry
        self.active_consultations: Dict[str, Consultation] = {}
        self.consensus_engine = ByzantineFaultTolerantConsensus()
        self.communication_manager = EncryptedExpertCommunication()
        self.performance_monitor = CoordinationPerformanceMonitor()
        
        # Configuration
        self.default_consensus_threshold = 0.67  # 2/3 majority
        self.expert_timeout_seconds = 30
        self.max_concurrent_consultations = 100
        
    async def coordinate_expert_validation(self, 
                                         request: ValidationRequest,
                                         required_consensus: float = None,
                                         max_experts: int = 3) -> ExpertConsensus:
        """Coordinate multi-expert validation with Byzantine fault tolerance"""
        
        consultation_id = f"consult_{secrets.token_hex(16)}"
        consensus_threshold = required_consensus or self.default_consensus_threshold
        
        # Rate limiting for consultations
        if len(self.active_consultations) >= self.max_concurrent_consultations:
            raise CoordinationError("Maximum concurrent consultations exceeded")
        
        start_time = time.perf_counter()
        
        try:
            # Find and validate expert availability
            available_experts = await self._find_qualified_experts(request, max_experts)
            
            if len(available_experts) < 2:
                return await self._handle_insufficient_experts(request)
            
            # Create consultation with comprehensive tracking
            consultation = Consultation(
                consultation_id=consultation_id,
                request=request,
                experts=available_experts,
                required_consensus=consensus_threshold,
                timeout_seconds=self.expert_timeout_seconds,
                created_at=datetime.utcnow(),
                status=ConsultationStatus.ACTIVE
            )
            
            self.active_consultations[consultation_id] = consultation
            
            # Coordinate expert responses with fault tolerance
            expert_responses = await self._coordinate_expert_responses(consultation)
            
            # Apply Byzantine fault tolerant consensus
            consensus = await self.consensus_engine.calculate_consensus(
                responses=expert_responses,
                threshold=consensus_threshold,
                byzantine_tolerance=True
            )
            
            # Update consultation status
            consultation.status = ConsultationStatus.COMPLETED
            consultation.completed_at = datetime.utcnow()
            consultation.consensus_result = consensus
            
            # Record performance metrics
            coordination_time = time.perf_counter() - start_time
            self.performance_monitor.record_consultation(
                consultation_id=consultation_id,
                duration_seconds=coordination_time,
                expert_count=len(available_experts),
                consensus_achieved=consensus.achieved
            )
            
            return ExpertConsensus(
                consultation_id=consultation_id,
                decision=consensus.decision,
                confidence=consensus.confidence,
                expert_responses=expert_responses,
                consensus_achieved=consensus.achieved,
                reasoning=consensus.reasoning,
                coordination_time_ms=coordination_time * 1000,
                expert_agreement_score=consensus.agreement_score
            )
            
        except Exception as e:
            logger.error(f"Expert coordination failed: {consultation_id} - {e}")
            raise CoordinationError(f"Expert coordination failed: {str(e)}")
            
        finally:
            # Cleanup
            if consultation_id in self.active_consultations:
                del self.active_consultations[consultation_id]
    
    async def _coordinate_expert_responses(self, consultation: Consultation) -> List[ExpertResponse]:
        """Coordinate responses from multiple experts with timeout handling"""
        
        expert_tasks = []
        
        for expert in consultation.experts:
            task = asyncio.create_task(
                self._request_expert_validation(expert, consultation)
            )
            expert_tasks.append((expert.agent_id, task))
        
        responses = []
        
        try:
            # Wait for all responses with timeout
            done, pending = await asyncio.wait_for(
                [task for _, task in expert_tasks],
                timeout=consultation.timeout_seconds
            )
            
            # Cancel any pending tasks
            for task in pending:
                task.cancel()
            
            # Collect successful responses
            for task in done:
                try:
                    response = await task
                    if response:
                        responses.append(response)
                except Exception as e:
                    logger.warning(f"Expert response failed: {e}")
            
        except asyncio.TimeoutError:
            # Cancel all remaining tasks
            for _, task in expert_tasks:
                task.cancel()
            
            logger.warning(f"Expert coordination timeout: {consultation.consultation_id}")
        
        return responses
    
    async def _find_qualified_experts(self, request: ValidationRequest, max_experts: int) -> List[ExpertProfile]:
        """Find qualified experts for validation request"""
        
        # Determine required capabilities based on request analysis
        required_capabilities = self._analyze_required_capabilities(request)
        
        # Find experts with matching capabilities
        all_candidates = []
        for capability in required_capabilities:
            candidates = await self.expert_registry.find_experts(
                capability=capability,
                max_results=max_experts * 2,  # Get more candidates for better selection
                prefer_available=True
            )
            all_candidates.extend(candidates)
        
        # Remove duplicates and score experts
        unique_experts = {expert.agent_id: expert for expert in all_candidates}
        scored_experts = []
        
        for expert in unique_experts.values():
            if expert.is_available():
                score = self._calculate_expert_score(expert, required_capabilities)
                scored_experts.append((score, expert))
        
        # Sort by score (descending) and return top experts
        scored_experts.sort(key=lambda x: x[0], reverse=True)
        return [expert for _, expert in scored_experts[:max_experts]]
    
    def _analyze_required_capabilities(self, request: ValidationRequest) -> List[ExpertCapability]:
        """Analyze request to determine required expert capabilities"""
        
        capabilities = []
        command = request.command_text.lower()
        
        # Security-related patterns
        if any(pattern in command for pattern in ['sudo', 'rm', 'chmod', 'passwd']):
            capabilities.append(ExpertCapability.SECURITY_AUDIT)
        
        # File operations
        if any(pattern in command for pattern in ['cp', 'mv', 'rm', 'mkdir']):
            capabilities.append(ExpertCapability.SYSTEM_ADMINISTRATION)
        
        # Network operations
        if any(pattern in command for pattern in ['wget', 'curl', 'ssh', 'scp']):
            capabilities.append(ExpertCapability.NETWORK_SECURITY)
        
        # Code-related operations
        if request.tool_name in ['Edit', 'Write', 'MultiEdit']:
            capabilities.append(ExpertCapability.CODE_REVIEW)
        
        # Default to general problem solving if no specific capability identified
        if not capabilities:
            capabilities.append(ExpertCapability.PROBLEM_SOLVING)
        
        return capabilities

class ByzantineFaultTolerantConsensus:
    """Byzantine fault tolerant consensus for expert decisions"""
    
    async def calculate_consensus(self, 
                                responses: List[ExpertResponse],
                                threshold: float,
                                byzantine_tolerance: bool = True) -> ConsensusResult:
        """Calculate consensus with Byzantine fault tolerance"""
        
        if len(responses) < 2:
            return ConsensusResult(
                achieved=False,
                decision=ValidationDecision.ESCALATE,
                confidence=0.0,
                reasoning="Insufficient expert responses for consensus",
                agreement_score=0.0
            )
        
        # Group responses by decision
        decision_groups = defaultdict(list)
        for response in responses:
            decision_groups[response.decision].append(response)
        
        # Apply Byzantine fault tolerance if enabled
        if byzantine_tolerance:
            responses = self._filter_byzantine_responses(responses)
        
        # Find majority decision
        decision_counts = {decision: len(responses) for decision, responses in decision_groups.items()}
        majority_decision = max(decision_counts, key=decision_counts.get)
        majority_count = decision_counts[majority_decision]
        
        # Calculate agreement score
        agreement_score = majority_count / len(responses)
        
        # Check if consensus threshold is met
        consensus_achieved = agreement_score >= threshold
        
        # Calculate weighted confidence
        majority_responses = decision_groups[majority_decision]
        weighted_confidence = sum(r.confidence for r in majority_responses) / len(majority_responses)
        
        # Generate reasoning
        reasoning = self._generate_consensus_reasoning(
            majority_decision, majority_responses, agreement_score, consensus_achieved
        )
        
        return ConsensusResult(
            achieved=consensus_achieved,
            decision=majority_decision,
            confidence=weighted_confidence,
            reasoning=reasoning,
            agreement_score=agreement_score,
            response_distribution=decision_counts
        )
    
    def _filter_byzantine_responses(self, responses: List[ExpertResponse]) -> List[ExpertResponse]:
        """Filter out potential Byzantine (malicious/faulty) responses"""
        
        if len(responses) < 4:  # Need at least 4 responses for Byzantine filtering
            return responses
        
        # Calculate response similarity scores
        similarity_matrix = self._calculate_response_similarities(responses)
        
        # Identify outliers (potential Byzantine responses)
        outlier_threshold = 0.3  # Responses with <30% similarity to others
        filtered_responses = []
        
        for i, response in enumerate(responses):
            avg_similarity = np.mean([similarity_matrix[i][j] for j in range(len(responses)) if i != j])
            
            if avg_similarity >= outlier_threshold:
                filtered_responses.append(response)
            else:
                logger.warning(f"Filtering potential Byzantine response from {response.expert_id}")
        
        return filtered_responses or responses  # Return original if all filtered
```

**Phase 2 Acceptance Criteria**:
- [ ] Expert LLM integration functional with comprehensive safety validation
- [ ] LLM responses validated for security (no dangerous recommendations)
- [ ] Policy engine integrated with OPA and comprehensive fallback rules
- [ ] Expert coordination system handles Byzantine fault tolerance
- [ ] Multi-expert consensus algorithms working correctly
- [ ] Performance maintained: 95% of requests processed efficiently
- [ ] Error handling and fallback mechanisms tested

---

## 📁 Phase 3: FUSE Content Generation

**PRIORITY**: HIGH - EXPERT AGENT USABILITY  
**OBJECTIVE**: Generate meaningful virtual filesystem content  

### 3.1 Intelligent Current Directory Content

**Location**: `src/lighthouse/bridge/fuse_mount/content_generator.py`

```python
class IntelligentContentGenerator:
    """Generate intelligent virtual filesystem content for expert agents"""
    
    def __init__(self, project_aggregate: ProjectAggregate):
        self.project_aggregate = project_aggregate
        self.ast_analyzer = ProductionASTAnalyzer()
        self.content_cache = TTLCache(maxsize=10000, ttl=300)  # 5-minute cache
        self.security_analyzer = CodeSecurityAnalyzer()
        
    async def generate_current_view(self, file_path: str, agent_id: str) -> str:
        """Generate intelligent current project view with security analysis"""
        
        cache_key = f"current:{file_path}:{agent_id}"
        if cache_key in self.content_cache:
            return self.content_cache[cache_key]
        
        try:
            if os.path.exists(file_path):
                # Read actual file content
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    base_content = await f.read()
                
                # Generate enhanced content based on file type
                if self._is_code_file(file_path):
                    enhanced_content = await self._enhance_code_file(base_content, file_path, agent_id)
                elif self._is_config_file(file_path):
                    enhanced_content = await self._enhance_config_file(base_content, file_path)
                elif self._is_documentation_file(file_path):
                    enhanced_content = await self._enhance_documentation(base_content, file_path)
                else:
                    enhanced_content = await self._enhance_generic_file(base_content, file_path)
                
                self.content_cache[cache_key] = enhanced_content
                return enhanced_content
                
            else:
                # Generate placeholder content for virtual files
                return await self._generate_virtual_file_content(file_path, agent_id)
                
        except Exception as e:
            logger.error(f"Error generating content for {file_path}: {e}")
            return self._generate_error_content(file_path, str(e))
    
    async def _enhance_code_file(self, content: str, file_path: str, agent_id: str) -> str:
        """Enhance code files with AST analysis and security annotations"""
        
        try:
            # Parse AST and generate anchors
            ast_analysis = await self.ast_analyzer.analyze_code(content, file_path)
            
            # Security analysis
            security_analysis = await self.security_analyzer.analyze_code(content, file_path)
            
            # Build enhanced content
            enhanced_lines = content.split('\n')
            
            # Insert AST anchor comments
            for anchor in reversed(ast_analysis.anchors):  # Reverse to maintain line numbers
                anchor_comment = f"  # AST_ANCHOR: {anchor.id} [{anchor.node_type}:{anchor.name}] - Line {anchor.line_number}"
                enhanced_lines.insert(anchor.line_number, anchor_comment)
            
            # Insert security annotations
            for warning in reversed(security_analysis.warnings):
                security_comment = f"  # SECURITY: {warning.severity} - {warning.description}"
                enhanced_lines.insert(warning.line_number, security_comment)
            
            # Add file header with analysis summary
            header = f"""# LIGHTHOUSE ENHANCED VIEW - {os.path.basename(file_path)}
# Generated for agent: {agent_id}
# AST Anchors: {len(ast_analysis.anchors)} functions/classes identified
# Security Warnings: {len(security_analysis.warnings)} issues found
# File Type: {ast_analysis.language}
# Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()}
#
# EXPERT ANALYSIS:
# - Complexity Score: {ast_analysis.complexity_score}/10
# - Security Risk: {security_analysis.risk_level}
# - Maintainability: {ast_analysis.maintainability_score}/10
#
# Use standard Unix tools: grep, find, cat, vim, etc.
# AST anchors help identify code structure changes
# Security annotations highlight potential issues
#
#{'='*60}

"""
            
            return header + '\n'.join(enhanced_lines)
            
        except Exception as e:
            logger.error(f"Error enhancing code file {file_path}: {e}")
            return f"# Error enhancing code file: {str(e)}\n\n{content}"
    
    async def _enhance_config_file(self, content: str, file_path: str) -> str:
        """Enhance configuration files with validation and security checks"""
        
        try:
            # Detect config format
            config_format = self._detect_config_format(file_path)
            
            # Parse and validate configuration
            config_analysis = await self._analyze_configuration(content, config_format, file_path)
            
            header = f"""# LIGHTHOUSE CONFIG ANALYSIS - {os.path.basename(file_path)}
# Config Format: {config_format}
# Validation Status: {'VALID' if config_analysis.is_valid else 'INVALID'}
# Security Issues: {len(config_analysis.security_issues)}
# Deprecated Settings: {len(config_analysis.deprecated_settings)}
#
# CONFIGURATION ANALYSIS:
"""
            
            for issue in config_analysis.security_issues:
                header += f"# SECURITY WARNING: {issue.description} (Line {issue.line_number})\n"
            
            for deprecated in config_analysis.deprecated_settings:
                header += f"# DEPRECATED: {deprecated.setting} -> use {deprecated.replacement}\n"
            
            header += "#\n" + "="*60 + "\n\n"
            
            # Add line-by-line annotations
            lines = content.split('\n')
            for i, line in enumerate(lines):
                line_issues = [issue for issue in config_analysis.line_issues if issue.line_number == i + 1]
                if line_issues:
                    for issue in line_issues:
                        lines[i] += f"  # {issue.severity}: {issue.description}"
            
            return header + '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Error enhancing config file {file_path}: {e}")
            return f"# Error analyzing configuration: {str(e)}\n\n{content}"

class ProductionASTAnalyzer:
    """Production-grade AST analysis with multiple language support"""
    
    def __init__(self):
        self.parsers = {
            '.py': PythonASTParser(),
            '.js': JavaScriptASTParser(), 
            '.ts': TypeScriptASTParser(),
            '.go': GoASTParser(),
            '.java': JavaASTParser(),
            '.cpp': CppASTParser(),
            '.c': CASTParser(),
        }
    
    async def analyze_code(self, content: str, file_path: str) -> ASTAnalysis:
        """Perform comprehensive AST analysis"""
        
        file_ext = os.path.splitext(file_path)[1].lower()
        parser = self.parsers.get(file_ext)
        
        if not parser:
            return ASTAnalysis(
                language="unknown",
                anchors=[],
                complexity_score=0,
                maintainability_score=0,
                error="Unsupported file type"
            )
        
        try:
            # Parse AST
            ast_tree = await parser.parse(content)
            
            # Extract structural elements
            anchors = await parser.extract_anchors(ast_tree, file_path)
            
            # Calculate metrics
            complexity_score = await parser.calculate_complexity(ast_tree)
            maintainability_score = await parser.calculate_maintainability(ast_tree)
            
            return ASTAnalysis(
                language=parser.language,
                anchors=anchors,
                complexity_score=complexity_score,
                maintainability_score=maintainability_score,
                ast_tree=ast_tree
            )
            
        except Exception as e:
            logger.error(f"AST analysis failed for {file_path}: {e}")
            return ASTAnalysis(
                language=parser.language,
                anchors=[],
                complexity_score=0,
                maintainability_score=0,
                error=str(e)
            )

class CodeSecurityAnalyzer:
    """Analyze code for security vulnerabilities and best practices"""
    
    def __init__(self):
        self.security_rules = self._load_security_rules()
        self.vulnerability_patterns = self._load_vulnerability_patterns()
    
    async def analyze_code(self, content: str, file_path: str) -> SecurityAnalysis:
        """Perform comprehensive security analysis"""
        
        warnings = []
        risk_level = "LOW"
        
        try:
            # Check for common vulnerability patterns
            for pattern in self.vulnerability_patterns:
                matches = re.finditer(pattern.regex, content, re.MULTILINE | re.IGNORECASE)
                for match in matches:
                    line_number = content[:match.start()].count('\n') + 1
                    warnings.append(SecurityWarning(
                        line_number=line_number,
                        severity=pattern.severity,
                        description=pattern.description,
                        pattern=pattern.name,
                        matched_text=match.group(0)[:50] + "..." if len(match.group(0)) > 50 else match.group(0)
                    ))
            
            # Determine overall risk level
            if any(w.severity == "CRITICAL" for w in warnings):
                risk_level = "CRITICAL"
            elif any(w.severity == "HIGH" for w in warnings):
                risk_level = "HIGH"
            elif any(w.severity == "MEDIUM" for w in warnings):
                risk_level = "MEDIUM"
            
            return SecurityAnalysis(
                risk_level=risk_level,
                warnings=warnings,
                file_path=file_path
            )
            
        except Exception as e:
            logger.error(f"Security analysis failed for {file_path}: {e}")
            return SecurityAnalysis(
                risk_level="UNKNOWN",
                warnings=[],
                error=str(e)
            )
    
    def _load_vulnerability_patterns(self) -> List[VulnerabilityPattern]:
        """Load vulnerability detection patterns"""
        
        return [
            VulnerabilityPattern(
                name="hardcoded_password",
                regex=r'password\s*=\s*["\'][^"\']{3,}["\']',
                severity="HIGH",
                description="Hardcoded password detected"
            ),
            VulnerabilityPattern(
                name="sql_injection",
                regex=r'execute\(.*%.*\)|query\(.*\+.*\)',
                severity="CRITICAL", 
                description="Potential SQL injection vulnerability"
            ),
            VulnerabilityPattern(
                name="command_injection",
                regex=r'os\.system\(.*\+.*\)|subprocess\.(call|run)\(.*\+.*\)',
                severity="CRITICAL",
                description="Potential command injection vulnerability"
            ),
            # Add more patterns...
        ]
```

### 3.2 Time Travel History Generation

**Location**: `src/lighthouse/bridge/fuse_mount/history_generator.py`

```python
class TimeravelHistoryGenerator:
    """Generate accurate time travel debugging views"""
    
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.history_cache = TTLCache(maxsize=1000, ttl=600)  # 10-minute cache
        self.diff_engine = IntelligentDiffEngine()
        
    async def generate_history_view(self, file_path: str, timestamp: str, agent_id: str) -> str:
        """Generate accurate historical view with expert analysis"""
        
        cache_key = f"history:{file_path}:{timestamp}:{agent_id}"
        if cache_key in self.history_cache:
            return self.history_cache[cache_key]
        
        try:
            target_time = self._parse_timestamp(timestamp)
            
            # Query event store for file history
            file_events = await self.event_store.get_file_history(
                file_path=file_path,
                before_timestamp=target_time,
                include_metadata=True
            )
            
            if not file_events:
                return self._generate_no_history_content(file_path, timestamp)
            
            # Reconstruct file state at target time
            reconstructed_state = await self._reconstruct_file_state(file_events)
            
            # Generate change analysis
            change_analysis = await self._analyze_file_changes(file_events)
            
            # Build comprehensive history view
            history_content = await self._build_history_content(
                file_path, timestamp, target_time, 
                reconstructed_state, file_events, change_analysis, agent_id
            )
            
            self.history_cache[cache_key] = history_content
            return history_content
            
        except Exception as e:
            logger.error(f"Error generating history for {file_path} at {timestamp}: {e}")
            return self._generate_error_history_content(file_path, timestamp, str(e))
    
    async def _reconstruct_file_state(self, events: List[Event]) -> FileState:
        """Accurately reconstruct file state from event history"""
        
        current_content = ""
        metadata = {}
        
        # Process events chronologically
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        
        for event in sorted_events:
            if event.event_type == EventType.FILE_CREATED:
                current_content = event.data.get('content', '')
                metadata.update(event.data.get('metadata', {}))
                
            elif event.event_type == EventType.FILE_MODIFIED:
                # Apply diff if available, otherwise use full content
                if 'diff' in event.data:
                    current_content = await self.diff_engine.apply_diff(
                        current_content, event.data['diff']
                    )
                else:
                    current_content = event.data.get('new_content', current_content)
                    
                metadata.update(event.data.get('metadata', {}))
                
            elif event.event_type == EventType.FILE_MOVED:
                # Update file path metadata
                metadata['original_path'] = event.data.get('old_path')
                metadata['moved_at'] = event.timestamp
                
            elif event.event_type == EventType.FILE_DELETED:
                current_content = ""
                metadata['deleted_at'] = event.timestamp
        
        return FileState(
            content=current_content,
            metadata=metadata,
            last_modified=sorted_events[-1].timestamp if sorted_events else None,
            total_modifications=len([e for e in sorted_events if e.event_type == EventType.FILE_MODIFIED])
        )
    
    async def _build_history_content(self, 
                                   file_path: str, 
                                   timestamp: str, 
                                   target_time: datetime,
                                   file_state: FileState,
                                   events: List[Event],
                                   change_analysis: ChangeAnalysis,
                                   agent_id: str) -> str:
        """Build comprehensive history view content"""
        
        # Calculate time travel statistics
        total_events = len(events)
        modifications = len([e for e in events if e.event_type == EventType.FILE_MODIFIED])
        contributors = set(e.agent_id for e in events if e.agent_id)
        
        # Build header with time travel context
        header = f"""# LIGHTHOUSE TIME TRAVEL - {os.path.basename(file_path)}
# Reconstructed state at: {timestamp}
# Target time: {target_time.isoformat()}
# Viewing agent: {agent_id}
#
# TIME TRAVEL STATISTICS:
# - Total events: {total_events}
# - File modifications: {modifications}
# - Contributors: {len(contributors)} ({', '.join(list(contributors)[:5])})
# - First modification: {events[0].timestamp.isoformat() if events else 'N/A'}
# - Last modification: {events[-1].timestamp.isoformat() if events else 'N/A'}
#
# CHANGE ANALYSIS:
# - Code complexity change: {change_analysis.complexity_delta:+.1f}
# - Lines added: {change_analysis.lines_added}
# - Lines removed: {change_analysis.lines_removed}
# - Security risk change: {change_analysis.security_risk_delta}
# - Major refactoring events: {change_analysis.refactoring_events}
#
# RECONSTRUCTION STATUS: {'SUCCESS' if file_state.content else 'EMPTY/DELETED'}
# Reconstruction confidence: {change_analysis.reconstruction_confidence:.1%}
#
#{'='*70}

"""
        
        # Add file content if available
        if file_state.content:
            content_with_annotations = await self._add_historical_annotations(
                file_state.content, events, file_path
            )
            main_content = f"\n{content_with_annotations}\n"
        else:
            main_content = "\n# FILE WAS EMPTY OR DELETED AT THIS TIME\n\n"
        
        # Add detailed event history
        event_history = self._format_detailed_event_history(events, target_time)
        
        # Combine all sections
        return header + main_content + "\n" + event_history
    
    async def _add_historical_annotations(self, 
                                        content: str, 
                                        events: List[Event], 
                                        file_path: str) -> str:
        """Add historical context annotations to content"""
        
        lines = content.split('\n')
        
        # Track line origins from events
        line_origins = await self._track_line_origins(events, lines)
        
        # Add annotations
        annotated_lines = []
        for i, line in enumerate(lines):
            origin = line_origins.get(i)
            if origin:
                annotation = f"  # HISTORY: Added by {origin.agent_id} at {origin.timestamp.strftime('%Y-%m-%d %H:%M')}"
                if origin.modification_type == "refactoring":
                    annotation += " [REFACTORED]"
                elif origin.modification_type == "bug_fix":
                    annotation += " [BUG FIX]"
                
                annotated_lines.append(line + annotation)
            else:
                annotated_lines.append(line)
        
        return '\n'.join(annotated_lines)

class ChangeAnalysis:
    """Analysis of file changes over time"""
    
    def __init__(self):
        self.complexity_delta = 0.0
        self.lines_added = 0
        self.lines_removed = 0
        self.security_risk_delta = "UNCHANGED"
        self.refactoring_events = 0
        self.reconstruction_confidence = 1.0
        self.major_changes = []
```

**Phase 3 Acceptance Criteria**:
- [ ] Current directory serves intelligent content with AST anchors and security analysis
- [ ] History directory provides accurate time travel debugging with change analysis
- [ ] Context directory generates comprehensive expert context packages
- [ ] Shadow directory shows code alternatives and refactoring suggestions  
- [ ] Streams directory handles real-time expert communication
- [ ] Expert agents can effectively use standard Unix tools (grep, cat, find, vim)
- [ ] Content generation performance: <5ms for cached content, <50ms for new analysis
- [ ] All generated content is secure and doesn't leak sensitive information

---

## 🧪 Phase 4: Comprehensive Testing Framework

**PRIORITY**: CRITICAL - SYSTEM RELIABILITY  
**OBJECTIVE**: Comprehensive testing for production readiness  

### 4.1 Multi-Agent Integration Testing

**Location**: `tests/integration/test_multi_agent_workflows.py`

```python
@pytest.mark.integration
class TestMultiAgentWorkflows:
    """Comprehensive multi-agent workflow testing"""
    
    @pytest.fixture(scope="class")
    async def production_test_environment(self):
        """Set up production-like test environment"""
        
        # Create real components (not mocks)
        event_store = await self._create_production_event_store()
        bridge = await self._create_production_bridge(event_store)
        expert_registry = await self._create_expert_registry()
        fuse_mount = await self._create_fuse_mount()
        
        # Register diverse expert agents
        experts = await self._register_test_experts(expert_registry)
        
        yield {
            'event_store': event_store,
            'bridge': bridge,
            'expert_registry': expert_registry,
            'fuse_mount': fuse_mount,
            'experts': experts
        }
        
        # Cleanup
        await self._cleanup_test_environment(bridge, fuse_mount, expert_registry)
    
    async def test_complete_dangerous_command_workflow(self, production_test_environment):
        """Test complete workflow for dangerous command requiring multi-expert consensus"""
        
        env = production_test_environment
        
        # Create highly dangerous command
        dangerous_request = ValidationRequest(
            tool_name="Bash",
            tool_input={"command": "sudo rm -rf /var/log/audit.log /var/log/auth.log"},
            agent_id="test_user_agent",
            context={
                "working_directory": "/var/log",
                "user_role": "developer",
                "project_phase": "testing"
            }
        )
        
        # Send through complete validation pipeline
        start_time = time.perf_counter()
        validation_result = await env['bridge'].validate_command(dangerous_request)
        processing_time = time.perf_counter() - start_time
        
        # Verify expert escalation occurred
        assert validation_result.expert_required == True
        assert validation_result.decision == ValidationDecision.BLOCKED
        assert processing_time < 2.0  # Should complete within 2 seconds
        
        # Verify multiple experts were consulted
        recent_consultations = await env['expert_registry'].get_recent_consultations(
            since=datetime.utcnow() - timedelta(minutes=1)
        )
        
        assert len(recent_consultations) >= 1
        consultation = recent_consultations[0]
        assert len(consultation.expert_responses) >= 2  # Multiple experts
        
        # Verify consensus was reached
        assert consultation.consensus_achieved == True
        assert consultation.consensus_decision == ValidationDecision.BLOCKED
        
        # Verify proper logging in event store
        validation_events = await env['event_store'].query_events(
            EventQuery(
                event_types=[EventType.VALIDATION_COMPLETED],
                agent_id="test_user_agent",
                limit=1
            ),
            agent_id=AgentIdentity("test_system")
        )
        
        assert len(validation_events.events) == 1
        assert validation_events.events[0].data['decision'] == 'BLOCKED'
    
    async def test_concurrent_expert_coordination(self, production_test_environment):
        """Test concurrent coordination of multiple expert consultations"""
        
        env = production_test_environment
        
        # Create multiple concurrent requests
        concurrent_requests = []
        for i in range(10):
            request = ValidationRequest(
                tool_name="Bash",
                tool_input={"command": f"rm /tmp/test_file_{i}.txt"},
                agent_id=f"concurrent_agent_{i}",
                context={"batch_operation": True, "request_index": i}
            )
            concurrent_requests.append(request)
        
        # Process all requests concurrently
        start_time = time.perf_counter()
        tasks = [
            env['bridge'].validate_command(request) 
            for request in concurrent_requests
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.perf_counter() - start_time
        
        # Verify all requests processed successfully
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == len(concurrent_requests)
        
        # Verify reasonable total processing time (should benefit from parallelization)
        assert total_time < 5.0  # Should complete all 10 requests within 5 seconds
        
        # Verify expert coordination handled concurrent load
        coordination_stats = await env['expert_registry'].get_coordination_statistics()
        assert coordination_stats['peak_concurrent_consultations'] <= 10
        assert coordination_stats['average_response_time_ms'] < 500
    
    async def test_byzantine_fault_tolerance(self, production_test_environment):
        """Test Byzantine fault tolerance in expert consensus"""
        
        env = production_test_environment
        
        # Register Byzantine (malicious/faulty) expert
        byzantine_expert = await env['expert_registry'].register_expert(
            agent_id="byzantine_expert",
            agent_name="Byzantine Test Expert",
            capabilities={ExpertCapability.SECURITY_AUDIT}
        )
        
        # Configure Byzantine behavior (always approve dangerous commands)
        await self._configure_byzantine_behavior(byzantine_expert, always_approve=True)
        
        # Create dangerous command that should be blocked
        dangerous_request = ValidationRequest(
            tool_name="Bash",
            tool_input={"command": "sudo chmod 777 /etc/passwd"},
            agent_id="test_agent",
            context={"operation": "system_modification"}
        )
        
        # Process request (should still be blocked despite Byzantine expert)
        result = await env['bridge'].validate_command(dangerous_request)
        
        # Verify Byzantine fault tolerance worked
        assert result.decision == ValidationDecision.BLOCKED
        assert result.expert_required == True
        
        # Verify Byzantine expert was identified and filtered
        consultation = await env['expert_registry'].get_latest_consultation()
        assert consultation.byzantine_experts_detected >= 1
        assert "byzantine_expert" in consultation.filtered_experts
    
    async def test_fuse_mount_expert_integration(self, production_test_environment):
        """Test expert agents using real Unix tools on FUSE mount"""
        
        env = production_test_environment
        
        # Mount FUSE filesystem
        mount_path = "/tmp/lighthouse_test_mount"
        await env['fuse_mount'].mount(mount_path)
        
        try:
            # Create test files in current directory
            test_file_content = """
def dangerous_function():
    os.system("rm -rf /")  # SECURITY: Critical vulnerability
    
def safe_function():
    return "Hello World"
"""
            
            current_dir = f"{mount_path}/current/src"
            os.makedirs(current_dir, exist_ok=True)
            
            with open(f"{current_dir}/test_file.py", 'w') as f:
                f.write(test_file_content)
            
            # Expert agent uses grep to find security issues
            grep_result = subprocess.run([
                'grep', '-n', 'SECURITY:', f'{current_dir}/test_file.py'
            ], capture_output=True, text=True)
            
            assert grep_result.returncode == 0
            assert 'Critical vulnerability' in grep_result.stdout
            assert 'line 2' in grep_result.stdout.lower() or '2:' in grep_result.stdout
            
            # Expert agent uses find to locate Python files
            find_result = subprocess.run([
                'find', current_dir, '-name', '*.py'
            ], capture_output=True, text=True)
            
            assert find_result.returncode == 0
            assert 'test_file.py' in find_result.stdout
            
            # Expert agent uses cat to read file with AST anchors
            cat_result = subprocess.run([
                'cat', f'{current_dir}/test_file.py'
            ], capture_output=True, text=True)
            
            assert cat_result.returncode == 0
            assert 'AST_ANCHOR:' in cat_result.stdout  # Verify AST annotations added
            assert 'dangerous_function' in cat_result.stdout
            
            # Expert agent searches history
            history_dir = f"{mount_path}/history"
            if os.path.exists(history_dir):
                ls_result = subprocess.run([
                    'ls', '-la', history_dir
                ], capture_output=True, text=True)
                
                assert ls_result.returncode == 0
                
        finally:
            await env['fuse_mount'].unmount(mount_path)

class TestByzantineFaultTolerance:
    """Dedicated testing for Byzantine fault tolerance scenarios"""
    
    async def test_consensus_with_one_third_byzantine_experts(self):
        """Test consensus works with up to 1/3 Byzantine experts"""
        
        # Create 6 experts (can tolerate 2 Byzantine)
        honest_experts = await self._create_honest_experts(4)
        byzantine_experts = await self._create_byzantine_experts(2)
        all_experts = honest_experts + byzantine_experts
        
        consensus_engine = ByzantineFaultTolerantConsensus()
        
        # Create responses where Byzantine experts give opposite decision
        honest_responses = [
            ExpertResponse(
                response_id=f"honest_{i}",
                request_id="test_request",
                expert_id=expert.agent_id,
                decision="BLOCKED",
                reasoning="Command is dangerous",
                confidence=0.9
            ) for i, expert in enumerate(honest_experts)
        ]
        
        byzantine_responses = [
            ExpertResponse(
                response_id=f"byzantine_{i}",
                request_id="test_request", 
                expert_id=expert.agent_id,
                decision="APPROVED",  # Opposite decision
                reasoning="Command is safe",  # Deceptive reasoning
                confidence=0.95  # High confidence to appear credible
            ) for i, expert in enumerate(byzantine_experts)
        ]
        
        all_responses = honest_responses + byzantine_responses
        
        # Calculate consensus
        consensus = await consensus_engine.calculate_consensus(
            responses=all_responses,
            threshold=0.67,
            byzantine_tolerance=True
        )
        
        # Verify honest majority prevails
        assert consensus.achieved == True
        assert consensus.decision == "BLOCKED"
        assert consensus.agreement_score >= 0.67

class PropertyBasedTestFramework:
    """Property-based testing for system invariants"""
    
    @given(commands=st.text(min_size=1, max_size=1000))
    @settings(max_examples=1000, deadline=timedelta(seconds=30))
    async def test_validation_always_returns_decision(self, commands):
        """Property: Validation always returns a valid decision"""
        
        request = ValidationRequest(
            tool_name="Bash",
            tool_input={"command": commands},
            agent_id="property_test_agent"
        )
        
        result = await self.bridge.validate_command(request)
        
        # Invariant: Always returns valid decision
        assert result.decision in [
            ValidationDecision.APPROVED,
            ValidationDecision.BLOCKED, 
            ValidationDecision.ESCALATE
        ]
        
        # Invariant: Confidence is valid
        assert 0.0 <= result.confidence <= 1.0
        
        # Invariant: Has reasoning
        assert len(result.reason) > 0
    
    @given(file_paths=st.text(min_size=1, max_size=500))
    @settings(max_examples=500)
    async def test_path_validation_prevents_traversal(self, file_paths):
        """Property: Path validation prevents all traversal attempts"""
        
        path_validator = SecurePathValidator(["/allowed/base/path"])
        
        try:
            validated_path = path_validator.validate_path(file_paths)
            # If validation succeeds, path must be within allowed base
            assert validated_path.startswith("/allowed/base/path")
        except SecurityError:
            # Expected for invalid paths - this is correct behavior
            pass
    
    @given(
        events=st.lists(
            st.builds(Event, 
                event_type=st.sampled_from(list(EventType)),
                timestamp=st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1))
            ),
            min_size=0,
            max_size=100
        )
    )
    async def test_event_ordering_invariant(self, events):
        """Property: Event store maintains chronological ordering"""
        
        # Store events
        for event in events:
            await self.event_store.append_event(event, agent_id=AgentIdentity("test"))
        
        # Query events
        query_result = await self.event_store.query_events(
            EventQuery(limit=len(events) + 10),
            agent_id=AgentIdentity("test")
        )
        
        retrieved_events = query_result.events
        
        # Invariant: Events are chronologically ordered
        for i in range(1, len(retrieved_events)):
            assert retrieved_events[i-1].timestamp <= retrieved_events[i].timestamp
```

### 4.2 Performance and Load Testing

**Location**: `tests/performance/test_production_performance.py`

```python
@pytest.mark.performance
class TestProductionPerformance:
    """Production-grade performance testing"""
    
    async def test_speed_layer_sla_compliance(self):
        """Test 99% of requests complete in <100ms under load"""
        
        # Create optimized production configuration
        speed_layer = await self._create_production_speed_layer()
        
        # Generate realistic request distribution
        request_generators = [
            self._generate_safe_requests(7000),      # 70% safe commands
            self._generate_risky_requests(2000),     # 20% risky commands  
            self._generate_complex_requests(1000)    # 10% complex commands
        ]
        
        all_requests = []
        for generator in request_generators:
            all_requests.extend(await generator)
        
        # Shuffle to simulate realistic ordering
        random.shuffle(all_requests)
        
        # Measure performance under sustained load
        latencies = []
        cache_hits = []
        error_count = 0
        
        # Warm-up period
        warmup_requests = all_requests[:100]
        for request in warmup_requests:
            await speed_layer.validate(request)
        
        # Main performance test
        start_time = time.perf_counter()
        
        for i, request in enumerate(all_requests):
            request_start = time.perf_counter()
            
            try:
                result = await speed_layer.validate(request)
                request_end = time.perf_counter()
                
                latency_ms = (request_end - request_start) * 1000
                latencies.append(latency_ms)
                cache_hits.append(result.cache_hit)
                
                # Log progress every 1000 requests
                if (i + 1) % 1000 == 0:
                    current_p99 = np.percentile(latencies, 99)
                    logger.info(f"Progress: {i+1}/{len(all_requests)}, P99: {current_p99:.2f}ms")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Request {i} failed: {e}")
                latencies.append(999.0)  # High penalty for failures
        
        total_time = time.perf_counter() - start_time
        
        # Calculate comprehensive metrics
        p99_latency = np.percentile(latencies, 99)
        p95_latency = np.percentile(latencies, 95)
        p50_latency = np.percentile(latencies, 50)
        mean_latency = np.mean(latencies)
        cache_hit_rate = sum(cache_hits) / len(cache_hits)
        requests_per_second = len(all_requests) / total_time
        
        # Performance assertions (SLA requirements)
        assert p99_latency < 100.0, f"P99 latency {p99_latency:.2f}ms violates <100ms SLA"
        assert p95_latency < 50.0, f"P95 latency {p95_latency:.2f}ms exceeds 50ms target"
        assert cache_hit_rate > 0.90, f"Cache hit rate {cache_hit_rate:.2%} below 90% target"
        assert error_count < len(all_requests) * 0.01, f"Error rate {error_count/len(all_requests):.2%} above 1%"
        assert requests_per_second > 100, f"Throughput {requests_per_second:.1f} RPS below 100 RPS minimum"
        
        # Log comprehensive results
        logger.info("=== PERFORMANCE TEST RESULTS ===")
        logger.info(f"Total requests: {len(all_requests):,}")
        logger.info(f"Total time: {total_time:.2f}s") 
        logger.info(f"Requests/sec: {requests_per_second:.1f}")
        logger.info(f"P50 latency: {p50_latency:.2f}ms")
        logger.info(f"P95 latency: {p95_latency:.2f}ms")
        logger.info(f"P99 latency: {p99_latency:.2f}ms")
        logger.info(f"Mean latency: {mean_latency:.2f}ms")
        logger.info(f"Cache hit rate: {cache_hit_rate:.2%}")
        logger.info(f"Error count: {error_count}")
        logger.info("=== SLA COMPLIANCE: PASSED ===")
    
    async def test_concurrent_expert_coordination_performance(self):
        """Test expert coordination performance under concurrent load"""
        
        # Setup expert registry with realistic number of experts
        expert_registry = await self._create_production_expert_registry()
        await self._register_realistic_expert_pool(expert_registry, count=20)
        
        coordinator = ProductionExpertCoordinator(expert_registry)
        
        # Generate concurrent coordination requests
        coordination_requests = [
            ValidationRequest(
                tool_name="Bash",
                tool_input={"command": f"moderate_risk_command_{i}"},
                agent_id=f"concurrent_agent_{i % 5}",  # 5 different agents
                context={"concurrent_test": True, "batch_id": i // 10}
            ) for i in range(100)
        ]
        
        # Test concurrent coordination
        coordination_times = []
        consensus_success_count = 0
        
        # Process in batches to simulate realistic load
        batch_size = 10
        for batch_start in range(0, len(coordination_requests), batch_size):
            batch = coordination_requests[batch_start:batch_start + batch_size]
            
            batch_start_time = time.perf_counter()
            
            # Process batch concurrently
            tasks = [
                coordinator.coordinate_expert_validation(request)
                for request in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_time = time.perf_counter() - batch_start_time
            coordination_times.append(batch_time)
            
            # Count successful consensus
            for result in results:
                if not isinstance(result, Exception) and result.consensus_achieved:
                    consensus_success_count += 1
        
        # Performance assertions
        avg_batch_time = np.mean(coordination_times)
        max_batch_time = max(coordination_times)
        consensus_rate = consensus_success_count / len(coordination_requests)
        
        assert avg_batch_time < 5.0, f"Average batch coordination time {avg_batch_time:.2f}s too high"
        assert max_batch_time < 10.0, f"Maximum batch coordination time {max_batch_time:.2f}s too high"
        assert consensus_rate > 0.85, f"Consensus success rate {consensus_rate:.2%} too low"
        
        logger.info(f"Concurrent coordination test: {len(coordination_requests)} requests")
        logger.info(f"Average batch time: {avg_batch_time:.2f}s")
        logger.info(f"Consensus success rate: {consensus_rate:.2%}")
    
    async def test_fuse_mount_performance_under_load(self):
        """Test FUSE mount performance with multiple concurrent expert agents"""
        
        mount_manager = await self._create_production_fuse_mount()
        mount_path = "/tmp/lighthouse_performance_test"
        
        await mount_manager.mount(mount_path)
        
        try:
            # Create realistic file structure
            await self._create_realistic_project_structure(mount_path)
            
            # Define realistic expert agent operations
            operations = [
                ('grep', ['-r', 'SECURITY:', f'{mount_path}/current']),
                ('find', [mount_path, '-name', '*.py', '-type', 'f']),
                ('cat', [f'{mount_path}/current/src/main.py']),
                ('ls', ['-la', f'{mount_path}/current']),
                ('head', ['-n', '20', f'{mount_path}/history/recent.log']),
            ]
            
            # Test concurrent FUSE operations
            operation_times = []
            
            async def run_concurrent_operations():
                tasks = []
                
                # Create 20 concurrent "expert agents" 
                for agent_id in range(20):
                    for operation, args in operations:
                        task = asyncio.create_task(
                            self._run_fuse_operation(operation, args)
                        )
                        tasks.append(task)
                
                # Execute all operations concurrently
                start_time = time.perf_counter()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                total_time = time.perf_counter() - start_time
                
                return results, total_time
            
            results, total_time = await run_concurrent_operations()
            
            # Analyze results
            successful_operations = len([r for r in results if not isinstance(r, Exception)])
            failed_operations = len(results) - successful_operations
            operations_per_second = len(results) / total_time
            
            # Performance assertions
            success_rate = successful_operations / len(results)
            assert success_rate > 0.95, f"FUSE operation success rate {success_rate:.2%} too low"
            assert total_time < 30.0, f"Total concurrent operation time {total_time:.2f}s too high"
            assert operations_per_second > 10.0, f"FUSE operations/sec {operations_per_second:.1f} too low"
            
            logger.info(f"FUSE concurrent performance: {len(results)} operations")
            logger.info(f"Success rate: {success_rate:.2%}")
            logger.info(f"Operations/sec: {operations_per_second:.1f}")
            logger.info(f"Total time: {total_time:.2f}s")
            
        finally:
            await mount_manager.unmount(mount_path)
    
    async def _run_fuse_operation(self, operation: str, args: List[str]) -> float:
        """Run a FUSE operation and return execution time"""
        
        start_time = time.perf_counter()
        try:
            result = subprocess.run(
                [operation] + args,
                capture_output=True,
                text=True,
                timeout=10.0  # 10 second timeout
            )
            execution_time = time.perf_counter() - start_time
            
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, operation)
            
            return execution_time
            
        except subprocess.TimeoutExpired:
            raise Exception(f"FUSE operation timeout: {operation} {' '.join(args)}")
        except Exception as e:
            raise Exception(f"FUSE operation failed: {operation} - {str(e)}")
```

**Phase 4 Acceptance Criteria**:
- [ ] End-to-end multi-agent workflows tested and verified
- [ ] Performance SLA validated: 99% of requests <100ms under realistic load
- [ ] Byzantine fault tolerance tested with up to 1/3 malicious experts
- [ ] FUSE mount operations tested with concurrent expert agents
- [ ] Property-based testing validates critical system invariants
- [ ] Security boundary testing ensures expert agent isolation
- [ ] Load testing confirms system handles 1000+ concurrent requests
- [ ] Failure mode testing validates graceful degradation
- [ ] All tests pass consistently with <1% flake rate

---

## 🏗️ Phase 5: Production Infrastructure

**PRIORITY**: MEDIUM - DEPLOYMENT READINESS  
**OBJECTIVE**: Production-ready deployment and operations  

### 5.1 Container and Orchestration

**Location**: `docker/production.Dockerfile`

```dockerfile
# Multi-stage build for production optimization
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libfuse3-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt requirements-prod.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-prod.txt

# Production stage
FROM python:3.12-slim as production

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    fuse3 \
    libfuse3-3 \
    postgresql-client \
    redis-tools \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user with FUSE capabilities
RUN groupadd -r lighthouse && useradd -r -g lighthouse lighthouse \
    && mkdir -p /mnt/lighthouse \
    && chown lighthouse:lighthouse /mnt/lighthouse

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=lighthouse:lighthouse src/ /app/src/
COPY --chown=lighthouse:lighthouse policies/ /app/policies/
COPY --chown=lighthouse:lighthouse docker/entrypoint.sh /app/entrypoint.sh

# Set working directory
WORKDIR /app

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Security: Drop capabilities except those needed for FUSE
USER lighthouse

# Health check with comprehensive validation
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "
import requests
import sys
try:
    # Check API health
    r = requests.get('http://localhost:8765/health', timeout=5)
    health = r.json()
    
    # Validate all components are healthy
    if health['status'] != 'healthy':
        sys.exit(1)
    if health['components']['event_store']['status'] != 'healthy':
        sys.exit(1)
    if health['components']['expert_coordination']['status'] != 'healthy':
        sys.exit(1)
    if health['components']['fuse_mount']['status'] != 'healthy':
        sys.exit(1)
        
    sys.exit(0)
except:
    sys.exit(1)
"

# Expose ports
EXPOSE 8765 8080 8090

# Use entrypoint for proper initialization
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "lighthouse.server"]
```

**Location**: `docker/entrypoint.sh`

```bash
#!/bin/bash
set -euo pipefail

# Comprehensive production entrypoint script

echo "=== Lighthouse Production Startup ==="
echo "Environment: ${ENVIRONMENT:-production}"
echo "Build: ${BUILD_VERSION:-unknown}"
echo "Node: $(hostname)"

# Validate required environment variables
required_vars=(
    "LIGHTHOUSE_AUTH_SECRET"
    "LIGHTHOUSE_SYSTEM_SECRET"
    "DATABASE_URL"
    "REDIS_URL"
)

for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

# Validate secrets are not default values
if [[ "${LIGHTHOUSE_AUTH_SECRET}" == "lighthouse-default-secret" ]]; then
    echo "ERROR: LIGHTHOUSE_AUTH_SECRET is set to default value"
    exit 1
fi

# Database connectivity check
echo "Checking database connectivity..."
python -c "
import os
import psycopg2
try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.close()
    print('Database connection: OK')
except Exception as e:
    print(f'Database connection failed: {e}')
    exit(1)
"

# Redis connectivity check  
echo "Checking Redis connectivity..."
python -c "
import os
import redis
try:
    r = redis.from_url(os.environ['REDIS_URL'])
    r.ping()
    print('Redis connection: OK')
except Exception as e:
    print(f'Redis connection failed: {e}')
    exit(1)
"

# FUSE capability check
echo "Checking FUSE capabilities..."
if ! command -v fusermount3 &> /dev/null; then
    echo "ERROR: FUSE not available"
    exit 1
fi

# Create FUSE mount point with proper permissions
mkdir -p /mnt/lighthouse/project
if [[ ! -w /mnt/lighthouse/project ]]; then
    echo "ERROR: FUSE mount point not writable"
    exit 1
fi

# Initialize application
echo "Initializing Lighthouse components..."
python -c "
import asyncio
from lighthouse.server import initialize_production_server

async def startup_check():
    try:
        server = await initialize_production_server()
        print('Component initialization: OK')
        await server.shutdown()
    except Exception as e:
        print(f'Initialization failed: {e}')
        exit(1)

asyncio.run(startup_check())
"

echo "=== Startup Validation Complete ==="
echo "Starting Lighthouse server..."

# Execute the main command
exec "$@"
```

**Location**: `k8s/production/lighthouse-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lighthouse-bridge
  namespace: lighthouse-production
  labels:
    app: lighthouse-bridge
    version: v1.0.0
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  selector:
    matchLabels:
      app: lighthouse-bridge
  template:
    metadata:
      labels:
        app: lighthouse-bridge
        version: v1.0.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: lighthouse-bridge
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
      - name: lighthouse-bridge
        image: lighthouse/bridge:1.0.0
        imagePullPolicy: Always
        ports:
        - name: api
          containerPort: 8765
          protocol: TCP
        - name: metrics
          containerPort: 8080
          protocol: TCP
        - name: health
          containerPort: 8090
          protocol: TCP
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: BUILD_VERSION
          value: "1.0.0"
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: LIGHTHOUSE_AUTH_SECRET
          valueFrom:
            secretKeyRef:
              name: lighthouse-secrets
              key: auth-secret
        - name: LIGHTHOUSE_SYSTEM_SECRET
          valueFrom:
            secretKeyRef:
              name: lighthouse-secrets
              key: system-secret
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: lighthouse-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: lighthouse-config
              key: redis-url
        - name: OPA_URL
          valueFrom:
            configMapKeyRef:
              name: lighthouse-config
              key: opa-url
        - name: LLM_API_KEY
          valueFrom:
            secretKeyRef:
              name: lighthouse-secrets
              key: llm-api-key
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
            ephemeral-storage: "10Gi"
          limits:
            memory: "8Gi" 
            cpu: "4"
            ephemeral-storage: "20Gi"
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8090
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8090
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 5
          failureThreshold: 2
        startupProbe:
          httpGet:
            path: /health/startup
            port: 8090
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 12
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: false  # FUSE requires writable filesystem
          capabilities:
            add:
            - SYS_ADMIN  # Required for FUSE mounting
            drop:
            - ALL
        volumeMounts:
        - name: fuse-mount
          mountPath: /mnt/lighthouse
          mountPropagation: Bidirectional
        - name: tmp-volume
          mountPath: /tmp
        - name: cache-volume
          mountPath: /app/cache
      volumes:
      - name: fuse-mount
        hostPath:
          path: /mnt/lighthouse
          type: DirectoryOrCreate
      - name: tmp-volume
        emptyDir:
          sizeLimit: 1Gi
      - name: cache-volume
        emptyDir:
          sizeLimit: 2Gi
      nodeSelector:
        lighthouse.io/fuse-capable: "true"
      tolerations:
      - key: "lighthouse.io/fuse"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - lighthouse-bridge
              topologyKey: kubernetes.io/hostname
```

### 5.2 Production Monitoring and Observability

**Location**: `k8s/monitoring/prometheus-config.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-lighthouse-config
  namespace: lighthouse-production
data:
  lighthouse-rules.yml: |
    groups:
    - name: lighthouse.sla
      interval: 15s
      rules:
      - alert: ValidationLatencyHigh
        expr: histogram_quantile(0.99, rate(lighthouse_validation_duration_seconds_bucket[5m])) > 0.1
        for: 2m
        labels:
          severity: critical
          component: speed_layer
        annotations:
          summary: "Lighthouse validation P99 latency exceeds 100ms SLA"
          description: "P99 validation latency is {{ $value | humanizeDuration }} which exceeds the 100ms SLA"
          
      - alert: CacheHitRateLow
        expr: rate(lighthouse_cache_hits_total[5m]) / rate(lighthouse_cache_requests_total[5m]) < 0.90
        for: 5m
        labels:
          severity: warning
          component: cache
        annotations:
          summary: "Lighthouse cache hit rate below target"
          description: "Cache hit rate is {{ $value | humanizePercentage }} which is below the 90% target"
          
      - alert: ExpertCoordinationFailure
        expr: rate(lighthouse_expert_coordination_failures_total[5m]) / rate(lighthouse_expert_coordination_total[5m]) > 0.05
        for: 3m
        labels:
          severity: critical
          component: expert_coordination
        annotations:
          summary: "High expert coordination failure rate"
          description: "Expert coordination failure rate is {{ $value | humanizePercentage }}"
          
      - alert: FUSEMountUnavailable
        expr: lighthouse_fuse_mount_healthy != 1
        for: 1m
        labels:
          severity: critical
          component: fuse_mount
        annotations:
          summary: "FUSE mount is unavailable"
          description: "FUSE mount health check failing on {{ $labels.instance }}"
          
      - alert: SecurityViolationSpike
        expr: rate(lighthouse_security_violations_total[1m]) > 10
        for: 30s
        labels:
          severity: critical
          component: security
        annotations:
          summary: "High rate of security violations detected"
          description: "Security violations rate is {{ $value }} per second"
          
    - name: lighthouse.capacity
      interval: 30s
      rules:
      - alert: HighMemoryUsage
        expr: (container_memory_usage_bytes{pod=~"lighthouse-bridge-.*"} / container_spec_memory_limit_bytes) > 0.85
        for: 5m
        labels:
          severity: warning
          component: infrastructure
        annotations:
          summary: "Lighthouse pod memory usage high"
          description: "Pod {{ $labels.pod }} memory usage is {{ $value | humanizePercentage }}"
          
      - alert: CPUThrottling
        expr: rate(container_cpu_cfs_throttled_seconds_total{pod=~"lighthouse-bridge-.*"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          component: infrastructure
        annotations:
          summary: "Lighthouse pod CPU throttling detected"
          description: "Pod {{ $labels.pod }} is experiencing CPU throttling"
          
    - name: lighthouse.dependencies
      interval: 60s
      rules:
      - alert: DatabaseConnectionFailure
        expr: lighthouse_database_connection_failures_total > 0
        for: 1m
        labels:
          severity: critical
          component: database
        annotations:
          summary: "Database connection failures detected"
          description: "{{ $value }} database connection failures in the last minute"
          
      - alert: RedisConnectionFailure
        expr: lighthouse_redis_connection_failures_total > 0
        for: 1m
        labels:
          severity: warning
          component: cache
        annotations:
          summary: "Redis connection issues detected"
          description: "{{ $value }} Redis connection failures in the last minute"

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-lighthouse-dashboard
  namespace: lighthouse-production
data:
  lighthouse-dashboard.json: |
    {
      "dashboard": {
        "id": null,
        "title": "Lighthouse Multi-Agent Coordination System",
        "tags": ["lighthouse", "multi-agent"],
        "timezone": "browser",
        "refresh": "10s",
        "panels": [
          {
            "title": "Validation Performance",
            "type": "graph",
            "targets": [
              {
                "expr": "histogram_quantile(0.50, rate(lighthouse_validation_duration_seconds_bucket[5m]))",
                "legendFormat": "P50 Latency"
              },
              {
                "expr": "histogram_quantile(0.95, rate(lighthouse_validation_duration_seconds_bucket[5m]))", 
                "legendFormat": "P95 Latency"
              },
              {
                "expr": "histogram_quantile(0.99, rate(lighthouse_validation_duration_seconds_bucket[5m]))",
                "legendFormat": "P99 Latency"
              }
            ],
            "yAxes": [
              {
                "label": "Latency (seconds)",
                "max": 0.2
              }
            ],
            "alert": {
              "conditions": [
                {
                  "query": {
                    "queryType": "",
                    "refId": "A"
                  },
                  "reducer": {
                    "params": [],
                    "type": "last"
                  },
                  "evaluator": {
                    "params": [0.1],
                    "type": "gt"
                  }
                }
              ],
              "executionErrorState": "alerting",
              "noDataState": "no_data",
              "frequency": "10s",
              "handler": 1,
              "name": "Validation Latency Alert",
              "message": "P99 validation latency exceeds 100ms SLA"
            }
          },
          {
            "title": "Expert Coordination Metrics",
            "type": "graph",
            "targets": [
              {
                "expr": "rate(lighthouse_expert_consultations_total[5m])",
                "legendFormat": "Consultations/sec"
              },
              {
                "expr": "lighthouse_active_expert_sessions",
                "legendFormat": "Active Expert Sessions"
              },
              {
                "expr": "rate(lighthouse_expert_consensus_achieved_total[5m]) / rate(lighthouse_expert_consultations_total[5m])",
                "legendFormat": "Consensus Rate"
              }
            ]
          },
          {
            "title": "FUSE Operations",
            "type": "graph", 
            "targets": [
              {
                "expr": "rate(lighthouse_fuse_operations_total[5m]) by (operation)",
                "legendFormat": "{{ operation }}"
              }
            ]
          },
          {
            "title": "Cache Performance",
            "type": "stat",
            "targets": [
              {
                "expr": "rate(lighthouse_cache_hits_total[5m]) / rate(lighthouse_cache_requests_total[5m])",
                "legendFormat": "Hit Rate"
              }
            ],
            "fieldConfig": {
              "defaults": {
                "min": 0,
                "max": 1,
                "unit": "percentunit",
                "thresholds": {
                  "steps": [
                    {
                      "color": "red",
                      "value": 0
                    },
                    {
                      "color": "yellow", 
                      "value": 0.85
                    },
                    {
                      "color": "green",
                      "value": 0.90
                    }
                  ]
                }
              }
            }
          }
        ]
      }
    }
```

**Phase 5 Acceptance Criteria**:
- [ ] Production Docker containers built and tested
- [ ] Kubernetes deployment working with proper security contexts
- [ ] High availability achieved with 3+ replicas and anti-affinity rules
- [ ] Comprehensive monitoring with SLA-based alerting
- [ ] Grafana dashboards providing operational visibility
- [ ] Health checks validate all components before traffic acceptance
- [ ] Secrets management using Kubernetes secrets (not hard-coded values)
- [ ] FUSE mounting working correctly in containerized environment
- [ ] Rolling updates work without service disruption
- [ ] Resource limits prevent resource exhaustion
- [ ] Security scanning passes for all container images

---

## 📊 Final Production Readiness Criteria

### **Security Certification Requirements**
- [ ] **Zero critical security vulnerabilities** - confirmed by security scanning
- [ ] **External security audit passed** - third-party penetration testing
- [ ] **All secrets properly managed** - no hard-coded credentials anywhere
- [ ] **Authentication systems secure** - token generation cryptographically sound
- [ ] **Path traversal protection verified** - cannot escape allowed directories
- [ ] **Rate limiting active** - DoS protection operational
- [ ] **Security monitoring functional** - threat detection and alerting

### **Performance Validation Requirements**  
- [ ] **99% of requests <100ms** - validated under realistic load
- [ ] **Cache hit rate >90%** - confirmed across all cache tiers
- [ ] **Expert coordination <30s** - consensus within reasonable time
- [ ] **FUSE operations <5ms** - file system operations performant
- [ ] **1000+ concurrent requests** - system handles production load
- [ ] **24-hour sustained testing** - system stable under continuous load
- [ ] **Memory usage stable** - no memory leaks detected

### **Functional Completeness Requirements**
- [ ] **Expert LLM integration working** - real expert validation functional
- [ ] **Policy engine operational** - OPA/Cedar integration complete
- [ ] **Expert coordination complete** - multi-expert consensus working
- [ ] **FUSE content generation active** - meaningful virtual filesystem content
- [ ] **Time travel debugging functional** - historical views accurate
- [ ] **Multi-agent workflows tested** - end-to-end scenarios validated
- [ ] **Byzantine fault tolerance verified** - handles malicious experts

### **Operational Readiness Requirements**
- [ ] **High availability deployment** - 3+ replicas with failover
- [ ] **Monitoring and alerting comprehensive** - SLA violations detected
- [ ] **Health checks complete** - all components validated
- [ ] **Backup and recovery tested** - data protection operational
- [ ] **Documentation complete** - operations runbooks available
- [ ] **Incident response procedures** - emergency response plans
- [ ] **Rolling updates verified** - zero-downtime deployments

### **Integration Testing Requirements**
- [ ] **End-to-end workflows validated** - Hook → Bridge → Expert Agent
- [ ] **Expert agents use Unix tools** - grep, find, cat, vim working on FUSE
- [ ] **Multi-expert consensus tested** - Byzantine scenarios validated
- [ ] **Security boundaries confirmed** - expert isolation verified
- [ ] **Failure modes tested** - graceful degradation operational
- [ ] **Property-based testing passed** - system invariants maintained
- [ ] **Load testing completed** - production capacity verified

---

## 📋 Implementation Approach for Open Source AI Agents

### **Quality Over Speed**
Since this is an open source project implemented by AI agents without time/budget constraints:

1. **Implement each phase completely** before moving to the next
2. **Focus on technical excellence** and production-quality code  
3. **Comprehensive testing at each phase** to ensure reliability
4. **Complete documentation** for each component implemented
5. **Security-first approach** with immediate vulnerability fixes

### **Iterative Validation**
- **Continuous testing** as each component is implemented
- **Performance validation** at every integration point
- **Security scanning** after each major change
- **End-to-end validation** after each phase completion

### **Open Source Standards**
- **Clean, well-documented code** suitable for open source contribution
- **Comprehensive test coverage** for reliability and maintainability  
- **Security best practices** following OWASP guidelines
- **Performance optimization** for efficiency and scalability
- **Architectural documentation** for future contributors

---

**Document Status**: ✅ **READY FOR IMPLEMENTATION**  
**Implementation Approach**: Systematic, quality-focused, comprehensive  
**Success Criteria**: Production-ready multi-agent coordination system  

This revised plan focuses on technical excellence and comprehensive implementation, leveraging the advantages of AI agent development to create a truly production-ready system without the constraints of traditional project management limitations.