# Perennia AI — Agent Optimization Framework
## The Definitive Guide to Building & Maintaining Elite AI Agents

---

## 1. Agent Design Standards

### 1.1 The Agent Contract

Every agent in the Perennia fleet MUST have a documented contract before deployment:

```yaml
# AGENT CONTRACT TEMPLATE
# ================================================
agent:
  name: "[Human-readable name]"
  id: "[snake_case_identifier]"
  version: "1.0.0"
  owner: "[Team member responsible]"
  
purpose:
  mission: "[One sentence: what this agent does and why it exists]"
  inputs: "[Exactly what data this agent receives]"
  outputs: "[Exactly what this agent produces]"
  success_criteria: "[How we know the agent did its job correctly]"
  failure_criteria: "[How we know the agent failed]"

boundaries:
  does: "[Specific list of what this agent handles]"
  does_not: "[Explicit list of what this agent should NEVER do]"
  escalates_when: "[Conditions that trigger human review]"

performance:
  target_latency_ms: X
  target_accuracy_pct: X
  max_tokens_per_call: X
  max_cost_per_call: $X.XX
  
dependencies:
  requires: "[Other agents/services this agent needs]"
  provides_to: "[Agents/services that depend on this agent]"
  
compliance:
  pii_handling: "[none / processes / stores — with justification]"
  audit_logging: "[what gets logged]"
  regulatory: "[RESPA / TILA / ECOA / FCRA / state-specific requirements]"
```

### 1.2 Agent Sizing Rules

| Agent Complexity | Token Budget (System Prompt) | Model Tier | Max Tools |
|:---------------:|:---------------------------:|:----------:|:---------:|
| Micro (single task) | 500-1,500 tokens | Haiku | 0-2 |
| Standard (focused role) | 1,500-4,000 tokens | Sonnet | 3-6 |
| Complex (multi-step reasoning) | 4,000-8,000 tokens | Sonnet/Opus | 5-10 |
| Orchestrator (manages agents) | 6,000-12,000 tokens | Opus | 8-15 |

**Rule: If your system prompt exceeds 12,000 tokens, your agent is doing too much. Split it.**

### 1.3 Prompt Engineering Standards

#### Structure Template
Every agent prompt MUST follow this structure:

```
SECTION 1: IDENTITY & ROLE (50-100 tokens)
Who you are. One paragraph. Crystal clear.

SECTION 2: MISSION (50-100 tokens)  
What you do. Specific, measurable, unambiguous.

SECTION 3: RULES & CONSTRAINTS (200-500 tokens)
Hard rules. What you must always do. What you must never do.
Front-load the most critical rules (primacy effect).

SECTION 4: INPUT SPECIFICATION (100-300 tokens)
What data you'll receive. Format. Required vs optional fields.

SECTION 5: OUTPUT SPECIFICATION (200-500 tokens)
Exact output format. JSON schema, field descriptions, examples.
ALWAYS enforce structured output for machine-consumed responses.

SECTION 6: PROCESS (200-1000 tokens)
Step-by-step reasoning process. Decision trees for complex logic.
Include "if X then Y" logic for common edge cases.

SECTION 7: EXAMPLES (200-500 tokens)
2-3 representative input/output pairs.
Include one edge case example.

SECTION 8: ERROR HANDLING (100-200 tokens)
What to do when input is malformed, incomplete, or ambiguous.
Default behaviors. Escalation triggers.
```

#### Prompt Anti-Patterns (NEVER DO)

| Anti-Pattern | Why It's Bad | Fix |
|-------------|-------------|-----|
| "Be helpful and thorough" | Vague, wastes tokens, encourages verbosity | Remove. Use specific output format instead. |
| Repeating instructions 3 ways | Token waste, can create contradictions | Say it once, precisely. |
| "Consider all factors" | Invites hallucination, no stopping criteria | List the specific factors to consider. |
| Embedding data in prompts | Bloats prompt, data goes stale | Inject data dynamically at runtime. |
| "Use your best judgment" | Unpredictable behavior | Define the decision criteria explicitly. |
| Entire prompt in a single paragraph | Hard for LLM to parse | Use clear section headers and structure. |
| Negative instructions only | "Don't" is weaker than "Do" | Frame as positive instructions. |
| No output schema | Inconsistent outputs break downstream | Always define exact output format. |

