"""Pytest configuration and fixtures."""

import pytest
import asyncio
import sys
from pathlib import Path

# Add src directory to Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_log_file(tmp_path):
    """Create a temporary log file for testing."""
    log_file = tmp_path / "test_lighthouse.log"
    return log_file


@pytest.fixture
def sample_commands():
    """Sample commands for testing."""
    return {
        'safe_commands': [
            {
                "tool_name": "Read",
                "tool_input": {"file_path": "/home/user/test.txt"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Grep", 
                "tool_input": {"pattern": "test", "path": "/tmp"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
                "agent_id": "test_agent"
            }
        ],
        'risky_commands': [
            {
                "tool_name": "Bash",
                "tool_input": {"command": "sudo apt update"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/tmp/test.txt", "content": "large content" * 1000},
                "agent_id": "test_agent"
            }
        ],
        'dangerous_commands': [
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/etc/passwd", "content": "malicious"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "dd if=/dev/zero of=/dev/sda"},
                "agent_id": "test_agent"
            }
        ]
    }