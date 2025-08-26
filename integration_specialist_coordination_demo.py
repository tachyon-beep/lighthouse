#!/usr/bin/env python3
"""
Integration Specialist MCP Coordination Demo

Demonstrates live multi-agent coordination through the Lighthouse MCP service
using only valid event types and proper session management.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def demonstrate_integration_coordination():
    """Demonstrate integration specialist coordination capabilities"""
    
    print("🚀 Integration Specialist - MCP Coordination Demo")
    print("=" * 60)
    
    try:
        # Import components
        from lighthouse.mcp_server import (
            MCPSessionManager,
            MCPBridgeClient
        )
        from lighthouse.mcp_resource_manager import MCPResourceManager
        from lighthouse.event_store import Event, EventQuery, EventType
        import secrets
        
        # Initialize coordination system
        print("📡 Initializing Integration Specialist Coordination...")
        
        instance_id = f"integration_spec_{secrets.token_hex(6)}"
        resource_manager = MCPResourceManager(instance_id)
        
        config = {
            'auth_secret': secrets.token_urlsafe(32),
            'session_timeout': 3600,
            'max_concurrent_sessions': 50,
            'memory_cache_size': 2000,
            'expert_timeout': 15.0,
            'data_dir': f"/tmp/lighthouse_integration_{secrets.token_hex(4)}"
        }
        
        success = await resource_manager.initialize_resources(
            project_id="lighthouse_integration_coordination", 
            config=config
        )
        
        if not success:
            print("❌ Failed to initialize coordination system")
            return False
            
        bridge = resource_manager.bridge
        expert_coordinator = resource_manager.expert_coordinator
        session_manager = MCPSessionManager(bridge)
        
        print("✅ Coordination system initialized")
        
        # Create secure session for Integration Specialist
        print("\n🔐 Creating Integration Specialist Session...")
        
        integration_session = await session_manager.create_session(
            "integration_specialist_agent",
            "127.0.0.1", 
            "Claude-Integration-Specialist/1.0"
        )
        
        print(f"✅ Integration Specialist Session Active")
        print(f"   Agent ID: {integration_session.agent_id}")
        print(f"   Session ID: {integration_session.session_id[:16]}...")
        print(f"   Token: {integration_session.session_token[:24]}...")
        print(f"   Security: HMAC-SHA256 validated")
        
        # Validate session security
        print("\n🔍 Validating Session Security...")
        validated = await session_manager.validate_session(
            integration_session.session_token,
            "integration_specialist_agent"
        )
        
        if validated:
            print("✅ Session security validation passed")
        else:
            print("❌ Session security validation failed")
            return False
        
        # Store coordination events using valid event types
        print("\n📦 Storing Integration Coordination Events...")
        
        # Event 1: Agent Registration
        agent_registration_event = Event(
            event_id=f"integration_{secrets.token_hex(8)}",
            event_type=EventType.AGENT_REGISTERED,
            aggregate_id="integration_specialist_coordination",
            sequence_number=1,
            data={
                "agent_type": "integration_specialist",
                "capabilities": [
                    "interface_analysis",
                    "message_flow_debugging", 
                    "state_coordination",
                    "error_handling",
                    "performance_integration"
                ],
                "coordination_mode": "mcp_walkie_talkie",
                "session_id": integration_session.session_id,
                "timestamp": time.time()
            },
            metadata={
                "agent_id": "integration_specialist_agent",
                "session_token": integration_session.session_token,
                "coordination_type": "multi_agent_system"
            },
            timestamp=time.time()
        )
        
        await bridge.event_store.append(agent_registration_event)
        print(f"   ✅ Agent registration event: {agent_registration_event.event_id}")
        
        # Event 2: System Analysis Start
        system_analysis_event = Event(
            event_id=f"analysis_{secrets.token_hex(8)}",
            event_type=EventType.SYSTEM_STARTED,
            aggregate_id="integration_analysis",
            sequence_number=1,
            data={
                "analysis_type": "integration_health_check",
                "target_system": "lighthouse_mcp_coordination",
                "initiated_by": "integration_specialist_agent",
                "analysis_scope": [
                    "component_interfaces",
                    "message_flow_validation",
                    "state_synchronization", 
                    "error_propagation",
                    "performance_bottlenecks"
                ],
                "timestamp": time.time()
            },
            metadata={
                "session_token": integration_session.session_token,
                "priority": "high",
                "coordination_phase": "initial_assessment"
            },
            timestamp=time.time()
        )
        
        await bridge.event_store.append(system_analysis_event)
        print(f"   ✅ System analysis event: {system_analysis_event.event_id}")
        
        # Query coordination events
        print("\n🔍 Querying Integration Coordination Events...")
        
        coordination_query = EventQuery(
            event_types=[EventType.AGENT_REGISTERED, EventType.SYSTEM_STARTED],
            aggregate_ids=["integration_specialist_coordination", "integration_analysis"],
            limit=10
        )
        
        coordination_results = await bridge.event_store.query(coordination_query)
        
        print(f"✅ Found {len(coordination_results.events)} coordination events:")
        for event in coordination_results.events:
            print(f"   🔸 {event.event_id[:12]}... [{event.event_type.value}] {event.aggregate_id}")
            if "agent_type" in event.data:
                print(f"      Agent: {event.data['agent_type']}")
            if "analysis_type" in event.data:
                print(f"      Analysis: {event.data['analysis_type']}")
        
        # Test expert coordination
        print("\n🤝 Testing Expert Coordination System...")
        
        if expert_coordinator:
            stats = expert_coordinator.get_coordination_stats()
            print("✅ Expert coordination system active:")
            print(f"   Total Requests: {stats.get('total_requests', 0)}")
            print(f"   Success Rate: {stats.get('success_rate', 0):.1%}")
            print(f"   Average Response Time: {stats.get('avg_response_time_ms', 0):.2f}ms")
        else:
            print("⚠️  Expert coordination system not available")
        
        # System health check
        print("\n💊 System Health Assessment...")
        
        health = await bridge.event_store.get_health()
        print("✅ Event Store Health:")
        print(f"   Status: {health.status}")
        print(f"   Total Events: {health.total_events}")
        print(f"   Disk Usage: {health.disk_usage_bytes / 1024:.2f} KB")
        print(f"   Average Query Time: {health.average_query_latency_ms:.2f}ms")
        
        # Simulate coordination with other agents
        print("\n🌐 Simulating Multi-Agent Coordination...")
        
        # Create sessions for other system agents
        agent_types = [
            "system_architect_agent",
            "security_architect_agent", 
            "performance_engineer_agent"
        ]
        
        coordination_sessions = {}
        
        for agent_type in agent_types:
            agent_session = await session_manager.create_session(
                agent_type,
                "127.0.0.1",
                f"Claude-{agent_type.replace('_', '-').title()}/1.0"
            )
            coordination_sessions[agent_type] = agent_session
            
            # Store agent coordination event
            coordination_event = Event(
                event_id=f"coord_{secrets.token_hex(8)}",
                event_type=EventType.AGENT_SESSION_STARTED,
                aggregate_id="multi_agent_coordination",
                sequence_number=1,
                data={
                    "coordinating_agent": agent_type,
                    "coordination_with": "integration_specialist_agent",
                    "coordination_purpose": "system_integration_validation",
                    "session_id": agent_session.session_id,
                    "timestamp": time.time()
                },
                metadata={
                    "session_token": agent_session.session_token,
                    "coordination_level": "peer_to_peer"
                },
                timestamp=time.time()
            )
            
            await bridge.event_store.append(coordination_event)
            print(f"   ✅ Coordinated with: {agent_type}")
        
        # Query all coordination sessions
        session_query = EventQuery(
            event_types=[EventType.AGENT_SESSION_STARTED],
            aggregate_ids=["multi_agent_coordination"],
            limit=10
        )
        
        session_results = await bridge.event_store.query(session_query)
        
        print(f"\n📊 Active Coordination Summary:")
        print(f"   Active Agent Sessions: {len(session_manager.active_sessions)}")
        print(f"   Coordination Events: {len(session_results.events)}")
        print(f"   Event Store Health: {health.status}")
        print(f"   Session Security: HMAC-SHA256")
        
        # List all active sessions
        print(f"\n👥 Active Agent Sessions:")
        for session_id, session in session_manager.active_sessions.items():
            print(f"   🔸 {session.agent_id} - {session_id[:16]}...")
        
        # End coordination sessions (cleanup)
        print(f"\n🧹 Cleaning up coordination sessions...")
        for agent_type, agent_session in coordination_sessions.items():
            await session_manager.end_session(agent_session.session_id)
            print(f"   ✅ Ended session for: {agent_type}")
        
        # Final status
        remaining_sessions = len(session_manager.active_sessions)
        print(f"\n🎯 Integration Specialist Coordination Demo Complete!")
        print(f"   Remaining Active Sessions: {remaining_sessions}")
        print(f"   Integration Specialist Status: ACTIVE")
        print(f"   Session Token: {integration_session.session_token[:32]}...")
        print(f"   Ready for Live Multi-Agent Coordination: ✅")
        
        return True
        
    except Exception as e:
        print(f"❌ Coordination demo error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(demonstrate_integration_coordination())
    print("\n" + "=" * 60)
    if success:
        print("🎉 Integration Specialist Ready for MCP Walkie-Talkie Coordination!")
    else:
        print("❌ Coordination demo failed")
    sys.exit(0 if success else 1)