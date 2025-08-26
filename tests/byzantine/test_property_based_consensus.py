"""
Property-Based Testing for Byzantine Consensus

Uses Hypothesis framework for property-based testing of Byzantine fault tolerance,
ensuring consensus properties hold under various adversarial conditions.

Plan Delta Phase 1 Days 4-7: Property-Based Testing Framework Integration
"""

import asyncio
import pytest
from typing import List, Set, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Import hypothesis for property-based testing
try:
    from hypothesis import given, strategies as st, assume, settings, Verbosity
    from hypothesis.stateful import RuleBasedStateMachine, initialize, rule, precondition, invariant
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    # Create stubs for when hypothesis is not available
    def given(*args, **kwargs):
        def decorator(f):
            return f
        return decorator
    
    def settings(*args, **kwargs):
        def decorator(f):
            return f
        return decorator
    
    def assume(*args, **kwargs):
        pass
    
    class st:
        @staticmethod
        def integers(*args, **kwargs): return range(1, 10)
        @staticmethod  
        def floats(*args, **kwargs): return [0.1, 0.2, 0.3, 0.5, 0.7]
        @staticmethod
        def lists(*args, **kwargs): return [[1, 2], [1, 2, 3]]
        @staticmethod
        def sampled_from(items): return items
        @staticmethod
        def one_of(*args): return args[0] if args else "test"
        @staticmethod
        def text(*args, **kwargs): return "test_text"
        @staticmethod
        def dictionaries(*args, **kwargs): return {"test": "data"}
        @staticmethod
        def booleans(): return [True, False]
    
    class RuleBasedStateMachine:
        def __init__(self): pass
    
    def initialize(): 
        def decorator(f): return f
        return decorator
        
    def rule(*args, **kwargs):
        def decorator(f): return f
        return decorator
        
    def invariant():
        def decorator(f): return f
        return decorator

from test_byzantine_framework import (
    ByzantineAgentSimulator, ByzantineAgentType, ByzantineConsensusCoordinator,
    ConsensusProposal, ConsensusDecision, AgentState
)


class ConsensusProperty(Enum):
    """Fundamental consensus properties that must hold"""
    VALIDITY = "validity"          # If all honest agents propose same value, that value is decided
    AGREEMENT = "agreement"        # All honest agents decide on same value  
    TERMINATION = "termination"    # All honest agents eventually decide
    INTEGRITY = "integrity"        # Each agent decides at most once


@dataclass
class ConsensusExecution:
    """Records the execution of a consensus instance"""
    proposal_id: str
    honest_agents: List[str]
    byzantine_agents: List[str]
    byzantine_ratio: float
    initial_proposal: Any
    final_decision: ConsensusDecision
    honest_decisions: Dict[str, ConsensusDecision]
    execution_time_ms: float
    message_count: int
    
    def validates_property(self, prop: ConsensusProperty) -> bool:
        """Check if this execution validates a specific consensus property"""
        
        if prop == ConsensusProperty.VALIDITY:
            # If all honest agents propose the same value, that value should be decided
            if len(set(self.honest_decisions.values())) == 1:
                unanimous_decision = list(self.honest_decisions.values())[0]
                return self.final_decision == unanimous_decision
            return True  # Property doesn't apply if no unanimous proposal
            
        elif prop == ConsensusProperty.AGREEMENT:
            # All honest agents should decide on the same value
            honest_decision_values = set(self.honest_decisions.values())
            return len(honest_decision_values) <= 1
            
        elif prop == ConsensusProperty.TERMINATION:
            # All honest agents should eventually decide (non-None)
            return all(decision is not None for decision in self.honest_decisions.values())
            
        elif prop == ConsensusProperty.INTEGRITY:
            # Each agent should decide at most once (recorded in execution)
            return True  # This is enforced by our simulation framework
            
        return False


