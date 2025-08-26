# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lighthouse is an MCP (Model Context Protocol) server that provides command validation and enables closer command and control between peer agents and parent-child agents. It enforces security policies at the system level by intercepting and validating dangerous commands before execution using a two-layer validation strategy:

1. **Hook-Based Validation**: Every command is automatically intercepted by Claude Code hooks configured in `.claude/config.json`
2. **Validation Bridge**: Commands are sent to a validation bridge at `http://localhost:8765` for review and inter-agent coordination

## Architecture

The system consists of integrated core components:

- **MCP Server** (`src/lighthouse/mcp_server.py`): Secure MCP server with Bridge integration, HMAC-SHA256 session security, and unified event store
- **Minimal Bridge** (`src/lighthouse/mcp_bridge_minimal.py`): Essential Bridge components for MCP integration (EventStore, SessionSecurity, SpeedLayer, ExpertCoordination)
- **Main Bridge** (`src/lighthouse/bridge/main_bridge.py`): Full Bridge system for comprehensive multi-agent coordination and validation

## Development Commands

### Installation and Setup

```bash
# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Start the MCP server with Bridge integration
python -m lighthouse.mcp_server
```

### Testing

```bash
# Install dev dependencies first if not already installed
pip install -e ".[dev]"

# Run tests (requires dev dependencies)
python -m pytest

# Run tests with coverage
python -m pytest --cov=lighthouse

# Test hook validation manually
echo '{"tool_name": "Bash", "tool_input": {"command": "ls"}}' | python .claude/hooks/validate_command.py
```

### Code Quality

```bash
# Format code with Black
python -m black src/ tests/

# Sort imports with isort
python -m isort src/ tests/

# Type checking with mypy
python -m mypy src/

# Run pre-commit hooks
python -m pre_commit run --all-files
```

## Security Configuration

### Hook Configuration

The `.claude/config.json` file configures which tools are validated:

- `Bash`, `Edit`, `Write`, `MultiEdit` commands are intercepted by default
- Validation hook script: `.claude/hooks/validate_command.py`

### Validation Rules

Located in `src/lighthouse/validator.py`:

- **Dangerous patterns**: `rm -rf /`, `sudo rm`, `chmod 777`, hardware operations (`dd`, `fdisk`)
- **Protected paths**: `/etc/`, `/usr/`, `/var/`, `/boot/`, `/sys/`, `/proc/`, `/dev/`
- **Safe tools**: `Read`, `Glob`, `Grep`, `LS` (auto-approved)

## Important Files

- **MCP Server**: `src/lighthouse/mcp_server.py` (Secure MCP server with Bridge integration, session management, and event store)
- **Minimal Bridge**: `src/lighthouse/mcp_bridge_minimal.py` (Essential Bridge components for MCP integration)
- **Session Security**: `src/lighthouse/bridge/security/session_security.py` (HMAC-SHA256 session validation and hijacking prevention)
- **Main Bridge**: `src/lighthouse/bridge/main_bridge.py` (Full Bridge system with multi-agent coordination)
- **Hook configuration**: `.claude/config.json`
- **MCP Configuration**: `.mcp.json` (MCP server configuration for Claude Code)
- **Package config**: `pyproject.toml` (build system, dev dependencies, tool settings)

## Testing Strategy

- Unit tests in `tests/` directory
- Integration tests for hook validation
- Manual testing with curl commands for bridge endpoints
- Hook logging available at `/tmp/lighthouse_hook.log`

## Monitoring and Debugging

### Bridge Status

```bash
curl http://localhost:8765/status
curl http://localhost:8765/pending
```

### Fallback Behavior

When validation bridge is offline:

- Safe tools are allowed
- Dangerous commands are blocked
- Unknown tools proceed with logging

## CRITICAL FILE READING REQUIREMENTS - NO EXCEPTIONS

### ABSOLUTE REQUIREMENT: READ ENTIRE FILES COMPLETELY - NO PARTIAL READS ALLOWED

IF YOU TRY TO READ ANY FILE (PYTHON, MARKDOWN, JSON, ETC.) AND IT EXCEEDS THE LIMIT, YOU MUST STILL READ IT IN FULL. YOU MUST NEVER READ THE FIRST 100 LINES AND DECIDE YOU KNOW ENOUGH.

**THIS IS NON-NEGOTIABLE. PARTIAL FILE ANALYSIS IS COMPLETELY UNACCEPTABLE.**

### MANDATORY Process for Large Files

1. Read the file normally first
2. If truncated, immediately read the rest using offset/limit parameters
3. Continue reading ALL remaining sections until the ENTIRE file is read
4. ONLY then proceed with analysis

### EXAMPLES OF REQUIRED BEHAVIOR

- 1000-line file: Read lines 1-500, then 501-1000, then analyze
- 2000-line file: Read in 500-line chunks until complete
- Any file: Read EVERY SINGLE LINE before making any conclusions
- MD files: Read entire documentation files, not just headers
- Python files: Read all functions, classes, and implementation details
- JSON/config files: Read all configuration sections and values

### ABSOLUTELY FORBIDDEN BEHAVIORS

- "I read the first 100 lines, that's enough to understand the structure"
- "The file is too long, I'll just read the imports and classes"
- "I can see the pattern from the beginning, no need to read more"
- "I'll just read the headers and skip the implementation details"
- Making ANY architectural or debugging decisions from partial reads
- Concluding ANYTHING about a file's functionality without reading it completely

**VIOLATION OF THIS RULE IS COMPLETELY UNACCEPTABLE AND MUST NEVER HAPPEN.**
