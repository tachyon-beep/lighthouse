# Lighthouse: High-Level Design - Annex C

## Feature Pack 3: Agent Context Management System (ACMS)

### Executive Summary

The Agent Context Management System (ACMS) provides sophisticated context curation and management capabilities for multi-agent coordination. ACMS enables human operators and senior agents to manually craft "Context Packages" - curated collections of files, event history, architectural decisions, and domain knowledge that can be precisely injected into agent initialization. Unlike reactive context provision that responds to agent requests, ACMS is proactive context orchestration that ensures agents start with exactly the right foundational knowledge for their specific tasks.

**Critical Innovation**: ACMS transforms agent initialization from "blank slate" to "informed specialist" by providing rich, curated context packages that include not just code files, but the reasoning, history, and domain knowledge needed for intelligent decision-making.

### Motivation

During complex multi-agent development workflows, we've observed that agents often make suboptimal decisions not because of technical limitations, but because they lack crucial context that would guide better choices. Common scenarios include:

1. **Architecture Violations** - Agents adding features that conflict with established patterns because they weren't aware of the architectural principles
2. **Repeated Mistakes** - New agents making the same errors as previous agents because they don't know what was already tried and failed
3. **Missing Domain Knowledge** - Agents implementing technically correct but business-inappropriate solutions due to lack of domain context
4. **Inefficient Ramp-up** - Agents spending significant time discovering information that could have been provided upfront
5. **Inconsistent Standards** - Each agent developing their own approach instead of following established team conventions
6. **Lost Tribal Knowledge** - Critical insights and lessons learned not being transferred to new agents

ACMS addresses these issues by making context curation a first-class concern in multi-agent orchestration.

### Core Concepts

#### Context Package

A carefully curated collection of information designed to provide an agent with the precise knowledge needed for their task:

```yaml
ContextPackage:
  package_id: "ctx_security_review_v2.1"
  title: "Security Review Context for Event Store"
  description: "Complete context for security architects reviewing event store implementations"
  created_by: "senior_architect"
  created_at: "2025-08-24T15:00:00Z"
  version: "2.1"
  target_agent_types: ["security-architect", "security-auditor"]
  
  contents:
    architectural_context:
      - file: "/docs/architecture/ADR-002-EVENT_STORE_DATA_ARCHITECTURE.md"
        reason: "Understanding data flow and storage decisions"
        key_sections: ["Security Requirements", "Threat Model"]
      
      - file: "/docs/architecture/ADR-003-EVENT_STORE_SYSTEM_DESIGN.md"
        reason: "System-level security implications"
        key_sections: ["Authentication Mechanism", "Authorization Model"]
    
    implementation_context:
      - file: "/src/lighthouse/event_store/store.py"
        reason: "Core implementation with security controls"
        focus_areas: ["Authentication", "Input validation", "File operations"]
      
      - file: "/src/lighthouse/event_store/auth.py"
        reason: "Authentication and authorization system"
        focus_areas: ["Token validation", "Role permissions", "Rate limiting"]
    
    historical_context:
      event_range:
        from_sequence: 1450
        to_sequence: 1580
        filter:
          event_types: ["SECURITY_REVIEW_COMPLETED", "VULNERABILITY_FOUND", "SECURITY_DECISION_MADE"]
        reason: "Previous security review decisions and findings"
    
    threat_intelligence:
      - document: "OWASP_Event_Store_Checklist_2025.md"
        reason: "Current threat landscape for event stores"
      
      - document: "Previous_Security_Incidents_Sanitized.md"
        reason: "Lessons learned from past security issues"
    
    coding_standards:
      - file: "/docs/security/SECURE_CODING_GUIDELINES.md"
        reason: "Team security coding standards"
      
      - file: "/docs/security/SECURITY_REVIEW_CHECKLIST.md"
        reason: "Standard security review process"
    
    domain_knowledge:
      - document: "Multi_Agent_Security_Patterns.md"
        reason: "Specific security considerations for multi-agent systems"
      
      - document: "Event_Sourcing_Security_Best_Practices.md"
        reason: "Security patterns specific to event-sourced systems"
  
  packaging_metadata:
    size_estimate: "2.4MB compressed"
    preparation_time: "45 seconds"
    last_updated: "2025-08-24T15:00:00Z"
    usage_count: 23
    effectiveness_rating: 4.8
```

#### Context Package Templates

Reusable templates for common agent types and scenarios:

