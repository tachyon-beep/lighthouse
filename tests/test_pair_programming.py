"""Tests for pair programming functionality."""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from lighthouse.bridge import ValidationBridge, PairProgrammingSession
from lighthouse.validator import CommandValidator


class TestPairProgrammingBridge:
    """Test cases for pair programming in ValidationBridge."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.bridge = ValidationBridge(port=8766)
    
    @pytest.mark.asyncio
    async def test_pair_request_creation(self):
        """Test creating a pair programming request."""
        from aiohttp.web import Request
        from aiohttp.test_utils import make_mocked_request
        
        # Mock request
        request_data = {
            'requester': 'agent1',
            'task': 'Optimize database queries',
            'mode': 'COLLABORATIVE'
        }
        
        mock_request = make_mocked_request('POST', '/pair/request')
        mock_request.json = AsyncMock(return_value=request_data)
        
        # Mock notify_subscribers
        self.bridge.notify_subscribers = AsyncMock()
        
        response = await self.bridge.handle_pair_request(mock_request)
        
        assert response.status == 200
        response_data = json.loads(response.body.decode())
        
        assert response_data['success'] == True
        assert 'session_id' in response_data
        assert response_data['status'] == 'pending'
        
        # Check session was stored
        session_id = response_data['session_id']
        assert session_id in self.bridge.pair_sessions
        
        session = self.bridge.pair_sessions[session_id]
        assert session.requester == 'agent1'
        assert session.task == 'Optimize database queries'
        assert session.mode == 'COLLABORATIVE'
        assert session.status == 'pending'
    
    @pytest.mark.asyncio
    async def test_pair_acceptance(self):
        """Test accepting a pair programming session."""
        from aiohttp.test_utils import make_mocked_request
        
        # Create a session first
        session = PairProgrammingSession(
            id='test_session',
            requester='agent1',
            task='Test task',
            timestamp=1234567890
        )
        self.bridge.pair_sessions['test_session'] = session
        
        # Mock request
        request_data = {
            'session_id': 'test_session',
            'partner': 'agent2'
        }
        
        mock_request = make_mocked_request('POST', '/pair/accept')
        mock_request.json = AsyncMock(return_value=request_data)
        
        # Mock notify_subscribers
        self.bridge.notify_subscribers = AsyncMock()
        
        response = await self.bridge.handle_pair_accept(mock_request)
        
        assert response.status == 200
        response_data = json.loads(response.body.decode())
        
        assert response_data['success'] == True
        assert response_data['session_id'] == 'test_session'
        assert response_data['status'] == 'active'
        
        # Check session was updated
        updated_session = self.bridge.pair_sessions['test_session']
        assert updated_session.partner == 'agent2'
        assert updated_session.status == 'active'
    
    @pytest.mark.asyncio
    async def test_pair_suggestion(self):
        """Test sending a pair programming suggestion."""
        from aiohttp.test_utils import make_mocked_request
        
        # Create an active session
        session = PairProgrammingSession(
            id='test_session',
            requester='agent1',
            partner='agent2',
            status='active',
            task='Test task',
            timestamp=1234567890
        )
        self.bridge.pair_sessions['test_session'] = session
        
        # Mock request
        request_data = {
            'session_id': 'test_session',
            'agent': 'agent1',
            'suggestion': 'Let me add an index to the user_id column'
        }
        
        mock_request = make_mocked_request('POST', '/pair/suggest')
        mock_request.json = AsyncMock(return_value=request_data)
        
        # Mock notify_subscribers
        self.bridge.notify_subscribers = AsyncMock()
        
        response = await self.bridge.handle_pair_suggest(mock_request)
        
        assert response.status == 200
        response_data = json.loads(response.body.decode())
        
        assert response_data['success'] == True
        assert 'suggestion_id' in response_data
        
        # Check suggestion was added
        updated_session = self.bridge.pair_sessions['test_session']
        assert len(updated_session.suggestions) == 1
        
        suggestion = updated_session.suggestions[0]
        assert suggestion['agent'] == 'agent1'
        assert suggestion['content'] == 'Let me add an index to the user_id column'
        assert suggestion['status'] == 'pending'
    
    @pytest.mark.asyncio
    async def test_pair_review(self):
        """Test reviewing a pair programming suggestion."""
        from aiohttp.test_utils import make_mocked_request
        
        # Create an active session with a suggestion
        session = PairProgrammingSession(
            id='test_session',
            requester='agent1',
            partner='agent2',
            status='active',
            task='Test task',
            timestamp=1234567890,
            suggestions=[{
                'id': 'sugg_123',
                'agent': 'agent1',
                'content': 'Add database index',
                'timestamp': 1234567890,
                'status': 'pending'
            }]
        )
        self.bridge.pair_sessions['test_session'] = session
        
        # Mock request
        request_data = {
            'session_id': 'test_session',
            'suggestion_id': 'sugg_123',
            'reviewer': 'agent2',
            'decision': 'approve',
            'feedback': 'Good idea, this will improve query performance'
        }
        
        mock_request = make_mocked_request('POST', '/pair/review')
        mock_request.json = AsyncMock(return_value=request_data)
        
        # Mock notify_subscribers
        self.bridge.notify_subscribers = AsyncMock()
        
        response = await self.bridge.handle_pair_review(mock_request)
        
        assert response.status == 200
        response_data = json.loads(response.body.decode())
        
        assert response_data['success'] == True
        assert response_data['decision'] == 'approve'
        
        # Check suggestion was updated
        updated_session = self.bridge.pair_sessions['test_session']
        suggestion = updated_session.suggestions[0]
        assert suggestion['status'] == 'approve'
        assert suggestion['reviewer'] == 'agent2'
        assert suggestion['feedback'] == 'Good idea, this will improve query performance'
    
    @pytest.mark.asyncio
    async def test_get_pair_sessions(self):
        """Test getting active pair programming sessions."""
        from aiohttp.test_utils import make_mocked_request
        
        # Create test sessions
        session1 = PairProgrammingSession(
            id='session1',
            requester='agent1',
            task='Task 1',
            timestamp=1234567890
        )
        session2 = PairProgrammingSession(
            id='session2',
            requester='agent2',
            partner='agent3',
            status='active',
            task='Task 2',
            timestamp=1234567891
        )
        
        self.bridge.pair_sessions['session1'] = session1
        self.bridge.pair_sessions['session2'] = session2
        
        mock_request = make_mocked_request('GET', '/pair/sessions')
        
        response = await self.bridge.handle_get_pair_sessions(mock_request)
        
        assert response.status == 200
        response_data = json.loads(response.body.decode())
        
        assert 'sessions' in response_data
        assert len(response_data['sessions']) == 2
        
        # Check session data
        session_ids = [s['id'] for s in response_data['sessions']]
        assert 'session1' in session_ids
        assert 'session2' in session_ids


class TestPairProgrammingValidator:
    """Test cases for pair programming in CommandValidator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = CommandValidator("http://localhost:8766")
    
    @pytest.mark.asyncio
    async def test_request_pair_programming(self):
        """Test requesting a pair programming session."""
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'success': True,
                'session_id': 'pair_123',
                'status': 'pending'
            }
            mock_post.return_value = mock_response
            
            result = await self.validator.request_pair_programming(
                task='Debug authentication flow',
                mode='COLLABORATIVE',
                agent_id='validator_agent'
            )
            
            assert result['success'] == True
            assert result['session_id'] == 'pair_123'
            assert self.validator.current_session_id == 'pair_123'
            assert self.validator.pair_mode == 'COLLABORATIVE'
    
    @pytest.mark.asyncio
    async def test_accept_pair_session(self):
        """Test accepting a pair programming session."""
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'success': True,
                'session_id': 'pair_123',
                'status': 'active'
            }
            mock_post.return_value = mock_response
            
            result = await self.validator.accept_pair_session(
                session_id='pair_123',
                agent_id='validator_agent'
            )
            
            assert result['success'] == True
            assert self.validator.current_session_id == 'pair_123'
            assert self.validator.pair_mode == 'ACTIVE'
    
    @pytest.mark.asyncio
    async def test_suggest_to_pair(self):
        """Test sending suggestion to pair partner."""
        self.validator.current_session_id = 'pair_123'
        
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'success': True,
                'suggestion_id': 'sugg_456'
            }
            mock_post.return_value = mock_response
            
            result = await self.validator.suggest_to_pair(
                suggestion='Consider using async/await for this database call',
                agent_id='validator_agent'
            )
            
            assert result['success'] == True
            assert result['suggestion_id'] == 'sugg_456'
    
    @pytest.mark.asyncio
    async def test_review_suggestion(self):
        """Test reviewing a suggestion."""
        self.validator.current_session_id = 'pair_123'
        
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'success': True,
                'decision': 'approve'
            }
            mock_post.return_value = mock_response
            
            result = await self.validator.review_suggestion(
                suggestion_id='sugg_456',
                decision='approve',
                feedback='Excellent suggestion, this will improve performance',
                agent_id='validator_agent'
            )
            
            assert result['success'] == True
            assert result['decision'] == 'approve'
    
    @pytest.mark.asyncio
    async def test_validate_with_pair_collaborative(self):
        """Test validation with pair programming in collaborative mode."""
        self.validator.pair_mode = 'COLLABORATIVE'
        self.validator.current_session_id = 'pair_123'
        
        with patch.object(self.validator, 'validate_command') as mock_validate:
            with patch.object(self.validator, 'suggest_to_pair') as mock_suggest:
                # Mock validation result that needs review
                mock_validate.return_value = {
                    'status': 'review_required',
                    'risk_level': 'medium',
                    'reason': 'Sudo command requires review'
                }
                
                # Mock successful suggestion
                mock_suggest.return_value = {
                    'success': True,
                    'suggestion_id': 'sugg_789'
                }
                
                result = await self.validator.validate_with_pair(
                    tool='Bash',
                    tool_input={'command': 'sudo apt update'},
                    agent='test_agent'
                )
                
                assert result['status'] == 'review_required'
                assert result['pair_consultation'] == True
                assert result['suggestion_id'] == 'sugg_789'
                assert 'Shared with pair partner' in result['reason']
    
    @pytest.mark.asyncio
    async def test_validate_with_pair_passive(self):
        """Test validation with pair programming in passive mode."""
        self.validator.pair_mode = 'PASSIVE'
        self.validator.current_session_id = 'pair_123'
        
        with patch.object(self.validator, 'validate_command') as mock_validate:
            # Mock validation result that needs review
            mock_validate.return_value = {
                'status': 'review_required',
                'risk_level': 'medium',
                'reason': 'Sudo command requires review'
            }
            
            result = await self.validator.validate_with_pair(
                tool='Bash',
                tool_input={'command': 'sudo apt update'},
                agent='test_agent'
            )
            
            # In passive mode, no pair consultation should occur
            assert result['status'] == 'review_required'
            assert 'pair_consultation' not in result
    
    def test_set_pair_mode(self):
        """Test setting pair programming mode."""
        self.validator.set_pair_mode('ACTIVE')
        assert self.validator.pair_mode == 'ACTIVE'
        
        self.validator.set_pair_mode('COLLABORATIVE')
        assert self.validator.pair_mode == 'COLLABORATIVE'
        
        self.validator.set_pair_mode('REVIEW')
        assert self.validator.pair_mode == 'REVIEW'
        
        # Invalid mode should not change current mode
        self.validator.set_pair_mode('INVALID')
        assert self.validator.pair_mode == 'REVIEW'
    
    def test_end_pair_session(self):
        """Test ending a pair programming session."""
        self.validator.current_session_id = 'pair_123'
        self.validator.pair_mode = 'ACTIVE'
        
        self.validator.end_pair_session()
        
        assert self.validator.current_session_id is None
        assert self.validator.pair_mode == 'PASSIVE'


