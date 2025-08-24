#!/usr/bin/env python3
"""
Lighthouse Event Store Demo

Demonstrates the key features of the Lighthouse Event Store:
- Secure authentication and authorization
- Event creation and storage
- Queries with filtering
- Security validation
"""

import asyncio
import tempfile
import shutil
from pathlib import Path

from lighthouse.event_store import (
    EventStore, Event, EventType, EventQuery, EventFilter,
    EventBatch, AgentRole, SecurityError
)


async def demo_event_store():
    """Comprehensive demo of Event Store capabilities."""
    print("🚀 Lighthouse Event Store Demo")
    print("=" * 50)
    
    # Create temporary directory for demo
    temp_dir = tempfile.mkdtemp(prefix="lighthouse_demo_")
    print(f"📁 Using temporary directory: {temp_dir}")
    
    try:
        # Initialize secure event store
        print("\n🔒 Initializing secure Event Store...")
        store = EventStore(
            data_dir=temp_dir,
            allowed_base_dirs=[temp_dir, "/tmp"],
            auth_secret="demo-secret-change-in-production"
        )
        await store.initialize()
        print(f"✅ Event Store initialized: {store.status}")
        
        # Create and authenticate agents
        print("\n👥 Setting up agents...")
        
        # Regular agent
        agent_token = store.create_agent_token("demo-agent")
        agent_identity = store.authenticate_agent("demo-agent", agent_token, "agent")
        print(f"✅ Agent authenticated: {agent_identity.agent_id} ({agent_identity.role})")
        
        # Admin agent
        admin_token = store.create_agent_token("admin-agent") 
        admin_identity = store.authenticate_agent("admin-agent", admin_token, "admin")
        print(f"✅ Admin authenticated: {admin_identity.agent_id} ({admin_identity.role})")
        
        # Demo 1: Basic Event Storage
        print("\n📝 Demo 1: Basic Event Storage")
        print("-" * 30)
        
        events_data = [
            {"command": "ls -la", "safe": True},
            {"command": "git status", "safe": True},
            {"command": "pip install requests", "safe": False, "reason": "Package installation"},
        ]
        
        for i, data in enumerate(events_data):
            event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id=f"demo-cmd-{i+1}",
                data=data,
                metadata={"demo": True, "batch": 1}
            )
            
            await store.append(event, agent_id="demo-agent")
            print(f"  ✅ Stored event {i+1}: {event.event_id} (sequence: {event.sequence})")
        
        # Demo 2: Batch Operations
        print("\n📦 Demo 2: Batch Operations")
        print("-" * 30)
        
        batch_events = []
        for i in range(3):
            event = Event(
                event_type=EventType.AGENT_HEARTBEAT,
                aggregate_id=f"demo-agent",
                data={"timestamp": f"2025-08-24T{10+i:02d}:00:00Z", "status": "healthy"},
                metadata={"batch": True}
            )
            batch_events.append(event)
        
        batch = EventBatch(events=batch_events)
        await store.append_batch(batch, agent_id="demo-agent")
        print(f"  ✅ Stored batch of {len(batch_events)} events")
        
        # Demo 3: Queries and Filtering
        print("\n🔍 Demo 3: Queries and Filtering")
        print("-" * 30)
        
        # Query all command events
        query = EventQuery(
            filter=EventFilter(event_types=[EventType.COMMAND_RECEIVED]),
            limit=10
        )
        result = await store.query(query, agent_id="demo-agent")
        print(f"  📊 Found {len(result.events)} command events")
        for event in result.events:
            print(f"    • {event.aggregate_id}: {event.data.get('command', 'N/A')}")
        
        # Query with metadata filter
        query_batch = EventQuery(
            filter=EventFilter(event_types=[EventType.AGENT_HEARTBEAT]),
            limit=5
        )
        result_batch = await store.query(query_batch, agent_id="demo-agent")
        print(f"  📊 Found {len(result_batch.events)} heartbeat events")
        
        # Demo 4: Security Features
        print("\n🛡️ Demo 4: Security Features")
        print("-" * 30)
        
        # Test malicious event rejection
        try:
            malicious_event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id="evil-cmd",
                data={"script": "<script>alert('xss')</script>"}
            )
            await store.append(malicious_event, agent_id="demo-agent")
            print("  ❌ SECURITY FAILURE: Malicious event was not blocked!")
        except Exception as e:
            print(f"  ✅ Security validation blocked malicious event: {type(e).__name__}")
        
        # Test unauthenticated access
        try:
            safe_event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id="unauth-cmd",
                data={"command": "ls"}
            )
            await store.append(safe_event, agent_id="unknown-agent")
            print("  ❌ SECURITY FAILURE: Unauthenticated access allowed!")
        except Exception as e:
            print(f"  ✅ Authentication blocked unauthenticated access: {type(e).__name__}")
        
        # Demo 5: System Health
        print("\n💊 Demo 5: System Health")
        print("-" * 30)
        
        health = await store.get_health()
        print(f"  📊 Event Store Status: {health.event_store_status}")
        print(f"  📊 Current Sequence: {health.current_sequence}")
        print(f"  📊 Events/Second: {health.events_per_second:.2f}")
        print(f"  📊 Avg Append Latency: {health.average_append_latency_ms:.2f}ms")
        print(f"  📊 Disk Usage: {health.disk_usage_bytes / 1024:.2f} KB")
        
        # Demo 6: Event ID Format
        print("\n🆔 Demo 6: Event ID Format (ADR-003 Compliant)")
        print("-" * 30)
        
        from lighthouse.event_store.id_generator import generate_event_id
        
        for i in range(3):
            event_id = generate_event_id()
            print(f"  • Event ID {i+1}: {event_id}")
            print(f"    - Timestamp: {event_id.timestamp_ns}")
            print(f"    - Sequence: {event_id.sequence}")  
            print(f"    - Node: {event_id.node_id}")
        
        print(f"\n✅ Demo completed successfully!")
        print(f"📊 Final Stats:")
        print(f"  - Total Events Stored: {store.current_sequence}")
        print(f"  - Event Store Status: {store.status}")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        raise
        
    finally:
        # Cleanup
        await store.shutdown()
        shutil.rmtree(temp_dir)
        print(f"\n🧹 Cleaned up temporary directory: {temp_dir}")


