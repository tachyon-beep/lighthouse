"""
Comprehensive Threat Modeling Framework

Advanced threat modeling and attack surface analysis for the Lighthouse
multi-agent coordination system as required by Plan Charlie Phase 1.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
import uuid

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Threat severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AttackVector(Enum):
    """Common attack vectors in multi-agent systems."""
    NETWORK = "network"
    LOCAL_ACCESS = "local_access"
    INSIDER_THREAT = "insider_threat"
    SUPPLY_CHAIN = "supply_chain"
    SOCIAL_ENGINEERING = "social_engineering"
    MALICIOUS_AGENT = "malicious_agent"
    RACE_CONDITION = "race_condition"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    DENIAL_OF_SERVICE = "denial_of_service"


class AssetType(Enum):
    """Types of assets in the Lighthouse system."""
    EVENT_STORE = "event_store"
    FUSE_FILESYSTEM = "fuse_filesystem"  
    EXPERT_COORDINATION = "expert_coordination"
    AUTHENTICATION_SYSTEM = "authentication_system"
    VALIDATION_ENGINE = "validation_engine"
    API_ENDPOINTS = "api_endpoints"
    SECRET_MANAGEMENT = "secret_management"
    AGENT_COMMUNICATION = "agent_communication"
    PROJECT_DATA = "project_data"
    CONFIGURATION = "configuration"


@dataclass
class Asset:
    """System asset for threat modeling."""
    asset_id: str
    name: str
    asset_type: AssetType
    description: str
    criticality: ThreatLevel
    access_patterns: List[str] = field(default_factory=list)
    data_classification: str = "internal"
    dependencies: List[str] = field(default_factory=list)
    trust_boundaries: List[str] = field(default_factory=list)


@dataclass
class ThreatActor:
    """Potential threat actor."""
    actor_id: str
    name: str
    motivation: str
    capability_level: ThreatLevel
    access_level: str  # external, insider, privileged
    typical_attack_vectors: List[AttackVector] = field(default_factory=list)
    known_tactics: List[str] = field(default_factory=list)


@dataclass
class Threat:
    """Identified threat."""
    threat_id: str
    title: str
    description: str
    threat_level: ThreatLevel
    attack_vector: AttackVector
    affected_assets: List[str] = field(default_factory=list)
    threat_actors: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    attack_steps: List[str] = field(default_factory=list)
    impact_description: str = ""
    likelihood_score: int = 1  # 1-5 scale
    impact_score: int = 1  # 1-5 scale
    
    @property
    def risk_score(self) -> int:
        """Calculate risk score (likelihood × impact)."""
        return self.likelihood_score * self.impact_score


@dataclass
class SecurityControl:
    """Security control/mitigation."""
    control_id: str
    name: str
    description: str
    control_type: str  # preventive, detective, corrective
    implementation_status: str  # planned, implemented, verified
    effectiveness_rating: int = 1  # 1-5 scale
    mitigates_threats: List[str] = field(default_factory=list)
    cost_complexity: str = "medium"  # low, medium, high
    maintenance_burden: str = "medium"
    
    
@dataclass
class AttackPath:
    """Attack path through the system."""
    path_id: str
    name: str
    description: str
    start_point: str
    target_asset: str
    attack_steps: List[Dict[str, Any]] = field(default_factory=list)
    required_privileges: List[str] = field(default_factory=list)
    detection_points: List[str] = field(default_factory=list)
    overall_difficulty: ThreatLevel = ThreatLevel.MEDIUM


class ThreatModel:
    """Complete threat model for Lighthouse system."""
    
    def __init__(self, system_name: str = "Lighthouse Multi-Agent System"):
        """Initialize threat model."""
        self.system_name = system_name
        self.model_id = str(uuid.uuid4())
        self.created_at = datetime.utcnow()
        self.last_updated = datetime.utcnow()
        self.version = "1.0"
        
        # Model components
        self.assets: Dict[str, Asset] = {}
        self.threat_actors: Dict[str, ThreatActor] = {}
        self.threats: Dict[str, Threat] = {}
        self.security_controls: Dict[str, SecurityControl] = {}
        self.attack_paths: Dict[str, AttackPath] = {}
        
        # Analysis results
        self.risk_matrix: Dict[str, List[str]] = {}
        self.coverage_analysis: Dict[str, Any] = {}
        
        # Initialize with default Lighthouse components
        self._initialize_lighthouse_assets()
        self._initialize_threat_actors()
        self._initialize_lighthouse_threats()
        self._initialize_security_controls()
    
    def _initialize_lighthouse_assets(self):
        """Initialize Lighthouse system assets."""
        assets = [
            Asset(
                asset_id="event_store",
                name="Event Store",
                asset_type=AssetType.EVENT_STORE,
                description="Core event sourcing system storing all system events",
                criticality=ThreatLevel.CRITICAL,
                access_patterns=["agent_writes", "bridge_reads", "audit_queries"],
                data_classification="confidential",
                trust_boundaries=["authentication_required", "authorization_enforced"]
            ),
            Asset(
                asset_id="fuse_filesystem",
                name="FUSE Filesystem",
                asset_type=AssetType.FUSE_FILESYSTEM,
                description="Virtual filesystem for expert agent integration",
                criticality=ThreatLevel.HIGH,
                access_patterns=["expert_agent_access", "unix_tools", "concurrent_operations"],
                data_classification="internal",
                trust_boundaries=["agent_authentication", "path_validation"]
            ),
            Asset(
                asset_id="expert_coordination",
                name="Expert Coordination System",
                asset_type=AssetType.EXPERT_COORDINATION,
                description="Multi-expert consensus and coordination",
                criticality=ThreatLevel.HIGH,
                access_patterns=["expert_registration", "consensus_voting", "communication"],
                data_classification="internal",
                trust_boundaries=["expert_authentication", "consensus_validation"]
            ),
            Asset(
                asset_id="authentication_system",
                name="Authentication System",
                asset_type=AssetType.AUTHENTICATION_SYSTEM,
                description="HMAC-based agent authentication and session management",
                criticality=ThreatLevel.CRITICAL,
                access_patterns=["agent_login", "token_validation", "session_management"],
                data_classification="secret",
                trust_boundaries=["cryptographic_validation", "session_isolation"]
            ),
            Asset(
                asset_id="validation_engine",
                name="Command Validation Engine",
                asset_type=AssetType.VALIDATION_ENGINE,
                description="Speed layer validation with policy engine",
                criticality=ThreatLevel.HIGH,
                access_patterns=["command_validation", "policy_evaluation", "caching"],
                data_classification="internal",
                trust_boundaries=["input_validation", "policy_enforcement"]
            ),
            Asset(
                asset_id="api_endpoints",
                name="HTTP API Endpoints",
                asset_type=AssetType.API_ENDPOINTS,
                description="REST API for event store and system operations",
                criticality=ThreatLevel.MEDIUM,
                access_patterns=["http_requests", "websocket_connections", "api_calls"],
                data_classification="internal",
                trust_boundaries=["rate_limiting", "authentication_headers"]
            )
        ]
        
        for asset in assets:
            self.assets[asset.asset_id] = asset
    
    def _initialize_threat_actors(self):
        """Initialize threat actor profiles."""
        actors = [
            ThreatActor(
                actor_id="malicious_expert",
                name="Malicious Expert Agent",
                motivation="System compromise, data exfiltration, disruption",
                capability_level=ThreatLevel.HIGH,
                access_level="authenticated",
                typical_attack_vectors=[
                    AttackVector.MALICIOUS_AGENT,
                    AttackVector.INSIDER_THREAT,
                    AttackVector.RACE_CONDITION,
                    AttackVector.PRIVILEGE_ESCALATION
                ],
                known_tactics=[
                    "consensus_manipulation",
                    "byzantine_behavior",
                    "race_condition_exploitation",
                    "session_hijacking"
                ]
            ),
            ThreatActor(
                actor_id="external_attacker",
                name="External Network Attacker",
                motivation="Unauthorized access, data theft, system disruption",
                capability_level=ThreatLevel.MEDIUM,
                access_level="external",
                typical_attack_vectors=[
                    AttackVector.NETWORK,
                    AttackVector.DENIAL_OF_SERVICE,
                    AttackVector.SOCIAL_ENGINEERING
                ],
                known_tactics=[
                    "network_scanning",
                    "credential_stuffing",
                    "api_abuse",
                    "ddos_attacks"
                ]
            ),
            ThreatActor(
                actor_id="supply_chain_attacker",
                name="Supply Chain Attacker",
                motivation="Backdoor installation, persistent access",
                capability_level=ThreatLevel.HIGH,
                access_level="privileged",
                typical_attack_vectors=[
                    AttackVector.SUPPLY_CHAIN,
                    AttackVector.INSIDER_THREAT
                ],
                known_tactics=[
                    "dependency_poisoning",
                    "build_system_compromise",
                    "code_injection"
                ]
            ),
            ThreatActor(
                actor_id="insider_threat",
                name="Malicious Insider",
                motivation="Data theft, system sabotage, unauthorized access",
                capability_level=ThreatLevel.MEDIUM,
                access_level="privileged",
                typical_attack_vectors=[
                    AttackVector.INSIDER_THREAT,
                    AttackVector.LOCAL_ACCESS,
                    AttackVector.PRIVILEGE_ESCALATION
                ],
                known_tactics=[
                    "privilege_abuse",
                    "data_exfiltration",
                    "audit_log_tampering",
                    "configuration_manipulation"
                ]
            )
        ]
        
        for actor in actors:
            self.threat_actors[actor.actor_id] = actor
    
    def _initialize_lighthouse_threats(self):
        """Initialize Lighthouse-specific threats."""
        threats = [
            # Multi-Agent Coordination Threats
            Threat(
                threat_id="T001",
                title="Byzantine Agent Attack",
                description="Malicious expert agent provides false validation decisions to compromise consensus",
                threat_level=ThreatLevel.CRITICAL,
                attack_vector=AttackVector.MALICIOUS_AGENT,
                affected_assets=["expert_coordination", "validation_engine"],
                threat_actors=["malicious_expert"],
                preconditions=["Agent authentication", "Expert registration"],
                attack_steps=[
                    "Authenticate as legitimate expert agent",
                    "Participate in consensus voting",
                    "Provide consistently malicious validation decisions", 
                    "Attempt to sway consensus toward dangerous commands",
                    "Coordinate with other compromised agents if available"
                ],
                impact_description="Could lead to execution of dangerous commands, system compromise",
                likelihood_score=3,
                impact_score=5
            ),
            
            Threat(
                threat_id="T002", 
                title="FUSE Race Condition Exploitation",
                description="Attacker exploits race conditions in concurrent FUSE operations",
                threat_level=ThreatLevel.HIGH,
                attack_vector=AttackVector.RACE_CONDITION,
                affected_assets=["fuse_filesystem", "project_data"],
                threat_actors=["malicious_expert"],
                preconditions=["FUSE mount access", "Concurrent operation capability"],
                attack_steps=[
                    "Initiate multiple concurrent file operations",
                    "Exploit timing windows in file state checks",
                    "Corrupt file contents or metadata",
                    "Bypass access controls through state inconsistency"
                ],
                impact_description="Data corruption, unauthorized file access, system instability",
                likelihood_score=4,
                impact_score=4
            ),
            
            Threat(
                threat_id="T003",
                title="Authentication Token Replay Attack",
                description="Attacker captures and replays authentication tokens",
                threat_level=ThreatLevel.HIGH,
                attack_vector=AttackVector.NETWORK,
                affected_assets=["authentication_system"],
                threat_actors=["external_attacker", "malicious_expert"],
                preconditions=["Network access", "Token interception capability"],
                attack_steps=[
                    "Intercept authentication tokens via network sniffing",
                    "Analyze token structure and timing",
                    "Replay tokens within validity window",
                    "Establish unauthorized session"
                ],
                impact_description="Unauthorized system access, session hijacking",
                likelihood_score=2,
                impact_score=4
            ),
            
            Threat(
                threat_id="T004",
                title="Path Traversal Attack",
                description="Attacker uses directory traversal to access unauthorized files",
                threat_level=ThreatLevel.HIGH,
                attack_vector=AttackVector.LOCAL_ACCESS,
                affected_assets=["fuse_filesystem", "project_data", "configuration"],
                threat_actors=["malicious_expert", "external_attacker"],
                preconditions=["File system access", "Path manipulation capability"],
                attack_steps=[
                    "Identify file path input points",
                    "Craft malicious paths with traversal sequences (../)",
                    "Attempt to access system files or configuration",
                    "Exfiltrate sensitive data or modify critical files"
                ],
                impact_description="Unauthorized file access, configuration tampering, data theft",
                likelihood_score=3,
                impact_score=4
            ),
            
            Threat(
                threat_id="T005",
                title="DoS via Resource Exhaustion",
                description="Attacker overwhelms system resources through excessive requests",
                threat_level=ThreatLevel.MEDIUM,
                attack_vector=AttackVector.DENIAL_OF_SERVICE,
                affected_assets=["api_endpoints", "validation_engine", "event_store"],
                threat_actors=["external_attacker", "malicious_expert"],
                preconditions=["Network access or agent authentication"],
                attack_steps=[
                    "Generate high volume of requests",
                    "Target resource-intensive operations",
                    "Exhaust system memory, CPU, or disk",
                    "Cause system unavailability"
                ],
                impact_description="System unavailability, performance degradation",
                likelihood_score=4,
                impact_score=3
            ),
            
            Threat(
                threat_id="T006",
                title="Event Store Tampering",
                description="Attacker modifies event store data to hide malicious activity",
                threat_level=ThreatLevel.CRITICAL,
                attack_vector=AttackVector.INSIDER_THREAT,
                affected_assets=["event_store"],
                threat_actors=["insider_threat", "malicious_expert"],
                preconditions=["Database access", "Elevated privileges"],
                attack_steps=[
                    "Gain privileged access to event store",
                    "Identify audit events to hide",
                    "Modify or delete events from store",
                    "Update checksums or integrity controls"
                ],
                impact_description="Loss of audit trail, undetected malicious activity",
                likelihood_score=2,
                impact_score=5
            ),
            
            Threat(
                threat_id="T007",
                title="Expert Agent Impersonation", 
                description="Attacker impersonates legitimate expert agent",
                threat_level=ThreatLevel.HIGH,
                attack_vector=AttackVector.MALICIOUS_AGENT,
                affected_assets=["expert_coordination", "authentication_system"],
                threat_actors=["external_attacker", "malicious_expert"],
                preconditions=["Compromised credentials", "Agent registration process knowledge"],
                attack_steps=[
                    "Obtain legitimate agent credentials",
                    "Register as trusted expert agent",
                    "Participate in consensus decisions",
                    "Provide malicious recommendations"
                ],
                impact_description="Compromised decision making, system integrity loss",
                likelihood_score=3,
                impact_score=4
            ),
            
            Threat(
                threat_id="T008",
                title="Validation Cache Poisoning",
                description="Attacker poisons validation cache with malicious results",
                threat_level=ThreatLevel.MEDIUM,
                attack_vector=AttackVector.MALICIOUS_AGENT,
                affected_assets=["validation_engine"],
                threat_actors=["malicious_expert"],
                preconditions=["Expert agent privileges", "Cache write access"],
                attack_steps=[
                    "Identify cacheable validation patterns",
                    "Provide malicious validation results",
                    "Populate cache with dangerous approvals",
                    "Wait for cache hits on malicious content"
                ],
                impact_description="Bypass of validation controls, dangerous command approval",
                likelihood_score=3,
                impact_score=3
            )
        ]
        
        for threat in threats:
            self.threats[threat.threat_id] = threat
    
    def _initialize_security_controls(self):
        """Initialize security controls and mitigations."""
        controls = [
            SecurityControl(
                control_id="C001",
                name="Cryptographic Authentication Tokens",
                description="HMAC-based authentication with nonce and replay protection",
                control_type="preventive",
                implementation_status="implemented",
                effectiveness_rating=4,
                mitigates_threats=["T003"],
                cost_complexity="low"
            ),
            
            SecurityControl(
                control_id="C002", 
                name="Path Validation with Real Path Resolution",
                description="OS-level path resolution and containment checking",
                control_type="preventive",
                implementation_status="implemented",
                effectiveness_rating=5,
                mitigates_threats=["T004"],
                cost_complexity="low"
            ),
            
            SecurityControl(
                control_id="C003",
                name="Multi-Layer Rate Limiting",
                description="DoS protection with burst detection and adaptive limits",
                control_type="preventive",
                implementation_status="implemented", 
                effectiveness_rating=4,
                mitigates_threats=["T005"],
                cost_complexity="medium"
            ),
            
            SecurityControl(
                control_id="C004",
                name="FUSE Race Condition Prevention",
                description="Atomic operations with state validation and locking",
                control_type="preventive",
                implementation_status="implemented",
                effectiveness_rating=4,
                mitigates_threats=["T002"],
                cost_complexity="medium"
            ),
            
            SecurityControl(
                control_id="C005",
                name="Byzantine Fault Tolerance",
                description="Multi-expert consensus with malicious agent detection",
                control_type="detective",
                implementation_status="planned",
                effectiveness_rating=4,
                mitigates_threats=["T001", "T007"],
                cost_complexity="high"
            ),
            
            SecurityControl(
                control_id="C006",
                name="Event Store Integrity Monitoring",
                description="Cryptographic integrity checks and tamper detection",
                control_type="detective",
                implementation_status="planned",
                effectiveness_rating=5,
                mitigates_threats=["T006"],
                cost_complexity="medium"
            ),
            
            SecurityControl(
                control_id="C007",
                name="Validation Cache Integrity",
                description="Cache poisoning detection and validation result verification",
                control_type="detective",
                implementation_status="planned",
                effectiveness_rating=3,
                mitigates_threats=["T008"],
                cost_complexity="medium"
            ),
            
            SecurityControl(
                control_id="C008",
                name="Agent Behavior Analytics",
                description="ML-based detection of anomalous agent behavior patterns",
                control_type="detective",
                implementation_status="planned",
                effectiveness_rating=4,
                mitigates_threats=["T001", "T007", "T008"],
                cost_complexity="high"
            ),
            
            SecurityControl(
                control_id="C009",
                name="Comprehensive Audit Logging",
                description="Immutable audit logs with integrity protection",
                control_type="detective",
                implementation_status="implemented",
                effectiveness_rating=5,
                mitigates_threats=["T001", "T006", "T007"],
                cost_complexity="low"
            ),
            
            SecurityControl(
                control_id="C010",
                name="Network Segmentation",
                description="Network isolation and micro-segmentation of system components",
                control_type="preventive",
                implementation_status="planned",
                effectiveness_rating=4,
                mitigates_threats=["T003", "T005"],
                cost_complexity="high"
            )
        ]
        
        for control in controls:
            self.security_controls[control.control_id] = control
    
    def add_threat(self, threat: Threat) -> None:
        """Add a new threat to the model."""
        self.threats[threat.threat_id] = threat
        self.last_updated = datetime.utcnow()
    
    def add_security_control(self, control: SecurityControl) -> None:
        """Add a new security control to the model."""
        self.security_controls[control.control_id] = control
        self.last_updated = datetime.utcnow()
    
    def calculate_risk_matrix(self) -> Dict[str, List[str]]:
        """Calculate risk matrix by threat level."""
        risk_matrix = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": []
        }
        
        for threat in self.threats.values():
            # Calculate residual risk after controls
            mitigated = any(
                threat.threat_id in control.mitigates_threats
                and control.implementation_status == "implemented"
                for control in self.security_controls.values()
            )
            
            if mitigated:
                # Reduce risk level if mitigated
                if threat.threat_level == ThreatLevel.CRITICAL:
                    risk_level = "high"
                elif threat.threat_level == ThreatLevel.HIGH:
                    risk_level = "medium"
                else:
                    risk_level = "low"
            else:
                risk_level = threat.threat_level.value
            
            risk_matrix[risk_level].append(threat.threat_id)
        
        self.risk_matrix = risk_matrix
        return risk_matrix
    
    def analyze_coverage(self) -> Dict[str, Any]:
        """Analyze security control coverage."""
        total_threats = len(self.threats)
        covered_threats = set()
        
        implemented_controls = sum(
            1 for control in self.security_controls.values()
            if control.implementation_status == "implemented"
        )
        
        for control in self.security_controls.values():
            if control.implementation_status == "implemented":
                covered_threats.update(control.mitigates_threats)
        
        coverage_percentage = len(covered_threats) / max(1, total_threats) * 100
        
        self.coverage_analysis = {
            "total_threats": total_threats,
            "covered_threats": len(covered_threats),
            "coverage_percentage": coverage_percentage,
            "implemented_controls": implemented_controls,
            "total_controls": len(self.security_controls),
            "uncovered_threats": [
                threat_id for threat_id in self.threats.keys()
                if threat_id not in covered_threats
            ]
        }
        
        return self.coverage_analysis
    
    def generate_attack_paths(self) -> List[AttackPath]:
        """Generate potential attack paths through the system."""
        attack_paths = []
        
        # Example: External attacker to event store compromise
        external_to_eventstore = AttackPath(
            path_id="AP001",
            name="External Network Attack to Event Store Compromise",
            description="External attacker compromises authentication and accesses event store",
            start_point="external_network",
            target_asset="event_store",
            attack_steps=[
                {
                    "step": 1,
                    "description": "Network reconnaissance and service discovery",
                    "techniques": ["port_scanning", "service_enumeration"],
                    "assets_affected": ["api_endpoints"]
                },
                {
                    "step": 2, 
                    "description": "Authentication bypass or credential compromise",
                    "techniques": ["token_replay", "credential_stuffing"],
                    "assets_affected": ["authentication_system"]
                },
                {
                    "step": 3,
                    "description": "Privilege escalation through validation bypass",
                    "techniques": ["cache_poisoning", "consensus_manipulation"],
                    "assets_affected": ["validation_engine", "expert_coordination"]
                },
                {
                    "step": 4,
                    "description": "Event store access and tampering",
                    "techniques": ["audit_log_modification", "event_injection"],
                    "assets_affected": ["event_store"]
                }
            ],
            required_privileges=["network_access", "authentication_bypass"],
            detection_points=["rate_limiting", "authentication_monitoring", "audit_log_analysis"],
            overall_difficulty=ThreatLevel.HIGH
        )
        
        attack_paths.append(external_to_eventstore)
        
        # Example: Malicious insider attack path
        insider_attack = AttackPath(
            path_id="AP002", 
            name="Malicious Insider Data Exfiltration",
            description="Insider with legitimate access exfiltrates project data",
            start_point="authenticated_agent",
            target_asset="project_data",
            attack_steps=[
                {
                    "step": 1,
                    "description": "Use legitimate credentials to establish session",
                    "techniques": ["normal_authentication"],
                    "assets_affected": ["authentication_system"]
                },
                {
                    "step": 2,
                    "description": "Access FUSE filesystem with expanded permissions",
                    "techniques": ["permission_enumeration", "path_traversal"],
                    "assets_affected": ["fuse_filesystem"]
                },
                {
                    "step": 3,
                    "description": "Bulk data extraction through legitimate operations",
                    "techniques": ["data_aggregation", "covert_channels"],
                    "assets_affected": ["project_data"]
                },
                {
                    "step": 4,
                    "description": "Cover tracks by modifying audit logs",
                    "techniques": ["log_tampering", "event_deletion"],
                    "assets_affected": ["event_store"]
                }
            ],
            required_privileges=["authenticated_access", "insider_knowledge"],
            detection_points=["behavioral_analytics", "data_loss_prevention", "audit_integrity_monitoring"],
            overall_difficulty=ThreatLevel.MEDIUM
        )
        
        attack_paths.append(insider_attack)
        
        self.attack_paths = {path.path_id: path for path in attack_paths}
        return attack_paths
    
    def export_model(self, format: str = "json") -> str:
        """Export threat model in specified format."""
        model_data = {
            "system_name": self.system_name,
            "model_id": self.model_id,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "assets": {aid: {
                "asset_id": a.asset_id,
                "name": a.name,
                "asset_type": a.asset_type.value,
                "description": a.description,
                "criticality": a.criticality.value,
                "access_patterns": a.access_patterns,
                "data_classification": a.data_classification,
                "trust_boundaries": a.trust_boundaries
            } for aid, a in self.assets.items()},
            "threat_actors": {tid: {
                "actor_id": ta.actor_id,
                "name": ta.name,
                "motivation": ta.motivation,
                "capability_level": ta.capability_level.value,
                "access_level": ta.access_level,
                "typical_attack_vectors": [av.value for av in ta.typical_attack_vectors],
                "known_tactics": ta.known_tactics
            } for tid, ta in self.threat_actors.items()},
            "threats": {tid: {
                "threat_id": t.threat_id,
                "title": t.title,
                "description": t.description,
                "threat_level": t.threat_level.value,
                "attack_vector": t.attack_vector.value,
                "affected_assets": t.affected_assets,
                "threat_actors": t.threat_actors,
                "preconditions": t.preconditions,
                "attack_steps": t.attack_steps,
                "impact_description": t.impact_description,
                "likelihood_score": t.likelihood_score,
                "impact_score": t.impact_score,
                "risk_score": t.risk_score
            } for tid, t in self.threats.items()},
            "security_controls": {cid: {
                "control_id": c.control_id,
                "name": c.name,
                "description": c.description,
                "control_type": c.control_type,
                "implementation_status": c.implementation_status,
                "effectiveness_rating": c.effectiveness_rating,
                "mitigates_threats": c.mitigates_threats,
                "cost_complexity": c.cost_complexity,
                "maintenance_burden": c.maintenance_burden
            } for cid, c in self.security_controls.items()},
            "risk_matrix": self.risk_matrix,
            "coverage_analysis": self.coverage_analysis,
            "attack_paths": {pid: {
                "path_id": ap.path_id,
                "name": ap.name,
                "description": ap.description,
                "start_point": ap.start_point,
                "target_asset": ap.target_asset,
                "attack_steps": ap.attack_steps,
                "required_privileges": ap.required_privileges,
                "detection_points": ap.detection_points,
                "overall_difficulty": ap.overall_difficulty.value
            } for pid, ap in self.attack_paths.items()}
        }
        
        if format.lower() == "json":
            return json.dumps(model_data, indent=2, sort_keys=True)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def generate_report(self) -> str:
        """Generate human-readable threat model report."""
        self.calculate_risk_matrix()
        self.analyze_coverage()
        self.generate_attack_paths()
        
        report = [
            f"# Threat Model Report: {self.system_name}",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Model Version: {self.version}",
            "",
            "## Executive Summary",
            f"This threat model identifies {len(self.threats)} threats across {len(self.assets)} critical system assets.",
            f"Security control coverage: {self.coverage_analysis['coverage_percentage']:.1f}% ({self.coverage_analysis['covered_threats']}/{self.coverage_analysis['total_threats']} threats covered)",
            "",
            "## Risk Summary",
            f"Critical Risk Threats: {len(self.risk_matrix['critical'])}",
            f"High Risk Threats: {len(self.risk_matrix['high'])}",
            f"Medium Risk Threats: {len(self.risk_matrix['medium'])}",
            f"Low Risk Threats: {len(self.risk_matrix['low'])}",
            "",
            "## Top Threats by Risk Score",
        ]
        
        # Sort threats by risk score
        sorted_threats = sorted(self.threats.values(), key=lambda t: t.risk_score, reverse=True)
        
        for i, threat in enumerate(sorted_threats[:10]):  # Top 10
            report.append(f"{i+1}. **{threat.title}** (Risk Score: {threat.risk_score})")
            report.append(f"   - {threat.description}")
            report.append(f"   - Attack Vector: {threat.attack_vector.value}")
            report.append(f"   - Assets: {', '.join(threat.affected_assets)}")
            
            # Check if mitigated
            mitigating_controls = [
                control for control in self.security_controls.values()
                if threat.threat_id in control.mitigates_threats and
                control.implementation_status == "implemented"
            ]
            
            if mitigating_controls:
                report.append(f"   - Mitigations: {', '.join([c.name for c in mitigating_controls])}")
            else:
                report.append(f"   - ⚠️  **NO IMPLEMENTED MITIGATIONS**")
            
            report.append("")
        
        report.extend([
            "## Security Controls Status",
            f"Implemented: {len([c for c in self.security_controls.values() if c.implementation_status == 'implemented'])}",
            f"Planned: {len([c for c in self.security_controls.values() if c.implementation_status == 'planned'])}",
            "",
            "### Control Implementation Priority",
        ])
        
        # Priority controls (those that mitigate high-risk threats)
        high_risk_threats = [tid for tid in self.risk_matrix['critical'] + self.risk_matrix['high']]
        priority_controls = [
            control for control in self.security_controls.values()
            if any(tid in control.mitigates_threats for tid in high_risk_threats)
            and control.implementation_status == "planned"
        ]
        
        for control in sorted(priority_controls, key=lambda c: len(c.mitigates_threats), reverse=True):
            threat_count = len([tid for tid in control.mitigates_threats if tid in high_risk_threats])
            report.append(f"- **{control.name}** - Mitigates {threat_count} high-risk threats")
        
        return "\n".join(report)


# Global threat model instance
_global_threat_model: Optional[ThreatModel] = None


def get_threat_model() -> ThreatModel:
    """Get global threat model instance."""
    global _global_threat_model
    if _global_threat_model is None:
        _global_threat_model = ThreatModel()
    return _global_threat_model