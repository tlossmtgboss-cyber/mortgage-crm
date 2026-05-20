"""
Disaster Recovery Management Routes
Enterprise Readiness - Domain 8 (Checks 8.5-8.12)

Extends backup_routes.py with:
- Failover readiness validation
- Queue persistence verification
- RTO benchmarking
- Graceful degradation health
- Data retention policy management
- Archived data access for compliance
- Failover runbook API
"""

import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_async_db
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ADMIN_ROLES = ("admin", "site_admin", "platform_admin")


class RetentionPolicyUpdate(BaseModel):
    overrides: Dict[str, int]


def register_dr_routes(app, get_db, get_current_user, **kwargs):
    """
    Register disaster recovery management routes.

    All endpoints require admin-level authentication.
    """

    def _require_admin(current_user):
        role = getattr(current_user, "permission_role", "")
        if role not in ADMIN_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Admin access required for DR management",
            )
        return current_user

    # ==================================================================
    # GET /api/v1/admin/dr/failover-readiness
    # ==================================================================

    @app.get("/api/v1/admin/dr/failover-readiness")
    async def get_failover_readiness(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Validate failover readiness across all components.

        Checks WAL archiving, replication, DB latency, Redis broker,
        and connection recovery. Returns the failover runbook.
        """
        _require_admin(current_user)

        from services.failover_procedures import FailoverProcedureService

        service = FailoverProcedureService(db)
        return service.validate_failover_readiness()

    # ==================================================================
    # GET /api/v1/admin/dr/queue-persistence
    # ==================================================================

    @app.get("/api/v1/admin/dr/queue-persistence")
    async def get_queue_persistence(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Verify task queue persistence across restarts.

        Checks Celery configuration (task_acks_late, reject_on_worker_lost),
        Redis persistence (RDB/AOF), and current queue depths.
        """
        _require_admin(current_user)

        from services.failover_procedures import FailoverProcedureService

        service = FailoverProcedureService(db)
        return service.verify_queue_persistence()

    # ==================================================================
    # GET /api/v1/admin/dr/rto-benchmark
    # ==================================================================

    @app.get("/api/v1/admin/dr/rto-benchmark")
    async def get_rto_benchmark(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Measure achievable RTO by benchmarking recovery steps.

        Benchmarks DB reconnection, schema verification, integrity
        checks, and app readiness. Projects total RTO including
        Railway PITR restore time.
        """
        _require_admin(current_user)

        from services.failover_procedures import FailoverProcedureService

        service = FailoverProcedureService(db)
        return service.measure_rto_benchmark()

    # ==================================================================
    # GET /api/v1/admin/dr/degradation-health
    # ==================================================================

    @app.get("/api/v1/admin/dr/degradation-health")
    async def get_degradation_health(
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get graceful degradation status and capabilities.

        Reports current service level (full/degraded/minimal/maintenance),
        available capabilities, individual service health, and circuit
        breaker status.
        """
        _require_admin(current_user)

        try:
            import redis as redis_lib

            redis_url = __import__("os").getenv(
                "REDIS_URL", "redis://localhost:6379/0"
            )
            redis_client = redis_lib.from_url(
                redis_url, socket_timeout=5
            )
        except Exception as e:
            logger.error(f"Error connecting to Redis: {e}")
            redis_client = None

        from services.graceful_degradation import GracefulDegradation
        from services.circuit_breaker import CircuitBreaker

        # Get or create the shared circuit breaker
        breaker = CircuitBreaker(
            name="anthropic_api",
            failure_threshold=5,
            recovery_timeout=30,
        )

        degradation = GracefulDegradation(
            redis_client=redis_client,
            db=db,
            circuit_breaker=breaker,
        )

        capabilities = await degradation.get_capabilities()

        return {
            "service_level": capabilities["level"],
            "capabilities": capabilities["capabilities"],
            "health": capabilities["health"],
            "circuit_breaker": breaker.get_status(),
            "user_message": capabilities.get("message"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ==================================================================
    # GET /api/v1/admin/dr/runbook
    # ==================================================================

    @app.get("/api/v1/admin/dr/runbook")
    async def get_failover_runbook(
        current_user=Depends(get_current_user),
    ):
        """
        Get the documented failover runbook.

        Returns step-by-step procedures for database failover,
        Redis recovery, AI provider outage, and telephony outage.
        """
        _require_admin(current_user)

        from services.failover_procedures import FailoverProcedureService

        return FailoverProcedureService.get_failover_runbook()

    # ==================================================================
    # GET /api/v1/admin/dr/retention-policy
    # ==================================================================

    @app.get("/api/v1/admin/dr/retention-policy")
    async def get_retention_policy(
        organization_id: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get data retention policy.

        Returns per-table retention periods in days. If organization_id
        is provided, returns org-specific overrides merged with defaults.
        """
        _require_admin(current_user)

        from services.data_retention import DataRetentionService

        service = DataRetentionService(db)
        org_id = organization_id or getattr(
            current_user, "organization_id", None
        )
        return service.get_retention_policy(org_id)

    # ==================================================================
    # PUT /api/v1/admin/dr/retention-policy/{org_id}
    # ==================================================================

    @app.put("/api/v1/admin/dr/retention-policy/{org_id}")
    async def update_retention_policy(
        org_id: int,
        body: RetentionPolicyUpdate,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Set per-org retention policy overrides.

        Enforces regulatory minimums (7 years for loan data, 3 years
        for communications). Returns 400 if any override violates
        minimums.
        """
        _require_admin(current_user)

        from services.data_retention import DataRetentionService

        service = DataRetentionService(db)
        try:
            return service.set_retention_policy(
                organization_id=org_id,
                overrides=body.overrides,
                set_by_user_id=current_user.id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ==================================================================
    # POST /api/v1/admin/dr/retention-cleanup
    # ==================================================================

    @app.post("/api/v1/admin/dr/retention-cleanup")
    async def run_retention_cleanup(
        organization_id: Optional[int] = None,
        dry_run: bool = True,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Run retention cleanup for expired records.

        Default is dry_run=True which reports what would be cleaned
        without making changes. Set dry_run=False to execute.
        """
        _require_admin(current_user)

        from services.data_retention import DataRetentionService

        service = DataRetentionService(db)
        return service.run_retention_cleanup(
            organization_id=organization_id,
            dry_run=dry_run,
        )

    # ==================================================================
    # GET /api/v1/admin/dr/archived-loan/{loan_id}
    # ==================================================================

    @app.get("/api/v1/admin/dr/archived-loan/{loan_id}")
    async def get_archived_loan(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Retrieve archived loan data for compliance purposes.

        Returns the complete loan record including disclosures, fees,
        adverse actions, stage history, and audit trail. All data is
        retained per 7-year regulatory requirement.
        """
        _require_admin(current_user)

        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(
                status_code=400,
                detail="Organization context required",
            )

        from services.data_retention import DataRetentionService

        service = DataRetentionService(db)
        result = service.get_archived_loan_data(loan_id, org_id)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result

    # ==================================================================
    # GET /api/v1/admin/data-retention/report
    # ==================================================================

    @app.get("/api/v1/admin/data-retention/report")
    async def get_data_retention_report(
        organization_id: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get a comprehensive data retention report (dry-run preview).

        Shows what data is eligible for retention actions across both
        CRM tables and SOC 2 compliance tables, without making changes.
        Includes per-table record counts, cutoff dates, and planned
        actions (delete, redact, skip).
        """
        _require_admin(current_user)

        from services.data_retention import DataRetentionService

        service = DataRetentionService(db)
        org_id = organization_id or getattr(
            current_user, "organization_id", None
        )

        # CRM retention preview (dry run)
        crm_report = service.run_retention_cleanup(
            organization_id=org_id,
            dry_run=True,
        )

        # SOC 2 retention preview (best-effort)
        soc2_report = {}
        try:
            from soc2_compliance.services.retention_service import RetentionService

            soc2_service = RetentionService(db)
            soc2_report = {
                "preview": soc2_service.preview_retention_enforcement(),
                "status": soc2_service.get_retention_status(),
            }
        except Exception as e:
            logger.warning(f"SOC 2 retention report unavailable: {e}")
            soc2_report = {"error": str(e)}

        return {
            "crm": crm_report,
            "soc2": soc2_report,
            "policy": service.get_retention_policy(org_id),
        }

    # ==================================================================
    # POST /api/v1/admin/data-retention/enforce
    # ==================================================================

    @app.post("/api/v1/admin/data-retention/enforce")
    async def enforce_data_retention(
        dry_run: bool = True,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Manually trigger data retention enforcement.

        Dispatches the enforcement as an async Celery task so it does
        not block the request. Returns the task ID for status polling.
        Default is dry_run=True for safety.

        To execute actual enforcement, pass dry_run=false.
        """
        _require_admin(current_user)

        try:
            from tasks.data_retention_tasks import enforce_data_retention as retention_task

            task_result = retention_task.delay(dry_run=dry_run)

            return {
                "status": "dispatched",
                "task_id": task_result.id,
                "dry_run": dry_run,
                "message": (
                    "Retention enforcement dispatched as background task. "
                    f"Task ID: {task_result.id}"
                ),
            }
        except Exception as e:
            logger.warning(
                f"Celery dispatch failed, running synchronously: {e}"
            )
            # Fallback: run synchronously if Celery is unavailable
            from services.data_retention import DataRetentionService

            service = DataRetentionService(db)
            result = service.run_retention_cleanup(dry_run=dry_run)
            result["execution"] = "synchronous_fallback"
            return result

    logger.info("DR management routes registered")