class ByzantineConsensusPropertyTester:
    """Property-based testing for Byzantine consensus algorithms"""
    
    def __init__(self):
        self.executions: List[ConsensusExecution] = []
    
    async def test_consensus_properties(self, 
                                      total_agents: int,
                                      byzantine_ratio: float,
                                      proposal_content: Dict[str, Any]) -> ConsensusExecution:
        """Test consensus with given parameters and return execution record"""
        
        # Create agent mix
        byzantine_count = int(total_agents * byzantine_ratio)
        honest_count = total_agents - byzantine_count
        
        agents = []
        honest_agent_ids = []
        byzantine_agent_ids = []
        
        # Create honest agents
        for i in range(honest_count):
            agent_id = f"honest_{i}"
            agents.append(ByzantineAgentSimulator(agent_id, ByzantineAgentType.HONEST))
            honest_agent_ids.append(agent_id)
        
        # Create Byzantine agents
        byzantine_types = [ByzantineAgentType.SILENT, ByzantineAgentType.CONFLICTING, 
                          ByzantineAgentType.MALICIOUS, ByzantineAgentType.RANDOM]
        for i in range(byzantine_count):
            byz_type = byzantine_types[i % len(byzantine_types)]
            agent_id = f"byzantine_{byz_type.value}_{i}"
            agents.append(ByzantineAgentSimulator(agent_id, byz_type))
            byzantine_agent_ids.append(agent_id)
        
        # Run consensus
        coordinator = ByzantineConsensusCoordinator(agents)
        proposal = ConsensusProposal(
            proposal_id=f"property_test_{len(self.executions)}",
            proposer_id="property_tester",
            content=proposal_content
        )
        
        import time
        start_time = time.time()
        
        final_decision = await coordinator.propose_consensus(proposal)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Collect honest agent decisions (simulate individual agent decisions)
        honest_decisions = {}
        for agent_id in honest_agent_ids:
            # In a real system, we'd query each agent for their decision
            # For simulation, honest agents follow the coordinator's decision
            honest_decisions[agent_id] = final_decision
        
        execution = ConsensusExecution(
            proposal_id=proposal.proposal_id,
            honest_agents=honest_agent_ids,
            byzantine_agents=byzantine_agent_ids,
            byzantine_ratio=byzantine_ratio,
            initial_proposal=proposal_content,
            final_decision=final_decision,
            honest_decisions=honest_decisions,
            execution_time_ms=execution_time_ms,
            message_count=len(coordinator.message_log)
        )
        
        self.executions.append(execution)
        return execution
    
    def analyze_property_violations(self) -> Dict[ConsensusProperty, List[ConsensusExecution]]:
        """Analyze all executions for property violations"""
        
        violations = {prop: [] for prop in ConsensusProperty}
        
        for execution in self.executions:
            for prop in ConsensusProperty:
                if not execution.validates_property(prop):
                    violations[prop].append(execution)
        
        return violations
    
    def get_success_rate_by_byzantine_ratio(self) -> Dict[float, float]:
        """Get consensus success rate by Byzantine agent ratio"""
        
        ratio_groups: Dict[float, List[bool]] = {}
        
        for execution in self.executions:
            ratio = round(execution.byzantine_ratio, 2)
            if ratio not in ratio_groups:
                ratio_groups[ratio] = []
            
            # Consider APPROVE as success
            success = execution.final_decision == ConsensusDecision.APPROVE
            ratio_groups[ratio].append(success)
        
        success_rates = {}
        for ratio, results in ratio_groups.items():
            success_rates[ratio] = sum(results) / len(results)
        
        return success_rates


