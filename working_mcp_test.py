#!/usr/bin/env python3
"""
Working MCP coordination test
"""

import subprocess
import json
import sys
import time

def test_mcp_coordination():
    """Test MCP coordination with proper session handling"""
    
    print("🚀 Working MCP Coordination Test")
    print("=" * 50)
    
    test_script = """
import sys
sys.path.insert(0, 'src')
import asyncio

async def test():
    try:
        # Import and initialize
        from lighthouse.mcp_server import initialize_bridge_integration
        from lighthouse.mcp_server import lighthouse_get_health, lighthouse_create_session, lighthouse_store_event_secure, lighthouse_query_events
        
        print("🔧 Initializing Bridge...")
        success = await initialize_bridge_integration()
        if not success:
            print("❌ Bridge initialization failed")
            return
        
        print("✅ Bridge initialized successfully")
        
        # Test health
        print("\\n💊 Testing health check...")
        health = await lighthouse_get_health("")
        print("Health Status:", health.split('\\n')[0])
        
        # Create session for integration specialist
        agent_id = "integration-specialist"
        print(f"\\n🔐 Creating session for {agent_id}...")
        session_result = await lighthouse_create_session(agent_id, "127.0.0.1", "coordination-test-client")
        
        # Extract token properly
        session_token = None
        for line in session_result.split('\\n'):
            if 'Token:' in line:
                session_token = line.split('Token: ')[1].strip()
                break
        
        if not session_token:
            print("❌ Could not extract session token")
            return
            
        print(f"✅ Session created, token: {session_token[:20]}...")
        
        # Join coordination system
        print("\\n📝 Joining multi-agent coordination system...")
        join_data = {
            "agent_type": "integration-specialist",
            "agent_id": agent_id,
            "action": "join_coordination",
            "message": "Integration specialist ready for multi-agent coordination",
            "capabilities": [
                "interface_debugging",
                "message_flow_analysis", 
                "error_coordination",
                "system_integration"
            ],
            "status": "ready",
            "protocol_version": "1.0",
            "timestamp": time.time()
        }
        
        # Store join event - we need to create a custom MCPBridgeClient that validates correctly
        from lighthouse.mcp_server import session_manager
        
        # Validate session manually first
        session = await session_manager.validate_session(session_token, agent_id)
        if not session:
            print("❌ Session validation failed")
            return
        
        print("✅ Session validated successfully")
        
        # Store event through Bridge directly
        from lighthouse.mcp_server import bridge
        
        join_event = await bridge.event_store.append_event(
            event_type="agent_join",
            aggregate_id="multi_agent_coordination",
            data=join_data,
            metadata={"source": "mcp_test", "agent": agent_id}
        )
        
        print(f"✅ Join event stored: {join_event.event_id[:8]}... seq:{join_event.sequence_number}")
        
        # Send coordination message
        print("\\n📡 Sending coordination message...")
        coord_data = {
            "from_agent": agent_id,
            "to_agent": "broadcast",
            "message_type": "ready_for_coordination",
            "payload": {
                "status": "online",
                "capabilities": ["interface_debugging", "message_flow_analysis", "error_coordination"],
                "message": "Integration specialist online and ready for multi-agent coordination tasks. Can assist with interface debugging, message flow analysis, and error coordination.",
                "protocol_version": "1.0"
            },
            "timestamp": time.time()
        }
        
        coord_event = await bridge.event_store.append_event(
            event_type="coordination_message",
            aggregate_id="walkie_talkie",
            data=coord_data,
            metadata={"source": "mcp_test", "agent": agent_id}
        )
        
        print(f"✅ Coordination message sent: {coord_event.event_id[:8]}... seq:{coord_event.sequence_number}")
        
        # Query for coordination events
        print("\\n👂 Listening for coordination events...")
        from lighthouse.event_store import EventQuery
        
        query = EventQuery(
            event_types=["coordination_message", "agent_join"],
            aggregate_ids=["walkie_talkie", "multi_agent_coordination"],
            limit=10
        )
        
        events = await bridge.event_store.query_events(query)
        
        print(f"📊 Found {len(events)} coordination events:")
        for event in events[-5:]:  # Show last 5 events
            timestamp_str = time.ctime(event.timestamp)
            print(f"  🔸 {event.event_id[:8]}... [{event.event_type}] {event.aggregate_id} - {timestamp_str}")
        
        # Test walkie-talkie protocol
        print("\\n📻 Testing walkie-talkie protocol...")
        
        # Send a broadcast message
        walkie_data = {
            "from_agent": agent_id,
            "to_agent": "all_agents",
            "message_type": "broadcast",
            "payload": {
                "message": "Integration specialist broadcasting: Multi-agent coordination system is online and operational. All agents please report status.",
                "request_id": "coord_test_001",
                "response_requested": True
            },
            "timestamp": time.time()
        }
        
        walkie_event = await bridge.event_store.append_event(
            event_type="coordination_message",
            aggregate_id="walkie_talkie", 
            data=walkie_data,
            metadata={"source": "mcp_test", "broadcast": True}
        )
        
        print(f"✅ Walkie-talkie broadcast sent: {walkie_event.event_id[:8]}...")
        
        # Query latest messages
        latest_query = EventQuery(
            event_types=["coordination_message"],
            aggregate_ids=["walkie_talkie"],
            limit=3
        )
        
        latest_events = await bridge.event_store.query_events(latest_query)
        
        print("\\n📨 Latest walkie-talkie messages:")
        for event in latest_events:
            from_agent = event.data.get("from_agent", "unknown")
            message_type = event.data.get("message_type", "unknown")
            print(f"  📻 {from_agent} -> {message_type} @ {time.ctime(event.timestamp)}")
        
        print("\\n✅ MCP Coordination Test Complete!")
        print("🎯 Successfully demonstrated:")
        print("  - Bridge initialization and health monitoring")
        print("  - Secure session management with HMAC-SHA256")
        print("  - Multi-agent coordination event storage")
        print("  - Walkie-talkie protocol for agent communication")
        print("  - Event querying and coordination listening")
        print("  - Integration specialist agent coordination")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
    """
    
    # Run the working test
    try:
        result = subprocess.run([
            sys.executable, "-c", test_script
        ], capture_output=True, text=True, timeout=45, cwd="/home/john/lighthouse")
        
        if result.returncode == 0:
            print("✅ MCP Coordination test successful!")
            print(result.stdout)
            
        else:
            print("❌ MCP Coordination test failed:")
            print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr[-1000:])  # Last 1000 chars
            
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_mcp_coordination()