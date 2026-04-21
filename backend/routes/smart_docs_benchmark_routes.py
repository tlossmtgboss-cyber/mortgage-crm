"""
Smart Docs AI Benchmark Routes

Admin-only endpoints for managing AI classification accuracy benchmarks.
Provides dataset management, sample collection, benchmark execution,
accuracy trends, confusion matrices, and confidence calibration.

Endpoints:
    POST /benchmark/datasets                      - Create benchmark dataset
    POST /benchmark/datasets/{id}/collect          - Auto-collect from corrections
    POST /benchmark/datasets/{id}/run              - Run benchmark evaluation
    GET  /benchmark/accuracy-trend                 - Accuracy trend over time
    GET  /benchmark/confusion-matrix               - Confusion matrix
    GET  /benchmark/calibration                    - Confidence calibration
    GET  /benchmark/report                         - Full benchmark report
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from database.models.ai_benchmark import AIBenchmarkDataset
from services.smart_docs.ai_benchmarking_service import AIBenchmarkingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Benchmarking"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CreateDatasetRequest(BaseModel):
    """Request body for creating a benchmark dataset."""
    name: str = Field(..., min_length=1, max_length=255, description="Dataset name")
    description: Optional[str] = Field(None, max_length=1000, description="Optional description")


class AddSampleRequest(BaseModel):
    """Request body for manually adding a labeled sample."""
    document_hash: str = Field(..., min_length=1, max_length=64)
    actual_doc_type: str = Field(..., min_length=1, max_length=50)
    actual_category: str = Field("", max_length=50)
    metadata: Optional[dict] = None


# =============================================================================
# HELPERS
# =============================================================================

def _get_org_id(current_user) -> Optional[int]:
    """Extract organization_id from the authenticated user."""
    return getattr(current_user, "organization_id", None)


def _require_admin(current_user):
    """Verify the user has admin privileges."""
    role = getattr(current_user, "role", "")
    if role not in ("Platform Admin", "Site Admin", "Admin", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")


# =============================================================================
# DATASET MANAGEMENT
# =============================================================================

@router.post("/benchmark/datasets")
async def create_benchmark_dataset(
    body: CreateDatasetRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new benchmark dataset for organizing labeled samples."""
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = AIBenchmarkingService(db)
        dataset_id = service.create_benchmark_dataset(
            org_id=org_id,
            name=body.name,
            description=body.description,
        )
        db.commit()

        return {
            "status": "success",
            "dataset_id": dataset_id,
            "message": f"Dataset '{body.name}' created",
        }
    except Exception as e:
        db.rollback()
        logger.exception("Failed to create benchmark dataset")
        raise HTTPException(status_code=500, detail="Failed to create benchmark dataset")


