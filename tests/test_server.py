"""Tests for the MCP server."""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from lighthouse.server import LighthouseServer


class TestLighthouseServer:
    """Test cases for LighthouseServer."""
    
    @pytest.fixture
    def server(self):
        """Create a test server instance."""
        return LighthouseServer()
    
    def test_server_initialization(self, server):
        """Test server initializes correctly."""
        assert server.server is not None
        assert server.bridge is not None
        assert server.validator is not None
    
    @pytest.mark.asyncio
    async def test_list_tools_handler(self, server):
        """Test list tools handler."""
        # Get the handler function
        handler = None
        for tool_handler in server.server._tool_handlers:
            if hasattr(tool_handler, '__name__') and 'list_tools' in tool_handler.__name__:
                handler = tool_handler
                break
        
        if handler is None:
            # Try to call the list_tools method directly
            tools = await server.server.list_tools()
        else:
            tools = await handler()
        
        assert isinstance(tools, list)
        assert len(tools) >= 3  # Should have at least 3 tools
        
        tool_names = [tool.name for tool in tools]
        expected_tools = ['validate_command', 'bridge_status', 'approve_command']
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Missing tool: {expected_tool}"
    
    @pytest.mark.asyncio 
    async def test_validate_command_tool(self, server):
        """Test validate_command tool."""
        # Mock the validator
        with patch.object(server.validator, 'validate_command') as mock_validate:
            mock_validate.return_value = {
                'status': 'approved',
                'reason': 'Test approval'
            }
            
            # Get the call_tool handler
            handler = None
            for tool_handler in server.server._tool_handlers:
                if hasattr(tool_handler, '__name__') and 'call_tool' in tool_handler.__name__:
                    handler = tool_handler
                    break
            
            if handler:
                result = await handler(
                    name='validate_command',
                    arguments={
                        'tool': 'Bash',
                        'input': {'command': 'ls'},
                        'agent': 'test'
                    }
                )
                
                assert len(result) == 1
                assert result[0].type == 'text'
                response_data = json.loads(result[0].text)
                assert response_data['status'] == 'approved'
    
    @pytest.mark.asyncio
    async def test_bridge_status_tool(self, server):
        """Test bridge_status tool."""
        with patch.object(server.bridge, 'get_status') as mock_status:
            mock_status.return_value = {
                'status': 'running',
                'pending_commands': 0,
                'approved_commands': 0
            }
            
            # Get the call_tool handler 
            handler = None
            for tool_handler in server.server._tool_handlers:
                if hasattr(tool_handler, '__name__') and 'call_tool' in tool_handler.__name__:
                    handler = tool_handler
                    break
            
            if handler:
                result = await handler(
                    name='bridge_status',
                    arguments={}
                )
                
                assert len(result) == 1
                response_data = json.loads(result[0].text)
                assert response_data['status'] == 'running'
    
    @pytest.mark.asyncio
    async def test_approve_command_tool(self, server):
        """Test approve_command tool."""
        with patch.object(server.bridge, 'approve_command') as mock_approve:
            mock_approve.return_value = {
                'success': True,
                'id': 'test_cmd'
            }
            
            # Get the call_tool handler
            handler = None  
            for tool_handler in server.server._tool_handlers:
                if hasattr(tool_handler, '__name__') and 'call_tool' in tool_handler.__name__:
                    handler = tool_handler
                    break
            
            if handler:
                result = await handler(
                    name='approve_command',
                    arguments={
                        'command_id': 'test_cmd',
                        'reason': 'Test approval'
                    }
                )
                
                assert len(result) == 1
                response_data = json.loads(result[0].text)
                assert response_data['success'] is True
    
    @pytest.mark.asyncio
    async def test_unknown_tool_error(self, server):
        """Test error handling for unknown tools."""
        # Get the call_tool handler
        handler = None
        for tool_handler in server.server._tool_handlers:
            if hasattr(tool_handler, '__name__') and 'call_tool' in tool_handler.__name__:
                handler = tool_handler
                break
        
        if handler:
            result = await handler(
                name='unknown_tool',
                arguments={}
            )
            
            assert len(result) == 1
            assert 'Error' in result[0].text
    
    @pytest.mark.asyncio
    async def test_tool_exception_handling(self, server):
        """Test exception handling in tools."""
        with patch.object(server.validator, 'validate_command') as mock_validate:
            mock_validate.side_effect = Exception("Test exception")
            
            # Get the call_tool handler
            handler = None
            for tool_handler in server.server._tool_handlers:
                if hasattr(tool_handler, '__name__') and 'call_tool' in tool_handler.__name__:
                    handler = tool_handler
                    break
            
            if handler:
                result = await handler(
                    name='validate_command',
                    arguments={
                        'tool': 'Bash',
                        'input': {'command': 'ls'},
                        'agent': 'test'
                    }
                )
                
                assert len(result) == 1
                assert 'Error' in result[0].text
                assert 'Test exception' in result[0].text


class TestServerIntegration:
    """Integration tests for server components."""
    
    @pytest.mark.asyncio
    async def test_server_bridge_integration(self):
        """Test server integrates with bridge correctly."""
        server = LighthouseServer()
        
        # Test that bridge starts
        await server.bridge.start()
        
        status = await server.bridge.get_status()
        assert status['status'] == 'running'
        
        # Cleanup
        await server.bridge.stop()
    
    @pytest.mark.asyncio
    async def test_server_validator_integration(self):
        """Test server integrates with validator correctly."""
        server = LighthouseServer()
        
        # Test validator functionality
        result = await server.validator.validate_command(
            tool='Read',
            tool_input={'file_path': '/tmp/test.txt'},
            agent='test'
        )
        
        assert 'status' in result
        assert result['status'] == 'approved'  # Read is safe
    
    @pytest.mark.asyncio
    async def test_full_validation_flow(self):
        """Test complete validation flow through server."""
        server = LighthouseServer()
        await server.bridge.start()
        
        try:
            # Simulate a command validation request
            result = await server.validator.validate_command(
                tool='Bash',
                tool_input={'command': 'echo test'},
                agent='integration_test'
            )
            
            assert result['status'] == 'approved'
            assert 'reason' in result
            
        finally:
            await server.bridge.stop()