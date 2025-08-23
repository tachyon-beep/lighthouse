"""Tests for the command validator."""

import pytest
from lighthouse.validator import CommandValidator


class TestCommandValidator:
    """Test cases for CommandValidator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = CommandValidator()
    
    @pytest.mark.asyncio
    async def test_safe_bash_command(self):
        """Test validation of safe bash commands."""
        result = await self.validator.validate_command(
            tool="Bash",
            tool_input={"command": "ls -la"},
            agent="test_agent"
        )
        
        assert result["status"] == "approved"
        assert "safe" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_dangerous_bash_command(self):
        """Test validation of dangerous bash commands."""
        result = await self.validator.validate_command(
            tool="Bash",
            tool_input={"command": "rm -rf /"},
            agent="test_agent"
        )
        
        assert result["status"] == "blocked"
        assert result["risk_level"] == "high"
    
    @pytest.mark.asyncio
    async def test_risky_bash_command(self):
        """Test validation of risky bash commands."""
        result = await self.validator.validate_command(
            tool="Bash",
            tool_input={"command": "sudo apt update"},
            agent="test_agent"
        )
        
        assert result["status"] == "review_required"
        assert result["risk_level"] == "medium"
    
    @pytest.mark.asyncio
    async def test_safe_file_operation(self):
        """Test validation of safe file operations."""
        result = await self.validator.validate_command(
            tool="Write",
            tool_input={"file_path": "/home/user/test.txt", "content": "test"},
            agent="test_agent"
        )
        
        assert result["status"] == "approved"
    
    @pytest.mark.asyncio
    async def test_dangerous_file_operation(self):
        """Test validation of dangerous file operations."""
        result = await self.validator.validate_command(
            tool="Write",
            tool_input={"file_path": "/etc/passwd", "content": "malicious"},
            agent="test_agent"
        )
        
        assert result["status"] == "blocked"
        assert result["risk_level"] == "high"
    
    @pytest.mark.asyncio
    async def test_safe_tools(self):
        """Test validation of inherently safe tools."""
        for tool in ["Read", "Glob", "Grep", "LS"]:
            result = await self.validator.validate_command(
                tool=tool,
                tool_input={"path": "/home/user"},
                agent="test_agent"
            )
            
            assert result["status"] == "approved"
            assert "safe tool" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        """Test validation of unknown tools."""
        result = await self.validator.validate_command(
            tool="UnknownTool",
            tool_input={"param": "value"},
            agent="test_agent"
        )
        
        assert result["status"] == "review_required"
        assert "unknown tool" in result["reason"].lower()
    
    def test_validation_stats(self):
        """Test validation statistics."""
        stats = self.validator.get_validation_stats()
        
        assert "rules_loaded" in stats
        assert "dangerous_patterns" in stats
        assert "protected_paths" in stats
        assert all(isinstance(v, int) for v in stats.values())