```yaml
ContextTemplate:
  template_id: "new_feature_developer"
  title: "New Feature Development Context Template"
  description: "Standard context for agents implementing new features"
  
  template_structure:
    always_include:
      - architecture_overview: "/docs/architecture/SYSTEM_OVERVIEW.md"
      - coding_standards: "/docs/development/CODING_STANDARDS.md"
      - testing_guidelines: "/docs/development/TESTING_GUIDELINES.md"
      - recent_changes: 
          event_filter: "last_30_days"
          event_types: ["FEATURE_COMPLETED", "ARCHITECTURE_DECISION", "BREAKING_CHANGE"]
    
    conditional_include:
      - if_database_changes:
          - "/docs/database/SCHEMA_MIGRATION_GUIDE.md"
          - "/docs/database/PERFORMANCE_CONSIDERATIONS.md"
      
      - if_api_changes:
          - "/docs/api/API_DESIGN_PRINCIPLES.md"
          - "/docs/api/VERSIONING_STRATEGY.md"
      
      - if_security_sensitive:
          - "/docs/security/SECURITY_REVIEW_PROCESS.md"
          - "/docs/security/THREAT_MODEL.md"
    
    dynamic_content:
      - related_features:
          query: "features similar to {{requested_feature}}"
          limit: 5
      
      - past_failures:
          query: "failed implementations of {{feature_category}}"
          limit: 3
          reason: "Learn from past mistakes"
```

#### Agent Context State

Tracking what context each agent has been provided:

```yaml
AgentContextState:
  agent_id: "security-architect-session-447"
  session_start: "2025-08-24T15:30:00Z"
  
  context_packages_loaded:
    - package_id: "ctx_security_review_v2.1"
      loaded_at: "2025-08-24T15:30:15Z"
      loading_duration: "3.2s"
      files_loaded: 12
      events_loaded: 47
      
    - package_id: "ctx_recent_changes_event_store"
      loaded_at: "2025-08-24T15:30:45Z" 
      loading_duration: "1.8s"
      files_loaded: 6
      events_loaded: 23
  
  ad_hoc_context_provided:
    - context_type: "file_access"
      item: "/src/lighthouse/event_store/validation.py"
      provided_at: "2025-08-24T15:45:22Z"
      reason: "Agent requested during security review"
    
    - context_type: "event_query"
      query: "events where event_type='SECURITY_VULNERABILITY_FOUND' last 90 days"
      results_count: 3
      provided_at: "2025-08-24T15:47:33Z"
  
  context_effectiveness:
    questions_asked: 12
    questions_could_be_answered_from_context: 10
    context_hit_rate: 0.83
    
  context_gaps_identified:
    - gap: "Multi-agent coordination security patterns"
      identified_at: "2025-08-24T15:52:14Z"
      agent_question: "How do other multi-agent systems handle agent impersonation?"
      
    - gap: "Performance impact of security controls"
      identified_at: "2025-08-24T16:05:33Z"
      agent_question: "What's the latency impact of HMAC verification?"
```

### Implementation Architecture

#### Context Package Storage

Context packages are stored as structured documents in the event store with specialized metadata:

```yaml
ContextPackageEvent:
  event_type: "CONTEXT_PACKAGE_CREATED"
  aggregate_id: "ctx_security_review_v2.1"
  
  data:
    package_definition:
      # Full package definition as shown above
      
    content_snapshots:
      # Immutable snapshots of all referenced files
      # at the time of package creation
      
    dependency_graph:
      # Which files depend on which other files
      # for intelligent partial updates
      
    validation_results:
      # Results of package validation (missing files, broken references, etc.)
```

#### Context Injection System

Smart context loading that optimizes for relevance and performance:

```python
class ContextInjectionEngine:
    async def prepare_agent_context(
        self, 
        agent_type: str,
        task_description: str,
        context_packages: List[str],
        optimization_preferences: ContextOptimization
    ) -> PreparedContext:
        """
        Intelligently prepare context for agent initialization.
        
        Optimization strategies:
        - Relevance scoring to prioritize most important content
        - Deduplication to avoid redundant information
        - Size optimization to fit within context limits
        - Freshness weighting to prioritize recent information
        """
        
    async def inject_context(
        self,
        agent_session: AgentSession,
        prepared_context: PreparedContext
    ) -> ContextInjectionResult:
        """
        Inject prepared context into agent session.
        
        Tracks:
        - What was provided
        - How long it took to load
        - Any errors or truncations
        - Agent's initial response to context
        """
```

#### Context Analytics

Understanding context effectiveness to improve future curation:

```yaml
ContextAnalytics:
  package_id: "ctx_security_review_v2.1"
  
  usage_statistics:
    total_uses: 47
    successful_task_completions: 42
    success_rate: 0.89
    average_task_completion_time: "24.3 minutes"
    
  content_utilization:
    - file: "/docs/architecture/ADR-002-EVENT_STORE_DATA_ARCHITECTURE.md"
      referenced_by_agents: 39
      utilization_rate: 0.83
      most_referenced_sections: ["Security Requirements", "Data Flow"]
      
    - file: "/src/lighthouse/event_store/validation.py"
      referenced_by_agents: 47
      utilization_rate: 1.0
      most_referenced_functions: ["validate_event", "validate_path"]
  
  common_context_gaps:
    - gap: "Performance implications of security decisions"
      frequency: 12
      suggested_addition: "/docs/performance/SECURITY_PERFORMANCE_IMPACT.md"
      
    - gap: "Integration testing of security controls"
      frequency: 8
      suggested_addition: "/tests/integration/security/"
  
  agent_feedback:
    - agent_type: "security-architect"
      feedback: "Excellent coverage of threat model, but missing performance impact analysis"
      rating: 4.2
      
    - agent_type: "security-auditor"
      feedback: "Complete context package, no gaps identified"
      rating: 4.9
```

### Advanced Features

#### Dynamic Context Generation

Context packages that update themselves based on system evolution:

```yaml
DynamicContextPackage:
  package_id: "ctx_current_architecture"
  title: "Live System Architecture Context"
  
  dynamic_rules:
    - content_type: "recent_architecture_decisions"
      rule: "Include all ADR documents modified in last 30 days"
      refresh_frequency: "daily"
      
    - content_type: "active_development_areas"
      rule: "Include files with >5 commits in last 2 weeks"
      refresh_frequency: "hourly"
      
    - content_type: "current_issues"
      rule: "Include GitHub issues labeled 'architecture' with activity in last 7 days"
      refresh_frequency: "hourly"
  
  content_policies:
    max_size: "5MB"
    staleness_threshold: "3 days"
    relevance_threshold: 0.7
```

#### Context Inheritance and Composition

Building complex context from simpler building blocks:

```yaml
CompositeContextPackage:
  package_id: "ctx_full_stack_developer"
  title: "Full Stack Development Context"
  
  base_packages:
    - package_id: "ctx_backend_development"
      weight: 0.6
      
    - package_id: "ctx_frontend_development" 
      weight: 0.3
      
    - package_id: "ctx_database_development"
      weight: 0.1
  
  composition_rules:
    deduplication_strategy: "prefer_higher_weight"
    conflict_resolution: "merge_with_annotation"
    size_limit: "8MB"
    
  customizations:
    additional_content:
      - "/docs/full_stack/INTEGRATION_PATTERNS.md"
      - "/docs/full_stack/END_TO_END_TESTING.md"
    
    content_exclusions:
      - "/docs/backend/BACKEND_ONLY_DEPLOYMENT.md"
      - "/docs/frontend/FRONTEND_ONLY_DEPLOYMENT.md"
```

#### Subagent Context Propagation (Future)

Long-term vision for tracking context through subagent hierarchies:

```yaml
SubagentContextPropagation:
  parent_agent: "system-architect"
  parent_context_packages: ["ctx_architecture_review", "ctx_system_design"]
  
  spawned_subagents:
    - subagent_id: "security-specialist-sub-1"
      inheritance_policy: "security_focused"
      inherited_context:
        - package_id: "ctx_architecture_review"
          sections: ["Security Architecture", "Threat Model"]
        - package_id: "ctx_system_design" 
          sections: ["Security Controls", "Authentication Design"]
      additional_context:
        - package_id: "ctx_security_deep_dive"
    
    - subagent_id: "performance-specialist-sub-1"
      inheritance_policy: "performance_focused"
      inherited_context:
        - package_id: "ctx_architecture_review"
          sections: ["Performance Requirements", "Scalability"]
        - package_id: "ctx_system_design"
          sections: ["Performance Architecture"]
      additional_context:
        - package_id: "ctx_performance_testing"
  
  context_lineage_tracking:
    # Track how context flows through the agent hierarchy
    # Enable "context provenance" - understanding where knowledge came from
    # Support "context debugging" - why did this subagent make this decision?
```

### Context Package Lifecycle

#### Creation and Curation

```yaml
ContextPackageLifecycle:
  creation:
    - trigger: "manual_creation"
      actors: ["senior_architect", "lead_developer", "domain_expert"]
      process:
        1. "Identify context need"
        2. "Curate content sources"
        3. "Validate completeness"
        4. "Test with pilot agents"
        5. "Publish and version"
    
    - trigger: "automatic_generation"
      based_on: "task_patterns"
      process:
        1. "Detect recurring agent questions"
        2. "Identify knowledge gaps"
        3. "Generate context package proposal"
        4. "Human review and approval"
        5. "Automated testing and deployment"
  
  maintenance:
    - scheduled_review: "monthly"
      activities: ["content_freshness_check", "usage_analytics_review", "gap_analysis"]
    
    - triggered_updates: 
      triggers: ["architecture_changes", "security_updates", "process_changes"]
      activities: ["impact_analysis", "content_update", "regression_testing"]
  
  deprecation:
    - criteria: ["low_usage", "outdated_content", "replaced_by_newer_package"]
    - process: ["deprecation_notice", "migration_guidance", "sunset_timeline"]
```

