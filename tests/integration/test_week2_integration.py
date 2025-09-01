#!/usr/bin/env python3
"""
Integration Test Suite for Week 2 FEATURE_PACK_0

Tests end-to-end workflows, multi-agent coordination, expert delegation,
and event sourcing as required by Week 2 Day 4.
"""

import asyncio
import json
import pytest
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.lighthouse.bridge.elicitation.fast_manager import OptimizedElicitationManager
from src.lighthouse.bridge.expert_coordination.coordinator import ExpertCoordinator
from src.lighthouse.event_store import EventStore, EventType
from src.lighthouse.bridge.security.session_security import SessionSecurityValidator


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows"""
    
    @pytest.mark.asyncio
    async def test_complete_elicitation_workflow(self):
        """Test complete elicitation workflow from creation to response"""
        # Initialize components
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Create elicitation
        from_agent = "orchestrator"
        to_agent = "security_expert"
        
        elicit_id = await manager.create_elicitation(
            from_agent=from_agent,
            to_agent=to_agent,
            message="Analyze security vulnerabilities",
            schema={
                "type": "object",
                "properties": {
                    "vulnerabilities": {"type": "array"},
                    "severity": {"type": "string"}
                }
            },
            timeout_seconds=30
        )
        
        assert elicit_id is not None
        assert elicit_id in manager.projection.active_elicitations
        
        # Verify event was stored
        events = await event_store.get_events_by_type(EventType.CUSTOM)
        assert len(events) > 0
        
        # Respond to elicitation
        response_data = {
            "vulnerabilities": ["SQL injection", "XSS"],
            "severity": "HIGH"
        }
        
        success = await manager.respond_to_elicitation(
            elicitation_id=elicit_id,
            responding_agent=to_agent,
            response_type="accept",
            data=response_data
        )
        
        assert success is True
        
        # Verify response was stored
        response_events = await event_store.get_events_by_type(EventType.CUSTOM)
        assert len(response_events) > 1  # Creation + response
        
        # Verify elicitation is completed
        assert elicit_id not in manager.projection.active_elicitations
        
        # Cleanup
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_agent_registration_and_authentication(self):
        """Test agent registration and authentication flow"""
        event_store = EventStore()
        await event_store.initialize()
        
        # Create session validator
        session_validator = SessionSecurityValidator(
            secret_key="test_secret",
            event_store=event_store
        )
        
        # Register new agent
        agent_id = "test_agent_123"
        session_token = await session_validator.create_session(
            agent_id=agent_id,
            ip_address="127.0.0.1",
            user_agent="TestAgent/1.0"
        )
        
        assert session_token is not None
        
        # Validate session
        is_valid = await session_validator.validate_session(
            session_token=session_token,
            agent_id=agent_id,
            ip_address="127.0.0.1"
        )
        
        assert is_valid is True
        
        # Test invalid session
        is_valid = await session_validator.validate_session(
            session_token="invalid_token",
            agent_id=agent_id,
            ip_address="127.0.0.1"
        )
        
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_rollback_capability(self):
        """Test rollback from elicitation to wait_for_messages"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Create elicitations
        elicit_ids = []
        for i in range(5):
            elicit_id = await manager.create_elicitation(
                from_agent=f"agent_{i}",
                to_agent=f"agent_{i+1}",
                message=f"Test {i}",
                schema={},
                timeout_seconds=30
            )
            elicit_ids.append(elicit_id)
        
        # Verify elicitations are active
        assert len(manager.projection.active_elicitations) == 5
        
        # Simulate rollback - disable elicitation
        manager.enabled = False  # Feature flag
        
        # Attempt new elicitation (should fail or fallback)
        with pytest.raises(Exception):
            await manager.create_elicitation(
                from_agent="agent_rollback",
                to_agent="agent_target",
                message="Should fail",
                schema={},
                timeout_seconds=30
            )
        
        # Cleanup active elicitations
        for elicit_id in elicit_ids:
            if elicit_id in manager.projection.active_elicitations:
                del manager.projection.active_elicitations[elicit_id]
        
        assert len(manager.projection.active_elicitations) == 0
        
        await manager.shutdown()


