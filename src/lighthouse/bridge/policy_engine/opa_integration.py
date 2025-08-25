"""
OPA (Open Policy Agent) Policy Engine Integration

Provides centralized policy management and evaluation for the Lighthouse system
using Open Policy Agent for flexible, declarative policy enforcement.

Part of Plan Charlie Phase 2 implementation.
"""

import asyncio
import json
import logging
import hashlib
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set
import aiohttp
import os
import yaml

logger = logging.getLogger(__name__)


class PolicyDecision(Enum):
    """Policy evaluation decision."""
    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


class PolicyType(Enum):
    """Types of policies supported."""
    COMMAND_VALIDATION = "command_validation"
    FILE_ACCESS = "file_access"
    NETWORK_ACCESS = "network_access"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMITING = "rate_limiting"
    SECURITY_COMPLIANCE = "security_compliance"
    DATA_GOVERNANCE = "data_governance"


class PolicyScope(Enum):
    """Scope of policy enforcement."""
    SYSTEM = "system"
    COMPONENT = "component"
    USER = "user"
    SESSION = "session"
    REQUEST = "request"


@dataclass
class PolicyQuery:
    """Represents a policy evaluation query."""
    query_id: str
    policy_type: PolicyType
    policy_name: str
    input_data: Dict[str, Any]
    context: Dict[str, Any]
    scope: PolicyScope
    timestamp: datetime
    timeout_seconds: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['policy_type'] = self.policy_type.value
        data['scope'] = self.scope.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class PolicyResult:
    """Result of policy evaluation."""
    query_id: str
    policy_name: str
    decision: PolicyDecision
    allowed: bool
    reason: str
    conditions: List[str]
    metadata: Dict[str, Any]
    evaluation_time_ms: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['decision'] = self.decision.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class PolicyDefinition:
    """Represents a policy definition."""
    name: str
    policy_type: PolicyType
    scope: PolicyScope
    rego_code: str
    description: str
    version: str
    enabled: bool
    created_at: datetime
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['policy_type'] = self.policy_type.value
        data['scope'] = self.scope.value
        data['created_at'] = self.created_at.isoformat()
        return data


