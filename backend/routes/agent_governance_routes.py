"""
Agent Governance API Routes
Perennia AI - IBMA

Provides endpoints for:
- Agent profile management (CRUD)
- Agent health monitoring
- Execution tracking and metrics
- Alert management
- System-wide health reporting
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import logging
import uuid

from database import get_db, engine
from routes.auth_deps import require_auth

from services.agent_governance_service import AgentGovernanceService
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agents", tags=["agent-governance"], dependencies=[Depends(require_auth)])


# ============================================================================
# Pydantic Models
# ============================================================================

class AgentProfileCreate(BaseModel):
    """Request model for creating an agent profile."""
    name: str = Field(..., description="Agent name")
    agent_type: str = Field(..., description="Type of agent (e.g., pipeline_analyst, compliance_checker)")
    description: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    version: str = Field(default="1.0.0")


class AgentProfileUpdate(BaseModel):
    """Request model for updating an agent profile."""
    name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    version: Optional[str] = None
    is_active: Optional[bool] = None


class AgentStatusUpdate(BaseModel):
    """Request model for updating agent status."""
    status: str = Field(..., description="New status: active, paused, maintenance, disabled")
    reason: Optional[str] = None


class ExecutionCreate(BaseModel):
    """Request model for recording an execution."""
    action_type: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class ExecutionComplete(BaseModel):
    """Request model for completing an execution."""
    success: bool
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    tools_used: Optional[List[str]] = None
    tokens_used: Optional[int] = None


class AlertCreate(BaseModel):
    """Request model for creating an alert."""
    alert_type: str = Field(..., description="Type: error, warning, performance, anomaly")
    severity: str = Field(default="medium", description="Severity: low, medium, high, critical")
    title: str
    message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AlertUpdate(BaseModel):
    """Request model for updating an alert."""
    status: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


class MetricRecord(BaseModel):
    """Request model for recording a metric."""
    metric_type: str
    metric_name: str
    metric_value: float
    dimensions: Optional[Dict[str, Any]] = None


class AgentProfileResponse(BaseModel):
    """Response model for agent profile."""
    id: str
    name: str
    agent_type: str
    description: Optional[str]
    status: str
    capabilities: Optional[Dict[str, Any]]
    config: Optional[Dict[str, Any]]
    version: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_active_at: Optional[datetime]

    class Config:
        from_attributes = True


class AgentExecutionResponse(BaseModel):
    """Response model for agent execution."""
    id: str
    agent_id: str
    session_id: Optional[str]
    status: str
    action_type: Optional[str]
    success: Optional[bool]
    execution_time_ms: Optional[int]
    tokens_used: Optional[int]
    tools_used: Optional[List[str]]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class AgentAlertResponse(BaseModel):
    """Response model for agent alert."""
    id: int
    agent_id: int
    agent_name: Optional[str] = None
    alert_type: str
    severity: str
    title: str
    message: Optional[str]
    status: str
    created_at: datetime
    triggered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# Database Migration
# ============================================================================

def ensure_agent_tables_exist():
    """Create agent governance tables if they don't exist."""
    try:
        with engine.connect() as conn:
            # Check if tables exist
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'agent_profiles'
                )
            """))
            exists = result.scalar()

            # Also check for training_scenarios table
            result2 = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'training_scenarios'
                )
            """))
            training_exists = result2.scalar()

            if not exists or not training_exists:
                logger.info("Creating/updating agent governance tables...")

                # Run the migration script
                from migrations.add_agent_governance_system import run_migration
                run_migration()

                logger.info("Agent governance tables created successfully")
            else:
                logger.info("Agent governance tables already exist")

    except Exception as e:
        logger.warning(f"Agent tables check warning: {e}")


# Auto-create tables on module load
try:
    ensure_agent_tables_exist()
except Exception as e:
    logger.warning(f"Could not auto-create agent tables: {e}")


# ============================================================================
# Migration Endpoint
# ============================================================================

@router.post("/migrate")
async def run_agent_migration(db: Session = Depends(get_db)):
    """
    Run agent governance database migrations.
    Call this once to set up the agent system.
    """
    try:
        ensure_agent_tables_exist()
        return {
            "status": "success",
            "message": "Agent governance tables created/verified"
        }
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Agent Profile Routes
# ============================================================================

