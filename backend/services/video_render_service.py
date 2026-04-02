"""
Video Render Service
Handles render job management with state machine, queue processing, and artifact management.
"""

import os
import json
import logging
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RenderState(str, Enum):
    """Render job state machine states."""
    CREATED = "created"
    SCRIPTED = "scripted"
    VOICED = "voiced"
    STORYBOARDED = "storyboarded"
    VISUALIZED = "visualized"
    RENDERING = "rendering"
    RENDERED = "rendered"
    PUBLISHED = "published"
    FAILED = "failed"


# Valid state transitions
STATE_TRANSITIONS = {
    RenderState.CREATED: [RenderState.SCRIPTED, RenderState.FAILED],
    RenderState.SCRIPTED: [RenderState.VOICED, RenderState.FAILED],
    RenderState.VOICED: [RenderState.STORYBOARDED, RenderState.FAILED],
    RenderState.STORYBOARDED: [RenderState.VISUALIZED, RenderState.FAILED],
    RenderState.VISUALIZED: [RenderState.RENDERING, RenderState.FAILED],
    RenderState.RENDERING: [RenderState.RENDERED, RenderState.FAILED],
    RenderState.RENDERED: [RenderState.PUBLISHED, RenderState.FAILED],
    RenderState.PUBLISHED: [],  # Terminal state
    RenderState.FAILED: [RenderState.CREATED],  # Can retry from failed
}

# Progress percentage per state
STATE_PROGRESS = {
    RenderState.CREATED: 0,
    RenderState.SCRIPTED: 10,
    RenderState.VOICED: 25,
    RenderState.STORYBOARDED: 40,
    RenderState.VISUALIZED: 60,
    RenderState.RENDERING: 80,
    RenderState.RENDERED: 95,
    RenderState.PUBLISHED: 100,
    RenderState.FAILED: 0,
}


