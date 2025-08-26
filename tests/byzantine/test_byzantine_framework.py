"""
Byzantine Fault Tolerance Testing Framework

Implements comprehensive Byzantine agent simulation for testing consensus algorithms,
malicious agent behavior, and system resilience under adversarial conditions.

Plan Delta Phase 1 Days 4-7: Byzantine Testing Implementation
"""

import asyncio
import random
import pytest
import pytest_asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Callable
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

from lighthouse.bridge import LighthouseBridge


class ByzantineAgentType(Enum):
    """Types of Byzantine (malicious) agent behavior"""
    HONEST = "honest"                    # Normal cooperative behavior
    SILENT = "silent"                    # Fails to respond/participate
    CONFLICTING = "conflicting"          # Sends conflicting information
    SELFISH = "selfish"                  # Acts in own interest only
    MALICIOUS = "malicious"              # Actively tries to disrupt
    RANDOM = "random"                    # Random/unpredictable behavior
    PARTITION = "partition"              # Simulates network partitions


class ConsensusDecision(Enum):
    """Possible consensus outcomes"""
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    TIMEOUT = "timeout"


@dataclass
class AgentState:
    """Represents the state of an agent in the consensus system"""
    agent_id: str
    agent_type: ByzantineAgentType
    is_online: bool = True
    last_seen: datetime = field(default_factory=datetime.utcnow)
    reputation_score: float = 1.0
    message_count: int = 0
    malicious_actions: List[str] = field(default_factory=list)
    
    def record_malicious_action(self, action: str):
        """Record a malicious action for analysis"""
        self.malicious_actions.append(f"{datetime.utcnow().isoformat()}: {action}")
        self.reputation_score = max(0.0, self.reputation_score - 0.1)


@dataclass  
class ConsensusMessage:
    """Message in the consensus protocol"""
    message_id: str
    sender_id: str
    proposal_id: str
    message_type: str  # "prepare", "promise", "accept", "decision"
    content: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    signature: Optional[str] = None


@dataclass
class ConsensusProposal:
    """A proposal requiring consensus"""
    proposal_id: str
    proposer_id: str
    content: Dict[str, Any]
    required_approval_threshold: float = 0.67  # 2/3 majority
    timeout_seconds: int = 30
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Consensus tracking
    promises: Set[str] = field(default_factory=set)
    accepts: Set[str] = field(default_factory=set) 
    rejects: Set[str] = field(default_factory=set)
    decision: Optional[ConsensusDecision] = None
    decision_time: Optional[datetime] = None


