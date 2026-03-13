"""
Batch Job Model

Model for Smart Docs V2 batch operations: bulk upload, bulk classify,
bulk export, bulk reminder, and stacking order generation.

Each batch job tracks overall progress (total/processed/failed/skipped),
per-item error logs, and supports cancellation via status transitions.

Key table:
    smart_docs_batch_jobs  - Tracks batch job lifecycle and results

Usage:
    from database.models.batch_job import (
        BatchJob,
        BatchJobType,
        BatchJobStatus,
    )

    # Create a new batch job
    job = BatchJob(
        organization_id=org_id,
        job_type=BatchJobType.BULK_UPLOAD.value,
        total_items=25,
        created_by_user_id=user_id,
    )
    db.add(job)
    db.commit()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
)

from db import Base


# =============================================================================
# ENUMS
# =============================================================================

class BatchJobType(str, enum.Enum):
    """Type of batch operation."""
    BULK_UPLOAD = "BULK_UPLOAD"
    BULK_CLASSIFY = "BULK_CLASSIFY"
    BULK_EXPORT = "BULK_EXPORT"
    BULK_REMINDER = "BULK_REMINDER"
    STACKING_ORDER = "STACKING_ORDER"


class BatchJobStatus(str, enum.Enum):
    """Lifecycle status of a batch job."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# =============================================================================
# MODEL
# =============================================================================

class BatchJob(Base):
    """
    Tracks a Smart Docs batch operation.

    Lifecycle: PENDING -> RUNNING -> COMPLETED | FAILED | CANCELLED

    Cancellation is cooperative: running jobs check the status column
    between item iterations and stop gracefully when CANCELLED.

    Concurrency control: max 3 concurrent RUNNING/PENDING jobs per org,
    enforced at the service layer before inserting new rows.
    """
    __tablename__ = "smart_docs_batch_jobs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Tenant isolation -- every query must filter on this",
    )
    job_type = Column(
        String(50),
        nullable=False,
        comment="BULK_UPLOAD, BULK_CLASSIFY, BULK_EXPORT, BULK_REMINDER, STACKING_ORDER",
    )
    status = Column(
        String(20),
        nullable=False,
        default=BatchJobStatus.PENDING.value,
        comment="PENDING, RUNNING, COMPLETED, FAILED, CANCELLED",
    )

    # Progress counters
    total_items = Column(Integer, nullable=False, default=0)
    processed_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)
    skipped_items = Column(Integer, nullable=False, default=0)

    # Payloads
    input_params = Column(
        JSON,
        nullable=True,
        comment="Job-specific input parameters (loan_id, file list, etc.)",
    )
    results = Column(
        JSON,
        nullable=True,
        comment="Aggregated results after completion (download URL, summary, etc.)",
    )
    error_log = Column(
        JSON,
        nullable=True,
        comment="Per-item error details [{item_index, filename, error, ...}]",
    )

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(Integer, nullable=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index(
            "ix_batch_jobs_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_batch_jobs_created_at",
            "created_at",
        ),
    )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def progress_pct(self) -> float:
        """Return percentage complete (0.0 - 100.0)."""
        if self.total_items == 0:
            return 0.0
        processed = (self.processed_items or 0) + (self.failed_items or 0) + (self.skipped_items or 0)
        return min(round((processed / self.total_items) * 100, 1), 100.0)

    @property
    def is_terminal(self) -> bool:
        """Return True if the job is in a terminal state."""
        return self.status in (
            BatchJobStatus.COMPLETED.value,
            BatchJobStatus.FAILED.value,
            BatchJobStatus.CANCELLED.value,
        )

    def to_dict(self) -> dict:
        """Serialize for API responses."""
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
            "skipped_items": self.skipped_items,
            "progress_pct": self.progress_pct,
            "input_params": self.input_params,
            "results": self.results,
            "error_log": self.error_log,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "BatchJob",
    "BatchJobType",
    "BatchJobStatus",
]
