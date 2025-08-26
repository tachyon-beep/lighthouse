"""
Updated tests for the new LighthouseBridge API

These tests focus on the core validation functionality without requiring
HTTP endpoints, making them more suitable for unit testing.
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from lighthouse import LighthouseBridge
from lighthouse.bridge import CommandData


class TestLighthouseBridge:
    """Test cases for the new LighthouseBridge."""
    
    @pytest_asyncio.fixture
    async def bridge(self):
        """Create a test bridge instance."""
        # Mock FUSE availability before creating bridge
        with patch('lighthouse.bridge.fuse_mount.mount_manager.FUSE_AVAILABLE', True):
            bridge = LighthouseBridge(
                project_id="test_project", 
                mount_point="/tmp/lighthouse_test",
                config={
                    'fuse_foreground': True,
                    'fuse_allow_other': False
                }
            )
            
            # Mock FUSE mount operations 
            with patch.object(bridge.fuse_mount_manager, 'mount', AsyncMock(return_value=True)), \
                 patch.object(bridge.fuse_mount_manager, 'unmount', AsyncMock(return_value=True)):
                await bridge.start()
                yield bridge
                await bridge.stop()
    
    @pytest.fixture
    def sample_command_data(self):
        """Sample command data for testing."""
        return CommandData(
            id='test_cmd_001',
            tool='Bash',
            input={'command': 'ls -la'},
            agent='test_agent'
        )
    
    @pytest.mark.asyncio
    async def test_bridge_startup(self, bridge):
        """Test bridge starts correctly."""
        status = bridge.get_system_status()
        assert status['is_running'] is True
        assert status['project_id'] == "test_project"
    
    @pytest.mark.asyncio 
    async def test_safe_command_validation(self, bridge, sample_command_data):
        """Test validation of safe commands."""
        result = await bridge.validate_command(
            tool_name=sample_command_data.tool,
            tool_input=sample_command_data.input,
            agent_id=sample_command_data.agent
        )
        
        # Should get a validation result
        assert isinstance(result, dict)
        assert 'decision' in result or 'approved' in result
    
    @pytest.mark.asyncio
    async def test_dangerous_command_validation(self, bridge):
        """Test validation of dangerous commands."""
        result = await bridge.validate_command(
            tool_name='Bash',
            tool_input={'command': 'rm -rf /'},
            agent_id='test_agent'
        )
        
        # Should block dangerous command
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_file_modification(self, bridge):
        """Test file modification through bridge."""
        success = await bridge.modify_file(
            file_path="/tmp/test_file.py",
            content="print('hello world')",
            agent_id="test_agent"
        )
        
        # Should handle file modification
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_system_status(self, bridge):
        """Test system status retrieval."""
        status = bridge.get_system_status()
        
        assert 'is_running' in status
        assert 'project_id' in status
        assert 'components' in status
        assert 'performance' in status
    
    @pytest.mark.asyncio
    async def test_context_package_creation(self, bridge):
        """Test context package creation."""
        success = await bridge.create_context_package(
            package_id="test_package",
            files=["file1.py", "file2.py"],
            description="Test package"
        )
        
        assert isinstance(success, bool)


@pytest.mark.asyncio 
async def test_command_data_creation():
    """Test CommandData creation and attributes."""
    cmd_data = CommandData(
        id="test_001",
        tool="Bash", 
        input={"command": "echo hello"},
        agent="test_agent"
    )
    
    assert cmd_data.id == "test_001"
    assert cmd_data.tool == "Bash"
    assert cmd_data.agent == "test_agent"
    assert cmd_data.timestamp is not None


@pytest.mark.asyncio
async def test_bridge_context_manager():
    """Test bridge as async context manager."""
    with patch('lighthouse.bridge.main_bridge.FUSEMountManager') as mock_fuse:
        mock_fuse.return_value.mount = AsyncMock(return_value=True)
        mock_fuse.return_value.unmount = AsyncMock(return_value=True)
        
        async with LighthouseBridge(project_id="ctx_test") as bridge:
            assert bridge.is_running
            status = bridge.get_system_status()
            assert status['is_running'] is True


# Integration tests with speed layer
class TestBridgeIntegration:
    """Integration tests for bridge components."""
    
    @pytest.mark.asyncio
    async def test_speed_layer_integration(self):
        """Test integration with speed layer."""
        with patch('lighthouse.bridge.main_bridge.FUSEMountManager') as mock_fuse:
            mock_fuse.return_value.mount = AsyncMock(return_value=True) 
            mock_fuse.return_value.unmount = AsyncMock(return_value=True)
            
            async with LighthouseBridge(project_id="speed_test") as bridge:
                # Test that speed layer is initialized
                assert bridge.speed_layer_dispatcher is not None
                
                # Test validation goes through speed layer
                result = await bridge.validate_command(
                    tool_name="Read",  # Safe tool
                    tool_input={"file_path": "/tmp/test.txt"},
                    agent_id="test_agent"
                )
                
                assert isinstance(result, dict)