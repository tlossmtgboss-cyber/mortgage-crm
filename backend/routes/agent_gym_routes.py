"""
Agent Gym API Routes
Perennia AI - IBMA

Provides endpoints for:
- Training scenario management
- Training session execution
- Agent skill assessment
- Performance benchmarking
- Leaderboards
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from database import get_db

from services.agent_gym_service import AgentGymService
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/agents/gym",
    tags=["agent-gym"],
    dependencies=[Depends(_get_current_user())],
)


# ============================================================================
# Pydantic Models
# ============================================================================

class ScenarioCreate(BaseModel):
    """Request model for creating a training scenario."""
    name: str = Field(..., description="Scenario name")
    description: str = Field(..., description="Scenario description")
    agent_type: str = Field(..., description="Target agent type")
    difficulty: str = Field(..., description="Difficulty: beginner, intermediate, advanced, expert")
    scenario_data: Dict[str, Any] = Field(..., description="Scenario input data and context")
    expected_outcomes: Dict[str, Any] = Field(..., description="Expected results for evaluation")
    time_limit_seconds: Optional[int] = None
    tags: Optional[List[str]] = None


class ScenarioUpdate(BaseModel):
    """Request model for updating a training scenario."""
    name: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    scenario_data: Optional[Dict[str, Any]] = None
    expected_outcomes: Optional[Dict[str, Any]] = None
    time_limit_seconds: Optional[int] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class SessionStart(BaseModel):
    """Request model for starting a training session."""
    agent_id: str = Field(..., description="Agent ID to train")
    initiated_by: Optional[str] = None


class SessionComplete(BaseModel):
    """Request model for completing a training session."""
    results: Dict[str, Any] = Field(..., description="Session results data")
    score: float = Field(..., ge=0, le=100, description="Score (0-100)")
    passed: bool = Field(..., description="Whether the agent passed")
    feedback: Optional[str] = None


class SessionFail(BaseModel):
    """Request model for marking a session as failed."""
    error: str = Field(..., description="Error message")


class ScenarioResponse(BaseModel):
    """Response model for training scenario."""
    id: str
    name: str
    description: str
    agent_type: str
    difficulty: str
    scenario_data: Dict[str, Any]
    expected_outcomes: Dict[str, Any]
    time_limit_seconds: Optional[int]
    tags: List[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Response model for training session."""
    id: str
    agent_id: str
    scenario_id: str
    status: str
    score: Optional[float]
    passed: Optional[bool]
    duration_seconds: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# Training Scenario Routes
# ============================================================================

