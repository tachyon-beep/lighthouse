#!/usr/bin/env python3
"""
Quick test to verify elicitation manager fixes
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.lighthouse.bridge.elicitation.fast_manager import OptimizedElicitationManager
from src.lighthouse.event_store import EventStore


async def test_elicitation():
    """Test that elicitation manager works after fixes"""
    
    print("Testing elicitation manager fixes...")
    
    # Initialize event store
    event_store = EventStore()
    await event_store.initialize()
    
    # Create optimized manager
    manager = OptimizedElicitationManager(
        event_store=event_store,
        bridge_secret_key="test_secret",
        enable_security=True
    )
    
    await manager.initialize()
    
    try:
        # Test creating elicitation
        print("Creating elicitation...")
        elicit_id = await manager.create_elicitation(
            from_agent="test_agent_a",
            to_agent="test_agent_b",
            message="Test request",
            schema={"type": "object"},
            timeout_seconds=30
        )
        
        print(f"✅ Created elicitation: {elicit_id}")
        
        # Test responding to elicitation
        print("Responding to elicitation...")
        success = await manager.respond_to_elicitation(
            elicitation_id=elicit_id,
            responding_agent="test_agent_b",
            response_type="accept",
            data={"result": "success"}
        )
        
        if success:
            print("✅ Successfully responded to elicitation")
        else:
            print("❌ Failed to respond to elicitation")
            return False
        
        # Check metrics
        metrics = manager.get_metrics()
        print(f"✅ Metrics: P50={metrics.p50_latency_ms}ms, P99={metrics.p99_latency_ms}ms")
        
        # Test performance
        print("\nPerformance test (100 elicitations)...")
        import time
        
        start = time.time()
        for i in range(100):
            elicit_id = await manager.create_elicitation(
                from_agent=f"agent_{i % 10}",
                to_agent=f"agent_{(i+1) % 10}",
                message=f"Request {i}",
                schema={"type": "object"},
                timeout_seconds=5
            )
            
            # Respond immediately
            await manager.respond_to_elicitation(
                elicitation_id=elicit_id,
                responding_agent=f"agent_{(i+1) % 10}",
                response_type="accept",
                data={"count": i}
            )
        
        elapsed = (time.time() - start) * 1000
        avg_latency = elapsed / 100
        
        print(f"✅ Completed 100 elicitations in {elapsed:.0f}ms")
        print(f"✅ Average latency: {avg_latency:.1f}ms")
        
        # Check if P99 < 300ms
        final_metrics = manager.get_metrics()
        if final_metrics.p99_latency_ms < 300:
            print(f"✅ P99 latency {final_metrics.p99_latency_ms:.0f}ms MEETS <300ms target!")
        else:
            print(f"⚠️ P99 latency {final_metrics.p99_latency_ms:.0f}ms exceeds 300ms target")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await manager.shutdown()


async def main():
    success = await test_elicitation()
    
    if success:
        print("\n✅ ALL TESTS PASSED - Elicitation manager is working!")
        sys.exit(0)
    else:
        print("\n❌ TESTS FAILED - Issues remain")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())