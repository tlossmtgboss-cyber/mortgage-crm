"""
Operations Manager Routes

Endpoints for triggering pipeline sweeps, viewing impediment summaries,
reviewing sweep history, priority queues, loan health checks, and
stage transition evaluation.

Endpoints:
  POST /api/v1/ops-manager/sweep          - Trigger full pipeline sweep
  POST /api/v1/ops-manager/sweep/all      - Sweep all active orgs (platform admin / cron)
  GET  /api/v1/ops-manager/summary        - Current impediment counts by category
  GET  /api/v1/ops-manager/history        - Sweep run history
  GET  /api/v1/ops-manager/priority-queue - Daily priority queue (MustToday/ShouldToday/Strategic)
  GET  /api/v1/ops-manager/loan/{id}/health - Single-loan health check
  POST /api/v1/ops-manager/transition/evaluate - Stage transition gating
"""

import os
import logging
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Query, Path
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RBAC helper
# ---------------------------------------------------------------------------
_ADMIN_ROLES = ('admin', 'site_admin', 'platform_admin', 'super_admin', 'superadmin', 'system_admin', 'master_admin')
_PLATFORM_ADMIN_ROLES = ('admin', 'platform_admin', 'super_admin', 'superadmin', 'system_admin', 'master_admin')


def _require_ops_admin(current_user):
    """Require admin-level role for ops manager endpoints. Raises 403 if not authorized."""
    user_role = (getattr(current_user, 'role', '') or '').lower()
    perm_role = (getattr(current_user, 'permission_role', '') or '').lower()
    if user_role not in _ADMIN_ROLES and perm_role not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required for operations manager")
    return current_user


def _resolve_org_id(current_user, requested_org_id):
    """Resolve and validate organization_id. Enforces tenant isolation."""
    user_org = getattr(current_user, 'organization_id', None)
    user_role = (getattr(current_user, 'role', '') or '').lower()
    perm_role = (getattr(current_user, 'permission_role', '') or '').lower()
    is_platform = user_role in _PLATFORM_ADMIN_ROLES or perm_role in _PLATFORM_ADMIN_ROLES

    if requested_org_id and requested_org_id != user_org and not is_platform:
        raise HTTPException(status_code=403, detail="Cannot access another organization's data")
    return requested_org_id or user_org


# ---------------------------------------------------------------------------
# Rate limiting for sweep endpoint
# ---------------------------------------------------------------------------
_sweep_rate_store = {}  # {org_id: last_run_utc_timestamp}
_SWEEP_COOLDOWN_SECONDS = 300  # 5 minutes
_redis_sweep_client = None
_redis_sweep_initialized = False


def _check_sweep_rate_limit(org_id):
    """Check if sweep is rate-limited for this org. Returns remaining seconds or 0."""
    global _redis_sweep_client, _redis_sweep_initialized
    if not _redis_sweep_initialized:
        _redis_sweep_initialized = True
        try:
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                import redis
                _redis_sweep_client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
                _redis_sweep_client.ping()
        except Exception:
            _redis_sweep_client = None

    key = f"ratelimit:ops_sweep:{org_id or 'global'}"

    # Try Redis first
    if _redis_sweep_client:
        try:
            ttl = _redis_sweep_client.ttl(key)
            if ttl and ttl > 0:
                return ttl
            _redis_sweep_client.setex(key, _SWEEP_COOLDOWN_SECONDS, "1")
            return 0
        except Exception:
            pass

    # Fall back to in-memory
    now = datetime.now(timezone.utc).timestamp()
    last_run = _sweep_rate_store.get(org_id)
    if last_run:
        elapsed = now - last_run
        if elapsed < _SWEEP_COOLDOWN_SECONDS:
            return int(_SWEEP_COOLDOWN_SECONDS - elapsed)
    _sweep_rate_store[org_id] = now
    return 0


def _build_agent_context(current_user, db):
    """Build standard agent context dict."""
    return {
        "user_id": str(getattr(current_user, "id", "system")),
        "user_email": getattr(current_user, "email", ""),
        "user_role": (getattr(current_user, "role", "") or ""),
        "_shared_db": db,
    }


