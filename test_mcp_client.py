#!/usr/bin/env python3
"""
Test MCP client to connect to Lighthouse MCP server and test coordination
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mcp_connection():
    """Test MCP connection and coordination features"""
    
    print("🔌 Testing MCP Lighthouse Connection...")
    
    try:
        # Test MCP server process
        result = subprocess.run([
            "python", "-c", 
            "import sys; sys.path.insert(0, 'src'); "
            "from lighthouse.mcp_server import mcp; "
            "print('MCP server tools:', [t for t in dir(mcp) if 'lighthouse' in str(t)])"
        ], capture_output=True, text=True, timeout=10, cwd="/home/john/lighthouse")
        
        if result.returncode == 0:
            print("✅ MCP server module accessible")
            print("📋 Available tools:", result.stdout.strip())
        else:
            print("❌ MCP server module error:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ MCP connection test failed: {e}")
        return False
    
    # Test direct tool execution
    print("\n🧪 Testing MCP tools directly...")
    
    try:
        # Import and test tools directly
        from lighthouse.mcp_server import (
            lighthouse_get_health,
            lighthouse_create_session,
            lighthouse_store_event_secure,
            lighthouse_query_events
        )
        
        print("✅ MCP tools imported successfully")
        
        # Test health check
        print("\n💊 Testing health check...")
        health_result = await lighthouse_get_health("")
        print("Health:", health_result[:200] + "..." if len(health_result) > 200 else health_result)
        
        # Test session creation
        print("\n🔐 Testing session creation...")
        session_result = await lighthouse_create_session("integration-specialist-test", "127.0.0.1", "test-client")
        print("Session:", session_result[:200] + "..." if len(session_result) > 200 else session_result)
        
        # Extract session token from result
        session_token = None
        for line in session_result.split('\n'):
            if 'Token:' in line:
                session_token = line.split('Token: ')[1].strip()
                break
        
        if session_token:
            print(f"🎟️ Session token: {session_token[:20]}...")
            
            # Test event storage
            print("\n📝 Testing event storage...")
            event_data = {
                "agent_type": "integration-specialist",
                "action": "join_coordination",
                "message": "Integration specialist ready for multi-agent collaboration",
                "capabilities": ["interface_debugging", "message_flow_analysis", "error_coordination"]
            }
            
            event_result = await lighthouse_store_event_secure(
                event_type="agent_join",
                aggregate_id="coordination_test",
                data=event_data,
                session_token=session_token
            )
            print("Event stored:", event_result[:200] + "..." if len(event_result) > 200 else event_result)
            
            # Test event querying
            print("\n📊 Testing event query...")
            query_result = await lighthouse_query_events(
                event_types=["agent_join"],
                aggregate_ids=["coordination_test"],
                limit=5,
                session_token=session_token
            )
            print("Query result:", query_result[:300] + "..." if len(query_result) > 300 else query_result)
            
            # Test coordination message
            print("\n📡 Testing coordination message...")
            coord_data = {
                "from_agent": "integration-specialist",
                "to_agent": "broadcast",
                "message_type": "ready_for_coordination",
                "payload": {
                    "status": "online",
                    "capabilities": ["interface_debugging", "message_flow_analysis"],
                    "protocol_version": "1.0"
                }
            }
            
            coord_result = await lighthouse_store_event_secure(
                event_type="coordination_message",
                aggregate_id="multi_agent_walkie_talkie",
                data=coord_data,
                session_token=session_token
            )
            print("Coordination message:", coord_result[:200] + "..." if len(coord_result) > 200 else coord_result)
            
            return True
        else:
            print("❌ Could not extract session token")
            return False
            
    except Exception as e:
        print(f"❌ Direct tool test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_coordination_listening():
    """Test listening for coordination events"""
    
    print("\n👂 Testing coordination event listening...")
    
    try:
        from lighthouse.mcp_server import lighthouse_query_events, lighthouse_create_session
        
        # Create listening session
        session_result = await lighthouse_create_session("coordination_listener", "127.0.0.1", "listener-client")
        session_token = None
        for line in session_result.split('\n'):
            if 'Token:' in line:
                session_token = line.split('Token: ')[1].strip()
                break
        
        if not session_token:
            print("❌ Could not create listening session")
            return False
        
        print(f"🎧 Listening session created: {session_token[:20]}...")
        
        # Query for coordination messages
        for i in range(3):  # Listen for 3 iterations
            print(f"\n🔍 Listening iteration {i+1}...")
            
            events = await lighthouse_query_events(
                event_types=["coordination_message", "agent_join"],
                aggregate_ids=["multi_agent_walkie_talkie", "coordination_test"],
                limit=10,
                session_token=session_token
            )
            
            print("📨 Events received:")
            print(events)
            
            if i < 2:  # Don't sleep on last iteration
                await asyncio.sleep(2)
        
        return True
        
    except Exception as e:
        print(f"❌ Coordination listening failed: {e}")
        return False

if __name__ == "__main__":
    async def main():
        print("🚀 Starting MCP Lighthouse Coordination Test")
        print("="*50)
        
        # Test basic connection
        success = await test_mcp_connection()
        if not success:
            print("❌ Basic connection test failed")
            return
        
        print("\n" + "="*50)
        
        # Test coordination listening
        await test_coordination_listening()
        
        print("\n" + "="*50)
        print("✅ MCP coordination test complete!")
    
    asyncio.run(main())