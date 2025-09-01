#!/usr/bin/env python3
"""
Quick performance test for P99 latency evaluation
"""

import asyncio
import time
import statistics
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

from lighthouse.bridge.elicitation.fast_manager import OptimizedElicitationManager
from lighthouse.event_store import EventStore

async def quick_latency_test():
    """Quick test of elicitation latency"""
    print("🔬 Quick Performance Test - P99 Latency Evaluation")
    print("=" * 60)
    
    # Initialize
    event_store = EventStore()
    await event_store.initialize()
    
    manager = OptimizedElicitationManager(
        event_store=event_store,
        bridge_secret_key="test_secret",
        enable_security=True
    )
    await manager.initialize()
    
    # Test scenarios
    scenarios = [
        {"agents": 10, "requests": 100, "name": "Low Load"},
        {"agents": 50, "requests": 200, "name": "Medium Load"}, 
        {"agents": 100, "requests": 300, "name": "High Load"}
    ]
    
    results = []
    
    for scenario in scenarios:
        print(f"\n📊 Testing: {scenario['name']} ({scenario['agents']} agents, {scenario['requests']} requests)")
        
        latencies = []
        start_time = time.time()
        
        # Run concurrent requests
        tasks = []
        for i in range(scenario['requests']):
            agent_from = f"agent_{i % scenario['agents']}"
            agent_to = f"agent_{(i + 1) % scenario['agents']}"
            
            task = asyncio.create_task(test_single_elicitation(manager, agent_from, agent_to, i))
            tasks.append(task)
        
        # Wait for completion
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect latencies
        for result in task_results:
            if isinstance(result, float):
                latencies.append(result)
        
        # Calculate metrics
        if latencies:
            sorted_latencies = sorted(latencies)
            n = len(sorted_latencies)
            
            metrics = {
                "scenario": scenario['name'],
                "agents": scenario['agents'],
                "requests": scenario['requests'],
                "successful": len(latencies),
                "p50": sorted_latencies[int(n * 0.5)],
                "p95": sorted_latencies[int(n * 0.95)], 
                "p99": sorted_latencies[int(n * 0.99)],
                "mean": statistics.mean(latencies),
                "max": max(latencies)
            }
            
            results.append(metrics)
            
            print(f"  ✅ Success Rate: {len(latencies)}/{scenario['requests']} ({len(latencies)/scenario['requests']*100:.1f}%)")
            print(f"  ⏱️  P50: {metrics['p50']:.1f}ms | P95: {metrics['p95']:.1f}ms | P99: {metrics['p99']:.1f}ms")
            
            if metrics['p99'] <= 300:
                print(f"  🎯 P99 {metrics['p99']:.1f}ms MEETS <300ms target")
            else:
                print(f"  ⚠️  P99 {metrics['p99']:.1f}ms EXCEEDS 300ms target")
        else:
            print("  ❌ No successful requests")
    
    await manager.shutdown()
    
    # Final assessment
    print(f"\n{'=' * 60}")
    print("🏆 FINAL PERFORMANCE ASSESSMENT")
    print(f"{'=' * 60}")
    
    for result in results:
        print(f"{result['scenario']:12} | P99: {result['p99']:6.1f}ms | Target Met: {'✅' if result['p99'] <= 300 else '❌'}")
    
    # Overall conclusion
    all_meet_target = all(r['p99'] <= 300 for r in results)
    max_p99 = max(r['p99'] for r in results) if results else 0
    
    print(f"\nOverall P99 Target (<300ms): {'✅ MET' if all_meet_target else '❌ NOT MET'}")
    print(f"Worst P99: {max_p99:.1f}ms")
    
    return all_meet_target, max_p99

async def test_single_elicitation(manager, from_agent, to_agent, request_id):
    """Test a single elicitation"""
    start = time.time()
    
    try:
        # Create elicitation
        elicit_id = await manager.create_elicitation(
            from_agent=from_agent,
            to_agent=to_agent,
            message=f"Test request {request_id}",
            schema={"type": "object"},
            timeout_seconds=10
        )
        
        # Small delay to simulate processing
        await asyncio.sleep(0.01)
        
        # Respond
        success = await manager.respond_to_elicitation(
            elicitation_id=elicit_id,
            responding_agent=to_agent,
            response_type="accept",
            data={"result": "ok"}
        )
        
        if success:
            return (time.time() - start) * 1000  # Return latency in ms
        else:
            return None
            
    except Exception as e:
        print(f"Error in elicitation {request_id}: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(quick_latency_test())