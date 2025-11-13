"""
AI Agent Definitions
The 7 core specialized agents for the Mortgage OS
"""

from ai_models import AgentConfig, AgentType, AgentStatus, ToolDefinition, ToolCategory, RiskLevel


# ============================================================================
# AGENT 1: LEAD MANAGEMENT AGENT
# ============================================================================

LEAD_MANAGEMENT_AGENT = AgentConfig(
    id="lead_manager",
    name="Lead Management Agent",
    description="Triages, qualifies, and routes incoming leads. Ensures first-contact SLAs and proper assignment.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Qualify all new leads within 5 minutes",
        "Assign to appropriate LO based on criteria",
        "Create initial contact tasks",
        "Schedule discovery appointments",
        "Maintain >95% first-contact SLA"
    ],
    tools=[
        "getLeadById",
        "updateLeadStage",
        "createTask",
        "assignLeadToUser",
        "sendSms",
        "sendEmail",
        "bookCalendarSlot",
        "scoreLeadQuality"
    ],
    triggers=[
        "LeadCreated",
        "LeadUpdated",
        "InboundInquiry",
        "WebFormSubmitted",
        "PartnerReferralReceived"
    ],
    config={
        "qualification_criteria": {
            "min_credit_score": 580,
            "max_dti": 50,
            "required_fields": ["first_name", "last_name", "phone", "email"]
        },
        "sla_minutes": 5,
        "auto_assign_rules": {
            "fha": "team_member_3",
            "conventional": "team_member_1",
            "jumbo": "team_member_2"
        }
    }
)

# ============================================================================
# AGENT 2: PIPELINE MOVEMENT AGENT
# ============================================================================

PIPELINE_MOVEMENT_AGENT = AgentConfig(
    id="pipeline_manager",
    name="Pipeline Movement Agent",
    description="Monitors pipeline health, identifies stuck loans, creates nudges, and coordinates movement.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Reduce average days in stage by 20%",
        "Identify stuck loans within 24 hours",
        "Create proactive nudge tasks",
        "Coordinate with other agents for blockers",
        "Forecast pipeline velocity"
    ],
    tools=[
        "getLoanById",
        "updateLoanStage",
        "getPipelineSnapshot",
        "findStaleLo",
        "createTask",
        "sendMessage",
        "calculateVelocityMetrics",
        "escalateToHuman"
    ],
    triggers=[
        "DailyPipelineSweep",
        "LoanStageChanged",
        "LoanAged",
        "ConditionCleared",
        "DocumentReceived"
    ],
    config={
        "stale_thresholds": {
            "application": 3,  # days
            "processing": 5,
            "underwriting": 7,
            "clear_to_close": 3
        },
        "sweep_schedule": "0 9 * * *",  # 9 AM daily
        "escalation_threshold_days": 10
    }
)

# ============================================================================
# AGENT 3: DOCUMENT / UNDERWRITING AGENT
# ============================================================================

UNDERWRITING_ASSISTANT_AGENT = AgentConfig(
    id="underwriting_assistant",
    name="Document & Underwriting Agent",
    description="Extracts doc types, suggests condition clearing, flags missing docs, coordinates with pipeline.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Auto-classify 95% of uploaded docs",
        "Suggest condition clearing strategies",
        "Reduce doc chase time by 30%",
        "Flag missing docs proactively",
        "Coordinate with Pipeline Agent on blockers"
    ],
    tools=[
        "extractDocumentMetadata",
        "classifyDocument",
        "getLoanConditions",
        "suggestConditionStrategy",
        "createDocChaseTask",
        "sendDocumentRequest",
        "updateDocumentStatus",
        "sendMessage"
    ],
    triggers=[
        "DocUploaded",
        "EmailParsedWithDocs",
        "ConditionAdded",
        "UnderwritingRequested"
    ],
    config={
        "supported_doc_types": [
            "w2", "paystub", "bank_statement", "tax_return",
            "voe", "vod", "appraisal", "title", "insurance"
        ],
        "confidence_threshold": 0.85,
        "auto_approve_threshold": 0.95
    }
)

