#!/usr/bin/env python3
"""Test the actual hook integration with real command scenarios."""

import json
import subprocess
import sys
from pathlib import Path


def test_hook_with_command(description, tool_name, tool_input, expected_behavior):
    """Test hook with a specific command."""
    hook_path = Path(__file__).parent / ".claude" / "hooks" / "validate_command.py"
    
    test_input = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "agent_id": "demo_agent"
    }
    
    print(f"\n🧪 Testing: {description}")
    print(f"   Tool: {tool_name}")
    print(f"   Input: {tool_input}")
    
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(test_input),
        text=True,
        capture_output=True,
        timeout=10
    )
    
    if expected_behavior == "allow":
        if result.returncode == 0:
            print(f"   ✅ ALLOWED (exit code {result.returncode})")
            return True
        else:
            print(f"   ❌ BLOCKED unexpectedly (exit code {result.returncode})")
            print(f"   stderr: {result.stderr[:200]}")
            return False
    else:  # block
        if result.returncode == 2:
            print(f"   ✅ BLOCKED (exit code {result.returncode})")
            return True
        else:
            print(f"   ❌ ALLOWED unexpectedly (exit code {result.returncode})")
            return False


def main():
    """Run real hook integration tests."""
    print("🎣 Lighthouse Hook Integration Test")
    print("=" * 50)
    
    tests = [
        # Safe commands that should be allowed
        ("Safe file read", "Read", {"file_path": "/home/user/document.txt"}, "allow"),
        ("Directory listing", "LS", {"path": "/home/user"}, "allow"),
        ("Search files", "Grep", {"pattern": "TODO", "path": "/home/user/project"}, "allow"),
        ("Find files", "Glob", {"pattern": "*.py"}, "allow"),
        ("Safe bash command", "Bash", {"command": "echo 'Hello World'"}, "allow"),
        ("List files bash", "Bash", {"command": "ls -la"}, "allow"),
        ("Check process", "Bash", {"command": "ps aux | grep python"}, "allow"),
        
        # File operations that should be allowed
        ("Write user file", "Write", {"file_path": "/home/user/test.txt", "content": "test"}, "allow"),
        ("Edit user file", "Edit", {"file_path": "/home/user/config.json", "old_string": "old", "new_string": "new"}, "allow"),
        
        # Dangerous commands that should be blocked
        ("Delete root", "Bash", {"command": "rm -rf /"}, "block"),
        ("Delete all files", "Bash", {"command": "rm -rf *"}, "block"),
        ("Sudo delete", "Bash", {"command": "sudo rm -rf /etc"}, "block"),
        ("Format disk", "Bash", {"command": "dd if=/dev/zero of=/dev/sda"}, "block"),
        ("Make filesystem", "Bash", {"command": "mkfs.ext4 /dev/sda1"}, "block"),
        ("System shutdown", "Bash", {"command": "shutdown now"}, "block"),
        
        # System file modifications that should be blocked
        ("Modify passwd", "Write", {"file_path": "/etc/passwd", "content": "hacked"}, "block"),
        ("Edit system config", "Edit", {"file_path": "/usr/bin/sudo", "old_string": "a", "new_string": "b"}, "block"),
        ("Modify boot", "Write", {"file_path": "/boot/grub/grub.cfg", "content": "malicious"}, "block"),
        
        # Edge cases
        ("Empty bash command", "Bash", {"command": ""}, "allow"),
        ("Complex safe command", "Bash", {"command": "find /home/user -name '*.py' | head -10"}, "allow"),
    ]
    
    passed = 0
    failed = 0
    
    for description, tool_name, tool_input, expected in tests:
        if test_hook_with_command(description, tool_name, tool_input, expected):
            passed += 1
        else:
            failed += 1
    
    print(f"\n📊 Results:")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📈 Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print(f"\n🎉 All tests passed! Hook validation is working perfectly.")
        print(f"🛡️  Dangerous commands are blocked, safe commands are allowed.")
    else:
        print(f"\n⚠️  Some tests failed. Review the hook validation logic.")
    
    print(f"\n🚀 Lighthouse hook system is operational!")


if __name__ == "__main__":
    main()