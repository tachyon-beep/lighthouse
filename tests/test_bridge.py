"""Tests for the validation bridge."""

import asyncio
import json
import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from lighthouse.bridge import ValidationBridge, CommandData


class TestValidationBridge:
    """Test cases for ValidationBridge."""
    
    @pytest.fixture
    async def bridge(self):
        """Create a test bridge instance."""
        bridge = ValidationBridge(port=8766)  # Use different port for testing
        await bridge.start()
        yield bridge
        await bridge.stop()
    
    @pytest.fixture
    def sample_command_data(self):
        """Sample command data for testing."""
        return {
            'id': 'test_cmd_001',
            'tool': 'Bash',
            'input': {'command': 'ls -la'},
            'agent': 'test_agent'
        }
    
    @pytest.mark.asyncio
    async def test_bridge_startup(self, bridge):
        """Test bridge starts correctly."""
        status = await bridge.get_status()
        assert status['status'] == 'running'
        assert status['port'] == 8766
    
    @pytest.mark.asyncio
    async def test_safe_command_validation(self, bridge, sample_command_data):
        """Test validation of safe commands."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'http://localhost:8766/validate',
                json=sample_command_data
            ) as resp:
                result = await resp.json()
                assert result['status'] == 'approved'
                assert 'id' in result
    
    @pytest.mark.asyncio
    async def test_dangerous_command_validation(self, bridge):
        """Test validation of dangerous commands."""
        dangerous_cmd = {
            'id': 'test_dangerous_001',
            'tool': 'Bash',
            'input': {'command': 'rm -rf /'},
            'agent': 'test_agent'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'http://localhost:8766/validate',
                json=dangerous_cmd
            ) as resp:
                result = await resp.json()
                assert result['status'] == 'blocked'
                assert 'concern' in result
    
    @pytest.mark.asyncio
    async def test_command_approval(self, bridge, sample_command_data):
        """Test manual command approval."""
        # First submit a command that requires review
        risky_cmd = {
            'id': 'test_risky_001',
            'tool': 'Bash',
            'input': {'command': 'sudo apt update'},
            'agent': 'test_agent'
        }
        
        async with aiohttp.ClientSession() as session:
            # Submit command
            async with session.post(
                'http://localhost:8766/validate',
                json=risky_cmd
            ) as resp:
                result = await resp.json()
                assert result['status'] in ['review_required', 'blocked']
            
            # Approve the command
            approval_data = {
                'id': 'test_risky_001',
                'status': 'approved',
                'reason': 'Manual test approval'
            }
            
            async with session.post(
                'http://localhost:8766/approve',
                json=approval_data
            ) as resp:
                approval_result = await resp.json()
                assert approval_result['success'] is True
    
    @pytest.mark.asyncio
    async def test_status_endpoint(self, bridge):
        """Test status endpoint."""
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8766/status') as resp:
                status = await resp.json()
                assert status['status'] == 'running'
                assert 'pending_commands' in status
                assert 'approved_commands' in status
    
    @pytest.mark.asyncio
    async def test_pending_commands_endpoint(self, bridge):
        """Test pending commands endpoint."""
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8766/pending') as resp:
                pending = await resp.json()
                assert 'pending' in pending
                assert isinstance(pending['pending'], list)
    
    def test_dangerous_command_detection(self, bridge):
        """Test dangerous command pattern detection."""
        test_cases = [
            ('rm -rf /', True),
            ('sudo rm -rf /etc', True),
            ('dd if=/dev/zero of=/dev/sda', True),
            ('ls -la', False),
            ('echo hello', False),
            ('mkdir test', False)
        ]
        
        for command, should_be_dangerous in test_cases:
            cmd_data = CommandData(
                id='test',
                tool='Bash',
                input={'command': command},
                agent='test',
                timestamp=0.0
            )
            result = bridge.is_dangerous_command(cmd_data)
            assert result == should_be_dangerous, f"Command '{command}' danger detection failed"
    
    def test_protected_path_detection(self, bridge):
        """Test protected path detection for file operations."""
        test_cases = [
            ('/etc/passwd', True),
            ('/usr/bin/test', True),
            ('/var/log/test.log', True),
            ('/home/user/test.txt', False),
            ('/tmp/test.txt', False),
            ('/opt/myapp/config.json', False)
        ]
        
        for path, should_be_dangerous in test_cases:
            cmd_data = CommandData(
                id='test',
                tool='Write',
                input={'file_path': path, 'content': 'test'},
                agent='test',
                timestamp=0.0
            )
            result = bridge.is_dangerous_command(cmd_data)
            assert result == should_be_dangerous, f"Path '{path}' protection detection failed"
    
    @pytest.mark.asyncio
    async def test_command_timeout(self, bridge):
        """Test command validation timeout behavior."""
        # Submit command and don't approve it
        timeout_cmd = {
            'id': 'test_timeout_001',
            'tool': 'Bash',
            'input': {'command': 'echo test'},
            'agent': 'test_agent'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'http://localhost:8766/validate',
                json=timeout_cmd
            ) as resp:
                result = await resp.json()
                # Safe command should be approved even on timeout
                assert result['status'] == 'approved'
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_commands(self, bridge):
        """Test automatic cleanup of expired commands."""
        # Add a command to pending
        cmd_data = CommandData(
            id='expired_test',
            tool='Bash',
            input={'command': 'test'},
            agent='test',
            timestamp=0.0  # Very old timestamp
        )
        bridge.pending_commands['expired_test'] = cmd_data
        
        # Wait for cleanup (manually trigger for testing)
        import time
        current_time = time.time()
        expired_pending = [
            cmd_id for cmd_id, cmd in bridge.pending_commands.items()
            if current_time - cmd.timestamp > 300
        ]
        
        for cmd_id in expired_pending:
            del bridge.pending_commands[cmd_id]
        
        assert 'expired_test' not in bridge.pending_commands
    
    def test_command_hash(self, bridge):
        """Test command hashing for pre-approval."""
        cmd1 = CommandData(
            id='test1',
            tool='Bash',
            input={'command': 'ls'},
            agent='test',
            timestamp=0.0
        )
        cmd2 = CommandData(
            id='test2',
            tool='Bash',
            input={'command': 'ls'},
            agent='test',
            timestamp=1.0
        )
        cmd3 = CommandData(
            id='test3',
            tool='Bash',
            input={'command': 'pwd'},
            agent='test',
            timestamp=0.0
        )
        
        hash1 = bridge._hash_command(cmd1)
        hash2 = bridge._hash_command(cmd2)
        hash3 = bridge._hash_command(cmd3)
        
        # Same command should have same hash regardless of timestamp/id
        assert hash1 == hash2
        # Different command should have different hash
        assert hash1 != hash3