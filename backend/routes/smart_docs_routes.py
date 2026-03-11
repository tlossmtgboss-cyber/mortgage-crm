"""
Smart Document Collection API Routes

Thin router that includes all Smart Docs sub-routers:
- smart_docs_crud_routes: Needs list, upload/download, merge, templates, queue, dashboard
- smart_docs_approval_routes: Review, approve, reject, re-request, extraction
- smart_docs_requests_routes: Custom requests, waive, type updates, portal, admin, diagnostics
- smart_docs_followup_routes: Follow-up campaigns, appointments, templates
- smart_docs_review_routes: AI document review, review queue, validation, completeness
- smart_docs_analytics_routes: Document analytics dashboard, SLA, AI perf, trends, bottlenecks

Pydantic models and shared helpers live in smart_docs_models.py.
"""

from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from routes.smart_docs_crud_routes import router as crud_router
from routes.smart_docs_approval_routes import router as approval_router
from routes.smart_docs_requests_routes import router as requests_router
from routes.smart_docs_followup_routes import router as followup_router
from routes.smart_docs_review_routes import router as review_router
from routes.smart_docs_analytics_routes import router as analytics_router

router = APIRouter(
    prefix="/api/v1/smart-docs",
    tags=["Smart Documents"],
    dependencies=[Depends(get_current_user)],
)

# Include all sub-routers (they share the same prefix via this parent)
router.include_router(crud_router)
router.include_router(approval_router)
router.include_router(requests_router)
router.include_router(followup_router)
router.include_router(review_router)
router.include_router(analytics_router)
