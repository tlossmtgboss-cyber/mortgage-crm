# AI Agent Remediation

## Table of Contents
1. [Tool Registry ↔ Agent Bridge](#bridge)
2. [Agent Value Metrics Dashboard](#metrics)
3. [Agent Reliability & Monitoring](#reliability)

---

<a name="bridge"></a>
## 1. Tool Registry ↔ Agent Bridge

### Current State
- Tool registry has 206 registered tools
- Agent service only creates ~22 inline tools
- ~90% of registered tools are disconnected from the agents that should use them
- The bridge between the registry and agent service was recently built but unproven

### The Problem

Two systems exist that should be one:

```
Tool Registry (206 tools)     Agent Service (~22 inline tools)
├── lead_scoring_tool          ├── score_lead (inline)
├── loan_analysis_tool         ├── analyze_loan (inline)
├── compliance_check_tool      ├── check_compliance (inline)
├── ... 183 more               ├── ... 19 more
└── (disconnected)             └── (hardcoded)
```

### Bridge Architecture

```python
# app/agents/tool_bridge.py
"""
Bridge between the tool registry (source of truth for tool definitions)
and the agent service (runtime tool execution).

The registry defines WHAT tools exist and their schemas.
The bridge makes them AVAILABLE to agents at runtime.
The agent service EXECUTES them.
"""

from app.agents.tool_registry import ToolRegistry
from app.agents.agent_service import AgentService

class ToolBridge:
    def __init__(self, registry: ToolRegistry, agent_service: AgentService):
        self.registry = registry
        self.agent_service = agent_service

    async def load_tools_for_agent(self, agent_name: str) -> list[dict]:
        """Load all tools registered for a specific agent.

        Returns tool definitions in the format the agent service expects
        (OpenAI function calling schema).
        """
        # Get tools registered for this agent
        registered_tools = await self.registry.get_tools_for_agent(agent_name)

        # Convert registry format → agent service format
        agent_tools = []
        for tool in registered_tools:
            agent_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameter_schema
                }
            })

        return agent_tools

    async def execute_tool(self, tool_name: str, arguments: dict, context: dict) -> dict:
        """Execute a registered tool by name.

        Looks up the tool implementation from the registry,
        validates arguments against the schema, and executes.
        """
        tool = await self.registry.get_tool(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found in registry"}

        # Validate arguments against schema
        validation_result = self._validate_arguments(arguments, tool.parameter_schema)
        if not validation_result["valid"]:
            return {"error": f"Invalid arguments: {validation_result['errors']}"}

        # Execute the tool's implementation
        try:
            result = await tool.execute(arguments, context)
            # Track execution for metrics
            await self._track_execution(tool_name, context, success=True)
            return result
        except Exception as e:
            await self._track_execution(tool_name, context, success=False, error=str(e))
            return {"error": f"Tool execution failed: {str(e)}"}
```

### Migration Plan

1. **Audit all 206 registered tools** — Classify each as:
   - Active (has working implementation): Keep
   - Stub (registered but no implementation): Implement or remove
   - Duplicate (overlaps with inline tool): Merge
   - Dead (never called): Remove

2. **For each agent, define its tool set** in config:

```python
# app/agents/config/agent_tools.py
AGENT_TOOL_MAPPING = {
    "lead_agent": [
        "score_lead",
        "qualify_lead",
        "assign_lead",
        "create_follow_up_task",
        "check_dnc_status",
        "enrich_contact_data",
    ],
    "loan_agent": [
        "analyze_loan",
        "calculate_dti",
        "check_rate_lock_status",
        "estimate_closing_costs",
        "compare_loan_programs",
    ],
    "compliance_agent": [
        "check_tila_compliance",
        "verify_disclosure_timing",
        "audit_equal_housing",
        "check_hmda_data",
    ],
    # ... 17 more agents
}
```

3. **Replace inline tools with registry lookups**:

```python
# BEFORE (inline tool definition)
tools = [
    {"type": "function", "function": {"name": "score_lead", ...}},
    {"type": "function", "function": {"name": "qualify_lead", ...}},
]

# AFTER (loaded from registry via bridge)
bridge = ToolBridge(registry, agent_service)
tools = await bridge.load_tools_for_agent("lead_agent")
```

4. **Test each agent** with its full tool set from the registry

---

<a name="metrics"></a>
## 2. Agent Value Metrics Dashboard

### Why This Matters

The 20-agent fleet is the biggest differentiator. But there's no dashboard showing ROI. Without metrics, you can't:
- Prove value to customers ("AI saved you 12 hours this week")
- Identify which agents are useful and which aren't
- Justify the infrastructure cost of running 20 agents
- Create sales collateral with real data

### Metrics to Track

```python
# app/models/agent_metrics.py
class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    agent_name = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=True)

    # Execution details
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)

    # Value tracking
    action_type = Column(String(50))  # "auto_followup", "risk_detection", "content_generation"
    estimated_time_saved_minutes = Column(Float, nullable=True)
    entities_affected = Column(Integer, default=0)  # leads touched, loans analyzed, etc.

    # Token usage (cost tracking)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)

    # Context
    trigger_source = Column(String(50))  # "user_command", "scheduled", "webhook", "workflow"
```

### Time Saved Estimation

```python
# app/services/agent_metrics_service.py

# Estimated manual time for each action type (based on industry benchmarks)
TIME_SAVED_ESTIMATES = {
    "lead_scoring": 3,          # 3 min to manually review and score a lead
    "follow_up_scheduling": 5,  # 5 min to decide timing + create task
    "loan_analysis": 15,        # 15 min to manually analyze loan scenario
    "compliance_check": 10,     # 10 min to review compliance items
    "content_generation": 20,   # 20 min to write a marketing email
    "document_review": 12,      # 12 min to review loan documents
    "rate_lock_monitoring": 8,  # 8 min to check rates + alert
    "contact_enrichment": 5,    # 5 min to research a contact
    "pipeline_update": 2,       # 2 min to update pipeline status
    "email_classification": 1,  # 1 min to classify and route an email
}

async def record_execution(
    db: AsyncSession,
    agent_name: str,
    tool_name: str,
    action_type: str,
    tenant_id: int,
    user_id: int = None,
    success: bool = True,
    duration_ms: int = None,
    entities_affected: int = 1,
    input_tokens: int = None,
    output_tokens: int = None,
    trigger_source: str = "user_command",
    error_message: str = None,
):
    estimated_time = TIME_SAVED_ESTIMATES.get(action_type, 2) * entities_affected

    execution = AgentExecution(
        tenant_id=tenant_id,
        user_id=user_id,
        agent_name=agent_name,
        tool_name=tool_name,
        started_at=datetime.utcnow() - timedelta(milliseconds=duration_ms or 0),
        completed_at=datetime.utcnow(),
        duration_ms=duration_ms,
        success=success,
        action_type=action_type,
        estimated_time_saved_minutes=estimated_time if success else 0,
        entities_affected=entities_affected,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        trigger_source=trigger_source,
        error_message=error_message,
    )
    db.add(execution)
```

### Dashboard API Endpoints

```python
# app/routes/agent_metrics.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/agent-metrics")

@router.get("/summary")
async def get_agent_summary(
    period: str = "week",  # "day", "week", "month"
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get agent performance summary for the current tenant."""
    return {
        "period": period,
        "total_executions": 1247,
        "successful_executions": 1198,
        "success_rate": 96.1,
        "total_time_saved_hours": 42.3,
        "total_tokens_used": 2_340_000,
        "top_agents": [
            {"name": "lead_agent", "executions": 423, "time_saved_hours": 14.1},
            {"name": "compliance_agent", "executions": 312, "time_saved_hours": 10.4},
            {"name": "content_agent", "executions": 187, "time_saved_hours": 8.7},
        ],
        "top_actions": [
            {"type": "lead_scoring", "count": 380, "time_saved_hours": 19.0},
            {"type": "compliance_check", "count": 245, "time_saved_hours": 12.3},
        ]
    }

@router.get("/user/{user_id}")
async def get_user_agent_stats(user_id: int, period: str = "week"):
    """Get per-LO agent usage stats.

    This powers the 'AI saved you X hours this week' notification.
    """
    return {
        "user_id": user_id,
        "time_saved_hours": 8.2,
        "actions_automated": 47,
        "highlight": "AI scored 23 leads and flagged 3 compliance issues this week"
    }
```

### Frontend Widget

```tsx
// features/ai-metrics/components/AIValueWidget.tsx
import { useQuery } from '@tanstack/react-query';

export function AIValueWidget() {
  const { data } = useQuery({
    queryKey: ['agent-metrics', 'summary'],
    queryFn: () => fetch('/api/agent-metrics/summary?period=week').then(r => r.json())
  });

  if (!data) return null;

  return (
    <div className="ai-value-card">
      <h3>AI Performance This Week</h3>
      <div className="metric-grid">
        <div className="metric">
          <span className="value">{data.total_time_saved_hours}h</span>
          <span className="label">Time Saved</span>
        </div>
        <div className="metric">
          <span className="value">{data.success_rate}%</span>
          <span className="label">Success Rate</span>
        </div>
        <div className="metric">
          <span className="value">{data.total_executions}</span>
          <span className="label">AI Actions</span>
        </div>
      </div>
    </div>
  );
}
```

---

<a name="reliability"></a>
## 3. Agent Reliability & Monitoring

### Hallucination Detection

The existing hallucination detection system should be integrated with the metrics:

```python
async def execute_agent_with_monitoring(
    agent_name: str,
    prompt: str,
    context: dict,
    db: AsyncSession
):
    """Execute an agent with full monitoring and hallucination detection."""
    start = time.monotonic()

    try:
        result = await agent_service.execute(agent_name, prompt, context)

        # Run hallucination detection on output
        hallucination_score = await detect_hallucinations(result, context)

        duration = int((time.monotonic() - start) * 1000)

        await record_execution(
            db=db,
            agent_name=agent_name,
            action_type=result.get("action_type", "unknown"),
            success=hallucination_score < 0.3,  # Flag if hallucination likely
            duration_ms=duration,
            tenant_id=context["tenant_id"],
            error_message=f"Hallucination score: {hallucination_score}" if hallucination_score >= 0.3 else None
        )

        return result

    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        await record_execution(
            db=db,
            agent_name=agent_name,
            action_type="error",
            success=False,
            duration_ms=duration,
            tenant_id=context["tenant_id"],
            error_message=str(e)
        )
        raise
```

### Alert on Agent Failures

```python
# app/services/agent_alerting.py
async def check_agent_health(db: AsyncSession, tenant_id: int):
    """Check if any agent's success rate has dropped below threshold."""
    # Last 100 executions per agent
    for agent_name in AGENT_NAMES:
        recent = await db.execute(
            select(AgentExecution)
            .where(
                AgentExecution.agent_name == agent_name,
                AgentExecution.tenant_id == tenant_id
            )
            .order_by(AgentExecution.started_at.desc())
            .limit(100)
        )
        executions = recent.scalars().all()

        if len(executions) >= 10:
            success_rate = sum(1 for e in executions if e.success) / len(executions)
            if success_rate < 0.85:
                await send_admin_alert(
                    f"Agent '{agent_name}' success rate dropped to {success_rate:.0%} "
                    f"(last {len(executions)} executions)"
                )
```

## Validation Checklist

- [ ] Tool registry audited: active/stub/duplicate/dead tools classified
- [ ] Agent-to-tool mapping defined for all 20 agents
- [ ] Bridge loads tools from registry (not inline definitions)
- [ ] Agent execution metrics table created and migrated
- [ ] Time-saved estimation working for top 10 action types
- [ ] Summary API endpoint returning accurate data
- [ ] Per-user "AI saved you X hours" calculation working
- [ ] AI Value Widget displaying on dashboard
- [ ] Hallucination detection integrated with execution monitoring
- [ ] Agent health alerts configured for <85% success rate