@router.get("/scenarios")
async def list_scenarios(
    agent_type: Optional[str] = Query(None, description="Filter by target agent type"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: bool = Query(True),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """List training scenarios with optional filtering."""
    try:
        service = AgentGymService(db)
        result = service.list_scenarios(
            agent_type=agent_type,
            difficulty=difficulty,
            is_active=is_active,
            limit=limit,
            offset=offset
        )
        # Transform scenarios to match expected response format
        scenarios = []
        for scenario in result["scenarios"]:
            scenarios.append({
                "id": str(scenario.id),
                "name": scenario.name,
                "description": scenario.description or "",
                "category": scenario.category or "",
                "agent_type": scenario.target_agent_type or "",
                "target_agent_type": scenario.target_agent_type or "",
                "difficulty": scenario.difficulty or "medium",
                "scenario_data": scenario.input_data or {},
                "input_data": scenario.input_data or {},
                "expected_outcomes": scenario.expected_output or {},
                "expected_output": scenario.expected_output or {},
                "time_limit_seconds": scenario.time_limit_seconds,
                "max_score": scenario.max_score or 100,
                "is_active": scenario.is_active,
                "times_run": scenario.times_run or 0,
                "avg_score": scenario.avg_score,
                "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
                "updated_at": scenario.updated_at.isoformat() if scenario.updated_at else None,
            })
        return scenarios
    except Exception as e:
        logger.warning(f"Scenarios query failed (tables may not exist): {e}")
        return []


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific training scenario."""
    service = AgentGymService(db)
    scenario = service.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@router.post("/scenarios", response_model=ScenarioResponse)
async def create_scenario(
    scenario: ScenarioCreate,
    created_by: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Create a new training scenario."""
    try:
        service = AgentGymService(db)
        new_scenario = service.create_training_scenario(
            name=scenario.name,
            description=scenario.description,
            agent_type=scenario.agent_type,
            difficulty=scenario.difficulty,
            scenario_data=scenario.scenario_data,
            expected_outcomes=scenario.expected_outcomes,
            time_limit_seconds=scenario.time_limit_seconds,
            tags=scenario.tags,
            created_by=created_by
        )
        return new_scenario
    except Exception as e:
        logger.error(f"Error creating scenario: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def update_scenario(
    scenario_id: str,
    scenario: ScenarioUpdate,
    db: Session = Depends(get_db)
):
    """Update a training scenario."""
    service = AgentGymService(db)
    updates = scenario.dict(exclude_unset=True)
    updated = service.update_scenario(scenario_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return updated


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(
    scenario_id: str,
    db: Session = Depends(get_db)
):
    """Soft delete a training scenario."""
    service = AgentGymService(db)
    success = service.delete_scenario(scenario_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"status": "success", "message": "Scenario deactivated"}


@router.get("/scenarios/{scenario_id}/stats")
async def get_scenario_stats(
    scenario_id: str,
    db: Session = Depends(get_db)
):
    """Get statistics for a training scenario."""
    service = AgentGymService(db)
    stats = service.get_scenario_stats(scenario_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return stats


# ============================================================================
# Training Session Routes
# ============================================================================

@router.post("/scenarios/{scenario_id}/start")
async def start_training_session(
    scenario_id: str,
    session_data: SessionStart,
    db: Session = Depends(get_db)
):
    """Start a new training session for an agent."""
    try:
        service = AgentGymService(db)
        session = service.start_training_session(
            agent_id=session_data.agent_id,
            scenario_id=scenario_id,
            initiated_by=session_data.initiated_by
        )
        return {
            "status": "success",
            "session_id": session.id,
            "scenario_id": scenario_id,
            "agent_id": session_data.agent_id,
            "started_at": session.started_at
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except SQLAlchemyError as e:
        logger.error(f"Error starting session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/complete")
async def complete_training_session(
    session_id: str,
    completion: SessionComplete,
    db: Session = Depends(get_db)
):
    """Complete a training session with results."""
    try:
        service = AgentGymService(db)
        session = service.complete_training_session(
            session_id=session_id,
            results=completion.results,
            score=completion.score,
            passed=completion.passed,
            feedback=completion.feedback
        )
        return {
            "status": "success",
            "session_id": session.id,
            "score": session.score,
            "passed": session.passed,
            "duration_seconds": session.duration_seconds
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except SQLAlchemyError as e:
        logger.error(f"Error completing session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/fail")
async def fail_training_session(
    session_id: str,
    failure: SessionFail,
    db: Session = Depends(get_db)
):
    """Mark a training session as failed."""
    try:
        service = AgentGymService(db)
        session = service.fail_training_session(session_id, failure.error)
        return {
            "status": "success",
            "session_id": session.id,
            "session_status": session.status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except SQLAlchemyError as e:
        logger.error(f"Error failing session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions")
async def list_training_sessions(
    agent_id: Optional[str] = Query(None),
    scenario_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    days: int = Query(30, le=90),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """List training sessions with filtering."""
    try:
        service = AgentGymService(db)
        result = service.list_training_sessions(
            agent_id=agent_id,
            scenario_id=scenario_id,
            status=status,
            days=days,
            limit=limit,
            offset=offset
        )
        return result["sessions"]
    except Exception as e:
        logger.warning(f"Training sessions query failed: {e}")
        return []


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_training_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific training session."""
    service = AgentGymService(db)
    session = service.get_training_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ============================================================================
# Agent Assessment Routes
# ============================================================================

@router.get("/agents/{agent_id}/assessment")
async def assess_agent_skills(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Get comprehensive skill assessment for an agent."""
    service = AgentGymService(db)
    assessment = service.assess_agent_skills(agent_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Agent not found")
    return assessment


@router.get("/agents/{agent_id}/recommended-scenarios")
async def get_recommended_scenarios(
    agent_id: str,
    limit: int = Query(5, le=20),
    db: Session = Depends(get_db)
):
    """Get recommended training scenarios for an agent."""
    service = AgentGymService(db)
    scenarios = service.get_recommended_scenarios(agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "recommended_scenarios": scenarios
    }


# ============================================================================
# Benchmarking Routes
# ============================================================================

@router.get("/agents/{agent_id}/benchmark")
async def benchmark_agent(
    agent_id: str,
    scenario_ids: Optional[str] = Query(None, description="Comma-separated scenario IDs"),
    db: Session = Depends(get_db)
):
    """Run benchmark assessment on an agent."""
    service = AgentGymService(db)
    scenario_list = scenario_ids.split(",") if scenario_ids else None
    benchmark = service.benchmark_agent(agent_id, scenario_ids=scenario_list)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Agent not found")
    return benchmark


@router.get("/leaderboard")
async def get_leaderboard(
    agent_type: Optional[str] = Query(None),
    scenario_id: Optional[str] = Query(None),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """Get training leaderboard."""
    try:
        service = AgentGymService(db)
        leaderboard = service.get_leaderboard(
            agent_type=agent_type,
            scenario_id=scenario_id,
            limit=limit
        )
        return {
            "filters": {"agent_type": agent_type, "scenario_id": scenario_id},
            "leaderboard": leaderboard
        }
    except Exception as e:
        logger.warning(f"Leaderboard query failed: {e}")
        return {"filters": {"agent_type": agent_type, "scenario_id": scenario_id}, "leaderboard": []}


# ============================================================================
# Scenario Generation Route
# ============================================================================

@router.post("/scenarios/generate-from-execution")
async def generate_scenario_from_execution(
    execution_id: str = Query(..., description="Execution ID to generate scenario from"),
    difficulty: str = Query("intermediate", description="Difficulty level for generated scenario"),
    db: Session = Depends(get_db)
):
    """Generate a training scenario from a real execution."""
    try:
        service = AgentGymService(db)
        scenario = service.generate_scenario_from_execution(execution_id, difficulty)
        if not scenario:
            raise HTTPException(status_code=404, detail="Execution not found")
        return {
            "status": "success",
            "scenario_id": scenario.id,
            "name": scenario.name,
            "message": "Scenario generated from execution"
        }
    except Exception as e:
        logger.error(f"Error generating scenario: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Seed Default Scenarios Route
# ============================================================================

@router.post("/seed-defaults")
async def seed_default_scenarios(
    db: Session = Depends(get_db)
):
    """Seed default training scenarios for the system."""
    service = AgentGymService(db)

    default_scenarios = [
        {
            "name": "Pipeline Health Check",
            "description": "Analyze pipeline metrics and identify at-risk loans",
            "agent_type": "pipeline_analyst",
            "category": "benchmark",
            "difficulty": "beginner",
            "scenario_data": {
                "input": {"task": "Analyze current pipeline health"},
                "context": {"loan_count": 50, "at_risk_count": 5}
            },
            "expected_outcomes": {
                "success": True,
                "expected_tools": ["get_pipeline_metrics", "get_bottleneck_analysis"]
            }
        },
        {
            "name": "TRID Compliance Check",
            "description": "Check loan for TRID compliance violations",
            "agent_type": "compliance_checker",
            "category": "benchmark",
            "difficulty": "intermediate",
            "scenario_data": {
                "input": {"loan_id": "test-loan-1", "task": "Check TRID compliance"},
                "context": {"loan_type": "conventional", "days_since_app": 2}
            },
            "expected_outcomes": {
                "success": True,
                "expected_tools": ["check_trid_compliance", "get_disclosure_timeline"]
            }
        },
        {
            "name": "Lead Scoring Assessment",
            "description": "Score and prioritize a new lead",
            "agent_type": "lead_nurturer",
            "category": "benchmark",
            "difficulty": "beginner",
            "scenario_data": {
                "input": {"lead_id": "test-lead-1", "task": "Score lead and suggest followup"},
                "context": {"source": "website", "days_since_contact": 3}
            },
            "expected_outcomes": {
                "success": True,
                "expected_tools": ["score_lead", "suggest_followup"]
            }
        },
        {
            "name": "Document Collection Strategy",
            "description": "Identify missing documents and create collection plan",
            "agent_type": "document_tracker",
            "category": "benchmark",
            "difficulty": "intermediate",
            "scenario_data": {
                "input": {"loan_id": "test-loan-2", "task": "Get missing documents and plan collection"},
                "context": {"loan_status": "processing", "docs_collected": 5}
            },
            "expected_outcomes": {
                "success": True,
                "expected_tools": ["get_missing_documents", "get_loan_conditions"]
            }
        },
        {
            "name": "Complex Pipeline Analysis",
            "description": "Perform deep analysis of pipeline bottlenecks with recommendations",
            "agent_type": "pipeline_analyst",
            "category": "advanced",
            "difficulty": "advanced",
            "scenario_data": {
                "input": {"task": "Identify bottlenecks and provide recommendations"},
                "context": {"loan_count": 200, "branches": 5, "time_period_days": 90}
            },
            "expected_outcomes": {
                "success": True,
                "expected_tools": ["get_pipeline_metrics", "get_bottleneck_analysis", "compare_to_benchmark"]
            }
        }
    ]

    created = []
    skipped = []

    for scenario_data in default_scenarios:
        # Check if scenario with same name exists
        existing = service.list_scenarios(agent_type=scenario_data["agent_type"])
        existing_names = [s.name for s in existing["scenarios"]]

        if scenario_data["name"] in existing_names:
            skipped.append(scenario_data["name"])
            continue

        scenario = service.create_training_scenario(
            name=scenario_data["name"],
            description=scenario_data["description"],
            agent_type=scenario_data["agent_type"],
            difficulty=scenario_data["difficulty"],
            scenario_data=scenario_data["scenario_data"],
            expected_outcomes=scenario_data["expected_outcomes"],
            category=scenario_data.get("category", "benchmark")
        )
        created.append(scenario.id)

    return {
        "status": "success",
        "created": len(created),
        "skipped": len(skipped),
        "created_ids": created,
        "skipped_names": skipped
    }
