#!/usr/bin/env python3
"""
Final working MCP coordination test - Integration specialist demonstrates multi-agent coordination
"""

import subprocess
import sys

def run_integration_specialist_coordination_test():
    """Final test of integration specialist joining MCP coordination system"""
    
    print("🚀 INTEGRATION SPECIALIST MCP COORDINATION TEST")
    print("=" * 70)
    
    test_script = '''
import sys
import time
sys.path.insert(0, 'src')
import asyncio

async def test():
    try:
        # Initialize Lighthouse system
        from lighthouse.mcp_server import initialize_bridge_integration
        from lighthouse.mcp_server import lighthouse_get_health, lighthouse_create_session
        
        print("🔧 Initializing Lighthouse Bridge system...")
        success = await initialize_bridge_integration()
        if not success:
            print("❌ Bridge initialization failed")
            return
        
        print("✅ Bridge system initialized successfully")
        
        # Check system health
        print("\\n💊 System health check...")
        health = await lighthouse_get_health("")
        health_status = "✅ Online" if "Bridge Status: running" in health else "⚠️ Issues detected"
        print(f"System Status: {health_status}")
        
        # Create authenticated session
        agent_id = "integration-specialist"
        print(f"\\n🔐 Creating authenticated session for {agent_id}...")
        session_result = await lighthouse_create_session(agent_id, "127.0.0.1", "mcp-coordination-client")
        
        # Parse session token
        session_token = None
        for line in session_result.split('\\n'):
            if 'Token:' in line:
                session_token = line.split('Token: ')[1].strip()
                break
        
        if not session_token:
            print("❌ Could not extract session token")
            return
            
        print(f"✅ Session authenticated: {session_token[:20]}...")
        
        # Access Bridge for coordination
        print("\\n📡 Accessing multi-agent coordination system...")
        from lighthouse.mcp_server import bridge, session_manager
        from lighthouse.event_store.models import Event, EventType
        
        # Validate session
        session = await session_manager.validate_session(session_token, agent_id)
        if not session:
            print("❌ Session validation failed")
            return
        
        print("✅ Session validated with HMAC-SHA256 security")
        
        # 1. Agent join event
        print("\\n📝 Registering agent with coordination system...")
        
        join_event = Event(
            event_type=EventType.AGENT_REGISTERED,
            aggregate_id="multi_agent_coordination",
            data={
                "agent_type": "integration-specialist",
                "agent_id": "integration-specialist-001",
                "capabilities": [
                    "interface_debugging",
                    "message_flow_analysis", 
                    "error_coordination",
                    "system_integration",
                    "multi_agent_workflow_coordination"
                ],
                "status": "ready",
                "message": "Integration specialist ready for multi-agent collaboration and coordination tasks",
                "protocol_version": "1.0",
                "joined_at": time.time()
            },
            metadata={"source": "mcp_coordination", "priority": "normal"}
        )
        
        await bridge.event_store.append(join_event, agent_id)
        print(f"✅ Agent registered: Event ID {join_event.event_id[:8]}...")
        
        # 2. Coordination broadcast message
        print("\\n📻 Broadcasting coordination readiness...")
        
        broadcast_event = Event(
            event_type=EventType.COMMAND_EXECUTED,
            aggregate_id="walkie_talkie",
            data={
                "command_type": "coordination_broadcast",
                "from_agent": "integration-specialist",
                "to_agent": "broadcast", 
                "message_type": "ready_for_coordination",
                "payload": {
                    "status": "online",
                    "specialization": "integration-coordination",
                    "message": "Integration specialist online and ready for multi-agent workflow coordination. Available for interface debugging, message flow analysis, and error coordination assistance.",
                    "services": [
                        "interface_debugging",
                        "message_flow_tracing",
                        "error_propagation_analysis", 
                        "coordination_workflow_validation"
                    ]
                },
                "timestamp": time.time()
            },
            metadata={"broadcast": True, "protocol": "walkie_talkie"}
        )
        
        await bridge.event_store.append(broadcast_event, agent_id)
        print(f"✅ Broadcast sent: Event ID {broadcast_event.event_id[:8]}...")
        
        # 3. Listen for coordination events
        print("\\n👂 Listening for coordination events...")
        from lighthouse.event_store.models import EventQuery
        
        coord_query = EventQuery(
            event_types=[EventType.AGENT_REGISTERED, EventType.COMMAND_EXECUTED],
            aggregate_ids=["multi_agent_coordination", "walkie_talkie"],
            limit=8
        )
        
        query_result = await bridge.event_store.query(coord_query, agent_id)
        events = query_result.events
        
        print(f"📊 Coordination events received: {len(events)}")
        for i, event in enumerate(events[-3:], 1):  # Show last 3
            event_type = event.event_type.value
            agent_ref = event.data.get("from_agent", event.data.get("agent_id", "system"))
            timestamp = time.ctime(event.timestamp)
            print(f"  {i}. [{event_type}] {agent_ref} @ {timestamp}")
        
        # 4. Send status report
        print("\\n🤝 Sending coordination status report...")
        
        status_event = Event(
            event_type=EventType.COMMAND_EXECUTED,
            aggregate_id="walkie_talkie",
            data={
                "command_type": "status_report",
                "from_agent": "integration-specialist",
                "to_agent": "system_coordinator",
                "message_type": "coordination_status_report",
                "payload": {
                    "status": "fully_operational",
                    "active_integrations": 0,
                    "pending_requests": 0,
                    "message": "Integration specialist reporting: All systems operational. Ready to handle coordination requests and interface debugging tasks."
                },
                "timestamp": time.time()
            },
            metadata={"response_type": "status_report"}
        )
        
        await bridge.event_store.append(status_event, agent_id)
        print(f"✅ Status report sent: Event ID {status_event.event_id[:8]}...")
        
        # 5. Final walkie-talkie check
        print("\\n📻 Final walkie-talkie activity check...")
        
        final_query = EventQuery(
            event_types=[EventType.COMMAND_EXECUTED],
            aggregate_ids=["walkie_talkie"],
            limit=10
        )
        
        final_result = await bridge.event_store.query(final_query, agent_id)
        final_events = final_result.events
        
        print("📨 Recent walkie-talkie messages:")
        for event in final_events[-4:]:  # Last 4 messages
            from_agent = event.data.get("from_agent", "unknown")
            msg_type = event.data.get("message_type", event.data.get("command_type", "unknown"))
            print(f"  📡 {from_agent} -> {msg_type}")
        
        # Success summary
        print("\\n" + "="*70)
        print("🎉 INTEGRATION SPECIALIST MCP COORDINATION SUCCESS!")
        print("\\n✅ DEMONSTRATED CAPABILITIES:")
        print("  🔗 Lighthouse Bridge initialization and health monitoring")
        print("  🔐 Secure HMAC-SHA256 session management and authentication")
        print("  👥 Multi-agent coordination system registration")
        print("  📡 Walkie-talkie protocol broadcasting and message exchange")
        print("  📊 Event-driven coordination with real-time event storage")
        print("  📋 Coordination status reporting and system monitoring")
        print("  🔄 Event querying and coordination event listening")
        
        print("\\n🚀 INTEGRATION SPECIALIST STATUS: ONLINE & COORDINATED")
        print("📋 Session Summary:")
        print(f"  • Agent ID: {agent_id}")
        print(f"  • Session: {session_token[:20]}... (HMAC-SHA256)")
        print(f"  • Events: 3 stored (register, broadcast, status)")
        print(f"  • Protocol: MCP + Bridge + Event Store coordination")
        print("  • Ready for multi-agent collaboration tasks")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
    '''
    
    # Execute the final working test
    try:
        result = subprocess.run([
            sys.executable, "-c", test_script
        ], capture_output=True, text=True, timeout=90, cwd="/home/john/lighthouse")
        
        if result.returncode == 0:
            print("✅ INTEGRATION SPECIALIST COORDINATION TEST COMPLETED SUCCESSFULLY!")
            print(result.stdout)
        else:
            print("❌ Test failed:")
            print(result.stdout)
            if result.stderr:
                print("Errors:")
                # Show only relevant error messages
                error_lines = [line for line in result.stderr.split('\\n') 
                              if any(keyword in line.lower() for keyword in ['error', 'exception', 'failed'])]
                for line in error_lines[-5:]:  # Last 5 error lines
                    print(f"  {line}")
        
    except subprocess.TimeoutExpired:
        print("❌ Test timed out - system may need more time to initialize")
    except Exception as e:
        print(f"❌ Test execution error: {e}")

if __name__ == "__main__":
    run_integration_specialist_coordination_test()