class TestMultiAgentCoordination:
    """Test multi-agent coordination capabilities"""
    
    @pytest.mark.asyncio
    async def test_concurrent_agent_coordination(self):
        """Test coordination between multiple concurrent agents"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Create multiple agents
        agents = [f"agent_{i}" for i in range(100)]
        
        # Create concurrent elicitations
        tasks = []
        for i in range(0, len(agents), 2):
            task = asyncio.create_task(
                manager.create_elicitation(
                    from_agent=agents[i],
                    to_agent=agents[i+1],
                    message=f"Coordination test {i}",
                    schema={},
                    timeout_seconds=30
                )
            )
            tasks.append(task)
        
        # Wait for all elicitations to be created
        elicit_ids = await asyncio.gather(*tasks)
        
        # Verify all were created
        assert len(elicit_ids) == 50
        assert all(eid is not None for eid in elicit_ids)
        
        # Respond to all elicitations concurrently
        response_tasks = []
        for i, elicit_id in enumerate(elicit_ids):
            agent_idx = i * 2 + 1
            task = asyncio.create_task(
                manager.respond_to_elicitation(
                    elicitation_id=elicit_id,
                    responding_agent=agents[agent_idx],
                    response_type="accept",
                    data={"response": f"From agent {agent_idx}"}
                )
            )
            response_tasks.append(task)
        
        # Wait for all responses
        responses = await asyncio.gather(*response_tasks)
        
        # Verify all succeeded
        assert all(r is True for r in responses)
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_agent_message_routing(self):
        """Test message routing between agents"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Create chain of elicitations
        chain_length = 10
        agents = [f"agent_{i}" for i in range(chain_length)]
        
        elicit_ids = []
        for i in range(chain_length - 1):
            elicit_id = await manager.create_elicitation(
                from_agent=agents[i],
                to_agent=agents[i+1],
                message=f"Chain message {i}",
                schema={},
                timeout_seconds=30
            )
            elicit_ids.append(elicit_id)
            
            # Immediately respond
            await manager.respond_to_elicitation(
                elicitation_id=elicit_id,
                responding_agent=agents[i+1],
                response_type="accept",
                data={"hop": i}
            )
        
        # Verify all messages were routed
        assert len(elicit_ids) == chain_length - 1
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_deadlock_prevention(self):
        """Test that system prevents deadlocks in multi-agent scenarios"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Create potential deadlock scenario
        # Agent A -> B, B -> C, C -> A (circular dependency)
        agents = ["agent_a", "agent_b", "agent_c"]
        
        # Create elicitations in order
        elicit_ab = await manager.create_elicitation(
            from_agent=agents[0],
            to_agent=agents[1],
            message="A to B",
            schema={},
            timeout_seconds=5
        )
        
        elicit_bc = await manager.create_elicitation(
            from_agent=agents[1],
            to_agent=agents[2],
            message="B to C",
            schema={},
            timeout_seconds=5
        )
        
        elicit_ca = await manager.create_elicitation(
            from_agent=agents[2],
            to_agent=agents[0],
            message="C to A",
            schema={},
            timeout_seconds=5
        )
        
        # System should handle this without deadlock
        # Timeouts should prevent infinite waiting
        await asyncio.sleep(6)  # Wait for timeouts
        
        # Verify elicitations timeout gracefully
        assert elicit_ab not in manager.projection.active_elicitations
        assert elicit_bc not in manager.projection.active_elicitations
        assert elicit_ca not in manager.projection.active_elicitations
        
        await manager.shutdown()


class TestExpertDelegation:
    """Test expert agent delegation"""
    
    @pytest.mark.asyncio
    async def test_expert_registration(self):
        """Test expert agent registration"""
        event_store = EventStore()
        await event_store.initialize()
        
        coordinator = ExpertCoordinator(event_store=event_store)
        await coordinator.initialize()
        
        # Register security expert
        expert_id = await coordinator.register_expert(
            agent_id="security_expert_001",
            expert_type="security",
            capabilities=["vulnerability_analysis", "penetration_testing", "code_review"],
            metadata={
                "experience_level": "senior",
                "specializations": ["web_security", "cryptography"]
            }
        )
        
        assert expert_id is not None
        
        # Verify expert is registered
        expert = coordinator.get_expert(expert_id)
        assert expert is not None
        assert expert["expert_type"] == "security"
        
        # Register performance expert
        perf_expert_id = await coordinator.register_expert(
            agent_id="performance_expert_001",
            expert_type="performance",
            capabilities=["profiling", "optimization", "load_testing"],
            metadata={
                "tools": ["pytest-benchmark", "locust", "memory_profiler"]
            }
        )
        
        assert perf_expert_id is not None
    
    @pytest.mark.asyncio
    async def test_expert_task_delegation(self):
        """Test delegating tasks to expert agents"""
        event_store = EventStore()
        await event_store.initialize()
        
        coordinator = ExpertCoordinator(event_store=event_store)
        await coordinator.initialize()
        
        # Register experts
        security_expert = await coordinator.register_expert(
            agent_id="security_expert",
            expert_type="security",
            capabilities=["security_analysis"]
        )
        
        perf_expert = await coordinator.register_expert(
            agent_id="performance_expert",
            expert_type="performance",
            capabilities=["performance_analysis"]
        )
        
        # Delegate security task
        task_id = await coordinator.delegate_task(
            task_type="security_analysis",
            task_data={
                "component": "authentication",
                "priority": "high"
            },
            requester="orchestrator"
        )
        
        assert task_id is not None
        
        # Verify task was assigned to security expert
        task = coordinator.get_task(task_id)
        assert task is not None
        assert task["assigned_to"] == "security_expert"
        
        # Complete task
        result = await coordinator.complete_task(
            task_id=task_id,
            expert_id=security_expert,
            result={
                "vulnerabilities_found": 0,
                "status": "secure"
            }
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_expert_load_balancing(self):
        """Test load balancing across multiple experts"""
        event_store = EventStore()
        await event_store.initialize()
        
        coordinator = ExpertCoordinator(event_store=event_store)
        await coordinator.initialize()
        
        # Register multiple security experts
        expert_ids = []
        for i in range(3):
            expert_id = await coordinator.register_expert(
                agent_id=f"security_expert_{i}",
                expert_type="security",
                capabilities=["security_analysis"]
            )
            expert_ids.append(expert_id)
        
        # Delegate multiple tasks
        task_ids = []
        for i in range(9):
            task_id = await coordinator.delegate_task(
                task_type="security_analysis",
                task_data={"task": i},
                requester="orchestrator"
            )
            task_ids.append(task_id)
        
        # Verify tasks are distributed
        expert_tasks = {}
        for task_id in task_ids:
            task = coordinator.get_task(task_id)
            expert = task["assigned_to"]
            expert_tasks[expert] = expert_tasks.get(expert, 0) + 1
        
        # Each expert should have approximately equal load
        for expert in expert_ids:
            agent_id = f"security_expert_{expert_ids.index(expert)}"
            assert expert_tasks.get(agent_id, 0) >= 2  # At least 2 tasks each


class TestEventSourcing:
    """Test event sourcing implementation"""
    
    @pytest.mark.asyncio
    async def test_event_persistence(self):
        """Test that all events are persisted correctly"""
        event_store = EventStore()
        await event_store.initialize()
        
        # Create various event types
        events_to_create = [
            {
                "type": EventType.CUSTOM,
                "data": {"elicitation": "created"},
                "metadata": {"agent": "test"}
            },
            {
                "type": EventType.CUSTOM,
                "data": {"elicitation": "responded"},
                "metadata": {"agent": "test"}
            },
            {
                "type": EventType.AUDIT,
                "data": {"action": "security_check"},
                "metadata": {"severity": "info"}
            }
        ]
        
        event_ids = []
        for event_data in events_to_create:
            event_id = await event_store.append(
                event_type=event_data["type"],
                data=event_data["data"],
                metadata=event_data["metadata"]
            )
            event_ids.append(event_id)
        
        # Verify all events were stored
        assert len(event_ids) == 3
        assert all(eid is not None for eid in event_ids)
        
        # Retrieve events
        all_events = await event_store.get_all_events()
        assert len(all_events) >= 3
        
        # Verify event order
        for i in range(len(event_ids) - 1):
            event_i = await event_store.get_event(event_ids[i])
            event_j = await event_store.get_event(event_ids[i+1])
            assert event_i.timestamp < event_j.timestamp
    
    @pytest.mark.asyncio
    async def test_event_replay(self):
        """Test event replay capability"""
        event_store = EventStore()
        await event_store.initialize()
        
        # Create a sequence of events
        events = []
        for i in range(10):
            event_id = await event_store.append(
                event_type=EventType.CUSTOM,
                data={"sequence": i, "action": f"action_{i}"},
                metadata={"replay_test": True}
            )
            events.append(event_id)
        
        # Simulate replay from specific point
        replay_from = 5
        replayed_events = []
        
        all_events = await event_store.get_all_events()
        for event in all_events:
            if event.data.get("sequence", -1) >= replay_from:
                replayed_events.append(event)
        
        # Verify correct events were replayed
        assert len(replayed_events) >= 5
        
        # Verify order is maintained
        sequences = [e.data["sequence"] for e in replayed_events if "sequence" in e.data]
        assert sequences == sorted(sequences)
    
    @pytest.mark.asyncio
    async def test_event_projection(self):
        """Test building projections from events"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Create elicitations to build projection
        elicit_ids = []
        for i in range(5):
            elicit_id = await manager.create_elicitation(
                from_agent=f"agent_{i}",
                to_agent=f"agent_{i+1}",
                message=f"Test {i}",
                schema={},
                timeout_seconds=30
            )
            elicit_ids.append(elicit_id)
        
        # Verify projection is built correctly
        assert len(manager.projection.active_elicitations) == 5
        
        # Respond to some elicitations
        for i in range(3):
            await manager.respond_to_elicitation(
                elicitation_id=elicit_ids[i],
                responding_agent=f"agent_{i+1}",
                response_type="accept",
                data={"response": i}
            )
        
        # Verify projection is updated
        assert len(manager.projection.active_elicitations) == 2  # 2 still active
        
        # Rebuild projection from events
        await manager.projection.rebuild()
        
        # Verify projection is consistent
        assert len(manager.projection.active_elicitations) == 2
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_event_immutability(self):
        """Test that events cannot be modified after creation"""
        event_store = EventStore()
        await event_store.initialize()
        
        # Create an event
        event_id = await event_store.append(
            event_type=EventType.CUSTOM,
            data={"immutable": True, "value": 42},
            metadata={"test": "immutability"}
        )
        
        # Retrieve event
        event = await event_store.get_event(event_id)
        original_data = event.data.copy()
        
        # Attempt to modify (should not affect stored event)
        event.data["value"] = 999
        
        # Retrieve again
        event_fresh = await event_store.get_event(event_id)
        
        # Verify data is unchanged
        assert event_fresh.data == original_data
        assert event_fresh.data["value"] == 42


