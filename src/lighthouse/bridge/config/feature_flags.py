"""
Feature Flag Management System for FEATURE_PACK_0 Migration

Provides dynamic feature flag control for progressive rollout of elicitation protocol.
Supports percentage-based rollouts, A/B testing, and emergency rollback.
"""

import json
import logging
import random
import hashlib
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class FeatureFlagStatus(Enum):
    """Feature flag statuses"""
    DISABLED = "disabled"
    ENABLED = "enabled"
    PERCENTAGE_ROLLOUT = "percentage_rollout"
    AB_TEST = "ab_test"
    CANARY = "canary"


class FeatureFlagManager:
    """
    Manages feature flags for FEATURE_PACK_0 migration.
    
    Provides:
    - Percentage-based progressive rollouts
    - Agent-specific feature targeting
    - A/B testing capabilities
    - Emergency rollback controls
    - Audit logging of all flag changes
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize feature flag manager.
        
        Args:
            config_path: Path to feature flag configuration file
        """
        self.config_path = config_path or Path("/home/john/lighthouse/config/feature_flags.json")
        self.flags: Dict[str, Dict[str, Any]] = {}
        self.overrides: Dict[str, Dict[str, bool]] = {}  # agent_id -> flag -> override
        self.canary_agents: Set[str] = set()
        self.flag_history: List[Dict[str, Any]] = []
        
        # Load initial configuration
        self._load_configuration()
        
        # Initialize default FEATURE_PACK_0 flags
        self._initialize_default_flags()
    
    def _initialize_default_flags(self):
        """Initialize default feature flags for FEATURE_PACK_0"""
        default_flags = {
            "elicitation_enabled": {
                "status": FeatureFlagStatus.DISABLED.value,
                "description": "Enable MCP Elicitation protocol",
                "rollout_percentage": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "emergency_rollback": False,
                "dependencies": [],
                "metrics": {
                    "enabled_count": 0,
                    "disabled_count": 0,
                    "error_count": 0
                }
            },
            "elicitation_security_enhanced": {
                "status": FeatureFlagStatus.ENABLED.value,
                "description": "Enhanced security features for elicitation",
                "rollout_percentage": 100,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "dependencies": ["elicitation_enabled"]
            },
            "wait_for_messages_deprecated": {
                "status": FeatureFlagStatus.DISABLED.value,
                "description": "Mark wait_for_messages as deprecated",
                "rollout_percentage": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "dependencies": ["elicitation_enabled"]
            },
            "elicitation_performance_monitoring": {
                "status": FeatureFlagStatus.ENABLED.value,
                "description": "Enable detailed performance monitoring",
                "rollout_percentage": 100,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "elicitation_ab_test": {
                "status": FeatureFlagStatus.DISABLED.value,
                "description": "A/B test elicitation vs wait_for_messages",
                "rollout_percentage": 0,
                "test_groups": {
                    "control": "wait_for_messages",
                    "treatment": "elicitation"
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
        # Merge with existing flags
        for flag_name, flag_config in default_flags.items():
            if flag_name not in self.flags:
                self.flags[flag_name] = flag_config
                logger.info(f"Initialized feature flag: {flag_name}")
    
    def is_enabled(self, flag_name: str, agent_id: Optional[str] = None) -> bool:
        """
        Check if a feature flag is enabled for a specific agent.
        
        Args:
            flag_name: Name of the feature flag
            agent_id: Optional agent ID for agent-specific checks
            
        Returns:
            True if feature is enabled for this agent
        """
        if flag_name not in self.flags:
            logger.warning(f"Unknown feature flag: {flag_name}")
            return False
        
        flag = self.flags[flag_name]
        
        # Check emergency rollback
        if flag.get("emergency_rollback", False):
            self._record_metric(flag_name, "disabled", agent_id)
            return False
        
        # Check agent-specific override
        if agent_id and agent_id in self.overrides:
            if flag_name in self.overrides[agent_id]:
                enabled = self.overrides[agent_id][flag_name]
                self._record_metric(flag_name, "enabled" if enabled else "disabled", agent_id)
                return enabled
        
        # Check flag status
        status = FeatureFlagStatus(flag["status"])
        
        if status == FeatureFlagStatus.DISABLED:
            self._record_metric(flag_name, "disabled", agent_id)
            return False
        
        if status == FeatureFlagStatus.ENABLED:
            self._record_metric(flag_name, "enabled", agent_id)
            return True
        
        if status == FeatureFlagStatus.PERCENTAGE_ROLLOUT:
            enabled = self._check_percentage_rollout(flag, agent_id)
            self._record_metric(flag_name, "enabled" if enabled else "disabled", agent_id)
            return enabled
        
        if status == FeatureFlagStatus.AB_TEST:
            enabled = self._check_ab_test(flag, agent_id)
            self._record_metric(flag_name, "enabled" if enabled else "disabled", agent_id)
            return enabled
        
        if status == FeatureFlagStatus.CANARY:
            enabled = agent_id in self.canary_agents if agent_id else False
            self._record_metric(flag_name, "enabled" if enabled else "disabled", agent_id)
            return enabled
        
        self._record_metric(flag_name, "disabled", agent_id)
        return False
    
    def set_rollout_percentage(self, flag_name: str, percentage: int):
        """
        Set rollout percentage for a feature flag.
        
        Args:
            flag_name: Name of the feature flag
            percentage: Rollout percentage (0-100)
        """
        if flag_name not in self.flags:
            raise ValueError(f"Unknown feature flag: {flag_name}")
        
        if not 0 <= percentage <= 100:
            raise ValueError(f"Invalid percentage: {percentage}")
        
        old_percentage = self.flags[flag_name].get("rollout_percentage", 0)
        
        self.flags[flag_name]["rollout_percentage"] = percentage
        self.flags[flag_name]["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        if percentage == 0:
            self.flags[flag_name]["status"] = FeatureFlagStatus.DISABLED.value
        elif percentage == 100:
            self.flags[flag_name]["status"] = FeatureFlagStatus.ENABLED.value
        else:
            self.flags[flag_name]["status"] = FeatureFlagStatus.PERCENTAGE_ROLLOUT.value
        
        # Record change in history
        self._record_history({
            "action": "set_rollout_percentage",
            "flag": flag_name,
            "old_percentage": old_percentage,
            "new_percentage": percentage,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        self._save_configuration()
        logger.info(f"Set {flag_name} rollout to {percentage}% (was {old_percentage}%)")
    
    def enable_canary(self, flag_name: str, agent_ids: List[str]):
        """
        Enable canary deployment for specific agents.
        
        Args:
            flag_name: Name of the feature flag
            agent_ids: List of agent IDs for canary deployment
        """
        if flag_name not in self.flags:
            raise ValueError(f"Unknown feature flag: {flag_name}")
        
        self.canary_agents.update(agent_ids)
        self.flags[flag_name]["status"] = FeatureFlagStatus.CANARY.value
        self.flags[flag_name]["canary_agents"] = list(self.canary_agents)
        self.flags[flag_name]["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        self._record_history({
            "action": "enable_canary",
            "flag": flag_name,
            "agents": agent_ids,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        self._save_configuration()
        logger.info(f"Enabled canary for {flag_name} with {len(agent_ids)} agents")
    
    def emergency_rollback(self, flag_name: str):
        """
        Trigger emergency rollback for a feature flag.
        
        Args:
            flag_name: Name of the feature flag to rollback
        """
        if flag_name not in self.flags:
            raise ValueError(f"Unknown feature flag: {flag_name}")
        
        self.flags[flag_name]["emergency_rollback"] = True
        self.flags[flag_name]["status"] = FeatureFlagStatus.DISABLED.value
        self.flags[flag_name]["rollback_at"] = datetime.now(timezone.utc).isoformat()
        
        self._record_history({
            "action": "emergency_rollback",
            "flag": flag_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        self._save_configuration()
        logger.critical(f"EMERGENCY ROLLBACK triggered for {flag_name}")
    
    def clear_rollback(self, flag_name: str):
        """Clear emergency rollback status."""
        if flag_name in self.flags:
            self.flags[flag_name]["emergency_rollback"] = False
            self.flags[flag_name]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_configuration()
            logger.info(f"Cleared emergency rollback for {flag_name}")
    
    def get_metrics(self, flag_name: Optional[str] = None) -> Dict[str, Any]:
        """Get metrics for feature flags."""
        if flag_name:
            if flag_name in self.flags:
                return self.flags[flag_name].get("metrics", {})
            return {}
        
        # Return all metrics
        metrics = {}
        for name, flag in self.flags.items():
            metrics[name] = flag.get("metrics", {})
        return metrics
    
    def _check_percentage_rollout(self, flag: Dict[str, Any], agent_id: Optional[str]) -> bool:
        """Check if agent falls within rollout percentage."""
        percentage = flag.get("rollout_percentage", 0)
        
        if not agent_id:
            # No agent ID, use random selection
            return random.randint(1, 100) <= percentage
        
        # Use consistent hashing for deterministic rollout
        hash_value = int(hashlib.md5(agent_id.encode()).hexdigest(), 16)
        return (hash_value % 100) < percentage
    
    def _check_ab_test(self, flag: Dict[str, Any], agent_id: Optional[str]) -> bool:
        """Check if agent is in treatment group for A/B test."""
        if not agent_id:
            return False
        
        # Use consistent hashing for deterministic group assignment
        hash_value = int(hashlib.md5(agent_id.encode()).hexdigest(), 16)
        return (hash_value % 2) == 1  # 50/50 split
    
    def _record_metric(self, flag_name: str, result: str, agent_id: Optional[str]):
        """Record metric for feature flag usage."""
        if flag_name in self.flags:
            metrics = self.flags[flag_name].setdefault("metrics", {})
            key = f"{result}_count"
            metrics[key] = metrics.get(key, 0) + 1
    
    def _record_history(self, entry: Dict[str, Any]):
        """Record feature flag change history."""
        self.flag_history.append(entry)
        
        # Keep only last 1000 entries
        if len(self.flag_history) > 1000:
            self.flag_history = self.flag_history[-1000:]
    
    def _load_configuration(self):
        """Load feature flag configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    self.flags = data.get("flags", {})
                    self.canary_agents = set(data.get("canary_agents", []))
                    self.flag_history = data.get("history", [])
                    logger.info(f"Loaded feature flags from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load feature flags: {e}")
    
    def _save_configuration(self):
        """Save feature flag configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "flags": self.flags,
                "canary_agents": list(self.canary_agents),
                "history": self.flag_history[-100:],  # Keep last 100 history entries
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved feature flags to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save feature flags: {e}")


# Global instance
_feature_flag_manager: Optional[FeatureFlagManager] = None


def get_feature_flag_manager() -> FeatureFlagManager:
    """Get or create the global feature flag manager instance."""
    global _feature_flag_manager
    if _feature_flag_manager is None:
        _feature_flag_manager = FeatureFlagManager()
    return _feature_flag_manager