---

## 2. Performance Optimization Playbook

### 2.1 Token Reduction Strategies

#### Strategy 1: Dynamic Prompt Assembly
Don't send the full prompt every time. Build prompts from modular blocks:

```python
# BEFORE: 8,000 token static prompt every call
system_prompt = GIANT_STATIC_PROMPT  # wasteful

# AFTER: Assemble only what's needed
system_prompt = assemble_prompt(
    base=CORE_IDENTITY,           # ~200 tokens (always included)
    rules=AGENT_RULES,            # ~300 tokens (always included)
    output_schema=OUTPUT_FORMAT,  # ~200 tokens (always included)
    context_block=get_context(),  # ~variable (only relevant data)
    examples=select_examples(     # ~200 tokens (rotate examples)
        input_type=classify_input(user_input)
    ),
    tools=select_tools(           # ~variable (only needed tools)
        task_type=classify_task(user_input)
    )
)
```

#### Strategy 2: Context Compression
```python
# BEFORE: Passing full conversation history
context = full_conversation_history  # could be 50,000+ tokens

# AFTER: Summarize and compress
context = {
    "summary": summarize_conversation(history),  # ~500 tokens
    "key_decisions": extract_decisions(history),  # ~200 tokens
    "current_state": get_current_state(),         # ~300 tokens
    "last_3_messages": history[-3:]               # ~500 tokens
}
```

#### Strategy 3: Output Minimization
```python
# BEFORE: Agent returns verbose natural language
"Based on my analysis of the loan application, I have determined 
that the borrower meets the DTI requirements because their 
debt-to-income ratio of 38% falls below the maximum threshold 
of 43% for conventional loans..."  # 200+ tokens

# AFTER: Structured minimal output
{
    "decision": "APPROVED",
    "dti_ratio": 0.38,
    "dti_limit": 0.43,
    "confidence": 0.95,
    "flags": []
}  # ~30 tokens
```

### 2.2 Latency Reduction Strategies

#### Strategy 1: Parallel Agent Execution
```python
# BEFORE: Sequential (total = sum of all latencies)
email_analysis = await analyze_email(email)        # 3s
lead_score = await score_lead(email_analysis)       # 2s
task_list = await generate_tasks(email_analysis)    # 2s
notification = await draft_notification(lead_score) # 1s
# Total: 8 seconds

# AFTER: Parallel where dependencies allow
email_analysis = await analyze_email(email)         # 3s
# These three don't depend on each other, run in parallel:
lead_score, task_list, notification = await asyncio.gather(
    score_lead(email_analysis),                     # 2s
    generate_tasks(email_analysis),                 # 2s  
    draft_notification(email_analysis)              # 1s
)
# Total: 5 seconds (3s + 2s parallel) — 37% faster
```

#### Strategy 2: Prompt Caching
```python
# System prompts that rarely change should use Anthropic's prompt caching
# This can reduce costs by 90% and latency by 85% for cached portions

# Tag static portions for caching:
messages = [
    {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": STATIC_SYSTEM_PROMPT,  # Cached — served from memory
                "cache_control": {"type": "ephemeral"}
            }
        ]
    },
    {
        "role": "user", 
        "content": DYNAMIC_INPUT  # Not cached — changes every call
    }
]
```

#### Strategy 3: Pre-computation
```python
# Don't make agents compute what can be pre-computed
# BEFORE: Agent calculates DTI every time
prompt = f"Calculate the DTI ratio from these financials: {raw_data}"

# AFTER: Pre-compute, agent only interprets
dti = calculate_dti(financials)  # deterministic code, microseconds
prompt = f"DTI is {dti}. Assess qualification. Threshold: 43%."
```

### 2.3 Accuracy Enhancement Strategies

#### Strategy 1: Structured Output Enforcement
```python
# Use JSON mode or tool_use to force structured output
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    tools=[{
        "name": "submit_analysis",
        "description": "Submit the completed analysis",
        "input_schema": {
            "type": "object",
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["QUALIFIED", "NOT_QUALIFIED", "NEEDS_REVIEW"]
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1
                },
                "reasoning": {
                    "type": "string",
                    "maxLength": 500
                }
            },
            "required": ["classification", "confidence", "reasoning"]
        }
    }],
    tool_choice={"type": "tool", "name": "submit_analysis"}
)
```

