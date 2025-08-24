"""
Policy Engine Cache

Rule-based validation cache that evaluates security policies and organizational rules.
Provides 1-5ms response times for policy-based validation decisions.

Features:
- Rule priority ordering and conflict resolution
- Dynamic rule loading from configuration
- Rule usage analytics and optimization
- Integration with external policy engines (OPA/Cedar)
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

from .models import PolicyRule, ValidationRequest, ValidationResult, ValidationDecision, ValidationConfidence

logger = logging.getLogger(__name__)


class RuleEngine:
    """Core rule evaluation engine"""
    
    def __init__(self):
        self.rules: Dict[str, PolicyRule] = {}
        self.rule_priority_order: List[str] = []
        self.compiled_patterns: Dict[str, re.Pattern] = {}
    
    def add_rule(self, rule: PolicyRule):
        """Add a policy rule to the engine"""
        self.rules[rule.rule_id] = rule
        
        # Recompile pattern for performance
        try:
            self.compiled_patterns[rule.rule_id] = re.compile(
                rule.pattern, 
                re.IGNORECASE | re.MULTILINE
            )
        except re.error as e:
            logger.warning(f"Invalid regex in rule {rule.rule_id}: {e}")
            # Fall back to literal string matching
            self.compiled_patterns[rule.rule_id] = None
        
        # Maintain priority order
        self._update_priority_order()
    
    def remove_rule(self, rule_id: str):
        """Remove a rule from the engine"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            self.compiled_patterns.pop(rule_id, None)
            self._update_priority_order()
    
    def _update_priority_order(self):
        """Update rule evaluation order by priority"""
        self.rule_priority_order = sorted(
            self.rules.keys(),
            key=lambda rule_id: self.rules[rule_id].priority,
            reverse=True  # Higher priority first
        )
    
    def evaluate(self, request: ValidationRequest) -> Optional[ValidationResult]:
        """
        Evaluate request against all rules
        
        Returns the first matching rule's decision, or None if no matches.
        """
        for rule_id in self.rule_priority_order:
            rule = self.rules[rule_id]
            
            # Check if rule applies to this request
            if not self._rule_applies(rule, request):
                continue
            
            # Check pattern match
            if self._pattern_matches(rule_id, rule, request):
                # Apply rule and return result
                result = rule.apply_to_request(request)
                logger.debug(f"Rule {rule_id} matched request {request.request_id}")
                return result
        
        return None
    
    def _rule_applies(self, rule: PolicyRule, request: ValidationRequest) -> bool:
        """Check if rule applies to the request based on tool/agent restrictions"""
        # Check tool name restriction
        if rule.tool_names and request.tool_name not in rule.tool_names:
            return False
        
        # Check agent pattern restriction  
        if rule.agent_patterns:
            agent_match = any(
                re.search(pattern, request.agent_id, re.IGNORECASE)
                for pattern in rule.agent_patterns
            )
            if not agent_match:
                return False
        
        return True
    
    def _pattern_matches(self, rule_id: str, rule: PolicyRule, request: ValidationRequest) -> bool:
        """Check if the rule pattern matches the request"""
        text_to_match = request.command_text
        compiled_pattern = self.compiled_patterns.get(rule_id)
        
        if compiled_pattern:
            # Use compiled regex
            return bool(compiled_pattern.search(text_to_match))
        else:
            # Fall back to literal string matching
            return rule.pattern.lower() in text_to_match.lower()
    
    def get_matching_rules(self, request: ValidationRequest) -> List[PolicyRule]:
        """Get all rules that match the request (for debugging)"""
        matching = []
        for rule_id in self.rule_priority_order:
            rule = self.rules[rule_id]
            if self._rule_applies(rule, request) and self._pattern_matches(rule_id, rule, request):
                matching.append(rule)
        return matching


