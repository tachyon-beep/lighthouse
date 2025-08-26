#!/usr/bin/env python3
"""
Simple MCP coordination test using subprocess
"""

import subprocess
import json
import sys
import time

def test_mcp_tools():
    """Test MCP tools through direct subprocess call"""
    
    print("🚀 Simple MCP Coordination Test")
    print("=" * 40)
    
    # Test the MCP server by directly calling the tools
    try:
        print("\n🧪 Testing MCP tools via import...")
        
        # Test import and initialization
        test_script = """
import sys
sys.path.insert(0, 'src')
import asyncio

async def test():
    try:
        # Import and initialize
        from lighthouse.mcp_server import initialize_bridge_integration
        from lighthouse.mcp_server import lighthouse_get_health, lighthouse_create_session, lighthouse_store_event_secure, lighthouse_query_events
        
        print("Initializing Bridge...")
        success = await initialize_bridge_integration()
        if not success:
            print("❌ Bridge initialization failed")
            return
        
        print("✅ Bridge initialized successfully")
        
        # Test health
        print("Testing health check...")
        health = await lighthouse_get_health("")
        print(f"Health: {health[:100]}...")
        
        # Create session
        print("Creating session...")
        session_result = await lighthouse_create_session("integration-specialist", "127.0.0.1", "test-client")
        print(f"Session: {session_result[:100]}...")
        
        # Extract token
        session_token = None
        for line in session_result.split('\\n'):
            if 'Token:' in line:
                session_token = line.split('Token: ')[1].strip()
                break
        
        if session_token:
            print(f"Token: {session_token[:20]}...")
            
            # Store coordination event
            event_data = {
                "agent_type": "integration-specialist",
                "action": "join_coordination",
                "message": "Integration specialist ready for multi-agent collaboration",
                "capabilities": ["interface_debugging", "message_flow_analysis", "error_coordination"]
            }
            
            event_result = await lighthouse_store_event_secure(
                "agent_join", "coordination_test", event_data, session_token
            )
            print(f"Event: {event_result[:100]}...")
            
            # Query events
            query_result = await lighthouse_query_events(
                ["agent_join"], ["coordination_test"], 5, session_token
            )
            print(f"Query: {query_result[:200]}...")
            
            print("✅ MCP coordination test successful!")
        else:
            print("❌ Could not extract session token")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
        """
        
        # Run the test script
        result = subprocess.run([
            sys.executable, "-c", test_script
        ], capture_output=True, text=True, timeout=30, cwd="/home/john/lighthouse")
        
        if result.returncode == 0:
            print("✅ Direct MCP test successful:")
            print(result.stdout)
            
            if result.stderr:
                print("📋 Debug output:")
                print(result.stderr[-500:])  # Last 500 chars
                
        else:
            print("❌ Direct MCP test failed:")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_mcp_tools()