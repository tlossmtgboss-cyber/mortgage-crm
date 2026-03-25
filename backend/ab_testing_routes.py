"""
A/B Testing API Routes
Endpoints for creating, managing, and analyzing experiments

SEC-004 FIX: All queries now filter by organization_id from the authenticated
user to prevent cross-tenant enumeration and data injection.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from database import get_db
from routes.auth_deps import require_auth, current_user_flexible_dep
from ab_testing_models import Experiment, ExperimentType, ExperimentStatus
from ab_testing.experiment_service import ExperimentService
from ab_testing.statistical_analysis import StatisticalAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/experiments", tags=["A/B Testing"], dependencies=[Depends(require_auth)])


# ============================================================================
# HELPERS
# ============================================================================

def _get_org_id(current_user) -> int:
    """Extract organization_id from current user, raising 403 if missing."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context available")
    return org_id


def _get_experiment_for_org(db: Session, experiment_id: int, org_id: int) -> Experiment:
    """Fetch an experiment scoped to the caller's org, raising 404 if not found."""
    experiment = db.query(Experiment).filter(
        Experiment.id == experiment_id,
        Experiment.organization_id == org_id,
    ).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class VariantCreate(BaseModel):
    """Variant configuration for creating an experiment"""
    name: str = Field(..., description="Variant name (e.g., 'Control', 'Treatment A')")
    description: Optional[str] = None
    is_control: bool = Field(default=False, description="Is this the control/baseline variant?")
    traffic_allocation: float = Field(default=50.0, ge=0, le=100, description="% of traffic (must sum to 100)")
    config: Dict[str, Any] = Field(..., description="Variant configuration (depends on experiment type)")


class ExperimentCreate(BaseModel):
    """Create a new A/B test experiment"""
    name: str = Field(..., description="Experiment name")
    description: str = Field(..., description="Detailed description")
    experiment_type: str = Field(..., description="Type: prompt, model, agent_config, feature, ui, workflow")
    primary_metric: str = Field(..., description="Primary metric to optimize (e.g., 'resolution_rate')")
    secondary_metrics: Optional[List[str]] = Field(default=[], description="Additional metrics to track")
    variants: List[VariantCreate] = Field(..., min_items=2, description="List of variants (minimum 2)")
    target_percentage: float = Field(default=100.0, ge=0, le=100, description="% of users to include")
    min_sample_size: int = Field(default=100, ge=10, description="Minimum samples before declaring winner")
    confidence_level: float = Field(default=0.95, ge=0.8, le=0.99, description="Statistical confidence (0.95 = 95%)")


