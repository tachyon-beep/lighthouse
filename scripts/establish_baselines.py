#!/usr/bin/env python3
"""
Baseline Establishment Script

Establishes performance baselines for all Lighthouse components before
integration begins. This is required by Plan Charlie Phase 2.

Usage:
    python scripts/establish_baselines.py [--component COMPONENT] [--duration SECONDS]
"""

import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lighthouse.bridge.performance.baseline_measurement import (
    get_baseline_manager,
    PerformanceBaselineManager
)
from lighthouse.event_store import EventStore
from lighthouse.bridge.security.rate_limiter import get_global_rate_limiter
from lighthouse.bridge.fuse_mount.authentication import FUSEAuthenticationManager

logger = logging.getLogger(__name__)


class BaselineRunner:
    """Runs baseline establishment for all components."""
    
    def __init__(self):
        """Initialize baseline runner."""
        self.baseline_manager = get_baseline_manager()
        self.components = [
            'event_store',
            'validation_engine', 
            'authentication_system',
            'rate_limiter',
            'fuse_filesystem',
            'expert_coordination'
        ]
    
    async def establish_all_baselines(self, duration_seconds: int = 60) -> dict:
        """Establish baselines for all components."""
        logger.info("Starting baseline establishment for all Lighthouse components")
        
        results = {}
        
        for component in self.components:
            try:
                logger.info(f"Establishing baseline for {component}...")
                
                baseline = await self.baseline_manager.establish_baseline(
                    component=component,
                    measurement_duration_seconds=duration_seconds,
                    target_operations=min(1000, duration_seconds * 50)  # Scale operations with duration
                )
                
                results[component] = {
                    'status': 'success',
                    'baseline': baseline,
                    'latency_p99_ms': baseline.latency_p99,
                    'throughput_rps': baseline.throughput_rps,
                    'memory_peak_mb': baseline.memory_peak_mb
                }
                
                logger.info(f"✓ {component} baseline established")
                
            except Exception as e:
                logger.error(f"✗ Failed to establish baseline for {component}: {str(e)}")
                results[component] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        return results
    
    async def establish_component_baseline(self, component: str, duration_seconds: int = 60):
        """Establish baseline for a single component."""
        if component not in self.components:
            raise ValueError(f"Unknown component: {component}. Available: {self.components}")
        
        logger.info(f"Establishing baseline for {component}")
        
        baseline = await self.baseline_manager.establish_baseline(
            component=component,
            measurement_duration_seconds=duration_seconds,
            target_operations=min(1000, duration_seconds * 50)
        )
        
        logger.info(f"✓ {component} baseline established:")
        logger.info(f"  Latency P99: {baseline.latency_p99:.2f}ms")
        logger.info(f"  Throughput: {baseline.throughput_rps:.2f} RPS")
        logger.info(f"  Memory Peak: {baseline.memory_peak_mb:.2f} MB")
        
        return baseline
    
    def print_baseline_summary(self):
        """Print summary of all established baselines."""
        summary = self.baseline_manager.get_baseline_summary()
        
        print("\n" + "="*70)
        print("LIGHTHOUSE PERFORMANCE BASELINE SUMMARY")
        print("="*70)
        
        print(f"Total Baselines: {summary['total_baselines']}")
        
        if summary['baselines']:
            print("\nComponent Performance Baselines:")
            print("-" * 50)
            
            for component, data in summary['baselines'].items():
                print(f"{component:20} | P99: {data['latency_p99_ms']:6.2f}ms | "
                      f"RPS: {data['throughput_rps']:7.1f} | "
                      f"Mem: {data['memory_peak_mb']:6.1f}MB")
            
            print("-" * 50)
            print(f"Baseline data stored in: {self.baseline_manager.storage_path}")
        else:
            print("\nNo baselines established yet.")
        
        print("="*70)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Establish Lighthouse component performance baselines")
    parser.add_argument('--component', '-c', help='Specific component to baseline')
    parser.add_argument('--duration', '-d', type=int, default=60, help='Measurement duration in seconds')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--summary', '-s', action='store_true', help='Show baseline summary only')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    runner = BaselineRunner()
    
    # Show summary only
    if args.summary:
        runner.print_baseline_summary()
        return
    
    try:
        if args.component:
            # Establish baseline for single component
            await runner.establish_component_baseline(args.component, args.duration)
        else:
            # Establish baselines for all components
            results = await runner.establish_all_baselines(args.duration)
            
            # Print results
            success_count = sum(1 for r in results.values() if r['status'] == 'success')
            error_count = len(results) - success_count
            
            logger.info(f"Baseline establishment complete: {success_count} success, {error_count} errors")
            
            if error_count > 0:
                logger.error("Components with errors:")
                for component, result in results.items():
                    if result['status'] == 'error':
                        logger.error(f"  {component}: {result['error']}")
        
        # Show final summary
        print("")
        runner.print_baseline_summary()
        
    except Exception as e:
        logger.error(f"Baseline establishment failed: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())