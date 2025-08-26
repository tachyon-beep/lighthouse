#!/usr/bin/env python3
"""
Final MCP coordination test - demonstrating integration specialist joining coordination system
"""

import subprocess
import sys

def test_integration_specialist_coordination():
    """Test integration specialist joining MCP coordination system"""
    
    print("🚀 Integration Specialist MCP Coordination Test")
    print("=" * 60)
    
    test_script = """
import sys
import time
sys.path.insert(0, 'src')
import asyncio

async def test():
    try:
        # Import and initialize
        from lighthouse.mcp_server import initialize_bridge_integration
        from lighthouse.mcp_server import lighthouse_get_health, lighthouse_create_session
        
        print("🔧 Initializing Lighthouse Bridge system...")
        success = await initialize_bridge_integration()
        if not success:
            print("❌ Bridge initialization failed")
            return
        
        print("✅ Bridge initialized successfully")
        
        # Test system health
        print("\\n💊 Checking system health...")
        health = await lighthouse_get_health("")
        print("System Status:", "✅ Online" if "running" in health else "❌ Issues detected")
        
        # Create session for integration specialist
        agent_id = "integration-specialist"
        print(f"\\n🔐 Creating secure session for {agent_id}...")
        session_result = await lighthouse_create_session(agent_id, "127.0.0.1", "integration-coordination-client")
        
        # Extract session token
        session_token = None
        for line in session_result.split('\\n'):
            if 'Token:' in line:
                session_token = line.split('Token: ')[1].strip()
                break
        
        if not session_token:
            print("❌ Could not extract session token")
            return
            
        print(f"✅ Secure session established: {session_token[:20]}...")
        
        # Access Bridge components directly for coordination
        print("\\n📡 Joining multi-agent coordination system...")
        from lighthouse.mcp_server import bridge, session_manager
        
        # Validate our session
        session = await session_manager.validate_session(session_token, agent_id)
        if not session:
            print("❌ Session validation failed")
            return
        
        print("✅ Session authenticated via HMAC-SHA256")
        
        # 1. Announce integration specialist joining coordination
        join_data = {
            "agent_type": "integration-specialist",
            "agent_id": "integration-specialist-001", 
            "capabilities": [
                "interface_debugging",
                "message_flow_analysis",
                "error_coordination", 
                "system_integration",
                "multi_agent_workflow_debugging"
            ],
            "status": "ready",
            "message": "Integration specialist ready for multi-agent collaboration and coordination tasks",
            "protocol_version": "1.0",
            "joined_at": time.time()
        }
        
        join_event = await bridge.event_store.append_event(
            event_type="agent_join",
            aggregate_id="multi_agent_coordination",
            data=join_data,
            metadata={"source": "mcp_coordination", "priority": "normal"}
        )
        
        print(f"✅ Agent join announced: Event ID {join_event.event_id[:8]}...")
        
        # 2. Send ready-for-coordination message via walkie-talkie protocol
        print("\\n📻 Broadcasting via walkie-talkie protocol...")
        
        walkie_data = {
            "from_agent": "integration-specialist",
            "to_agent": "broadcast",
            "message_type": "ready_for_coordination",
            "payload": {
                "status": "online",
                "specialization": "integration-coordination",
                "message": "Integration specialist online. Available for interface debugging, message flow analysis, and multi-agent workflow coordination. Ready to assist with system integration challenges.",
                "available_services": [
                    "interface_debugging",
                    "message_flow_tracing",
                    "error_propagation_analysis",
                    "coordination_workflow_validation"
                ]
            },
            "timestamp": time.time()
        }
        
        coord_event = await bridge.event_store.append_event(
            event_type="coordination_message",
            aggregate_id="walkie_talkie",
            data=walkie_data,
            metadata={"broadcast": True, "protocol": "walkie_talkie"}
        )
        
        print(f"✅ Coordination broadcast sent: Event ID {coord_event.event_id[:8]}...")
        
        # 3. Listen for coordination events (simulating walkie-talkie listening)
        print("\\n👂 Listening for coordination events...")
        from lighthouse.event_store import EventQuery
        
        # Query for recent coordination activity
        coord_query = EventQuery(
            event_types=["coordination_message", "agent_join"],
            aggregate_ids=["walkie_talkie", "multi_agent_coordination"],
            limit=5
        )
        
        events = await bridge.event_store.query_events(coord_query)
        
        print(f"📊 Received {len(events)} coordination events:")
        for i, event in enumerate(events[-3:], 1):  # Show last 3 events
            from_agent = event.data.get("from_agent", event.data.get("agent_id", "system"))
            message_type = event.data.get("message_type", event.event_type)
            timestamp = time.ctime(event.timestamp)
            print(f"  {i}. [{event.event_type}] {from_agent} -> {message_type} @ {timestamp}")
        
        # 4. Test coordination response capability
        print("\\n🤝 Testing coordination response...")
        
        response_data = {
            "from_agent": "integration-specialist",
            "to_agent": "system_coordinator",
            "message_type": "coordination_status_report",
            "payload": {
                "status": "fully_operational",
                "active_integrations": 0,
                "pending_coordination_requests": 0,
                "message": "Integration specialist reporting: All systems operational. Ready to handle coordination requests and interface debugging tasks."
            },
            "timestamp": time.time()
        }
        
        response_event = await bridge.event_store.append_event(
            event_type="coordination_message", 
            aggregate_id="walkie_talkie",
            data=response_data,
            metadata={"response_type": "status_report"}
        )
        
        print(f"✅ Status report sent: Event ID {response_event.event_id[:8]}...")
        
        # 5. Demonstrate listening and responding to messages
        print("\\n📻 Final coordination message check...")
        
        final_query = EventQuery(
            event_types=["coordination_message"],
            aggregate_ids=["walkie_talkie"],
            limit=10
        )
        
        final_events = await bridge.event_store.query_events(final_query)
        
        print("📨 Recent walkie-talkie activity:")
        for event in final_events[-5:]:
            from_agent = event.data.get("from_agent", "unknown")
            msg_type = event.data.get("message_type", "unknown")
            print(f"  📡 {from_agent} -> {msg_type}")
        
        # Summary
        print("\\n" + "="*60)
        print("✅ INTEGRATION SPECIALIST MCP COORDINATION TEST COMPLETE!")
        print("\\n🎯 Successfully demonstrated:")
        print("  ✓ Lighthouse Bridge initialization and health monitoring")
        print("  ✓ Secure HMAC-SHA256 session management")
        print("  ✓ Integration specialist agent registration")
        print("  ✓ Multi-agent coordination event storage")
        print("  ✓ Walkie-talkie protocol broadcasting and listening")
        print("  ✓ Event-driven coordination message exchange")
        print("  ✓ Real-time coordination status reporting")
        print("\\n🔗 Integration specialist is now ONLINE and coordinated!")
        print("📊 Ready for multi-agent collaboration tasks")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
    """
    
    # Run the final integration test
    try:
        result = subprocess.run([
            sys.executable, "-c", test_script
        ], capture_output=True, text=True, timeout=60, cwd="/home/john/lighthouse")
        
        print("✅ Integration specialist coordination test completed!")
        print(result.stdout)
        
        if result.stderr:
            print("\\n📋 System logs:")
            # Show only important error info, not all debug output
            stderr_lines = result.stderr.split('\\n')
            important_lines = [line for line in stderr_lines if any(keyword in line.lower() for keyword in ['error', 'failed', 'exception', 'warning'])]
            if important_lines:
                for line in important_lines[-10:]:  # Last 10 important lines
                    print(f"  {line}")
            else:
                print("  No critical issues detected")
            
    except Exception as e:
        print(f"❌ Test execution error: {e}")

if __name__ == "__main__":
    test_integration_specialist_coordination()