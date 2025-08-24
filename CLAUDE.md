# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lighthouse is an MCP (Model Context Protocol) server that provides command validation and enables closer command and control between peer agents and parent-child agents. It enforces security policies at the system level by intercepting and validating dangerous commands before execution using a two-layer validation strategy:

1. **Hook-Based Validation**: Every command is automatically intercepted by Claude Code hooks configured in `.claude/config.json`
2. **Validation Bridge**: Commands are sent to a validation bridge at `http://localhost:8765` for review and inter-agent coordination

## Architecture

The system consists of three core components:

- **Server** (`src/lighthouse/server.py`): Main MCP server implementation
- **Bridge** (`src/lighthouse/bridge.py`): Validation bridge for inter-agent communication, pair programming sessions, and agent coordination
- **Validator** (`src/lighthouse/validator.py`): Command validation logic with security rules

## Development Commands

### Installation and Setup

```bash
# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Start the validation bridge server
python -m lighthouse.server
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

- **Core validation logic**: `src/lighthouse/validator.py:19-50` (validation rules)
- **Bridge server**: `src/lighthouse/bridge.py:47-80` (HTTP endpoints)
- **MCP server**: `src/lighthouse/server.py:30-60` (tool handlers)
- **Hook configuration**: `.claude/config.json`
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
