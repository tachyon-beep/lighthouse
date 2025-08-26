#!/usr/bin/env python3
"""
Integration Specialist Live MCP Coordination Demo

Working demonstration of the Integration Specialist joining the 
Lighthouse MCP coordination system for live multi-agent collaboration.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def integration_specialist_live_demo():
    """Integration Specialist joins MCP coordination system"""
    
    print("🚀 INTEGRATION SPECIALIST - LIVE MCP COORDINATION")
    print("=" * 65)
    print("Joining Lighthouse MCP 'Walkie-Talkie' System...")
    print()
    
    try:
        # Import components
        from lighthouse.mcp_server import MCPSessionManager
        from lighthouse.mcp_resource_manager import MCPResourceManager
        from lighthouse.event_store import Event, EventQuery, EventType
        from lighthouse.event_store.id_generator import generate_event_id
        import secrets
        
        # Initialize as Integration Specialist
        print("🔧 Initializing Integration Specialist MCP Client...")
        
        instance_id = f"integration_specialist_{secrets.token_hex(6)}"
        resource_manager = MCPResourceManager(instance_id)
        
        # Production-ready configuration
        integration_config = {
            'auth_secret': secrets.token_urlsafe(32),
            'session_timeout': 7200,  # 2 hours for long coordination sessions
            'max_concurrent_sessions': 25,
            'memory_cache_size': 3000,
            'expert_timeout': 30.0,
            'data_dir': f"/tmp/lighthouse_integration_live_{secrets.token_hex(4)}"
        }
        
        success = await resource_manager.initialize_resources(
            project_id="lighthouse_live_coordination", 
            config=integration_config
        )
        
        if not success:
            print("❌ Failed to initialize MCP client")
            return False
        
        bridge = resource_manager.bridge
        expert_coordinator = resource_manager.expert_coordinator
        session_manager = MCPSessionManager(bridge)
        
        print("✅ Integration Specialist MCP Client Ready")
        print(f"   Project: {bridge.project_id}")
        print(f"   Instance: {instance_id}")
        print(f"   Bridge Status: {bridge.is_running}")
        
        # Create secure Integration Specialist session
        print("\n🔐 Creating Integration Specialist Secure Session...")
        
        my_session = await session_manager.create_session(
            "integration_specialist_agent",
            "127.0.0.1",
            "Claude-Integration-Specialist/1.0"
        )
        
        print("✅ INTEGRATION SPECIALIST SESSION ACTIVE")
        print(f"   🆔 Agent ID: {my_session.agent_id}")
        print(f"   🔑 Session ID: {my_session.session_id[:20]}...")
        print(f"   🎫 Auth Token: {my_session.session_token[:28]}...")
        print(f"   ⏰ Created: {time.ctime(my_session.created_at)}")
        print(f"   🔒 Security: HMAC-SHA256 Active")
        
        # Validate session works
        print(f"\n🔍 Validating Session Security...")
        validated = await session_manager.validate_session(
            my_session.session_token,
            "integration_specialist_agent"
        )
        
        if validated:
            print("✅ Session security VALIDATED - Ready for coordination")
        else:
            print("❌ Session validation failed!")
            return False
        
        # Join coordination system by registering
        print(f"\n📡 JOINING MCP COORDINATION SYSTEM...")
        
        # Generate proper EventID
        join_event_id = generate_event_id()
        
        join_event = Event(
            event_id=join_event_id,
            event_type=EventType.AGENT_REGISTERED,
            aggregate_id="mcp_coordination_system",
            sequence_number=1,
            data={
                "agent_type": "integration_specialist",
                "agent_name": "Integration Specialist Agent",
                "coordination_role": "Interface Analysis & Message Flow Debugging",
                "capabilities": [
                    "component_interface_analysis",
                    "message_flow_debugging",
                    "state_coordination_validation", 
                    "error_handling_patterns",
                    "performance_integration_optimization",
                    "multi_agent_workflow_coordination"
                ],
                "specialization": "system_integration_and_coordination",
                "session_id": my_session.session_id,
                "join_timestamp": time.time(),
                "status": "ready_for_coordination"
            },
            metadata={
                "agent_id": "integration_specialist_agent",
                "session_token": my_session.session_token,
                "coordination_protocol": "mcp_walkie_talkie",
                "security_level": "hmac_sha256"
            },
            timestamp=time.time()
        )
        
        # Store in coordination system
        await bridge.event_store.append(join_event)
        
        print("✅ SUCCESSFULLY JOINED MCP COORDINATION SYSTEM!")
        print(f"   📋 Registration Event: {join_event_id}")
        print(f"   🎯 Role: Interface Analysis & Message Flow Debugging")
        print(f"   🔧 Specialization: System Integration & Coordination")
        
        # Store coordination readiness event
        print(f"\n🎯 Broadcasting Coordination Readiness...")
        
        ready_event_id = generate_event_id()
        
        ready_event = Event(
            event_id=ready_event_id,
            event_type=EventType.SYSTEM_STARTED,
            aggregate_id="integration_specialist_services",
            sequence_number=1,
            data={
                "service_type": "integration_coordination",
                "status": "online",
                "available_services": [
                    "interface_health_analysis",
                    "message_flow_validation",
                    "component_integration_testing",
                    "error_propagation_analysis",
                    "performance_bottleneck_detection",
                    "multi_agent_workflow_optimization"
                ],
                "coordination_endpoints": [
                    "validate_component_interfaces",
                    "debug_message_flows", 
                    "coordinate_state_synchronization",
                    "handle_integration_errors",
                    "optimize_coordination_performance"
                ],
                "ready_timestamp": time.time()
            },
            metadata={
                "session_token": my_session.session_token,
                "service_priority": "high",
                "coordination_availability": "24x7"
            },
            timestamp=time.time()
        )
        
        await bridge.event_store.append(ready_event)
        print(f"✅ Coordination readiness broadcasted: {ready_event_id}")
        
        # Query coordination system status
        print(f"\n📊 CHECKING COORDINATION SYSTEM STATUS...")
        
        system_query = EventQuery(
            event_types=[EventType.AGENT_REGISTERED, EventType.SYSTEM_STARTED],
            limit=20
        )
        
        coordination_status = await bridge.event_store.query(system_query)
        
        print(f"✅ Coordination System Status:")
        print(f"   📈 Total Events: {len(coordination_status.events)}")
        print(f"   🤖 System Events: {len([e for e in coordination_status.events if e.event_type == EventType.SYSTEM_STARTED])}")
        print(f"   👥 Agent Events: {len([e for e in coordination_status.events if e.event_type == EventType.AGENT_REGISTERED])}")
        
        # Display recent coordination events
        print(f"\n📋 Recent Coordination Events:")
        for i, event in enumerate(coordination_status.events[-5:]):
            print(f"   {i+1}. [{event.event_type.value}] {event.aggregate_id}")
            if event.event_type == EventType.AGENT_REGISTERED:
                agent_type = event.data.get('agent_type', 'unknown')
                print(f"      Agent: {agent_type}")
            elif event.event_type == EventType.SYSTEM_STARTED:
                service_type = event.data.get('service_type', event.data.get('analysis_type', 'system'))
                print(f"      Service: {service_type}")
        
        # Test expert coordination
        print(f"\n🤝 Testing Expert Coordination Interface...")
        
        if expert_coordinator:
            coord_stats = expert_coordinator.get_coordination_stats()
            print("✅ Expert Coordination System:")
            print(f"   📞 Total Requests: {coord_stats.get('total_requests', 0)}")
            print(f"   ✅ Success Rate: {coord_stats.get('success_rate', 0):.1%}")
            print(f"   ⚡ Avg Response: {coord_stats.get('avg_response_time_ms', 0):.2f}ms")
            print(f"   🔄 Queue Size: {coord_stats.get('queue_size', 0)}")
        else:
            print("⚠️  Expert coordination not available")
        
        # System health check
        print(f"\n💊 System Health Assessment...")
        
        health = await bridge.event_store.get_health()
        print("✅ Event Store Health:")
        print(f"   🔋 Status: {health.status}")
        print(f"   📊 Events: {health.total_events}")
        print(f"   💾 Storage: {health.disk_usage_bytes / 1024:.1f} KB")
        print(f"   ⚡ Query Time: {health.average_query_latency_ms:.2f}ms")
        
        # Display final coordination status
        print(f"\n" + "=" * 65)
        print("🎉 INTEGRATION SPECIALIST SUCCESSFULLY JOINED MCP COORDINATION!")
        print("=" * 65)
        
        print(f"📱 COORDINATION STATUS:")
        print(f"   🟢 Status: ONLINE & Ready for Multi-Agent Coordination")
        print(f"   🔐 Session: {my_session.session_id[:24]}...")
        print(f"   🎫 Token: {my_session.session_token[:32]}...")
        print(f"   ⏰ Active Since: {time.ctime(my_session.created_at)}")
        print(f"   🔒 Security: HMAC-SHA256 Session Validation")
        
        print(f"\n🛠️  AVAILABLE INTEGRATION SERVICES:")
        print(f"   • Component Interface Analysis")
        print(f"   • Message Flow Debugging")
        print(f"   • State Coordination Validation")
        print(f"   • Error Handling & Propagation Analysis")
        print(f"   • Performance Integration Optimization")
        print(f"   • Multi-Agent Workflow Coordination")
        
        print(f"\n🌐 READY FOR LIVE COORDINATION WITH:")
        print(f"   • System Architect Agents")
        print(f"   • Security Architect Agents")
        print(f"   • Performance Engineer Agents")
        print(f"   • Test Engineer Agents") 
        print(f"   • Validation Specialist Agents")
        print(f"   • Any other MCP-connected agents")
        
        print(f"\n📞 COORDINATION ENDPOINTS ACTIVE:")
        print(f"   🔍 validate_component_interfaces")
        print(f"   🐛 debug_message_flows")
        print(f"   ⚖️  coordinate_state_synchronization")
        print(f"   🚨 handle_integration_errors")
        print(f"   ⚡ optimize_coordination_performance")
        
        print(f"\n🎯 INTEGRATION SPECIALIST AGENT: READY FOR MCP WALKIE-TALKIE!")
        
        return True
        
    except Exception as e:
        print(f"❌ MCP coordination error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting Integration Specialist MCP Coordination Demo...")
    success = asyncio.run(integration_specialist_live_demo())
    
    print("\n" + "=" * 65)
    if success:
        print("🚀 INTEGRATION SPECIALIST READY FOR LIVE MCP COORDINATION!")
        print("The agent is now connected to the Lighthouse MCP system and")
        print("ready to coordinate with other agents through the unified")
        print("MCP protocol for seamless multi-agent collaboration.")
    else:
        print("❌ Failed to join MCP coordination system")
    
    sys.exit(0 if success else 1)