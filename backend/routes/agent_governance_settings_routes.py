"""
Agent Governance Settings API Routes
Perennia AI - Proof of Concept for Comprehensive Error Handling

This file demonstrates the error handling pattern that should be applied
across all settings pages. It shows:
- Structured error responses with error codes
- Field-level validation
- Permission checks
- Database transactions with rollback
- Cost estimation
- Comprehensive logging

Use this as a template for refactoring other routes.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import logging

from database import get_db
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    ConflictException,
    BusinessRuleException,
    success_response,
    validate_required_fields,
    validate_field_length,
    raise_if_errors,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/settings/agent-governance",
    tags=["agent-governance-settings"]
)


# =============================================================================
# ENUMS
# =============================================================================

class AgentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    TESTING = "testing"
    MAINTENANCE = "maintenance"


class ModelType(str, Enum):
    GPT4_TURBO = "gpt-4-turbo"
    GPT4 = "gpt-4"
    GPT35_TURBO = "gpt-3.5-turbo"
    CLAUDE_SONNET = "claude-sonnet-4"
    CLAUDE_OPUS = "claude-opus-4"
    CLAUDE_HAIKU = "claude-haiku"


class SafetyLevel(str, Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    PERMISSIVE = "permissive"


class RiskTier(str, Enum):
    TIER_1 = "1"  # High risk - requires approval
    TIER_2 = "2"  # Medium risk
    TIER_3 = "3"  # Low risk


# =============================================================================
# PYDANTIC MODELS WITH VALIDATION
# =============================================================================

class TokenLimits(BaseModel):
    """Token usage limits for an agent"""
    max_tokens_per_request: int = Field(
        default=2000,
        ge=100,
        le=32000,
        description="Maximum tokens per single request"
    )
    max_tokens_per_day: Optional[int] = Field(
        default=None,
        ge=1000,
        le=1000000,
        description="Daily token limit (optional)"
    )
    warn_threshold_percentage: int = Field(
        default=80,
        ge=50,
        le=95,
        description="Percentage of limit to trigger warning"
    )

    @validator('max_tokens_per_day')
    def validate_daily_limit(cls, v, values):
        if v and 'max_tokens_per_request' in values:
            per_request = values['max_tokens_per_request']
            if v < per_request * 10:
                raise ValueError(
                    'Daily token limit should be at least 10x the per-request limit'
                )
        return v


class SafetyGuardrails(BaseModel):
    """Safety configuration for an agent"""
    level: SafetyLevel = SafetyLevel.MODERATE
    block_pii: bool = True
    block_profanity: bool = True
    require_human_review: bool = False
    max_consecutive_errors: int = Field(default=3, ge=1, le=10)
    auto_disable_on_error: bool = True
    allowed_domains: Optional[List[str]] = None
    blocked_keywords: Optional[List[str]] = None


class PromptTemplate(BaseModel):
    """Agent prompt configuration"""
    system_prompt: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="System prompt that defines agent behavior"
    )
    user_prompt_template: Optional[str] = Field(
        default=None,
        max_length=5000
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)

    @validator('system_prompt')
    def validate_system_prompt(cls, v):
        # Check for potentially dangerous patterns
        dangerous_patterns = ['exec(', 'eval(', '__import__', 'subprocess', 'os.system']
        for pattern in dangerous_patterns:
            if pattern.lower() in v.lower():
                raise ValueError(
                    f'System prompt contains potentially dangerous code: {pattern}'
                )
        return v.strip()


class AgentSettingsUpdate(BaseModel):
    """Complete agent settings update model"""
    agent_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name for the agent"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000
    )
    status: AgentStatus = AgentStatus.ACTIVE
    model: ModelType = ModelType.CLAUDE_SONNET
    risk_tier: RiskTier = RiskTier.TIER_2
    prompt_template: PromptTemplate
    token_limits: TokenLimits = TokenLimits()
    safety_guardrails: SafetyGuardrails = SafetyGuardrails()
    enable_memory: bool = True
    enable_tools: bool = True
    allowed_tools: Optional[List[str]] = None
    requires_approval: bool = False
    elite_status: bool = False

    @validator('allowed_tools')
    def validate_tools(cls, v, values):
        if values.get('enable_tools') and (not v or len(v) == 0):
            raise ValueError('Must specify allowed_tools when enable_tools is True')
        return v


class AgentTestRequest(BaseModel):
    """Request model for testing agent configuration"""
    test_input: str = Field(..., min_length=1, max_length=1000)
    variables: Optional[Dict[str, str]] = None


class BulkStatusUpdate(BaseModel):
    """Bulk status update request"""
    agent_ids: List[int] = Field(..., min_items=1, max_items=50)
    new_status: AgentStatus
    reason: Optional[str] = None


# =============================================================================
# COST ESTIMATION
# =============================================================================

# Pricing per 1K tokens (approximate)
MODEL_PRICING = {
    ModelType.GPT4_TURBO: {"input": 0.01, "output": 0.03},
    ModelType.GPT4: {"input": 0.03, "output": 0.06},
    ModelType.GPT35_TURBO: {"input": 0.0005, "output": 0.0015},
    ModelType.CLAUDE_SONNET: {"input": 0.003, "output": 0.015},
    ModelType.CLAUDE_OPUS: {"input": 0.015, "output": 0.075},
    ModelType.CLAUDE_HAIKU: {"input": 0.00025, "output": 0.00125},
}


def calculate_cost_estimate(settings: AgentSettingsUpdate) -> Dict[str, Any]:
    """Calculate estimated monthly cost for agent configuration"""
    pricing = MODEL_PRICING.get(settings.model, {"input": 0.01, "output": 0.03})

    # Estimate based on daily limit or per-request limit
    if settings.token_limits.max_tokens_per_day:
        daily_tokens = settings.token_limits.max_tokens_per_day
    else:
        # Assume 100 requests per day with 50% input/output ratio
        daily_tokens = settings.token_limits.max_tokens_per_request * 100

    # Assume 40% input, 60% output ratio
    daily_input_tokens = daily_tokens * 0.4
    daily_output_tokens = daily_tokens * 0.6

    daily_cost = (daily_input_tokens / 1000 * pricing["input"]) + \
                 (daily_output_tokens / 1000 * pricing["output"])
    monthly_cost = daily_cost * 30

    return {
        "estimated_monthly_cost": round(monthly_cost, 2),
        "estimated_daily_cost": round(daily_cost, 2),
        "monthly_tokens": int(daily_tokens * 30),
        "model": settings.model.value,
        "cost_per_1k_input": pricing["input"],
        "cost_per_1k_output": pricing["output"],
    }


def validate_configuration(settings: AgentSettingsUpdate) -> List[str]:
    """Validate configuration and return warnings"""
    warnings = []

    # Warn about high-cost models
    if settings.model in [ModelType.GPT4, ModelType.CLAUDE_OPUS]:
        cost = calculate_cost_estimate(settings)
        if cost['estimated_monthly_cost'] > 500:
            warnings.append(
                f"High estimated monthly cost (${cost['estimated_monthly_cost']:.2f}). "
                "Consider using a more cost-effective model for high-volume operations."
            )

    # Warn about permissive safety with tools enabled
    if settings.enable_tools and settings.safety_guardrails.level == SafetyLevel.PERMISSIVE:
        warnings.append(
            "Tools enabled with permissive safety level. "
            "Consider using at least moderate safety for production."
        )

    # Warn about Tier 1 without approval
    if settings.risk_tier == RiskTier.TIER_1 and not settings.requires_approval:
        warnings.append(
            "High-risk agent (Tier 1) without approval requirement. "
            "Consider enabling requires_approval for safety."
        )

    # Warn about elite status without Tier 3
    if settings.elite_status and settings.risk_tier != RiskTier.TIER_3:
        warnings.append(
            "Elite status typically requires Tier 3 (low risk) classification."
        )

    return warnings


# =============================================================================
# AUTH DEPENDENCY
# =============================================================================

class _UserWithPermissions:
    """Wraps user object to add has_permission for agent governance endpoints."""
    _DEFAULT_PERMISSIONS = ["view_agents", "manage_agents", "test_agents", "approve_high_cost"]

    def __init__(self, user):
        self._user = user

    def __getattr__(self, name):
        return getattr(self._user, name)

    def has_permission(self, permission: str) -> bool:
        if hasattr(self._user, 'has_permission'):
            return self._user.has_permission(permission)
        role = (getattr(self._user, 'role', '') or '').lower()
        perm_role = (getattr(self._user, 'permission_role', '') or '').lower()
        is_admin = getattr(self._user, 'is_admin', False)
        if role in ('admin', 'owner', 'site_admin') or perm_role in ('admin', 'owner', 'site_admin') or is_admin:
            return True
        return permission in self._DEFAULT_PERMISSIONS


async def get_current_user(request: Request = None, db: Session = Depends(get_db)):
    """Auth dependency using real auth from main, wrapped with permission support."""
    from main import get_current_user as _main_auth
    from fastapi.security import OAuth2PasswordBearer
    _scheme = OAuth2PasswordBearer(tokenUrl="token")
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    user = await _main_auth(token=token, request=request, db=db)
    return _UserWithPermissions(user)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("/agents")
async def list_agent_settings(
    status: Optional[AgentStatus] = None,
    category: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all agents with their current configuration.

    This endpoint demonstrates:
    - Permission checking
    - Query filtering
    - Structured response format
    """
    # Permission check
    if not current_user.has_permission("view_agents"):
        raise PermissionException(
            "You don't have permission to view agent configurations",
            required_permission="view_agents"
        )

    try:
        # Build query
        query = """
            SELECT
                id, agent_name, display_name, description, category,
                status, health_status, model, config,
                tool_count, risk_tier, elite_status, requires_approval,
                total_executions, success_rate, avg_response_time_ms,
                last_execution_at, updated_at
            FROM agent_profiles
            WHERE 1=1
        """
        params = {}

        if status:
            query += " AND status = :status"
            params["status"] = status.value

        if category:
            query += " AND category = :category"
            params["category"] = category

        query += " ORDER BY display_name ASC"

        result = db.execute(text(query), params)
        agents = []

        for row in result:
            agent_dict = {
                "id": row.id,
                "agent_name": row.agent_name,
                "display_name": row.display_name,
                "description": row.description,
                "category": row.category,
                "status": row.status,
                "health_status": row.health_status,
                "model": row.model if hasattr(row, 'model') else "claude-sonnet-4",
                "tool_count": row.tool_count,
                "risk_tier": row.risk_tier,
                "elite_status": row.elite_status,
                "requires_approval": row.requires_approval,
                "total_executions": row.total_executions,
                "success_rate": float(row.success_rate) if row.success_rate else 0,
                "avg_response_time_ms": float(row.avg_response_time_ms) if row.avg_response_time_ms else 0,
                "last_execution_at": row.last_execution_at.isoformat() if row.last_execution_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            agents.append(agent_dict)

        return success_response(
            data={"agents": agents, "total": len(agents)},
            message=f"Retrieved {len(agents)} agents"
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error listing agents: {str(e)}", exc_info=True)
        raise DatabaseException("Failed to retrieve agents")


@router.get("/agents/{agent_id}")
async def get_agent_settings(
    agent_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed configuration for a specific agent.

    Demonstrates:
    - Parameter validation
    - Not found handling
    - Cost estimation calculation
    """
    if not current_user.has_permission("view_agents"):
        raise PermissionException()

    try:
        result = db.execute(
            text("""
                SELECT * FROM agent_profiles WHERE id = :agent_id
            """),
            {"agent_id": agent_id}
        )
        row = result.fetchone()

        if not row:
            raise NotFoundException(
                f"Agent with ID {agent_id} not found",
                resource_type="agent",
                resource_id=str(agent_id)
            )

        # Build response
        agent_data = {
            "id": row.id,
            "agent_name": row.agent_name,
            "display_name": row.display_name,
            "description": row.description,
            "category": row.category,
            "status": row.status,
            "health_status": row.health_status,
            "version": row.version,
            "model": getattr(row, 'model', 'claude-sonnet-4'),
            "config": row.config or {},
            "tool_count": row.tool_count,
            "risk_tier": row.risk_tier,
            "elite_status": row.elite_status,
            "requires_approval": row.requires_approval,
            "total_executions": row.total_executions,
            "successful_executions": row.successful_executions,
            "failed_executions": row.failed_executions,
            "success_rate": float(row.success_rate) if row.success_rate else 0,
            "avg_response_time_ms": float(row.avg_response_time_ms) if row.avg_response_time_ms else 0,
            "last_execution_at": row.last_execution_at.isoformat() if row.last_execution_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

        # Calculate cost estimate if we have config data
        cost_estimate = None
        config = row.config or {}
        if config.get('token_limits'):
            try:
                mock_settings = AgentSettingsUpdate(
                    agent_name=row.display_name or row.agent_name,
                    model=ModelType(config.get('model', 'claude-sonnet-4')),
                    prompt_template=PromptTemplate(
                        system_prompt=config.get('system_prompt', 'Default prompt')
                    ),
                    token_limits=TokenLimits(**config.get('token_limits', {})),
                )
                cost_estimate = calculate_cost_estimate(mock_settings)
            except Exception:
                pass  # Cost estimate is optional

        return success_response(
            data={
                "agent": agent_data,
                "cost_estimate": cost_estimate,
                "statistics": {
                    "total_executions": row.total_executions,
                    "successful_executions": row.successful_executions,
                    "failed_executions": row.failed_executions,
                    "success_rate": float(row.success_rate) if row.success_rate else 0,
                },
            },
            message="Agent configuration retrieved"
        )

    except NotFoundException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error getting agent {agent_id}: {str(e)}", exc_info=True)
        raise DatabaseException("Failed to retrieve agent configuration")


@router.put("/agents/{agent_id}")
async def update_agent_settings(
    agent_id: int,
    settings: AgentSettingsUpdate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update agent configuration with comprehensive validation.

    This is the primary endpoint demonstrating all error handling patterns:
    - Permission checks
    - Input validation (Pydantic)
    - Business logic validation
    - Database transactions with rollback
    - Cost estimation
    - Warning system
    - Comprehensive logging
    """
    # 1. Permission check
    if not current_user.has_permission("manage_agents"):
        logger.warning(
            f"Permission denied: user {current_user.id} attempted to update agent {agent_id}"
        )
        raise PermissionException(
            "You don't have permission to modify agent configurations",
            required_permission="manage_agents"
        )

    try:
        # 2. Verify agent exists
        result = db.execute(
            text("SELECT id, agent_name FROM agent_profiles WHERE id = :agent_id"),
            {"agent_id": agent_id}
        )
        row = result.fetchone()

        if not row:
            raise NotFoundException(
                f"Agent with ID {agent_id} not found",
                resource_type="agent",
                resource_id=str(agent_id)
            )

        # 3. Validate configuration and get warnings
        warnings = validate_configuration(settings)

        # 4. Calculate cost estimate
        cost_estimate = calculate_cost_estimate(settings)

        # 5. Check cost budget
        if cost_estimate['estimated_monthly_cost'] > 1000:
            if not current_user.has_permission("approve_high_cost"):
                raise BusinessRuleException(
                    f"Estimated monthly cost ${cost_estimate['estimated_monthly_cost']:.2f} "
                    "exceeds $1000 limit. Requires approval from an administrator.",
                    rule_code="COST_LIMIT_EXCEEDED"
                )

        # 6. Database transaction
        try:
            # Build config JSON
            config_json = {
                "model": settings.model.value,
                "system_prompt": settings.prompt_template.system_prompt,
                "user_prompt_template": settings.prompt_template.user_prompt_template,
                "temperature": settings.prompt_template.temperature,
                "top_p": settings.prompt_template.top_p,
                "token_limits": settings.token_limits.dict(),
                "safety_guardrails": settings.safety_guardrails.dict(),
                "enable_memory": settings.enable_memory,
                "enable_tools": settings.enable_tools,
                "allowed_tools": settings.allowed_tools,
            }

            # Update agent
            db.execute(
                text("""
                    UPDATE agent_profiles SET
                        display_name = :display_name,
                        description = :description,
                        status = :status,
                        risk_tier = :risk_tier,
                        elite_status = :elite_status,
                        requires_approval = :requires_approval,
                        config = :config,
                        updated_at = :updated_at
                    WHERE id = :agent_id
                """),
                {
                    "agent_id": agent_id,
                    "display_name": settings.agent_name,
                    "description": settings.description,
                    "status": settings.status.value,
                    "risk_tier": settings.risk_tier.value,
                    "elite_status": settings.elite_status,
                    "requires_approval": settings.requires_approval,
                    "config": config_json,
                    "updated_at": datetime.now(timezone.utc),
                }
            )

            db.commit()

            # 7. Log success
            logger.info(
                f"Agent configuration updated: {agent_id}",
                extra={
                    "agent_id": agent_id,
                    "user_id": current_user.id,
                    "status": settings.status.value,
                    "model": settings.model.value,
                    "estimated_monthly_cost": cost_estimate['estimated_monthly_cost'],
                }
            )

            # 8. Return success with data
            response_data = {
                "agent": {
                    "id": agent_id,
                    "agent_name": row.agent_name,
                    "display_name": settings.agent_name,
                    "status": settings.status.value,
                    "model": settings.model.value,
                },
                "cost_estimate": cost_estimate,
            }

            if warnings:
                response_data["warnings"] = warnings

            return success_response(
                data=response_data,
                message="Agent configuration updated successfully"
            )

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(
                f"Database error updating agent {agent_id}: {str(e)}",
                extra={"agent_id": agent_id, "user_id": current_user.id},
                exc_info=True
            )
            raise DatabaseException(
                "Failed to save agent configuration. Please try again."
            )

    except (ValidationException, PermissionException, NotFoundException,
            DatabaseException, BusinessRuleException):
        raise
    except SQLAlchemyError as e:
        logger.error(
            f"Unexpected error updating agent {agent_id}: {str(e)}",
            extra={"agent_id": agent_id, "user_id": current_user.id},
            exc_info=True
        )
        raise DatabaseException(
            "An unexpected error occurred while updating agent configuration"
        )


@router.post("/agents/{agent_id}/test")
async def test_agent_configuration(
    agent_id: int,
    test_request: AgentTestRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Test agent configuration with sample input.

    Demonstrates async operation with test results.
    """
    if not current_user.has_permission("test_agents"):
        raise PermissionException(
            "You don't have permission to test agents",
            required_permission="test_agents"
        )

    # Verify agent exists
    result = db.execute(
        text("SELECT id, agent_name, config FROM agent_profiles WHERE id = :agent_id"),
        {"agent_id": agent_id}
    )
    row = result.fetchone()

    if not row:
        raise NotFoundException(f"Agent with ID {agent_id} not found")

    # For demo purposes, simulate a test response
    # In production, this would call the actual agent
    import random

    test_result = {
        "response": f"Test response for: {test_request.test_input[:50]}...",
        "tokens_used": random.randint(100, 500),
        "latency_ms": random.randint(200, 1500),
        "cost": round(random.uniform(0.001, 0.05), 4),
        "success": True,
        "errors": [],
    }

    logger.info(
        f"Agent test completed: {agent_id}",
        extra={
            "agent_id": agent_id,
            "user_id": current_user.id,
            "tokens_used": test_result["tokens_used"],
        }
    )

    return success_response(
        data=test_result,
        message="Agent test completed successfully"
    )


@router.post("/agents/bulk-status")
async def bulk_update_status(
    bulk_request: BulkStatusUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update status for multiple agents at once.

    Demonstrates bulk operation handling.
    """
    if not current_user.has_permission("manage_agents"):
        raise PermissionException()

    updated = []
    failed = []

    for agent_id in bulk_request.agent_ids:
        try:
            result = db.execute(
                text("""
                    UPDATE agent_profiles
                    SET status = :status, updated_at = :updated_at
                    WHERE id = :agent_id
                    RETURNING id
                """),
                {
                    "agent_id": agent_id,
                    "status": bulk_request.new_status.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            if result.rowcount > 0:
                updated.append(agent_id)
            else:
                failed.append({"id": agent_id, "error": "Agent not found"})

        except Exception as e:
            failed.append({"id": agent_id, "error": "Internal server error"})

    db.commit()

    logger.info(
        f"Bulk status update: {len(updated)} updated, {len(failed)} failed",
        extra={
            "user_id": current_user.id,
            "new_status": bulk_request.new_status.value,
            "updated_count": len(updated),
        }
    )

    return success_response(
        data={
            "updated": updated,
            "failed": failed,
            "summary": {
                "total_requested": len(bulk_request.agent_ids),
                "updated": len(updated),
                "failed": len(failed),
            }
        },
        message=f"Updated {len(updated)} agents"
    )


@router.get("/models")
async def list_available_models(
    current_user=Depends(get_current_user),
):
    """
    List available AI models with pricing information.
    """
    models = []
    for model in ModelType:
        pricing = MODEL_PRICING.get(model, {"input": 0.01, "output": 0.03})
        models.append({
            "id": model.value,
            "name": model.value.replace("-", " ").title(),
            "pricing": {
                "input_per_1k": pricing["input"],
                "output_per_1k": pricing["output"],
            },
            "recommended": model in [ModelType.CLAUDE_SONNET, ModelType.GPT4_TURBO],
        })

    return success_response(
        data={"models": models},
        message=f"Retrieved {len(models)} available models"
    )


@router.get("/cost-estimate")
async def calculate_agent_cost(
    model: ModelType,
    tokens_per_day: int = 10000,
    current_user=Depends(get_current_user),
):
    """
    Calculate estimated cost for given model and usage.
    """
    pricing = MODEL_PRICING.get(model, {"input": 0.01, "output": 0.03})

    daily_input_tokens = tokens_per_day * 0.4
    daily_output_tokens = tokens_per_day * 0.6

    daily_cost = (daily_input_tokens / 1000 * pricing["input"]) + \
                 (daily_output_tokens / 1000 * pricing["output"])

    return success_response(
        data={
            "model": model.value,
            "tokens_per_day": tokens_per_day,
            "estimated_daily_cost": round(daily_cost, 2),
            "estimated_monthly_cost": round(daily_cost * 30, 2),
            "estimated_yearly_cost": round(daily_cost * 365, 2),
        },
        message="Cost estimate calculated"
    )
