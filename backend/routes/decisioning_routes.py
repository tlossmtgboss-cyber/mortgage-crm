"""
Real-Time Pipeline Decisioning Routes

Provides LOs with a morning dashboard showing next-best-action,
compliance risk, and close probability for every loan in pipeline.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/decisioning", tags=["Pipeline Decisioning"])


def register_decisioning_routes(app, get_db_func, get_current_user_func):
    from services.pipeline_decisioning import PipelineDecisioningService

    @router.get("/pipeline")
    async def get_pipeline_decisions(
        limit: int = Query(50, ge=1, le=200),
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")

        service = PipelineDecisioningService(db, org_id, str(current_user.id))
        decisions = service.get_pipeline_decisions(limit=limit)
        return {
            "count": len(decisions),
            "loans": [d.to_dict() for d in decisions],
        }

    @router.get("/summary")
    async def get_pipeline_summary(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")

        service = PipelineDecisioningService(db, org_id, str(current_user.id))
        return service.get_dashboard_summary()

    app.include_router(router)
