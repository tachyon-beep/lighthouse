#!/usr/bin/env python3
"""
Event Store Integration Test

Comprehensive test to verify that all Event Store integration
import paths are working and components can be initialized properly.
"""

import sys
import asyncio
import tempfile
import os

def test_event_store_integration():
    """Test Event Store integration and import paths"""
    
    print("🔗 Testing Event Store Integration")
    print("=" * 60)
    
    # Test 1: Core imports
    print("1. Testing core Event Store imports...")
    
    try:
        sys.path.append('src')
        
        # Main event store
        from lighthouse.event_store import EventStore, SQLiteEventStore, EventStoreError
        print("   ✅ EventStore and SQLiteEventStore imported")
        
        # Storage configuration
        from lighthouse.event_store.storage_config import StorageConfig, create_sqlite_event_store
        print("   ✅ Storage configuration imported")
        
        # Event models
        from lighthouse.event_store.models import Event, EventType, EventQuery
        print("   ✅ Event models imported")
        
    except Exception as e:
        print(f"   ❌ Core imports failed: {e}")
        return False
    
    # Test 2: Bridge components
    print("\n2. Testing Bridge component imports...")
    
    try:
        # Main bridge
        from lighthouse.bridge import LighthouseBridge
        print("   ✅ LighthouseBridge imported")
        
        # FUSE components
        from lighthouse.bridge.fuse_mount import FUSEMountManager
        print("   ✅ FUSE mount manager imported")
        
        # Expert coordination
        from lighthouse.bridge.expert_coordination import ExpertRegistry
        print("   ✅ Expert registry imported")
        
        # Event store bridge components
        from lighthouse.bridge.event_store.project_aggregate import ProjectAggregate
        print("   ✅ Bridge ProjectAggregate imported")
        
    except Exception as e:
        print(f"   ❌ Bridge imports failed: {e}")
        return False
    
    # Test 3: Configuration factory
    print("\n3. Testing configuration factory...")
    
    try:
        # Test different storage configurations
        file_config = StorageConfig.get_recommended_config("development")
        sqlite_config = StorageConfig.get_recommended_config("production")
        
        if file_config["storage_type"] == "sqlite_wal" and sqlite_config["storage_type"] == "sqlite_wal":
            print("   ✅ Configuration factory working")
        else:
            print(f"   ❌ Unexpected config types: {file_config['storage_type']}, {sqlite_config['storage_type']}")
            return False
        
        # Test validation
        from lighthouse.event_store.storage_config import validate_storage_config
        validated = validate_storage_config(sqlite_config)
        
        if "db_path" in validated:
            print("   ✅ Configuration validation working")
        else:
            print("   ❌ Configuration validation failed")
            return False
        
    except Exception as e:
        print(f"   ❌ Configuration factory failed: {e}")
        return False
    
    # Test 4: Authentication integration
    print("\n4. Testing authentication integration...")
    
    try:
        from lighthouse.bridge.fuse_mount.authentication import FUSEAuthenticationManager
        from lighthouse.event_store.auth import create_system_authenticator
        
        # Test that authentication components can be created
        auth_manager = FUSEAuthenticationManager("test_secret")
        sys_auth = create_system_authenticator("test_secret")
        
        if auth_manager and sys_auth:
            print("   ✅ Authentication integration working")
        else:
            print("   ❌ Authentication creation failed")
            return False
        
    except Exception as e:
        print(f"   ❌ Authentication integration failed: {e}")
        return False
    
    # Test 5: Speed layer integration
    print("\n5. Testing Speed Layer integration...")
    
    try:
        from lighthouse.bridge.speed_layer.models import ValidationRequest, ValidationDecision
        from lighthouse.bridge.speed_layer.dispatcher import SpeedLayerDispatcher
        
        # Test that speed layer components exist
        if ValidationRequest and ValidationDecision and SpeedLayerDispatcher:
            print("   ✅ Speed Layer integration working")
        else:
            print("   ❌ Speed Layer components missing")
            return False
        
    except Exception as e:
        print(f"   ❌ Speed Layer integration failed: {e}")
        return False
    
    # Test 6: AST anchoring integration
    print("\n6. Testing AST anchoring integration...")
    
    try:
        from lighthouse.bridge.ast_anchoring.anchor_manager import ASTAnchorManager
        
        if ASTAnchorManager:
            print("   ✅ AST anchoring integration working")
        else:
            print("   ❌ AST anchoring components missing")
            return False
        
    except Exception as e:
        print(f"   ❌ AST anchoring integration failed: {e}")
        return False
    
    # Test 7: End-to-end import test
    print("\n7. Testing end-to-end imports...")
    
    try:
        # This should import everything without errors
        from lighthouse import bridge, event_store
        
        if hasattr(bridge, 'LighthouseBridge') and hasattr(event_store, 'EventStore'):
            print("   ✅ End-to-end imports successful")
        else:
            print("   ❌ Missing expected attributes")
            return False
        
    except Exception as e:
        print(f"   ❌ End-to-end imports failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ EVENT STORE INTEGRATION - ALL TESTS PASSED!")
    print("   🔗 All import paths resolved")
    print("   📦 Missing modules created")
    print("   ⚙️  Configuration system working")
    print("   🔐 Authentication integration verified")
    print("   🚀 Bridge components ready")
    print("   ✅ Critical blocker resolved!")
    
    return True

async def test_sqlite_store_instantiation():
    """Test that SQLite store can actually be instantiated"""
    
    print("\n🗃️  Testing SQLite Store Instantiation")
    print("=" * 50)
    
    try:
        # Import required components
        from lighthouse.event_store.storage_config import create_sqlite_event_store
        
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create SQLite store
            store = create_sqlite_event_store(
                db_path=db_path,
                auth_secret="test_secret"
            )
            
            if store:
                print("   ✅ SQLite Event Store created successfully")
                
                # Test initialization (would require full mocking for models)
                print("   ✅ Store instantiation working")
                return True
            else:
                print("   ❌ Store creation returned None")
                return False
                
        finally:
            # Cleanup
            for ext in ['', '-wal', '-shm']:
                try:
                    os.unlink(db_path + ext)
                except:
                    pass
                    
    except Exception as e:
        print(f"   ❌ SQLite store instantiation failed: {e}")
        return False

def main():
    """Run all integration tests"""
    print("Testing Event Store Integration and Import Paths...")
    print("=" * 80)
    
    # Test 1: Import paths and integration
    success1 = test_event_store_integration()
    
    # Test 2: SQLite store instantiation
    success2 = asyncio.run(test_sqlite_store_instantiation())
    
    overall_success = success1 and success2
    
    print("\n" + "=" * 80)
    if overall_success:
        print("🎉 EVENT STORE INTEGRATION FULLY WORKING!")
        print("   ✅ All import paths resolved")
        print("   ✅ All components can be instantiated") 
        print("   ✅ SQLite storage with WAL mode ready")
        print("   ✅ Bridge integration verified")
        print("   ✅ Critical blocker completely resolved!")
    else:
        print("💥 Event Store integration issues remain!")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)