#### Strategy 2: Chain-of-Verification
```python
# For high-stakes decisions, use a two-pass approach
# Pass 1: Agent makes the decision
decision = await agent_decide(input_data)

# Pass 2: Verification agent checks the work (can be cheaper model)
verification = await verify_decision(
    original_input=input_data,
    decision=decision,
    check_for=["logical_consistency", "data_accuracy", "compliance"]
)

if verification.confidence < 0.85:
    escalate_to_human(decision, verification)
```

#### Strategy 3: Confidence-Based Routing
```python
# Don't treat all inputs the same
confidence = quick_classify(input_data)

if confidence > 0.95:
    # High confidence: Use fast, cheap model
    result = await haiku_agent.process(input_data)
elif confidence > 0.75:
    # Medium confidence: Use standard model
    result = await sonnet_agent.process(input_data)
else:
    # Low confidence: Use best model + human review
    result = await opus_agent.process(input_data)
    flag_for_review(result)
```

---

## 3. Agent Testing Framework

### 3.1 Test Categories

Every agent MUST have tests in these categories:

#### Unit Tests (Per-Agent)
```python
class TestEmailTriageAgent:
    """Test the email triage agent in isolation."""
    
    # ACCURACY TESTS
    def test_correctly_classifies_purchase_inquiry(self):
        """Agent should classify purchase inquiry emails correctly."""
        
    def test_correctly_classifies_refinance_inquiry(self):
        """Agent should classify refinance inquiry emails correctly."""
    
    def test_handles_ambiguous_email(self):
        """Agent should flag ambiguous emails for human review."""
    
    def test_handles_spam(self):
        """Agent should identify and flag spam/irrelevant emails."""
    
    # OUTPUT FORMAT TESTS
    def test_output_matches_schema(self):
        """Agent output must match the defined JSON schema."""
    
    def test_required_fields_present(self):
        """All required output fields must be present."""
    
    # EDGE CASE TESTS
    def test_empty_email_body(self):
        """Agent should handle empty email bodies gracefully."""
    
    def test_extremely_long_email(self):
        """Agent should handle emails exceeding typical length."""
    
    def test_non_english_email(self):
        """Agent should detect and handle non-English content."""
    
    # SECURITY TESTS
    def test_prompt_injection_resistance(self):
        """Agent should not follow instructions embedded in email content."""
    
    def test_pii_not_leaked_in_logs(self):
        """Agent should not include PII in log output."""
    
    # PERFORMANCE TESTS
    def test_response_under_latency_target(self):
        """Agent should respond within target latency."""
    
    def test_token_usage_under_budget(self):
        """Agent should not exceed token budget per call."""
```

#### Integration Tests (Agent-to-Agent)
```python
class TestEmailToTaskPipeline:
    """Test the complete email → triage → task creation pipeline."""
    
    def test_purchase_email_creates_correct_tasks(self):
        """A purchase inquiry should trigger specific task creation."""
    
    def test_context_preserved_across_agents(self):
        """Data from email triage should be fully available to task agent."""
    
    def test_pipeline_handles_agent_failure(self):
        """If triage agent fails, pipeline should retry/escalate gracefully."""
```

#### Regression Tests
```python
class TestAgentRegression:
    """Run previous failure cases to ensure they stay fixed."""
    
    # Each time an agent fails in production, add the case here
    def test_regression_case_001_misclassified_heloc(self):
        """Previously misclassified HELOC inquiry as refinance."""
    
    def test_regression_case_002_missed_urgency(self):
        """Previously missed urgent deadline in email body."""
```

### 3.2 Evaluation Scoring

```python
# Automated scoring rubric for agent outputs
SCORING_RUBRIC = {
    "accuracy": {
        "weight": 0.35,
        "criteria": {
            "correct_classification": 0.4,
            "data_extraction_accuracy": 0.3,
            "no_hallucinated_data": 0.3
        }
    },
    "completeness": {
        "weight": 0.25,
        "criteria": {
            "all_required_fields_present": 0.5,
            "no_missing_insights": 0.3,
            "edge_cases_handled": 0.2
        }
    },
    "efficiency": {
        "weight": 0.20,
        "criteria": {
            "token_usage_within_budget": 0.4,
            "latency_within_target": 0.4,
            "no_unnecessary_tool_calls": 0.2
        }
    },
    "safety": {
        "weight": 0.20,
        "criteria": {
            "no_pii_exposure": 0.4,
            "prompt_injection_resistant": 0.3,
            "compliance_rules_followed": 0.3
        }
    }
}
```

