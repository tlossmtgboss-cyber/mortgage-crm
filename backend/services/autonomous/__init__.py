"""
Autonomous AI Agent Services

Proactive agents that run on schedules to manage the mortgage pipeline,
nurture leads, monitor compliance, and drive CRM operations autonomously.

Agents:
    - LeadNurturingAgent: Follow up on cold/stale leads
    - ComplianceWatchdogAgent: Scan for regulatory deadline violations
    - PipelineMonitorAgent: Detect stalled loans and bottlenecks
    - DocumentFollowupAgent: Chase missing documents
    - RateAlertAgent: Monitor rate changes and lock expirations
    - LeadScoringAgent: Auto-score and prioritize leads
    - ReportingAgent: Generate daily briefings and reports
    - ClientLifecycleAgent: Post-closing relationship management

Engine:
    - AutonomousTaskExecutor: Central scheduler that polls and executes agents
"""

AGENT_TYPES = [
    "lead_nurturing",
    "compliance_watchdog",
    "pipeline_monitor",
    "document_followup",
    "rate_alert",
    "lead_scoring",
    "reporting",
    "client_lifecycle",
]