class TestPairProgrammingIntegration:
    """Integration tests for pair programming functionality."""
    
    @pytest.mark.asyncio
    async def test_full_pair_programming_workflow(self):
        """Test a complete pair programming workflow."""
        bridge = ValidationBridge(port=8767)
        validator1 = CommandValidator("http://localhost:8767")
        validator2 = CommandValidator("http://localhost:8767")
        
        # Start bridge
        await bridge.start()
        
        try:
            # Agent 1 requests pair programming
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'success': True,
                    'session_id': 'pair_integration',
                    'status': 'pending'
                }
                mock_post.return_value = mock_response
                
                request_result = await validator1.request_pair_programming(
                    task='Optimize database performance',
                    agent_id='agent1'
                )
                
                assert request_result['success'] == True
            
            # Agent 2 accepts the session
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'success': True,
                    'session_id': 'pair_integration',
                    'status': 'active'
                }
                mock_post.return_value = mock_response
                
                accept_result = await validator2.accept_pair_session(
                    session_id='pair_integration',
                    agent_id='agent2'
                )
                
                assert accept_result['success'] == True
            
            # Agent 1 makes a suggestion
            validator1.current_session_id = 'pair_integration'
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'success': True,
                    'suggestion_id': 'sugg_integration'
                }
                mock_post.return_value = mock_response
                
                suggest_result = await validator1.suggest_to_pair(
                    'Add composite index on (user_id, created_at)',
                    agent_id='agent1'
                )
                
                assert suggest_result['success'] == True
            
            # Agent 2 reviews the suggestion
            validator2.current_session_id = 'pair_integration'
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'success': True,
                    'decision': 'approve'
                }
                mock_post.return_value = mock_response
                
                review_result = await validator2.review_suggestion(
                    suggestion_id='sugg_integration',
                    decision='approve',
                    feedback='Great idea! This will speed up the recent posts query.',
                    agent_id='agent2'
                )
                
                assert review_result['success'] == True
                assert review_result['decision'] == 'approve'
                
        finally:
            await bridge.stop()