### 3.3 A/B Testing Protocol

```yaml
ab_test:
  name: "[Agent Name] v[X] vs v[Y]"
  hypothesis: "[What we expect the new version to improve]"
  
  variants:
    control:
      prompt_version: "v1.2.0"
      model: "claude-sonnet-4-5-20250929"
    treatment:
      prompt_version: "v1.3.0-candidate"
      model: "claude-sonnet-4-5-20250929"
  
  traffic_split: 50/50
  duration: "7 days"
  sample_size_target: 500
  
  success_metrics:
    primary: "accuracy_score >= control + 5%"
    secondary:
      - "latency_p95 <= control"
      - "token_cost <= control + 10%"
      - "human_escalation_rate <= control"
  
  guardrails:
    auto_rollback_if:
      - "error_rate > control + 2%"
      - "compliance_violation_detected"
      - "latency_p99 > 30_seconds"
```

---

## 4. Agent Governance System

### 4.1 Agent Lifecycle

```
PROPOSED → DESIGNED → DEVELOPED → TESTED → STAGED → DEPLOYED → MONITORED → RETIRED
    |          |          |          |        |         |           |           |
    v          v          v          v        v         v           v           v
 Contract   Prompt    Unit Tests  QA Pass  Canary   Production  Dashboards  Sunset
 Approved   Reviewed  Pass        Review   Deploy   Traffic     Alerts      Plan
```

### 4.2 Deployment Checklist

Before ANY agent goes to production:

```
PRE-DEPLOYMENT CHECKLIST
========================

□ Agent contract documented and approved
□ System prompt reviewed by second person
□ Output schema defined and validated
□ Unit tests written and passing (min 80% coverage of scenarios)
□ Integration tests written and passing
□ Security review completed
  □ Prompt injection test passed
  □ PII handling verified
  □ Access control configured
□ Performance benchmarks established
  □ Latency target defined and met
  □ Token budget defined and met
  □ Cost projection reviewed
□ Monitoring configured
  □ Logging enabled
  □ Metrics dashboard created
  □ Alerting rules set
□ Rollback plan documented
□ Runbook for common failure scenarios
□ Compliance review (for mortgage-regulated functions)
```

### 4.3 Version Control

```yaml
# Every prompt change is versioned
prompt_versions:
  "1.0.0":
    date: "2025-01-15"
    change: "Initial deployment"
    author: "Tim"
    
  "1.1.0":
    date: "2025-02-01"
    change: "Added HELOC classification support"
    author: "Tim"
    test_results: "accuracy +8%, latency unchanged"
    
  "1.2.0":
    date: "2025-02-15"
    change: "Reduced token usage by 30% via prompt compression"
    author: "Tim"
    test_results: "accuracy unchanged, tokens -30%, cost -$45/mo"
    
  "1.2.1":
    date: "2025-02-18"
    change: "Hotfix: edge case with FHA loan classification"
    author: "Tim"
    regression_test_added: true
```

---

## 5. Agent Performance Dashboard Metrics

### 5.1 Per-Agent Metrics

```yaml
dashboard:
  real_time:
    - current_requests_in_flight
    - avg_latency_last_5min
    - error_rate_last_5min
    
  hourly:
    - total_invocations
    - p50_latency_ms
    - p95_latency_ms
    - p99_latency_ms
    - avg_tokens_in
    - avg_tokens_out
    - total_cost
    - error_count_by_type
    - human_escalation_count
    
  daily:
    - accuracy_score (from automated evaluation)
    - total_cost
    - total_invocations
    - unique_users_served
    - avg_confidence_score
    - regression_test_results
    
  weekly:
    - accuracy_trend
    - latency_trend
    - cost_trend
    - top_5_failure_patterns
    - optimization_opportunities
```

### 5.2 Fleet-Wide Metrics

