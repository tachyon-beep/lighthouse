#!/usr/bin/env python3
"""
Validation hook script for Claude Code.
This script validates commands before they are executed by Claude.
"""

import json
import sys
import time
import logging
from typing import Dict, Any, Optional

try:
    import requests
except ImportError:
    # Fallback if requests not available
    import urllib.request
    import urllib.parse
    requests = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/lighthouse_hook.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("lighthouse-hook")

class ValidationClient:
    """Client for communicating with the validation bridge."""
    
    def __init__(self, bridge_url: str = "http://localhost:8765"):
        self.bridge_url = bridge_url
    
    def validate_command(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to validation bridge."""
        try:
            if requests:
                response = requests.post(
                    f"{self.bridge_url}/validate",
                    json=command_data,
                    timeout=5.0
                )
                return response.json()
            else:
                # Fallback using urllib
                data = json.dumps(command_data).encode('utf-8')
                req = urllib.request.Request(
                    f"{self.bridge_url}/validate",
                    data=data,
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req, timeout=5.0) as response:
                    return json.loads(response.read().decode('utf-8'))
                    
        except Exception as e:
            logger.error(f"Bridge communication failed: {e}")
            return self._fallback_validation(command_data)
    
    def _fallback_validation(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback validation when bridge is unavailable."""
        tool_name = command_data.get('tool', '')
        tool_input = command_data.get('input', {})
        
        # Basic safety checks
        if tool_name == 'Bash':
            command = tool_input.get('command', '')
            if any(dangerous in command.lower() for dangerous in 
                   ['rm -rf /', 'rm -rf *', 'sudo rm', '> /dev/', 'dd if=', 'mkfs', 'shutdown']):
                return {
                    'status': 'blocked',
                    'reason': 'Dangerous command detected (fallback validation)',
                    'concern': 'Bridge offline - blocking dangerous command'
                }
        
        if tool_name in ['Write', 'Edit', 'MultiEdit']:
            file_path = tool_input.get('file_path', '')
            if any(file_path.startswith(path) for path in ['/etc/', '/usr/', '/var/', '/boot/']):
                return {
                    'status': 'blocked',
                    'reason': 'System file modification (fallback validation)',
                    'concern': 'Bridge offline - blocking system file changes'
                }
        
        # Safe by default for known tools
        if tool_name in ['Read', 'Glob', 'Grep', 'LS']:
            return {'status': 'approved', 'reason': 'Safe tool (fallback)'}
        
        # Unknown tools - proceed with caution
        logger.warning(f"Unknown tool {tool_name} - proceeding (bridge offline)")
        return {'status': 'approved', 'reason': 'Bridge offline - allowing unknown tool'}

def main():
    """Main hook execution function."""
    try:
        # Read the command data from stdin
        input_data = sys.stdin.read()
        if not input_data.strip():
            logger.error("No input data received")
            sys.exit(1)
        
        try:
            data = json.loads(input_data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON input: {e}")
            sys.exit(1)
        
        logger.info(f"Validating command: {data.get('tool_name')} for agent {data.get('agent_id', 'unknown')}")
        
        # Create command data for validation
        command_data = {
            'id': f"cmd_{int(time.time()*1000)}",
            'tool': data.get('tool_name'),
            'input': data.get('tool_input', {}),
            'agent': data.get('agent_id', 'unknown'),
            'timestamp': time.time()
        }
        
        # Send to validation bridge
        client = ValidationClient()
        result = client.validate_command(command_data)
        
        logger.info(f"Validation result: {result.get('status')} - {result.get('reason')}")
        
        # Handle the validation result
        status = result.get('status', 'blocked')
        
        if status == 'approved':
            # Allow the command to proceed
            logger.info("Command approved - proceeding")
            sys.exit(0)
        
        elif status == 'review_required':
            # Block and request manual review
            concern = result.get('concern', 'Manual review required')
            reason = result.get('reason', 'Command requires validation')
            
            print(f"REVIEW REQUIRED: {reason}", file=sys.stderr)
            print(f"Concern: {concern}", file=sys.stderr)
            print("Join the validation bridge to discuss this command", file=sys.stderr)
            
            logger.warning(f"Command blocked for review: {reason}")
            sys.exit(2)  # Block command with message
        
        else:  # blocked
            # Block the command
            reason = result.get('reason', 'Command blocked by validator')
            concern = result.get('concern', 'Security policy violation')
            
            print(f"BLOCKED: {reason}", file=sys.stderr)
            print(f"Concern: {concern}", file=sys.stderr)
            
            logger.error(f"Command blocked: {reason}")
            sys.exit(2)  # Block command with message
    
    except Exception as e:
        logger.error(f"Hook execution failed: {e}")
        # Fail safe - block unknown errors
        print(f"HOOK ERROR: {str(e)}", file=sys.stderr)
        print("Contact system administrator", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()