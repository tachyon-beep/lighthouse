#!/usr/bin/env python3
"""
Test script for Expert LLM Client Integration

Tests the Expert LLM client integration with mock services and
validates all functionality for querying expert LLM services.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lighthouse.bridge.llm_integration.expert_llm_client import (
    ExpertLLMClient,
    ExpertType,
    QueryPriority,
    QueryStatus,
    ExpertQuery,
    ExpertResponse,
    ExpertConfig,
    AnthropicExpertProvider,
    OpenAIExpertProvider,
    get_expert_llm_client,
    query_security_expert
)


class MockHTTPResponse:
    """Mock HTTP response for testing."""
    
    def __init__(self, status: int, json_data: dict):
        self.status = status
        self._json_data = json_data
    
    async def json(self):
        return self._json_data
    
    async def text(self):
        return json.dumps(self._json_data)


async def test_expert_config():
    """Test expert configuration."""
    print("🔍 Testing Expert Configuration...")
    
    passed = 0
    failed = 0
    
    # Test creating expert config
    config = ExpertConfig(
        expert_type=ExpertType.SECURITY_ANALYST,
        endpoint_url="https://api.anthropic.com/v1/messages",
        api_key="test-key",
        model_name="claude-3-sonnet",
        max_tokens=2048,
        temperature=0.1,
        timeout_seconds=30,
        retry_attempts=3,
        rate_limit_per_minute=60,
        system_prompt="You are a security expert."
    )
    
    if config.expert_type == ExpertType.SECURITY_ANALYST:
        print("✓ Expert config creation")
        passed += 1
    else:
        print("✗ Expert config creation failed")
        failed += 1
    
    # Test config serialization
    config_dict = config.to_dict()
    if "security_analyst" in config_dict['expert_type']:
        print("✓ Config serialization")
        passed += 1
    else:
        print("✗ Config serialization failed")
        failed += 1
    
    print(f"Expert Configuration: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_expert_query_creation():
    """Test expert query creation."""
    print("🔍 Testing Expert Query Creation...")
    
    passed = 0
    failed = 0
    
    from datetime import datetime
    
    query = ExpertQuery(
        query_id="test-123",
        expert_type=ExpertType.CODE_REVIEWER,
        query_text="Review this code for issues",
        context={"code": "print('hello')", "language": "python"},
        priority=QueryPriority.HIGH,
        timeout_seconds=30,
        created_at=datetime.utcnow()
    )
    
    # Test query properties
    if query.query_id == "test-123":
        print("✓ Query ID assignment")
        passed += 1
    else:
        print("✗ Query ID assignment failed")
        failed += 1
    
    if query.expert_type == ExpertType.CODE_REVIEWER:
        print("✓ Expert type assignment")
        passed += 1
    else:
        print("✗ Expert type assignment failed")
        failed += 1
    
    if query.priority == QueryPriority.HIGH:
        print("✓ Priority assignment")
        passed += 1
    else:
        print("✗ Priority assignment failed")
        failed += 1
    
    # Test query serialization
    query_dict = query.to_dict()
    if query_dict['expert_type'] == 'code_reviewer':
        print("✓ Query serialization")
        passed += 1
    else:
        print("✗ Query serialization failed")
        failed += 1
    
    print(f"Expert Query Creation: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_anthropic_provider():
    """Test Anthropic expert provider with mocked responses."""
    print("🔍 Testing Anthropic Expert Provider...")
    
    passed = 0
    failed = 0
    
    provider = AnthropicExpertProvider()
    
    config = ExpertConfig(
        expert_type=ExpertType.SECURITY_ANALYST,
        endpoint_url="https://api.anthropic.com/v1/messages",
        api_key="test-key",
        model_name="claude-3-sonnet",
        max_tokens=1000,
        temperature=0.1,
        timeout_seconds=30,
        retry_attempts=3,
        rate_limit_per_minute=60,
        system_prompt="You are a security expert."
    )
    
    query = ExpertQuery(
        query_id="test-anthropic",
        expert_type=ExpertType.SECURITY_ANALYST,
        query_text="Analyze this for security issues",
        context={"code": "print('test')"},
        priority=QueryPriority.NORMAL,
        timeout_seconds=30,
        created_at=__import__('datetime').datetime.utcnow()
    )
    
    # Mock successful response
    mock_response = MockHTTPResponse(200, {
        "content": [{
            "text": '{"analysis": "No security issues found", "confidence": 0.9, "reasoning": "Simple print statement", "recommendations": []}'
        }],
        "model": "claude-3-sonnet",
        "usage": {"input_tokens": 100, "output_tokens": 50}
    })
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response
        
        try:
            response = await provider.query_expert(query, config)
            
            if response.query_id == "test-anthropic":
                print("✓ Query ID preserved")
                passed += 1
            else:
                print("✗ Query ID not preserved")
                failed += 1
            
            if response.confidence == 0.9:
                print("✓ Confidence parsing")
                passed += 1
            else:
                print("✗ Confidence parsing failed")
                failed += 1
            
            if "No security issues" in response.response_text:
                print("✓ Response text parsing")
                passed += 1
            else:
                print("✗ Response text parsing failed")
                failed += 1
            
        except Exception as e:
            print(f"✗ Anthropic provider test failed: {str(e)}")
            failed += 3
    
    await provider.close()
    
    print(f"Anthropic Provider: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_expert_client():
    """Test Expert LLM client."""
    print("🔍 Testing Expert LLM Client...")
    
    passed = 0
    failed = 0
    
    client = ExpertLLMClient()
    
    # Test expert types
    expert_types = client.get_expert_types()
    if ExpertType.SECURITY_ANALYST in expert_types:
        print("✓ Security analyst configured")
        passed += 1
    else:
        print("✗ Security analyst not configured")
        failed += 1
    
    if ExpertType.CODE_REVIEWER in expert_types:
        print("✓ Code reviewer configured")
        passed += 1
    else:
        print("✗ Code reviewer not configured")
        failed += 1
    
    # Test configuration retrieval
    security_config = client.get_expert_config(ExpertType.SECURITY_ANALYST)
    if security_config and security_config.expert_type == ExpertType.SECURITY_ANALYST:
        print("✓ Config retrieval")
        passed += 1
    else:
        print("✗ Config retrieval failed")
        failed += 1
    
    # Test query creation (without actual API call)
    try:
        query_id = client._select_provider(security_config)
        if query_id in ["anthropic", "openai"]:
            print("✓ Provider selection")
            passed += 1
        else:
            print("✗ Provider selection failed")
            failed += 1
    except Exception as e:
        print(f"✗ Provider selection failed: {str(e)}")
        failed += 1
    
    await client.close()
    
    print(f"Expert Client: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_convenience_functions():
    """Test convenience functions."""
    print("🔍 Testing Convenience Functions...")
    
    passed = 0
    failed = 0
    
    # Test global client
    client = get_expert_llm_client()
    if isinstance(client, ExpertLLMClient):
        print("✓ Global client creation")
        passed += 1
    else:
        print("✗ Global client creation failed")
        failed += 1
    
    # Test singleton behavior
    client2 = get_expert_llm_client()
    if client is client2:
        print("✓ Singleton pattern")
        passed += 1
    else:
        print("✗ Singleton pattern failed")
        failed += 1
    
    await client.close()
    
    print(f"Convenience Functions: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_error_handling():
    """Test error handling."""
    print("🔍 Testing Error Handling...")
    
    passed = 0
    failed = 0
    
    client = ExpertLLMClient()
    
    # Test querying non-existent expert type
    try:
        # Create a custom expert type that doesn't exist
        class FakeExpertType:
            value = "fake_expert"
        
        fake_expert = FakeExpertType()
        fake_expert.__class__.__bases__ = (object,)
        
        # This should not be in the configs
        if fake_expert.value not in [e.value for e in client.get_expert_types()]:
            print("✓ Non-existent expert type not in configs")
            passed += 1
        else:
            print("✗ Non-existent expert type found in configs")
            failed += 1
    except Exception as e:
        print(f"✗ Error handling test failed: {str(e)}")
        failed += 1
    
    # Test timeout behavior (simulated)
    provider = AnthropicExpertProvider()
    short_config = ExpertConfig(
        expert_type=ExpertType.SECURITY_ANALYST,
        endpoint_url="https://api.anthropic.com/v1/messages",
        api_key="test-key",
        model_name="claude-3-sonnet",
        max_tokens=1000,
        temperature=0.1,
        timeout_seconds=1,  # Very short timeout
        retry_attempts=1,
        rate_limit_per_minute=60,
        system_prompt="Test"
    )
    
    # Mock timeout response
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_post.side_effect = asyncio.TimeoutError()
        
        try:
            query = ExpertQuery(
                query_id="timeout-test",
                expert_type=ExpertType.SECURITY_ANALYST,
                query_text="Test timeout",
                context={},
                priority=QueryPriority.NORMAL,
                timeout_seconds=1,
                created_at=__import__('datetime').datetime.utcnow()
            )
            
            await provider.query_expert(query, short_config)
            print("✗ Timeout should have been raised")
            failed += 1
        except Exception as e:
            if "timeout" in str(e).lower():
                print("✓ Timeout handling")
                passed += 1
            else:
                print(f"✗ Unexpected error: {str(e)}")
                failed += 1
    
    await provider.close()
    await client.close()
    
    print(f"Error Handling: {passed} passed, {failed} failed\n")
    return passed, failed


async def test_performance():
    """Test client performance characteristics."""
    print("🔍 Testing Performance...")
    
    passed = 0
    failed = 0
    
    client = ExpertLLMClient()
    
    # Test configuration loading speed
    import time
    start_time = time.time()
    client._load_default_configs()
    config_time = (time.time() - start_time) * 1000
    
    if config_time < 100:  # Should be very fast
        print(f"✓ Config loading speed: {config_time:.2f}ms")
        passed += 1
    else:
        print(f"✗ Config loading too slow: {config_time:.2f}ms")
        failed += 1
    
    # Test memory usage (basic check)
    initial_expert_count = len(client.get_expert_types())
    if initial_expert_count >= 3:  # Should have at least security, code, arch experts
        print(f"✓ Expert configuration count: {initial_expert_count}")
        passed += 1
    else:
        print(f"✗ Insufficient expert configurations: {initial_expert_count}")
        failed += 1
    
    await client.close()
    
    print(f"Performance: {passed} passed, {failed} failed\n")
    return passed, failed


async def main():
    """Run all tests."""
    print("🚀 Starting Expert LLM Client Integration Tests\n")
    
    total_passed = 0
    total_failed = 0
    
    # Run all test suites
    test_suites = [
        test_expert_config,
        test_expert_query_creation,
        test_anthropic_provider,
        test_expert_client,
        test_convenience_functions,
        test_error_handling,
        test_performance,
    ]
    
    for test_suite in test_suites:
        passed, failed = await test_suite()
        total_passed += passed
        total_failed += failed
    
    # Print final results
    print("="*70)
    print("EXPERT LLM CLIENT TEST RESULTS")
    print("="*70)
    print(f"Total Tests: {total_passed + total_failed}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if total_failed == 0:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"❌ {total_failed} tests failed")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)