```yaml
fleet_dashboard:
  health:
    - total_agents_active
    - agents_above_error_threshold
    - agents_above_latency_threshold
    - agents_above_cost_threshold
    
  economics:
    - total_daily_token_consumption
    - total_daily_cost
    - cost_per_agent_ranking
    - cost_trend_7d
    - projected_monthly_cost
    
  performance:
    - fleet_avg_latency
    - fleet_avg_accuracy
    - slowest_agent
    - least_accurate_agent
    - most_improved_agent_7d
    
  efficiency:
    - total_tokens_saved_by_caching
    - parallel_execution_time_savings
    - model_tier_distribution (% on haiku vs sonnet vs opus)
```

---

## 6. Continuous Learning Protocol

### 6.1 Weekly Agent Review

Every week, for each agent:

```
1. Pull last 7 days of metrics
2. Identify any accuracy drops, latency spikes, or cost increases
3. Review a random sample of 20 agent interactions
4. Score interactions against rubric
5. Identify top 3 failure patterns
6. Determine if prompt update is needed
7. If yes: draft update → test → A/B → deploy
8. Update regression test suite with any new failure cases
```

### 6.2 Monthly Fleet Review

```
1. Run /u_agent_fleet audit
2. Review agent scorecard rankings
3. Identify candidates for consolidation/elimination
4. Review competitive landscape for new capabilities
5. Update 90-day optimization roadmap
6. Review and update agent contracts as needed
7. Audit compliance and security posture
8. Cost optimization review — right-size models
```

### 6.3 Quarterly Strategic Review

```
1. Full competitive analysis vs. market
2. Agent capability gap analysis
3. Architecture review — is the agent topology still right?
4. Technology review — new models, new techniques, new tools
5. Cost projection for next quarter at projected growth
6. Team training on new agent development best practices
7. Update this framework document based on lessons learned
```

---

## 7. Perennia Agent Registry

### Active Agent Roster (Template)

| # | Agent Name | Category | Model | Criticality | Status | Last Audit |
|---|-----------|----------|-------|:-----------:|:------:|:----------:|
| 1 | Call Intelligence | 🧠 Intelligence | Sonnet | P0 | ✅ Active | [date] |
| 2 | Email Triage | 🧠 Intelligence | Haiku | P0 | ✅ Active | [date] |
| 3 | Document Parser | 🧠 Intelligence | Sonnet | P0 | ✅ Active | [date] |
| 4 | Lead Scorer | 🎯 Decision | Sonnet | P1 | ✅ Active | [date] |
| 5 | Task Generator | 🤖 Automation | Haiku | P1 | ✅ Active | [date] |
| 6 | Email Drafter | 💬 Communication | Sonnet | P1 | ✅ Active | [date] |
| 7 | SMS Responder | 💬 Communication | Haiku | P2 | ✅ Active | [date] |
| 8 | Rate Advisor | 🔍 Research | Sonnet | P1 | ✅ Active | [date] |
| 9 | Compliance Checker | 🛡️ Governance | Opus | P0 | ✅ Active | [date] |
| 10 | Workflow Orchestrator | 🔄 Orchestration | Sonnet | P0 | ✅ Active | [date] |
| ... | [Add all agents] | ... | ... | ... | ... | ... |

---

## 8. Emergency Runbook

### Agent Down / Producing Bad Output

```
SEVERITY 1 — Agent producing incorrect output in production:
1. IMMEDIATELY: Enable human-in-the-loop override for affected agent
2. Check: Is it a model API issue? (check Anthropic status page)
3. Check: Did input data format change? (check upstream systems)
4. Check: Was the prompt recently updated? (check version history)
5. If prompt change: ROLLBACK to last known good version
6. If data issue: Fix upstream and reprocess
7. If model issue: Switch to fallback model or queue for retry
8. Add failing case to regression tests
9. Post-mortem within 24 hours

SEVERITY 2 — Agent degraded performance:
1. Check metrics dashboard for anomaly source
2. Compare current performance to 7-day average
3. Review recent changes (deploys, data changes, volume spikes)
4. If volume spike: Scale resources, consider rate limiting
5. If gradual degradation: Schedule prompt optimization
6. Document and track in optimization backlog

SEVERITY 3 — Agent not meeting SLA:
1. Add to next weekly review agenda
2. Collect sample of underperforming interactions
3. Analyze for common patterns
4. Schedule prompt update cycle
```

---

*This framework is a living document. Update it as the fleet evolves, new patterns emerge, and new best practices are discovered. The goal: every Perennia AI agent operates at superhuman speed and accuracy, every day, getting better every week.*
