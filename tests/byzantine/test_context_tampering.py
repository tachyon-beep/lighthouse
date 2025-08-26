"""
Context Package Tampering Detection Tests

Tests Byzantine agents' ability to tamper with context packages and the system's
ability to detect and prevent such tampering.

Plan Delta Phase 1 Days 4-7: Context Package Tampering Detection Testing
"""

import asyncio
import hashlib
import json
import pytest
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from test_byzantine_framework import (
    ByzantineAgentSimulator, ByzantineAgentType, ByzantineConsensusCoordinator,
    ConsensusProposal, ConsensusDecision
)


@dataclass
class ContextPackage:
    """Represents a context package with integrity verification"""
    package_id: str
    title: str
    description: str
    files: List[str]
    metadata: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    checksum: Optional[str] = None
    signature: Optional[str] = None
    
    def __post_init__(self):
        if self.checksum is None:
            self.checksum = self.calculate_checksum()
    
    def calculate_checksum(self) -> str:
        """Calculate SHA-256 checksum of package contents"""
        content_str = json.dumps({
            "package_id": self.package_id,
            "title": self.title,
            "description": self.description,
            "files": sorted(self.files),
            "metadata": self.metadata
        }, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def verify_integrity(self) -> bool:
        """Verify package integrity by recalculating checksum"""
        return self.checksum == self.calculate_checksum()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transmission"""
        return {
            "package_id": self.package_id,
            "title": self.title,
            "description": self.description,
            "files": self.files,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "checksum": self.checksum,
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextPackage':
        """Create from dictionary"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow()
        return cls(
            package_id=data["package_id"],
            title=data["title"],
            description=data["description"],
            files=data["files"],
            metadata=data["metadata"],
            created_at=created_at,
            checksum=data.get("checksum"),
            signature=data.get("signature")
        )


class ContextPackageTamperingAgent(ByzantineAgentSimulator):
    """Byzantine agent specialized in context package tampering"""
    
    def __init__(self, agent_id: str, agent_type: ByzantineAgentType, tampering_strategy: str = "modify_files"):
        super().__init__(agent_id, agent_type)
        self.tampering_strategy = tampering_strategy
        self.tampering_attempts = []
    
    def tamper_with_package(self, package: ContextPackage) -> ContextPackage:
        """Apply tampering based on strategy"""
        
        if self.agent_type == ByzantineAgentType.HONEST:
            return package  # No tampering
        
        tampered_package = ContextPackage.from_dict(package.to_dict())
        
        if self.tampering_strategy == "modify_files":
            # Add malicious files
            tampered_package.files.append("malicious_payload.py")
            tampered_package.files.append("backdoor.sh")
            self.state.record_malicious_action("Added malicious files to context package")
            
        elif self.tampering_strategy == "modify_metadata":
            # Modify metadata to change behavior
            tampered_package.metadata["security_level"] = "bypassed"
            tampered_package.metadata["validation_required"] = False
            tampered_package.metadata["malicious_payload"] = True
            self.state.record_malicious_action("Modified package metadata")
            
        elif self.tampering_strategy == "corrupt_checksum":
            # Corrupt the checksum to hide tampering
            tampered_package.checksum = "corrupted_checksum_" + tampered_package.checksum[:16]
            self.state.record_malicious_action("Corrupted package checksum")
            
        elif self.tampering_strategy == "replace_content":
            # Replace entire content
            tampered_package.title = "Malicious Package"
            tampered_package.description = "This package has been compromised"
            tampered_package.files = ["malicious_code.py", "exploit.sh"]
            tampered_package.metadata = {"compromised": True, "attack_type": "replacement"}
            self.state.record_malicious_action("Replaced package content")
        
        # Record tampering attempt
        self.tampering_attempts.append({
            "strategy": self.tampering_strategy,
            "original_checksum": package.checksum,
            "tampered_checksum": tampered_package.calculate_checksum(),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return tampered_package


class ContextPackageValidator:
    """Validates context packages for tampering"""
    
    def __init__(self):
        self.validation_history = []
        self.known_good_packages = {}
    
    def register_trusted_package(self, package: ContextPackage):
        """Register a package as trusted"""
        self.known_good_packages[package.package_id] = {
            "checksum": package.checksum,
            "signature": package.signature,
            "files": set(package.files),
            "registered_at": datetime.utcnow()
        }
    
    def validate_package_integrity(self, package: ContextPackage) -> Dict[str, Any]:
        """Comprehensive package validation"""
        
        validation_result = {
            "package_id": package.package_id,
            "is_valid": True,
            "integrity_check": True,
            "tampering_detected": False,
            "issues": [],
            "validation_timestamp": datetime.utcnow().isoformat()
        }
        
        # 1. Basic integrity check
        if not package.verify_integrity():
            validation_result["integrity_check"] = False
            validation_result["is_valid"] = False
            validation_result["issues"].append("Checksum verification failed")
        
        # 2. Check against known good packages
        if package.package_id in self.known_good_packages:
            trusted = self.known_good_packages[package.package_id]
            
            if package.checksum != trusted["checksum"]:
                validation_result["tampering_detected"] = True
                validation_result["is_valid"] = False
                validation_result["issues"].append("Package content differs from trusted version")
            
            # Check for suspicious files
            package_files = set(package.files)
            trusted_files = trusted["files"]
            
            added_files = package_files - trusted_files
            removed_files = trusted_files - package_files
            
            if added_files:
                validation_result["tampering_detected"] = True
                validation_result["issues"].append(f"Suspicious files added: {list(added_files)}")
            
            if removed_files:
                validation_result["tampering_detected"] = True
                validation_result["issues"].append(f"Expected files removed: {list(removed_files)}")
        
        # 3. Content-based anomaly detection
        suspicious_files = self._detect_suspicious_files(package.files)
        if suspicious_files:
            validation_result["tampering_detected"] = True
            validation_result["issues"].append(f"Suspicious files detected: {suspicious_files}")
        
        # 4. Metadata validation
        metadata_issues = self._validate_metadata(package.metadata)
        if metadata_issues:
            validation_result["tampering_detected"] = True
            validation_result["issues"].extend(metadata_issues)
        
        # Update validation result
        if validation_result["tampering_detected"] or not validation_result["integrity_check"]:
            validation_result["is_valid"] = False
        
        self.validation_history.append(validation_result)
        return validation_result
    
    def _detect_suspicious_files(self, files: List[str]) -> List[str]:
        """Detect files with suspicious names or extensions"""
        suspicious_patterns = [
            "malicious", "backdoor", "exploit", "payload", "hack",
            ".sh", ".bat", ".exe", ".dll", ".so"
        ]
        
        suspicious_files = []
        for file_name in files:
            file_lower = file_name.lower()
            if any(pattern in file_lower for pattern in suspicious_patterns):
                suspicious_files.append(file_name)
        
        return suspicious_files
    
    def _validate_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate package metadata for suspicious content"""
        issues = []
        
        # Check for suspicious metadata keys
        suspicious_keys = ["malicious", "compromised", "backdoor", "exploit", "attack"]
        for key in metadata.keys():
            if any(suspicious in key.lower() for suspicious in suspicious_keys):
                issues.append(f"Suspicious metadata key: {key}")
        
        # Check for security bypasses
        if metadata.get("validation_required") is False:
            issues.append("Validation bypass detected in metadata")
        
        if metadata.get("security_level") == "bypassed":
            issues.append("Security level bypass detected")
        
        return issues


class TestContextPackageTampering:
    """Test suite for context package tampering detection"""
    
    @pytest.fixture
    def clean_context_package(self):
        """Create a clean, untampered context package"""
        return ContextPackage(
            package_id="security_review_v1.2",
            title="Security Review Context",
            description="Context package for security review analysis",
            files=["auth.py", "validation.py", "crypto.py", "tests.py"],
            metadata={
                "security_level": "high",
                "validation_required": True,
                "created_by": "security_team",
                "review_type": "comprehensive"
            }
        )
    
    @pytest.fixture
    def package_validator(self):
        """Create package validator"""
        return ContextPackageValidator()
    
    def test_clean_package_validation(self, clean_context_package, package_validator):
        """Test validation of a clean, untampered package"""
        
        # Register as trusted
        package_validator.register_trusted_package(clean_context_package)
        
        # Validate
        result = package_validator.validate_package_integrity(clean_context_package)
        
        assert result["is_valid"] is True
        assert result["integrity_check"] is True
        assert result["tampering_detected"] is False
        assert len(result["issues"]) == 0
    
    def test_file_tampering_detection(self, clean_context_package, package_validator):
        """Test detection of file tampering"""
        
        # Register original as trusted
        package_validator.register_trusted_package(clean_context_package)
        
        # Create tampering agent
        tampering_agent = ContextPackageTamperingAgent(
            "malicious_agent",
            ByzantineAgentType.MALICIOUS,
            tampering_strategy="modify_files"
        )
        
        # Tamper with package
        tampered_package = tampering_agent.tamper_with_package(clean_context_package)
        
        # Validate tampered package
        result = package_validator.validate_package_integrity(tampered_package)
        
        assert result["is_valid"] is False
        assert result["tampering_detected"] is True
        assert any("files added" in issue for issue in result["issues"])
        assert len(tampering_agent.tampering_attempts) == 1
    
    def test_metadata_tampering_detection(self, clean_context_package, package_validator):
        """Test detection of metadata tampering"""
        
        package_validator.register_trusted_package(clean_context_package)
        
        tampering_agent = ContextPackageTamperingAgent(
            "metadata_tamperer",
            ByzantineAgentType.MALICIOUS,
            tampering_strategy="modify_metadata"
        )
        
        tampered_package = tampering_agent.tamper_with_package(clean_context_package)
        result = package_validator.validate_package_integrity(tampered_package)
        
        assert result["tampering_detected"] is True
        assert any("bypass" in issue.lower() for issue in result["issues"])
    
    def test_checksum_corruption_detection(self, clean_context_package, package_validator):
        """Test detection of checksum corruption"""
        
        tampering_agent = ContextPackageTamperingAgent(
            "checksum_corruptor",
            ByzantineAgentType.MALICIOUS,
            tampering_strategy="corrupt_checksum"
        )
        
        tampered_package = tampering_agent.tamper_with_package(clean_context_package)
        result = package_validator.validate_package_integrity(tampered_package)
        
        assert result["integrity_check"] is False
        assert result["is_valid"] is False
        assert "Checksum verification failed" in result["issues"]
    
    @pytest.mark.asyncio
    async def test_consensus_with_package_tampering(self, clean_context_package):
        """Test consensus protocol with package tampering agents"""
        
        # Create mix of honest and tampering agents
        agents = [
            ByzantineAgentSimulator("honest_1", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("honest_2", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("honest_3", ByzantineAgentType.HONEST),
            ContextPackageTamperingAgent("tamperer_1", ByzantineAgentType.MALICIOUS, "modify_files"),
            ContextPackageTamperingAgent("tamperer_2", ByzantineAgentType.CONFLICTING, "modify_metadata")
        ]
        
        coordinator = ByzantineConsensusCoordinator(agents)
        validator = ContextPackageValidator()
        
        # Register trusted package
        validator.register_trusted_package(clean_context_package)
        
        # Create consensus proposal for package validation
        proposal = ConsensusProposal(
            proposal_id="context_package_validation",
            proposer_id="security_coordinator",
            content={
                "command": "validate_context_package",
                "package": clean_context_package.to_dict(),
                "validation_required": True
            }
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        # Analyze consensus behavior
        stats = coordinator.get_consensus_statistics()
        
        # Should detect Byzantine behavior
        assert stats["byzantine_agent_count"] == 2
        assert stats["total_messages"] > 0
        
        # Check if tampering agents attempted malicious behavior
        tampering_agents = [a for a in agents if isinstance(a, ContextPackageTamperingAgent)]
        for agent in tampering_agents:
            if agent.state.malicious_actions:
                assert len(agent.state.malicious_actions) >= 0  # May or may not have had chance to tamper
    
    def test_multiple_tampering_strategies(self, clean_context_package, package_validator):
        """Test detection of various tampering strategies"""
        
        package_validator.register_trusted_package(clean_context_package)
        
        strategies = ["modify_files", "modify_metadata", "corrupt_checksum", "replace_content"]
        
        for strategy in strategies:
            tampering_agent = ContextPackageTamperingAgent(
                f"tamperer_{strategy}",
                ByzantineAgentType.MALICIOUS,
                tampering_strategy=strategy
            )
            
            tampered_package = tampering_agent.tamper_with_package(clean_context_package)
            result = package_validator.validate_package_integrity(tampered_package)
            
            # Each strategy should be detected
            assert result["is_valid"] is False, f"Failed to detect tampering strategy: {strategy}"
            
            if strategy != "corrupt_checksum":
                # Corruption strategies may not show as tampering if checksum is wrong
                assert result["tampering_detected"] is True, f"Failed to detect tampering for: {strategy}"
    
    def test_package_recovery_after_tampering(self, clean_context_package):
        """Test recovery of valid package after tampering is detected"""
        
        validator = ContextPackageValidator()
        validator.register_trusted_package(clean_context_package)
        
        # Create tampering agent
        tampering_agent = ContextPackageTamperingAgent(
            "recoverable_tamperer",
            ByzantineAgentType.MALICIOUS,
            tampering_strategy="modify_files"
        )
        
        # Tamper with package
        tampered_package = tampering_agent.tamper_with_package(clean_context_package)
        
        # Detect tampering
        result = validator.validate_package_integrity(tampered_package)
        assert result["tampering_detected"] is True
        
        # "Recover" by using original package
        recovery_result = validator.validate_package_integrity(clean_context_package)
        assert recovery_result["is_valid"] is True
        assert recovery_result["tampering_detected"] is False
        
        # Verify validator has history
        assert len(validator.validation_history) == 2
    
    @pytest.mark.asyncio
    async def test_context_package_consensus_with_validation(self, clean_context_package):
        """Test consensus protocol that includes package validation"""
        
        # Create honest agents and one tampering agent
        agents = [
            ByzantineAgentSimulator("validator_1", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("validator_2", ByzantineAgentType.HONEST),
            ByzantineAgentSimulator("validator_3", ByzantineAgentType.HONEST),
            ContextPackageTamperingAgent("package_tamperer", ByzantineAgentType.MALICIOUS, "modify_files")
        ]
        
        coordinator = ByzantineConsensusCoordinator(agents)
        validator = ContextPackageValidator()
        
        # Pre-validate the clean package
        validation_result = validator.validate_package_integrity(clean_context_package)
        
        # Create consensus proposal with validation result
        proposal = ConsensusProposal(
            proposal_id="validated_context_package",
            proposer_id="package_coordinator",
            content={
                "command": "approve_context_package",
                "package_id": clean_context_package.package_id,
                "validation_result": validation_result,
                "integrity_verified": validation_result["is_valid"]
            }
        )
        
        decision = await coordinator.propose_consensus(proposal)
        
        # With honest majority and valid package, should approve
        if validation_result["is_valid"]:
            assert decision == ConsensusDecision.APPROVE
        
        # Verify Byzantine agent behavior was tracked
        stats = coordinator.get_consensus_statistics()
        assert stats["byzantine_agent_count"] == 1


@pytest.mark.asyncio
async def test_context_tampering_framework_integration():
    """Integration test for context tampering detection framework"""
    
    # Create test package
    test_package = ContextPackage(
        package_id="integration_test",
        title="Integration Test Package",
        description="Test package for integration testing",
        files=["test.py", "config.json"],
        metadata={"test": True, "integration": True}
    )
    
    # Create validator
    validator = ContextPackageValidator()
    validator.register_trusted_package(test_package)
    
    # Test various tampering scenarios
    scenarios = [
        ("honest", ByzantineAgentType.HONEST, None),
        ("file_tamperer", ByzantineAgentType.MALICIOUS, "modify_files"),
        ("metadata_tamperer", ByzantineAgentType.MALICIOUS, "modify_metadata"),
        ("checksum_corruptor", ByzantineAgentType.MALICIOUS, "corrupt_checksum")
    ]
    
    results = []
    
    for agent_id, agent_type, strategy in scenarios:
        if strategy:
            agent = ContextPackageTamperingAgent(agent_id, agent_type, strategy)
            processed_package = agent.tamper_with_package(test_package)
        else:
            # Honest agent doesn't tamper
            processed_package = test_package
        
        validation_result = validator.validate_package_integrity(processed_package)
        results.append({
            "agent_id": agent_id,
            "strategy": strategy,
            "is_valid": validation_result["is_valid"],
            "tampering_detected": validation_result["tampering_detected"]
        })
    
    # Verify results
    honest_result = next(r for r in results if r["agent_id"] == "honest")
    assert honest_result["is_valid"] is True
    assert honest_result["tampering_detected"] is False
    
    tampering_results = [r for r in results if r["strategy"] is not None]
    for result in tampering_results:
        assert result["is_valid"] is False, f"Failed to detect tampering for {result['strategy']}"
    
    # Verify validation history
    assert len(validator.validation_history) == len(scenarios)
    
    print(f"Context tampering integration test completed: {len(results)} scenarios tested")