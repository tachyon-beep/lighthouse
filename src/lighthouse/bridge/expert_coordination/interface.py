"""
Expert Agent Interface

Primary interface for expert agents to interact with the Lighthouse system
through the FUSE mount as the primary interface.

Expert agents use standard Unix tools through the mounted filesystem:
- Read validation requests from named pipes  
- Access context packages through filesystem
- Submit responses through output streams
- Use standard tools like cat, grep, find, vim
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from ..speed_layer.models import ValidationRequest, ValidationResult
from .context_manager import ContextPackage

logger = logging.getLogger(__name__)


class ExpertResponse:
    """Response from expert agent"""
    
    def __init__(self,
                 request_id: str,
                 decision: str,
                 confidence: float,
                 reasoning: str,
                 expert_id: str,
                 processing_time: float = 0.0,
                 metadata: Optional[Dict[str, Any]] = None):
        self.request_id = request_id
        self.decision = decision  # approved, blocked, escalate
        self.confidence = confidence  # 0.0 to 1.0
        self.reasoning = reasoning
        self.expert_id = expert_id
        self.processing_time = processing_time
        self.metadata = metadata or {}
        self.timestamp = asyncio.get_event_loop().time()
    
    def to_json(self) -> str:
        """Convert to JSON for stream output"""
        return json.dumps({
            'request_id': self.request_id,
            'decision': self.decision,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'expert_id': self.expert_id,
            'processing_time': self.processing_time,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ExpertResponse':
        """Create from JSON"""
        data = json.loads(json_str)
        return cls(**data)


class ExpertAgentInterface:
    """
    Expert agents interact through FUSE mount as primary interface
    
    This class provides utilities for expert agents to:
    - Read validation requests from streams
    - Access context packages  
    - Submit responses
    - Use standard Unix tools
    """
    
    def __init__(self, 
                 expert_id: str,
                 mount_point: str = "/mnt/lighthouse/project",
                 capabilities: Optional[List[str]] = None):
        """
        Initialize expert agent interface
        
        Args:
            expert_id: Unique identifier for this expert agent
            mount_point: Path to FUSE mount point
            capabilities: List of expert capabilities
        """
        self.expert_id = expert_id
        self.mount_point = Path(mount_point)
        self.capabilities = capabilities or []
        
        # Key filesystem paths
        self.context_dir = self.mount_point / "context"
        self.streams_dir = self.mount_point / "streams" 
        self.current_dir = self.mount_point / "current"
        self.history_dir = self.mount_point / "history"
        self.shadows_dir = self.mount_point / "shadows"
        
        # Stream paths
        self.validation_requests_stream = self.streams_dir / "validation_requests"
        self.expert_responses_stream = self.streams_dir / "expert_responses"
        
        # State tracking
        self.is_active = False
        self.processed_requests = 0
    
    async def start_listening(self):
        """Start listening for validation requests"""
        logger.info(f"Expert {self.expert_id} starting to listen for requests")
        self.is_active = True
        
        while self.is_active:
            try:
                # Read validation request from stream
                request = await self.receive_validation_request()
                
                if request:
                    # Process the request
                    response = await self.process_validation_request(request)
                    
                    # Submit response
                    await self.submit_expert_response(response)
                    
                    self.processed_requests += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in expert {self.expert_id} request processing: {e}")
                await asyncio.sleep(1.0)  # Brief pause before retry
    
    async def receive_validation_request(self) -> Optional[ValidationRequest]:
        """
        Expert agents read from validation stream
        
        This blocks until data is available in the named pipe.
        """
        try:
            # Named pipe - blocks until data available
            async with aiofiles.open(self.validation_requests_stream, 'r') as f:
                request_line = await f.readline()
                
                if request_line.strip():
                    request_data = json.loads(request_line.strip())
                    
                    # Convert to ValidationRequest object
                    return ValidationRequest(
                        tool_name=request_data['tool_name'],
                        tool_input=request_data['tool_input'],
                        agent_id=request_data['agent_id'],
                        request_id=request_data.get('request_id'),
                        context=request_data.get('context', {})
                    )
            
            return None
            
        except FileNotFoundError:
            # Stream not available yet
            await asyncio.sleep(0.1)
            return None
        except Exception as e:
            logger.warning(f"Error reading validation request: {e}")
            return None
    
    async def submit_expert_response(self, response: ExpertResponse):
        """Expert agents write to response stream"""
        try:
            async with aiofiles.open(self.expert_responses_stream, 'a') as f:
                await f.write(response.to_json() + '\n')
                
        except Exception as e:
            logger.error(f"Error submitting expert response: {e}")
    
    def get_context_package(self, package_id: str) -> Optional[ContextPackage]:
        """
        Load context package for informed decision-making
        
        Expert agents can access context packages through standard filesystem operations.
        """
        try:
            package_path = self.context_dir / package_id
            
            if not package_path.exists():
                logger.warning(f"Context package {package_id} not found")
                return None
            
            # Load manifest
            manifest_path = package_path / "manifest.json"
            if not manifest_path.exists():
                logger.warning(f"Context package {package_id} missing manifest")
                return None
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Create context package
            return ContextPackage(
                package_id=package_id,
                title=manifest.get('title', package_id),
                description=manifest.get('description', ''),
                architectural_context=self._load_architectural_context(package_path),
                implementation_context=self._load_implementation_context(package_path),
                historical_context=self._load_historical_context(package_path),
                metadata=manifest.get('metadata', {})
            )
            
        except Exception as e:
            logger.error(f"Error loading context package {package_id}: {e}")
            return None
    
    def _load_architectural_context(self, package_path: Path) -> Dict[str, str]:
        """Load architectural context from package"""
        context = {}
        
        arch_dir = package_path / "architectural_context"
        if arch_dir.exists():
            for file_path in arch_dir.rglob("*.md"):
                try:
                    context[file_path.name] = file_path.read_text()
                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")
        
        return context
    
    def _load_implementation_context(self, package_path: Path) -> Dict[str, str]:
        """Load implementation context from package"""
        context = {}
        
        impl_dir = package_path / "implementation_context"
        if impl_dir.exists():
            for file_path in impl_dir.rglob("*"):
                if file_path.is_file():
                    try:
                        context[str(file_path.relative_to(impl_dir))] = file_path.read_text()
                    except Exception as e:
                        logger.warning(f"Error reading {file_path}: {e}")
        
        return context
    
    def _load_historical_context(self, package_path: Path) -> Dict[str, Any]:
        """Load historical context from package"""
        context = {}
        
        hist_dir = package_path / "historical_context"
        if hist_dir.exists():
            for file_path in hist_dir.rglob("*.json"):
                try:
                    with open(file_path, 'r') as f:
                        context[file_path.name] = json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")
        
        return context
    
    async def process_validation_request(self, request: ValidationRequest) -> ExpertResponse:
        """
        Process validation request (to be implemented by specific experts)
        
        This is a default implementation that expert agents can override.
        """
        
        # Simple rule-based processing for demonstration
        decision = "approved"
        confidence = 0.8
        reasoning = f"Default expert processing for {request.tool_name} command"
        
        # Check for dangerous patterns
        if request.tool_name == "Bash":
            command = request.tool_input.get('command', '')
            if any(pattern in command for pattern in ['rm -rf', 'sudo rm', 'chmod 777']):
                decision = "blocked"
                confidence = 0.95
                reasoning = f"Dangerous command pattern detected: {command}"
        
        return ExpertResponse(
            request_id=request.request_id,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            expert_id=self.expert_id
        )
    
    # Unix tool integration methods
    
    def find_files(self, pattern: str, directory: Optional[str] = None) -> List[str]:
        """Use find command to locate files"""
        search_path = Path(directory) if directory else self.current_dir
        
        try:
            import subprocess
            result = subprocess.run(
                ['find', str(search_path), '-name', pattern],
                capture_output=True,
                text=True,
                cwd=str(search_path)
            )
            
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
            
        except Exception as e:
            logger.warning(f"Error running find command: {e}")
        
        return []
    
    def grep_files(self, pattern: str, files: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """Use grep to search in files"""
        if not files:
            files = self.find_files("*")
        
        results = {}
        
        try:
            import subprocess
            
            for file_path in files[:10]:  # Limit to first 10 files
                result = subprocess.run(
                    ['grep', '-n', pattern, file_path],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    matches = [line.strip() for line in result.stdout.splitlines()]
                    if matches:
                        results[file_path] = matches
                        
        except Exception as e:
            logger.warning(f"Error running grep command: {e}")
        
        return results
    
    def read_file(self, file_path: str) -> Optional[str]:
        """Read file content (equivalent to cat)"""
        try:
            full_path = self.current_dir / file_path
            return full_path.read_text()
        except Exception as e:
            logger.warning(f"Error reading file {file_path}: {e}")
            return None
    
    def list_directory(self, directory: Optional[str] = None) -> List[str]:
        """List directory contents (equivalent to ls)"""
        try:
            dir_path = Path(directory) if directory else self.current_dir
            return [item.name for item in dir_path.iterdir()]
        except Exception as e:
            logger.warning(f"Error listing directory {directory}: {e}")
            return []
    
    def get_file_stats(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get file statistics (equivalent to stat)"""
        try:
            full_path = self.current_dir / file_path
            stat = full_path.stat()
            
            return {
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'permissions': oct(stat.st_mode)[-3:],
                'is_file': full_path.is_file(),
                'is_dir': full_path.is_dir()
            }
            
        except Exception as e:
            logger.warning(f"Error getting stats for {file_path}: {e}")
            return None
    
    async def stop_listening(self):
        """Stop listening for requests"""
        logger.info(f"Expert {self.expert_id} stopping")
        self.is_active = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get expert agent status"""
        return {
            'expert_id': self.expert_id,
            'is_active': self.is_active,
            'capabilities': self.capabilities,
            'processed_requests': self.processed_requests,
            'mount_point': str(self.mount_point)
        }