class OPAClient:
    """Client for communicating with Open Policy Agent server."""
    
    def __init__(self, opa_url: str = "http://localhost:8181"):
        """
        Initialize OPA client.
        
        Args:
            opa_url: URL of OPA server
        """
        self.opa_url = opa_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def health_check(self) -> bool:
        """Check if OPA server is healthy."""
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.opa_url}/health") as response:
                return response.status == 200
                
        except Exception as e:
            logger.warning(f"OPA health check failed: {str(e)}")
            return False
    
    async def create_policy(self, policy: PolicyDefinition) -> bool:
        """
        Create or update a policy in OPA.
        
        Args:
            policy: Policy definition to create
            
        Returns:
            Success status
        """
        try:
            session = await self._get_session()
            
            policy_path = f"policies/{policy.name}"
            url = f"{self.opa_url}/v1/policies/{policy_path}"
            
            headers = {"Content-Type": "text/plain"}
            
            async with session.put(url, data=policy.rego_code, headers=headers) as response:
                if response.status in [200, 204]:
                    logger.info(f"Policy {policy.name} created/updated successfully")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create policy {policy.name}: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error creating policy {policy.name}: {str(e)}")
            return False
    
    async def delete_policy(self, policy_name: str) -> bool:
        """
        Delete a policy from OPA.
        
        Args:
            policy_name: Name of policy to delete
            
        Returns:
            Success status
        """
        try:
            session = await self._get_session()
            
            policy_path = f"policies/{policy_name}"
            url = f"{self.opa_url}/v1/policies/{policy_path}"
            
            async with session.delete(url) as response:
                if response.status in [200, 204]:
                    logger.info(f"Policy {policy_name} deleted successfully")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to delete policy {policy_name}: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error deleting policy {policy_name}: {str(e)}")
            return False
    
    async def list_policies(self) -> List[str]:
        """
        List all policies in OPA.
        
        Returns:
            List of policy names
        """
        try:
            session = await self._get_session()
            
            url = f"{self.opa_url}/v1/policies"
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return list(data.get("result", {}).keys())
                else:
                    logger.error(f"Failed to list policies: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error listing policies: {str(e)}")
            return []
    
    async def evaluate_policy(self, policy_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a policy with given input.
        
        Args:
            policy_name: Name of policy to evaluate
            input_data: Input data for policy evaluation
            
        Returns:
            Policy evaluation result
        """
        try:
            session = await self._get_session()
            
            url = f"{self.opa_url}/v1/data/policies/{policy_name}"
            
            payload = {"input": input_data}
            headers = {"Content-Type": "application/json"}
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("result", {})
                else:
                    error_text = await response.text()
                    logger.error(f"Policy evaluation failed for {policy_name}: {error_text}")
                    return {"error": f"Evaluation failed: {error_text}"}
                    
        except Exception as e:
            logger.error(f"Error evaluating policy {policy_name}: {str(e)}")
            return {"error": str(e)}
    
    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None


class PolicyEngine:
    """Main policy engine for managing and evaluating policies."""
    
    def __init__(self, opa_url: str = None):
        """
        Initialize policy engine.
        
        Args:
            opa_url: OPA server URL (defaults to environment variable or localhost)
        """
        self.opa_url = opa_url or os.getenv("LIGHTHOUSE_OPA_URL", "http://localhost:8181")
        self.opa_client = OPAClient(self.opa_url)
        self.policies: Dict[str, PolicyDefinition] = {}
        self.policy_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl_seconds = 300  # 5 minutes
        
        # Load default policies
        self._load_default_policies()
    
    def _load_default_policies(self):
        """Load default security policies."""
        
        # Command validation policy
        command_policy = PolicyDefinition(
            name="command_validation",
            policy_type=PolicyType.COMMAND_VALIDATION,
            scope=PolicyScope.SYSTEM,
            description="Validates command execution requests for security",
            version="1.0.0",
            enabled=True,
            created_at=datetime.utcnow(),
            rego_code="""
package policies.command_validation

import rego.v1

# Default decision is deny
default allow := false
default dangerous := false

# Dangerous command patterns
dangerous_patterns := [
    "rm -rf",
    "sudo rm",
    "chmod 777",
    "dd if=",
    "mkfs",
    "fdisk",
    "> /dev/",
    "curl | bash",
    "wget | sh"
]

# Dangerous system paths
dangerous_paths := [
    "/etc/passwd",
    "/etc/shadow",
    "/boot/",
    "/sys/",
    "/proc/",
    "/dev/"
]

# Check for dangerous patterns
dangerous if {
    some pattern in dangerous_patterns
    contains(input.command, pattern)
}

# Check for dangerous paths
dangerous if {
    some path in dangerous_paths
    contains(input.command, path)
}

# Allow safe commands
allow if {
    input.tool == "Read"
    not dangerous
}

allow if {
    input.tool == "Glob"
    not dangerous
}

allow if {
    input.tool == "Grep"
    not dangerous
}

allow if {
    input.tool == "LS"
    not dangerous
}

# Allow bash commands if not dangerous and user is authorized
allow if {
    input.tool == "Bash"
    not dangerous
    input.user.authorized == true
}

# Decision and reason
decision := "allow" if allow
decision := "deny" if not allow

reason := "Command allowed - no security issues detected" if allow
reason := "Command blocked - dangerous operation detected" if not allow
"""
        )
        self.policies["command_validation"] = command_policy
        
        # File access policy
        file_access_policy = PolicyDefinition(
            name="file_access",
            policy_type=PolicyType.FILE_ACCESS,
            scope=PolicyScope.COMPONENT,
            description="Controls file system access permissions",
            version="1.0.0",
            enabled=True,
            created_at=datetime.utcnow(),
            rego_code="""
package policies.file_access

import rego.v1

default allow := false

# Allowed directories for different components
allowed_directories := {
    "lighthouse": ["/tmp/lighthouse", "./data", "./logs"],
    "fuse": ["/mnt/lighthouse"],
    "event_store": ["./data/events", "/tmp/lighthouse/events"],
    "general": ["./", "/tmp"]
}

# System directories that are never allowed
forbidden_directories := [
    "/etc/", "/usr/", "/var/", "/boot/", 
    "/sys/", "/proc/", "/dev/", "/root/"
]

# Check if path is in allowed directories for component
path_allowed if {
    component_dirs := allowed_directories[input.component]
    some allowed_dir in component_dirs
    startswith(input.path, allowed_dir)
}

# Check if path is forbidden
path_forbidden if {
    some forbidden_dir in forbidden_directories
    startswith(input.path, forbidden_dir)
}

# Allow access if path is allowed and not forbidden
allow if {
    path_allowed
    not path_forbidden
}

decision := "allow" if allow
decision := "deny" if not allow

reason := "File access allowed" if allow
reason := "File access denied - unauthorized path" if not allow
"""
        )
        self.policies["file_access"] = file_access_policy
        
        # Rate limiting policy
        rate_limit_policy = PolicyDefinition(
            name="rate_limiting",
            policy_type=PolicyType.RATE_LIMITING,
            scope=PolicyScope.USER,
            description="Controls request rate limits per user/component",
            version="1.0.0",
            enabled=True,
            created_at=datetime.utcnow(),
            rego_code="""
package policies.rate_limiting

import rego.v1

default allow := false

# Rate limits per component/user type
rate_limits := {
    "agent": {"requests_per_minute": 100, "burst": 20},
    "user": {"requests_per_minute": 60, "burst": 10},
    "system": {"requests_per_minute": 1000, "burst": 50}
}

# Allow if within rate limits
allow if {
    limits := rate_limits[input.user_type]
    input.current_rate <= limits.requests_per_minute
    input.current_burst <= limits.burst
}

decision := "allow" if allow
decision := "deny" if not allow

reason := "Request allowed - within rate limits" if allow
reason := "Request denied - rate limit exceeded" if not allow

# Include current limits in response
limits := rate_limits[input.user_type]
"""
        )
        self.policies["rate_limiting"] = rate_limit_policy
    
    async def initialize(self) -> bool:
        """
        Initialize the policy engine and deploy policies.
        
        Returns:
            Success status
        """
        logger.info("Initializing OPA Policy Engine")
        
        # Check OPA server health
        if not await self.opa_client.health_check():
            logger.error("OPA server is not healthy - policies may not function correctly")
            return False
        
        # Deploy default policies
        success_count = 0
        for policy_name, policy in self.policies.items():
            if await self.opa_client.create_policy(policy):
                success_count += 1
            else:
                logger.error(f"Failed to deploy policy: {policy_name}")
        
        logger.info(f"Deployed {success_count}/{len(self.policies)} policies")
        return success_count == len(self.policies)
    
    async def evaluate_policy(self, query: PolicyQuery) -> PolicyResult:
        """
        Evaluate a policy query.
        
        Args:
            query: Policy query to evaluate
            
        Returns:
            Policy evaluation result
        """
        start_time = time.time()
        
        logger.debug(f"Evaluating policy {query.policy_name} for query {query.query_id}")
        
        # Check cache first
        cache_key = self._get_cache_key(query)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            logger.debug(f"Using cached result for query {query.query_id}")
            return cached_result
        
        try:
            # Evaluate policy with OPA
            opa_result = await self.opa_client.evaluate_policy(query.policy_name, query.input_data)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Parse OPA result
            result = self._parse_opa_result(query, opa_result, processing_time)
            
            # Cache result
            self._cache_result(cache_key, result)
            
            logger.debug(f"Policy evaluation complete for query {query.query_id}: {result.decision.value}")
            return result
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"Policy evaluation failed for query {query.query_id}: {str(e)}")
            
            return PolicyResult(
                query_id=query.query_id,
                policy_name=query.policy_name,
                decision=PolicyDecision.DENY,
                allowed=False,
                reason=f"Evaluation error: {str(e)}",
                conditions=[],
                metadata={"error": str(e)},
                evaluation_time_ms=processing_time,
                timestamp=datetime.utcnow()
            )
    
    def _parse_opa_result(self, query: PolicyQuery, opa_result: Dict[str, Any], 
                         processing_time: float) -> PolicyResult:
        """Parse OPA evaluation result."""
        
        # Handle errors
        if "error" in opa_result:
            return PolicyResult(
                query_id=query.query_id,
                policy_name=query.policy_name,
                decision=PolicyDecision.UNKNOWN,
                allowed=False,
                reason=f"Policy error: {opa_result['error']}",
                conditions=[],
                metadata=opa_result,
                evaluation_time_ms=processing_time,
                timestamp=datetime.utcnow()
            )
        
        # Extract decision information
        allowed = opa_result.get("allow", False)
        decision_str = opa_result.get("decision", "unknown")
        reason = opa_result.get("reason", "No reason provided")
        conditions = opa_result.get("conditions", [])
        
        # Map decision string to enum
        decision_map = {
            "allow": PolicyDecision.ALLOW,
            "deny": PolicyDecision.DENY,
            "conditional": PolicyDecision.CONDITIONAL,
            "unknown": PolicyDecision.UNKNOWN
        }
        decision = decision_map.get(decision_str.lower(), PolicyDecision.UNKNOWN)
        
        return PolicyResult(
            query_id=query.query_id,
            policy_name=query.policy_name,
            decision=decision,
            allowed=allowed,
            reason=reason,
            conditions=conditions if isinstance(conditions, list) else [],
            metadata=opa_result,
            evaluation_time_ms=processing_time,
            timestamp=datetime.utcnow()
        )
    
    def _get_cache_key(self, query: PolicyQuery) -> str:
        """Generate cache key for query."""
        key_data = f"{query.policy_name}:{json.dumps(query.input_data, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[PolicyResult]:
        """Get cached policy result."""
        if cache_key in self.policy_cache:
            cache_entry = self.policy_cache[cache_key]
            
            # Check if cache entry is still valid
            if time.time() - cache_entry["timestamp"] < self.cache_ttl_seconds:
                return cache_entry["result"]
            else:
                # Remove expired entry
                del self.policy_cache[cache_key]
        
        return None
    
    def _cache_result(self, cache_key: str, result: PolicyResult):
        """Cache policy evaluation result."""
        self.policy_cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }
        
        # Simple cache cleanup - remove oldest entries if cache gets too large
        if len(self.policy_cache) > 1000:
            # Remove 20% of oldest entries
            sorted_entries = sorted(
                self.policy_cache.items(),
                key=lambda x: x[1]["timestamp"]
            )
            for key, _ in sorted_entries[:200]:
                del self.policy_cache[key]
    
    async def add_policy(self, policy: PolicyDefinition) -> bool:
        """
        Add a new policy to the engine.
        
        Args:
            policy: Policy definition to add
            
        Returns:
            Success status
        """
        success = await self.opa_client.create_policy(policy)
        if success:
            self.policies[policy.name] = policy
            logger.info(f"Added policy: {policy.name}")
        return success
    
    async def remove_policy(self, policy_name: str) -> bool:
        """
        Remove a policy from the engine.
        
        Args:
            policy_name: Name of policy to remove
            
        Returns:
            Success status
        """
        success = await self.opa_client.delete_policy(policy_name)
        if success:
            self.policies.pop(policy_name, None)
            logger.info(f"Removed policy: {policy_name}")
        return success
    
    async def list_policies(self) -> List[str]:
        """List all available policies."""
        return list(self.policies.keys())
    
    def get_policy(self, policy_name: str) -> Optional[PolicyDefinition]:
        """Get policy definition by name."""
        return self.policies.get(policy_name)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check policy engine health."""
        opa_healthy = await self.opa_client.health_check()
        
        return {
            "opa_server": opa_healthy,
            "policies_loaded": len(self.policies),
            "cache_entries": len(self.policy_cache),
            "status": "healthy" if opa_healthy else "degraded"
        }
    
    async def close(self):
        """Close policy engine and cleanup resources."""
        await self.opa_client.close()
        self.policy_cache.clear()


# Global policy engine instance
_global_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Get global policy engine instance."""
    global _global_policy_engine
    if _global_policy_engine is None:
        _global_policy_engine = PolicyEngine()
    return _global_policy_engine


async def evaluate_command_policy(tool: str, command: str, user_context: Dict[str, Any]) -> PolicyResult:
    """Convenience function to evaluate command policy."""
    engine = get_policy_engine()
    
    query = PolicyQuery(
        query_id=hashlib.md5(f"{tool}:{command}:{time.time()}".encode()).hexdigest()[:16],
        policy_type=PolicyType.COMMAND_VALIDATION,
        policy_name="command_validation",
        input_data={
            "tool": tool,
            "command": command,
            "user": user_context
        },
        context={},
        scope=PolicyScope.SYSTEM,
        timestamp=datetime.utcnow()
    )
    
    return await engine.evaluate_policy(query)


async def evaluate_file_access_policy(component: str, path: str, operation: str) -> PolicyResult:
    """Convenience function to evaluate file access policy."""
    engine = get_policy_engine()
    
    query = PolicyQuery(
        query_id=hashlib.md5(f"{component}:{path}:{operation}:{time.time()}".encode()).hexdigest()[:16],
        policy_type=PolicyType.FILE_ACCESS,
        policy_name="file_access",
        input_data={
            "component": component,
            "path": path,
            "operation": operation
        },
        context={},
        scope=PolicyScope.COMPONENT,
        timestamp=datetime.utcnow()
    )
    
    return await engine.evaluate_policy(query)