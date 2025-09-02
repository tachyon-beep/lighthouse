#!/usr/bin/env python3
"""
Migration Script: Remove wait_for_messages System
FEATURE_PACK_0 - Final Migration Task (Week 12)

This script removes all wait_for_messages functionality after successful
migration to the elicitation system.

CAUTION: This is a destructive operation. Ensure all agents have migrated
to elicitation before running this script.
"""

import os
import sys
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

# Color codes for output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header():
    """Print script header"""
    print("=" * 70)
    print(f"{BLUE}FEATURE_PACK_0 - Remove wait_for_messages Migration Script{RESET}")
    print("=" * 70)
    print(f"{YELLOW}⚠️  WARNING: This will permanently remove wait_for_messages{RESET}")
    print("=" * 70)
    print()

def confirm_action() -> bool:
    """Get user confirmation"""
    print(f"{RED}This script will:{RESET}")
    print("  1. Remove lighthouse_wait_for_messages MCP tool")
    print("  2. Remove /event/wait HTTP endpoint")
    print("  3. Remove related implementation code")
    print("  4. Create backups of modified files")
    print()
    
    response = input(f"{YELLOW}Are you sure you want to proceed? (yes/no): {RESET}")
    return response.lower() == 'yes'

def create_backup(file_path: Path) -> Path:
    """Create backup of file before modification"""
    backup_dir = Path("backups/wait_for_messages_removal")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{file_path.name}.{timestamp}.bak"
    
    shutil.copy2(file_path, backup_path)
    print(f"  {GREEN}✓{RESET} Backed up: {file_path.name}")
    return backup_path

def remove_mcp_tool(mcp_file: Path) -> Tuple[bool, str]:
    """Remove lighthouse_wait_for_messages tool from MCP server"""
    print(f"\n{BLUE}Removing MCP tool from {mcp_file.name}...{RESET}")
    
    if not mcp_file.exists():
        return False, "File not found"
    
    # Create backup
    create_backup(mcp_file)
    
    with open(mcp_file, 'r') as f:
        content = f.read()
    
    # Find and remove the tool definition
    pattern = r'@mcp\.tool\(\)\s*async def lighthouse_wait_for_messages.*?(?=@mcp\.tool\(\)|# ====|# Init|\Z)'
    
    modified_content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    if modified_content != content:
        with open(mcp_file, 'w') as f:
            f.write(modified_content)
        print(f"  {GREEN}✓{RESET} Removed lighthouse_wait_for_messages tool")
        return True, "Tool removed"
    else:
        print(f"  {YELLOW}⚠{RESET} Tool not found or already removed")
        return False, "Tool not found"

def remove_http_endpoint(http_file: Path) -> Tuple[bool, str]:
    """Remove /event/wait endpoint from HTTP server"""
    print(f"\n{BLUE}Removing HTTP endpoint from {http_file.name}...{RESET}")
    
    if not http_file.exists():
        return False, "File not found"
    
    # Create backup
    create_backup(http_file)
    
    with open(http_file, 'r') as f:
        content = f.read()
    
    # Find and remove the endpoint definition
    pattern = r'@app\.get\("/event/wait"\).*?(?=@app\.|# ====|# WebSocket|\Z)'
    
    modified_content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    if modified_content != content:
        with open(http_file, 'w') as f:
            f.write(modified_content)
        print(f"  {GREEN}✓{RESET} Removed /event/wait endpoint")
        return True, "Endpoint removed"
    else:
        print(f"  {YELLOW}⚠{RESET} Endpoint not found or already removed")
        return False, "Endpoint not found"

def update_documentation() -> List[Tuple[Path, str]]:
    """Update documentation to reflect removal"""
    print(f"\n{BLUE}Updating documentation...{RESET}")
    
    updates = []
    
    # Add deprecation notice to relevant docs
    docs_to_update = [
        Path("docs/architecture/HLD.md"),
        Path("CLAUDE.md"),
        Path("README.md")
    ]
    
    for doc_path in docs_to_update:
        if doc_path.exists():
            create_backup(doc_path)
            
            with open(doc_path, 'r') as f:
                content = f.read()
            
            # Add migration notice if not already present
            if "wait_for_messages" in content and "DEPRECATED" not in content:
                migration_notice = """
## Migration Notice (FEATURE_PACK_0)

**Note**: The `wait_for_messages` system has been removed and replaced with the MCP Elicitation protocol.
All agent-to-agent communication now uses the elicitation system for improved performance and reliability.

"""
                # Add notice at the beginning of the main content
                content = content.replace("## ", migration_notice + "## ", 1)
                
                with open(doc_path, 'w') as f:
                    f.write(content)
                
                updates.append((doc_path, "Added migration notice"))
                print(f"  {GREEN}✓{RESET} Updated: {doc_path.name}")
    
    return updates

