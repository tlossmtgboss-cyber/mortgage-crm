"""
Agent Performance Metrics Routes

Admin-only REST API for viewing AI agent invocation metrics.

Endpoints:
    GET /api/admin/agent-metrics           Summary dashboard
    GET /api/admin/agent-metrics/tools     Per-tool performance breakdown
    GET /api/admin/agent-metrics/errors    Error pattern analysis
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from utils.response import success_response, error_response, ErrorCodes
import logging

logger = logging.getLogger(__name__)


def register_agent_metrics_routes(app, get_db, get_current_user, **kwargs):
    """
    Register agent metrics admin routes.

    Args:
        app: FastAPI application instance.
        get_db: Database session dependency.
        get_current_user: Auth dependency returning current User.
    """

    # -----------------------------------------------------------------------
    # Lazy imports inside the registration function to avoid circular deps
    # -----------------------------------------------------------------------
    from services.agent_metrics_service import (
        get_metrics_summary,
        get_slow_tools,
        get_error_patterns,
    )

    def _require_admin(current_user):
        """Raise 403 if the user is not a platform or site admin."""
        role = getattr(current_user, "role", None)
        if role not in ("Platform Admin", "Site Admin", "platform_admin", "site_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

    # -----------------------------------------------------------------------
    # GET /api/admin/agent-metrics — Summary
    # -----------------------------------------------------------------------
    @app.get("/api/admin/agent-metrics", tags=["Agent Metrics"])
    async def get_agent_metrics_summary(
        days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
        organization_id: Optional[int] = Query(default=None, description="Filter by organization"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Return aggregate agent performance metrics.

        Includes total invocations, success rate, average duration,
        breakdowns by agent role and tool, and error distribution.
        """
        _require_admin(current_user)

        try:
            summary = get_metrics_summary(
                db=db,
                org_id=organization_id,
                days=days,
            )
            return success_response(data=summary)
        except Exception as e:
            logger.exception(f"Failed to retrieve agent metrics summary: {e}")
            return error_response(
                code=ErrorCodes.INTERNAL_ERROR,
                message="Failed to retrieve agent metrics",
                status_code=500,
            )

    # -----------------------------------------------------------------------
    # GET /api/admin/agent-metrics/tools — Per-tool breakdown
    # -----------------------------------------------------------------------
    @app.get("/api/admin/agent-metrics/tools", tags=["Agent Metrics"])
    async def get_agent_metrics_tools(
        threshold_ms: int = Query(default=5000, ge=0, le=60000, description="Duration threshold in ms"),
        days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
        organization_id: Optional[int] = Query(default=None, description="Filter by organization"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Return tools that exceed the duration threshold.

        Useful for identifying slow tools that may need optimization or
        timeout adjustments.
        """
        _require_admin(current_user)

        try:
            slow_tools = get_slow_tools(
                db=db,
                threshold_ms=threshold_ms,
                org_id=organization_id,
                days=days,
            )
            return success_response(data={"threshold_ms": threshold_ms, "slow_tools": slow_tools})
        except Exception as e:
            logger.exception(f"Failed to retrieve slow tools: {e}")
            return error_response(
                code=ErrorCodes.INTERNAL_ERROR,
                message="Failed to retrieve tool metrics",
                status_code=500,
            )

    # -----------------------------------------------------------------------
    # GET /api/admin/agent-metrics/errors — Error analysis
    # -----------------------------------------------------------------------
    @app.get("/api/admin/agent-metrics/errors", tags=["Agent Metrics"])
    async def get_agent_metrics_errors(
        days: int = Query(default=7, ge=1, le=90, description="Lookback window in days"),
        organization_id: Optional[int] = Query(default=None, description="Filter by organization"),
        limit: int = Query(default=20, ge=1, le=100, description="Max error patterns to return"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Return the most common error patterns.

        Groups errors by tool, agent role, status, and error message to
        help diagnose recurring failures.
        """
        _require_admin(current_user)

        try:
            patterns = get_error_patterns(
                db=db,
                days=days,
                org_id=organization_id,
                limit=limit,
            )
            return success_response(data={"period_days": days, "error_patterns": patterns})
        except Exception as e:
            logger.exception(f"Failed to retrieve error patterns: {e}")
            return error_response(
                code=ErrorCodes.INTERNAL_ERROR,
                message="Failed to retrieve error patterns",
                status_code=500,
            )

    # -----------------------------------------------------------------------
    # GET /api/admin/agent-metrics/response-times — Real-time response time percentiles
    # -----------------------------------------------------------------------
    @app.get("/api/admin/agent-metrics/response-times", tags=["Agent Metrics"])
    async def get_response_time_stats(
        current_user=Depends(get_current_user),
    ):
        """
        Return real-time response time percentiles from in-memory tracker.

        Includes p50, p75, p90, p95, p99 plus breakdowns by intent and model.
        Data is from the current server process lifetime (not persisted).
        """
        _require_admin(current_user)

        try:
            from agents.orchestration.performance_tracker import get_response_time_tracker
            stats = get_response_time_tracker().get_stats()
            return success_response(data=stats)
        except Exception as e:
            logger.exception(f"Failed to retrieve response time stats: {e}")
            return error_response(
                code=ErrorCodes.INTERNAL_ERROR,
                message="Failed to retrieve response time stats",
                status_code=500,
            )