### Integration Points

#### Event Store Integration

Context packages leverage the event store for:

- **Versioning**: Each context package version is an immutable event
- **Audit Trail**: Complete history of what context was provided to which agents
- **Analytics**: Rich querying of context usage patterns
- **Distribution**: Efficient replication across distributed Lighthouse instances

#### Agent Initialization Integration

```python
# Enhanced agent initialization with context packages
@agent_task
async def security_review(
    context_packages=["ctx_security_review_v2.1", "ctx_recent_changes"],
    dynamic_context={"recent_security_events": "last_30_days"},
    task_description="Review event store security implementation"
):
    # Agent starts with rich, curated context
    # rather than discovering everything from scratch
    pass
```

#### Multi-Agent Coordination Integration

Context packages can be shared and coordinated across multiple agents:

```yaml
CoordinatedContextSession:
  session_id: "architecture_review_session_447"
  participants: ["system-architect", "security-architect", "performance-engineer"]
  
  shared_context:
    - package_id: "ctx_system_architecture_v3.1"
      shared_by: "all"
      
    - package_id: "ctx_security_requirements" 
      shared_by: ["system-architect", "security-architect"]
      
    - package_id: "ctx_performance_requirements"
      shared_by: ["system-architect", "performance-engineer"]
  
  context_synchronization:
    strategy: "eventual_consistency"
    sync_frequency: "real_time"
    conflict_resolution: "last_writer_wins_with_notification"
```

### Benefits and Impact

#### For Human Operators

1. **Precise Agent Control**: Exactly specify what knowledge agents should have
2. **Consistent Results**: Ensure all agents working on similar tasks have consistent context
3. **Knowledge Retention**: Capture and reuse tribal knowledge that would otherwise be lost
4. **Onboarding Acceleration**: New team members (human or AI) get comprehensive context instantly
5. **Quality Assurance**: Reduce variability in agent outputs through standardized context

#### For Agent Performance

1. **Faster Task Completion**: Agents start informed rather than discovering context
2. **Higher Quality Decisions**: Rich context leads to better-informed choices
3. **Reduced Back-and-Forth**: Less need to ask questions that could be answered upfront
4. **Pattern Recognition**: Access to historical context enables learning from past experiences
5. **Specialized Expertise**: Different agent types can have tailored context packages

#### For System Architecture

1. **Context as Code**: Version-controlled, testable context management
2. **Context Observability**: Full visibility into what context influences which decisions
3. **Context Evolution**: Understanding how context needs evolve over time
4. **Context Optimization**: Data-driven improvement of context package effectiveness
5. **Context Governance**: Policies and processes around context curation and access

### Future Extensions

#### Machine Learning-Enhanced Context Curation

- **Automatic Context Discovery**: ML models identify what context would be most valuable
- **Context Quality Prediction**: Predict which context packages will lead to successful task completion
- **Personalized Context**: Adapt context packages to individual agent strengths and preferences
- **Context Gap Detection**: Automatically identify when agents need additional context

#### Cross-System Context Integration

- **External Knowledge Bases**: Integration with wikis, documentation systems, and knowledge repositories
- **Real-Time Context**: Dynamic context from monitoring systems, logs, and live system state
- **Collaborative Context**: Context packages that span multiple projects and teams
- **Context Marketplaces**: Sharing high-quality context packages across organizations

### Implementation Roadmap

#### Phase 1: Foundation (4-6 weeks)
- Basic context package structure and storage
- Manual context package creation tools
- Simple context injection during agent initialization
- Basic usage tracking and analytics

#### Phase 2: Intelligence (6-8 weeks)  
- Dynamic context generation based on system changes
- Context effectiveness measurement and optimization
- Template-based context package creation
- Integration with existing agent coordination workflows

#### Phase 3: Sophistication (8-12 weeks)
- Subagent context propagation
- ML-enhanced context curation
- Advanced analytics and optimization
- Cross-system context integration

---

**Status**: Design Complete - Ready for Phase 1 Implementation  
**Priority**: High - Addresses critical gaps in agent context management  
**Dependencies**: Event Store Foundation (✅ Complete), Basic Agent Coordination  
**Impact**: Transforms agent effectiveness through intelligent context curation