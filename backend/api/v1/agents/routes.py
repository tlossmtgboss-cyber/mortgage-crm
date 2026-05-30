"""
Agent Orchestration API Routes

Endpoints for agent execution, metrics, A/B testing, and quality analysis.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional
from pathlib import Path
import os
import json
import time
import logging
import uuid


def _get_current_user():
    """Lazy import auth dependency to avoid circular imports."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

from .schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    EmailAnalysisRequest,
    EmailAnalysisResponse,
    OutcomeLogRequest,
    ABTestCreateRequest,
    ABTestResultsResponse,
    QualityAnalysisRequest,
    QualityAnalysisResponse,
    AgentMetricsResponse,
    StageBreakdownResponse,
    AgentConfigResponse,
    AgentListResponse,
    TokenUsageResponse,
    OrganizationInfo,
)

# Import db_helpers for organization lookups
from agents.orchestration.db_helpers import get_organization_for_agent

# Import orchestration components
from agents.orchestration.context_manager import ContextManager
from agents.orchestration.performance_tracker import PerformanceTracker, ABTestTracker
from agents.orchestration.quality_analyzer import QualityAnalyzer, generate_quality_report
from agents.orchestration.prompt_builder import (
    AgentPromptBuilder,
    create_lead_qualification_agent,
    create_email_intelligence_agent,
    create_document_collection_agent,
    create_rate_lock_agent,
)
from agents.orchestration.config.agent_configs import (
    AGENT_REGISTRY,
    get_agent_config,
    export_agent_config,
    get_all_agent_ids,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents",
    tags=["Agent Orchestration"],
    dependencies=[Depends(_get_current_user())],
)

# Initialize components
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "agents" / "perennia-prompts"
context_manager = ContextManager(PROMPTS_DIR)
performance_tracker = PerformanceTracker()
ab_test_tracker = ABTestTracker()
quality_analyzer = QualityAnalyzer()

# Default organization for fallback
DEFAULT_ORGANIZATION = {
    "id": None,
    "name": "The Tim Loss Team",
    "brand_name": "The Tim Loss Team",
    "display_name": "The Tim Loss Team",
    "website": None,
    "phone": None,
    "agent_personas": {},
    "custom_prompts": {},
}


def resolve_organization(
    organization_id: int = None,
    organization: OrganizationInfo = None,
    db = None
) -> dict:
    """
    Resolve organization branding info from various sources.

    Priority:
    1. Explicit organization object in request
    2. Database lookup by organization_id
    3. Default fallback
    """
    # If explicit organization object provided, use it
    if organization:
        return {
            "id": organization.id,
            "name": organization.name or organization.brand_name,
            "brand_name": organization.brand_name or organization.name or DEFAULT_ORGANIZATION["brand_name"],
            "display_name": organization.display_name or organization.name or DEFAULT_ORGANIZATION["display_name"],
            "website": organization.website,
            "phone": organization.phone,
            "agent_personas": organization.agent_personas or {},
            "custom_prompts": {},
        }

    # If organization_id provided and db available, look it up
    if organization_id and db:
        try:
            org_data = get_organization_for_agent(db, organization_id=organization_id)
            if org_data and org_data.get("id"):
                return org_data
        except Exception as e:
            logger.warning(f"Failed to fetch organization {organization_id}: {e}")

    # Return default
    return DEFAULT_ORGANIZATION


# =============================================================================
# AGENT EXECUTION ENDPOINTS
# =============================================================================

