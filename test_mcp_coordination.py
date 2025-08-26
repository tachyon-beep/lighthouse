#!/usr/bin/env python3
"""
Test script for MCP coordination system
Demonstrates multi-agent coordination through the unified MCP service
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_mcp_coordination():
    """Test MCP coordination system functionality"""
    
    print("🚀 Starting MCP Coordination Test")
    
    try:
        # Import MCP server components
        from lighthouse.mcp_server import (
            initialize_bridge_integration, 
            bridge, 
            session_manager, 
            expert_coordinator
        )
        
        # Initialize the bridge integration
        print("📡 Initializing Bridge Integration...")
        success = await initialize_bridge_integration()
        if not success:
            print("❌ Failed to initialize bridge")
            return False
            
        print("✅ Bridge Integration Initialized")
        
        # Test 1: Create Integration Specialist Session
        print("\n🔐 Test 1: Creating Integration Specialist Session...")
        if not session_manager:
            print("❌ Session manager not available")
            return False
            
        session = await session_manager.create_session(
            "integration_specialist_agent",
            "127.0.0.1",
            "Claude-Integration-Specialist/1.0"
        )
        
        print(f"✅ Session Created:")
        print(f"   Session ID: {session.session_id}")
        print(f"   Agent ID: {session.agent_id}")
        print(f"   Token: {session.session_token[:16]}...")
        print(f"   Created: {time.ctime(session.created_at)}")
        
        # Test 2: Validate Session
        print("\n🔍 Test 2: Validating Session...")
        validated_session = await session_manager.validate_session(
            session.session_token,
            "integration_specialist_agent"
        )
        
        if validated_session:
            print("✅ Session validation successful")
        else:
            print("❌ Session validation failed")
            return False
            
        # Test 3: Store Coordination Event
        print("\n📦 Test 3: Storing Coordination Event...")
        if not bridge:
            print("❌ Bridge not available")
            return False
            
        event_data = {
            "action": "agent_coordination_test",
            "agent_type": "integration_specialist",
            "test_scenario": "mcp_walkie_talkie",
            "timestamp": time.time(),
            "session_id": session.session_id
        }
        
        event = await bridge.event_store.append_event(
            event_type="coordination_test",
            aggregate_id="integration_test_coordination",
            data=event_data,
            metadata={
                "agent_id": "integration_specialist_agent",
                "session_token": session.session_token,
                "test_type": "multi_agent_coordination"
            }
        )
        
        print(f"✅ Event stored with ID: {event.event_id}")
        
        # Test 4: Query Events
        print("\n🔍 Test 4: Querying Coordination Events...")
        from lighthouse.event_store import EventQuery
        
        query = EventQuery(
            event_types=["coordination_test"],
            aggregate_ids=["integration_test_coordination"],
            limit=5
        )
        
        events = await bridge.event_store.query_events(query)
        
        print(f"✅ Found {len(events)} coordination events")
        for event in events:
            print(f"   Event {event.event_id}: {event.event_type}")
            
        # Test 5: Expert Coordination
        print("\n🤝 Test 5: Testing Expert Coordination...")
        if expert_coordinator:
            stats = expert_coordinator.get_coordination_stats()
            print(f"✅ Expert coordination stats: {json.dumps(stats, indent=2)}")
        else:
            print("⚠️  Expert coordinator not available")
            
        # Test 6: Health Check
        print("\n💊 Test 6: Health Check...")
        health = await bridge.event_store.get_health()
        print(f"✅ Event Store Health:")
        print(f"   Status: {health.event_store_status}")
        print(f"   Events: {health.current_sequence}")
        print(f"   EPS: {health.events_per_second:.2f}")
        print(f"   Latency: {health.average_append_latency_ms:.2f}ms")
        
        print("\n🎉 All coordination tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Coordination test error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_coordination())
    sys.exit(0 if success else 1)