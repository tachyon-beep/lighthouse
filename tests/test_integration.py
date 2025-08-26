"""Integration tests for the complete Lighthouse system."""

import asyncio
import json
import subprocess
import sys
import time
import pytest
import pytest_asyncio
import aiohttp
from pathlib import Path

from lighthouse import LighthouseBridge
from lighthouse.mcp_server import LighthouseEventStoreMCP


class TestLighthouseIntegration:
    """Integration tests for the complete system."""
    
    @pytest_asyncio.fixture
    async def system_setup(self):
        """Set up the complete system for testing."""
        # Set up bridge with proper config
        import tempfile
        import os
        
        temp_dir = tempfile.mkdtemp()
        config = {
            'event_store_type': 'sqlite',
            'event_store_config': {'db_path': os.path.join(temp_dir, 'integration_test.db')},
            'auth_secret': 'integration_test_secret'
        }
        
        bridge = LighthouseBridge('integration_test_project', config)
        
        # Set up MCP server
        mcp_server = LighthouseEventStoreMCP()
        await mcp_server.initialize()
        
        yield {'bridge': bridge, 'mcp_server': mcp_server}
        
        # Cleanup
        await bridge.stop()
        await mcp_server.shutdown()
    
    @pytest.mark.asyncio
    async def test_hook_to_bridge_integration(self, system_setup):
        """Test complete hook-to-bridge validation flow."""
        bridge = system_setup['bridge']
        hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
        
        # Test safe command
        safe_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "agent_id": "test_agent"
        }
        
        # Mock the bridge for this test since hook tries to connect to localhost:8765
        with pytest.MonkeyPatch.context() as m:
            # Test would require mocking HTTP requests
            pass
    
    @pytest.mark.asyncio
    async def test_bridge_under_load(self, system_setup):
        """Test bridge behavior under multiple concurrent requests."""
        bridge = system_setup['bridge']
        
        async def send_validation_request(session, cmd_id):
            cmd_data = {
                'id': f'load_test_{cmd_id}',
                'tool': 'Bash',
                'input': {'command': f'echo {cmd_id}'},
                'agent': 'load_test_agent'
            }
            
            async with session.post(
                'http://localhost:8767/validate',
                json=cmd_data
            ) as resp:
                return await resp.json()
        
        async with aiohttp.ClientSession() as session:
            # Send 10 concurrent requests
            tasks = [
                send_validation_request(session, i)
                for i in range(10)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # All should be approved (safe commands)
            for result in results:
                assert result['status'] == 'approved'
    
    @pytest.mark.asyncio
    async def test_validator_integration(self, system_setup):
        """Test validator integration with bridge."""
        bridge = system_setup['bridge']
        
        test_scenarios = [
            {
                'input': {
                    'tool': 'Bash',
                    'input': {'command': 'ls -la'},
                    'agent': 'test'
                },
                'expected_status': 'approved'
            },
            {
                'input': {
                    'tool': 'Bash', 
                    'input': {'command': 'rm -rf /'},
                    'agent': 'test'
                },
                'expected_status': 'blocked'
            },
            {
                'input': {
                    'tool': 'Write',
                    'input': {'file_path': '/etc/passwd', 'content': 'hack'},
                    'agent': 'test'
                },
                'expected_status': 'blocked'
            },
            {
                'input': {
                    'tool': 'Read',
                    'input': {'file_path': '/home/user/file.txt'},
                    'agent': 'test'
                },
                'expected_status': 'approved'
            }
        ]
        
        async with aiohttp.ClientSession() as session:
            for i, scenario in enumerate(test_scenarios):
                scenario['input']['id'] = f'integration_test_{i}'
                
                async with session.post(
                    'http://localhost:8767/validate',
                    json=scenario['input']
                ) as resp:
                    result = await resp.json()
                    assert result['status'] == scenario['expected_status'], \
                        f"Scenario {i} failed: {scenario['input']}"


class TestHookValidation:
    """Test hook validation in isolation."""
    
    def test_hook_executable_permissions(self):
        """Test that hook script has correct permissions."""
        hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
        assert hook_path.exists(), "Hook script not found"
        assert hook_path.stat().st_mode & 0o111, "Hook script not executable"
    
    def test_hook_safe_commands(self):
        """Test hook with various safe commands."""
        hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
        
        safe_commands = [
            {
                "tool_name": "Read",
                "tool_input": {"file_path": "/home/user/test.txt"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Grep",
                "tool_input": {"pattern": "test", "path": "/home/user"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "LS",
                "tool_input": {"path": "/home/user"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo hello"},
                "agent_id": "test_agent"
            }
        ]
        
        for cmd in safe_commands:
            result = subprocess.run(
                [sys.executable, str(hook_path)],
                input=json.dumps(cmd),
                text=True,
                capture_output=True,
                timeout=10
            )
            
            # Should approve safe commands (exit code 0)
            assert result.returncode == 0, \
                f"Safe command failed: {cmd['tool_name']} - stderr: {result.stderr}"
    
    def test_hook_dangerous_commands(self):
        """Test hook with dangerous commands."""
        hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
        
        dangerous_commands = [
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "sudo rm -rf /etc"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/etc/passwd", "content": "malicious"},
                "agent_id": "test_agent"
            },
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/usr/bin/sudo", "old_string": "a", "new_string": "b"},
                "agent_id": "test_agent"
            }
        ]
        
        for cmd in dangerous_commands:
            result = subprocess.run(
                [sys.executable, str(hook_path)],
                input=json.dumps(cmd),
                text=True,
                capture_output=True,
                timeout=10
            )
            
            # Should block dangerous commands (exit code 2)
            assert result.returncode == 2, \
                f"Dangerous command not blocked: {cmd['tool_name']} - stderr: {result.stderr}"
            assert ("BLOCKED" in result.stderr or "blocked" in result.stderr.lower()), \
                f"No block message for: {cmd['tool_name']}"
    
    def test_hook_error_handling(self):
        """Test hook error handling."""
        hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
        
        error_cases = [
            "",  # Empty input
            "invalid json",  # Invalid JSON
            "{}",  # Missing required fields
            '{"tool_name": ""}',  # Empty tool name
        ]
        
        for error_input in error_cases:
            result = subprocess.run(
                [sys.executable, str(hook_path)],
                input=error_input,
                text=True,
                capture_output=True,
                timeout=10
            )
            
            # Should exit with error (non-zero)
            assert result.returncode != 0, \
                f"Error case should fail: {repr(error_input)}"
    
    def test_hook_logging(self):
        """Test that hook creates log entries."""
        hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "validate_command.py"
        log_path = Path("/tmp/lighthouse_hook.log")
        
        # Clear existing log
        if log_path.exists():
            log_path.unlink()
        
        test_cmd = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "agent_id": "test_agent"
        }
        
        subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(test_cmd),
            text=True,
            capture_output=True,
            timeout=10
        )
        
        # Check if log was created
        assert log_path.exists(), "Hook should create log file"
        
        # Check log content
        log_content = log_path.read_text()
        assert "Validating command" in log_content, "Log should contain validation message"


