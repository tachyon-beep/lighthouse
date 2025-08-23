"""Validation bridge for inter-agent communication."""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import aiohttp
import aiohttp.web
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class CommandData(BaseModel):
    """Command validation data structure."""
    id: str
    tool: str
    input: Dict[str, Any]
    agent: str
    timestamp: float
    status: str = "pending"

class PairProgrammingSession(BaseModel):
    """Pair programming session data structure."""
    id: str
    requester: str
    partner: Optional[str] = None
    mode: str = "COLLABORATIVE"  # PASSIVE, ACTIVE, COLLABORATIVE, REVIEW
    status: str = "pending"  # pending, active, completed, cancelled
    task: str
    suggestions: List[Dict[str, Any]] = []
    timestamp: float

class ValidationBridge:
    """Bridge for command validation between agents."""
    
    def __init__(self, port: int = 8765):
        self.port = port
        self.pending_commands: Dict[str, CommandData] = {}
        self.approved_commands: Dict[str, Dict[str, Any]] = {}
        self.subscribers: List[Any] = []
        self.pair_sessions: Dict[str, PairProgrammingSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the validation bridge server."""
        self.app = aiohttp.web.Application()
        self.app.router.add_post('/validate', self.handle_validation)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_post('/approve', self.handle_approval)
        self.app.router.add_get('/pending', self.handle_get_pending)
        
        # Pair programming endpoints
        self.app.router.add_post('/pair/request', self.handle_pair_request)
        self.app.router.add_post('/pair/accept', self.handle_pair_accept)
        self.app.router.add_post('/pair/suggest', self.handle_pair_suggest)
        self.app.router.add_post('/pair/review', self.handle_pair_review)
        self.app.router.add_get('/pair/sessions', self.handle_get_pair_sessions)
        
        self.runner = aiohttp.web.AppRunner(self.app)
        await self.runner.setup()
        
        site = aiohttp.web.TCPSite(self.runner, 'localhost', self.port)
        await site.start()
        
        logger.info(f"Validation bridge started on http://localhost:{self.port}")
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())
    
    async def stop(self):
        """Stop the validation bridge server."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            
        if hasattr(self, 'runner'):
            await self.runner.cleanup()
    
    async def handle_validation(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle command validation requests."""
        try:
            data = await request.json()
            
            command = CommandData(
                id=data.get('id', f"cmd_{int(time.time()*1000)}"),
                tool=data['tool'],
                input=data['input'],
                agent=data.get('agent', 'unknown'),
                timestamp=time.time()
            )
            
            # Check if pre-approved
            if self.check_pre_approved(command):
                return aiohttp.web.json_response({
                    'status': 'approved',
                    'reason': 'Pre-approved',
                    'id': command.id
                })
            
            # Check if dangerous command
            if self.is_dangerous_command(command):
                if not await self.wait_for_validator():
                    return aiohttp.web.json_response({
                        'status': 'blocked',
                        'reason': 'No validator available for dangerous command',
                        'concern': 'Join bridge to discuss this command',
                        'id': command.id
                    })
            
            # Add to pending and wait for response
            self.pending_commands[command.id] = command
            
            # Notify subscribers about new pending command
            await self.notify_subscribers('command_pending', command.model_dump())
            
            # Wait for validation response
            result = await self.wait_for_validation(command.id, timeout=2.0)
            
            return aiohttp.web.json_response(result)
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return aiohttp.web.json_response({
                'status': 'error',
                'reason': str(e)
            }, status=500)
    
    async def handle_status(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle status requests."""
        return aiohttp.web.json_response({
            'status': 'running',
            'pending_commands': len(self.pending_commands),
            'approved_commands': len(self.approved_commands),
            'subscribers': len(self.subscribers),
            'uptime': time.time()
        })
    
    async def handle_approval(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle command approval."""
        try:
            data = await request.json()
            command_id = data['id']
            status = data.get('status', 'approved')
            reason = data.get('reason', 'Manual approval')
            
            if command_id in self.pending_commands:
                self.pending_commands[command_id].status = status
                
                if status == 'approved':
                    self.approved_commands[command_id] = {
                        'timestamp': time.time(),
                        'reason': reason
                    }
            
            return aiohttp.web.json_response({
                'success': True,
                'id': command_id,
                'status': status
            })
            
        except Exception as e:
            return aiohttp.web.json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    
    async def handle_get_pending(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Get pending commands."""
        return aiohttp.web.json_response({
            'pending': [cmd.model_dump() for cmd in self.pending_commands.values()]
        })
    
    async def handle_pair_request(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle pair programming session request."""
        try:
            data = await request.json()
            
            session = PairProgrammingSession(
                id=data.get('id', f"pair_{int(time.time()*1000)}"),
                requester=data['requester'],
                mode=data.get('mode', 'COLLABORATIVE'),
                task=data['task'],
                timestamp=time.time()
            )
            
            self.pair_sessions[session.id] = session
            
            # Notify available agents about pair request
            await self.notify_subscribers('pair_request', session.model_dump())
            
            return aiohttp.web.json_response({
                'success': True,
                'session_id': session.id,
                'status': 'pending',
                'message': 'Pair programming request created'
            })
            
        except Exception as e:
            return aiohttp.web.json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    
    async def handle_pair_accept(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle pair programming session acceptance."""
        try:
            data = await request.json()
            session_id = data['session_id']
            partner = data['partner']
            
            if session_id not in self.pair_sessions:
                return aiohttp.web.json_response({
                    'success': False,
                    'error': 'Session not found'
                }, status=404)
            
            session = self.pair_sessions[session_id]
            if session.status != 'pending':
                return aiohttp.web.json_response({
                    'success': False,
                    'error': 'Session no longer available'
                }, status=400)
            
            session.partner = partner
            session.status = 'active'
            
            # Notify both agents about successful pairing
            await self.notify_subscribers('pair_accepted', {
                'session_id': session_id,
                'requester': session.requester,
                'partner': partner,
                'mode': session.mode,
                'task': session.task
            })
            
            return aiohttp.web.json_response({
                'success': True,
                'session_id': session_id,
                'status': 'active',
                'message': f'Paired with {session.requester}'
            })
            
        except Exception as e:
            return aiohttp.web.json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    
    async def handle_pair_suggest(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle pair programming suggestion."""
        try:
            data = await request.json()
            session_id = data['session_id']
            agent = data['agent']
            suggestion = data['suggestion']
            
            if session_id not in self.pair_sessions:
                return aiohttp.web.json_response({
                    'success': False,
                    'error': 'Session not found'
                }, status=404)
            
            session = self.pair_sessions[session_id]
            if session.status != 'active':
                return aiohttp.web.json_response({
                    'success': False,
                    'error': 'Session not active'
                }, status=400)
            
            # Add suggestion to session
            suggestion_data = {
                'id': f"sugg_{int(time.time()*1000)}",
                'agent': agent,
                'content': suggestion,
                'timestamp': time.time(),
                'status': 'pending'
            }
            
            session.suggestions.append(suggestion_data)
            
            # Notify partner about suggestion
            await self.notify_subscribers('pair_suggestion', {
                'session_id': session_id,
                'suggestion': suggestion_data
            })
            
            return aiohttp.web.json_response({
                'success': True,
                'suggestion_id': suggestion_data['id'],
                'message': 'Suggestion shared with partner'
            })
            
        except Exception as e:
            return aiohttp.web.json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    
    async def handle_pair_review(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle pair programming review."""
        try:
            data = await request.json()
            session_id = data['session_id']
            suggestion_id = data['suggestion_id']
            reviewer = data['reviewer']
            decision = data['decision']  # 'approve', 'reject', 'modify'
            feedback = data.get('feedback', '')
            
            if session_id not in self.pair_sessions:
                return aiohttp.web.json_response({
                    'success': False,
                    'error': 'Session not found'
                }, status=404)
            
            session = self.pair_sessions[session_id]
            
            # Find and update suggestion
            suggestion_found = False
            for suggestion in session.suggestions:
                if suggestion['id'] == suggestion_id:
                    suggestion['status'] = decision
                    suggestion['reviewer'] = reviewer
                    suggestion['feedback'] = feedback
                    suggestion['review_timestamp'] = time.time()
                    suggestion_found = True
                    break
            
            if not suggestion_found:
                return aiohttp.web.json_response({
                    'success': False,
                    'error': 'Suggestion not found'
                }, status=404)
            
            # Notify both agents about review
            await self.notify_subscribers('pair_review', {
                'session_id': session_id,
                'suggestion_id': suggestion_id,
                'decision': decision,
                'reviewer': reviewer,
                'feedback': feedback
            })
            
            return aiohttp.web.json_response({
                'success': True,
                'decision': decision,
                'message': f'Review completed: {decision}'
            })
            
        except Exception as e:
            return aiohttp.web.json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    
    async def handle_get_pair_sessions(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Get active pair programming sessions."""
        return aiohttp.web.json_response({
            'sessions': [session.model_dump() for session in self.pair_sessions.values()]
        })
    
    def check_pre_approved(self, command: CommandData) -> bool:
        """Check if command was pre-approved."""
        # Simple hash-based pre-approval check
        command_hash = self._hash_command(command)
        return command_hash in self.approved_commands
    
    def is_dangerous_command(self, command: CommandData) -> bool:
        """Check if command is potentially dangerous."""
        dangerous_patterns = [
            'rm -rf',
            'rm -r',
            'rmdir',
            'sudo',
            'chmod 777',
            'chown',
            '> /dev/',
            'dd if=',
            'mkfs',
            'fdisk',
            'parted',
            'shutdown',
            'reboot',
            'halt',
            'init 0',
            'kill -9',
            'pkill',
            'killall'
        ]
        
        if command.tool == 'Bash':
            cmd = command.input.get('command', '')
            return any(pattern in cmd for pattern in dangerous_patterns)
        
        if command.tool in ['Write', 'MultiEdit', 'Edit']:
            path = command.input.get('file_path', '')
            dangerous_paths = ['/etc/', '/usr/', '/var/', '/boot/', '/sys/', '/proc/']
            return any(path.startswith(dp) for dp in dangerous_paths)
        
        return False
    
    async def wait_for_validator(self) -> bool:
        """Check if a validator is available."""
        # Simple check - in real implementation, this would check for active subscribers
        return len(self.subscribers) > 0
    
    async def wait_for_validation(self, command_id: str, timeout: float = 2.0) -> Dict[str, Any]:
        """Wait for validation response."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if command_id in self.pending_commands:
                cmd = self.pending_commands[command_id]
                if cmd.status != 'pending':
                    result = {
                        'status': cmd.status,
                        'id': command_id
                    }
                    
                    if cmd.status == 'approved':
                        result['reason'] = 'Validated by supervisor'
                    else:
                        result['reason'] = 'Blocked by validator'
                        result['concern'] = 'Join bridge to discuss'
                    
                    # Clean up
                    del self.pending_commands[command_id]
                    return result
            
            await asyncio.sleep(0.1)
        
        # Timeout - fail safe or fail open based on danger level
        cmd = self.pending_commands.get(command_id)
        if cmd and self.is_dangerous_command(cmd):
            return {
                'status': 'blocked',
                'reason': 'Timeout on dangerous command',
                'concern': 'No validator responded - join bridge',
                'id': command_id
            }
        else:
            return {
                'status': 'approved',
                'reason': 'Timeout - proceeding with safe command',
                'id': command_id
            }
    
    async def notify_subscribers(self, event_type: str, data: Dict[str, Any]):
        """Notify subscribers of events."""
        # In real implementation, this would use WebSockets or similar
        logger.info(f"Event {event_type}: {data}")
    
    def _hash_command(self, command: CommandData) -> str:
        """Create a hash for command pre-approval."""
        import hashlib
        content = f"{command.tool}:{json.dumps(command.input, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def _cleanup_expired(self):
        """Clean up expired commands and approvals."""
        while True:
            try:
                current_time = time.time()
                
                # Clean up pending commands older than 5 minutes
                expired_pending = [
                    cmd_id for cmd_id, cmd in self.pending_commands.items()
                    if current_time - cmd.timestamp > 300
                ]
                
                for cmd_id in expired_pending:
                    del self.pending_commands[cmd_id]
                
                # Clean up approved commands older than 1 hour
                expired_approved = [
                    cmd_id for cmd_id, approval in self.approved_commands.items()
                    if current_time - approval['timestamp'] > 3600
                ]
                
                for cmd_id in expired_approved:
                    del self.approved_commands[cmd_id]
                
                # Clean up completed/cancelled pair sessions older than 2 hours
                expired_pairs = [
                    session_id for session_id, session in self.pair_sessions.items()
                    if session.status in ['completed', 'cancelled'] and 
                       current_time - session.timestamp > 7200
                ]
                
                for session_id in expired_pairs:
                    del self.pair_sessions[session_id]
                
                await asyncio.sleep(60)  # Clean up every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def get_status(self) -> Dict[str, Any]:
        """Get bridge status."""
        return {
            'status': 'running',
            'pending_commands': len(self.pending_commands),
            'approved_commands': len(self.approved_commands),
            'pair_sessions': len(self.pair_sessions),
            'active_pairs': len([s for s in self.pair_sessions.values() if s.status == 'active']),
            'port': self.port
        }
    
    async def approve_command(self, command_id: str, reason: str = "Manual approval") -> Dict[str, Any]:
        """Approve a command."""
        if command_id in self.pending_commands:
            self.pending_commands[command_id].status = 'approved'
            self.approved_commands[command_id] = {
                'timestamp': time.time(),
                'reason': reason
            }
            return {'success': True, 'id': command_id}
        
        return {'success': False, 'reason': 'Command not found'}