@router.post("/benchmark/datasets/{dataset_id}/samples")
async def add_labeled_sample(
    dataset_id: int,
    body: AddSampleRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually add a labeled sample to a benchmark dataset."""
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Verify dataset belongs to the org
    dataset = db.query(AIBenchmarkDataset).filter(
        AIBenchmarkDataset.id == dataset_id,
        AIBenchmarkDataset.organization_id == org_id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        service = AIBenchmarkingService(db)
        sample_id = service.add_labeled_sample(
            dataset_id=dataset_id,
            document_hash=body.document_hash,
            actual_doc_type=body.actual_doc_type,
            actual_category=body.actual_category,
            metadata=body.metadata,
            source="manual_label",
        )
        db.commit()

        return {
            "status": "success",
            "sample_id": sample_id,
            "message": "Sample added to dataset",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Failed to add benchmark sample")
        raise HTTPException(status_code=500, detail="Failed to add benchmark sample")


# =============================================================================
# AUTO-COLLECTION
# =============================================================================

@router.post("/benchmark/datasets/{dataset_id}/collect")
async def collect_from_corrections(
    dataset_id: int,
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Auto-collect labeled samples from human corrections.

    Scans AIDocumentClassification records where humans marked predictions
    as incorrect and provided the correct type. Adds these as labeled
    samples to the specified benchmark dataset.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Verify dataset
    dataset = db.query(AIBenchmarkDataset).filter(
        AIBenchmarkDataset.id == dataset_id,
        AIBenchmarkDataset.organization_id == org_id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        service = AIBenchmarkingService(db)
        collected = service.auto_collect_from_corrections(
            org_id=org_id,
            days=days,
            dataset_id=dataset_id,
        )
        db.commit()

        return {
            "status": "success",
            "samples_collected": collected,
            "dataset_id": dataset_id,
            "message": f"Collected {collected} samples from corrections (last {days} days)",
        }
    except Exception as e:
        db.rollback()
        logger.exception("Failed to collect from corrections")
        raise HTTPException(status_code=500, detail="Failed to collect samples from corrections")


# =============================================================================
# BENCHMARK EXECUTION
# =============================================================================

@router.post("/benchmark/datasets/{dataset_id}/run")
async def run_benchmark(
    dataset_id: int,
    classifier_version: str = Query("current", description="Classifier version identifier"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run a benchmark evaluation against all samples in a dataset.

    Compares AI predictions against ground-truth labels and returns
    accuracy, precision, recall, F1 scores, and confusion matrix.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    dataset = db.query(AIBenchmarkDataset).filter(
        AIBenchmarkDataset.id == dataset_id,
        AIBenchmarkDataset.organization_id == org_id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        service = AIBenchmarkingService(db)
        result = service.run_benchmark(
            dataset_id=dataset_id,
            classifier_version=classifier_version,
        )
        db.commit()

        return {
            "status": "success",
            "benchmark": result.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Failed to run benchmark")
        raise HTTPException(status_code=500, detail="Failed to run benchmark")


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@router.get("/benchmark/accuracy-trend")
async def accuracy_trend(
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get daily accuracy trend based on human-reviewed classifications.

    Shows how classifier accuracy changes over time, tracking
    improvement or regression.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = AIBenchmarkingService(db)
        trend = service.get_accuracy_trend(org_id=org_id, days=days)

        return {
            "status": "success",
            "period_days": days,
            "data_points": len(trend),
            "trend": trend,
        }
    except Exception as e:
        logger.exception("Failed to get accuracy trend")
        raise HTTPException(status_code=500, detail="Failed to get accuracy trend")


@router.get("/benchmark/confusion-matrix")
async def confusion_matrix(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get confusion matrix showing which document types get confused.

    Identifies the most common misclassification pairs to help
    target classifier improvements.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = AIBenchmarkingService(db)
        result = service.get_confusion_matrix(org_id=org_id, days=days)

        return {
            "status": "success",
            **result,
        }
    except Exception as e:
        logger.exception("Failed to get confusion matrix")
        raise HTTPException(status_code=500, detail="Failed to get confusion matrix")


@router.get("/benchmark/calibration")
async def confidence_calibration(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get confidence score calibration analysis.

    Evaluates whether the classifier's confidence scores are well-calibrated.
    For example, when the classifier says 90% confidence, is it actually
    correct 90% of the time?
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = AIBenchmarkingService(db)
        result = service.get_confidence_calibration(org_id=org_id)

        return {
            "status": "success",
            **result,
        }
    except Exception as e:
        logger.exception("Failed to get calibration data")
        raise HTTPException(status_code=500, detail="Failed to get calibration data")


@router.get("/benchmark/report")
async def benchmark_report(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get comprehensive benchmark report.

    Combines overall accuracy, per-type performance, trend analysis,
    confusion highlights, calibration assessment, and actionable
    recommendations for improving classifier accuracy.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = AIBenchmarkingService(db)
        report = service.generate_benchmark_report(org_id=org_id)

        return {
            "status": "success",
            "report": report,
        }
    except Exception as e:
        logger.exception("Failed to generate benchmark report")
        raise HTTPException(status_code=500, detail="Failed to generate benchmark report")