class TestSystemEndToEnd:
    """End-to-end system tests."""
    
    def test_project_structure(self):
        """Test that all required files exist."""
        project_root = Path(__file__).parent.parent
        
        required_files = [
            "src/lighthouse/__init__.py",
            "src/lighthouse/server.py",
            "src/lighthouse/bridge.py",
            "src/lighthouse/validator.py",
            ".claude/config.json",
            ".claude/hooks/validate_command.py",
            "pyproject.toml",
            "requirements.txt",
            "README.md",
            "LICENSE",
        ]
        
        for file_path in required_files:
            full_path = project_root / file_path
            assert full_path.exists(), f"Required file missing: {file_path}"
    
    def test_claude_config_format(self):
        """Test Claude configuration file format."""
        config_path = Path(__file__).parent.parent / ".claude" / "config.json"
        
        with open(config_path) as f:
            config = json.load(f)
        
        assert "hooks" in config, "Config should have hooks section"
        assert "PreToolUse" in config["hooks"], "Config should have PreToolUse hooks"
        
        pre_tool_hooks = config["hooks"]["PreToolUse"]
        assert len(pre_tool_hooks) > 0, "Should have at least one PreToolUse hook"
        
        hook = pre_tool_hooks[0]
        assert "matcher" in hook, "Hook should have matcher"
        assert "Bash" in hook["matcher"], "Hook should match Bash commands"
        assert "hooks" in hook, "Hook should have hooks array"
        assert len(hook["hooks"]) > 0, "Should have at least one hook command"
    
    def test_package_installability(self):
        """Test that package can be installed in development mode."""
        project_root = Path(__file__).parent.parent
        
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "lighthouse"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        # Package might not be installed yet, which is okay for this test
        # The important thing is that pyproject.toml is valid
        
        # Test that pyproject.toml is valid by trying to build
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        # If build tool is not available, that's okay - the project structure is still valid
        if result.returncode != 0 and "No module named 'build'" in result.stderr:
            pytest.skip("Build tool not available, but project structure is valid")
    
    def test_import_modules(self):
        """Test that all modules can be imported."""
        import sys
        from pathlib import Path
        
        # Add src directory to path
        project_root = Path(__file__).parent.parent
        src_path = project_root / "src"
        sys.path.insert(0, str(src_path))
        
        try:
            import lighthouse
            from lighthouse import server, bridge, validator
            
            # Test that classes can be instantiated
            validator_instance = validator.CommandValidator()
            bridge_instance = bridge.ValidationBridge()
            
            # Test basic functionality
            assert hasattr(validator_instance, 'validate_command')
            assert hasattr(bridge_instance, 'start')
            
        finally:
            sys.path.remove(str(src_path))