class RecordResultRequest(BaseModel):
    """Record an experiment result"""
    experiment_name: str
    metric_name: str
    metric_value: float
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class GetVariantRequest(BaseModel):
    """Get variant assignment for a user"""
    experiment_name: str
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_experiment(
    experiment_data: ExperimentCreate,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """
    Create a new A/B test experiment

    Example:
    ```json
    {
      "name": "Lead Qualification Prompt Test",
      "description": "Testing new prompt with few-shot examples",
      "experiment_type": "prompt",
      "primary_metric": "resolution_rate",
      "secondary_metrics": ["satisfaction_score", "response_time"],
      "variants": [
        {
          "name": "Control",
          "is_control": true,
          "traffic_allocation": 50.0,
          "config": {"system_prompt": "Current prompt..."}
        },
        {
          "name": "Treatment A",
          "is_control": false,
          "traffic_allocation": 50.0,
          "config": {"system_prompt": "New prompt with examples..."}
        }
      ],
      "target_percentage": 100.0,
      "min_sample_size": 100,
      "confidence_level": 0.95
    }
    ```
    """
    org_id = _get_org_id(current_user)

    try:
        service = ExperimentService(db, organization_id=org_id)

        # Convert experiment_type string to enum
        try:
            exp_type = ExperimentType[experiment_data.experiment_type.upper()]
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid experiment_type. Must be one of: {[e.value for e in ExperimentType]}"
            )

        # Convert variants to dict format
        variants = [v.dict() for v in experiment_data.variants]

        logger.info(f"Creating experiment: name={experiment_data.name}, type={exp_type}, variants={len(variants)}, org_id={org_id}")

        experiment = service.create_experiment(
            name=experiment_data.name,
            description=experiment_data.description,
            experiment_type=exp_type,
            primary_metric=experiment_data.primary_metric,
            variants=variants,
            secondary_metrics=experiment_data.secondary_metrics,
            target_percentage=experiment_data.target_percentage,
            min_sample_size=experiment_data.min_sample_size,
            confidence_level=experiment_data.confidence_level
        )

        if not experiment:
            logger.error("ExperimentService.create_experiment returned None - check service logs for details")
            raise HTTPException(status_code=500, detail="Failed to create experiment - service returned None")

        return {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status.value,
            "message": "Experiment created successfully. Use /start endpoint to begin."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating experiment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{experiment_id}/start")
async def start_experiment(
    experiment_id: int,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Start an experiment (begin collecting data)"""
    org_id = _get_org_id(current_user)

    try:
        # Verify experiment belongs to caller's org before mutating
        _get_experiment_for_org(db, experiment_id, org_id)

        service = ExperimentService(db, organization_id=org_id)
        success = service.start_experiment(experiment_id)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to start experiment")

        return {"message": f"Experiment {experiment_id} started successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting experiment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: int,
    declare_winner: bool = False,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Stop an experiment and optionally declare a winner"""
    org_id = _get_org_id(current_user)

    try:
        # Verify experiment belongs to caller's org before mutating
        _get_experiment_for_org(db, experiment_id, org_id)

        service = ExperimentService(db, organization_id=org_id)
        success = service.stop_experiment(experiment_id, declare_winner=declare_winner)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to stop experiment")

        return {"message": f"Experiment {experiment_id} stopped successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping experiment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/get-variant")
async def get_variant(
    request: GetVariantRequest,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """
    Get variant assignment for a user/session

    Use this endpoint to determine which variant a user should see.
    The assignment is consistent (same user always gets same variant).
    """
    org_id = _get_org_id(current_user)

    try:
        service = ExperimentService(db, organization_id=org_id)
        variant = service.get_variant_for_user(
            experiment_name=request.experiment_name,
            user_id=request.user_id,
            session_id=request.session_id,
            context=request.context
        )

        if not variant:
            return {
                "in_experiment": False,
                "message": "User not in experiment or experiment not running"
            }

        return {
            "in_experiment": True,
            "variant": variant
        }

    except Exception as e:
        logger.error(f"Error getting variant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/record-result")
async def record_result(
    request: RecordResultRequest,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """
    Record an experiment result/outcome

    Call this when you measure the primary or secondary metric.
    Example: After AI responds, record resolution_rate, satisfaction_score, etc.
    """
    org_id = _get_org_id(current_user)

    try:
        service = ExperimentService(db, organization_id=org_id)
        success = service.record_result(
            experiment_name=request.experiment_name,
            metric_name=request.metric_name,
            metric_value=request.metric_value,
            user_id=request.user_id,
            session_id=request.session_id,
            context=request.context
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to record result")

        return {"message": "Result recorded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording result: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{experiment_id}/analyze")
async def analyze_experiment(
    experiment_id: int,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """
    Perform statistical analysis on experiment results

    Returns p-value, significance, and winner recommendation
    """
    org_id = _get_org_id(current_user)

    try:
        # Verify experiment belongs to caller's org before analyzing
        _get_experiment_for_org(db, experiment_id, org_id)

        analyzer = StatisticalAnalyzer(db, organization_id=org_id)
        insight = analyzer.analyze_experiment(experiment_id)

        if not insight:
            raise HTTPException(status_code=404, detail="No data available for analysis")

        return {
            "experiment_id": experiment_id,
            "analysis_date": insight.analysis_date.isoformat(),
            "variant_stats": insight.variant_stats,
            "p_value": insight.p_value,
            "is_significant": insight.is_significant,
            "recommended_winner_id": insight.recommended_winner_id,
            "recommendation_confidence": insight.recommendation_confidence,
            "recommendation_reason": insight.recommendation_reason,
            "sufficient_sample_size": insight.sufficient_sample_size,
            "current_sample_size": insight.current_sample_size,
            "required_sample_size": insight.required_sample_size
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing experiment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{experiment_id}/summary")
async def get_experiment_summary(
    experiment_id: int,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """
    Get human-readable summary of experiment results
    """
    org_id = _get_org_id(current_user)

    try:
        # Verify experiment belongs to caller's org before returning data
        _get_experiment_for_org(db, experiment_id, org_id)

        analyzer = StatisticalAnalyzer(db, organization_id=org_id)
        summary = analyzer.get_experiment_summary(experiment_id)

        if not summary:
            raise HTTPException(status_code=404, detail="Experiment not found")

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting experiment summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/")
async def list_experiments(
    status_filter: Optional[str] = None,
    experiment_type: Optional[str] = None,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """List all experiments with optional filtering (scoped to caller's org)"""
    org_id = _get_org_id(current_user)

    try:
        query = db.query(Experiment).filter(
            Experiment.organization_id == org_id,
        )

        if status_filter:
            try:
                status_enum = ExperimentStatus[status_filter.upper()]
                query = query.filter(Experiment.status == status_enum)
            except KeyError:
                pass

        if experiment_type:
            try:
                type_enum = ExperimentType[experiment_type.upper()]
                query = query.filter(Experiment.experiment_type == type_enum)
            except KeyError:
                pass

        experiments = query.order_by(Experiment.created_at.desc()).all()

        return {
            "experiments": [
                {
                    "id": exp.id,
                    "name": exp.name,
                    "description": exp.description,
                    "type": exp.experiment_type.value,
                    "status": exp.status.value,
                    "primary_metric": exp.primary_metric,
                    "created_at": exp.created_at.isoformat(),
                    "started_at": exp.started_at.isoformat() if exp.started_at else None,
                    "ended_at": exp.ended_at.isoformat() if exp.ended_at else None
                }
                for exp in experiments
            ],
            "count": len(experiments)
        }

    except Exception as e:
        logger.error(f"Error listing experiments: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: int,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Get detailed information about an experiment"""
    org_id = _get_org_id(current_user)

    try:
        from ab_testing_models import ExperimentVariant

        experiment = _get_experiment_for_org(db, experiment_id, org_id)

        variants = db.query(ExperimentVariant).filter(
            ExperimentVariant.experiment_id == experiment_id
        ).all()

        return {
            "id": experiment.id,
            "name": experiment.name,
            "description": experiment.description,
            "type": experiment.experiment_type.value,
            "status": experiment.status.value,
            "primary_metric": experiment.primary_metric,
            "secondary_metrics": experiment.secondary_metrics,
            "target_percentage": experiment.target_percentage,
            "min_sample_size": experiment.min_sample_size,
            "confidence_level": experiment.confidence_level,
            "created_at": experiment.created_at.isoformat(),
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "ended_at": experiment.ended_at.isoformat() if experiment.ended_at else None,
            "winning_variant_id": experiment.winning_variant_id,
            "variants": [
                {
                    "id": v.id,
                    "name": v.name,
                    "description": v.description,
                    "is_control": v.is_control,
                    "traffic_allocation": v.traffic_allocation,
                    "config": v.config
                }
                for v in variants
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting experiment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{experiment_id}")
async def delete_experiment(
    experiment_id: int,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Delete an experiment (only if DRAFT or ARCHIVED)"""
    org_id = _get_org_id(current_user)

    try:
        experiment = _get_experiment_for_org(db, experiment_id, org_id)

        if experiment.status not in [ExperimentStatus.DRAFT, ExperimentStatus.ARCHIVED]:
            raise HTTPException(
                status_code=400,
                detail="Can only delete DRAFT or ARCHIVED experiments"
            )

        db.delete(experiment)
        db.commit()

        return {"message": f"Experiment {experiment_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting experiment: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
