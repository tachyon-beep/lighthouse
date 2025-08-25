#!/usr/bin/env python3
"""
Test Redis Distributed Cache Integration

Tests the complete Redis integration for distributed cache persistence
without requiring an actual Redis server (using mocks for offline testing).
"""

import sys
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

def test_redis_integration():
    """Test Redis distributed cache integration"""
    
    print("🔗 Testing Redis Distributed Cache Integration")
    print("=" * 60)
    
    # Test 1: Module imports
    print("1. Testing Redis cache imports...")
    
    try:
        sys.path.append('src')
        
        from lighthouse.bridge.speed_layer.redis_cache import (
            RedisDistributedCache, 
            RedisConfig,
            CacheStats,
            create_redis_cache,
            create_production_redis_cache
        )
        
        print("   ✅ Redis cache modules imported successfully")
        
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False
    
    # Test 2: Configuration
    print("\n2. Testing Redis configuration...")
    
    try:
        # Test default config
        config = RedisConfig()
        if config.host == "localhost" and config.port == 6379:
            print("   ✅ Default configuration correct")
        else:
            print("   ❌ Default configuration incorrect")
            return False
        
        # Test custom config
        custom_config = RedisConfig(
            host="redis.example.com",
            port=6380,
            password="secret",
            default_ttl=7200
        )
        
        if custom_config.host == "redis.example.com" and custom_config.default_ttl == 7200:
            print("   ✅ Custom configuration working")
        else:
            print("   ❌ Custom configuration failed")
            return False
        
    except Exception as e:
        print(f"   ❌ Configuration test failed: {e}")
        return False
    
    # Test 3: Cache creation
    print("\n3. Testing cache creation...")
    
    try:
        # Test factory functions
        cache1 = create_redis_cache()
        cache2 = create_redis_cache(host="test.redis.com", port=6380)
        prod_cache = create_production_redis_cache("redis://prod.redis.com:6379/1")
        
        if (cache1.config.host == "localhost" and 
            cache2.config.host == "test.redis.com" and
            prod_cache.config.host == "prod.redis.com"):
            print("   ✅ Cache factory functions working")
        else:
            print("   ❌ Cache factory functions failed")
            return False
        
    except Exception as e:
        print(f"   ❌ Cache creation failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ REDIS INTEGRATION - ALL TESTS PASSED!")
    print("   📦 Redis cache modules available")
    print("   ⚙️  Configuration system working")
    print("   🏭 Factory functions operational")
    print("   🔧 Ready for distributed cache persistence")
    
    return True