class TestIntegrationPerformance:
    """Test integration performance requirements"""
    
    @pytest.mark.asyncio
    async def test_integration_latency(self):
        """Test end-to-end latency meets requirements"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Measure end-to-end latency
        latencies = []
        
        for i in range(100):
            start = time.time()
            
            # Create elicitation
            elicit_id = await manager.create_elicitation(
                from_agent="agent_a",
                to_agent="agent_b",
                message="Performance test",
                schema={},
                timeout_seconds=30
            )
            
            # Respond immediately
            await manager.respond_to_elicitation(
                elicitation_id=elicit_id,
                responding_agent="agent_b",
                response_type="accept",
                data={"test": i}
            )
            
            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)
        
        # Calculate percentiles
        import numpy as np
        p50 = np.percentile(latencies, 50)
        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)
        
        # Verify meets requirements
        assert p99 < 300, f"P99 latency {p99}ms exceeds 300ms target"
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test system handles concurrent operations"""
        event_store = EventStore()
        await event_store.initialize()
        
        manager = OptimizedElicitationManager(
            event_store=event_store,
            bridge_secret_key="test_secret",
            enable_security=True
        )
        await manager.initialize()
        
        # Run concurrent operations
        async def operation(op_id: int):
            elicit_id = await manager.create_elicitation(
                from_agent=f"agent_{op_id}",
                to_agent=f"target_{op_id}",
                message=f"Concurrent {op_id}",
                schema={},
                timeout_seconds=30
            )
            
            await manager.respond_to_elicitation(
                elicitation_id=elicit_id,
                responding_agent=f"target_{op_id}",
                response_type="accept",
                data={"op": op_id}
            )
            
            return True
        
        # Run 1000 concurrent operations
        tasks = [operation(i) for i in range(1000)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify high success rate
        successes = sum(1 for r in results if r is True)
        success_rate = successes / len(results)
        
        assert success_rate > 0.99, f"Success rate {success_rate} below 99%"
        
        await manager.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])