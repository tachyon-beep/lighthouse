#!/usr/bin/env python3
"""
Final performance validation test for OptimizedElicitationManager
"""

import asyncio
import sys
import time
from pathlib import Path

# Add source to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lighthouse.event_store import EventStore
from lighthouse.bridge.elicitation.fast_manager import OptimizedElicitationManager


async def run_performance_validation():
    """Run comprehensive performance validation."""
    
    print("🔍 FINAL PERFORMANCE VALIDATION")
    print("=" * 50)
    
    # Initialize event store
    event_store = EventStore()
    await event_store.initialize()
    
    # Create optimized manager
    manager = OptimizedElicitationManager(
        event_store=event_store,
        bridge_secret_key="test_secret_key_for_validation",
        enable_security=True
    )
    
    await manager.initialize()
    
    try:
        print("\n1. Basic Functionality Test")
        print("-" * 30)
        
        # Test creation
        start = time.time()
        elicit_id = await manager.create_elicitation(
            from_agent="test_agent_alpha",
            to_agent="test_agent_beta",
            message="Performance validation request",
            schema={"type": "object", "properties": {"result": {"type": "string"}}},
            timeout_seconds=30
        )
        creation_time = (time.time() - start) * 1000
        
        print(f"✅ Created elicitation {elicit_id[:16]}... in {creation_time:.2f}ms")
        
        # Test response
        start = time.time()
        success = await manager.respond_to_elicitation(
            elicitation_id=elicit_id,
            responding_agent="test_agent_beta",
            response_type="accept",
            data={"result": "validation_success"}
        )
        response_time = (time.time() - start) * 1000
        
        if success:
            print(f"✅ Response processed in {response_time:.2f}ms")
        else:
            print("❌ Response processing failed")
            return False
        
        print("\n2. Performance Benchmark (100 Operations)")
        print("-" * 30)
        
        # Warm up
        for i in range(5):
            eid = await manager.create_elicitation(
                from_agent="warmup_agent",
                to_agent="warmup_target", 
                message=f"Warmup {i}",
                schema={"type": "object"},
                timeout_seconds=5
            )
            await manager.respond_to_elicitation(eid, "warmup_target", "accept", {"warmup": True})
        
        # Full benchmark
        start = time.time()
        successful_ops = 0
        
        for i in range(100):
            try:
                # Create elicitation
                elicit_id = await manager.create_elicitation(
                    from_agent=f"perf_agent_{i % 5}",
                    to_agent=f"target_agent_{(i+1) % 5}",
                    message=f"Performance test request {i}",
                    schema={"type": "object", "properties": {"index": {"type": "integer"}}},
                    timeout_seconds=10
                )
                
                # Respond to elicitation
                await manager.respond_to_elicitation(
                    elicitation_id=elicit_id,
                    responding_agent=f"target_agent_{(i+1) % 5}",
                    response_type="accept",
                    data={"index": i, "status": "completed"}
                )
                
                successful_ops += 1
                
            except Exception as e:
                print(f"⚠️ Operation {i} failed: {e}")
        
        total_time = (time.time() - start) * 1000
        avg_latency = total_time / successful_ops if successful_ops > 0 else float('inf')
        
        print(f"✅ Completed {successful_ops}/100 operations")
        print(f"✅ Total time: {total_time:.0f}ms")
        print(f"✅ Average latency: {avg_latency:.1f}ms per operation")
        
        print("\n3. Latency Distribution Analysis")
        print("-" * 30)
        
        # Get final metrics
        final_metrics = manager.get_metrics()
        
        print(f"📊 P50 latency: {final_metrics.p50_latency_ms:.1f}ms")
        print(f"📊 P95 latency: {final_metrics.p95_latency_ms:.1f}ms") 
        print(f"📊 P99 latency: {final_metrics.p99_latency_ms:.1f}ms")
        print(f"📊 Active elicitations: {final_metrics.active_elicitations}")
        
        print("\n4. Performance Target Validation")
        print("-" * 30)
        
        # Check P99 < 300ms target
        p99_target_met = final_metrics.p99_latency_ms < 300
        avg_target_met = avg_latency < 100  # Avg should be much lower
        
        if p99_target_met:
            print(f"✅ P99 latency {final_metrics.p99_latency_ms:.1f}ms MEETS <300ms target")
        else:
            print(f"❌ P99 latency {final_metrics.p99_latency_ms:.1f}ms EXCEEDS 300ms target")
        
        if avg_target_met:
            print(f"✅ Average latency {avg_latency:.1f}ms meets expectations")
        else:
            print(f"⚠️ Average latency {avg_latency:.1f}ms higher than expected")
        
        print("\n5. System Stability Check")
        print("-" * 30)
        
        # Check for any issues
        memory_efficient = len(manager._signature_cache) < 1000  # Cache shouldn't grow too large
        batch_processed = len(manager._event_batch) < 50  # Batches should be processed
        
        print(f"📈 Signature cache size: {len(manager._signature_cache)}")
        print(f"📈 Pending batch events: {len(manager._event_batch)}")
        
        if memory_efficient:
            print("✅ Memory usage within bounds")
        else:
            print("⚠️ High memory usage detected")
        
        # Overall assessment
        print("\n" + "=" * 50)
        print("🏁 FINAL ASSESSMENT")
        print("=" * 50)
        
        all_good = (
            successful_ops >= 95 and  # 95%+ success rate
            p99_target_met and       # P99 < 300ms
            avg_target_met and       # Average reasonable
            memory_efficient         # Memory under control
        )
        
        if all_good:
            print("🎉 ALL PERFORMANCE TARGETS MET")
            print("✅ System ready for 5% canary deployment")
            return True
        else:
            print("❌ Performance targets not met")
            print("🚫 Not ready for deployment")
            return False
        
    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await manager.shutdown()


async def main():
    success = await run_performance_validation()
    
    if success:
        print("\n✅ FINAL GO/NO-GO: GO FOR DEPLOYMENT")
        sys.exit(0)
    else:
        print("\n❌ FINAL GO/NO-GO: NO-GO")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())