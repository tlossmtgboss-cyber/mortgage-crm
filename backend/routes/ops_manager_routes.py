"""
Operations Manager Routes

Endpoints for triggering pipeline sweeps, viewing impediment summaries,
and reviewing sweep history.

Endpoints:
  POST /api/v1/ops-manager/sweep    - Trigger full pipeline sweep
  GET  /api/v1/ops-manager/summary  - Current impediment counts by category
  GET  /api/v1/ops-manager/history  - Sweep run history
"""

import logging
from datetime import datetime
from fastapi import Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def register_ops_manager_routes(app, get_db, get_current_user, **kwargs):
    """Register operations manager routes and ensure ops_sweep_results table exists."""

    # Create tracking table if it doesn't exist
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS ops_sweep_results (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    sweep_type VARCHAR(50) NOT NULL DEFAULT 'full',
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    duration_seconds NUMERIC(10,2),
                    leads_scanned INTEGER DEFAULT 0,
                    loans_scanned INTEGER DEFAULT 0,
                    mum_scanned INTEGER DEFAULT 0,
                    impediments_found INTEGER DEFAULT 0,
                    tasks_created INTEGER DEFAULT 0,
                    tasks_skipped_dedup INTEGER DEFAULT 0,
                    impediment_breakdown JSONB DEFAULT '{}',
                    dry_run BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.commit()
            logger.info("ops_sweep_results table ready")
        except Exception as e:
            db.rollback()
            logger.warning(f"ops_sweep_results table creation skipped: {e}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not initialize ops_sweep_results table: {e}")

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
        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent
            from agents.specialized.base import AgentContext

            org_id = organization_id or getattr(current_user, "organization_id", None)

            context = {
                "user_id": str(getattr(current_user, "id", "system")),
                "user_email": getattr(current_user, "email", ""),
                "user_role": getattr(current_user, "role", "admin"),
                "_shared_db": db,
            }

            agent = OpsManagerAgent(context)
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
            logger.exception(f"Pipeline sweep failed: {e}")
            raise HTTPException(status_code=500, detail="Pipeline sweep failed")

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
        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent
            from agents.specialized.base import AgentContext

            org_id = organization_id or getattr(current_user, "organization_id", None)

            context = {
                "user_id": str(getattr(current_user, "id", "system")),
                "user_email": getattr(current_user, "email", ""),
                "user_role": getattr(current_user, "role", "admin"),
                "_shared_db": db,
            }

            agent = OpsManagerAgent(context)
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
            logger.exception(f"Impediment summary failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to get impediment summary")

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
        try:
            from agents.specialized.ops_manager_agent import OpsManagerAgent
            from agents.specialized.base import AgentContext

            org_id = organization_id or getattr(current_user, "organization_id", None)

            context = {
                "user_id": str(getattr(current_user, "id", "system")),
                "user_email": getattr(current_user, "email", ""),
                "user_role": getattr(current_user, "role", "admin"),
                "_shared_db": db,
            }

            agent = OpsManagerAgent(context)
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
            logger.exception(f"Sweep history failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to get sweep history")
