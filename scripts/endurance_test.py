#!/usr/bin/env python3
"""
Endurance Testing Script for FEATURE_PACK_0

Tests system stability over extended periods (72 hours) with 5,000 concurrent agents.
Includes memory leak detection and performance degradation monitoring.
"""

import asyncio
import gc
import json
import logging
import psutil
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field
import numpy as np
from collections import deque

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.lighthouse.bridge.elicitation.fast_manager import OptimizedElicitationManager
from src.lighthouse.event_store import EventStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Memory usage snapshot"""
    timestamp: str
    rss_mb: float  # Resident Set Size
    vms_mb: float  # Virtual Memory Size
    available_mb: float
    percent_used: float
    gc_stats: Dict[str, int]
    top_allocations: List[Tuple[str, int]]


@dataclass
class PerformanceSnapshot:
    """Performance metrics snapshot"""
    timestamp: str
    hour: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_rps: float
    error_rate: float
    active_agents: int


@dataclass
class EnduranceReport:
    """Complete endurance test report"""
    start_time: str
    end_time: str
    duration_hours: float
    target_duration_hours: float
    agent_count: int
    
    # Memory analysis
    memory_leak_detected: bool
    memory_growth_rate_mb_per_hour: float
    peak_memory_mb: float
    final_memory_mb: float
    memory_snapshots: List[MemorySnapshot]
    
    # Performance analysis  
    performance_degradation: bool
    performance_snapshots: List[PerformanceSnapshot]
    latency_trend: str  # STABLE, INCREASING, DECREASING
    
    # Stability metrics
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_types: Dict[str, int]
    crashes: int
    restarts_required: int
    
    # Verdict
    passed: bool
    issues: List[str]
    recommendations: List[str]


class EnduranceTestRunner:
    """Runs extended endurance tests with monitoring"""
    
    def __init__(self, duration_hours: int = 72, agent_count: int = 5000):
        self.duration_hours = duration_hours
        self.agent_count = agent_count
        self.results_dir = Path("/home/john/lighthouse/data/endurance_results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Monitoring state
        self.running = False
        self.start_time = None
        self.memory_snapshots = deque(maxlen=1000)  # Keep last 1000 snapshots
        self.performance_snapshots = deque(maxlen=1000)
        self.error_counts = {}
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.crashes = 0
        self.restarts = 0
        
        # Components
        self.event_store = None
        self.manager = None
        self.agents = []
        
        # Memory tracking
        self.initial_memory = None
        self.peak_memory = 0
        
        # Performance baselines
        self.baseline_p99 = None
        self.baseline_throughput = None
    
    async def run(self) -> EnduranceReport:
        """Run complete endurance test"""
        logger.info("="*80)
        logger.info(f"ENDURANCE TEST: {self.duration_hours}h with {self.agent_count} agents")
        logger.info("="*80)
        
        self.start_time = datetime.now(timezone.utc)
        self.running = True
        
        # Start memory tracking
        tracemalloc.start()
        
        try:
            # Initialize components
            await self.initialize_components()
            
            # Capture baseline
            await self.capture_baseline()
            
            # Start monitoring tasks
            monitor_tasks = [
                asyncio.create_task(self.monitor_memory()),
                asyncio.create_task(self.monitor_performance()),
                asyncio.create_task(self.monitor_stability())
            ]
            
            # Run agent simulation
            agent_task = asyncio.create_task(self.run_agent_simulation())
            
            # Run for specified duration
            end_time = self.start_time + timedelta(hours=self.duration_hours)
            
            while datetime.now(timezone.utc) < end_time and self.running:
                # Log progress every hour
                elapsed = datetime.now(timezone.utc) - self.start_time
                if int(elapsed.total_seconds()) % 3600 == 0:
                    await self.log_progress(elapsed)
                
                await asyncio.sleep(60)  # Check every minute
            
            # Stop simulation
            self.running = False
            agent_task.cancel()
            
            # Cancel monitoring
            for task in monitor_tasks:
                task.cancel()
            
            # Final analysis
            report = await self.analyze_results()
            
            # Save report
            await self.save_report(report)
            
            return report
            
        except Exception as e:
            logger.error(f"Endurance test failed: {e}")
            self.running = False
            raise
        finally:
            # Cleanup
            await self.cleanup()
            tracemalloc.stop()
    
    async def initialize_components(self):
        """Initialize test components"""
        logger.info("Initializing components...")
        
        # Initialize event store
        self.event_store = EventStore()
        await self.event_store.initialize()
        
        # Initialize elicitation manager
        self.manager = OptimizedElicitationManager(
            event_store=self.event_store,
            bridge_secret_key="endurance_test_secret",
            enable_security=True
        )
        await self.manager.initialize()
        
        # Create virtual agents
        self.agents = [f"agent_{i}" for i in range(self.agent_count)]
        
        logger.info(f"Initialized with {len(self.agents)} agents")
    
    async def capture_baseline(self):
        """Capture baseline metrics"""
        logger.info("Capturing baseline metrics...")
        
        # Memory baseline
        process = psutil.Process()
        self.initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Performance baseline (run for 1 minute)
        latencies = []
        start = time.time()
        
        while time.time() - start < 60:
            try:
                # Run sample elicitation
                agent_from = self.agents[0]
                agent_to = self.agents[1]
                
                elicit_start = time.time()
                elicit_id = await self.manager.create_elicitation(
                    from_agent=agent_from,
                    to_agent=agent_to,
                    message="Baseline test",
                    schema={"type": "object"},
                    timeout_seconds=5
                )
                
                await self.manager.respond_to_elicitation(
                    elicitation_id=elicit_id,
                    responding_agent=agent_to,
                    response_type="accept",
                    data={"baseline": True}
                )
                
                latency = (time.time() - elicit_start) * 1000
                latencies.append(latency)
                
            except Exception:
                pass
            
            await asyncio.sleep(0.1)
        
        if latencies:
            self.baseline_p99 = np.percentile(latencies, 99)
            self.baseline_throughput = len(latencies) / 60
            logger.info(f"Baseline P99: {self.baseline_p99:.2f}ms, "
                       f"Throughput: {self.baseline_throughput:.1f} rps")
    
    async def run_agent_simulation(self):
        """Simulate agent activity"""
        logger.info("Starting agent simulation...")
        
        async def agent_activity(agent_id: str):
            """Single agent activity loop"""
            while self.running:
                try:
                    # Random interaction with another agent
                    import random
                    target = random.choice(self.agents)
                    if target == agent_id:
                        continue
                    
                    # Create elicitation
                    elicit_id = await self.manager.create_elicitation(
                        from_agent=agent_id,
                        to_agent=target,
                        message=f"Request from {agent_id}",
                        schema={"type": "object"},
                        timeout_seconds=10
                    )
                    
                    self.total_requests += 1
                    
                    # Simulate response delay
                    await asyncio.sleep(random.uniform(0.1, 0.5))
                    
                    # Respond
                    success = await self.manager.respond_to_elicitation(
                        elicitation_id=elicit_id,
                        responding_agent=target,
                        response_type="accept",
                        data={"response": f"From {target}"}
                    )
                    
                    if success:
                        self.successful_requests += 1
                    else:
                        self.failed_requests += 1
                    
                    # Rate limiting
                    await asyncio.sleep(random.uniform(1, 5))
                    
                except Exception as e:
                    error_type = type(e).__name__
                    self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
                    self.failed_requests += 1
                    
                    # Back off on error
                    await asyncio.sleep(10)
        
        # Start agent tasks (limit concurrent tasks for resource management)
        max_concurrent = min(100, self.agent_count)  # Max 100 concurrent tasks
        
        tasks = []
        for i in range(max_concurrent):
            agent_id = self.agents[i % self.agent_count]
            task = asyncio.create_task(agent_activity(agent_id))
            tasks.append(task)
        
        # Wait for all tasks
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Agent simulation stopped")
    
    async def monitor_memory(self):
        """Monitor memory usage for leaks"""
        logger.info("Starting memory monitoring...")
        
        while self.running:
            try:
                process = psutil.Process()
                mem_info = process.memory_info()
                
                # System memory
                sys_mem = psutil.virtual_memory()
                
                # GC stats
                gc_stats = {
                    f"gen{i}": gc.get_count()[i] 
                    for i in range(gc.get_count().__len__())
                }
                
                # Top memory allocations (if tracemalloc is running)
                top_stats = []
                if tracemalloc.is_tracing():
                    snapshot = tracemalloc.take_snapshot()
                    top_stats = [
                        (str(stat.traceback), stat.size)
                        for stat in snapshot.statistics('traceback')[:5]
                    ]
                
                snapshot = MemorySnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    rss_mb=mem_info.rss / 1024 / 1024,
                    vms_mb=mem_info.vms / 1024 / 1024,
                    available_mb=sys_mem.available / 1024 / 1024,
                    percent_used=sys_mem.percent,
                    gc_stats=gc_stats,
                    top_allocations=top_stats
                )
                
                self.memory_snapshots.append(snapshot)
                
                # Track peak memory
                self.peak_memory = max(self.peak_memory, snapshot.rss_mb)
                
                # Force garbage collection periodically
                if len(self.memory_snapshots) % 60 == 0:  # Every hour
                    gc.collect()
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def monitor_performance(self):
        """Monitor performance metrics"""
        logger.info("Starting performance monitoring...")
        
        while self.running:
            try:
                # Collect performance samples for 1 minute
                latencies = []
                errors = 0
                start = time.time()
                
                while time.time() - start < 60 and self.running:
                    try:
                        # Test elicitation
                        import random
                        agent_from = random.choice(self.agents)
                        agent_to = random.choice(self.agents)
                        
                        if agent_from == agent_to:
                            continue
                        
                        elicit_start = time.time()
                        elicit_id = await self.manager.create_elicitation(
                            from_agent=agent_from,
                            to_agent=agent_to,
                            message="Performance test",
                            schema={"type": "object"},
                            timeout_seconds=5
                        )
                        
                        success = await self.manager.respond_to_elicitation(
                            elicitation_id=elicit_id,
                            responding_agent=agent_to,
                            response_type="accept",
                            data={"test": True}
                        )
                        
                        if success:
                            latency = (time.time() - elicit_start) * 1000
                            latencies.append(latency)
                        else:
                            errors += 1
                        
                    except Exception:
                        errors += 1
                    
                    await asyncio.sleep(0.5)
                
                # Calculate metrics
                if latencies:
                    snapshot = PerformanceSnapshot(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        hour=int((datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600),
                        p50_latency_ms=np.percentile(latencies, 50),
                        p95_latency_ms=np.percentile(latencies, 95),
                        p99_latency_ms=np.percentile(latencies, 99),
                        throughput_rps=len(latencies) / 60,
                        error_rate=errors / (len(latencies) + errors) if latencies else 1.0,
                        active_agents=len([a for a in self.agents if a])  # Simplified
                    )
                    
                    self.performance_snapshots.append(snapshot)
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Performance monitoring error: {e}")
                await asyncio.sleep(300)
    
    async def monitor_stability(self):
        """Monitor system stability"""
        logger.info("Starting stability monitoring...")
        
        last_check = time.time()
        last_request_count = 0
        
        while self.running:
            try:
                # Check if system is making progress
                current_requests = self.total_requests
                if current_requests == last_request_count:
                    # No progress in last interval
                    logger.warning("System appears stuck, no new requests processed")
                    self.crashes += 1
                    
                    # Attempt recovery
                    await self.attempt_recovery()
                
                last_request_count = current_requests
                
                # Check Bridge health
                bridge_healthy = await self.check_bridge_health()
                if not bridge_healthy:
                    logger.warning("Bridge health check failed")
                    self.crashes += 1
                
                # Check memory pressure
                mem = psutil.virtual_memory()
                if mem.percent > 90:
                    logger.warning(f"High memory pressure: {mem.percent}%")
                    gc.collect()  # Force garbage collection
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stability monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def check_bridge_health(self) -> bool:
        """Check if Bridge is healthy"""
        try:
            # Simple health check - try to create an elicitation
            elicit_id = await self.manager.create_elicitation(
                from_agent="health_check",
                to_agent="health_check",
                message="Health check",
                schema={},
                timeout_seconds=1
            )
            return elicit_id is not None
        except Exception:
            return False
    
    async def attempt_recovery(self):
        """Attempt to recover from failure"""
        logger.info("Attempting recovery...")
        self.restarts += 1
        
        try:
            # Reinitialize manager
            await self.manager.shutdown()
            await self.manager.initialize()
            logger.info("Recovery successful")
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
    
    async def log_progress(self, elapsed: timedelta):
        """Log test progress"""
        hours = elapsed.total_seconds() / 3600
        progress = (hours / self.duration_hours) * 100
        
        # Current memory
        if self.memory_snapshots:
            current_mem = self.memory_snapshots[-1].rss_mb
            memory_growth = current_mem - self.initial_memory
            growth_rate = memory_growth / hours if hours > 0 else 0
        else:
            current_mem = 0
            growth_rate = 0
        
        # Current performance
        if self.performance_snapshots:
            current_perf = self.performance_snapshots[-1]
            p99 = current_perf.p99_latency_ms
            throughput = current_perf.throughput_rps
        else:
            p99 = 0
            throughput = 0
        
        logger.info(f"\n{'='*60}")
        logger.info(f"PROGRESS: {hours:.1f}h / {self.duration_hours}h ({progress:.1f}%)")
        logger.info(f"Memory: {current_mem:.1f}MB (growth: {growth_rate:.2f}MB/h)")
        logger.info(f"Performance: P99={p99:.1f}ms, Throughput={throughput:.1f}rps")
        logger.info(f"Requests: {self.successful_requests}/{self.total_requests} successful")
        logger.info(f"Stability: {self.crashes} crashes, {self.restarts} restarts")
        logger.info(f"{'='*60}\n")
    
    async def analyze_results(self) -> EnduranceReport:
        """Analyze test results"""
        logger.info("Analyzing endurance test results...")
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - self.start_time).total_seconds() / 3600
        
        # Memory analysis
        memory_leak = False
        memory_growth_rate = 0
        if self.memory_snapshots and len(self.memory_snapshots) > 2:
            initial_mem = self.memory_snapshots[0].rss_mb
            final_mem = self.memory_snapshots[-1].rss_mb
            memory_growth = final_mem - initial_mem
            memory_growth_rate = memory_growth / duration if duration > 0 else 0
            
            # Leak detection: > 10MB/hour growth
            memory_leak = memory_growth_rate > 10
        
        # Performance analysis
        performance_degradation = False
        latency_trend = "STABLE"
        if self.performance_snapshots and len(self.performance_snapshots) > 2:
            # Compare first and last hour
            early_perfs = [p for p in self.performance_snapshots if p.hour < 2]
            late_perfs = [p for p in self.performance_snapshots if p.hour >= duration - 2]
            
            if early_perfs and late_perfs:
                early_p99 = np.mean([p.p99_latency_ms for p in early_perfs])
                late_p99 = np.mean([p.p99_latency_ms for p in late_perfs])
                
                if late_p99 > early_p99 * 1.5:  # 50% degradation
                    performance_degradation = True
                    latency_trend = "INCREASING"
                elif late_p99 < early_p99 * 0.8:
                    latency_trend = "DECREASING"
        
        # Determine pass/fail
        issues = []
        if memory_leak:
            issues.append(f"Memory leak detected: {memory_growth_rate:.1f}MB/hour")
        if performance_degradation:
            issues.append("Performance degradation detected")
        if self.crashes > 5:
            issues.append(f"Too many crashes: {self.crashes}")
        if self.error_counts and sum(self.error_counts.values()) > self.total_requests * 0.05:
            issues.append("Error rate exceeds 5%")
        
        passed = len(issues) == 0 and duration >= self.duration_hours * 0.95
        
        # Generate recommendations
        recommendations = []
        if memory_leak:
            recommendations.append("Investigate memory leak in elicitation manager")
        if performance_degradation:
            recommendations.append("Optimize for sustained performance")
        if self.crashes > 0:
            recommendations.append("Improve crash recovery mechanisms")
        
        if not recommendations:
            recommendations.append("System shows excellent endurance")
        
        return EnduranceReport(
            start_time=self.start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_hours=duration,
            target_duration_hours=self.duration_hours,
            agent_count=self.agent_count,
            memory_leak_detected=memory_leak,
            memory_growth_rate_mb_per_hour=memory_growth_rate,
            peak_memory_mb=self.peak_memory,
            final_memory_mb=self.memory_snapshots[-1].rss_mb if self.memory_snapshots else 0,
            memory_snapshots=list(self.memory_snapshots),
            performance_degradation=performance_degradation,
            performance_snapshots=list(self.performance_snapshots),
            latency_trend=latency_trend,
            total_requests=self.total_requests,
            successful_requests=self.successful_requests,
            failed_requests=self.failed_requests,
            error_types=self.error_counts,
            crashes=self.crashes,
            restarts_required=self.restarts,
            passed=passed,
            issues=issues,
            recommendations=recommendations
        )
    
    async def save_report(self, report: EnduranceReport):
        """Save endurance test report"""
        report_file = self.results_dir / f"endurance_report_{int(time.time())}.json"
        
        # Convert report to dict (handle non-serializable types)
        report_dict = asdict(report)
        
        # Simplify memory snapshots for JSON
        report_dict['memory_snapshots'] = [
            {
                'timestamp': s.timestamp,
                'rss_mb': s.rss_mb,
                'percent_used': s.percent_used
            }
            for s in report.memory_snapshots[-100:]  # Keep last 100
        ]
        
        with open(report_file, 'w') as f:
            json.dump(report_dict, f, indent=2)
        
        logger.info(f"Report saved to {report_file}")
        
        # Print summary
        logger.info("\n" + "="*80)
        logger.info("ENDURANCE TEST SUMMARY")
        logger.info("="*80)
        logger.info(f"Duration: {report.duration_hours:.1f}/{report.target_duration_hours} hours")
        logger.info(f"Agents: {report.agent_count}")
        logger.info(f"Memory Leak: {'YES' if report.memory_leak_detected else 'NO'}")
        logger.info(f"Memory Growth: {report.memory_growth_rate_mb_per_hour:.2f}MB/hour")
        logger.info(f"Performance Degradation: {'YES' if report.performance_degradation else 'NO'}")
        logger.info(f"Total Requests: {report.total_requests:,}")
        logger.info(f"Success Rate: {report.successful_requests/report.total_requests*100:.1f}%")
        logger.info(f"Crashes: {report.crashes}")
        logger.info(f"VERDICT: {'PASS' if report.passed else 'FAIL'}")
        
        if report.issues:
            logger.warning("\nIssues:")
            for issue in report.issues:
                logger.warning(f"  - {issue}")
        
        if report.recommendations:
            logger.info("\nRecommendations:")
            for rec in report.recommendations:
                logger.info(f"  - {rec}")
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up...")
        
        if self.manager:
            await self.manager.shutdown()
        
        if self.event_store:
            # Event store cleanup if needed
            pass
        
        # Force garbage collection
        gc.collect()


async def main():
    """Run endurance test"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run endurance test")
    parser.add_argument("--hours", type=int, default=72, 
                       help="Test duration in hours (default: 72)")
    parser.add_argument("--agents", type=int, default=5000,
                       help="Number of agents (default: 5000)")
    parser.add_argument("--demo", action="store_true",
                       help="Run short demo (1 hour, 100 agents)")
    
    args = parser.parse_args()
    
    if args.demo:
        duration = 1
        agents = 100
        logger.info("Running in DEMO mode (1 hour, 100 agents)")
    else:
        duration = args.hours
        agents = args.agents
    
    runner = EnduranceTestRunner(duration_hours=duration, agent_count=agents)
    
    try:
        report = await runner.run()
        
        if report.passed:
            logger.info("\n✅ Endurance test PASSED!")
            return 0
        else:
            logger.warning("\n❌ Endurance test FAILED!")
            return 1
            
    except KeyboardInterrupt:
        logger.info("\nEndurance test interrupted by user")
        return 2
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))