@router.get("/profiles")
async def list_agent_profiles(
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """Get all agent profiles with optional filtering."""
    try:
        service = AgentGovernanceService(db)
        result = service.list_agents(
            agent_type=agent_type,
            status=status,
            is_active=is_active,
            limit=limit,
            offset=offset
        )
        # Transform to match frontend expectations
        profiles = []
        for agent in result["agents"]:
            profiles.append({
                "id": str(agent.get("id", "")),
                "name": agent.get("display_name") or agent.get("agent_name", ""),
                "agent_name": agent.get("agent_name", ""),
                "display_name": agent.get("display_name", ""),
                "agent_type": agent.get("category", ""),
                "category": agent.get("category", ""),
                "description": agent.get("description", ""),
                "status": agent.get("status", "active"),
                "health_status": agent.get("health_status", "healthy"),
                "version": agent.get("version", "1.0.0"),
                "is_active": agent.get("status") == "active",
                "tool_count": agent.get("tool_count", 0),
                "total_executions": agent.get("total_executions", 0),
                "success_rate": agent.get("success_rate", 0),
                "avg_response_time_ms": agent.get("avg_response_time_ms", 0),
                "last_execution_at": agent.get("last_execution_at"),
                "elite_status": agent.get("elite_status", False),
                "risk_tier": agent.get("risk_tier", "low")
            })
        return profiles
    except Exception as e:
        logger.warning(f"Agent profiles query failed (tables may not exist): {e}")
        return []


@router.get("/profiles/{agent_id}")
async def get_agent_profile(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific agent profile by ID."""
    try:
        service = AgentGovernanceService(db)
        agent = service.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Agent profile query failed: {e}")
        raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/profiles", response_model=AgentProfileResponse)
async def create_agent_profile(
    profile: AgentProfileCreate,
    db: Session = Depends(get_db)
):
    """Create a new agent profile."""
    try:
        service = AgentGovernanceService(db)
        agent = service.create_agent(
            name=profile.name,
            agent_type=profile.agent_type,
            description=profile.description,
            capabilities=profile.capabilities,
            config=profile.config,
            version=profile.version
        )
        return agent
    except Exception as e:
        logger.error(f"Error creating agent profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/profiles/{agent_id}", response_model=AgentProfileResponse)
async def update_agent_profile(
    agent_id: str,
    profile: AgentProfileUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing agent profile."""
    service = AgentGovernanceService(db)
    updates = profile.dict(exclude_unset=True)
    agent = service.update_agent(agent_id, updates)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/profiles/{agent_id}")
async def delete_agent_profile(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Soft delete an agent profile (sets is_active=False)."""
    service = AgentGovernanceService(db)
    success = service.deactivate_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "message": "Agent deactivated"}


@router.post("/profiles/{agent_id}/status")
async def update_agent_status(
    agent_id: str,
    status_update: AgentStatusUpdate,
    db: Session = Depends(get_db)
):
    """Update agent operational status."""
    service = AgentGovernanceService(db)
    agent = service.update_agent_status(
        agent_id,
        status_update.status,
        reason=status_update.reason
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {
        "status": "success",
        "agent_id": agent_id,
        "new_status": agent.status
    }


@router.get("/profiles/{agent_id}/health")
async def get_agent_health(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Get health status for a specific agent."""
    service = AgentGovernanceService(db)
    health = service.get_agent_health(agent_id)
    if not health:
        raise HTTPException(status_code=404, detail="Agent not found")
    return health


# ============================================================================
# Execution Tracking Routes
# ============================================================================

@router.post("/profiles/{agent_id}/executions")
async def start_execution(
    agent_id: str,
    execution: ExecutionCreate,
    db: Session = Depends(get_db)
):
    """Start tracking a new execution for an agent."""
    try:
        service = AgentGovernanceService(db)
        exec_record = service.start_execution(
            agent_id=agent_id,
            action_type=execution.action_type,
            input_data=execution.input_data,
            context=execution.context
        )
        return {
            "status": "success",
            "execution_id": exec_record.id,
            "session_id": exec_record.session_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Error starting execution: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/executions/{execution_id}/complete")
async def complete_execution(
    execution_id: str,
    completion: ExecutionComplete,
    db: Session = Depends(get_db)
):
    """Complete an execution with results."""
    try:
        service = AgentGovernanceService(db)
        exec_record = service.complete_execution(
            execution_id=execution_id,
            success=completion.success,
            output_data=completion.output_data,
            error_message=completion.error_message,
            tools_used=completion.tools_used,
            tokens_used=completion.tokens_used
        )
        return {
            "status": "success",
            "execution_id": exec_record.id,
            "execution_time_ms": exec_record.execution_time_ms
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Error completing execution: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profiles/{agent_id}/executions")
async def list_agent_executions(
    agent_id: str,
    status: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    days: int = Query(7, le=90),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """Get executions for a specific agent."""
    try:
        service = AgentGovernanceService(db)
        result = service.list_executions(
            agent_id=agent_id,
            status=status,
            success=success,
            days=days,
            limit=limit,
            offset=offset
        )
        return result["executions"]
    except Exception as e:
        logger.warning(f"Executions query failed: {e}")
        return []


@router.get("/executions/{execution_id}", response_model=AgentExecutionResponse)
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific execution by ID."""
    service = AgentGovernanceService(db)
    execution = service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/executions")
async def list_all_executions(
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    days: int = Query(7, le=90),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """Get all executions across agents with filtering."""
    service = AgentGovernanceService(db)
    result = service.list_executions(
        status=status,
        success=success,
        days=days,
        limit=limit,
        offset=offset
    )
    return result


# ============================================================================
# Metrics Routes
# ============================================================================

@router.post("/profiles/{agent_id}/metrics")
async def record_metric(
    agent_id: str,
    metric: MetricRecord,
    db: Session = Depends(get_db)
):
    """Record a metric for an agent."""
    try:
        service = AgentGovernanceService(db)
        metric_record = service.record_metric(
            agent_id=agent_id,
            metric_type=metric.metric_type,
            metric_name=metric.metric_name,
            metric_value=metric.metric_value,
            dimensions=metric.dimensions
        )
        return {
            "status": "success",
            "metric_id": metric_record.id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Error recording metric: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profiles/{agent_id}/metrics")
async def get_agent_metrics(
    agent_id: str,
    metric_type: Optional[str] = Query(None),
    metric_name: Optional[str] = Query(None),
    days: int = Query(7, le=90),
    db: Session = Depends(get_db)
):
    """Get metrics for a specific agent."""
    try:
        service = AgentGovernanceService(db)
        metrics = service.get_agent_metrics(
            agent_id=agent_id,
            metric_type=metric_type,
            metric_name=metric_name,
            days=days
        )
        return metrics
    except Exception as e:
        logger.warning(f"Agent metrics query failed: {e}")
        return []


@router.get("/profiles/{agent_id}/metrics/aggregate")
async def get_aggregated_metrics(
    agent_id: str,
    metric_type: Optional[str] = Query(None),
    metric_name: Optional[str] = Query(None),
    days: int = Query(30, le=90),
    db: Session = Depends(get_db)
):
    """Get aggregated metrics for an agent."""
    try:
        service = AgentGovernanceService(db)
        aggregated = service.aggregate_metrics(
            agent_id=agent_id,
            metric_type=metric_type,
            metric_name=metric_name,
            days=days
        )
        return aggregated
    except Exception as e:
        logger.warning(f"Aggregated metrics query failed: {e}")
        return {}


# ============================================================================
# Alert Routes
# ============================================================================

@router.post("/profiles/{agent_id}/alerts")
async def create_alert(
    agent_id: str,
    alert: AlertCreate,
    db: Session = Depends(get_db)
):
    """Create an alert for an agent."""
    try:
        service = AgentGovernanceService(db)
        alert_record = service.create_alert(
            agent_id=agent_id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            context=alert.context
        )
        return {
            "status": "success",
            "alert_id": alert_record.id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts")
async def list_alerts(
    agent_id: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    days: int = Query(7, le=90),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """Get alerts with optional filtering."""
    try:
        service = AgentGovernanceService(db)
        result = service.list_alerts(
            agent_id=agent_id,
            alert_type=alert_type,
            severity=severity,
            status=status,
            days=days,
            limit=limit,
            offset=offset
        )
        return result["alerts"]
    except Exception as e:
        logger.warning(f"Alerts query failed: {e}")
        return []


@router.get("/alerts/{alert_id}", response_model=AgentAlertResponse)
async def get_alert(
    alert_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific alert by ID."""
    service = AgentGovernanceService(db)
    alert = service.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str = Query(..., description="User ID acknowledging the alert"),
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    service = AgentGovernanceService(db)
    alert = service.acknowledge_alert(alert_id, acknowledged_by)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "status": "success",
        "alert_id": alert_id,
        "acknowledged_at": alert.acknowledged_at
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolved_by: str = Query(..., description="User ID resolving the alert"),
    resolution_notes: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Resolve an alert."""
    service = AgentGovernanceService(db)
    alert = service.resolve_alert(alert_id, resolved_by, resolution_notes)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "status": "success",
        "alert_id": alert_id,
        "resolved_at": alert.resolved_at
    }


# ============================================================================
# Dashboard & Health Routes
# ============================================================================

_EMPTY_DASHBOARD = {
    "health": {"status": "unknown", "total_agents": 0, "active_agents": 0},
    "metrics": {
        "last_24h": {"total_executions": 0, "successful": 0, "failed": 0, "success_rate": 0, "total_cost": 0},
        "last_7d": {"total_executions": 0, "successful": 0, "failed": 0, "success_rate": 0, "total_cost": 0},
        "source": "none"
    },
    "top_agents": [],
    "recent_alerts": [],
}


@router.get("/governance/dashboard")
@router.get("/dashboard")
async def get_agent_dashboard(
    db: Session = Depends(get_db)
):
    """Get comprehensive agent dashboard data."""
    try:
        service = AgentGovernanceService(db)
        dashboard = service.get_dashboard_data()
        return dashboard
    except Exception as e:
        logger.warning(f"Agent dashboard query failed (tables may not exist): {e}")
        return {
            **_EMPTY_DASHBOARD,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "message": "Agent governance data not yet available"
        }


@router.get("/health")
async def get_system_health(
    db: Session = Depends(get_db)
):
    """Get overall agent system health status."""
    try:
        service = AgentGovernanceService(db)
        health = service.get_system_health()
        return health
    except Exception as e:
        logger.warning(f"System health query failed: {e}")
        return {"status": "unknown", "message": "Health data not yet available"}


@router.get("/health/summary")
async def get_health_summary(
    db: Session = Depends(get_db)
):
    """Get a quick health summary of all agents."""
    try:
        service = AgentGovernanceService(db)
        result = service.list_agents(limit=1000)
        agents = result["agents"]

        summary = {
            "total_agents": len(agents),
            "active": len([a for a in agents if a.get("status") == "active"]),
            "paused": len([a for a in agents if a.get("status") == "paused"]),
            "maintenance": len([a for a in agents if a.get("status") == "maintenance"]),
            "disabled": len([a for a in agents if a.get("status") == "disabled"]),
            "by_type": {}
        }

        for agent in agents:
            agent_type = agent.get("category", "unknown")
            if agent_type not in summary["by_type"]:
                summary["by_type"][agent_type] = {"total": 0, "active": 0}
            summary["by_type"][agent_type]["total"] += 1
            if agent.get("status") == "active":
                summary["by_type"][agent_type]["active"] += 1

        return summary
    except Exception as e:
        logger.warning(f"Health summary query failed: {e}")
        return {"total_agents": 0, "active": 0, "paused": 0, "maintenance": 0, "disabled": 0, "by_type": {}}


@router.get("/statistics")
async def get_agent_statistics(
    days: int = Query(30, le=90),
    db: Session = Depends(get_db)
):
    """Get aggregate statistics across all agents."""
    try:
        service = AgentGovernanceService(db)

        # Get execution stats
        exec_result = service.list_executions(days=days, limit=10000)
        executions = exec_result["executions"]

        total_executions = len(executions)
        successful = len([e for e in executions if e.success])
        failed = len([e for e in executions if e.success == False])

        # Calculate average execution time
        exec_times = [e.execution_time_ms for e in executions if e.execution_time_ms]
        avg_exec_time = sum(exec_times) / len(exec_times) if exec_times else 0

        # Calculate total tokens
        tokens = [e.tokens_used for e in executions if e.tokens_used]
        total_tokens = sum(tokens)

        # Get alert stats
        alert_result = service.list_alerts(days=days, limit=10000)
        alerts = alert_result["alerts"]

        return {
            "period_days": days,
            "executions": {
                "total": total_executions,
                "successful": successful,
                "failed": failed,
                "success_rate": (successful / total_executions * 100) if total_executions > 0 else 0,
                "avg_execution_time_ms": round(avg_exec_time, 2),
                "total_tokens_used": total_tokens
            },
            "alerts": {
                "total": len(alerts),
                "active": len([a for a in alerts if a.status == "active"]),
                "acknowledged": len([a for a in alerts if a.status == "acknowledged"]),
                "resolved": len([a for a in alerts if a.status == "resolved"]),
                "by_severity": {
                    "critical": len([a for a in alerts if a.severity == "critical"]),
                    "high": len([a for a in alerts if a.severity == "high"]),
                    "medium": len([a for a in alerts if a.severity == "medium"]),
                    "low": len([a for a in alerts if a.severity == "low"])
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting agent statistics: {e}")
        return {
            "period_days": days,
            "executions": {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0,
                "avg_execution_time_ms": 0,
                "total_tokens_used": 0
            },
            "alerts": {
                "total": 0,
                "active": 0,
                "acknowledged": 0,
                "resolved": 0,
                "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0}
            },
            "error": "Internal server error"
        }


# ============================================================================
# Bulk Operations Routes
# ============================================================================

@router.post("/bulk/pause")
async def bulk_pause_agents(
    agent_ids: List[str],
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Pause multiple agents at once."""
    service = AgentGovernanceService(db)
    results = {"paused": [], "failed": []}

    for agent_id in agent_ids:
        try:
            agent = service.update_agent_status(agent_id, "paused", reason=reason)
            if agent:
                results["paused"].append(agent_id)
            else:
                results["failed"].append({"id": agent_id, "error": "Not found"})
        except Exception as e:
            results["failed"].append({"id": agent_id, "error": "Internal server error"})

    return results


@router.post("/bulk/activate")
async def bulk_activate_agents(
    agent_ids: List[str],
    db: Session = Depends(get_db)
):
    """Activate multiple agents at once."""
    service = AgentGovernanceService(db)
    results = {"activated": [], "failed": []}

    for agent_id in agent_ids:
        try:
            agent = service.update_agent_status(agent_id, "active")
            if agent:
                results["activated"].append(agent_id)
            else:
                results["failed"].append({"id": agent_id, "error": "Not found"})
        except Exception as e:
            results["failed"].append({"id": agent_id, "error": "Internal server error"})

    return results


# ============================================================================
# Agent Types Route
# ============================================================================

@router.get("/types")
async def get_agent_types(
    db: Session = Depends(get_db)
):
    """Get list of available agent types with descriptions."""
    agent_types = [
        {
            "type": "pipeline_analyst",
            "name": "Pipeline Analyst",
            "description": "Analyzes loan pipeline metrics, tracks conversion rates, and identifies bottlenecks",
            "capabilities": ["pipeline_metrics", "conversion_analysis", "bottleneck_detection"]
        },
        {
            "type": "compliance_checker",
            "name": "Compliance Checker",
            "description": "Monitors regulatory compliance, TRID timelines, and fair lending requirements",
            "capabilities": ["trid_compliance", "respa_compliance", "fair_lending"]
        },
        {
            "type": "lead_nurturer",
            "name": "Lead Nurturer",
            "description": "Manages lead engagement, scoring, and follow-up recommendations",
            "capabilities": ["lead_scoring", "engagement_tracking", "follow_up_suggestions"]
        },
        {
            "type": "document_tracker",
            "name": "Document Tracker",
            "description": "Tracks document collection, conditions, and third-party orders",
            "capabilities": ["document_tracking", "condition_monitoring", "expiration_alerts"]
        },
        {
            "type": "team_coach",
            "name": "Team Coach",
            "description": "Provides performance coaching, goal tracking, and training recommendations",
            "capabilities": ["performance_analysis", "goal_tracking", "coaching_recommendations"]
        },
        {
            "type": "rate_advisor",
            "name": "Rate Advisor",
            "description": "Monitors interest rates, lock timing, and pricing optimization",
            "capabilities": ["rate_monitoring", "lock_recommendations", "pricing_analysis"]
        },
        {
            "type": "scheduler",
            "name": "Scheduler Agent",
            "description": "Manages calendar, scheduling, and appointment coordination",
            "capabilities": ["calendar_management", "appointment_scheduling", "conflict_resolution"]
        },
        {
            "type": "receptionist",
            "name": "Receptionist Agent",
            "description": "Handles initial contact, routing, and basic inquiries",
            "capabilities": ["call_routing", "inquiry_handling", "message_taking"]
        },
        {
            "type": "voice_agent",
            "name": "Voice Agent",
            "description": "Handles voice interactions and phone communications",
            "capabilities": ["voice_calls", "transcription", "sentiment_analysis"]
        },
        {
            "type": "video_agent",
            "name": "Video Agent",
            "description": "Manages video meetings and visual communications",
            "capabilities": ["video_meetings", "screen_sharing", "recording"]
        },
        {
            "type": "email_intel",
            "name": "Email Intelligence Agent",
            "description": "Analyzes email communications and extracts insights",
            "capabilities": ["email_analysis", "intent_detection", "response_suggestions"]
        },
        {
            "type": "sla_monitor",
            "name": "SLA Monitor Agent",
            "description": "Monitors SLA compliance and alerts on potential violations",
            "capabilities": ["sla_tracking", "deadline_monitoring", "escalation"]
        },
        {
            "type": "profitability",
            "name": "Profitability Agent",
            "description": "Analyzes loan profitability and pricing optimization",
            "capabilities": ["margin_analysis", "pricing_optimization", "fee_tracking"]
        },
        {
            "type": "onboarding",
            "name": "Onboarding Agent",
            "description": "Guides new users and borrowers through onboarding",
            "capabilities": ["user_onboarding", "borrower_onboarding", "checklist_tracking"]
        },
        {
            "type": "integrations",
            "name": "Integrations Agent",
            "description": "Manages external system integrations and data syncing",
            "capabilities": ["api_management", "data_sync", "error_handling"]
        },
        {
            "type": "subscription",
            "name": "Subscription Agent",
            "description": "Manages user subscriptions and billing",
            "capabilities": ["subscription_management", "billing", "usage_tracking"]
        }
    ]

    return agent_types


# ============================================================================
# Seed Default Agents Route
# ============================================================================

@router.post("/seed-defaults")
async def seed_default_agents(
    db: Session = Depends(get_db)
):
    """Seed default agent profiles for the system."""
    service = AgentGovernanceService(db)

    default_agents = [
        {
            "name": "Pipeline Analyst",
            "agent_type": "pipeline_analyst",
            "description": "Analyzes loan pipeline metrics and identifies bottlenecks",
            "capabilities": {
                "tools": ["get_pipeline_metrics", "get_loans_by_status", "get_loan_aging_report"],
                "max_concurrent_executions": 5
            }
        },
        {
            "name": "Compliance Checker",
            "agent_type": "compliance_checker",
            "description": "Monitors regulatory compliance and disclosure timelines",
            "capabilities": {
                "tools": ["check_trid_compliance", "check_respa_compliance", "audit_loan_file"],
                "max_concurrent_executions": 3
            }
        },
        {
            "name": "Lead Nurturer",
            "agent_type": "lead_nurturer",
            "description": "Manages lead engagement and follow-up sequences",
            "capabilities": {
                "tools": ["get_lead_details", "score_lead", "suggest_followup"],
                "max_concurrent_executions": 10
            }
        },
        {
            "name": "Document Tracker",
            "agent_type": "document_tracker",
            "description": "Tracks document collection and loan conditions",
            "capabilities": {
                "tools": ["get_missing_documents", "get_loan_conditions", "check_document_expiration"],
                "max_concurrent_executions": 5
            }
        }
    ]

    created = []
    skipped = []

    for agent_data in default_agents:
        # Check if agent already exists
        existing = service.list_agents(agent_type=agent_data["agent_type"])
        if existing["total"] > 0:
            skipped.append(agent_data["agent_type"])
            continue

        agent = service.create_agent(
            name=agent_data["name"],
            agent_type=agent_data["agent_type"],
            description=agent_data["description"],
            capabilities=agent_data["capabilities"]
        )
        created.append(agent.id)

    return {
        "status": "success",
        "created": len(created),
        "skipped": len(skipped),
        "created_ids": created,
        "skipped_types": skipped
    }


# ============================================================================
# Governance Settings Endpoints
# ============================================================================

class GovernanceSettingsModel(BaseModel):
    """Model for agent governance settings."""
    # System Settings
    agentGovernanceEnabled: bool = True
    autoHealthChecks: bool = True
    costTrackingEnabled: bool = True
    websocketEnabled: bool = True
    auditLogging: bool = True

    # Performance Thresholds
    defaultSuccessRate: int = 90
    defaultResponseTime: int = 15000
    defaultMaxCost: float = 0.015

    # Cost Budgets
    defaultDailyBudget: int = 50
    systemMonthlyBudget: int = 30000
    costAlertThreshold: int = 80

    # Alerts
    alertChannel: str = "Slack"
    slackWebhook: str = ""
    dailyDigest: bool = True
    digestTime: str = "8:00 AM"

    # Access Control
    requireApproval: bool = False
    viewPermissions: List[str] = ["All Users"]
    modifyPermissions: List[str] = ["Admins Only"]

    # Compliance
    enforceEliteForTier3: bool = True
    fairLendingMonitoring: bool = True
    auditRetentionDays: int = 2555

    # Integrations
    anthropicApiKey: str = ""
    webhookUrl: str = ""

    # Gym
    autoDailyTesting: bool = True
    minPassRate: int = 95
    blockOnFailedTests: bool = False


# In-memory settings storage (replace with database in production)
_governance_settings: Dict[str, Any] = {
    "agentGovernanceEnabled": True,
    "autoHealthChecks": True,
    "costTrackingEnabled": True,
    "websocketEnabled": True,
    "auditLogging": True,
    "defaultSuccessRate": 90,
    "defaultResponseTime": 15000,
    "defaultMaxCost": 0.015,
    "defaultDailyBudget": 50,
    "systemMonthlyBudget": 30000,
    "costAlertThreshold": 80,
    "alertChannel": "Slack",
    "slackWebhook": "",
    "dailyDigest": True,
    "digestTime": "8:00 AM",
    "requireApproval": False,
    "viewPermissions": ["All Users"],
    "modifyPermissions": ["Admins Only"],
    "enforceEliteForTier3": True,
    "fairLendingMonitoring": True,
    "auditRetentionDays": 2555,
    "anthropicApiKey": "",
    "webhookUrl": "",
    "autoDailyTesting": True,
    "minPassRate": 95,
    "blockOnFailedTests": False
}


@router.get("/governance/settings")
async def get_governance_settings():
    """
    Get current agent governance settings.

    Returns all system-wide configuration for agent governance.
    """
    return _governance_settings


@router.put("/governance/settings")
async def update_governance_settings(settings: GovernanceSettingsModel):
    """
    Update agent governance settings.

    Updates all system-wide configuration for agent governance.
    """
    global _governance_settings
    _governance_settings = settings.dict()

    logger.info("Agent governance settings updated")

    return {
        "status": "success",
        "message": "Agent governance settings updated successfully",
        "settings": _governance_settings
    }


# =============================================================================
# AGENT SEEDING ENDPOINT - Add Missing Agents
# =============================================================================

# All 20 required agents
REQUIRED_AGENTS = [
    {"agent_name": "receptionist", "display_name": "AI Receptionist", "description": "Voice/chat receptionist for inbound calls & queries", "category": "communication", "tools": 8},
    {"agent_name": "task_automation", "display_name": "Task Automation", "description": "Task creation, scheduling & workflow automation", "category": "operations", "tools": 9},
    {"agent_name": "profitability_analyst", "display_name": "Profitability Analyst", "description": "Loan & branch profitability analysis", "category": "analytics", "tools": 8},
    {"agent_name": "subscription_manager", "display_name": "Subscription Manager", "description": "SaaS subscription & billing management", "category": "operations", "tools": 8},
    {"agent_name": "compliance_checker", "display_name": "Compliance Checker", "description": "TRID, RESPA, fair lending compliance", "category": "compliance", "tools": 8},
    {"agent_name": "onboarding_assistant", "display_name": "Onboarding Assistant", "description": "New user onboarding & training", "category": "operations", "tools": 8},
    {"agent_name": "document_tracker", "display_name": "Document Tracker", "description": "Document collection & condition tracking", "category": "operations", "tools": 8},
    {"agent_name": "voice_agent", "display_name": "Voice OS", "description": "Voice command processing & interaction", "category": "communication", "tools": 8},
    {"agent_name": "lead_nurturer", "display_name": "Lead Nurturer", "description": "Lead scoring, follow-up & conversion", "category": "sales", "tools": 8},
    {"agent_name": "team_coach", "display_name": "Team Coach", "description": "LO performance coaching & benchmarking", "category": "analytics", "tools": 8},
    {"agent_name": "sla_monitor", "display_name": "SLA Tracker", "description": "SLA monitoring & milestone tracking", "category": "monitoring", "tools": 8},
    {"agent_name": "pipeline_analyst", "display_name": "Pipeline Analyst", "description": "Pipeline metrics, velocity & forecasting", "category": "analytics", "tools": 8},
    {"agent_name": "email_intel_agent", "display_name": "Email Intelligence", "description": "Email parsing, response & training", "category": "automation", "tools": 12},
    {"agent_name": "notification_center", "display_name": "Notification Center", "description": "Push/email/SMS notification management", "category": "automation", "tools": 8},
    {"agent_name": "customer_intelligence", "display_name": "Customer Intelligence", "description": "Customer lifecycle & retention analysis", "category": "analytics", "tools": 9},
    {"agent_name": "scheduler", "display_name": "Smart Scheduler", "description": "Intelligent meeting & calendar scheduling", "category": "operations", "tools": 8},
    {"agent_name": "video_agent", "display_name": "UVIP", "description": "Unified Video Intelligence Platform", "category": "analytics", "tools": 8},
    {"agent_name": "integrations_agent", "display_name": "Integrations", "description": "Third-party integration management", "category": "operations", "tools": 8},
    {"agent_name": "reporting_engine", "display_name": "Reporting Engine", "description": "Report generation & analytics", "category": "analytics", "tools": 8},
    {"agent_name": "rate_advisor", "display_name": "Rate Advisor", "description": "Rate lock, pricing & float-down advice", "category": "advisory", "tools": 8},
]


@router.post("/governance/setup-tables")
async def setup_agent_tables(db: Session = Depends(get_db)):
    """
    Create/update agent governance tables.
    Safe to call multiple times - uses CREATE TABLE IF NOT EXISTS and ALTER TABLE.
    """
    try:
        # Create agent_profiles table with all columns
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_profiles (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(100) UNIQUE NOT NULL,
                display_name VARCHAR(200),
                description TEXT,
                category VARCHAR(50),
                status VARCHAR(20) DEFAULT 'active',
                health_status VARCHAR(20) DEFAULT 'healthy',
                version VARCHAR(20) DEFAULT '1.0.0',
                tool_count INTEGER DEFAULT 0,
                config JSONB DEFAULT '{}',
                risk_tier VARCHAR(10) DEFAULT '2',
                elite_status BOOLEAN DEFAULT FALSE,
                requires_approval BOOLEAN DEFAULT FALSE,
                approval_threshold FLOAT DEFAULT 0.95,
                total_executions INTEGER DEFAULT 0,
                successful_executions INTEGER DEFAULT 0,
                failed_executions INTEGER DEFAULT 0,
                success_rate FLOAT DEFAULT 0,
                avg_response_time_ms FLOAT DEFAULT 0,
                total_cost DECIMAL(12,4) DEFAULT 0,
                cost_this_month DECIMAL(12,4) DEFAULT 0,
                last_execution_at TIMESTAMP WITH TIME ZONE,
                last_health_check TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Add missing columns if table already exists (idempotent)
        add_column_sqls = [
            "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS elite_status BOOLEAN DEFAULT FALSE",
            "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN DEFAULT FALSE",
            "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS approval_threshold FLOAT DEFAULT 0.95",
        ]

        for sql in add_column_sqls:
            try:
                db.execute(text(sql))
            except Exception as e:
                logger.debug(f"Skipping agent_profiles column migration: {e}")

        # Add missing columns to agent_executions
        execution_columns = [
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS user_email VARCHAR(255)",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS execution_time_ms FLOAT",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS input_text TEXT",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS input_data JSONB DEFAULT '{}'",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS output_data JSONB DEFAULT '{}'",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS trajectory JSONB DEFAULT '[]'",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS tool_calls JSONB DEFAULT '[]'",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS tokens_used INTEGER DEFAULT 0",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS total_cost NUMERIC(10,4) DEFAULT 0",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS response_time_ms INTEGER",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS success BOOLEAN",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS error_message TEXT",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE",
        ]

        for sql in execution_columns:
            try:
                db.execute(text(sql))
            except Exception as e:
                logger.debug(f"Skipping agent_executions column migration: {e}")

        # Add missing columns to agent_alerts
        alert_columns = [
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS title VARCHAR(200)",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS message TEXT",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS details JSONB DEFAULT '{}'",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS acknowledged_by_id INTEGER",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS resolved_by_id INTEGER",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS resolution_notes TEXT",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS snooze_until TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS triggered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE agent_alerts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
        ]

        for sql in alert_columns:
            try:
                db.execute(text(sql))
            except Exception as e:
                logger.debug(f"Skipping agent_alerts column migration: {e}")

        db.commit()

        logger.info("Agent governance tables created/verified")

        return {
            "status": "success",
            "message": "Agent governance tables created/verified"
        }

    except SQLAlchemyError as e:
        logger.error(f"Error creating tables: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error creating tables")


@router.post("/governance/seed-missing-agents")
async def seed_missing_agents(db: Session = Depends(get_db)):
    """
    Add any missing agents to reach the full 20 agents.

    This endpoint checks which agents are missing and creates them.
    Safe to call multiple times - only adds agents that don't exist.
    """
    from datetime import datetime
    from models.agent_governance import AgentProfile

    try:
        # Get existing agent names
        existing_agents = db.query(AgentProfile.agent_name).all()
        existing_names = {a.agent_name for a in existing_agents}

        # Find missing agents
        missing = []
        for agent_data in REQUIRED_AGENTS:
            if agent_data["agent_name"] not in existing_names:
                missing.append(agent_data)

        if not missing:
            return {
                "status": "success",
                "message": "All 20 agents already exist",
                "existing_count": len(existing_names),
                "added_count": 0,
                "agents_added": []
            }

        # Add missing agents with zeroed-out metrics (real data accumulates over time)
        added = []
        for data in missing:
            agent = AgentProfile(
                agent_name=data["agent_name"],
                display_name=data["display_name"],
                description=data["description"],
                category=data["category"],
                status="active",
                health_status="healthy",
                version="1.0.0",
                tool_count=data["tools"],
                config={
                    "model_name": "claude-3-sonnet",
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                total_executions=0,
                successful_executions=0,
                failed_executions=0,
                success_rate=0,
                avg_response_time_ms=0,
                last_execution_at=None,
                last_health_check=datetime.now(timezone.utc)
            )

            db.add(agent)
            added.append(data["display_name"])

        db.commit()

        # Get final count
        final_count = db.query(AgentProfile).count()

        logger.info(f"Added {len(added)} missing agents. Total now: {final_count}")

        return {
            "status": "success",
            "message": f"Added {len(added)} missing agents",
            "existing_count": len(existing_names),
            "added_count": len(added),
            "agents_added": added,
            "total_agents": final_count
        }

    except SQLAlchemyError as e:
        logger.error(f"Error seeding agents: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error seeding agents")
