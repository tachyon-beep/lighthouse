#!/usr/bin/env python3
"""
Bridge Server Runner
Starts the Lighthouse Bridge AND HTTP server
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure logging
logging.basicConfig(
    level=os.environ.get('LIGHTHOUSE_LOG_LEVEL', 'INFO'),
    format='[%(levelname)s] %(asctime)s - %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point - runs HTTP server which manages Bridge"""
    
    # Configuration from environment
    host = os.environ.get('LIGHTHOUSE_HOST', '0.0.0.0')
    port = int(os.environ.get('LIGHTHOUSE_PORT', '8765'))
    
    logger.info(f"Starting Lighthouse Bridge with HTTP API...")
    logger.info(f"HTTP Server: {host}:{port}")
    
    # Import and run the HTTP server (which will start the Bridge)
    from lighthouse.bridge.http_server import run_server
    
    # Run the HTTP server (this will block and handle Bridge lifecycle)
    run_server(host=host, port=port)

if __name__ == "__main__":
    main()