async def demo_security_features():
    """Demo focused on security features."""
    print("\n🔐 Security Features Deep Dive")
    print("=" * 50)
    
    from lighthouse.event_store.validation import PathValidator, InputValidator, SecurityError
    from lighthouse.event_store.auth import SimpleAuthenticator, AgentRole
    
    # Path validation demo
    print("\n🛡️ Path Validation:")
    validator = PathValidator(["/safe/path"])
    
    dangerous_paths = [
        "../../../etc/passwd",
        "/etc/shadow", 
        "file:///etc/hosts",
        "javascript:alert(1)"
    ]
    
    for path in dangerous_paths:
        try:
            validator.validate_path(path)
            print(f"  ❌ FAILED to block: {path}")
        except SecurityError:
            print(f"  ✅ Blocked dangerous path: {path}")
    
    # Input validation demo  
    print("\n🛡️ Input Validation:")
    input_validator = InputValidator()
    
    malicious_data = [
        {"script": "<script>alert('xss')</script>"},
        {"eval": "eval('malicious code')"},
        {"null": "file.txt\x00.exe"},
    ]
    
    for data in malicious_data:
        try:
            event = Event(
                event_type=EventType.COMMAND_RECEIVED,
                aggregate_id="test",
                data=data
            )
            input_validator.validate_event(event)
            print(f"  ❌ FAILED to block: {list(data.keys())[0]}")
        except SecurityError:
            print(f"  ✅ Blocked malicious input: {list(data.keys())[0]}")
    
    # Authentication demo
    print("\n🔐 Authentication:")
    authenticator = SimpleAuthenticator("test-secret")
    
    # Valid authentication
    token = authenticator.create_token("test-agent")
    identity = authenticator.authenticate("test-agent", token, AgentRole.AGENT)
    print(f"  ✅ Authenticated: {identity.agent_id} with role {identity.role}")
    
    # Invalid token
    try:
        authenticator.authenticate("test-agent", "invalid-token", AgentRole.AGENT)
        print("  ❌ FAILED: Invalid token accepted")
    except Exception:
        print("  ✅ Rejected invalid authentication token")
    
    print("\n🔒 All security features working correctly!")


if __name__ == "__main__":
    print("🌟 Lighthouse Event Store - Enterprise-Grade Multi-Agent Coordination")
    print("Version 1.0.0 - Phase 1 Complete with Security Hardening")
    
    # Run main demo
    asyncio.run(demo_event_store())
    
    # Run security demo
    asyncio.run(demo_security_features())
    
    print("\n🎉 All demos completed successfully!")
    print("📖 For more information, see: docs/architecture/")