@router.post("/execute", response_model=AgentExecuteResponse)
async def execute_agent(
    request: AgentExecuteRequest,
    background_tasks: BackgroundTasks
):
    """
    Execute an agent with token-optimized prompt loading.

    This endpoint:
    1. Loads context-aware prompt (12-18k tokens instead of 90k)
    2. Injects dynamic company name for white-label support
    3. Executes the AI model
    4. Tracks performance metrics
    5. Returns the response with suggested next stage

    White-label support:
    - Pass `organization_id` to fetch branding from database
    - Or pass `organization` object directly with brand_name, display_name, etc.
    """
    start_time = time.time()

    try:
        # Resolve organization for white-label branding
        organization = resolve_organization(
            organization_id=request.organization_id,
            organization=request.organization
        )

        # Get optimized prompt with company name injection
        prompt = await context_manager.get_optimized_prompt(
            agent_id=request.agent_id,
            conversation_stage=request.stage.value,
            conversation_history=[{"role": m.role, "content": m.content} for m in request.history],
            user_profile=request.user_profile,
            metadata=request.metadata,
            organization=organization  # Pass organization for white-label
        )

        # Get agent config for model selection
        agent_config = get_agent_config(request.agent_id)
        model = agent_config.ai_model if agent_config else "claude-sonnet-4-6"

        # Execute AI call
        # NOTE: Replace with actual AI client call
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Build messages from history
        messages = []
        for msg in request.history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # If no user message, add a placeholder
        if not messages or messages[-1]["role"] != "user":
            messages.append({
                "role": "user",
                "content": request.metadata.get("initial_trigger", "Starting conversation")
            })

        from agents.anthropic_client import cached_system_block
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=cached_system_block(prompt),
            messages=messages
        )

        response_text = response.content[0].text
        latency_ms = int((time.time() - start_time) * 1000)

        # Detect stage transition
        suggested_next_stage = context_manager.detect_stage_transition(
            current_stage=request.stage.value,
            conversation_history=[{"role": m.role, "content": m.content} for m in request.history],
            qualification_data=request.user_profile.get("qualification_data")
        )

        # Log execution in background
        background_tasks.add_task(
            performance_tracker.log_execution,
            {
                "agent_id": request.agent_id,
                "conversation_id": request.conversation_id,
                "stage": request.stage.value,
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "model_used": model,
                "response": response_text,
            }
        )

        return AgentExecuteResponse(
            success=True,
            response_text=response_text,
            conversation_id=request.conversation_id,
            stage=request.stage.value,
            suggested_next_stage=suggested_next_stage,
            qualification_data=request.user_profile.get("qualification_data"),
            execution_metrics={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                "latency_ms": latency_ms,
                "model": model,
            }
        )

    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email/analyze", response_model=EmailAnalysisResponse)
