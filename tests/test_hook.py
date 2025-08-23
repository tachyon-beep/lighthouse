"""Tests for the validation hook."""

import json
import subprocess
import sys
from pathlib import Path


def test_hook_safe_command():
    """Test hook with safe command."""
    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
    
    test_input = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/home/user/test.txt"},
        "agent_id": "test_agent"
    }
    
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(test_input),
        text=True,
        capture_output=True
    )
    
    # Should exit with code 0 (approved) for safe commands
    assert result.returncode == 0


def test_hook_dangerous_command():
    """Test hook with dangerous command."""
    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
    
    test_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"},
        "agent_id": "test_agent"
    }
    
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(test_input),
        text=True,
        capture_output=True
    )
    
    # Should exit with code 2 (blocked) for dangerous commands
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr or "blocked" in result.stderr.lower()


def test_hook_invalid_input():
    """Test hook with invalid JSON input."""
    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
    
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input="invalid json",
        text=True,
        capture_output=True
    )
    
    # Should exit with non-zero code for invalid input
    assert result.returncode != 0


def test_hook_empty_input():
    """Test hook with empty input."""
    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
    
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input="",
        text=True,
        capture_output=True
    )
    
    # Should exit with non-zero code for empty input
    assert result.returncode != 0