"""A/B testing routes — create experiments, assign variants, record results, view analysis."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import get_db
from services.ab_test_service import get_ab_test_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ab-tests", tags=["ab-testing"])


class VariantConfig(BaseModel):
    name: str
    description: str = ""
    is_control: bool = False
    traffic_allocation: float = 50.0
    config: dict = {}


class CreateExperimentRequest(BaseModel):
    name: str
    experiment_type: str  # call_script, sms_template, email_subject, drip_sequence
    primary_metric: str  # contact_rate, appointment_rate, response_rate, conversion_rate
    variants: List[VariantConfig]
    description: str = ""
    min_sample_size: int = 100
    confidence_level: float = 0.95


class RecordResultRequest(BaseModel):
    variant_id: int
    metric_name: str
    metric_value: float


class AssignVariantRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/experiments")
async def create_experiment(request: CreateExperimentRequest, db=Depends(get_db)):
    """Create a new A/B experiment with variants."""
    service = get_ab_test_service()
    result = service.create_experiment(
        db=db,
        name=request.name,
        experiment_type=request.experiment_type,
        primary_metric=request.primary_metric,
        variants=[v.dict() for v in request.variants],
        description=request.description,
        min_sample_size=request.min_sample_size,
        confidence_level=request.confidence_level,
    )
    return result


@router.post("/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: int, db=Depends(get_db)):
    """Start an experiment (move from draft to running)."""
    service = get_ab_test_service()
    return service.start_experiment(db, experiment_id)


@router.post("/experiments/{experiment_id}/assign")
async def assign_variant(experiment_id: int, request: AssignVariantRequest, db=Depends(get_db)):
    """Assign a user/session to a variant."""
    service = get_ab_test_service()
    return service.assign_variant(db, experiment_id, request.user_id, request.session_id)


@router.post("/experiments/{experiment_id}/results")
async def record_result(experiment_id: int, request: RecordResultRequest, db=Depends(get_db)):
    """Record a metric result for a variant."""
    service = get_ab_test_service()
    return service.record_result(db, experiment_id, request.variant_id,
                                 request.metric_name, request.metric_value)


@router.get("/experiments/{experiment_id}/results")
async def get_results(experiment_id: int, db=Depends(get_db)):
    """Get experiment results with statistical analysis."""
    service = get_ab_test_service()
    return service.get_results(db, experiment_id)


@router.get("/experiments")
async def list_experiments(status: Optional[str] = None, db=Depends(get_db)):
    """List all experiments, optionally filtered by status."""
    from sqlalchemy import text
    params = {}
    status_filter = ""
    if status:
        status_filter = "WHERE status = :status"
        params["status"] = status

    try:
        rows = db.execute(text(f"""
            SELECT e.id, e.name, e.experiment_type, e.status, e.primary_metric,
                   e.started_at, e.ended_at,
                   (SELECT COUNT(*) FROM ab_variants WHERE experiment_id = e.id) as variant_count,
                   (SELECT COUNT(*) FROM ab_assignments WHERE experiment_id = e.id) as total_assignments
            FROM ab_experiments e
            {status_filter}
            ORDER BY e.created_at DESC
        """), params).mappings().all()

        return {
            "experiments": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": r["experiment_type"],
                    "status": r["status"],
                    "primary_metric": r["primary_metric"],
                    "variant_count": r["variant_count"],
                    "total_assignments": r["total_assignments"],
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.warning(f"List experiments failed: {e}")
        return {"experiments": [], "error": str(e)}
