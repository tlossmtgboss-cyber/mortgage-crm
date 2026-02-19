"""
Backup & Disaster Recovery Management Routes
Enterprise Readiness - Domain 8: Disaster Recovery (Checks 8.3, 8.4)

Admin-only endpoints for:
- Backup history and verification
- RPO/RTO compliance monitoring
- Cross-region replication status
- Overall DR readiness dashboard
"""

import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Admin permission roles that can access DR endpoints
ADMIN_ROLES = ("admin", "site_admin", "platform_admin")


def register_backup_routes(app, get_db, get_current_user, **kwargs):
    """
    Register backup and disaster recovery management routes.

    All endpoints require admin-level authentication.

    Args:
        app: FastAPI application instance.
        get_db: Database session dependency.
        get_current_user: Auth dependency.
        **kwargs: Additional dependencies (unused).
    """

    def _require_admin(current_user):
        """Verify the current user has admin privileges."""
        role = getattr(current_user, "permission_role", "")
        if role not in ADMIN_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Admin access required for DR management",
            )
        return current_user

    # ==================================================================
    # GET /api/v1/admin/backups - List backup history
    # ==================================================================

    @app.get("/api/v1/admin/backups")
    async def list_backups(
        limit: int = 20,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        List backup verification history.

        Returns recent backup verification records with status,
        row counts, and RPO compliance information.
        """
        _require_admin(current_user)

        from services.backup_service import BackupVerificationService

        service = BackupVerificationService(db)
        return service.get_backup_history(limit=limit)

    # ==================================================================
    # POST /api/v1/admin/backups/verify - Trigger backup verification
    # ==================================================================

    @app.post("/api/v1/admin/backups/verify")
    async def verify_backup(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Trigger a backup verification.

        Checks the latest backup status, verifies data integrity across
        key tables, computes checksums, and records the verification
        result in the audit log.

        Returns the full verification result.
        """
        _require_admin(current_user)

        from services.backup_service import BackupVerificationService

        service = BackupVerificationService(db)

        # Run verification checks
        backup_status = service.verify_latest_backup()
        integrity = service.verify_backup_integrity()

        # Record the verification
        record_id = service.record_verification(backup_status, integrity)

        return {
            "verification_id": record_id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "backup_status": backup_status,
            "integrity": integrity,
            "triggered_by": getattr(current_user, "email", "unknown"),
        }

    # ==================================================================
    # GET /api/v1/admin/backups/rpo-status - RPO compliance status
    # ==================================================================

    @app.get("/api/v1/admin/backups/rpo-status")
    async def get_rpo_status(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get RPO (Recovery Point Objective) compliance status.

        Checks whether the configured RPO target is being met based on
        backup frequency and recency. Includes RTO target information
        and actionable recommendations.
        """
        _require_admin(current_user)

        from services.backup_service import BackupVerificationService

        service = BackupVerificationService(db)
        return service.calculate_rpo_compliance()

    # ==================================================================
    # GET /api/v1/admin/backups/replication-status - Cross-region status
    # ==================================================================

    @app.get("/api/v1/admin/backups/replication-status")
    async def get_replication_status(
        current_user=Depends(get_current_user),
    ):
        """
        Get cross-region replication status for S3 document backups.

        Checks S3 replication configuration, destination bucket
        accessibility, and replication lag metrics.
        """
        _require_admin(current_user)

        from services.backup_replication import (
            verify_replication_status,
            get_replication_lag,
        )

        replication = verify_replication_status()
        lag = get_replication_lag()

        return {
            "replication": replication,
            "lag": lag,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ==================================================================
    # GET /api/v1/admin/dr/status - Overall DR readiness dashboard
    # ==================================================================

    @app.get("/api/v1/admin/dr/status")
    async def get_dr_status(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get comprehensive disaster recovery readiness dashboard.

        Combines backup verification, RPO/RTO compliance, data integrity,
        and cross-region replication status into a single view.
        """
        _require_admin(current_user)

        from services.backup_service import get_dr_status_summary
        from services.backup_replication import (
            verify_replication_status,
            get_replication_lag,
        )

        # Database DR status
        dr_summary = get_dr_status_summary(db)

        # S3 replication status
        try:
            replication = verify_replication_status()
            lag = get_replication_lag()
            dr_summary["s3_replication"] = {
                "status": replication.get("status", "unknown"),
                "configured": replication.get(
                    "replication_configured", False
                ),
                "lag_seconds": lag.get("lag_seconds"),
                "lag_status": lag.get("lag_status", "unknown"),
                "latest_db_backup": replication.get("latest_db_backup"),
            }
        except Exception as e:
            logger.warning(f"S3 replication check failed: {e}")
            dr_summary["s3_replication"] = {
                "status": "check_failed",
                "error": str(e),
            }

        return dr_summary

    # ==================================================================
    # POST /api/v1/admin/backups/export-to-s3 - Export DB backup to S3
    # ==================================================================

    @app.post("/api/v1/admin/backups/export-to-s3")
    async def export_backup_to_s3(
        current_user=Depends(get_current_user),
    ):
        """
        Export a database backup (pg_dump) to S3.

        Creates a compressed SQL dump and uploads it to the configured
        S3 backup bucket. This is an on-demand supplement to Railway's
        automatic daily backups.
        """
        _require_admin(current_user)

        from services.backup_replication import export_db_backup_to_s3

        result = export_db_backup_to_s3()

        if result.get("status") == "failed":
            raise HTTPException(
                status_code=500,
                detail="Backup export failed",
            )

        return result

    logger.info("Backup & DR routes registered")