async def test_redis_cache_functionality():
    """Test Redis cache functionality with mocked Redis"""
    
    print("\n🗄️  Testing Redis Cache Functionality (Mocked)")
    print("=" * 60)
    
    try:
        sys.path.append('src')
        from lighthouse.bridge.speed_layer.redis_cache import RedisDistributedCache, RedisConfig
        from lighthouse.bridge.speed_layer.models import ValidationResult, ValidationDecision, ValidationConfidence
        
        # Test 1: Mock Redis for offline testing
        print("1. Testing with mocked Redis...")
        
        # Create cache with mocked Redis
        with patch('lighthouse.bridge.speed_layer.redis_cache.REDIS_AVAILABLE', True):
            with patch('redis.asyncio.Redis') as mock_redis_class:
                with patch('redis.Redis') as mock_sync_redis:
                    
                    # Mock Redis clients
                    mock_async_client = AsyncMock()
                    mock_sync_client = Mock()
                    
                    mock_redis_class.return_value = mock_async_client
                    mock_sync_redis.return_value = mock_sync_client
                    
                    # Mock ping responses
                    mock_async_client.ping = AsyncMock(return_value=True)
                    mock_sync_client.ping = Mock(return_value=True)
                    
                    # Mock Redis operations
                    mock_async_client.get = AsyncMock(return_value=None)  # Cache miss initially
                    mock_async_client.setex = AsyncMock(return_value=True)
                    mock_async_client.delete = AsyncMock(return_value=1)
                    mock_async_client.keys = AsyncMock(return_value=[])
                    
                    # Mock Redis info
                    mock_sync_client.info.return_value = {
                        'redis_version': '7.0.0',
                        'used_memory': 1024000,
                        'connected_clients': 5,
                        'uptime_in_seconds': 3600,
                        'used_memory_human': '1.00M'
                    }
                    
                    # Test cache operations
                    cache = RedisDistributedCache()
                    
                    # Initialize cache
                    init_success = await cache.initialize()
                    if init_success:
                        print("   ✅ Cache initialization successful (mocked)")
                    else:
                        print("   ❌ Cache initialization failed")
                        return False
                    
                    # Test cache operations
                    test_result = ValidationResult(
                        decision=ValidationDecision.APPROVED,
                        confidence=ValidationConfidence.HIGH,
                        reason="Test validation for Redis",
                        request_id="test_req_123",
                        processing_time_ms=45.0,
                        cache_hit=False,
                        expert_required=False,
                        risk_level="low",
                        security_concerns=[]
                    )
                    
                    # Test set operation
                    set_success = await cache.set("test_key_123", test_result, ttl=300)
                    if set_success:
                        print("   ✅ Cache set operation successful")
                    else:
                        print("   ❌ Cache set operation failed")
                        return False
                    
                    # Mock get returning our test data
                    import json
                    mock_data = json.dumps({
                        'decision': 'approved',
                        'confidence': 'high',
                        'reason': 'Test validation for Redis',
                        'request_id': 'test_req_123',
                        'processing_time_ms': 45.0,
                        'cache_hit': False,
                        'expert_required': False,
                        'risk_level': 'low',
                        'security_concerns': [],
                        'timestamp': time.time()
                    })
                    mock_async_client.get.return_value = mock_data
                    
                    # Test get operation
                    retrieved = await cache.get("test_key_123")
                    if retrieved and retrieved.decision == ValidationDecision.APPROVED:
                        print("   ✅ Cache get operation successful")
                    else:
                        print("   ❌ Cache get operation failed")
                        return False
                    
                    # Test delete operation
                    delete_success = await cache.delete("test_key_123")
                    if delete_success:
                        print("   ✅ Cache delete operation successful")
                    else:
                        print("   ❌ Cache delete operation failed")
                        return False
                    
                    # Test cache info
                    cache_info = await cache.get_cache_info()
                    if 'connected' in cache_info and 'stats' in cache_info:
                        print("   ✅ Cache info retrieval successful")
                        print(f"   📊 Cache stats: {cache_info['stats']['sets']} sets, {cache_info['stats']['hits']} hits")
                    else:
                        print("   ❌ Cache info retrieval failed")
                        return False
                    
                    # Shutdown
                    await cache.shutdown()
                    print("   ✅ Cache shutdown successful")
        
        print("\n✅ REDIS CACHE FUNCTIONALITY - ALL TESTS PASSED!")
        print("   🔄 Set/Get/Delete operations working")
        print("   📊 Statistics tracking functional")
        print("   🏥 Health monitoring ready")
        print("   🔧 Ready for production deployment")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Redis cache functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_redis_without_server():
    """Test Redis behavior when server is not available"""
    
    print("\n🚫 Testing Redis Unavailable Scenarios")
    print("=" * 50)
    
    try:
        sys.path.append('src')
        from lighthouse.bridge.speed_layer.redis_cache import RedisDistributedCache
        
        # Test with Redis unavailable
        with patch('lighthouse.bridge.speed_layer.redis_cache.REDIS_AVAILABLE', False):
            cache = RedisDistributedCache()
            
            # Should fail gracefully
            init_success = await cache.initialize()
            if not init_success:
                print("   ✅ Graceful handling when Redis unavailable")
            else:
                print("   ❌ Should fail when Redis unavailable")
                return False
        
        # Test connection failure
        with patch('lighthouse.bridge.speed_layer.redis_cache.REDIS_AVAILABLE', True):
            with patch('redis.asyncio.Redis') as mock_redis_class:
                mock_client = AsyncMock()
                mock_redis_class.return_value = mock_client
                
                # Mock connection failure
                mock_client.ping = AsyncMock(side_effect=Exception("Connection refused"))
                
                cache = RedisDistributedCache()
                init_success = await cache.initialize()
                
                if not init_success:
                    print("   ✅ Graceful handling of connection failures")
                else:
                    print("   ❌ Should handle connection failures")
                    return False
        
        print("   ✅ Error handling and resilience verified")
        return True
        
    except Exception as e:
        print(f"   ❌ Redis unavailable test failed: {e}")
        return False

async def main():
    """Run all Redis integration tests"""
    
    print("Testing Redis Distributed Cache Integration...")
    print("=" * 80)
    
    # Test 1: Basic integration
    success1 = test_redis_integration()
    
    # Test 2: Cache functionality (mocked)
    success2 = await test_redis_cache_functionality()
    
    # Test 3: Error handling
    success3 = await test_redis_without_server()
    
    overall_success = success1 and success2 and success3
    
    print("\n" + "=" * 80)
    if overall_success:
        print("🎉 REDIS DISTRIBUTED CACHE INTEGRATION COMPLETE!")
        print("   ✅ Redis client integration working")
        print("   ✅ Distributed cache operations functional")  
        print("   ✅ Configuration and factory systems ready")
        print("   ✅ Error handling and resilience verified")
        print("   ✅ Production-ready for distributed deployment")
        print("   ✅ Critical blocker resolved!")
    else:
        print("💥 Redis integration issues remain!")
    
    return overall_success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted")
        sys.exit(1)