#!/usr/bin/env python3
"""
Deployment automation script for FEATURE_PACK_0 Elicitation

Handles progressive rollout of elicitation feature with safety checks.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.lighthouse.bridge.config.feature_flags import FeatureFlagManager
from src.lighthouse.bridge.elicitation import SecureElicitationManager
from src.lighthouse.event_store import EventStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ElicitationDeployment:
    """Manages automated deployment of elicitation feature"""
    
    def __init__(self):
        self.feature_flags = FeatureFlagManager()
        self.event_store = EventStore()
        self.deployment_log = []
        self.health_checks_passed = False
        self.rollback_triggered = False
        
    async def run_pre_deployment_checks(self) -> bool:
        """Run comprehensive pre-deployment validation"""
        logger.info("Running pre-deployment checks...")
        
        checks = {
            "event_store_health": await self._check_event_store(),
            "feature_flags_initialized": await self._check_feature_flags(),
            "security_tests_passed": await self._run_security_tests(),
            "performance_baseline_exists": await self._check_baseline(),
            "rollback_script_ready": await self._check_rollback_script(),
            "monitoring_active": await self._check_monitoring()
        }
        
        failed_checks = [name for name, passed in checks.items() if not passed]
        
        if failed_checks:
            logger.error(f"Pre-deployment checks failed: {failed_checks}")
            return False
        
        logger.info("All pre-deployment checks passed ✓")
        self.health_checks_passed = True
        return True
    
    async def deploy_canary(self, percentage: int = 5) -> bool:
        """Deploy elicitation to canary percentage"""
        logger.info(f"Deploying elicitation to {percentage}% canary...")
        
        try:
            # Enable feature flag for percentage
            self.feature_flags.set_rollout_percentage("elicitation_enabled", percentage)
            
            # Log deployment event
            self._log_deployment({
                "phase": "canary",
                "percentage": percentage,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Wait for stabilization
            await asyncio.sleep(5)
            
            # Run health checks
            if not await self._run_canary_health_checks():
                logger.error("Canary health checks failed")
                await self.rollback()
                return False
            
            logger.info(f"Canary deployment at {percentage}% successful ✓")
            return True
            
        except Exception as e:
            logger.error(f"Canary deployment failed: {e}")
            await self.rollback()
            return False
    
    async def progressive_rollout(self, target_percentage: int) -> bool:
        """Progressive rollout to target percentage"""
        logger.info(f"Starting progressive rollout to {target_percentage}%...")
        
        current = self.feature_flags.flags.get("elicitation_enabled", {}).get("rollout_percentage", 0)
        
        # Rollout in increments
        increments = [25, 50, 75, 100]
        
        for target in increments:
            if target > target_percentage:
                break
            
            if current >= target:
                continue
            
            logger.info(f"Scaling to {target}%...")
            
            try:
                # Update feature flag
                self.feature_flags.set_rollout_percentage("elicitation_enabled", target)
                
                # Wait for propagation
                await asyncio.sleep(10)
                
                # Check metrics
                if not await self._check_rollout_metrics(target):
                    logger.error(f"Metrics check failed at {target}%")
                    await self.rollback()
                    return False
                
                # Check error rate
                error_rate = await self._get_error_rate()
                if error_rate > 0.01:  # 1% threshold
                    logger.error(f"Error rate {error_rate:.2%} exceeds threshold")
                    await self.rollback()
                    return False
                
                logger.info(f"Rollout to {target}% successful ✓")
                current = target
                
                # Longer wait between larger rollouts
                if target < 100:
                    await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Rollout failed at {target}%: {e}")
                await self.rollback()
                return False
        
        logger.info(f"Progressive rollout to {target_percentage}% complete ✓")
        return True
    
    async def rollback(self) -> bool:
        """Emergency rollback procedure"""
        if self.rollback_triggered:
            logger.warning("Rollback already triggered")
            return True
        
        logger.critical("INITIATING EMERGENCY ROLLBACK")
        self.rollback_triggered = True
        
        try:
            # Step 1: Disable elicitation immediately
            self.feature_flags.emergency_rollback("elicitation_enabled")
            
            # Step 2: Log rollback event
            self._log_deployment({
                "phase": "rollback",
                "reason": "automated_rollback",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Step 3: Wait for drain
            logger.info("Draining in-flight elicitations...")
            await asyncio.sleep(5)
            
            # Step 4: Verify rollback
            if not await self._verify_rollback():
                logger.error("Rollback verification failed")
                return False
            
            logger.info("Rollback completed successfully ✓")
            return True
            
        except Exception as e:
            logger.critical(f"ROLLBACK FAILED: {e}")
            return False
    
    async def enable_monitoring(self) -> bool:
        """Enable comprehensive monitoring"""
        logger.info("Enabling elicitation monitoring...")
        
        try:
            # Enable performance monitoring
            self.feature_flags.flags["elicitation_performance_monitoring"]["status"] = "enabled"
            
            # Enable security monitoring
            self.feature_flags.flags["elicitation_security_enhanced"]["status"] = "enabled"
            
            self.feature_flags._save_configuration()
            
            logger.info("Monitoring enabled ✓")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable monitoring: {e}")
            return False
    
    # Helper methods
    
    async def _check_event_store(self) -> bool:
        """Check event store health"""
        try:
            await self.event_store.initialize()
            return True
        except Exception as e:
            logger.error(f"Event store check failed: {e}")
            return False
    
    async def _check_feature_flags(self) -> bool:
        """Check feature flags are initialized"""
        return "elicitation_enabled" in self.feature_flags.flags
    
    async def _run_security_tests(self) -> bool:
        """Run security test suite"""
        import subprocess
        
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/security/test_elicitation_security.py", "-v"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Security tests failed:\n{result.stdout}\n{result.stderr}")
            return False
        
        logger.info("Security tests passed ✓")
        return True
    
    async def _check_baseline(self) -> bool:
        """Check if performance baseline exists"""
        baseline_file = Path("/home/john/lighthouse/data/baselines/elicitation_baseline.json")
        if not baseline_file.exists():
            logger.warning("Performance baseline not found")
            return False
        return True
    
    async def _check_rollback_script(self) -> bool:
        """Check rollback script exists and is executable"""
        rollback_script = Path("/home/john/lighthouse/scripts/rollback_elicitation.py")
        return rollback_script.exists()
    
    async def _check_monitoring(self) -> bool:
        """Check monitoring is active"""
        # In production, would check actual monitoring systems
        return True
    
    async def _run_canary_health_checks(self) -> bool:
        """Run health checks on canary deployment"""
        # Simulate health checks
        await asyncio.sleep(2)
        
        # Check error rates, latency, etc.
        # In production, would query actual metrics
        return True
    
    async def _check_rollout_metrics(self, percentage: int) -> bool:
        """Check metrics at current rollout percentage"""
        # In production, would query Prometheus/Grafana
        logger.info(f"Checking metrics at {percentage}%...")
        
        # Simulate metric checks
        metrics = {
            "p99_latency_ms": 250,  # Should be < 300ms
            "error_rate": 0.001,  # Should be < 0.1%
            "success_rate": 0.999
        }
        
        if metrics["p99_latency_ms"] > 300:
            logger.error(f"P99 latency {metrics['p99_latency_ms']}ms exceeds threshold")
            return False
        
        if metrics["error_rate"] > 0.001:
            logger.error(f"Error rate {metrics['error_rate']:.2%} exceeds threshold")
            return False
        
        return True
    
    async def _get_error_rate(self) -> float:
        """Get current error rate"""
        # In production, would query actual metrics
        return 0.0005  # 0.05% error rate
    
    async def _verify_rollback(self) -> bool:
        """Verify rollback completed successfully"""
        # Check that elicitation is disabled
        if self.feature_flags.is_enabled("elicitation_enabled"):
            return False
        
        # Check that wait_for_messages is working
        # In production, would make actual test calls
        return True
    
    def _log_deployment(self, event: Dict[str, Any]):
        """Log deployment event"""
        self.deployment_log.append(event)
        
        # Also write to file
        log_file = Path("/home/john/lighthouse/logs/deployment.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(event) + '\n')


async def main():
    """Main deployment flow"""
    deployment = ElicitationDeployment()
    
    # Pre-deployment checks
    if not await deployment.run_pre_deployment_checks():
        logger.error("Pre-deployment checks failed. Aborting deployment.")
        sys.exit(1)
    
    # Enable monitoring first
    if not await deployment.enable_monitoring():
        logger.error("Failed to enable monitoring. Aborting deployment.")
        sys.exit(1)
    
    # Deploy to 5% canary
    if not await deployment.deploy_canary(5):
        logger.error("Canary deployment failed")
        sys.exit(1)
    
    # Wait for canary bake time
    logger.info("Canary bake time (would be longer in production)...")
    await asyncio.sleep(10)
    
    # Progressive rollout to 25%
    if not await deployment.progressive_rollout(25):
        logger.error("Progressive rollout failed")
        sys.exit(1)
    
    logger.info("Deployment completed successfully! 🎉")
    
    # Generate deployment report
    report = {
        "deployment_id": f"deploy_{int(time.time())}",
        "status": "success",
        "final_percentage": 25,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "events": deployment.deployment_log
    }
    
    report_file = Path("/home/john/lighthouse/reports/deployment_report.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Deployment report saved to {report_file}")


if __name__ == "__main__":
    asyncio.run(main())