async def analyze_email(
    request: EmailAnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    Analyze an incoming email and extract intelligence.

    Returns structured data including:
    - Category (rate_lock, document_upload, status_inquiry, etc.)
    - Urgency level
    - Action items
    - Routing recommendation

    White-label support:
    - Pass `organization_id` to fetch branding from database
    - Or pass `organization` object directly
    """
    start_time = time.time()
    conversation_id = request.conversation_id or str(uuid.uuid4())

    try:
        # Resolve organization for white-label branding
        organization = resolve_organization(
            organization_id=request.organization_id,
            organization=request.organization
        )

        # Get optimized prompt for email analysis with company name injection
        prompt = await context_manager.get_optimized_prompt(
            agent_id="email_intel",
            conversation_stage="email_analysis",
            conversation_history=[{
                "role": "user",
                "content": f"Subject: {request.subject}\nFrom: {request.sender}\n\n{request.email_content}"
            }],
            user_profile={"email": request.sender},
            metadata={"subject": request.subject},
            organization=organization  # Pass organization for white-label
        )

        # Execute AI call
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        from agents.anthropic_client import cached_system_block
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=cached_system_block(prompt),
            messages=[{
                "role": "user",
                "content": f"Analyze this email:\n\nSubject: {request.subject}\nFrom: {request.sender}\n\n{request.email_content}"
            }]
        )

        response_text = response.content[0].text
        latency_ms = int((time.time() - start_time) * 1000)

        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            result = json.loads(json_text.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse email analysis JSON: {response_text[:200]}")
            result = {
                "category": "general_question",
                "confidence": 0.5,
                "urgency": "Medium",
                "action_items": [],
                "routing": "general_inbox",
                "summary": response_text[:100]
            }

        # Log execution
        background_tasks.add_task(
            performance_tracker.log_execution,
            {
                "agent_id": "email_intel",
                "conversation_id": conversation_id,
                "stage": "email_analysis",
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "response": response_text,
            }
        )

        return EmailAnalysisResponse(
            success=True,
            category=result.get("category", "general_question"),
            confidence=result.get("confidence", 0.5),
            loan_number=result.get("loan_number"),
            borrower=result.get("borrower"),
            urgency=result.get("urgency", "Medium"),
            action_items=result.get("action_items", []),
            deadline=result.get("deadline"),
            routing=result.get("routing", "general_inbox"),
            summary=result.get("summary", ""),
            execution_metrics={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
            }
        )

    except Exception as e:
        logger.error(f"Email analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# PERFORMANCE METRICS ENDPOINTS
# =============================================================================

@router.get("/metrics/{agent_id}", response_model=AgentMetricsResponse)
async def get_agent_metrics(
    agent_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get performance metrics for an agent.

    Returns conversion rates, token usage, latency, and revenue metrics.
    """
    try:
        metrics = await performance_tracker.get_agent_metrics(agent_id, days)
        return AgentMetricsResponse(**metrics)
    except Exception as e:
        logger.error(f"Failed to get agent metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics/{agent_id}/stages", response_model=StageBreakdownResponse)
async def get_stage_breakdown(
    agent_id: str,
    days: int = Query(30, ge=1, le=365)
):
    """
    Get performance breakdown by conversation stage.

    Helps identify bottlenecks in the conversation flow.
    """
    try:
        breakdown = await performance_tracker.get_stage_breakdown(agent_id, days)
        return StageBreakdownResponse(**breakdown)
    except Exception as e:
        logger.error(f"Failed to get stage breakdown: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics/{agent_id}/tokens", response_model=TokenUsageResponse)
async def get_token_trends(
    agent_id: str,
    days: int = Query(30, ge=1, le=365)
):
    """
    Get token usage trends over time.

    Useful for monitoring cost optimization.
    """
    try:
        trends = await performance_tracker.get_token_trends(agent_id, days)

        total_tokens = sum(t.get("total_tokens", 0) for t in trends.get("trends", []))
        estimated_cost = total_tokens / 1000 * 0.003  # Rough estimate

        return TokenUsageResponse(
            agent_id=agent_id,
            period_days=days,
            trends=trends.get("trends", []),
            total_tokens=total_tokens,
            estimated_cost=round(estimated_cost, 2)
        )
    except Exception as e:
        logger.error(f"Failed to get token trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/outcomes")
async def log_outcome(request: OutcomeLogRequest):
    """
    Log a conversation outcome.

    Used for tracking conversion metrics and funnel analysis.
    """
    try:
        outcome_id = await performance_tracker.log_outcome({
            "conversation_id": request.conversation_id,
            "agent_id": request.agent_id,
            "outcome_type": request.outcome_type.value,
            "total_messages": request.total_messages,
            "qualification_complete": request.qualification_complete,
            "booking_made": request.booking_made,
            "revenue_generated": request.revenue_generated,
            "metrics": request.metrics,
        })
        return {"success": True, "outcome_id": outcome_id}
    except Exception as e:
        logger.error(f"Failed to log outcome: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# A/B TESTING ENDPOINTS
# =============================================================================

@router.post("/ab-tests", response_model=dict)
async def create_ab_test(request: ABTestCreateRequest):
    """
    Create a new A/B test for an agent.

    Allows testing different prompt configurations.
    """
    try:
        test_id = await ab_test_tracker.create_test(
            test_name=request.test_name,
            agent_id=request.agent_id,
            variant_a_config=request.variant_a_config,
            variant_b_config=request.variant_b_config,
            traffic_split=request.traffic_split
        )
        return {"success": True, "test_id": test_id, "test_name": request.test_name}
    except Exception as e:
        logger.error(f"Failed to create A/B test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ab-tests/{test_id}", response_model=ABTestResultsResponse)
async def get_ab_test_results(test_id: str):
    """
    Get results for an A/B test.

    Includes statistical significance and recommendations.
    """
    try:
        results = await ab_test_tracker.get_results(test_id)
        if not results:
            raise HTTPException(status_code=404, detail="Test not found")
        return ABTestResultsResponse(**results)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ab-tests/{test_id}/end")
async def end_ab_test(test_id: str):
    """
    End an A/B test.
    """
    try:
        await ab_test_tracker.end_test(test_id)
        return {"success": True, "test_id": test_id, "status": "completed"}
    except Exception as e:
        logger.error(f"Failed to end A/B test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# QUALITY ANALYSIS ENDPOINTS
# =============================================================================

@router.post("/quality/analyze", response_model=QualityAnalysisResponse)
async def analyze_prompt_quality(request: QualityAnalysisRequest):
    """
    Analyze a prompt for quality based on best practices.

    Scores against:
    - Identity & Role clarity
    - Conversation style
    - Qualification process
    - Objection handling
    - Rules & guardrails
    - FAQ coverage
    """
    try:
        analysis = quality_analyzer.analyze(request.prompt)
        return QualityAnalysisResponse(**analysis)
    except Exception as e:
        logger.error(f"Failed to analyze prompt quality: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/quality/report")
async def generate_prompt_report(request: QualityAnalysisRequest):
    """
    Generate a formatted quality report for a prompt.
    """
    try:
        report = generate_quality_report(
            request.prompt,
            request.agent_name or "Agent"
        )
        return {"report": report}
    except Exception as e:
        logger.error(f"Failed to generate quality report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/quality/suggestions/{agent_id}")
async def get_improvement_suggestions(agent_id: str):
    """
    Get specific improvement suggestions for an agent's prompt.
    """
    try:
        # Get the agent's current prompt
        config = get_agent_config(agent_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Build prompt from config
        from agents.orchestration.prompt_builder import AgentPromptBuilder, ConversationRules
        builder = AgentPromptBuilder()
        prompt = builder \
            .set_objective(f"perform {config.use_case.value}") \
            .set_rules(ConversationRules(
                max_questions_per_message=config.rules.max_questions_per_message,
                max_response_words=config.rules.max_response_words,
                avoid_conciliatory_phrases=config.rules.avoid_conciliatory_phrases,
                persistent_engagement=config.rules.persistent_engagement,
            )) \
            .build()

        suggestions = quality_analyzer.suggest_improvements(prompt)
        return {"agent_id": agent_id, "suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get improvement suggestions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# AGENT CONFIGURATION ENDPOINTS
# =============================================================================

@router.get("/", response_model=AgentListResponse)
async def list_agents():
    """
    List all registered agents with their configurations.
    """
    try:
        agents = []
        for agent_id in get_all_agent_ids():
            config = export_agent_config(agent_id)
            if config:
                agents.append(AgentConfigResponse(**config))

        return AgentListResponse(agents=agents, total=len(agents))
    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{agent_id}", response_model=AgentConfigResponse)
async def get_agent(agent_id: str):
    """
    Get configuration for a specific agent.
    """
    try:
        config = export_agent_config(agent_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        return AgentConfigResponse(**config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{agent_id}/prompt")
async def get_agent_prompt(
    agent_id: str,
    stage: str = Query("initial_contact", description="Conversation stage")
):
    """
    Get the full prompt for an agent at a specific stage.

    Useful for debugging and prompt review.
    """
    try:
        prompt = await context_manager.get_optimized_prompt(
            agent_id=agent_id,
            conversation_stage=stage,
            conversation_history=[],
            user_profile={"first_name": "{{first_name}}"},
            metadata={}
        )

        # Estimate tokens
        estimated_tokens = len(prompt) // 4

        return {
            "agent_id": agent_id,
            "stage": stage,
            "prompt": prompt,
            "estimated_tokens": estimated_tokens,
            "character_count": len(prompt),
        }
    except Exception as e:
        logger.error(f"Failed to get agent prompt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# TEMPLATE ENDPOINTS
# =============================================================================

@router.get("/templates/lead-qualification")
async def get_lead_qualification_template():
    """
    Get the pre-built lead qualification agent template.
    """
    prompt = create_lead_qualification_agent()
    score = quality_analyzer.get_quick_score(prompt)

    return {
        "template_name": "Lead Qualification Agent",
        "prompt": prompt,
        "estimated_tokens": len(prompt) // 4,
        "quality_score": score,
    }


@router.get("/templates/email-intelligence")
async def get_email_intelligence_template():
    """
    Get the pre-built email intelligence agent template.
    """
    prompt = create_email_intelligence_agent()
    score = quality_analyzer.get_quick_score(prompt)

    return {
        "template_name": "Email Intelligence Agent",
        "prompt": prompt,
        "estimated_tokens": len(prompt) // 4,
        "quality_score": score,
    }


@router.get("/templates/document-collection")
async def get_document_collection_template():
    """
    Get the pre-built document collection agent template.
    """
    prompt = create_document_collection_agent()
    score = quality_analyzer.get_quick_score(prompt)

    return {
        "template_name": "Document Collection Agent",
        "prompt": prompt,
        "estimated_tokens": len(prompt) // 4,
        "quality_score": score,
    }


@router.get("/templates/rate-lock")
async def get_rate_lock_template():
    """
    Get the pre-built rate lock intelligence agent template.
    """
    prompt = create_rate_lock_agent()
    score = quality_analyzer.get_quick_score(prompt)

    return {
        "template_name": "Rate Lock Intelligence Agent",
        "prompt": prompt,
        "estimated_tokens": len(prompt) // 4,
        "quality_score": score,
    }
