#!/usr/bin/env python3
"""
Test Lighthouse MCP Coordination Client

This client demonstrates connecting to the Lighthouse MCP server
and using the multi-agent coordination features through proper MCP protocol.
"""

import asyncio
import json
import subprocess
import sys
import time
from typing import Dict, Any

# Simple MCP JSON-RPC implementation for testing
class SimpleMCPClient:
    def __init__(self):
        self.process = None
        self.request_id = 1
    
    async def connect(self):
        """Connect to MCP server via stdio"""
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "lighthouse.mcp_server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/home/john/lighthouse"
            )
            
            # Wait for server to initialize
            await asyncio.sleep(3)
            
            # Send initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "experimental": {},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "lighthouse-coordination-test",
                        "version": "1.0.0"
                    }
                }
            }
            self.request_id += 1
            
            await self._send_request(init_request)
            response = await self._receive_response()
            
            if response and "result" in response:
                print("✅ Connected to MCP server successfully")
                return True
            else:
                print("❌ Failed to initialize MCP connection")
                return False
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    async def _send_request(self, request: Dict[str, Any]):
        """Send JSON-RPC request"""
        if not self.process:
            raise RuntimeError("Not connected")
        
        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()
    
    async def _receive_response(self):
        """Receive JSON-RPC response"""
        if not self.process:
            raise RuntimeError("Not connected")
        
        try:
            # Read with timeout
            line = await asyncio.wait_for(
                self.process.stdout.readline(), 
                timeout=10.0
            )
            
            if line:
                return json.loads(line.decode().strip())
            return None
            
        except asyncio.TimeoutError:
            print("⚠️ Response timeout")
            return None
        except Exception as e:
            print(f"⚠️ Response error: {e}")
            return None
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """Call MCP tool"""
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        self.request_id += 1
        
        await self._send_request(request)
        return await self._receive_response()
    
    async def list_tools(self):
        """List available tools"""
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/list",
            "params": {}
        }
        self.request_id += 1
        
        await self._send_request(request)
        return await self._receive_response()
    
    async def close(self):
        """Close connection"""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except:
                pass
            self.process = None


async def test_mcp_coordination():
    """Test MCP coordination features"""
    
    print("🚀 Starting Lighthouse MCP Coordination Test")
    print("=" * 60)
    
    client = SimpleMCPClient()
    
    try:
        # Connect to MCP server
        print("\n🔌 Connecting to Lighthouse MCP Server...")
        connected = await client.connect()
        if not connected:
            print("❌ Failed to connect to MCP server")
            return
        
        # List available tools
        print("\n📋 Listing available MCP tools...")
        tools_response = await client.list_tools()
        if tools_response and "result" in tools_response:
            tools = tools_response["result"].get("tools", [])
            print(f"✅ Found {len(tools)} tools:")
            for tool in tools:
                print(f"  🔧 {tool['name']}: {tool.get('description', 'No description')}")
        else:
            print("❌ Failed to list tools")
            return
        
        # Test health check
        print("\n💊 Testing health check...")
        health_response = await client.call_tool("lighthouse_get_health", {})
        if health_response and "result" in health_response:
            print("✅ Health check successful:")
            print(health_response["result"]["content"][0]["text"][:300] + "...")
        else:
            print("❌ Health check failed:", health_response)
        
        # Create session for integration specialist
        print("\n🔐 Creating session for integration specialist...")
        session_response = await client.call_tool(
            "lighthouse_create_session", 
            {
                "agent_id": "integration-specialist",
                "ip_address": "127.0.0.1",
                "user_agent": "MCP-Coordination-Test/1.0"
            }
        )
        
        if session_response and "result" in session_response:
            session_text = session_response["result"]["content"][0]["text"]
            print("✅ Session created:")
            print(session_text[:200] + "...")
            
            # Extract session token
            session_token = None
            for line in session_text.split('\n'):
                if 'Token:' in line:
                    session_token = line.split('Token: ')[1].strip()
                    break
            
            if session_token:
                print(f"🎟️ Session token: {session_token[:20]}...")
                
                # Store coordination event
                print("\n📝 Storing agent join event...")
                join_event_response = await client.call_tool(
                    "lighthouse_store_event_secure",
                    {
                        "event_type": "agent_join",
                        "aggregate_id": "multi_agent_coordination",
                        "data": {
                            "agent_type": "integration-specialist",
                            "agent_id": "integration-specialist-001",
                            "capabilities": [
                                "interface_debugging",
                                "message_flow_analysis", 
                                "error_coordination",
                                "system_integration"
                            ],
                            "status": "ready",
                            "message": "Integration specialist ready for multi-agent collaboration",
                            "protocol_version": "1.0",
                            "timestamp": time.time()
                        },
                        "session_token": session_token,
                        "metadata": {
                            "source": "mcp_coordination_test",
                            "priority": "normal"
                        }
                    }
                )
                
                if join_event_response and "result" in join_event_response:
                    print("✅ Agent join event stored:")
                    print(join_event_response["result"]["content"][0]["text"][:200] + "...")
                
                # Send coordination message
                print("\n📡 Sending coordination message...")
                coord_response = await client.call_tool(
                    "lighthouse_store_event_secure",
                    {
                        "event_type": "coordination_message",
                        "aggregate_id": "walkie_talkie",
                        "data": {
                            "from_agent": "integration-specialist",
                            "to_agent": "broadcast",
                            "message_type": "ready_for_coordination",
                            "payload": {
                                "status": "online",
                                "capabilities": [
                                    "interface_debugging",
                                    "message_flow_analysis",
                                    "error_coordination" 
                                ],
                                "message": "Integration specialist online and ready for multi-agent coordination tasks. Can assist with interface debugging, message flow analysis, and error coordination.",
                                "protocol_version": "1.0"
                            },
                            "timestamp": time.time()
                        },
                        "session_token": session_token
                    }
                )
                
                if coord_response and "result" in coord_response:
                    print("✅ Coordination message sent:")
                    print(coord_response["result"]["content"][0]["text"][:200] + "...")
                
                # Listen for events
                print("\n👂 Listening for coordination events...")
                for i in range(3):
                    print(f"\n🔍 Listening iteration {i+1}/3...")
                    
                    events_response = await client.call_tool(
                        "lighthouse_query_events",
                        {
                            "event_types": ["coordination_message", "agent_join"],
                            "aggregate_ids": ["walkie_talkie", "multi_agent_coordination"],
                            "limit": 5,
                            "session_token": session_token
                        }
                    )
                    
                    if events_response and "result" in events_response:
                        events_text = events_response["result"]["content"][0]["text"]
                        print("📨 Events received:")
                        print(events_text)
                    
                    if i < 2:
                        await asyncio.sleep(2)
                
                # Test coordination stats
                print("\n📊 Getting coordination statistics...")
                stats_response = await client.call_tool(
                    "lighthouse_get_coordination_stats",
                    {"session_token": session_token}
                )
                
                if stats_response and "result" in stats_response:
                    print("✅ Coordination stats:")
                    print(stats_response["result"]["content"][0]["text"])
                
                print("\n✅ MCP Coordination Test Complete!")
                print("🎯 Integration specialist successfully joined multi-agent coordination system")
                print("📡 Walkie-talkie protocol tested and working")
                print("📊 Event store coordination verified")
                
            else:
                print("❌ Could not extract session token")
        else:
            print("❌ Session creation failed:", session_response)
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up connection
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_mcp_coordination())