def verify_removal() -> bool:
    """Verify that wait_for_messages has been removed"""
    print(f"\n{BLUE}Verifying removal...{RESET}")
    
    files_to_check = [
        Path("src/lighthouse/mcp_server.py"),
        Path("src/lighthouse/bridge/http_server.py")
    ]
    
    found_references = []
    
    for file_path in files_to_check:
        if file_path.exists():
            with open(file_path, 'r') as f:
                content = f.read()
                if "wait_for_messages" in content.lower():
                    # Check if it's just in comments or actual code
                    if "lighthouse_wait_for_messages" in content or "/event/wait" in content:
                        found_references.append(file_path.name)
    
    if found_references:
        print(f"  {RED}✗{RESET} Still found references in: {', '.join(found_references)}")
        return False
    else:
        print(f"  {GREEN}✓{RESET} No wait_for_messages references found")
        return True

def generate_report(results: dict):
    """Generate migration report"""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}Migration Report{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")
    
    print(f"\nTimestamp: {datetime.now().isoformat()}")
    print(f"Status: {'SUCCESS' if results['success'] else 'PARTIAL'}")
    
    print(f"\n{GREEN}Completed Tasks:{RESET}")
    for task in results['completed']:
        print(f"  ✓ {task}")
    
    if results['failed']:
        print(f"\n{RED}Failed Tasks:{RESET}")
        for task in results['failed']:
            print(f"  ✗ {task}")
    
    if results['backups']:
        print(f"\n{BLUE}Backups Created:{RESET}")
        for backup in results['backups']:
            print(f"  • {backup}")
    
    print(f"\n{BLUE}{'=' * 70}{RESET}")

def main():
    """Main migration script"""
    print_header()
    
    # Get confirmation
    if not confirm_action():
        print(f"{YELLOW}Migration cancelled by user{RESET}")
        sys.exit(0)
    
    results = {
        'success': True,
        'completed': [],
        'failed': [],
        'backups': []
    }
    
    # Get project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Remove MCP tool
    mcp_file = Path("src/lighthouse/mcp_server.py")
    success, message = remove_mcp_tool(mcp_file)
    if success:
        results['completed'].append(f"Remove MCP tool: {message}")
    else:
        results['failed'].append(f"Remove MCP tool: {message}")
        results['success'] = False
    
    # Remove HTTP endpoint
    http_file = Path("src/lighthouse/bridge/http_server.py")
    success, message = remove_http_endpoint(http_file)
    if success:
        results['completed'].append(f"Remove HTTP endpoint: {message}")
    else:
        results['failed'].append(f"Remove HTTP endpoint: {message}")
        results['success'] = False
    
    # Update documentation
    doc_updates = update_documentation()
    for doc_path, status in doc_updates:
        results['completed'].append(f"Update {doc_path.name}: {status}")
    
    # Verify removal
    if verify_removal():
        results['completed'].append("Verification: All references removed")
    else:
        results['failed'].append("Verification: References still exist")
        results['success'] = False
    
    # Generate report
    generate_report(results)
    
    if results['success']:
        print(f"\n{GREEN}✅ Migration completed successfully!{RESET}")
        print(f"{GREEN}wait_for_messages has been removed.{RESET}")
        print(f"{GREEN}All agents should now use the elicitation system.{RESET}")
    else:
        print(f"\n{YELLOW}⚠️  Migration completed with issues.{RESET}")
        print(f"{YELLOW}Please review the failed tasks and complete manually.{RESET}")
    
    print(f"\n{BLUE}Next Steps:{RESET}")
    print("  1. Run the test suite to ensure everything works")
    print("  2. Monitor logs for any 404 errors on removed endpoints")
    print("  3. Verify all agents are using elicitation successfully")
    print()

if __name__ == "__main__":
    main()