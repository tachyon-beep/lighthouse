# Lighthouse: High-Level Design - Annex B

## Feature Pack 2: Multi-Agent Review & Sign-off System (MARS)

### Executive Summary

The Multi-Agent Review & Sign-off System (MARS) adds formal review gates to Lighthouse, enabling comprehensive design reviews and code reviews where multiple specialized agents must examine and explicitly approve changes before they're considered complete. Unlike reactive validation that blocks dangerous commands, MARS provides proactive, thorough review with documented sign-offs that become part of the permanent record through CAH.

### Motivation

Current Lighthouse validation happens at execution time - it's reactive and focused on safety. But senior developers know that the best bugs are caught in review, not in execution. The pattern of "have multiple agents review this work" is proven valuable, but currently ad-hoc. MARS formalizes this into a powerful review workflow that:

1. **Catches subtle bugs** that pass safety validation but are still wrong
2. **Ensures architectural compliance** before code is integrated
3. **Distributes knowledge** across the team (human and AI)
4. **Creates accountability** through recorded sign-offs
5. **Builds confidence** through multi-perspective validation
6. **Enables learning** by recording what reviewers missed

### Core Concepts

#### Review Package

A collection of changes bundled for review:

```yaml
ReviewPackage:
  package_id: "review_pkg_123"
  title: "Implement OAuth2 authentication"
  description: "Adds OAuth2 flow with Google and GitHub providers"
  created_by: "builder_john"
  created_at: "2024-01-15T10:00:00Z"
  
  changes:
    files_modified: [
      {
        path: "/api/auth.py",
        diff: "...",
        full_content_after: "...",
        edit_ids: ["edit_447", "edit_448", "edit_449"]
      }
    ]
    files_added: ["/api/oauth_providers.py", "/config/oauth.yaml"]
    files_deleted: []
    tests_added: ["/tests/test_oauth.py"]
    
  context:
    original_request: "Add social login to reduce password fatigue"
    design_decisions: [
      "Chose OAuth2 over SAML for simplicity",
      "Storing tokens in encrypted Redis cache",
      "15-minute access token lifetime"
    ]
    alternatives_considered: ["SAML", "Magic links", "Passkeys"]
    
  review_requirements:
    required_reviewers: ["security_expert", "architecture_expert"]
    optional_reviewers: ["performance_expert", "ux_expert"]
    human_review_required: false
    review_deadline: "2024-01-16T10:00:00Z"
    approval_threshold: "all_required"  # or "majority", "any_two", etc.
```

#### Review Types

```yaml
Review_Types:
  design_review:
    description: "Review design before implementation"
    reviewers: ["architecture_expert", "security_expert", "senior_dev"]
    artifacts: ["design_doc", "api_spec", "data_model"]
    
  code_review:
    description: "Review completed implementation"
    reviewers: ["security_expert", "performance_expert", "best_practices_expert"]
    artifacts: ["code_changes", "tests", "documentation"]
    
  pre_production_review:
    description: "Final review before production deployment"
    reviewers: ["security_expert", "operations_expert", "business_expert"]
    artifacts: ["full_changeset", "deployment_plan", "rollback_plan"]
    
  incident_review:
    description: "Review fix for production incident"
    reviewers: ["security_expert", "stability_expert", "original_author"]
    artifacts: ["fix", "root_cause_analysis", "test_additions"]
```

### Review Workflow

#### 1. Package Creation

```yaml
Developer_Action: "Package these changes for review"

System_Response:
  1. Collect_Changes:
     - Gather all modified files
     - Include full context from CAH
     - Add design decisions and reasoning
     
  2. Intelligent_Reviewer_Selection:
     Based on changes:
     - auth.py modified → security_expert required
     - New API endpoints → architecture_expert required  
     - Database queries added → performance_expert suggested
     - UI components changed → ux_expert optional
     
  3. Create_Review_Package:
     - Assign package_id
     - Set review deadline
     - Notify selected reviewers
```

#### 2. Multi-Agent Review Process

```yaml
Parallel_Review_Process:
  security_expert:
    focus_areas: ["Authentication", "Authorization", "Input validation", "Secrets"]
    review_process:
      1. Scan for vulnerability patterns
      2. Check OWASP compliance
      3. Verify security best practices
      4. Review token handling
    
  architecture_expert:
    focus_areas: ["Design patterns", "Service boundaries", "Dependencies", "Scalability"]
    review_process:
      1. Verify architectural compliance
      2. Check service boundaries
      3. Review dependency management
      4. Assess scalability impact
      
  performance_expert:
    focus_areas: ["Query optimization", "Caching", "Algorithm complexity", "Resource usage"]
    review_process:
      1. Analyze database queries
      2. Check for N+1 patterns
      3. Review caching strategy
      4. Estimate load impact
```