# ============================================================================
# AGENT 4: CUSTOMER ENGAGEMENT AGENT
# ============================================================================

CUSTOMER_ENGAGEMENT_AGENT = AgentConfig(
    id="customer_engagement",
    name="Customer Engagement Agent",
    description="Drafts communications, maintains relationship cadence, coordinates touchpoints, manages tone.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Maintain 7-day communication cadence",
        "Draft contextual, personalized messages",
        "Coordinate with other agents for timing",
        "Boost NPS by 15 points",
        "Reduce client anxiety through proactive updates"
    ],
    tools=[
        "draftSms",
        "draftEmail",
        "sendSms",
        "sendEmail",
        "getClientHistory",
        "getBorrowerProfile",
        "scheduleFollowUp",
        "sendMessage"
    ],
    triggers=[
        "LoanMilestoneReached",
        "ClientInquiry",
        "7DaysSinceLastContact",
        "ApplicationStatusChanged",
        "RateLockExpiringSoon"
    ],
    config={
        "tone_profiles": {
            "first_time_buyer": "warm, educational, patient",
            "investor": "professional, data-driven, concise",
            "repeat_client": "familiar, efficient, grateful"
        },
        "cadence_rules": {
            "application": 3,  # days between touches
            "processing": 5,
            "underwriting": 4,
            "clear_to_close": 2
        },
        "auto_send_threshold": 0.9  # confidence to auto-send
    }
)

# ============================================================================
# AGENT 5: PORTFOLIO ANALYSIS AGENT
# ============================================================================

PORTFOLIO_ANALYST_AGENT = AgentConfig(
    id="portfolio_analyst",
    name="Portfolio Analysis Agent",
    description="Scans closed loans for refi/MI drop/move-up opportunities, creates campaigns, coordinates outreach.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Identify 20+ refi opportunities per month",
        "Create targeted campaigns for portfolio",
        "Predict rate environment impact",
        "Coordinate with Customer Engagement for outreach",
        "Track campaign conversion rates"
    ],
    tools=[
        "getPortfolioLoans",
        "scanForRefiOpportunities",
        "checkMIDropEligibility",
        "calculateBreakEvenAnalysis",
        "createCampaign",
        "sendMessage",
        "getRateEnvironmentData"
    ],
    triggers=[
        "MonthlyPortfolioReview",
        "RateEnvironmentUpdate",
        "LoanAnniversary",
        "PropertyValueIncrease"
    ],
    config={
        "refi_criteria": {
            "min_rate_improvement_bps": 50,
            "min_time_since_closing_months": 6,
            "min_equity_percent": 20
        },
        "mi_drop_criteria": {
            "min_equity_percent": 20,
            "min_payment_history_months": 12
        },
        "scan_frequency_days": 30
    }
)

# ============================================================================
# AGENT 6: OPERATIONS AGENT
# ============================================================================

OPERATIONS_AGENT = AgentConfig(
    id="operations_agent",
    name="Operations Agent",
    description="Monitors system health, backlogs, queues. Highlights bottlenecks, recommends optimizations.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Maintain system uptime >99.9%",
        "Identify bottlenecks within 1 hour",
        "Optimize worker allocation",
        "Reduce processing time by 25%",
        "Proactively prevent outages"
    ],
    tools=[
        "getSystemHealth",
        "getQueueMetrics",
        "getAgentPerformance",
        "adjustWorkerConfig",
        "createIncident",
        "sendAlert",
        "generateOpsReport"
    ],
    triggers=[
        "HourlyHealthCheck",
        "QueueBacklogDetected",
        "AgentFailureDetected",
        "PerformanceDegradation",
        "DailyOpsReview"
    ],
    config={
        "health_check_interval_minutes": 60,
        "alert_thresholds": {
            "queue_depth": 100,
            "avg_response_time_ms": 5000,
            "error_rate_percent": 5
        },
        "auto_scale_rules": {
            "enabled": True,
            "max_workers": 10,
            "scale_up_threshold": 80,  # percent
            "scale_down_threshold": 20
        }
    }
)

