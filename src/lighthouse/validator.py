"""Command validator for the Lighthouse system."""

import logging
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

class CommandValidator:
    """Validates commands before execution."""
    
    def __init__(self, bridge_url: str = "http://localhost:8765"):
        self.validation_rules = self._load_validation_rules()
        self.bridge_url = bridge_url
        self.pair_mode = "PASSIVE"  # PASSIVE, ACTIVE, COLLABORATIVE, REVIEW
        self.current_session_id: Optional[str] = None
    
    def _load_validation_rules(self) -> Dict[str, Any]:
        """Load validation rules configuration."""
        return {
            "dangerous_bash_patterns": [
                r"rm\s+-rf\s+/",
                r"rm\s+-rf\s+\*",
                r"sudo\s+rm",
                r"chmod\s+777",
                r">\s*/dev/",
                r"dd\s+if=",
                r"mkfs",
                r"fdisk",
                r"shutdown",
                r"reboot",
                r"init\s+0",
                r"kill\s+-9\s+1"
            ],
            "protected_paths": [
                "/etc/",
                "/usr/",
                "/var/",
                "/boot/",
                "/sys/",
                "/proc/",
                "/dev/"
            ],
            "safe_tools": [
                "Read",
                "Glob",
                "Grep",
                "LS"
            ],
            "review_required_tools": [
                "Bash",
                "Write",
                "Edit",
                "MultiEdit"
            ]
        }
    
    async def validate_command(self, tool: str, tool_input: Dict[str, Any], agent: str = "unknown") -> Dict[str, Any]:
        """Validate a command and return approval/rejection."""
        try:
            validation_result = {
                "id": f"val_{int(time.time()*1000)}",
                "tool": tool,
                "agent": agent,
                "timestamp": time.time(),
                "status": "approved",
                "reason": "Command validated successfully",
                "risk_level": "low"
            }
            
            # Check if tool is in safe list
            if tool in self.validation_rules["safe_tools"]:
                validation_result["reason"] = f"Safe tool: {tool}"
                return validation_result
            
            # Validate based on tool type
            if tool == "Bash":
                return await self._validate_bash_command(tool_input, validation_result)
            
            elif tool in ["Write", "Edit", "MultiEdit"]:
                return await self._validate_file_operation(tool_input, validation_result)
            
            elif tool in self.validation_rules["review_required_tools"]:
                validation_result["status"] = "review_required"
                validation_result["reason"] = f"Tool {tool} requires manual review"
                validation_result["risk_level"] = "medium"
                return validation_result
            
            else:
                # Unknown tool - require review
                validation_result["status"] = "review_required"
                validation_result["reason"] = f"Unknown tool: {tool}"
                validation_result["risk_level"] = "medium"
                return validation_result
                
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "status": "blocked",
                "reason": f"Validation error: {str(e)}",
                "risk_level": "high"
            }
    
    async def _validate_bash_command(self, tool_input: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate bash commands."""
        command = tool_input.get("command", "")
        
        # Check for dangerous patterns
        import re
        for pattern in self.validation_rules["dangerous_bash_patterns"]:
            if re.search(pattern, command, re.IGNORECASE):
                result["status"] = "blocked"
                result["reason"] = f"Dangerous command pattern detected: {pattern}"
                result["risk_level"] = "high"
                result["concern"] = "This command could cause system damage"
                return result
        
        # Check for specific risky commands
        risky_commands = ["sudo", "rm", "chmod", "chown", "dd", "fdisk"]
        for risky_cmd in risky_commands:
            if risky_cmd in command.lower():
                result["status"] = "review_required"
                result["reason"] = f"Risky command requires review: {risky_cmd}"
                result["risk_level"] = "medium"
                result["concern"] = "Manual approval needed for system commands"
                return result
        
        # Safe command
        result["reason"] = "Bash command appears safe"
        return result
    
    async def _validate_file_operation(self, tool_input: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate file operations."""
        file_path = tool_input.get("file_path", "")
        
        # Check for protected paths
        for protected_path in self.validation_rules["protected_paths"]:
            if file_path.startswith(protected_path):
                result["status"] = "blocked"
                result["reason"] = f"Access to protected path: {protected_path}"
                result["risk_level"] = "high"
                result["concern"] = "Modifying system files is not allowed"
                return result
        
        # Check for dangerous file operations
        if tool_input.get("old_string") == "" and len(tool_input.get("new_string", "")) > 10000:
            result["status"] = "review_required"
            result["reason"] = "Large file creation requires review"
            result["risk_level"] = "medium"
            return result
        
        # Safe file operation
        result["reason"] = "File operation appears safe"
        return result
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        return {
            "rules_loaded": len(self.validation_rules),
            "dangerous_patterns": len(self.validation_rules["dangerous_bash_patterns"]),
            "protected_paths": len(self.validation_rules["protected_paths"])
        }
    
    # Pair Programming Methods
    
    async def request_pair_programming(self, task: str, mode: str = "COLLABORATIVE", agent_id: str = "validator") -> Dict[str, Any]:
        """Request a pair programming session."""
        try:
            response = requests.post(f"{self.bridge_url}/pair/request", 
                json={
                    "requester": agent_id,
                    "task": task,
                    "mode": mode
                }, 
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    self.current_session_id = data["session_id"]
                    self.pair_mode = mode
                    logger.info(f"Pair programming session requested: {self.current_session_id}")
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Failed to request pair programming: {e}")
            return {"success": False, "error": str(e)}
    
    async def accept_pair_session(self, session_id: str, agent_id: str = "validator") -> Dict[str, Any]:
        """Accept a pair programming session."""
        try:
            response = requests.post(f"{self.bridge_url}/pair/accept",
                json={
                    "session_id": session_id,
                    "partner": agent_id
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    self.current_session_id = session_id
                    self.pair_mode = "ACTIVE"
                    logger.info(f"Accepted pair programming session: {session_id}")
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Failed to accept pair session: {e}")
            return {"success": False, "error": str(e)}
    
    async def suggest_to_pair(self, suggestion: str, agent_id: str = "validator") -> Dict[str, Any]:
        """Send a suggestion to pair programming partner."""
        if not self.current_session_id:
            return {"success": False, "error": "No active pair session"}
        
        try:
            response = requests.post(f"{self.bridge_url}/pair/suggest",
                json={
                    "session_id": self.current_session_id,
                    "agent": agent_id,
                    "suggestion": suggestion
                },
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Failed to send suggestion: {e}")
            return {"success": False, "error": str(e)}
    
    async def review_suggestion(self, suggestion_id: str, decision: str, feedback: str = "", agent_id: str = "validator") -> Dict[str, Any]:
        """Review a pair programming suggestion."""
        if not self.current_session_id:
            return {"success": False, "error": "No active pair session"}
        
        try:
            response = requests.post(f"{self.bridge_url}/pair/review",
                json={
                    "session_id": self.current_session_id,
                    "suggestion_id": suggestion_id,
                    "reviewer": agent_id,
                    "decision": decision,
                    "feedback": feedback
                },
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Failed to review suggestion: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_pair_sessions(self) -> Dict[str, Any]:
        """Get active pair programming sessions."""
        try:
            response = requests.get(f"{self.bridge_url}/pair/sessions", timeout=5)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Failed to get pair sessions: {e}")
            return {"success": False, "error": str(e)}
    
    async def validate_with_pair(self, tool: str, tool_input: Dict[str, Any], agent: str = "unknown") -> Dict[str, Any]:
        """Validate command with pair programming support."""
        # First do standard validation
        result = await self.validate_command(tool, tool_input, agent)
        
        # If in collaborative mode and command needs review, involve pair
        if (self.pair_mode == "COLLABORATIVE" and 
            result["status"] == "review_required" and 
            self.current_session_id):
            
            # Suggest to pair partner for review
            suggestion_text = f"Command needs review: {tool} with {tool_input}. Risk: {result['risk_level']}. Reason: {result['reason']}"
            
            suggestion_result = await self.suggest_to_pair(suggestion_text, agent)
            
            if suggestion_result.get("success"):
                result["pair_consultation"] = True
                result["suggestion_id"] = suggestion_result.get("suggestion_id")
                result["reason"] += " - Shared with pair partner for collaborative review"
                
        return result
    
    def set_pair_mode(self, mode: str):
        """Set the pair programming mode."""
        if mode in ["PASSIVE", "ACTIVE", "COLLABORATIVE", "REVIEW"]:
            self.pair_mode = mode
            logger.info(f"Pair mode set to: {mode}")
        else:
            logger.warning(f"Invalid pair mode: {mode}")
    
    def end_pair_session(self):
        """End the current pair programming session."""
        if self.current_session_id:
            logger.info(f"Ending pair session: {self.current_session_id}")
            self.current_session_id = None
            self.pair_mode = "PASSIVE"