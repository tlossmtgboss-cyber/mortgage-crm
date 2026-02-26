"""
Change Management Service — Record deployments, config changes, and migrations.
SOC 2 Criteria: CC8 (Change Management)

Provides methods for recording change events into the soc2_change_record table.
Designed to be called from deployment hooks, startup events, and admin routes.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..constants import ChangeType, ChangeStatus

logger = logging.getLogger("soc2.change_management")


class ChangeManagementService:
    """
    Record change management events for SOC 2 CC8 compliance.

    Usage:
        cms = ChangeManagementService(db)
        cms.record_deployment(
            title="v2.5.0 release",
            description="Added SOC 2 compliance module",
            git_commit="abc123",
        )
    """

    def __init__(self, db: Session):
        self.db = db

    def record_deployment(
        self,
        title: str,
        description: str,
        git_commit: Optional[str] = None,
        git_branch: Optional[str] = None,
        pull_request_url: Optional[str] = None,
        deployment_id: Optional[str] = None,
        requested_by: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        affected_systems: Optional[List[str]] = None,
    ) -> UUID:
        """Record a deployment event."""
        record_id = uuid4()
        now = datetime.now(timezone.utc)

        self.db.execute(
            text("""
                INSERT INTO soc2_change_record (
                    id, created_at, updated_at, title, description,
                    change_type, status, requested_by, tenant_id,
                    affected_systems, git_commit, git_branch,
                    pull_request_url, deployment_id,
                    implemented_at, success
                ) VALUES (
                    :id, :now, :now, :title, :description,
                    :change_type, :status, :requested_by, :tenant_id,
                    :affected_systems, :git_commit, :git_branch,
                    :pull_request_url, :deployment_id,
                    :now, TRUE
                )
            """),
            {
                "id": str(record_id),
                "now": now,
                "title": title,
                "description": description,
                "change_type": ChangeType.DEPLOYMENT,
                "status": ChangeStatus.COMPLETED,
                "requested_by": str(requested_by) if requested_by else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "affected_systems": affected_systems or ["application"],
                "git_commit": git_commit,
                "git_branch": git_branch,
                "pull_request_url": pull_request_url,
                "deployment_id": deployment_id,
            }
        )
        self.db.commit()

        logger.info(
            "deployment_recorded",
            extra={
                "record_id": str(record_id),
                "title": title,
                "git_commit": git_commit,
                "deployment_id": deployment_id,
            }
        )
        return record_id

    def record_configuration_change(
        self,
        title: str,
        description: str,
        changed_by: Optional[UUID] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[UUID] = None,
        affected_systems: Optional[List[str]] = None,
    ) -> UUID:
        """Record a configuration change."""
        record_id = uuid4()
        now = datetime.now(timezone.utc)

        # Store old/new values in testing_evidence as JSON
        testing_evidence = None
        if old_values or new_values:
            testing_evidence = json.dumps({
                "old_values": old_values,
                "new_values": new_values,
            })

        self.db.execute(
            text("""
                INSERT INTO soc2_change_record (
                    id, created_at, updated_at, title, description,
                    change_type, status, requested_by, implemented_by,
                    tenant_id, affected_systems,
                    implemented_at, success, testing_evidence
                ) VALUES (
                    :id, :now, :now, :title, :description,
                    :change_type, :status, :changed_by, :changed_by,
                    :tenant_id, :affected_systems,
                    :now, TRUE, :testing_evidence
                )
            """),
            {
                "id": str(record_id),
                "now": now,
                "title": title,
                "description": description,
                "change_type": ChangeType.CONFIGURATION,
                "status": ChangeStatus.COMPLETED,
                "changed_by": str(changed_by) if changed_by else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "affected_systems": affected_systems or ["configuration"],
                "testing_evidence": testing_evidence,
            }
        )
        self.db.commit()

        logger.info(
            "configuration_change_recorded",
            extra={"record_id": str(record_id), "title": title}
        )
        return record_id

    def record_database_migration(
        self,
        title: str,
        description: str,
        migration_name: Optional[str] = None,
        requested_by: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> UUID:
        """Record a database migration."""
        record_id = uuid4()
        now = datetime.now(timezone.utc)

        self.db.execute(
            text("""
                INSERT INTO soc2_change_record (
                    id, created_at, updated_at, title, description,
                    change_type, status, requested_by,
                    tenant_id, affected_systems,
                    implemented_at, success,
                    post_implementation_notes
                ) VALUES (
                    :id, :now, :now, :title, :description,
                    :change_type, :status, :requested_by,
                    :tenant_id, :affected_systems,
                    :now, TRUE, :notes
                )
            """),
            {
                "id": str(record_id),
                "now": now,
                "title": title,
                "description": description,
                "change_type": ChangeType.DATABASE_MIGRATION,
                "status": ChangeStatus.COMPLETED,
                "requested_by": str(requested_by) if requested_by else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "affected_systems": ["database"],
                "notes": f"Migration: {migration_name}" if migration_name else None,
            }
        )
        self.db.commit()

        logger.info(
            "database_migration_recorded",
            extra={
                "record_id": str(record_id),
                "title": title,
                "migration_name": migration_name,
            }
        )
        return record_id
