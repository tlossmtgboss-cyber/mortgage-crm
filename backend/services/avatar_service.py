"""
Avatar Service - Manages AI avatar profiles, training, and video generation.

This service coordinates between:
- Avatar profile CRUD operations
- Voice cloning service (XTTS)
- Lip sync service (Wav2Lip)
- Video storage and CDN
"""

import os
import uuid
import logging
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

from sqlalchemy.exc import SQLAlchemyError
from models.avatar_models import (
    AvatarStatus,
    AvatarJobStatus,
    AvatarEmotion,
    AvatarProfileCreate,
    AvatarProfileUpdate,
    AvatarJobCreate,
)

logger = logging.getLogger(__name__)


class AvatarService:
    """Service for managing AI avatars."""

    def __init__(self):
        """Initialize avatar service with ML service URLs."""
        self.voice_clone_url = os.getenv("VOICE_CLONE_SERVICE_URL", "http://localhost:5501")
        self.lip_sync_url = os.getenv("LIP_SYNC_SERVICE_URL", "http://localhost:5502")
        self.s3_bucket = os.getenv("AVATAR_ASSETS_BUCKET", os.getenv("AWS_S3_BUCKET", "perennia-avatars"))
        self.cdn_base_url = os.getenv("AVATAR_CDN_URL", os.getenv("CDN_BASE_URL", ""))

    # =========================================================================
    # Avatar Profile CRUD
    # =========================================================================

    def create_profile(
        self,
        db: Session,
        data: AvatarProfileCreate,
        user_id: int,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new avatar profile."""
        result = db.execute(
            text("""
                INSERT INTO video_avatar_profiles (
                    name, description, user_id, organization_id,
                    default_background, default_resolution, crop_style,
                    lip_sync_quality, voice_similarity, status
                ) VALUES (
                    :name, :description, :user_id, :organization_id,
                    :default_background, :default_resolution, :crop_style,
                    :lip_sync_quality, :voice_similarity, 'pending'
                )
                RETURNING id, created_at
            """),
            {
                "name": data.name,
                "description": data.description,
                "user_id": user_id,
                "organization_id": organization_id,
                "default_background": data.default_background,
                "default_resolution": data.default_resolution,
                "crop_style": data.crop_style.value,
                "lip_sync_quality": data.lip_sync_quality.value,
                "voice_similarity": data.voice_similarity,
            }
        )
        row = result.fetchone()
        db.commit()

        return self.get_profile(db, row[0])

    def get_profile(self, db: Session, avatar_id: int) -> Optional[Dict[str, Any]]:
        """Get avatar profile by ID."""
        result = db.execute(
            text("""
                SELECT * FROM video_avatar_profiles WHERE id = :id
            """),
            {"id": avatar_id}
        )
        row = result.fetchone()
        if not row:
            return None

        columns = result.keys()
        return dict(zip(columns, row))

    def get_profile_by_user(
        self,
        db: Session,
        avatar_id: int,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get avatar profile by ID, ensuring user ownership."""
        result = db.execute(
            text("""
                SELECT * FROM video_avatar_profiles
                WHERE id = :id AND user_id = :user_id
            """),
            {"id": avatar_id, "user_id": user_id}
        )
        row = result.fetchone()
        if not row:
            return None

        columns = result.keys()
        return dict(zip(columns, row))

    def list_profiles(
        self,
        db: Session,
        user_id: int,
        organization_id: Optional[int] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List avatar profiles for a user."""
        offset = (page - 1) * page_size

        # Build WHERE clause
        where_clauses = ["user_id = :user_id"]
        params = {"user_id": user_id, "limit": page_size, "offset": offset}

        if organization_id:
            where_clauses.append("organization_id = :organization_id")
            params["organization_id"] = organization_id

        if status:
            where_clauses.append("status = :status")
            params["status"] = status

        where_sql = " AND ".join(where_clauses)

        # Get total count
        query = f"SELECT COUNT(*) FROM video_avatar_profiles WHERE {where_sql}"
        count_result = db.execute(
            text(query),
            params
        )
        total = count_result.scalar()

        # Get profiles
        query = f"""
                SELECT id, name, status, reference_image_url,
                       total_videos_generated, last_used_at, created_at
                FROM video_avatar_profiles
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """
        result = db.execute(
            text(query),
            params
        )

        profiles = []
        columns = result.keys()
        for row in result.fetchall():
            profiles.append(dict(zip(columns, row)))

        return profiles, total

    def update_profile(
        self,
        db: Session,
        avatar_id: int,
        user_id: int,
        data: AvatarProfileUpdate
    ) -> Optional[Dict[str, Any]]:
        """Update avatar profile."""
        # Build SET clause from non-None fields
        updates = []
        params = {"id": avatar_id, "user_id": user_id}

        if data.name is not None:
            updates.append("name = :name")
            params["name"] = data.name

        if data.description is not None:
            updates.append("description = :description")
            params["description"] = data.description

        if data.default_background is not None:
            updates.append("default_background = :default_background")
            params["default_background"] = data.default_background

        if data.default_resolution is not None:
            updates.append("default_resolution = :default_resolution")
            params["default_resolution"] = data.default_resolution

        if data.crop_style is not None:
            updates.append("crop_style = :crop_style")
            params["crop_style"] = data.crop_style.value

        if data.lip_sync_quality is not None:
            updates.append("lip_sync_quality = :lip_sync_quality")
            params["lip_sync_quality"] = data.lip_sync_quality.value

        if data.voice_similarity is not None:
            updates.append("voice_similarity = :voice_similarity")
            params["voice_similarity"] = data.voice_similarity

        if not updates:
            return self.get_profile_by_user(db, avatar_id, user_id)

        updates.append("updated_at = NOW()")
        set_sql = ", ".join(updates)

        query = f"""
                UPDATE video_avatar_profiles
                SET {set_sql}
                WHERE id = :id AND user_id = :user_id
            """
        db.execute(
            text(query),
            params
        )
        db.commit()

        return self.get_profile_by_user(db, avatar_id, user_id)

    def delete_profile(
        self,
        db: Session,
        avatar_id: int,
        user_id: int
    ) -> bool:
        """Delete avatar profile."""
        result = db.execute(
            text("""
                DELETE FROM video_avatar_profiles
                WHERE id = :id AND user_id = :user_id
            """),
            {"id": avatar_id, "user_id": user_id}
        )
        db.commit()
        return result.rowcount > 0

    # =========================================================================
    # Training Video Upload
    # =========================================================================

    def generate_upload_url(
        self,
        db: Session,
        avatar_id: int,
        user_id: int,
        file_name: str,
        content_type: str
    ) -> Optional[Dict[str, Any]]:
        """Generate pre-signed URL for training video upload."""
        profile = self.get_profile_by_user(db, avatar_id, user_id)
        if not profile:
            return None

        # Generate S3 key
        file_ext = file_name.split('.')[-1] if '.' in file_name else 'mp4'
        s3_key = f"avatars/{avatar_id}/training/video.{file_ext}"

        try:
            import boto3
            s3_client = boto3.client('s3')

            # Generate presigned POST
            presigned = s3_client.generate_presigned_post(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, 500_000_000],  # 500MB max
                ],
                ExpiresIn=3600  # 1 hour
            )

            # Update profile status
            db.execute(
                text("""
                    UPDATE video_avatar_profiles
                    SET status = 'uploading', updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": avatar_id}
            )
            db.commit()

            return {
                "upload_url": presigned["url"],
                "upload_fields": presigned["fields"],
                "s3_key": s3_key,
                "max_size_bytes": 500_000_000,
                "allowed_formats": ["mp4", "mov", "webm"],
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to generate upload URL: {e}")
            # Fallback for local development
            return {
                "upload_url": f"/api/v1/video-os/avatars/{avatar_id}/upload-direct",
                "upload_fields": {},
                "s3_key": s3_key,
                "max_size_bytes": 500_000_000,
                "allowed_formats": ["mp4", "mov", "webm"],
            }

    def complete_upload(
        self,
        db: Session,
        avatar_id: int,
        user_id: int,
        s3_key: str,
        duration_seconds: float,
        size_bytes: int
    ) -> Optional[Dict[str, Any]]:
        """Mark training video upload as complete."""
        video_url = f"s3://{self.s3_bucket}/{s3_key}"
        if self.cdn_base_url:
            video_url = f"{self.cdn_base_url}/{s3_key}"

        db.execute(
            text("""
                UPDATE video_avatar_profiles
                SET training_video_url = :url,
                    training_video_duration_seconds = :duration,
                    training_video_size_bytes = :size,
                    status = 'processing',
                    updated_at = NOW()
                WHERE id = :id AND user_id = :user_id
            """),
            {
                "id": avatar_id,
                "user_id": user_id,
                "url": video_url,
                "duration": duration_seconds,
                "size": size_bytes,
            }
        )
        db.commit()

        return self.get_profile_by_user(db, avatar_id, user_id)

    # =========================================================================
    # Training Status
    # =========================================================================

    def update_training_status(
        self,
        db: Session,
        avatar_id: int,
        status: str,
        progress: int = 0,
        error: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        voice_sample_url: Optional[str] = None,
        voice_model_id: Optional[str] = None
    ) -> None:
        """Update training status for an avatar."""
        updates = ["status = :status", "training_progress = :progress", "updated_at = NOW()"]
        params = {"id": avatar_id, "status": status, "progress": progress}

        if status == AvatarStatus.TRAINING.value and progress == 0:
            updates.append("training_started_at = NOW()")

        if status == AvatarStatus.READY.value:
            updates.append("training_completed_at = NOW()")

        if status == AvatarStatus.FAILED.value and error:
            updates.append("training_error = :error")
            params["error"] = error

        if reference_image_url:
            updates.append("reference_image_url = :reference_image_url")
            params["reference_image_url"] = reference_image_url

        if voice_sample_url:
            updates.append("voice_sample_url = :voice_sample_url")
            params["voice_sample_url"] = voice_sample_url

        if voice_model_id:
            updates.append("voice_model_id = :voice_model_id")
            params["voice_model_id"] = voice_model_id

        query = f"""
                UPDATE video_avatar_profiles
                SET {", ".join(updates)}
                WHERE id = :id
            """
        db.execute(
            text(query),
            params
        )
        db.commit()

    def get_training_status(
        self,
        db: Session,
        avatar_id: int,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get current training status."""
        result = db.execute(
            text("""
                SELECT id, status, training_progress, training_started_at,
                       training_completed_at, training_error
                FROM video_avatar_profiles
                WHERE id = :id AND user_id = :user_id
            """),
            {"id": avatar_id, "user_id": user_id}
        )
        row = result.fetchone()
        if not row:
            return None

        columns = result.keys()
        return dict(zip(columns, row))

    # =========================================================================
    # Avatar Generation Jobs
    # =========================================================================

    def create_generation_job(
        self,
        db: Session,
        data: AvatarJobCreate,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Create a new avatar video generation job."""
        # Verify avatar exists and is ready
        profile = self.get_profile_by_user(db, data.avatar_id, user_id)
        if not profile:
            return None

        if profile["status"] != AvatarStatus.READY.value:
            raise ValueError(f"Avatar is not ready for generation. Status: {profile['status']}")

        # Generate job ID
        job_id = f"AVJ-{uuid.uuid4().hex[:12].upper()}"

        result = db.execute(
            text("""
                INSERT INTO video_avatar_jobs (
                    job_id, avatar_id, project_id, scene_id,
                    script_text, emotion, speaking_rate, duration_hint_seconds,
                    status
                ) VALUES (
                    :job_id, :avatar_id, :project_id, :scene_id,
                    :script_text, :emotion, :speaking_rate, :duration_hint,
                    'pending'
                )
                RETURNING id, created_at
            """),
            {
                "job_id": job_id,
                "avatar_id": data.avatar_id,
                "project_id": data.project_id,
                "scene_id": data.scene_id,
                "script_text": data.script_text,
                "emotion": data.emotion.value,
                "speaking_rate": data.speaking_rate,
                "duration_hint": data.duration_hint_seconds,
            }
        )
        row = result.fetchone()
        db.commit()

        return self.get_job(db, job_id)

    def get_job(self, db: Session, job_id: str) -> Optional[Dict[str, Any]]:
        """Get avatar job by job ID."""
        result = db.execute(
            text("SELECT * FROM video_avatar_jobs WHERE job_id = :job_id"),
            {"job_id": job_id}
        )
        row = result.fetchone()
        if not row:
            return None

        columns = result.keys()
        return dict(zip(columns, row))

    def list_jobs(
        self,
        db: Session,
        avatar_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List avatar generation jobs."""
        offset = (page - 1) * page_size
        where_clauses = []
        params = {"limit": page_size, "offset": offset}

        if avatar_id:
            where_clauses.append("j.avatar_id = :avatar_id")
            params["avatar_id"] = avatar_id

        if user_id:
            where_clauses.append("p.user_id = :user_id")
            params["user_id"] = user_id

        if status:
            where_clauses.append("j.status = :status")
            params["status"] = status

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total
        query = f"""
                SELECT COUNT(*)
                FROM video_avatar_jobs j
                JOIN video_avatar_profiles p ON p.id = j.avatar_id
                WHERE {where_sql}
            """
        count_result = db.execute(
            text(query),
            params
        )
        total = count_result.scalar()

        # Get jobs
        query = f"""
                SELECT j.*
                FROM video_avatar_jobs j
                JOIN video_avatar_profiles p ON p.id = j.avatar_id
                WHERE {where_sql}
                ORDER BY j.created_at DESC
                LIMIT :limit OFFSET :offset
            """
        result = db.execute(
            text(query),
            params
        )

        jobs = []
        columns = result.keys()
        for row in result.fetchall():
            jobs.append(dict(zip(columns, row)))

        return jobs, total

    def update_job_status(
        self,
        db: Session,
        job_id: str,
        status: str,
        progress: int = 0,
        current_step: Optional[str] = None,
        error_message: Optional[str] = None,
        audio_url: Optional[str] = None,
        video_url: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        voice_generation_ms: Optional[int] = None,
        lip_sync_generation_ms: Optional[int] = None
    ) -> None:
        """Update job status."""
        updates = ["status = :status", "progress = :progress"]
        params = {"job_id": job_id, "status": status, "progress": progress}

        if status == AvatarJobStatus.GENERATING_VOICE.value and progress == 0:
            updates.append("started_at = NOW()")

        if status in [AvatarJobStatus.COMPLETED.value, AvatarJobStatus.FAILED.value]:
            updates.append("completed_at = NOW()")

        if current_step:
            updates.append("current_step = :current_step")
            params["current_step"] = current_step

        if error_message:
            updates.append("error_message = :error_message")
            params["error_message"] = error_message

        if audio_url:
            updates.append("audio_url = :audio_url")
            params["audio_url"] = audio_url

        if video_url:
            updates.append("video_url = :video_url")
            params["video_url"] = video_url

        if duration_seconds:
            updates.append("duration_seconds = :duration_seconds")
            params["duration_seconds"] = duration_seconds

        if voice_generation_ms:
            updates.append("voice_generation_ms = :voice_generation_ms")
            params["voice_generation_ms"] = voice_generation_ms

        if lip_sync_generation_ms:
            updates.append("lip_sync_generation_ms = :lip_sync_generation_ms")
            params["lip_sync_generation_ms"] = lip_sync_generation_ms

        query = f"""
                UPDATE video_avatar_jobs
                SET {", ".join(updates)}
                WHERE job_id = :job_id
            """
        db.execute(
            text(query),
            params
        )
        db.commit()

    # =========================================================================
    # ML Service Integration
    # =========================================================================

    async def synthesize_voice(
        self,
        voice_model_id: str,
        text: str,
        speaking_rate: float = 1.0
    ) -> Optional[bytes]:
        """Synthesize voice audio using XTTS service."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.voice_clone_url}/synthesize",
                    json={
                        "voice_model_id": voice_model_id,
                        "text": text,
                        "speaking_rate": speaking_rate,
                    }
                )
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Voice synthesis failed: {e}")
            return None

    async def generate_lipsync(
        self,
        reference_image_url: str,
        audio_data: bytes,
        emotion: str = "neutral"
    ) -> Optional[bytes]:
        """Generate lip-synced video using Wav2Lip service."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.lip_sync_url}/generate",
                    files={"audio": ("audio.wav", audio_data, "audio/wav")},
                    data={
                        "reference_image_url": reference_image_url,
                        "emotion": emotion,
                    }
                )
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Lip sync generation failed: {e}")
            return None

    # =========================================================================
    # Voice Preview
    # =========================================================================

    async def generate_voice_preview(
        self,
        db: Session,
        avatar_id: int,
        user_id: int,
        sample_text: str,
        speaking_rate: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """Generate a voice preview for an avatar."""
        profile = self.get_profile_by_user(db, avatar_id, user_id)
        if not profile or profile["status"] != AvatarStatus.READY.value:
            return None

        if not profile.get("voice_model_id"):
            return None

        audio_data = await self.synthesize_voice(
            profile["voice_model_id"],
            sample_text,
            speaking_rate
        )

        if not audio_data:
            return None

        # Save to temporary location and return URL
        preview_key = f"avatars/{avatar_id}/previews/{uuid.uuid4().hex}.wav"

        try:
            import boto3
            s3_client = boto3.client('s3')
            s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=preview_key,
                Body=audio_data,
                ContentType="audio/wav",
            )

            audio_url = f"{self.cdn_base_url}/{preview_key}" if self.cdn_base_url else f"s3://{self.s3_bucket}/{preview_key}"

            # Estimate duration (rough: ~150 words per minute)
            word_count = len(sample_text.split())
            duration_seconds = (word_count / 150) * 60 / speaking_rate

            return {
                "avatar_id": avatar_id,
                "audio_url": audio_url,
                "duration_seconds": duration_seconds,
                "sample_text": sample_text,
            }
        except Exception as e:
            logger.error(f"Failed to save voice preview: {e}")
            return None

    # =========================================================================
    # Usage Stats
    # =========================================================================

    def update_usage_stats(
        self,
        db: Session,
        avatar_id: int,
        duration_seconds: float
    ) -> None:
        """Update avatar usage statistics after video generation."""
        db.execute(
            text("""
                UPDATE video_avatar_profiles
                SET total_videos_generated = total_videos_generated + 1,
                    total_duration_generated_seconds = total_duration_generated_seconds + :duration,
                    last_used_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": avatar_id, "duration": duration_seconds}
        )
        db.commit()

    def log_analytics_event(
        self,
        db: Session,
        avatar_id: int,
        event_type: str,
        event_data: Dict[str, Any] = None
    ) -> None:
        """Log an analytics event for an avatar."""
        import json
        db.execute(
            text("""
                INSERT INTO video_avatar_analytics (avatar_id, event_type, event_data)
                VALUES (:avatar_id, :event_type, :event_data)
            """),
            {
                "avatar_id": avatar_id,
                "event_type": event_type,
                "event_data": json.dumps(event_data or {}),
            }
        )
        db.commit()


# Singleton instance
avatar_service = AvatarService()