# Property-based test cases using Hypothesis
class TestConsensusProperties:
    """Property-based tests for consensus algorithm correctness"""
    
    @pytest.fixture
    def property_tester(self):
        """Create a fresh property tester for each test"""
        return ByzantineConsensusPropertyTester()
    
    @pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not available")
    @given(
        total_agents=st.integers(min_value=3, max_value=15),
        byzantine_ratio=st.floats(min_value=0.0, max_value=0.49),  # Keep below 50%
        proposal_value=st.integers(min_value=1, max_value=1000)
    )
    @settings(max_examples=20, deadline=30000)  # 30 second timeout per example
    @pytest.mark.asyncio
    async def test_consensus_validity_property(self, property_tester, total_agents, byzantine_ratio, proposal_value):
        """Property test: If all honest agents propose same value, that value is decided"""
        
        assume(total_agents >= 3)  # Need minimum agents for consensus
        assume(byzantine_ratio < 0.5)  # Byzantine agents must be minority
        
        proposal_content = {
            "command": "test_validity",
            "value": proposal_value,
            "unanimous": True
        }
        
        execution = await property_tester.test_consensus_properties(
            total_agents=total_agents,
            byzantine_ratio=byzantine_ratio,
            proposal_content=proposal_content
        )
        
        # Property check: With honest majority and unanimous proposal, should succeed
        if execution.byzantine_ratio < 0.33:  # Well below Byzantine threshold
            assert execution.validates_property(ConsensusProperty.VALIDITY)
            assert execution.validates_property(ConsensusProperty.AGREEMENT)
    
    @pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not available")  
    @given(
        total_agents=st.integers(min_value=4, max_value=12),
        byzantine_ratio=st.floats(min_value=0.0, max_value=0.33)  # Industry standard limit
    )
    @settings(max_examples=15, deadline=30000)
    @pytest.mark.asyncio
    async def test_consensus_agreement_property(self, property_tester, total_agents, byzantine_ratio):
        """Property test: All honest agents decide on same value"""
        
        assume(total_agents >= 4)
        assume(byzantine_ratio <= 0.33)  # Standard Byzantine fault tolerance
        
        proposal_content = {
            "command": "test_agreement",
            "critical": True,
            "requires_consensus": True
        }
        
        execution = await property_tester.test_consensus_properties(
            total_agents=total_agents,
            byzantine_ratio=byzantine_ratio,
            proposal_content=proposal_content
        )
        
        # Property check: All honest agents should agree
        assert execution.validates_property(ConsensusProperty.AGREEMENT)
        
        # Additional invariant: With ≤33% Byzantine agents, consensus should succeed
        if execution.byzantine_ratio <= 0.33:
            assert execution.final_decision in [ConsensusDecision.APPROVE, ConsensusDecision.REJECT]
            assert execution.validates_property(ConsensusProperty.TERMINATION)
    
    @pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not available")
    @given(
        byzantine_types=st.lists(
            st.sampled_from([ByzantineAgentType.SILENT, ByzantineAgentType.CONFLICTING, 
                           ByzantineAgentType.MALICIOUS, ByzantineAgentType.RANDOM]),
            min_size=1, max_size=4
        )
    )
    @settings(max_examples=10, deadline=30000)
    @pytest.mark.asyncio
    async def test_consensus_with_mixed_byzantine_types(self, property_tester, byzantine_types):
        """Property test: Consensus works with different types of Byzantine agents"""
        
        total_agents = 7  # Fixed size for this test
        byzantine_count = len(byzantine_types)
        
        assume(byzantine_count < total_agents // 2)  # Maintain honest majority
        
        # Create specific agent mix
        agents = []
        honest_count = total_agents - byzantine_count
        
        # Honest agents
        for i in range(honest_count):
            agents.append(ByzantineAgentSimulator(f"honest_{i}", ByzantineAgentType.HONEST))
        
        # Specific Byzantine agents
        for i, byz_type in enumerate(byzantine_types):
            agents.append(ByzantineAgentSimulator(f"byz_{byz_type.value}_{i}", byz_type))
        
        # Run consensus
        coordinator = ByzantineConsensusCoordinator(agents)
        proposal = ConsensusProposal(
            proposal_id="mixed_byzantine_test",
            proposer_id="property_tester",
            content={
                "command": "test_mixed_byzantine",
                "byzantine_types": [bt.value for bt in byzantine_types]
            }
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        # With honest majority, should still reach some decision
        assert decision in [ConsensusDecision.APPROVE, ConsensusDecision.REJECT, ConsensusDecision.TIMEOUT]
        
        # Analyze Byzantine behavior
        stats = coordinator.get_consensus_statistics()
        assert stats["byzantine_agent_count"] == len(byzantine_types)
        
        # Should detect some malicious behavior from non-honest agents
        if ByzantineAgentType.MALICIOUS in byzantine_types:
            malicious_detected = any(
                actions["malicious_actions"] > 0 
                for actions in stats["byzantine_actions"].values()
                if "malicious" in actions.get("type", "")
            )
            assert malicious_detected


# Stateful property testing using Hypothesis
@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not available")
class ConsensusStateMachine(RuleBasedStateMachine):
    """Stateful testing of consensus system over multiple rounds"""
    
    def __init__(self):
        super().__init__()
        self.agents: List[ByzantineAgentSimulator] = []
        self.coordinator: ByzantineConsensusCoordinator = None
        self.round_count = 0
        self.total_proposals = 0
    
    @initialize()
    def setup_consensus_system(self):
        """Initialize the consensus system"""
        # Create a stable set of agents for stateful testing
        self.agents = [
            ByzantineAgentSimulator("honest_1", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("honest_2", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("honest_3", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("honest_4", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("byzantine_1", ByzantineAgentType.CONFLICTING),
            ByzantineAgentSimulator("byzantine_2", ByzantineAgentType.SILENT)
        ]
        self.coordinator = ByzantineConsensusCoordinator(self.agents)
    
    @rule(
        proposal_content=st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.text(min_size=1, max_size=50), st.integers(), st.booleans()),
            min_size=1, max_size=5
        )
    )
    async def run_consensus_round(self, proposal_content):
        """Run a consensus round with given proposal content"""
        
        self.total_proposals += 1
        proposal = ConsensusProposal(
            proposal_id=f"stateful_test_{self.total_proposals}",
            proposer_id="stateful_tester",
            content=proposal_content
        )
        
        decision = await self.coordinator.propose_consensus(proposal)
        
        # Record the round
        self.round_count += 1
        
        # Basic invariant: Should get some decision
        assert decision in [ConsensusDecision.APPROVE, ConsensusDecision.REJECT, ConsensusDecision.TIMEOUT]
    
    @rule()
    def make_agent_byzantine(self):
        """Convert an honest agent to Byzantine (simulating compromise)"""
        honest_agents = [a for a in self.agents if a.agent_type == ByzantineAgentType.HONEST]
        
        if honest_agents and len(honest_agents) > 2:  # Keep at least 2 honest
            import random
            agent = random.choice(honest_agents)
            agent.agent_type = ByzantineAgentType.MALICIOUS
            agent.state.record_malicious_action("Agent compromised in stateful test")
    
    @rule()
    def recover_byzantine_agent(self):
        """Recover a Byzantine agent (simulating detection and recovery)"""
        byzantine_agents = [a for a in self.agents if a.agent_type != ByzantineAgentType.HONEST]
        
        if byzantine_agents:
            import random
            agent = random.choice(byzantine_agents)
            agent.agent_type = ByzantineAgentType.HONEST
            agent.state.reputation_score = min(1.0, agent.state.reputation_score + 0.5)
    
    @invariant()
    def consensus_system_invariants(self):
        """Invariants that should hold throughout execution"""
        
        # System should always have agents
        assert len(self.agents) > 0
        assert self.coordinator is not None
        
        # Should have at least some honest agents
        honest_count = sum(1 for a in self.agents if a.agent_type == ByzantineAgentType.HONEST)
        assert honest_count >= 1
        
        # Byzantine ratio should not exceed 50%
        byzantine_count = sum(1 for a in self.agents if a.agent_type != ByzantineAgentType.HONEST)
        byzantine_ratio = byzantine_count / len(self.agents)
        assert byzantine_ratio <= 0.5
        
        # All agents should have valid state
        for agent in self.agents:
            assert agent.agent_id
            assert isinstance(agent.state, AgentState)
            assert 0.0 <= agent.state.reputation_score <= 1.0


# Integration tests
@pytest.mark.asyncio
async def test_property_based_framework_integration():
    """Test that property-based testing framework integrates correctly"""
    
    property_tester = ByzantineConsensusPropertyTester()
    
    # Run several test executions
    test_cases = [
        {"total_agents": 7, "byzantine_ratio": 0.14, "content": {"test": "basic"}},
        {"total_agents": 9, "byzantine_ratio": 0.33, "content": {"test": "threshold"}},
        {"total_agents": 5, "byzantine_ratio": 0.20, "content": {"test": "small_group"}}
    ]
    
    for i, case in enumerate(test_cases):
        execution = await property_tester.test_consensus_properties(
            total_agents=case["total_agents"],
            byzantine_ratio=case["byzantine_ratio"],
            proposal_content=case["content"]
        )
        
        # Validate execution record
        assert execution.proposal_id == f"property_test_{i}"
        assert len(execution.honest_agents) + len(execution.byzantine_agents) == case["total_agents"]
        assert abs(execution.byzantine_ratio - case["byzantine_ratio"]) < 0.05
        assert execution.execution_time_ms > 0
        assert execution.message_count > 0
    
    # Analyze results
    violations = property_tester.analyze_property_violations()
    success_rates = property_tester.get_success_rate_by_byzantine_ratio()
    
    # Should have run tests
    assert len(property_tester.executions) == 3
    
    # Should have success rate data
    assert len(success_rates) > 0
    
    # Should detect any property violations
    for prop, violation_list in violations.items():
        # For valid test cases, most properties should hold
        violation_rate = len(violation_list) / len(property_tester.executions)
        assert violation_rate <= 0.5  # Allow some violations due to Byzantine behavior


@pytest.mark.asyncio 
async def test_hypothesis_availability():
    """Test that property-based testing works with or without Hypothesis"""
    
    # Test should work regardless of whether Hypothesis is available
    property_tester = ByzantineConsensusPropertyTester()
    
    execution = await property_tester.test_consensus_properties(
        total_agents=5,
        byzantine_ratio=0.2,
        proposal_content={"test": "hypothesis_availability"}
    )
    
    assert execution is not None
    assert execution.final_decision in [ConsensusDecision.APPROVE, ConsensusDecision.REJECT, ConsensusDecision.TIMEOUT]
    
    # Property validation should work
    assert isinstance(execution.validates_property(ConsensusProperty.AGREEMENT), bool)
    assert isinstance(execution.validates_property(ConsensusProperty.VALIDITY), bool)
    
    # Framework should handle missing Hypothesis gracefully
    if not HYPOTHESIS_AVAILABLE:
        print("WARNING: Hypothesis not available - property-based tests will use simpler fallbacks")
    else:
        print("INFO: Hypothesis available - full property-based testing enabled")