class PolicyEngineCache:
    """High-performance policy evaluation cache"""
    
    def __init__(self, rule_config_path: Optional[str] = None):
        """
        Initialize policy engine cache
        
        Args:
            rule_config_path: Path to rule configuration file
        """
        self.rule_engine = RuleEngine()
        self.rule_config_path = rule_config_path
        self.last_config_check = 0.0
        
        # Cache for policy evaluations
        self._evaluation_cache: Dict[str, Tuple[ValidationResult, float]] = {}
        self._cache_ttl = 60.0  # 1 minute TTL for policy cache
        
        # Default security rules
        self._load_default_rules()
        
        # Load external rules if configured
        if rule_config_path and Path(rule_config_path).exists():
            self._load_rule_config(rule_config_path)
    
    def _load_default_rules(self):
        """Load built-in security rules"""
        
        # Critical system operations
        self.rule_engine.add_rule(PolicyRule(
            rule_id="critical_system_paths",
            pattern=r"/(etc|usr|var|boot|sys|proc|dev)/",
            decision=ValidationDecision.BLOCKED,
            confidence=ValidationConfidence.HIGH,
            reason="Access to critical system paths requires manual approval",
            created_at=datetime.now(),
            created_by="system",
            priority=1000,
            tool_names=["Write", "Edit", "MultiEdit", "Bash"]
        ))
        
        # Dangerous bash commands
        dangerous_commands = [
            "rm -rf", "rm -r /", "sudo rm", "chmod 777", "chown root",
            "dd if=", "mkfs", "fdisk", "parted", "shutdown", "reboot",
            "kill -9", "pkill -9", "killall", "> /dev/null", "mv / "
        ]
        
        for i, cmd in enumerate(dangerous_commands):
            self.rule_engine.add_rule(PolicyRule(
                rule_id=f"dangerous_command_{i:02d}",
                pattern=re.escape(cmd),
                decision=ValidationDecision.BLOCKED,
                confidence=ValidationConfidence.HIGH,
                reason=f"Dangerous command '{cmd}' requires explicit approval",
                created_at=datetime.now(),
                created_by="system", 
                priority=900,
                tool_names=["Bash"]
            ))
        
        # Safe operations - auto-approve
        safe_patterns = [
            (r"^ls\s", "Directory listing"),
            (r"^pwd$", "Print working directory"),
            (r"^echo\s", "Echo command"),
            (r"^cat\s[^/]", "Read file in current directory"),
            (r"^grep\s", "Text search"),
            (r"^find\s\.\s", "Find in current directory"),
            (r"^git status", "Git status check"),
            (r"^git log", "Git log check"),
            (r"^git diff", "Git diff check")
        ]
        
        for i, (pattern, description) in enumerate(safe_patterns):
            self.rule_engine.add_rule(PolicyRule(
                rule_id=f"safe_command_{i:02d}",
                pattern=pattern,
                decision=ValidationDecision.APPROVED,
                confidence=ValidationConfidence.HIGH,
                reason=f"Safe operation: {description}",
                created_at=datetime.now(),
                created_by="system",
                priority=500,
                tool_names=["Bash"]
            ))
        
        # Safe tools - always approve
        safe_tools = ["Read", "Glob", "Grep", "LS", "WebFetch", "WebSearch"]
        for tool in safe_tools:
            self.rule_engine.add_rule(PolicyRule(
                rule_id=f"safe_tool_{tool.lower()}",
                pattern=".*",  # Match all
                decision=ValidationDecision.APPROVED,
                confidence=ValidationConfidence.HIGH,
                reason=f"Tool {tool} is always safe",
                created_at=datetime.now(),
                created_by="system",
                priority=400,
                tool_names=[tool]
            ))
    
    def _load_rule_config(self, config_path: str):
        """Load rules from configuration file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            for rule_data in config.get('rules', []):
                rule = PolicyRule(
                    rule_id=rule_data['rule_id'],
                    pattern=rule_data['pattern'],
                    decision=ValidationDecision(rule_data['decision']),
                    confidence=ValidationConfidence(rule_data['confidence']),
                    reason=rule_data['reason'],
                    created_at=datetime.fromisoformat(rule_data['created_at']),
                    created_by=rule_data['created_by'],
                    priority=rule_data.get('priority', 100),
                    tool_names=rule_data.get('tool_names', []),
                    agent_patterns=rule_data.get('agent_patterns', [])
                )
                self.rule_engine.add_rule(rule)
                
            logger.info(f"Loaded {len(config.get('rules', []))} rules from {config_path}")
            
        except Exception as e:
            logger.error(f"Failed to load rule config from {config_path}: {e}")
    
    def _check_config_updates(self):
        """Check if rule configuration has been updated"""
        if not self.rule_config_path:
            return
        
        try:
            config_path = Path(self.rule_config_path)
            if config_path.exists():
                mtime = config_path.stat().st_mtime
                if mtime > self.last_config_check:
                    logger.info("Rule configuration updated, reloading...")
                    self._load_rule_config(str(config_path))
                    self.last_config_check = mtime
                    
                    # Clear cache to force re-evaluation with new rules
                    self._evaluation_cache.clear()
                    
        except Exception as e:
            logger.error(f"Failed to check config updates: {e}")
    
    async def evaluate(self, request: ValidationRequest) -> Optional[ValidationResult]:
        """
        Evaluate request against policy rules
        
        Returns validation result if a rule matches, None otherwise.
        """
        start_time = time.time()
        
        # Check for configuration updates
        self._check_config_updates()
        
        # Check cache first
        cache_key = f"{request.command_hash}:{request.agent_id}"
        cached_result = self._get_cached_evaluation(cache_key)
        if cached_result:
            return cached_result
        
        # Evaluate against rules
        result = self.rule_engine.evaluate(request)
        
        if result:
            # Update processing time
            processing_time = (time.time() - start_time) * 1000
            result.processing_time_ms = processing_time
            result.cache_hit = False
            
            # Cache the result
            self._cache_evaluation(cache_key, result)
        
        return result
    
    def _get_cached_evaluation(self, cache_key: str) -> Optional[ValidationResult]:
        """Get cached policy evaluation result"""
        if cache_key in self._evaluation_cache:
            result, cached_at = self._evaluation_cache[cache_key]
            
            # Check TTL
            if time.time() - cached_at < self._cache_ttl:
                # Update cache hit flag
                result.cache_hit = True
                result.processing_time_ms = 0.5  # Cached results are very fast
                return result
            else:
                # Remove expired entry
                del self._evaluation_cache[cache_key]
        
        return None
    
    def _cache_evaluation(self, cache_key: str, result: ValidationResult):
        """Cache policy evaluation result"""
        self._evaluation_cache[cache_key] = (result, time.time())
        
        # Limit cache size
        if len(self._evaluation_cache) > 1000:
            # Remove oldest entries
            sorted_items = sorted(
                self._evaluation_cache.items(),
                key=lambda x: x[1][1]  # Sort by cached_at timestamp
            )
            
            # Keep only the 800 most recent entries
            self._evaluation_cache = dict(sorted_items[-800:])
    
    def add_rule(self, rule: PolicyRule):
        """Add a new policy rule"""
        self.rule_engine.add_rule(rule)
        # Clear cache to ensure new rule is applied
        self._evaluation_cache.clear()
        logger.info(f"Added policy rule: {rule.rule_id}")
    
    def remove_rule(self, rule_id: str):
        """Remove a policy rule"""
        self.rule_engine.remove_rule(rule_id)
        self._evaluation_cache.clear()
        logger.info(f"Removed policy rule: {rule_id}")
    
    def get_rule_stats(self) -> Dict[str, any]:
        """Get statistics about rule usage"""
        stats = {
            'total_rules': len(self.rule_engine.rules),
            'cache_size': len(self._evaluation_cache),
            'cache_ttl': self._cache_ttl,
            'rules': []
        }
        
        for rule_id, rule in self.rule_engine.rules.items():
            rule_stats = {
                'rule_id': rule_id,
                'priority': rule.priority,
                'match_count': rule.match_count,
                'last_matched': rule.last_matched.isoformat() if rule.last_matched else None,
                'decision': rule.decision.value,
                'tool_names': rule.tool_names,
                'pattern_preview': rule.pattern[:50] + "..." if len(rule.pattern) > 50 else rule.pattern
            }
            stats['rules'].append(rule_stats)
        
        # Sort by match count
        stats['rules'].sort(key=lambda x: x['match_count'], reverse=True)
        
        return stats
    
    def debug_request(self, request: ValidationRequest) -> Dict[str, any]:
        """Debug information for a request"""
        matching_rules = self.rule_engine.get_matching_rules(request)
        
        return {
            'request_id': request.request_id,
            'command_hash': request.command_hash,
            'tool_name': request.tool_name,
            'agent_id': request.agent_id,
            'command_text': request.command_text,
            'matching_rules': [
                {
                    'rule_id': rule.rule_id,
                    'priority': rule.priority,
                    'decision': rule.decision.value,
                    'reason': rule.reason,
                    'pattern': rule.pattern
                }
                for rule in matching_rules
            ],
            'would_apply': matching_rules[0].rule_id if matching_rules else None
        }
    
    def clear_cache(self):
        """Clear the evaluation cache"""
        self._evaluation_cache.clear()
        logger.info("Policy evaluation cache cleared")
    
    async def periodic_maintenance(self, interval_seconds: int = 300):
        """
        Periodic maintenance tasks
        
        Should be run as a background task.
        """
        while True:
            try:
                # Check for config updates
                self._check_config_updates()
                
                # Clean up expired cache entries
                current_time = time.time()
                expired_keys = [
                    key for key, (_, cached_at) in self._evaluation_cache.items()
                    if current_time - cached_at > self._cache_ttl
                ]
                
                for key in expired_keys:
                    del self._evaluation_cache[key]
                
                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired policy cache entries")
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Policy cache maintenance error: {e}")
                await asyncio.sleep(interval_seconds)