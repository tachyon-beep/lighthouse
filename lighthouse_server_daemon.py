#!/usr/bin/env python3
"""
Lighthouse Server Daemon - Persistent Server for MCP Integration

This script runs the persistent Lighthouse server with REST API only,
without the MCP server main loop. This allows it to be used as a 
backend service for the thin MCP interface.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def main():
    """Run the persistent Lighthouse server daemon"""
    try:
        from lighthouse.mcp_server import initialize_bridge_integration, start_rest_api_server
        from lighthouse.mcp_server import mcp_logger
        
        print("🚀 Starting Lighthouse Server Daemon")
        print("   Mode: REST API only (no MCP main loop)")
        print("   Port: 8765")
        print("   Purpose: Backend for thin MCP interface")
        print()
        
        # Initialize Bridge integration
        mcp_logger.info("🔧 Initializing Lighthouse Bridge...")
        success = await initialize_bridge_integration()
        
        if not success:
            print("❌ Failed to initialize Lighthouse Bridge", file=sys.stderr)
            sys.exit(1)
        
        # Start REST API server
        mcp_logger.info("🌐 Starting REST API server...")
        rest_started = start_rest_api_server(8765)
        
        if not rest_started:
            print("❌ Failed to start REST API server", file=sys.stderr)
            sys.exit(1)
        
        print("✅ Lighthouse Server Daemon is running!")
        print("   REST API: http://localhost:8765")
        print("   Health: http://localhost:8765/health")
        print("   Status: http://localhost:8765/status")
        print()
        print("Press Ctrl+C to shutdown...")
        
        # Keep server running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutdown requested...")
            
        # Cleanup
        from lighthouse.mcp_server import stop_rest_api_server, shutdown_bridge_integration
        
        print("🧹 Cleaning up...")
        stop_rest_api_server()
        await shutdown_bridge_integration()
        print("✅ Shutdown complete")
        
    except Exception as e:
        print(f"❌ Server daemon error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Server daemon stopped")
        sys.exit(0)