def register_ops_manager_routes(app, get_db, get_current_user, **kwargs):
    """Register operations manager routes."""

    # Verify ops_sweep_results table exists (created by migrations/create_ops_sweep_results.py)
    # Note: Startup table existence check -- system-level, no tenant scope
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1 FROM ops_sweep_results LIMIT 0"))
            logger.info("ops_sweep_results table verified")
        except Exception:
            logger.warning("ops_sweep_results table not found — ensure migrations have run")
        finally:
            db.close()
    except Exception:
        pass

    # ====================================================================
    # POST /api/v1/ops-manager/sweep
    # ====================================================================
    @app.post("/api/v1/ops-manager/sweep", tags=["Operations Manager"])
    async def trigger_pipeline_sweep(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        organization_id: int = None,
        dry_run: bool = False,
    ):
        """Trigger a full pipeline sweep to detect impediments and create corrective tasks."""
        _require_ops_admin(current_user)
        org_id = _resolve_org_id(current_user, organization_id)

        # Rate limit check
        retry_after = _check_sweep_rate_limit(org_id)
        if retry_after > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Sweep rate limited. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            agent = OpsManagerAgent(_build_agent_context(current_user, db))
            result = await agent.execute_tool("run_pipeline_sweep", {
                "organization_id": org_id,
                "dry_run": dry_run,
            })

            return {
                "status": "success" if result.success else "error",
                "data": result.data,
                "message": result.message,
                "error": result.error,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Pipeline sweep failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"impediments_found": 0, "tasks_created": 0, "sweep_id": None, "dry_run": dry_run},
                "message": "Ops data not yet available",
                "error": None,
            }

    # ====================================================================
    # POST /api/v1/ops-manager/sweep/all  (platform admin / cron)
    # ====================================================================
    @app.post("/api/v1/ops-manager/sweep/all", tags=["Operations Manager"])
    async def trigger_sweep_all_orgs(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        dry_run: bool = False,
    ):
        """Sweep all active organizations. Platform admin only. Designed for nightly cron."""
        _require_ops_admin(current_user)
        user_role = (getattr(current_user, 'role', '') or '').lower()
        perm_role = (getattr(current_user, 'permission_role', '') or '').lower()
        if user_role not in _PLATFORM_ADMIN_ROLES and perm_role not in _PLATFORM_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Platform admin required for sweep-all")

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            orgs = db.execute(text(
                "SELECT id FROM organizations WHERE is_active = true ORDER BY id"
            )).fetchall()

            results = []
            for org_row in orgs:
                oid = org_row.id
                try:
                    agent = OpsManagerAgent(_build_agent_context(current_user, db))
                    result = await agent.execute_tool("run_pipeline_sweep", {
                        "organization_id": oid,
                        "dry_run": dry_run,
                    })
                    results.append({
                        "organization_id": oid,
                        "status": "success" if result.success else "error",
                        "impediments_found": (result.data or {}).get("impediments_found", 0),
                        "tasks_created": (result.data or {}).get("tasks_created", 0),
                        "error": result.error,
                    })
                except Exception as org_err:
                    logger.warning(f"Sweep failed for org {oid}: {org_err}")
                    results.append({
                        "organization_id": oid,
                        "status": "error",
                        "error": str(org_err),
                    })

            total_impediments = sum(r.get("impediments_found", 0) for r in results)
            total_tasks = sum(r.get("tasks_created", 0) for r in results)

            return {
                "status": "success",
                "data": {
                    "organizations_swept": len(results),
                    "total_impediments": total_impediments,
                    "total_tasks_created": total_tasks,
                    "results": results,
                },
                "message": f"Swept {len(results)} orgs: {total_impediments} impediments, {total_tasks} tasks",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Sweep-all failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"organizations_swept": 0, "total_impediments": 0, "total_tasks_created": 0, "results": []},
                "message": "Ops data not yet available",
            }

    # ====================================================================
    # GET /api/v1/ops-manager/summary
    # ====================================================================
    @app.get("/api/v1/ops-manager/summary", tags=["Operations Manager"])
    async def get_impediment_summary(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        organization_id: int = None,
        category: str = None,
    ):
        """Get current impediment counts grouped by category and priority."""
        _require_ops_admin(current_user)
        org_id = _resolve_org_id(current_user, organization_id)

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            agent = OpsManagerAgent(_build_agent_context(current_user, db))
            result = await agent.execute_tool("get_impediment_summary", {
                "organization_id": org_id,
                "category": category,
            })

            return {
                "status": "success" if result.success else "error",
                "data": result.data,
                "message": result.message,
                "error": result.error,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Impediment summary failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"total_impediments": 0, "critical_count": 0, "warning_count": 0, "info_count": 0, "by_category": {}, "by_priority": {}},
                "message": "Ops data not yet available",
                "error": None,
            }

    # ====================================================================
    # GET /api/v1/ops-manager/history
    # ====================================================================
    @app.get("/api/v1/ops-manager/history", tags=["Operations Manager"])
    async def get_sweep_history(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        organization_id: int = None,
        limit: int = Query(default=20, le=100),
    ):
        """Get history of pipeline sweep runs."""
        _require_ops_admin(current_user)
        org_id = _resolve_org_id(current_user, organization_id)

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            agent = OpsManagerAgent(_build_agent_context(current_user, db))
            result = await agent.execute_tool("get_sweep_history", {
                "organization_id": org_id,
                "limit": limit,
            })

            return {
                "status": "success" if result.success else "error",
                "data": result.data,
                "message": result.message,
                "error": result.error,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Sweep history failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"sweeps": [], "total_count": 0},
                "message": "Ops data not yet available",
                "error": None,
            }

    # ====================================================================
    # GET /api/v1/ops-manager/priority-queue
    # ====================================================================
    @app.get("/api/v1/ops-manager/priority-queue", tags=["Operations Manager"])
    async def get_priority_queue(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        organization_id: int = None,
        assigned_to_id: int = None,
    ):
        """Get daily priority queue bucketed into MustToday / ShouldToday / Strategic."""
        _require_ops_admin(current_user)
        org_id = _resolve_org_id(current_user, organization_id)

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            agent = OpsManagerAgent(_build_agent_context(current_user, db))
            result = await agent.execute_tool("get_priority_queue", {
                "organization_id": org_id,
                "assigned_to_id": assigned_to_id,
            })

            return {
                "status": "success" if result.success else "error",
                "data": result.data,
                "message": result.message,
                "error": result.error,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Priority queue failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"must_today": [], "should_today": [], "strategic": [], "total_items": 0},
                "message": "Ops data not yet available",
                "error": None,
            }

    # ====================================================================
    # GET /api/v1/ops-manager/loan/{loan_id}/health
    # ====================================================================
    @app.get("/api/v1/ops-manager/loan/{loan_id}/health", tags=["Operations Manager"])
    async def get_loan_health(
        loan_id: int = Path(..., description="Loan ID to check"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get comprehensive health check for a single loan."""
        _require_ops_admin(current_user)

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            agent = OpsManagerAgent(_build_agent_context(current_user, db))
            result = await agent.execute_tool("check_loan_health", {
                "loan_id": loan_id,
            })

            return {
                "status": "success" if result.success else "error",
                "data": result.data,
                "message": result.message,
                "error": result.error,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Loan health check failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"loan_id": loan_id, "health_score": None, "impediments": [], "recommendations": [], "stage": None, "days_in_stage": None},
                "message": "Ops data not yet available",
                "error": None,
            }

    # ====================================================================
    # POST /api/v1/ops-manager/transition/evaluate
    # ====================================================================
    @app.post("/api/v1/ops-manager/transition/evaluate", tags=["Operations Manager"])
    async def evaluate_stage_transition(
        loan_id: int = Query(..., description="Loan ID"),
        target_stage: str = Query(..., description="Target stage to evaluate"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Evaluate whether a loan can transition to a target stage."""
        _require_ops_admin(current_user)

        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent

            agent = OpsManagerAgent(_build_agent_context(current_user, db))
            result = await agent.execute_tool("evaluate_stage_transition", {
                "loan_id": loan_id,
                "target_stage": target_stage,
            })

            return {
                "status": "success" if result.success else "error",
                "data": result.data,
                "message": result.message,
                "error": result.error,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Transition evaluation failed (tables may not exist): {e}")
            return {
                "status": "success",
                "data": {"loan_id": loan_id, "target_stage": target_stage, "allowed": False, "blockers": [], "warnings": [], "requirements_met": []},
                "message": "Ops data not yet available",
                "error": None,
            }