# ============================================================================
# AGENT 7: FORECASTING & PLANNING AGENT
# ============================================================================

FORECASTING_AGENT = AgentConfig(
    id="forecasting_planner",
    name="Forecasting & Planning Agent",
    description="Forecasts volume, resourcing needs, suggests focus areas, predicts trends.",
    agent_type=AgentType.SPECIALIZED,
    status=AgentStatus.ACTIVE,
    goals=[
        "Forecast monthly volume within 10% accuracy",
        "Predict resource needs 2 weeks ahead",
        "Identify growth opportunities",
        "Suggest strategic focus areas",
        "Optimize capacity planning"
    ],
    tools=[
        "getPipelineSnapshot",
        "getHistoricalMetrics",
        "calculateVelocityTrends",
        "forecastVolume",
        "suggestResourceAllocation",
        "generateForecastReport",
        "sendMessage"
    ],
    triggers=[
        "WeeklyForecastRun",
        "MonthlyPlanningCycle",
        "PortfolioMilestone",
        "MarketConditionChange"
    ],
    config={
        "forecast_horizon_weeks": 12,
        "confidence_intervals": [0.5, 0.8, 0.95],
        "trend_analysis_months": 6,
        "factors": [
            "pipeline_velocity",
            "lead_quality",
            "conversion_rates",
            "rate_environment",
            "seasonal_patterns"
        ]
    }
)

# ============================================================================
# ALL AGENTS REGISTRY
# ============================================================================

ALL_AGENTS = [
    LEAD_MANAGEMENT_AGENT,
    PIPELINE_MOVEMENT_AGENT,
    UNDERWRITING_ASSISTANT_AGENT,
    CUSTOMER_ENGAGEMENT_AGENT,
    PORTFOLIO_ANALYST_AGENT,
    OPERATIONS_AGENT,
    FORECASTING_AGENT
]


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