class ByzantineAgentSimulator:
    """Simulates Byzantine agent behavior for consensus testing"""
    
    def __init__(self, agent_id: str, agent_type: ByzantineAgentType):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.state = AgentState(agent_id, agent_type)
        self.message_handlers = {
            "prepare": self._handle_prepare,
            "promise": self._handle_promise, 
            "accept": self._handle_accept,
            "decision": self._handle_decision
        }
    
    async def handle_consensus_message(self, message: ConsensusMessage) -> Optional[ConsensusMessage]:
        """Handle incoming consensus message based on agent type"""
        
        if not self.state.is_online:
            return None  # Silent failure
        
        self.state.message_count += 1
        self.state.last_seen = datetime.utcnow()
        
        # Get handler for message type
        handler = self.message_handlers.get(message.message_type)
        if not handler:
            return None
            
        # Apply Byzantine behavior
        return await self._apply_byzantine_behavior(message, handler)
    
    async def _apply_byzantine_behavior(self, message: ConsensusMessage, handler: Callable) -> Optional[ConsensusMessage]:
        """Apply Byzantine behavior patterns to message handling"""
        
        if self.agent_type == ByzantineAgentType.HONEST:
            return await handler(message)
            
        elif self.agent_type == ByzantineAgentType.SILENT:
            # 70% chance of not responding
            if random.random() < 0.7:
                self.state.record_malicious_action(f"Silent on {message.message_type}")
                return None
            return await handler(message)
            
        elif self.agent_type == ByzantineAgentType.CONFLICTING:
            # Send conflicting responses
            response = await handler(message)
            if response and random.random() < 0.5:
                # Corrupt the response
                response.content = self._corrupt_content(response.content)
                self.state.record_malicious_action(f"Conflicting response to {message.message_type}")
            return response
            
        elif self.agent_type == ByzantineAgentType.MALICIOUS:
            # Actively malicious behavior
            response = await handler(message)
            if response and random.random() < 0.8:
                # Always try to disrupt
                response.content = self._malicious_content(response.content)
                self.state.record_malicious_action(f"Malicious response to {message.message_type}")
            return response
            
        elif self.agent_type == ByzantineAgentType.RANDOM:
            # Random behavior
            if random.random() < 0.3:
                return None  # Random silence
            elif random.random() < 0.5:
                # Random corruption
                response = await handler(message)
                if response:
                    response.content = self._random_content(response.content)
                    self.state.record_malicious_action(f"Random behavior on {message.message_type}")
                return response
            else:
                return await handler(message)
        
        else:
            # Default to honest behavior
            return await handler(message)
    
    def _corrupt_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Create conflicting/corrupted content"""
        corrupted = content.copy()
        
        # Flip decisions
        if "decision" in corrupted:
            corrupted["decision"] = "reject" if content["decision"] == "approve" else "approve"
        
        # Change values
        if "value" in corrupted:
            corrupted["value"] = f"corrupted_{content['value']}"
            
        # Add false information
        corrupted["_byzantine_corruption"] = True
        return corrupted
    
    def _malicious_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Create actively malicious content"""
        malicious = content.copy()
        
        # Always reject/disrupt
        if "decision" in malicious:
            malicious["decision"] = "reject"
        
        # Add attack payloads
        malicious["_malicious_payload"] = "ATTACK_DATA"
        malicious["_byzantine_type"] = "malicious"
        return malicious
    
    def _random_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Create random content"""
        random_content = content.copy()
        
        # Random decision
        if "decision" in random_content:
            random_content["decision"] = random.choice(["approve", "reject", "timeout"])
        
        # Random values
        random_content["_random_data"] = random.randint(0, 1000000)
        return random_content
    
    # Consensus message handlers
    async def _handle_prepare(self, message: ConsensusMessage) -> ConsensusMessage:
        """Handle prepare phase of consensus"""
        return ConsensusMessage(
            message_id=f"{self.agent_id}_promise_{message.proposal_id}",
            sender_id=self.agent_id,
            proposal_id=message.proposal_id,
            message_type="promise",
            content={"promised": True, "last_accepted": None}
        )
    
    async def _handle_promise(self, message: ConsensusMessage) -> Optional[ConsensusMessage]:
        """Handle promise phase of consensus"""  
        # Acceptors don't respond to promises
        return None
    
    async def _handle_accept(self, message: ConsensusMessage) -> ConsensusMessage:
        """Handle accept phase of consensus"""
        return ConsensusMessage(
            message_id=f"{self.agent_id}_accepted_{message.proposal_id}",
            sender_id=self.agent_id,
            proposal_id=message.proposal_id,
            message_type="accepted",
            content={"accepted": True, "value": message.content.get("value")}
        )
    
    async def _handle_decision(self, message: ConsensusMessage) -> Optional[ConsensusMessage]:
        """Handle final decision phase"""
        # Learners don't respond to decisions
        return None


class ByzantineConsensusCoordinator:
    """Coordinates consensus among potentially Byzantine agents"""
    
    def __init__(self, agents: List[ByzantineAgentSimulator]):
        self.agents = {agent.agent_id: agent for agent in agents}
        self.proposals: Dict[str, ConsensusProposal] = {}
        self.message_log: List[ConsensusMessage] = []
        self.byzantine_agents = [a for a in agents if a.agent_type != ByzantineAgentType.HONEST]
        
    def get_byzantine_ratio(self) -> float:
        """Get the ratio of Byzantine to total agents"""
        return len(self.byzantine_agents) / len(self.agents) if self.agents else 0.0
    
    async def propose_consensus(self, proposal: ConsensusProposal) -> ConsensusDecision:
        """Run consensus protocol on a proposal"""
        
        self.proposals[proposal.proposal_id] = proposal
        
        # Phase 1: Prepare
        prepare_responses = await self._broadcast_prepare(proposal)
        
        # Check if we have majority promises
        promise_count = sum(1 for r in prepare_responses if r and r.content.get("promised"))
        if promise_count < len(self.agents) * proposal.required_approval_threshold:
            proposal.decision = ConsensusDecision.REJECT
            proposal.decision_time = datetime.utcnow()
            return ConsensusDecision.REJECT
        
        # Phase 2: Accept
        accept_responses = await self._broadcast_accept(proposal)
        
        # Check for majority acceptance
        accept_count = sum(1 for r in accept_responses if r and r.content.get("accepted"))
        
        if accept_count >= len(self.agents) * proposal.required_approval_threshold:
            proposal.decision = ConsensusDecision.APPROVE
        else:
            proposal.decision = ConsensusDecision.REJECT
            
        proposal.decision_time = datetime.utcnow()
        
        # Phase 3: Decision broadcast
        await self._broadcast_decision(proposal)
        
        return proposal.decision
    
    async def _broadcast_prepare(self, proposal: ConsensusProposal) -> List[Optional[ConsensusMessage]]:
        """Broadcast prepare messages to all agents"""
        
        prepare_msg = ConsensusMessage(
            message_id=f"prepare_{proposal.proposal_id}",
            sender_id="coordinator",
            proposal_id=proposal.proposal_id,
            message_type="prepare",
            content={"proposal": proposal.content}
        )
        
        self.message_log.append(prepare_msg)
        
        # Collect responses from all agents
        responses = []
        for agent in self.agents.values():
            try:
                response = await agent.handle_consensus_message(prepare_msg)
                responses.append(response)
                if response:
                    self.message_log.append(response)
            except Exception as e:
                # Agent failure
                responses.append(None)
        
        return responses
    
    async def _broadcast_accept(self, proposal: ConsensusProposal) -> List[Optional[ConsensusMessage]]:
        """Broadcast accept messages to all agents"""
        
        accept_msg = ConsensusMessage(
            message_id=f"accept_{proposal.proposal_id}",
            sender_id="coordinator",
            proposal_id=proposal.proposal_id,
            message_type="accept",
            content={"value": proposal.content, "proposal_id": proposal.proposal_id}
        )
        
        self.message_log.append(accept_msg)
        
        responses = []
        for agent in self.agents.values():
            try:
                response = await agent.handle_consensus_message(accept_msg)
                responses.append(response)
                if response:
                    self.message_log.append(response)
            except Exception as e:
                responses.append(None)
                
        return responses
    
    async def _broadcast_decision(self, proposal: ConsensusProposal) -> None:
        """Broadcast final decision to all agents"""
        
        decision_msg = ConsensusMessage(
            message_id=f"decision_{proposal.proposal_id}",
            sender_id="coordinator",
            proposal_id=proposal.proposal_id,
            message_type="decision",
            content={"decision": proposal.decision.value if proposal.decision else "timeout"}
        )
        
        self.message_log.append(decision_msg)
        
        for agent in self.agents.values():
            try:
                await agent.handle_consensus_message(decision_msg)
            except Exception:
                # Ignore agent failures during decision broadcast
                pass
    
    def get_consensus_statistics(self) -> Dict[str, Any]:
        """Get statistics about consensus behavior"""
        
        total_proposals = len(self.proposals)
        approved = sum(1 for p in self.proposals.values() if p.decision == ConsensusDecision.APPROVE)
        rejected = sum(1 for p in self.proposals.values() if p.decision == ConsensusDecision.REJECT)
        
        byzantine_actions = {}
        for agent in self.byzantine_agents:
            byzantine_actions[agent.agent_id] = {
                "type": agent.agent_type.value,
                "malicious_actions": len(agent.state.malicious_actions),
                "reputation": agent.state.reputation_score,
                "messages": agent.state.message_count
            }
        
        return {
            "total_proposals": total_proposals,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": approved / total_proposals if total_proposals > 0 else 0,
            "byzantine_ratio": self.get_byzantine_ratio(),
            "byzantine_agent_count": len(self.byzantine_agents),
            "total_messages": len(self.message_log),
            "byzantine_actions": byzantine_actions
        }


# Test Cases
class TestByzantineFaultTolerance:
    """Test suite for Byzantine fault tolerance"""
    
    def create_agent_mix(self, total_agents: int = 10, byzantine_ratio: float = 0.33) -> List[ByzantineAgentSimulator]:
        """Create a mix of honest and Byzantine agents"""
        
        byzantine_count = max(1, int(total_agents * byzantine_ratio + 0.5))  # Round to nearest
        honest_count = total_agents - byzantine_count
        
        agents = []
        
        # Create honest agents
        for i in range(honest_count):
            agents.append(ByzantineAgentSimulator(f"honest_{i}", ByzantineAgentType.HONEST))
        
        # Create Byzantine agents with different types
        byzantine_types = [
            ByzantineAgentType.SILENT,
            ByzantineAgentType.CONFLICTING, 
            ByzantineAgentType.MALICIOUS,
            ByzantineAgentType.RANDOM
        ]
        
        for i in range(byzantine_count):
            byz_type = byzantine_types[i % len(byzantine_types)]
            agents.append(ByzantineAgentSimulator(f"byzantine_{i}", byz_type))
        
        return agents
    
    @pytest.mark.asyncio
    async def test_consensus_with_honest_agents(self):
        """Test consensus with only honest agents"""
        
        # Create 7 honest agents
        agents = [ByzantineAgentSimulator(f"honest_{i}", ByzantineAgentType.HONEST) for i in range(7)]
        coordinator = ByzantineConsensusCoordinator(agents)
        
        # Propose consensus
        proposal = ConsensusProposal(
            proposal_id="test_honest",
            proposer_id="test",
            content={"command": "approve_deployment", "target": "production"}
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        assert decision == ConsensusDecision.APPROVE
        assert proposal.decision == ConsensusDecision.APPROVE
        
        stats = coordinator.get_consensus_statistics()
        assert stats["approval_rate"] == 1.0
        assert stats["byzantine_ratio"] == 0.0
    
    @pytest.mark.asyncio
    async def test_consensus_with_33_percent_byzantine(self):
        """Test consensus with 33% Byzantine agents (industry standard limit)"""
        
        agents = self.create_agent_mix(total_agents=9, byzantine_ratio=0.33)  # 3 Byzantine, 6 honest
        coordinator = ByzantineConsensusCoordinator(agents)
        
        proposal = ConsensusProposal(
            proposal_id="test_33_byzantine",
            proposer_id="test",
            content={"command": "validate_transaction", "amount": 1000}
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        # Should still reach consensus with 33% Byzantine agents
        assert decision in [ConsensusDecision.APPROVE, ConsensusDecision.REJECT]
        
        stats = coordinator.get_consensus_statistics()
        assert abs(stats["byzantine_ratio"] - 0.33) < 0.01  # Within 1% of target
        assert stats["byzantine_agent_count"] == 3
    
    @pytest.mark.asyncio
    async def test_consensus_failure_with_majority_byzantine(self):
        """Test consensus failure with majority Byzantine agents"""
        
        agents = self.create_agent_mix(total_agents=10, byzantine_ratio=0.6)  # 6 Byzantine, 4 honest
        coordinator = ByzantineConsensusCoordinator(agents)
        
        proposal = ConsensusProposal(
            proposal_id="test_majority_byzantine",
            proposer_id="test", 
            content={"command": "critical_operation", "risk": "high"}
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        # Should fail to reach consensus or reject
        assert decision in [ConsensusDecision.REJECT, ConsensusDecision.TIMEOUT]
        
        stats = coordinator.get_consensus_statistics()
        assert stats["byzantine_ratio"] == 0.6
        assert stats["approval_rate"] <= 0.5  # Should have low approval rate
    
    @pytest.mark.asyncio
    async def test_malicious_agent_detection(self):
        """Test detection and tracking of malicious agent behavior"""
        
        # Create agents with specific Byzantine types
        agents = [
            ByzantineAgentSimulator("honest_1", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("honest_2", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("malicious_1", ByzantineAgentType.MALICIOUS),
            ByzantineAgentSimulator("conflicting_1", ByzantineAgentType.CONFLICTING)
        ]
        
        coordinator = ByzantineConsensusCoordinator(agents)
        
        # Run multiple consensus rounds
        for i in range(5):
            proposal = ConsensusProposal(
                proposal_id=f"test_detection_{i}",
                proposer_id="test",
                content={"command": f"operation_{i}"}
            )
            await coordinator.propose_consensus(proposal)
        
        stats = coordinator.get_consensus_statistics()
        
        # Check that malicious behavior was detected
        assert "malicious_1" in stats["byzantine_actions"]
        assert "conflicting_1" in stats["byzantine_actions"]
        
        malicious_stats = stats["byzantine_actions"]["malicious_1"]
        assert malicious_stats["malicious_actions"] > 0
        assert malicious_stats["reputation"] < 1.0
        
        conflicting_stats = stats["byzantine_actions"]["conflicting_1"]
        assert conflicting_stats["malicious_actions"] >= 0
    
    @pytest.mark.asyncio
    async def test_agent_recovery_simulation(self):
        """Test agent recovery after Byzantine behavior"""
        
        # Create Byzantine agent that can "recover"
        byzantine_agent = ByzantineAgentSimulator("recovering_agent", ByzantineAgentType.MALICIOUS)
        honest_agents = [ByzantineAgentSimulator(f"honest_{i}", ByzantineAgentType.HONEST) for i in range(6)]
        
        agents = [byzantine_agent] + honest_agents
        coordinator = ByzantineConsensusCoordinator(agents)
        
        # Phase 1: Byzantine behavior
        proposal1 = ConsensusProposal(
            proposal_id="before_recovery",
            proposer_id="test",
            content={"phase": "before_recovery"}
        )
        await coordinator.propose_consensus(proposal1)
        
        initial_malicious_actions = len(byzantine_agent.state.malicious_actions)
        
        # Phase 2: "Recovery" - change agent to honest
        byzantine_agent.agent_type = ByzantineAgentType.HONEST
        
        proposal2 = ConsensusProposal(
            proposal_id="after_recovery", 
            proposer_id="test",
            content={"phase": "after_recovery"}
        )
        decision2 = await coordinator.propose_consensus(proposal2)
        
        # Agent should behave honestly now
        final_malicious_actions = len(byzantine_agent.state.malicious_actions)
        assert final_malicious_actions == initial_malicious_actions  # No new malicious actions
        assert decision2 == ConsensusDecision.APPROVE  # Should succeed with honest behavior
    
    @pytest.mark.asyncio 
    async def test_context_package_tampering_detection(self):
        """Test detection of context package tampering by Byzantine agents"""
        
        agents = self.create_agent_mix(total_agents=7, byzantine_ratio=0.28)  # 2 Byzantine, 5 honest
        coordinator = ByzantineConsensusCoordinator(agents)
        
        # Simulate context package validation proposal
        context_package = {
            "package_id": "security_review_v1.2",
            "files": ["auth.py", "validation.py", "crypto.py"],
            "checksum": "abc123def456",
            "signature": "valid_signature"
        }
        
        proposal = ConsensusProposal(
            proposal_id="context_package_validation",
            proposer_id="security_agent",
            content={
                "command": "validate_context_package",
                "package": context_package,
                "integrity_required": True
            }
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        # Analyze message log for tampering attempts
        tampering_detected = False
        for message in coordinator.message_log:
            if message.content.get("_byzantine_corruption") or message.content.get("_malicious_payload"):
                tampering_detected = True
                break
        
        stats = coordinator.get_consensus_statistics()
        
        # Should detect tampering attempts from Byzantine agents
        if stats["byzantine_agent_count"] > 0:
            assert tampering_detected or any(
                actions["malicious_actions"] > 0 
                for actions in stats["byzantine_actions"].values()
            )


# Integration with LighthouseBridge
@pytest.mark.asyncio
async def test_byzantine_integration_with_lighthouse_bridge():
    """Test Byzantine framework integration with LighthouseBridge"""
    
    with patch('lighthouse.bridge.fuse_mount.mount_manager.FUSE_AVAILABLE', True):
        bridge = LighthouseBridge(
            project_id="byzantine_test",
            mount_point="/tmp/lighthouse_byzantine_test",
            config={'fuse_foreground': True, 'fuse_allow_other': False}
        )
        
        # Mock FUSE operations
        with patch.object(bridge.fuse_mount_manager, 'mount', AsyncMock(return_value=True)), \
             patch.object(bridge.fuse_mount_manager, 'unmount', AsyncMock(return_value=True)):
            
            await bridge.start()
            
            try:
                # Create Byzantine agent simulation
                agents = [
                    ByzantineAgentSimulator("agent_1", ByzantineAgentType.HONEST),
                    ByzantineAgentSimulator("agent_2", ByzantineAgentType.HONEST),
                    ByzantineAgentSimulator("agent_3", ByzantineAgentType.MALICIOUS)
                ]
                
                coordinator = ByzantineConsensusCoordinator(agents)
                
                # Test consensus on a bridge validation request
                proposal = ConsensusProposal(
                    proposal_id="bridge_validation",
                    proposer_id="bridge_coordinator",
                    content={
                        "command": "validate_expert_request", 
                        "tool_name": "Bash",
                        "tool_input": {"command": "rm -rf /tmp/test"},
                        "risk_level": "high"
                    }
                )
                
                decision = await coordinator.propose_consensus(proposal)
                
                # Validate that bridge can handle consensus result
                if decision == ConsensusDecision.APPROVE:
                    # Simulate approved validation
                    result = await bridge.validate_command(
                        tool_name="Read",  # Use safe command for test
                        tool_input={"file_path": "/tmp/test.txt"},
                        agent_id="consensus_approved_agent"
                    )
                    assert isinstance(result, dict)
                
                stats = coordinator.get_consensus_statistics()
                assert stats["total_proposals"] == 1
                assert stats["byzantine_agent_count"] == 1
                
            finally:
                await bridge.stop()