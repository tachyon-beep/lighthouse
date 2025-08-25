#!/usr/bin/env python3
"""
Simple test script to verify FUSE authentication bypass fix
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import hashlib
import hmac
import unittest
from unittest.mock import Mock

from lighthouse.bridge.fuse_mount.authentication import (
    FUSEAuthenticationManager, 
    FUSEAuthenticationContext,
    AgentSession,
    FileSystemPermission
)

class TestFUSEAuthenticationFix(unittest.TestCase):
    """Test that the FUSE authentication bypass vulnerability is fixed"""
    
    def setUp(self):
        """Set up test environment"""
        self.auth_secret = "test_secret_key_for_authentication"
        self.auth_manager = FUSEAuthenticationManager(self.auth_secret)
    
    def test_authentication_required(self):
        """Test that authentication is required for operations"""
        # Test without authentication - should fail
        context = FUSEAuthenticationContext(self.auth_manager)
        
        # No session set - should deny access
        self.assertFalse(context.check_access("/current/test.py", "read"))
        self.assertFalse(context.check_access("/current/test.py", "write"))
        self.assertIsNone(context.get_current_agent())
    
    def test_valid_authentication_works(self):
        """Test that valid authentication allows access"""
        agent_id = "test_agent_123"
        challenge = "auth_challenge_123"
        
        # Generate valid HMAC response
        response = hmac.new(
            self.auth_secret.encode('utf-8'),
            f"{agent_id}:{challenge}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Authenticate agent
        session_id = self.auth_manager.authenticate_agent(agent_id, challenge, response)
        self.assertIsNotNone(session_id)
        
        # Set session in context
        context = FUSEAuthenticationContext(self.auth_manager)
        context.set_session(session_id)
        
        # Now should have access
        self.assertEqual(context.get_current_agent(), agent_id)
        self.assertTrue(context.check_access("/current/test.py", "read"))
        self.assertTrue(context.check_access("/current/test.py", "write"))
    
    def test_invalid_hmac_rejected(self):
        """Test that invalid HMAC responses are rejected"""
        agent_id = "test_agent_456"
        challenge = "auth_challenge_456"
        invalid_response = "invalid_hmac_response"
        
        # Authentication should fail
        session_id = self.auth_manager.authenticate_agent(agent_id, challenge, invalid_response)
        self.assertIsNone(session_id)
    
    def test_no_hardcoded_bypass(self):
        """Test that there's no hardcoded 'fuse_user' bypass"""
        # This test ensures the hardcoded "fuse_user" vulnerability is fixed
        
        # Even if someone tries to use "fuse_user" as agent_id, they need valid HMAC
        challenge = "test_challenge"
        invalid_response = "invalid_response"
        
        # Should fail without valid HMAC
        session_id = self.auth_manager.authenticate_agent("fuse_user", challenge, invalid_response)
        self.assertIsNone(session_id)
        
        # Should only work with proper HMAC
        valid_response = hmac.new(
            self.auth_secret.encode('utf-8'),
            f"fuse_user:{challenge}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        session_id = self.auth_manager.authenticate_agent("fuse_user", challenge, valid_response)
        self.assertIsNotNone(session_id)
    
    def test_session_management(self):
        """Test session creation and management"""
        agent_id = "test_agent_789"
        challenge = "auth_challenge_789"
        
        # Generate valid response
        response = hmac.new(
            self.auth_secret.encode('utf-8'),
            f"{agent_id}:{challenge}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Create session
        session_id = self.auth_manager.authenticate_agent(agent_id, challenge, response)
        self.assertIsNotNone(session_id)
        
        # Verify session info
        session_info = self.auth_manager.get_session_info(session_id)
        self.assertIsNotNone(session_info)
        self.assertEqual(session_info['agent_id'], agent_id)
        
        # Logout session
        success = self.auth_manager.logout_session(session_id)
        self.assertTrue(success)
        
        # Verify session is gone
        session_info = self.auth_manager.get_session_info(session_id)
        self.assertIsNone(session_info)

def run_authentication_fix_tests():
    """Run all authentication fix tests"""
    print("🔒 Testing FUSE Authentication Bypass Fix...")
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestFUSEAuthenticationFix))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Report results
    if result.wasSuccessful():
        print("✅ All authentication bypass fix tests passed!")
        print(f"   - {result.testsRun} tests executed")
        print("   - FUSE authentication bypass vulnerability FIXED ✅")
        print("   - No hardcoded 'fuse_user' bypass remaining")
        print("   - Proper HMAC authentication enforced")
        return True
    else:
        print("❌ Some authentication tests failed!")
        print(f"   - {len(result.failures)} failures")
        print(f"   - {len(result.errors)} errors")
        return False

if __name__ == "__main__":
    success = run_authentication_fix_tests()
    sys.exit(0 if success else 1)