#### 3. Review Outcomes

```yaml
ReviewOutcome:
  package_id: "review_pkg_123"
  status: "changes_requested"  # approved, changes_requested, rejected
  
  reviews: [
    {
      reviewer: "security_expert",
      decision: "changes_requested",
      confidence: 0.95,
      timestamp: "2024-01-15T11:30:00Z",
      
      findings: [
        {
          severity: "high",
          type: "security",
          location: "/api/auth.py:47",
          issue: "Token stored in plain text in logs",
          suggestion: "Use secure logging that redacts tokens",
          must_fix: true
        }
      ],
      
      positive_feedback: [
        "Good use of constant-time comparison for tokens",
        "Proper CSRF protection implemented"
      ],
      
      sign_off: null  # Will be provided after changes
    },
    
    {
      reviewer: "architecture_expert",
      decision: "approved",
      confidence: 0.88,
      timestamp: "2024-01-15T11:35:00Z",
      
      findings: [],
      positive_feedback: [
        "Clean separation of concerns",
        "Proper use of dependency injection"
      ],
      
      sign_off: {
        statement: "Architecture approved - clean OAuth implementation",
        signature: "arch_expert_sig_abc123",
        timestamp: "2024-01-15T11:35:00Z"
      }
    }
  ]
```

### The Sign-off Chain of Responsibility

Each sign-off becomes a permanent record:

```yaml
SignOffRecord:
  reviewer: "security_expert"
  package_id: "review_pkg_123"
  commit_hash: "abc123def"
  
  attestation:
    statement: "I have reviewed these changes for security vulnerabilities"
    findings_addressed: ["SQL injection", "XSS", "CSRF", "Token security"]
    residual_risks: ["Rate limiting not implemented - track in RISK-1234"]
    confidence: 0.92
    caveats: ["Assuming Redis cache is properly secured"]
    
  accountability:
    if_this_breaks: "I acknowledged the token storage pattern was secure"
    review_depth: "comprehensive"  # "cursory", "standard", "comprehensive"
    time_spent_minutes: 15
    tools_used: ["semgrep", "pattern_matching", "owasp_checklist"]
    
  signature:
    hash: "sha256:abcdef..."
    timestamp: "2024-01-15T11:45:00Z"
    valid_until: "2024-07-15T11:45:00Z"  # Review expires after 6 months
```

### Integration with CAH

All reviews become part of the permanent record:

```yaml
CAH_Review_Integration:
  When_Bug_Found_Later:
    Query: "Who reviewed the auth changes that broke?"
    
    Response:
      Review_Package: "review_pkg_123"
      Reviewers_Who_Signed_Off:
        - security_expert: "Approved token handling"
        - architecture_expert: "Approved service design"
        
      What_They_Missed:
        - "Token refresh race condition"
        - "Cache invalidation edge case"
        
      Learning_Opportunity:
        - Add "race condition" to security checklist
        - Require performance_expert for caching reviews
```

### Review Intelligence Features

#### Review Quality Metrics

```yaml
Reviewer_Performance:
  security_expert_1:
    reviews_performed: 247
    issues_found: 89
    false_positives: 12
    missed_issues: 3  # Found later in production
    
    strength_areas:
      - SQL injection: 100% catch rate
      - Authentication: 98% catch rate
      
    blind_spots:
      - Race conditions: 60% catch rate
      - Cache security: 70% catch rate
      
    recommendation: "Pair with performance_expert for cache-related reviews"
```

#### Intelligent Review Assignment

```yaml
Smart_Assignment:
  Change_Analysis:
    - Payment code modified
    - Database queries added
    - External API called
    
  Historical_Context:
    - "Last payment change without security review caused incident"
    - "performance_expert caught 3 payment query issues others missed"
    
  Recommended_Reviewers:
    required: ["security_expert", "performance_expert", "payment_specialist"]
    optional: ["compliance_expert"]  # PCI DSS implications
```

#### Review Fatigue Management

```yaml
Review_Load_Balancing:
  security_expert_1:
    reviews_today: 12
    avg_review_time: 15_minutes
    fatigue_score: 0.8  # High fatigue
    
  security_expert_2:
    reviews_today: 3
    avg_review_time: 20_minutes
    fatigue_score: 0.3  # Fresh
    
  Assignment: "Route to security_expert_2 for better review quality"
```