class VideoRenderService:
    """Service for managing video render jobs."""

    def __init__(self):
        self.storage_provider = os.getenv("STORAGE_PROVIDER", "local")
        self.s3_bucket = os.getenv("AWS_S3_BUCKET", "perennia-videos")
        self.cdn_base_url = os.getenv("CDN_BASE_URL", "")

    # =========================================================================
    # RENDER JOB CRUD
    # =========================================================================

    def create_render_job(
        self,
        db: Session,
        project_id: int,
        format: str = "portrait_9x16",
        resolution: str = "1080x1920",
        fps: int = 30,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """Create a new render job."""
        try:
            job_id = self._generate_job_id()

            result = db.execute(text("""
                INSERT INTO video_render_jobs (
                    job_id, project_id, format, resolution, fps,
                    state, progress, current_step,
                    queued_at, created_at, updated_at
                ) VALUES (
                    :job_id, :project_id, :format, :resolution, :fps,
                    'created', 0, 'Initializing',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING id
            """), {
                "job_id": job_id,
                "project_id": project_id,
                "format": format,
                "resolution": resolution,
                "fps": fps
            })

            render_id = result.fetchone()[0]
            db.commit()

            # Update project status
            db.execute(text("""
                UPDATE video_projects
                SET status = 'queued', updated_at = CURRENT_TIMESTAMP
                WHERE id = :project_id
            """), {"project_id": project_id})
            db.commit()

            return self.get_render_job(db, render_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating render job: {e}")
            raise

    def get_render_job(self, db: Session, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a render job by ID."""
        result = db.execute(text("""
            SELECT
                rj.*,
                p.title as project_title,
                p.status as project_status
            FROM video_render_jobs rj
            JOIN video_projects p ON p.id = rj.project_id
            WHERE rj.id = :id
        """), {"id": job_id}).fetchone()

        if not result:
            return None

        job = self._row_to_dict(result)

        # Get artifacts
        job["artifacts"] = self.get_render_artifacts(db, job_id)

        return job

    def get_render_job_by_job_id(self, db: Session, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a render job by job_id string."""
        result = db.execute(text("""
            SELECT id FROM video_render_jobs WHERE job_id = :job_id
        """), {"job_id": job_id}).fetchone()

        if not result:
            return None

        return self.get_render_job(db, result[0])

    def list_render_jobs(
        self,
        db: Session,
        organization_id: Optional[int] = None,
        project_id: Optional[int] = None,
        state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List render jobs with filters. Returns (jobs, total_count)."""
        params = {"limit": limit, "offset": offset}
        filters = []

        if organization_id:
            filters.append("p.organization_id = :org_id")
            params["org_id"] = organization_id
        if project_id:
            filters.append("rj.project_id = :project_id")
            params["project_id"] = project_id
        if state:
            filters.append("rj.state = :state")
            params["state"] = state

        where_clause = " AND ".join(filters) if filters else "1=1"

        # Get total count
        count_q = (
            "SELECT COUNT(*) FROM video_render_jobs rj"
            " JOIN video_projects p ON p.id = rj.project_id"
            " WHERE " + where_clause
        )
        count_result = db.execute(text(count_q), params)
        total = count_result.scalar() or 0

        list_q = (
            "SELECT rj.*, p.title as project_title"
            " FROM video_render_jobs rj"
            " JOIN video_projects p ON p.id = rj.project_id"
            " WHERE " + where_clause
            + " ORDER BY rj.created_at DESC"
            " LIMIT :limit OFFSET :offset"
        )
        results = db.execute(text(list_q), params).fetchall()

        return [self._row_to_dict(r) for r in results], total

    def get_pending_jobs(self, db: Session, limit: int = 10) -> List[Dict[str, Any]]:
        """Get jobs waiting to be processed."""
        results = db.execute(text("""
            SELECT
                rj.*,
                p.title as project_title,
                p.brand_template_id,
                p.voice_profile_id
            FROM video_render_jobs rj
            JOIN video_projects p ON p.id = rj.project_id
            WHERE rj.state NOT IN ('rendered', 'published', 'failed')
            ORDER BY rj.queued_at ASC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        return [self._row_to_dict(r) for r in results]

    # =========================================================================
    # STATE MACHINE
    # =========================================================================

    def transition_state(
        self,
        db: Session,
        job_id: int,
        new_state: RenderState,
        current_step: Optional[str] = None,
        error_message: Optional[str] = None,
        error_details: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """Transition a render job to a new state."""
        try:
            job = self.get_render_job(db, job_id)
            if not job:
                return False, "Job not found"

            current_state = RenderState(job["state"])

            # Validate transition
            if new_state not in STATE_TRANSITIONS.get(current_state, []):
                return False, f"Invalid transition from {current_state} to {new_state}"

            # Update job
            update_params = {
                "id": job_id,
                "state": new_state.value,
                "progress": STATE_PROGRESS.get(new_state, 0),
                "current_step": current_step or new_state.value.title()
            }

            if new_state == RenderState.FAILED:
                update_params["error_message"] = error_message
                update_params["error_details"] = json.dumps(error_details) if error_details else None

            if new_state == RenderState.RENDERING and job["started_at"] is None:
                db.execute(text("""
                    UPDATE video_render_jobs
                    SET state = :state, progress = :progress, current_step = :current_step,
                        started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), update_params)
            elif new_state in [RenderState.RENDERED, RenderState.PUBLISHED]:
                db.execute(text("""
                    UPDATE video_render_jobs
                    SET state = :state, progress = :progress, current_step = :current_step,
                        completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), update_params)
            elif new_state == RenderState.FAILED:
                db.execute(text("""
                    UPDATE video_render_jobs
                    SET state = :state, progress = :progress, current_step = :current_step,
                        error_message = :error_message, error_details = :error_details,
                        retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), update_params)
            else:
                db.execute(text("""
                    UPDATE video_render_jobs
                    SET state = :state, progress = :progress, current_step = :current_step,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), update_params)

            # Update project status based on job state
            project_status = "processing"
            if new_state == RenderState.RENDERED:
                project_status = "ready"
            elif new_state == RenderState.FAILED:
                project_status = "failed"

            db.execute(text("""
                UPDATE video_projects
                SET status = :status, updated_at = CURRENT_TIMESTAMP
                WHERE id = :project_id
            """), {"status": project_status, "project_id": job["project_id"]})

            db.commit()

            logger.info(f"Render job {job_id} transitioned from {current_state} to {new_state}")
            return True, f"Transitioned to {new_state}"

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"State transition failed: {e}")
            return False, str(e)

    def update_progress(
        self,
        db: Session,
        job_id: int,
        progress: int,
        current_step: Optional[str] = None
    ) -> bool:
        """Update job progress within the current state."""
        try:
            params = {
                "id": job_id,
                "progress": min(100, max(0, progress))
            }

            if current_step:
                db.execute(text("""
                    UPDATE video_render_jobs
                    SET progress = :progress, current_step = :step, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {**params, "step": current_step})
            else:
                db.execute(text("""
                    UPDATE video_render_jobs
                    SET progress = :progress, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), params)

            db.commit()
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Progress update failed: {e}")
            return False

    def retry_failed_job(self, db: Session, job_id: int) -> Tuple[bool, str]:
        """Retry a failed render job."""
        job = self.get_render_job(db, job_id)
        if not job:
            return False, "Job not found"

        if job["state"] != "failed":
            return False, "Can only retry failed jobs"

        if job["retry_count"] >= job["max_retries"]:
            return False, f"Max retries ({job['max_retries']}) exceeded"

        # Reset to created state
        return self.transition_state(
            db, job_id, RenderState.CREATED,
            current_step="Retrying..."
        )

    # =========================================================================
    # ARTIFACTS
    # =========================================================================

    def add_artifact(
        self,
        db: Session,
        render_job_id: int,
        artifact_type: str,
        file_url: str,
        file_size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        resolution: Optional[str] = None,
        word_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add an artifact to a render job."""
        try:
            result = db.execute(text("""
                INSERT INTO video_render_artifacts (
                    render_job_id, artifact_type, file_url,
                    file_size_bytes, mime_type, duration_seconds,
                    resolution, word_count, created_at
                ) VALUES (
                    :job_id, :type, :url,
                    :size, :mime, :duration,
                    :resolution, :words, CURRENT_TIMESTAMP
                )
                RETURNING id
            """), {
                "job_id": render_job_id,
                "type": artifact_type,
                "url": file_url,
                "size": file_size_bytes,
                "mime": mime_type,
                "duration": duration_seconds,
                "resolution": resolution,
                "words": word_count
            })

            artifact_id = result.fetchone()[0]
            db.commit()

            return self.get_artifact(db, artifact_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error adding artifact: {e}")
            raise

    def get_artifact(self, db: Session, artifact_id: int) -> Optional[Dict[str, Any]]:
        """Get an artifact by ID."""
        result = db.execute(text("""
            SELECT * FROM video_render_artifacts WHERE id = :id
        """), {"id": artifact_id}).fetchone()

        return self._row_to_dict(result) if result else None

    def get_render_artifacts(self, db: Session, render_job_id: int) -> List[Dict[str, Any]]:
        """Get all artifacts for a render job."""
        results = db.execute(text("""
            SELECT * FROM video_render_artifacts
            WHERE render_job_id = :job_id
            ORDER BY artifact_type
        """), {"job_id": render_job_id}).fetchall()

        return [self._row_to_dict(r) for r in results]

    def get_artifact_by_type(
        self,
        db: Session,
        render_job_id: int,
        artifact_type: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific artifact type for a job."""
        result = db.execute(text("""
            SELECT * FROM video_render_artifacts
            WHERE render_job_id = :job_id AND artifact_type = :type
        """), {"job_id": render_job_id, "type": artifact_type}).fetchone()

        return self._row_to_dict(result) if result else None

    # =========================================================================
    # RESOURCE TRACKING
    # =========================================================================

    def record_resource_usage(
        self,
        db: Session,
        job_id: int,
        gpu_seconds: float = 0,
        cpu_seconds: float = 0,
        storage_bytes: int = 0
    ) -> bool:
        """Record resource usage for a job."""
        try:
            db.execute(text("""
                UPDATE video_render_jobs
                SET gpu_seconds = gpu_seconds + :gpu,
                    cpu_seconds = cpu_seconds + :cpu,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {
                "id": job_id,
                "gpu": gpu_seconds,
                "cpu": cpu_seconds
            })
            db.commit()
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Resource tracking failed: {e}")
            return False

    def set_output_metrics(
        self,
        db: Session,
        job_id: int,
        duration_seconds: float,
        file_size_bytes: int
    ) -> bool:
        """Set the final output metrics for a completed job."""
        try:
            db.execute(text("""
                UPDATE video_render_jobs
                SET output_duration_seconds = :duration,
                    output_file_size_bytes = :size,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {
                "id": job_id,
                "duration": duration_seconds,
                "size": file_size_bytes
            })
            db.commit()
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Output metrics update failed: {e}")
            return False

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    def create_batch_render(
        self,
        db: Session,
        project_id: int,
        formats: List[str]
    ) -> List[Dict[str, Any]]:
        """Create render jobs for multiple formats."""
        jobs = []
        format_resolutions = {
            "portrait_9x16": "1080x1920",
            "square_1x1": "1080x1080",
            "landscape_16x9": "1920x1080"
        }

        for fmt in formats:
            resolution = format_resolutions.get(fmt, "1080x1920")
            job = self.create_render_job(
                db, project_id,
                format=fmt,
                resolution=resolution
            )
            jobs.append(job)

        return jobs

    def cancel_job(self, db: Session, job_id: int) -> Tuple[bool, str]:
        """Cancel a pending or in-progress job."""
        job = self.get_render_job(db, job_id)
        if not job:
            return False, "Job not found"

        if job["state"] in ["rendered", "published"]:
            return False, "Cannot cancel completed jobs"

        return self.transition_state(
            db, job_id, RenderState.FAILED,
            current_step="Cancelled",
            error_message="Job cancelled by user"
        )

    # =========================================================================
    # QUEUE MANAGEMENT
    # =========================================================================

    def get_queue_stats(self, db: Session) -> Dict[str, Any]:
        """Get render queue statistics."""
        result = db.execute(text("""
            SELECT
                state,
                COUNT(*) as count,
                AVG(EXTRACT(EPOCH FROM (COALESCE(completed_at, CURRENT_TIMESTAMP) - queued_at))) as avg_time
            FROM video_render_jobs
            WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            GROUP BY state
        """)).fetchall()

        stats = {
            "by_state": {r[0]: {"count": r[1], "avg_seconds": r[2]} for r in result},
            "total_24h": sum(r[1] for r in result)
        }

        # Get queue depth
        pending = db.execute(text("""
            SELECT COUNT(*) FROM video_render_jobs
            WHERE state NOT IN ('rendered', 'published', 'failed')
        """)).fetchone()

        stats["queue_depth"] = pending[0] if pending else 0

        return stats

    def claim_job(
        self,
        db: Session,
        worker_id: str
    ) -> Optional[Dict[str, Any]]:
        """Claim the next available job for a worker."""
        try:
            # Find and claim the next job atomically
            result = db.execute(text("""
                UPDATE video_render_jobs
                SET worker_id = :worker_id,
                    started_at = CASE WHEN started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM video_render_jobs
                    WHERE worker_id IS NULL
                    AND state NOT IN ('rendered', 'published', 'failed')
                    ORDER BY queued_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id
            """), {"worker_id": worker_id})

            row = result.fetchone()
            if row:
                db.commit()
                return self.get_render_job(db, row[0])

            return None

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Job claim failed: {e}")
            return None

    def release_job(self, db: Session, job_id: int) -> bool:
        """Release a job (on worker failure)."""
        try:
            db.execute(text("""
                UPDATE video_render_jobs
                SET worker_id = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": job_id})
            db.commit()
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Job release failed: {e}")
            return False

    def claim_next_job(
        self,
        db: Session,
        worker_id: str
    ) -> Optional[Dict[str, Any]]:
        """Claim the next available job for a worker (alias for claim_job)."""
        return self.claim_job(db, worker_id)

    def get_render_job_by_id(self, db: Session, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a render job by its integer database ID (alias for get_render_job)."""
        return self.get_render_job(db, job_id)

    def retry_job(self, db: Session, job_id: int) -> Tuple[bool, str]:
        """Retry a failed render job (alias for retry_failed_job)."""
        return self.retry_failed_job(db, job_id)

    def fail_job(
        self,
        db: Session,
        job_id: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Mark a job as failed with error details."""
        try:
            # Get job by job_id string
            job = self.get_render_job_by_job_id(db, job_id)
            if not job:
                logger.error(f"Cannot fail job {job_id}: not found")
                return False

            success, _ = self.transition_state(
                db,
                job["id"],
                RenderState.FAILED,
                current_step="Failed",
                error_message=error_message,
                error_details=error_details
            )

            return success

        except Exception as e:
            logger.error(f"Failed to mark job as failed: {e}")
            return False

    def complete_job(
        self,
        db: Session,
        job_id: str,
        duration_seconds: float,
        file_size_bytes: int
    ) -> bool:
        """Mark a job as completed with output metrics."""
        try:
            # Get job by job_id string
            job = self.get_render_job_by_job_id(db, job_id)
            if not job:
                logger.error(f"Cannot complete job {job_id}: not found")
                return False

            # Set output metrics
            self.set_output_metrics(db, job["id"], duration_seconds, file_size_bytes)

            return True

        except Exception as e:
            logger.error(f"Failed to complete job: {e}")
            return False

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        return f"VRJ-{uuid.uuid4().hex[:12].upper()}"

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to a dictionary."""
        if row is None:
            return None

        if hasattr(row, '_mapping'):
            d = dict(row._mapping)
        elif hasattr(row, '_asdict'):
            d = row._asdict()
        else:
            d = dict(row)

        # Parse JSON fields
        if 'error_details' in d and isinstance(d['error_details'], str):
            try:
                d['error_details'] = json.loads(d['error_details'])
            except (json.JSONDecodeError, TypeError):
                pass

        return d


# Global instance
video_render_service = VideoRenderService()
