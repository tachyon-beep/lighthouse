# Lighthouse - MCP Server with Hook-Based Command Validation

A Model Context Protocol (MCP) server that provides automatic command validation through Claude Code hooks. Lighthouse enforces security policies at the system level, ensuring that dangerous commands are intercepted and validated before execution.

## 🏗️ Architecture

Lighthouse uses a two-layer validation strategy:

1. **Hook-Based Validation (Mandatory)**: Every command is automatically intercepted by Claude Code hooks
2. **Agent Protocol (Best Practice)**: Agents can propose commands for discussion before execution

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd lighthouse

# Install dependencies
pip install -e .

# Or install in development mode
pip install -e ".[dev]"
```

### Setup

1. **Start the Validation Bridge**:
```bash
python -m lighthouse.server
```

2. **Configure Claude Code Hooks**:
The `.claude/config.json` file is already configured to use validation hooks for:
- `Bash` commands
- `Edit`, `Write`, `MultiEdit` file operations

3. **Test the Setup**:
```bash
# This should trigger validation
echo "rm -rf /" | python .claude/hooks/validate_command.py
```

## 🛡️ Security Features

### Automatic Command Interception

Every potentially dangerous command is automatically intercepted:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|MultiEdit",
        "hooks": [{
          "type": "command",
          "command": "python3 .claude/hooks/validate_command.py"
        }]
      }
    ]
  }
}
```

### Dangerous Command Detection

The system automatically blocks commands containing:
- `rm -rf /`, `rm -rf *`
- `sudo rm`, `chmod 777`
- System file modifications (`/etc/`, `/usr/`, etc.)
- Hardware operations (`dd`, `fdisk`, `mkfs`)
- System control (`shutdown`, `reboot`, `kill -9 1`)

### Validation Bridge

Commands are sent to a validation bridge at `http://localhost:8765` where:
- Validator agents can review pending commands
- Commands can be pre-approved for efficiency
- Manual approval is required for risky operations

## 📋 Usage Examples

### Safe Commands (Auto-Approved)
```bash
# These pass through automatically
ls -la
cat file.txt
grep "pattern" *.py
```

### Risky Commands (Review Required)
```bash
# These require manual approval
sudo apt update
rm important_file.txt
chmod 755 script.sh
```

### Dangerous Commands (Blocked)
```bash
# These are immediately blocked
rm -rf /
sudo rm -rf /etc/
dd if=/dev/zero of=/dev/sda
```

## 🔧 Configuration

### Hook Configuration

Edit `.claude/config.json` to modify which tools are validated:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|MultiEdit|YourCustomTool",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/validate_command.py"
          }
        ]
      }
    ]
  }
}
```

### Validation Rules

Modify `lighthouse/validator.py` to customize validation rules:

```python
"dangerous_bash_patterns": [
    r"rm\\s+-rf\\s+/",
    r"your_custom_pattern"
],
"protected_paths": [
    "/etc/",
    "/your/protected/path/"
]
```

## 🔄 Workflow

### For Well-Behaved Agents
1. Agent proposes command via bridge
2. Validator pre-approves if safe
3. Command executes immediately through hook

### For Agents That Skip Protocol
1. Agent attempts to execute command
2. Hook intercepts and sends to bridge
3. Validator reviews and approves/blocks
4. Hook allows/blocks based on response

### Fallback Behavior
When the validation bridge is offline:
- Safe tools (`Read`, `Grep`, etc.) are allowed
- Dangerous commands are blocked
- Unknown tools proceed with logging

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=lighthouse

# Test hook validation
echo '{"tool_name": "Bash", "tool_input": {"command": "ls"}}' | python .claude/hooks/validate_command.py
```

## 📊 Monitoring

### Bridge Status
```bash
curl http://localhost:8765/status
```

### Pending Commands
```bash
curl http://localhost:8765/pending
```

### Logs
- Hook logs: `/tmp/lighthouse_hook.log`
- Server logs: Standard output when running `lighthouse.server`

## 🤝 Development

### Project Structure
```
lighthouse/
├── src/lighthouse/
│   ├── __init__.py
│   ├── server.py          # Main MCP server
│   ├── bridge.py          # Validation bridge
│   └── validator.py       # Command validation logic
├── .claude/
│   ├── config.json        # Claude Code hooks config
│   └── hooks/
│       └── validate_command.py  # Validation hook script
├── tests/
├── pyproject.toml
└── README.md
```

### Adding New Validation Rules

1. Edit `src/lighthouse/validator.py`
2. Add patterns to `validation_rules`
3. Implement validation logic in `validate_command()`
4. Test with hook script

### Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.

## 🆘 Troubleshooting

### Hook Not Working
- Check that `.claude/config.json` is properly formatted
- Verify hook script has execute permissions: `chmod +x .claude/hooks/validate_command.py`
- Check hook logs at `/tmp/lighthouse_hook.log`

### Bridge Connection Failed
- Ensure the server is running: `python -m lighthouse.server`
- Check port 8765 is not blocked
- Review fallback validation in hook logs

### Commands Still Blocked
- Join the validation bridge to manually approve
- Check if command matches dangerous patterns
- Review validator logs for specific blocking reasons

## 🔗 Related Projects

- [Model Context Protocol](https://github.com/modelcontextprotocol/servers)
- [Claude Code](https://docs.anthropic.com/claude/docs)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)