TOOL_DEFINITIONS = [
    # Lead Management Tools
    ToolDefinition(
        name="getLeadById",
        description="Retrieve lead details by ID",
        category=ToolCategory.DATA_READ,
        input_schema={"type": "object", "properties": {"lead_id": {"type": "integer"}}, "required": ["lead_id"]},
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/get-lead",
        allowed_agents=["lead_manager", "customer_engagement"],
        risk_level=RiskLevel.LOW
    ),
    ToolDefinition(
        name="updateLeadStage",
        description="Update lead stage/status",
        category=ToolCategory.DATA_WRITE,
        input_schema={
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer"},
                "stage": {"type": "string"}
            },
            "required": ["lead_id", "stage"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/update-lead-stage",
        allowed_agents=["lead_manager"],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False
    ),
    ToolDefinition(
        name="createTask",
        description="Create a new task",
        category=ToolCategory.WORKFLOW,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "assigned_to": {"type": "integer"},
                "due_date": {"type": "string"},
                "priority": {"type": "string"},
                "entity_type": {"type": "string"},
                "entity_id": {"type": "integer"}
            },
            "required": ["title", "assigned_to"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/create-task",
        allowed_agents=["lead_manager", "pipeline_manager", "underwriting_assistant"],
        risk_level=RiskLevel.LOW
    ),
    ToolDefinition(
        name="sendSms",
        description="Send SMS message",
        category=ToolCategory.COMMUNICATION,
        input_schema={
            "type": "object",
            "properties": {
                "to_number": {"type": "string"},
                "message": {"type": "string"},
                "lead_id": {"type": "integer"}
            },
            "required": ["to_number", "message"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/send-sms",
        allowed_agents=["customer_engagement", "lead_manager"],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=True  # Require human approval for SMS
    ),
    ToolDefinition(
        name="sendEmail",
        description="Send email message",
        category=ToolCategory.COMMUNICATION,
        input_schema={
            "type": "object",
            "properties": {
                "to_email": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "lead_id": {"type": "integer"}
            },
            "required": ["to_email", "subject", "body"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/send-email",
        allowed_agents=["customer_engagement", "lead_manager"],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=True
    ),
    # Pipeline Management Tools
    ToolDefinition(
        name="getLoanById",
        description="Retrieve loan details by ID",
        category=ToolCategory.DATA_READ,
        input_schema={"type": "object", "properties": {"loan_id": {"type": "integer"}}, "required": ["loan_id"]},
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/get-loan",
        allowed_agents=["pipeline_manager", "underwriting_assistant", "portfolio_analyst"],
        risk_level=RiskLevel.LOW
    ),
    ToolDefinition(
        name="updateLoanStage",
        description="Update loan stage",
        category=ToolCategory.DATA_WRITE,
        input_schema={
            "type": "object",
            "properties": {
                "loan_id": {"type": "integer"},
                "stage": {"type": "string"},
                "reason": {"type": "string"}
            },
            "required": ["loan_id", "stage"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/update-loan-stage",
        allowed_agents=["pipeline_manager"],
        risk_level=RiskLevel.HIGH,
        requires_approval=True  # Stage changes need approval
    ),
    ToolDefinition(
        name="getPipelineSnapshot",
        description="Get current pipeline snapshot with metrics",
        category=ToolCategory.ANALYSIS,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/pipeline-snapshot",
        allowed_agents=["pipeline_manager", "operations_agent", "forecasting_planner"],
        risk_level=RiskLevel.LOW
    ),
    # Document / Underwriting Tools
    ToolDefinition(
        name="classifyDocument",
        description="Classify document type using AI",
        category=ToolCategory.ANALYSIS,
        input_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "file_path": {"type": "string"}
            },
            "required": ["document_id"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "document_type": {"type": "string"},
                "confidence": {"type": "number"}
            }
        },
        handler_endpoint="/api/ai/tools/classify-document",
        allowed_agents=["underwriting_assistant"],
        risk_level=RiskLevel.LOW
    ),
    # Portfolio Tools
    ToolDefinition(
        name="scanForRefiOpportunities",
        description="Scan portfolio for refinance opportunities",
        category=ToolCategory.ANALYSIS,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "array"},
        handler_endpoint="/api/ai/tools/scan-refi-opportunities",
        allowed_agents=["portfolio_analyst"],
        risk_level=RiskLevel.LOW
    ),
    # Operations Tools
    ToolDefinition(
        name="getSystemHealth",
        description="Get current system health metrics",
        category=ToolCategory.ANALYSIS,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/system-health",
        allowed_agents=["operations_agent"],
        risk_level=RiskLevel.LOW
    ),
    # Forecasting Tools
    ToolDefinition(
        name="forecastVolume",
        description="Forecast loan volume for next N weeks",
        category=ToolCategory.ANALYSIS,
        input_schema={
            "type": "object",
            "properties": {
                "weeks_ahead": {"type": "integer"}
            },
            "required": ["weeks_ahead"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/forecast-volume",
        allowed_agents=["forecasting_planner"],
        risk_level=RiskLevel.LOW
    ),
    # Inter-agent communication
    ToolDefinition(
        name="sendMessage",
        description="Send message to another agent",
        category=ToolCategory.COMMUNICATION,
        input_schema={
            "type": "object",
            "properties": {
                "to_agent_id": {"type": "string"},
                "subject": {"type": "string"},
                "content": {"type": "string"},
                "priority": {"type": "string"}
            },
            "required": ["to_agent_id", "subject", "content"]
        },
        output_schema={"type": "object"},
        handler_endpoint="/api/ai/tools/send-agent-message",
        allowed_agents=[agent.id for agent in ALL_AGENTS],  # All agents can message each other
        risk_level=RiskLevel.LOW
    )
]
