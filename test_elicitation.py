#!/usr/bin/env python3
"""
Test script for FEATURE_PACK_0 Elicitation Implementation

This script tests the basic functionality of the elicitation system:
1. Creating an elicitation request
2. Checking for pending elicitations
3. Responding to an elicitation
4. Verifying the response
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, Any

# Configuration
BRIDGE_URL = "http://localhost:8765"
TIMEOUT = aiohttp.ClientTimeout(total=30)


async def create_session(agent_id: str) -> Dict[str, Any]:
    """Create a session for an agent"""
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            f"{BRIDGE_URL}/session/create",
            json={
                "agent_id": agent_id,
                "ip_address": "127.0.0.1",
                "user_agent": "ElicitationTest/1.0"
            }
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                raise Exception(f"Failed to create session: {resp.status}")


async def test_elicitation():
    """Test the elicitation system"""
    print("=" * 60)
    print("FEATURE_PACK_0 Elicitation System Test")
    print("=" * 60)
    
    # Step 1: Create sessions for two agents
    print("\n1. Creating sessions for agents...")
    session_alpha = await create_session("agent_alpha")
    print(f"   ✓ Agent Alpha session: {session_alpha['session_id']}")
    
    session_beta = await create_session("agent_beta")
    print(f"   ✓ Agent Beta session: {session_beta['session_id']}")
    
    # Step 2: Create an elicitation request from Alpha to Beta
    print("\n2. Creating elicitation request...")
    elicitation_schema = {
        "type": "object",
        "properties": {
            "favorite_color": {"type": "string"},
            "lucky_number": {"type": "integer"}
        },
        "required": ["favorite_color", "lucky_number"]
    }
    
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            f"{BRIDGE_URL}/elicitation/create",
            json={
                "from_agent": "agent_alpha",
                "to_agent": "agent_beta",
                "message": "Please share your favorite color and lucky number",
                "schema": elicitation_schema,
                "timeout_seconds": 60
            },
            headers={"Authorization": f"Bearer {session_alpha['session_token']}"}
        ) as resp:
            if resp.status == 200:
                elicitation_data = await resp.json()
                elicitation_id = elicitation_data["elicitation_id"]
                print(f"   ✓ Elicitation created: {elicitation_id}")
            else:
                error = await resp.text()
                raise Exception(f"Failed to create elicitation: {resp.status} - {error}")
    
    # Step 3: Check for pending elicitations for Beta
    print("\n3. Checking pending elicitations for Beta...")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{BRIDGE_URL}/elicitation/pending",
            params={"agent_id": "agent_beta"},
            headers={"Authorization": f"Bearer {session_beta['session_token']}"}
        ) as resp:
            if resp.status == 200:
                pending_data = await resp.json()
                print(f"   ✓ Found {pending_data['count']} pending elicitation(s)")
                if pending_data['count'] > 0:
                    for elicit in pending_data['elicitations']:
                        print(f"      - ID: {elicit['id']}")
                        print(f"        From: {elicit['from_agent']}")
                        print(f"        Message: {elicit['message']}")
            else:
                error = await resp.text()
                print(f"   ✗ Failed to get pending elicitations: {error}")
    
    # Step 4: Beta responds to the elicitation
    print("\n4. Beta responding to elicitation...")
    response_data = {
        "favorite_color": "blue",
        "lucky_number": 42
    }
    
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            f"{BRIDGE_URL}/elicitation/respond",
            json={
                "elicitation_id": elicitation_id,
                "responding_agent": "agent_beta",
                "response_type": "accept",
                "data": response_data
            },
            headers={"Authorization": f"Bearer {session_beta['session_token']}"}
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"   ✓ Response sent: {result['message']}")
            else:
                error = await resp.text()
                print(f"   ✗ Failed to respond: {resp.status} - {error}")
    
    # Step 5: Check elicitation status
    print("\n5. Checking elicitation status...")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{BRIDGE_URL}/elicitation/status/{elicitation_id}",
            headers={"Authorization": f"Bearer {session_alpha['session_token']}"}
        ) as resp:
            if resp.status == 200:
                status = await resp.json()
                print(f"   ✓ Status: {status['status']}")
                if status.get('responded_at'):
                    print(f"     Response received at: {status['responded_at']}")
            else:
                error = await resp.text()
                print(f"   ✗ Failed to get status: {error}")
    
    # Step 6: Get elicitation metrics
    print("\n6. Getting elicitation metrics...")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{BRIDGE_URL}/elicitation/metrics",
            headers={"Authorization": f"Bearer {session_alpha['session_token']}"}
        ) as resp:
            if resp.status == 200:
                metrics = await resp.json()
                print("   ✓ Metrics retrieved:")
                print(f"     Performance: P50={metrics.get('performance', {}).get('p50_latency_ms', 'N/A')}ms")
                print(f"     Security: Rate limit violations={metrics.get('security', {}).get('rate_limit_violations', 0)}")
                print(f"     Activity: Active={metrics.get('activity', {}).get('active_elicitations', 0)}")
            else:
                error = await resp.text()
                print(f"   ✗ Failed to get metrics: {error}")
    
    print("\n" + "=" * 60)
    print("✅ FEATURE_PACK_0 Elicitation Test Complete!")
    print("=" * 60)


async def main():
    """Main test runner"""
    try:
        # Check if Bridge is running
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(f"{BRIDGE_URL}/health") as resp:
                if resp.status != 200:
                    print("❌ Bridge is not running!")
                    print("Please start the Bridge first:")
                    print("  docker run -p 8765:8765 lighthouse-bridge")
                    sys.exit(1)
        
        # Run the test
        await test_elicitation()
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


I GUESS I DIDN'T FUCK THIS TASK UP.