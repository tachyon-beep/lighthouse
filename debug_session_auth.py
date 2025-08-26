#!/usr/bin/env python3
"""
Debug Session Authentication Issues

This script analyzes the session authentication flow to identify
why "Agent X is not authenticated" errors occur even with valid tokens.
"""

import sys
import os
import time
import json

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lighthouse.mcp_server import MCPSessionManager
from lighthouse.mcp_bridge_minimal import MinimalLighthouseBridge
from lighthouse.bridge.security.session_security import SessionSecurityValidator
from lighthouse.event_store.auth import SimpleAuthenticator, AgentRole

async def debug_session_auth():
    """Debug session authentication flow"""
    print("🔍 DEBUGGING SESSION AUTHENTICATION")
    print("=" * 50)
    
    # 1. Initialize Bridge components
    print("\n1. Initializing Bridge components...")
    
    bridge = MinimalLighthouseBridge("debug_project")
    await bridge.initialize()
    
    session_manager = MCPSessionManager(bridge)
    
    # 2. Create a session for broadcast_coordinator
    print("\n2. Creating session for broadcast_coordinator...")
    
    agent_id = "broadcast_coordinator"
    session = await session_manager.create_session(agent_id, "127.0.0.1", "debug_script")
    
    print(f"✅ Session created:")
    print(f"   Agent ID: {session.agent_id}")
    print(f"   Session ID: {session.session_id}")
    print(f"   Token: {session.session_token}")
    print(f"   State: {session.state}")
    print(f"   Created: {session.created_at}")
    
    # 3. Parse session token
    print(f"\n3. Parsing session token...")
    token_parts = session.session_token.split(":")
    print(f"   Token parts count: {len(token_parts)}")
    for i, part in enumerate(token_parts):
        if i == 3:  # Don't print full HMAC for security
            print(f"   Part {i+1}: {part[:20]}... (HMAC signature)")
        else:
            print(f"   Part {i+1}: {part}")
    
    # 4. Validate session using session manager
    print(f"\n4. Validating session using SessionManager...")
    
    validated_session = await session_manager.validate_session(session.session_token, agent_id)
    if validated_session:
        print(f"✅ SessionManager validation: SUCCESS")
        print(f"   Validated agent: {validated_session.agent_id}")
        print(f"   Session state: {validated_session.state}")
    else:
        print(f"❌ SessionManager validation: FAILED")
    
    # 5. Check Bridge session security directly
    print(f"\n5. Checking Bridge SessionSecurityValidator...")
    
    is_valid = bridge.session_security.validate_session(session.session_token, agent_id)
    print(f"   Direct validation result: {is_valid}")
    
    # 6. Check active sessions in Bridge
    print(f"\n6. Checking active sessions in Bridge...")
    print(f"   Active sessions count: {len(bridge.session_security.active_sessions)}")
    for sid, sess in bridge.session_security.active_sessions.items():
        print(f"   Session {sid}: agent={sess.agent_id}, state={sess.state}")
    
    # 7. Check EventStore authentication
    print(f"\n7. Checking EventStore authentication...")
    if bridge.event_store:
        # Use the correct method name from the store
        authenticated_agent = bridge.event_store.get_agent_identity(agent_id)
        if authenticated_agent:
            print(f"✅ EventStore authentication: SUCCESS")
            print(f"   Agent: {authenticated_agent.agent_id}")
            print(f"   Role: {authenticated_agent.role}")
            print(f"   Permissions: {list(authenticated_agent.permissions)}")
            print(f"   Expired: {authenticated_agent.is_expired()}")
        else:
            print(f"❌ EventStore authentication: FAILED - Agent not found")
            
            # Try to authenticate with EventStore
            print(f"\n7b. Attempting EventStore authentication...")
            try:
                # Create token in correct format for EventStore
                auth_token = bridge.event_store.create_agent_token(agent_id)
                print(f"   Created auth token: {auth_token}")
                
                # Authenticate
                identity = bridge.event_store.authenticate_agent(
                    agent_id, auth_token, "agent"
                )
                print(f"✅ EventStore authentication successful:")
                print(f"   Agent: {identity.agent_id}")
                print(f"   Role: {identity.role}")
                
                # Check again
                authenticated_agent = bridge.event_store.get_agent_identity(agent_id)
                if authenticated_agent:
                    print(f"✅ Now authenticated in EventStore")
                else:
                    print(f"❌ Still not authenticated in EventStore")
                    
            except Exception as e:
                print(f"❌ EventStore authentication failed: {e}")
    
    # 8. Test the _validate_agent_access function
    print(f"\n8. Testing _validate_agent_access function...")
    
    # Import the function from mcp_server
    from lighthouse.mcp_server import _validate_agent_access
    
    # Set global variables that the function uses
    import lighthouse.mcp_server
    lighthouse.mcp_server.session_manager = session_manager
    lighthouse.mcp_server.bridge = bridge
    
    try:
        access_granted = await _validate_agent_access(
            session.session_token, 
            agent_id, 
            "annotation", 
            "test_file.py"
        )
        if access_granted:
            print(f"✅ _validate_agent_access: SUCCESS")
        else:
            print(f"❌ _validate_agent_access: FAILED")
    except Exception as e:
        print(f"❌ _validate_agent_access error: {e}")
    
    # 9. Test EventStore authorization directly
    print(f"\n9. Testing EventStore authorization directly...")
    
    if bridge.event_store:
        try:
            # First ensure agent is authenticated in EventStore
            if not bridge.event_store.get_agent_identity(agent_id):
                auth_token = bridge.event_store.create_agent_token(agent_id)
                bridge.event_store.authenticate_agent(agent_id, auth_token, "agent")
            
            # Test authorization
            authorized = bridge.event_store.authorizer.authorize_write(agent_id, 1)
            print(f"✅ EventStore authorization: SUCCESS")
            print(f"   Authorized agent: {authorized.agent_id}")
        except Exception as e:
            print(f"❌ EventStore authorization failed: {e}")
    
    # 10. Test the exact scenario from your error
    print(f"\n10. Testing exact MCP function scenario...")
    
    try:
        # Test lighthouse_shadow_annotate specifically
        from lighthouse.mcp_server import lighthouse_shadow_annotate
        
        # Set up global session manager
        import lighthouse.mcp_server
        lighthouse.mcp_server.session_manager = session_manager
        lighthouse.mcp_server.bridge = bridge
        
        # Test the function that was failing
        result = await lighthouse_shadow_annotate(
            file_path="test.py",
            line=10,
            message="Test annotation",
            category="debug",
            session_token=session.session_token
        )
        
        if "Access denied" in result:
            print(f"❌ lighthouse_shadow_annotate: ACCESS DENIED")
            print(f"   Result: {result}")
        else:
            print(f"✅ lighthouse_shadow_annotate: SUCCESS")
            print(f"   Result: {result[:100]}...")
            
    except Exception as e:
        print(f"❌ lighthouse_shadow_annotate error: {e}")
    
    # 11. Summary and recommendations
    print(f"\n11. SUMMARY AND RECOMMENDATIONS")
    print("=" * 40)
    
    if validated_session and is_valid:
        print("✅ Session validation is working correctly")
        
        # Check if EventStore authentication is the problem
        authenticated_agent = bridge.event_store.get_agent_identity(agent_id)
        if not authenticated_agent:
            print("❌ ISSUE FOUND: EventStore authentication missing")
            print("   The session is valid but the agent is not authenticated in EventStore")
            print("   This explains the 'Agent X is not authenticated' error")
        else:
            print("✅ EventStore authentication is working")
    else:
        print("❌ Session validation is failing")
        print("   Check the session token format and validation logic")
    
    print(f"\nRECOMMENDATIONS:")
    print(f"1. Ensure EventStore authenticator is properly initialized")
    print(f"2. Sync session creation with EventStore authentication")
    print(f"3. Add automatic EventStore authentication during session creation") 
    print(f"4. Add debug logging to trace authentication failures")
    
    return session  # Return for further testing

if __name__ == "__main__":
    import asyncio
    asyncio.run(debug_session_auth())