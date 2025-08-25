#!/usr/bin/env python3
"""
Direct test of FUSE authentication module without complex dependencies
"""

import sys
import os
import unittest
import hashlib
import hmac
from unittest.mock import Mock
from dataclasses import dataclass
from typing import Dict, Optional, Set, List
from datetime import datetime, timedelta

# Direct import without going through bridge init
sys.path.append('src')

# Mock the modules that authentication.py needs
class MockEvent:
    pass

class MockEventFilter:
    pass

class MockEventType:
    pass

# Set up module mocks before importing
sys.modules['lighthouse.event_store.models'] = type(sys)('module')
sys.modules['lighthouse.event_store.models'].Event = MockEvent
sys.modules['lighthouse.event_store.models'].EventFilter = MockEventFilter
sys.modules['lighthouse.event_store.models'].EventType = MockEventType

# Now import the authentication module directly
from lighthouse.bridge.fuse_mount.authentication import (
    FUSEAuthenticationManager,
    FUSEAuthenticationContext,
    AgentSession,
    FileSystemPermission
)

class TestFUSEAuthFix(unittest.TestCase):
    def setUp(self):
        self.auth_secret = "test_secret_key"
        self.auth_manager = FUSEAuthenticationManager(self.auth_secret)
    
    def test_no_hardcoded_bypass(self):
        """Test that hardcoded 'fuse_user' bypass is removed"""
        print("Testing hardcoded bypass removal...")
        
        # Try invalid authentication - should fail even with 'fuse_user'
        session_id = self.auth_manager.authenticate_agent(
            "fuse_user", "challenge", "invalid_response"
        )
        self.assertIsNone(session_id)
        
        # Valid authentication should work
        response = hmac.new(
            self.auth_secret.encode('utf-8'),
            f"fuse_user:challenge".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        session_id = self.auth_manager.authenticate_agent("fuse_user", "challenge", response)
        self.assertIsNotNone(session_id)
    
    def test_hmac_authentication(self):
        """Test HMAC-based authentication works"""
        print("Testing HMAC authentication...")
        
        agent_id = "test_agent"
        challenge = "test_challenge"
        
        # Generate valid response
        response = hmac.new(
            self.auth_secret.encode('utf-8'),
            f"{agent_id}:{challenge}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Should authenticate successfully
        session_id = self.auth_manager.authenticate_agent(agent_id, challenge, response)
        self.assertIsNotNone(session_id)
        
        # Invalid response should fail
        session_id2 = self.auth_manager.authenticate_agent(agent_id, challenge, "wrong")
        self.assertIsNone(session_id2)
    
    def test_access_control(self):
        """Test access control based on authentication"""
        print("Testing access control...")
        
        context = FUSEAuthenticationContext(self.auth_manager)
        
        # No session = no access
        self.assertFalse(context.check_access("/current/test.py", "read"))
        
        # Create valid session
        agent_id = "test_agent"
        challenge = "challenge"
        response = hmac.new(
            self.auth_secret.encode('utf-8'),
            f"{agent_id}:{challenge}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        session_id = self.auth_manager.authenticate_agent(agent_id, challenge, response)
        context.set_session(session_id)
        
        # Now should have access
        self.assertTrue(context.check_access("/current/test.py", "read"))
        self.assertEqual(context.get_current_agent(), agent_id)

def main():
    print("🔒 Testing FUSE Authentication Bypass Fix...")
    print("=" * 60)
    
    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFUSEAuthFix)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ FUSE Authentication Bypass FIXED!")
        print("   ✓ No hardcoded 'fuse_user' bypass")
        print("   ✓ HMAC authentication enforced")
        print("   ✓ Proper access control in place")
        print("   ✓ Critical security vulnerability resolved")
    else:
        print("❌ Authentication tests failed!")
        for failure in result.failures:
            print(f"   FAIL: {failure[0]}")
        for error in result.errors:
            print(f"   ERROR: {error[0]}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)