### UI/UX Enhancements

#### Review Dashboard

```
📋 Active Reviews
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[PENDING] OAuth Implementation
├── 👤 Created by: builder_john (2 hours ago)
├── 📝 Changes: 5 files, +450 -23 lines
├── ⏱️ Deadline: 22 hours remaining
└── 👥 Reviews: ✅ Architecture ⏳ Security ⏳ Performance

[CHANGES REQUESTED] Payment Refactor
├── 👤 Created by: builder_sarah (5 hours ago)
├── 📝 Changes: 8 files, +200 -180 lines
├── 🔴 Security: 2 high-severity issues
└── 👥 Reviews: ✅ Architecture ❌ Security ✅ Performance

[View All] [My Reviews] [Team Stats]
```

#### Review Interface for Agents

```yaml
Agent_Review_Interface:
  Presented_With:
    - Full diff of all changes
    - Original requirements and context
    - Design decisions and rationale
    - Test coverage report
    - Performance impact analysis
    
  Agent_Can:
    - Ask clarifying questions
    - Request additional context
    - Suggest specific changes
    - Conditionally approve with caveats
    - Escalate to human reviewer
```

### Advanced Review Patterns

#### Design Review BEFORE Implementation

```yaml
Pre_Implementation_Review:
  Developer: "Here's my design for the new payment system"
  
  Package_Contents:
    - API specification
    - Data model design
    - Sequence diagrams
    - Security threat model
    
  Reviews:
    architecture_expert: "Consider event sourcing for audit trail"
    security_expert: "Add rate limiting to prevent abuse"
    performance_expert: "This will need caching at these 3 points"
    
  Benefit: Catch design issues before any code is written
```

#### Incremental Review

```yaml
Progressive_Review:
  Monday: "Review API design" → Get early feedback
  Wednesday: "Review implementation" → Validate approach
  Friday: "Review complete feature" → Final sign-off
  
  Benefit: Continuous feedback instead of big-bang review
```

#### Cross-Team Review

```yaml
Cross_Pollination:
  Team_A_Package: "New authentication system"
  
  Invited_Reviewers:
    - Team_B.security_expert  # Different perspective
    - Team_C.auth_specialist  # Domain expertise
    - Platform_Team.architect  # Overall system view
    
  Benefit: Knowledge sharing and consistency across teams
```

### Compliance and Audit Features

#### Regulatory Compliance

```yaml
SOX_Compliance_Review:
  Financial_Code_Change: true
  
  Required_Reviews:
    - security_expert: "Check for data tampering risks"
    - compliance_expert: "Verify audit trail maintained"
    - separation_of_duties: "Different person must review than wrote"
    
  Audit_Record:
    - Who reviewed what
    - When they reviewed it
    - What they attested to
    - Immutable and timestamped
```

#### Review Expiration

```yaml
Review_Aging:
  Original_Review: "2024-01-15"
  
  Six_Months_Later:
    Status: "Review expired - requires re-review"
    Reason: "Dependencies updated, security landscape changed"
    
  Triggered_Re_Review:
    - Security expert re-scans with latest patterns
    - Architecture expert checks for drift
    - New sign-offs required
```

### Success Metrics

1. **Defect Detection Rate**: 95% of bugs caught in review vs production
2. **Review Turnaround**: 80% of reviews completed within 4 hours
3. **Sign-off Accuracy**: <1% of signed-off changes cause incidents
4. **Knowledge Distribution**: Each change reviewed by 2+ experts
5. **Learning Velocity**: 50% reduction in repeat issues after review feedback

### The Killer Feature: Blame with Receipts

```yaml
When_Something_Breaks:
  Developer: "How did this bug get through?"
  
  System: "Review package review_pkg_123:
    - security_expert signed off at 11:45am
    - architecture_expert signed off at 11:35am
    - They specifically checked for: [list]
    - They missed: race condition in token refresh
    - Similar issue was missed in review_pkg_089
    - Recommendation: Add race condition to checklist"
    
  Value: Not blame, but learning and improvement
```

This formal review system would be game-changing because it:

1. **Scales expertise** - One expert can review many developers' work
2. **Creates accountability** - Sign-offs are permanent records
3. **Enables learning** - Track what reviews miss to improve over time
4. **Builds confidence** - Multiple experts agreeing is powerful validation
5. **Distributes knowledge** - Reviews teach both developers and agents

The beauty is that this integrates perfectly with CAH - every review, every sign-off, every missed bug becomes part of the learning system. Over time, the review system gets better at catching the specific types of issues that have slipped through before.
