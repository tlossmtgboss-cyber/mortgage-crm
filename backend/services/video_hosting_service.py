"""
Video Hosting + Analytics Service
Handles video library management, sharing, embedding, and comprehensive analytics.
"""

import os
import uuid
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from sqlalchemy import text, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# S3-compatible storage configuration
S3_BUCKET = os.getenv("VIDEO_S3_BUCKET", "perennia-videos")
S3_REGION = os.getenv("VIDEO_S3_REGION", "us-east-1")
CDN_BASE_URL = os.getenv("VIDEO_CDN_URL", "")


class VideoS3Service:
    """
    S3 service specialized for video storage.

    Features:
    - 500MB file size limit for video files
    - Video-specific content types (mp4, webm, mov, etc.)
    - CDN URL generation
    - Thumbnail and preview support
    """

    # Maximum file size: 500MB
    MAX_VIDEO_SIZE = 500 * 1024 * 1024

    # Allowed video content types
    ALLOWED_VIDEO_TYPES = [
        'video/mp4',
        'video/webm',
        'video/quicktime',  # .mov
        'video/x-msvideo',  # .avi
        'video/x-matroska',  # .mkv
        'video/mpeg',
        'audio/mpeg',  # mp3 for audio tracks
        'audio/wav',
        'audio/x-wav',
        'image/jpeg',
        'image/png',
        'image/webp',  # for thumbnails
    ]

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
        cdn_url: Optional[str] = None
    ):
        """Initialize video S3 service."""
        self.bucket_name = bucket_name or os.getenv("VIDEO_S3_BUCKET", "perennia-videos")
        self.region = region or os.getenv("VIDEO_S3_REGION", "us-east-1")
        self.cdn_url = cdn_url or os.getenv("VIDEO_CDN_URL", "")

        self._client = None

    @property
    def client(self):
        """Lazy-load boto3 client."""
        if self._client is None:
            import boto3
            from botocore.config import Config

            config = Config(
                signature_version='s3v4',
                s3={'addressing_style': 'virtual'}
            )

            self._client = boto3.client(
                's3',
                region_name=self.region,
                config=config
            )
        return self._client

    def generate_video_key(
        self,
        job_id: str,
        artifact_type: str = "final",
        extension: str = "mp4",
        organization_id: int = None,
    ) -> str:
        """
        Generate a storage key for a video file.

        Format: org-{org_id}/videos/{job_id}/{artifact_type}.{extension}

        Args:
            job_id: The render job ID
            artifact_type: Type of artifact (final, preview, thumbnail, audio)
            extension: File extension
            organization_id: Organization ID for tenant isolation (REQUIRED)

        Returns:
            S3 storage key

        Raises:
            ValueError: If organization_id is not provided
        """
        if not organization_id:
            raise ValueError("organization_id is required for tenant-isolated video storage")
        return f"org-{organization_id}/videos/{job_id}/{artifact_type}.{extension}"

    def generate_thumbnail_key(self, job_id: str, index: int = 0, organization_id: int = None) -> str:
        """Generate storage key for a video thumbnail."""
        if not organization_id:
            raise ValueError("organization_id is required for tenant-isolated video storage")
        return f"org-{organization_id}/videos/{job_id}/thumbnails/thumb_{index:03d}.jpg"

    def generate_scene_key(self, job_id: str, scene_index: int, asset_type: str = "visual", organization_id: int = None) -> str:
        """Generate storage key for a scene asset."""
        if not organization_id:
            raise ValueError("organization_id is required for tenant-isolated video storage")
        ext = "png" if asset_type == "visual" else "wav"
        return f"org-{organization_id}/videos/{job_id}/scenes/{scene_index:03d}_{asset_type}.{ext}"

    def upload_video(
        self,
        file_path: str,
        job_id: str,
        artifact_type: str = "final",
        content_type: str = "video/mp4",
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """
        Upload a video file to S3.

        Args:
            file_path: Local path to the video file
            job_id: Render job ID
            artifact_type: Type of artifact
            content_type: MIME type
            organization_id: Organization ID for tenant isolation (REQUIRED)

        Returns:
            Dict with upload result and URLs
        """
        from botocore.exceptions import ClientError

        if not organization_id:
            return {"success": False, "error": "organization_id is required for video upload"}

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": "File not found"}

        file_size = path.stat().st_size
        if file_size > self.MAX_VIDEO_SIZE:
            return {
                "success": False,
                "error": f"File size {file_size} exceeds maximum {self.MAX_VIDEO_SIZE} bytes"
            }

        extension = path.suffix.lstrip('.') or 'mp4'
        storage_key = self.generate_video_key(job_id, artifact_type, extension, organization_id=organization_id)

        try:
            self.client.upload_file(
                str(path),
                self.bucket_name,
                storage_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'CacheControl': 'max-age=31536000'  # 1 year cache
                }
            )

            # Generate URL
            if self.cdn_url:
                url = f"{self.cdn_url}/{storage_key}"
            else:
                url = f"https://{self.bucket_name}.s3.amazonaws.com/{storage_key}"

            logger.info(f"Uploaded video to s3://{self.bucket_name}/{storage_key}")

            return {
                "success": True,
                "storage_key": storage_key,
                "url": url,
                "file_size": file_size,
                "content_type": content_type
            }

        except ClientError as e:
            logger.error(f"Error uploading video: {e}")
            return {"success": False, "error": "Internal server error"}

    def upload_file_content(
        self,
        content: bytes,
        storage_key: str,
        content_type: str
    ) -> Dict[str, Any]:
        """
        Upload file content directly to S3.

        Args:
            content: File bytes
            storage_key: S3 key
            content_type: MIME type

        Returns:
            Dict with upload result
        """
        from io import BytesIO
        from botocore.exceptions import ClientError

        if len(content) > self.MAX_VIDEO_SIZE:
            return {
                "success": False,
                "error": f"Content size exceeds maximum {self.MAX_VIDEO_SIZE} bytes"
            }

        try:
            self.client.upload_fileobj(
                BytesIO(content),
                self.bucket_name,
                storage_key,
                ExtraArgs={'ContentType': content_type}
            )

            if self.cdn_url:
                url = f"{self.cdn_url}/{storage_key}"
            else:
                url = f"https://{self.bucket_name}.s3.amazonaws.com/{storage_key}"

            return {
                "success": True,
                "storage_key": storage_key,
                "url": url,
                "file_size": len(content)
            }

        except ClientError as e:
            logger.error(f"Error uploading content: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_presigned_url(
        self,
        storage_key: str,
        expires_in: int = 3600,
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """
        Generate a presigned download URL.

        Args:
            storage_key: S3 key
            expires_in: URL expiry in seconds
            organization_id: Organization ID for tenant validation (REQUIRED)

        Returns:
            Dict with presigned URL
        """
        from botocore.exceptions import ClientError

        if not organization_id:
            return {"success": False, "error": "organization_id is required for presigned URL generation"}

        # Validate the storage key belongs to this organization
        expected_prefix = f"org-{organization_id}/"
        if not storage_key.startswith(expected_prefix):
            logger.warning(
                f"Presigned URL denied: org {organization_id} cannot access key {storage_key}"
            )
            return {"success": False, "error": "Access denied: video belongs to another organization"}

        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': storage_key
                },
                ExpiresIn=expires_in
            )

            return {
                "success": True,
                "url": url,
                "expires_in": expires_in
            }

        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return {"success": False, "error": "Internal server error"}

    def delete_video(self, storage_key: str) -> Dict[str, Any]:
        """Delete a video from S3."""
        from botocore.exceptions import ClientError

        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            return {"success": True, "deleted": storage_key}

        except ClientError as e:
            logger.error(f"Error deleting video: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_public_url(self, storage_key: str) -> str:
        """Get the public URL for a video (CDN or S3 direct)."""
        if self.cdn_url:
            return f"{self.cdn_url}/{storage_key}"
        return f"https://{self.bucket_name}.s3.amazonaws.com/{storage_key}"


# Singleton instance
_video_s3_service: Optional[VideoS3Service] = None


def get_video_s3_service() -> VideoS3Service:
    """Get or create the video S3 service singleton."""
    global _video_s3_service
    if _video_s3_service is None:
        _video_s3_service = VideoS3Service()
    return _video_s3_service


class VideoHostingService:
    """Service for video hosting, library management, and analytics."""

    # ==========================================================================
    # VIDEO LIBRARY MANAGEMENT
    # ==========================================================================

    def create_video(
        self,
        db: Session,
        organization_id: int,
        title: str,
        video_url: str,
        thumbnail_url: Optional[str] = None,
        project_id: Optional[int] = None,
        render_job_id: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        file_size_bytes: Optional[int] = None,
        format: Optional[str] = None,
        resolution: Optional[str] = None,
        visibility: str = "private",
        description: Optional[str] = None,
        folder_path: str = "/",
        tags: List[str] = None,
    ) -> Dict[str, Any]:
        """Create a new video in the library."""
        share_token = self._generate_share_token()

        result = db.execute(text("""
            INSERT INTO video_library (
                organization_id, title, description, project_id, render_job_id,
                video_url, thumbnail_url, duration_seconds, file_size_bytes,
                format, resolution, share_token, visibility, folder_path, tags,
                created_at, updated_at
            ) VALUES (
                :organization_id, :title, :description, :project_id, :render_job_id,
                :video_url, :thumbnail_url, :duration_seconds, :file_size_bytes,
                :format, :resolution, :share_token, :visibility, :folder_path, :tags,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
        """), {
            "organization_id": organization_id,
            "title": title,
            "description": description,
            "project_id": project_id,
            "render_job_id": render_job_id,
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": duration_seconds,
            "file_size_bytes": file_size_bytes,
            "format": format,
            "resolution": resolution,
            "share_token": share_token,
            "visibility": visibility,
            "folder_path": folder_path,
            "tags": tags or [],
        })

        video_id = result.fetchone()[0]
        db.commit()

        return self.get_video(db, video_id)

    def get_video(self, db: Session, video_id: int) -> Optional[Dict[str, Any]]:
        """Get video by ID."""
        result = db.execute(text("""
            SELECT * FROM video_library WHERE id = :video_id
        """), {"video_id": video_id})

        row = result.fetchone()
        return dict(row._mapping) if row else None

    def get_video_by_share_token(self, db: Session, share_token: str) -> Optional[Dict[str, Any]]:
        """Get video by share token for public access."""
        result = db.execute(text("""
            SELECT * FROM video_library
            WHERE share_token = :share_token
                AND visibility IN ('unlisted', 'public')
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """), {"share_token": share_token})

        row = result.fetchone()
        return dict(row._mapping) if row else None

    def list_videos(
        self,
        db: Session,
        organization_id: int,
        folder_path: Optional[str] = None,
        visibility: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List videos with filtering."""
        filters = ["organization_id = :organization_id"]
        params = {"organization_id": organization_id, "limit": limit, "offset": offset}

        if folder_path:
            filters.append("folder_path = :folder_path")
            params["folder_path"] = folder_path

        if visibility:
            filters.append("visibility = :visibility")
            params["visibility"] = visibility

        if search:
            filters.append("(title ILIKE :search OR description ILIKE :search)")
            params["search"] = f"%{search}%"

        if tags:
            filters.append("tags && :tags")
            params["tags"] = tags

        where_clause = " AND ".join(filters)

        # Get total count
        query = f"""
            SELECT COUNT(*) FROM video_library WHERE {where_clause}
        """
        count_result = db.execute(text(query), params)
        total = count_result.scalar()

        # Get videos
        query = f"""
            SELECT * FROM video_library
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(query), params)

        videos = [dict(row._mapping) for row in result.fetchall()]
        return videos, total

    def update_video(
        self,
        db: Session,
        video_id: int,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """Update video metadata."""
        allowed_fields = {
            "title", "description", "visibility", "password", "expires_at",
            "allow_embed", "allowed_domains", "cta_enabled", "cta_config",
            "folder_path", "tags", "thumbnail_url", "poster_url"
        }

        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered_updates:
            return self.get_video(db, video_id)

        set_clauses = [f"{k} = :{k}" for k in filtered_updates.keys()]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")

        filtered_updates["video_id"] = video_id

        query = f"""
            UPDATE video_library SET {', '.join(set_clauses)}
            WHERE id = :video_id
        """
        db.execute(text(query), filtered_updates)
        db.commit()

        return self.get_video(db, video_id)

    def delete_video(self, db: Session, video_id: int, soft_delete: bool = True) -> bool:
        """Delete a video (soft delete by default)."""
        if soft_delete:
            db.execute(text("""
                UPDATE video_library
                SET visibility = 'private', archived_at = CURRENT_TIMESTAMP
                WHERE id = :video_id
            """), {"video_id": video_id})
        else:
            db.execute(text("""
                DELETE FROM video_library WHERE id = :video_id
            """), {"video_id": video_id})

        db.commit()
        return True

    def regenerate_share_token(self, db: Session, video_id: int) -> str:
        """Regenerate the share token for a video."""
        new_token = self._generate_share_token()

        db.execute(text("""
            UPDATE video_library
            SET share_token = :new_token, updated_at = CURRENT_TIMESTAMP
            WHERE id = :video_id
        """), {"video_id": video_id, "new_token": new_token})
        db.commit()

        return new_token

    # ==========================================================================
    # SHARING & EMBEDDING
    # ==========================================================================

    def get_share_url(self, db: Session, video_id: int) -> Optional[str]:
        """Get the shareable URL for a video."""
        video = self.get_video(db, video_id)
        if not video:
            return None

        base_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
        return f"{base_url}/watch/{video['share_token']}"

    def get_embed_code(
        self,
        db: Session,
        video_id: int,
        width: int = 640,
        height: int = 360,
        autoplay: bool = False,
        muted: bool = False,
    ) -> Optional[str]:
        """Generate embed code for a video."""
        video = self.get_video(db, video_id)
        if not video or not video.get("allow_embed"):
            return None

        base_url = os.getenv("API_URL", "https://app.perenniaai.com")
        embed_url = f"{base_url}/api/v1/video-os/embed/{video['share_token']}"

        params = []
        if autoplay:
            params.append("autoplay=1")
        if muted:
            params.append("muted=1")

        if params:
            embed_url += "?" + "&".join(params)

        return f'''<iframe
    src="{embed_url}"
    width="{width}"
    height="{height}"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen>
</iframe>'''

    def check_embed_access(
        self,
        db: Session,
        share_token: str,
        referrer: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if embedding is allowed from the given referrer."""
        video = self.get_video_by_share_token(db, share_token)
        if not video:
            return False, None

        if not video.get("allow_embed"):
            return False, None

        allowed_domains = video.get("allowed_domains", [])
        if allowed_domains and referrer:
            # Extract domain from referrer
            from urllib.parse import urlparse
            parsed = urlparse(referrer)
            domain = parsed.netloc.lower()

            if not any(domain.endswith(allowed) for allowed in allowed_domains):
                return False, None

        return True, video

    # ==========================================================================
    # VIEWER SESSIONS
    # ==========================================================================

    def create_viewer_session(
        self,
        db: Session,
        video_id: int,
        viewer_id: Optional[str] = None,
        lead_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        user_id: Optional[int] = None,
        viewer_name: Optional[str] = None,
        viewer_email: Optional[str] = None,
        viewer_company: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        referrer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new viewer session."""
        session_id = str(uuid.uuid4())

        result = db.execute(text("""
            INSERT INTO video_viewer_sessions (
                video_id, session_id, viewer_id, lead_id, contact_id, user_id,
                viewer_name, viewer_email, viewer_company,
                user_agent, ip_address, referrer,
                started_at, last_activity_at
            ) VALUES (
                :video_id, :session_id, :viewer_id, :lead_id, :contact_id, :user_id,
                :viewer_name, :viewer_email, :viewer_company,
                :user_agent, :ip_address, :referrer,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
        """), {
            "video_id": video_id,
            "session_id": session_id,
            "viewer_id": viewer_id,
            "lead_id": lead_id,
            "contact_id": contact_id,
            "user_id": user_id,
            "viewer_name": viewer_name,
            "viewer_email": viewer_email,
            "viewer_company": viewer_company,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "referrer": referrer,
        })

        session_db_id = result.fetchone()[0]
        db.commit()

        # Increment view count
        db.execute(text("""
            UPDATE video_library
            SET view_count = view_count + 1,
                last_viewed_at = CURRENT_TIMESTAMP
            WHERE id = :video_id
        """), {"video_id": video_id})
        db.commit()

        return {
            "id": session_db_id,
            "session_id": session_id,
            "video_id": video_id,
        }

    def update_viewer_session(
        self,
        db: Session,
        session_id: str,
        watch_time_seconds: Optional[int] = None,
        max_percent_watched: Optional[float] = None,
        completed: Optional[bool] = None,
        cta_shown: Optional[bool] = None,
        cta_clicked: Optional[bool] = None,
    ) -> bool:
        """Update viewer session with new engagement data."""
        updates = ["last_activity_at = CURRENT_TIMESTAMP"]
        params = {"session_id": session_id}

        if watch_time_seconds is not None:
            updates.append("watch_time_seconds = GREATEST(watch_time_seconds, :watch_time)")
            params["watch_time"] = watch_time_seconds

        if max_percent_watched is not None:
            updates.append("max_percent_watched = GREATEST(max_percent_watched, :max_percent)")
            params["max_percent"] = max_percent_watched

        if completed is not None:
            updates.append("completed = :completed")
            params["completed"] = completed

        if cta_shown is not None:
            updates.append("cta_shown = :cta_shown")
            params["cta_shown"] = cta_shown

        if cta_clicked is not None:
            updates.append("cta_clicked = :cta_clicked")
            updates.append("cta_clicked_at = CURRENT_TIMESTAMP")
            params["cta_clicked"] = cta_clicked

        query = f"""
            UPDATE video_viewer_sessions
            SET {', '.join(updates)}
            WHERE session_id = :session_id
        """
        db.execute(text(query), params)
        db.commit()

        return True

    def end_viewer_session(self, db: Session, session_id: str) -> bool:
        """End a viewer session."""
        db.execute(text("""
            UPDATE video_viewer_sessions
            SET ended_at = CURRENT_TIMESTAMP, last_activity_at = CURRENT_TIMESTAMP
            WHERE session_id = :session_id AND ended_at IS NULL
        """), {"session_id": session_id})
        db.commit()

        # Update video aggregate stats
        result = db.execute(text("""
            SELECT video_id, watch_time_seconds, max_percent_watched
            FROM video_viewer_sessions
            WHERE session_id = :session_id
        """), {"session_id": session_id})

        row = result.fetchone()
        if row:
            self._update_video_aggregate_stats(db, row[0])

        return True

    def identify_viewer(
        self,
        db: Session,
        session_id: str,
        viewer_name: Optional[str] = None,
        viewer_email: Optional[str] = None,
        viewer_company: Optional[str] = None,
        lead_id: Optional[int] = None,
    ) -> bool:
        """Identify a viewer mid-session (e.g., after form submission)."""
        updates = []
        params = {"session_id": session_id}

        if viewer_name:
            updates.append("viewer_name = :viewer_name")
            params["viewer_name"] = viewer_name

        if viewer_email:
            updates.append("viewer_email = :viewer_email")
            params["viewer_email"] = viewer_email

        if viewer_company:
            updates.append("viewer_company = :viewer_company")
            params["viewer_company"] = viewer_company

        if lead_id:
            updates.append("lead_id = :lead_id")
            params["lead_id"] = lead_id

        if not updates:
            return False

        query = f"""
            UPDATE video_viewer_sessions
            SET {', '.join(updates)}
            WHERE session_id = :session_id
        """
        db.execute(text(query), params)
        db.commit()

        return True

    # ==========================================================================
    # ANALYTICS EVENTS
    # ==========================================================================

    def track_event(
        self,
        db: Session,
        video_id: int,
        event_type: str,
        session_id: Optional[str] = None,
        event_data: Dict[str, Any] = None,
        video_time_seconds: Optional[float] = None,
        percent_watched: Optional[float] = None,
        client_timestamp: Optional[datetime] = None,
    ) -> int:
        """Track an analytics event."""
        # Get session DB ID if we have a session_id string
        session_db_id = None
        if session_id:
            result = db.execute(text("""
                SELECT id FROM video_viewer_sessions WHERE session_id = :session_id
            """), {"session_id": session_id})
            row = result.fetchone()
            session_db_id = row[0] if row else None

        result = db.execute(text("""
            INSERT INTO video_analytics_events (
                video_id, session_id, event_type, event_data,
                video_time_seconds, percent_watched, client_timestamp, created_at
            ) VALUES (
                :video_id, :session_id, :event_type, :event_data,
                :video_time_seconds, :percent_watched, :client_timestamp, CURRENT_TIMESTAMP
            ) RETURNING id
        """), {
            "video_id": video_id,
            "session_id": session_db_id,
            "event_type": event_type,
            "event_data": event_data or {},
            "video_time_seconds": video_time_seconds,
            "percent_watched": percent_watched,
            "client_timestamp": client_timestamp,
        })

        event_id = result.fetchone()[0]
        db.commit()

        # Handle special event types
        if event_type == "complete" and session_id:
            self.update_viewer_session(db, session_id, completed=True)
        elif event_type == "cta_shown" and session_id:
            self.update_viewer_session(db, session_id, cta_shown=True)
        elif event_type == "cta_clicked" and session_id:
            self.update_viewer_session(db, session_id, cta_clicked=True)

        return event_id

    def track_batch_events(
        self,
        db: Session,
        events: List[Dict[str, Any]]
    ) -> int:
        """Track multiple analytics events in a batch."""
        count = 0
        for event in events:
            self.track_event(
                db,
                video_id=event["video_id"],
                event_type=event["event_type"],
                session_id=event.get("session_id"),
                event_data=event.get("event_data"),
                video_time_seconds=event.get("video_time_seconds"),
                percent_watched=event.get("percent_watched"),
                client_timestamp=event.get("client_timestamp"),
            )
            count += 1

        return count

    # ==========================================================================
    # ANALYTICS AGGREGATION
    # ==========================================================================

    def get_video_analytics(
        self,
        db: Session,
        video_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get comprehensive analytics for a video."""
        params = {"video_id": video_id}
        date_filter = ""

        if start_date:
            date_filter += " AND started_at >= :start_date"
            params["start_date"] = start_date
        if end_date:
            date_filter += " AND started_at <= :end_date"
            params["end_date"] = end_date

        # Get video details
        video = self.get_video(db, video_id)
        if not video:
            return {}

        # Get session aggregates
        query = f"""
            SELECT
                COUNT(*) as total_views,
                COUNT(DISTINCT COALESCE(viewer_id, session_id)) as unique_viewers,
                SUM(watch_time_seconds) as total_watch_time,
                AVG(max_percent_watched) as avg_watch_percent,
                COUNT(CASE WHEN completed THEN 1 END) as completions,
                COUNT(CASE WHEN cta_shown THEN 1 END) as cta_impressions,
                COUNT(CASE WHEN cta_clicked THEN 1 END) as cta_clicks
            FROM video_viewer_sessions
            WHERE video_id = :video_id {date_filter}
        """
        session_stats = db.execute(text(query), params).fetchone()

        # Calculate rates
        total_views = session_stats[0] or 0
        completion_rate = (session_stats[4] / total_views * 100) if total_views > 0 else 0
        cta_click_rate = (session_stats[6] / session_stats[5] * 100) if session_stats[5] > 0 else 0

        # Get views by day
        query = f"""
            SELECT
                DATE(started_at) as date,
                COUNT(*) as views,
                COUNT(DISTINCT COALESCE(viewer_id, session_id)) as unique_viewers
            FROM video_viewer_sessions
            WHERE video_id = :video_id {date_filter}
            GROUP BY DATE(started_at)
            ORDER BY date DESC
            LIMIT 30
        """
        views_by_day = db.execute(text(query), params).fetchall()

        # Get drop-off analysis
        drop_off_points = self._analyze_drop_off(db, video_id, video.get("duration_seconds", 60))

        return {
            "video_id": video_id,
            "title": video["title"],
            "duration_seconds": video.get("duration_seconds"),
            "total_views": total_views,
            "unique_viewers": session_stats[1] or 0,
            "total_watch_time_seconds": session_stats[2] or 0,
            "avg_watch_percent": round(session_stats[3] or 0, 1),
            "completion_rate": round(completion_rate, 1),
            "cta_impressions": session_stats[5] or 0,
            "cta_clicks": session_stats[6] or 0,
            "cta_click_rate": round(cta_click_rate, 1),
            "views_by_day": [
                {"date": str(row[0]), "views": row[1], "unique_viewers": row[2]}
                for row in views_by_day
            ],
            "drop_off_points": drop_off_points,
        }

    def get_watch_heatmap(
        self,
        db: Session,
        video_id: int,
        segment_count: int = 100,
    ) -> Dict[str, Any]:
        """Get watch heatmap showing engagement across video duration."""
        video = self.get_video(db, video_id)
        if not video or not video.get("duration_seconds"):
            return {"segments": [], "duration_seconds": 0}

        duration = video["duration_seconds"]
        segment_duration = duration / segment_count

        # Get all play/seek events to build heatmap
        events = db.execute(text("""
            SELECT video_time_seconds, event_type
            FROM video_analytics_events
            WHERE video_id = :video_id
                AND video_time_seconds IS NOT NULL
                AND event_type IN ('play', 'seek', 'resume')
        """), {"video_id": video_id}).fetchall()

        # Build segment engagement counts
        segments = [0] * segment_count
        for event in events:
            time = event[0]
            segment_idx = min(int(time / segment_duration), segment_count - 1)
            segments[segment_idx] += 1

        # Normalize to percentages
        max_engagement = max(segments) if segments else 1
        normalized = [round(s / max_engagement * 100, 1) for s in segments]

        return {
            "video_id": video_id,
            "duration_seconds": duration,
            "segment_duration_seconds": segment_duration,
            "segments": [
                {
                    "index": i,
                    "start_time": i * segment_duration,
                    "end_time": (i + 1) * segment_duration,
                    "engagement": normalized[i],
                    "raw_count": segments[i],
                }
                for i in range(segment_count)
            ],
        }

    def get_viewer_engagement(
        self,
        db: Session,
        organization_id: int,
        video_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get engagement data for specific viewers."""
        params = {"organization_id": organization_id, "limit": limit}
        filters = ["vl.organization_id = :organization_id"]

        if video_id:
            filters.append("vs.video_id = :video_id")
            params["video_id"] = video_id

        if lead_id:
            filters.append("vs.lead_id = :lead_id")
            params["lead_id"] = lead_id

        where_clause = " AND ".join(filters)

        query = f"""
            SELECT
                vs.viewer_email,
                vs.viewer_name,
                vs.lead_id,
                COUNT(DISTINCT vs.video_id) as videos_watched,
                SUM(vs.watch_time_seconds) as total_watch_time,
                AVG(vs.max_percent_watched) as avg_watch_percent,
                SUM(CASE WHEN vs.cta_clicked THEN 1 ELSE 0 END) as cta_clicks,
                MAX(vs.started_at) as last_watched
            FROM video_viewer_sessions vs
            JOIN video_library vl ON vl.id = vs.video_id
            WHERE {where_clause}
                AND vs.viewer_email IS NOT NULL
            GROUP BY vs.viewer_email, vs.viewer_name, vs.lead_id
            ORDER BY total_watch_time DESC
            LIMIT :limit
        """
        result = db.execute(text(query), params)

        return [
            {
                "viewer_email": row[0],
                "viewer_name": row[1],
                "lead_id": row[2],
                "videos_watched": row[3],
                "total_watch_time_seconds": row[4] or 0,
                "avg_watch_percent": round(row[5] or 0, 1),
                "cta_clicks": row[6],
                "last_watched_at": row[7].isoformat() if row[7] else None,
            }
            for row in result.fetchall()
        ]

    def get_org_video_stats(
        self,
        db: Session,
        organization_id: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get organization-wide video analytics summary."""
        result = db.execute(text("""
            SELECT
                COUNT(DISTINCT vl.id) as total_videos,
                SUM(vl.view_count) as total_views,
                SUM(vl.unique_viewer_count) as total_unique_viewers,
                SUM(vl.total_watch_time_seconds) as total_watch_time,
                AVG(vl.avg_watch_percent) as avg_watch_percent
            FROM video_library vl
            WHERE vl.organization_id = :organization_id
        """), {"organization_id": organization_id}).fetchone()

        # Get recent activity
        recent_views = db.execute(text("""
            SELECT COUNT(*)
            FROM video_viewer_sessions vs
            JOIN video_library vl ON vl.id = vs.video_id
            WHERE vl.organization_id = :organization_id
                AND vs.started_at >= CURRENT_DATE - :days
        """), {"organization_id": organization_id, "days": days}).scalar()

        # Top performing videos
        top_videos = db.execute(text("""
            SELECT id, title, view_count, avg_watch_percent
            FROM video_library
            WHERE organization_id = :organization_id
            ORDER BY view_count DESC
            LIMIT 5
        """), {"organization_id": organization_id}).fetchall()

        return {
            "total_videos": result[0] or 0,
            "total_views": result[1] or 0,
            "total_unique_viewers": result[2] or 0,
            "total_watch_time_seconds": result[3] or 0,
            "avg_watch_percent": round(result[4] or 0, 1),
            "recent_views": recent_views,
            "period_days": days,
            "top_videos": [
                {
                    "id": row[0],
                    "title": row[1],
                    "view_count": row[2],
                    "avg_watch_percent": round(row[3] or 0, 1),
                }
                for row in top_videos
            ],
        }

    # ==========================================================================
    # CTA OVERLAYS
    # ==========================================================================

    def create_cta_overlay(
        self,
        db: Session,
        organization_id: int,
        name: str,
        cta_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new CTA overlay template."""
        result = db.execute(text("""
            INSERT INTO video_cta_overlays (
                organization_id, name, cta_type,
                show_at_percent, show_at_seconds, show_on_pause, show_on_end,
                headline, description, button_text, button_url, button_color,
                form_fields, position, animation, action_type, action_config,
                is_active, created_at, updated_at
            ) VALUES (
                :organization_id, :name, :cta_type,
                :show_at_percent, :show_at_seconds, :show_on_pause, :show_on_end,
                :headline, :description, :button_text, :button_url, :button_color,
                :form_fields, :position, :animation, :action_type, :action_config,
                true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
        """), {
            "organization_id": organization_id,
            "name": name,
            "cta_type": cta_type,
            "show_at_percent": kwargs.get("show_at_percent"),
            "show_at_seconds": kwargs.get("show_at_seconds"),
            "show_on_pause": kwargs.get("show_on_pause", False),
            "show_on_end": kwargs.get("show_on_end", True),
            "headline": kwargs.get("headline"),
            "description": kwargs.get("description"),
            "button_text": kwargs.get("button_text"),
            "button_url": kwargs.get("button_url"),
            "button_color": kwargs.get("button_color"),
            "form_fields": kwargs.get("form_fields", []),
            "position": kwargs.get("position", "center"),
            "animation": kwargs.get("animation", "fade_in"),
            "action_type": kwargs.get("action_type"),
            "action_config": kwargs.get("action_config", {}),
        })

        cta_id = result.fetchone()[0]
        db.commit()

        return self.get_cta_overlay(db, cta_id)

    def get_cta_overlay(self, db: Session, cta_id: int) -> Optional[Dict[str, Any]]:
        """Get CTA overlay by ID."""
        result = db.execute(text("""
            SELECT * FROM video_cta_overlays WHERE id = :cta_id
        """), {"cta_id": cta_id})

        row = result.fetchone()
        return dict(row._mapping) if row else None

    def list_cta_overlays(
        self,
        db: Session,
        organization_id: int,
        cta_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List CTA overlays for an organization."""
        params = {"organization_id": organization_id}
        filters = ["organization_id = :organization_id", "is_active = true"]

        if cta_type:
            filters.append("cta_type = :cta_type")
            params["cta_type"] = cta_type

        query = f"""
            SELECT * FROM video_cta_overlays
            WHERE {' AND '.join(filters)}
            ORDER BY created_at DESC
        """
        result = db.execute(text(query), params)

        return [dict(row._mapping) for row in result.fetchall()]

    # ==========================================================================
    # CRM INTEGRATION
    # ==========================================================================

    def log_crm_event(
        self,
        db: Session,
        event_type: str,
        video_id: int,
        lead_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        details: Dict[str, Any] = None,
    ) -> None:
        """Log video engagement to CRM activity log."""
        video = self.get_video(db, video_id)
        video_title = video["title"] if video else f"Video #{video_id}"

        description = f"Video: {video_title}"
        if event_type == "play":
            description = f"Started watching: {video_title}"
        elif event_type == "complete":
            description = f"Completed watching: {video_title}"
        elif event_type == "cta_clicked":
            description = f"Clicked CTA on: {video_title}"

        # Log to lead activities if lead_id present
        if lead_id:
            db.execute(text("""
                INSERT INTO lead_activities (
                    lead_id, activity_type, description, metadata, created_at
                ) VALUES (
                    :lead_id, 'video_engagement', :description, :metadata, CURRENT_TIMESTAMP
                )
            """), {
                "lead_id": lead_id,
                "description": description,
                "metadata": {
                    "video_id": video_id,
                    "event_type": event_type,
                    **(details or {}),
                },
            })
            db.commit()

        logger.info(f"CRM Event: {event_type} on video {video_id} for lead {lead_id}")

    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================

    def _generate_share_token(self) -> str:
        """Generate a unique share token."""
        random_bytes = os.urandom(16)
        timestamp = datetime.now(timezone.utc).timestamp()
        combined = f"{random_bytes.hex()}{timestamp}"
        return hashlib.sha256(combined.encode()).hexdigest()[:24]

    def _update_video_aggregate_stats(self, db: Session, video_id: int) -> None:
        """Update video aggregate statistics from sessions."""
        db.execute(text("""
            UPDATE video_library vl SET
                unique_viewer_count = (
                    SELECT COUNT(DISTINCT COALESCE(viewer_id, session_id))
                    FROM video_viewer_sessions WHERE video_id = :video_id
                ),
                total_watch_time_seconds = (
                    SELECT COALESCE(SUM(watch_time_seconds), 0)
                    FROM video_viewer_sessions WHERE video_id = :video_id
                ),
                avg_watch_percent = (
                    SELECT COALESCE(AVG(max_percent_watched), 0)
                    FROM video_viewer_sessions WHERE video_id = :video_id
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :video_id
        """), {"video_id": video_id})
        db.commit()

    def _analyze_drop_off(
        self,
        db: Session,
        video_id: int,
        duration_seconds: float,
    ) -> List[Dict[str, Any]]:
        """Analyze where viewers drop off in the video."""
        # Get max_percent_watched distribution
        result = db.execute(text("""
            SELECT
                FLOOR(max_percent_watched / 10) * 10 as bucket,
                COUNT(*) as count
            FROM video_viewer_sessions
            WHERE video_id = :video_id
            GROUP BY bucket
            ORDER BY bucket
        """), {"video_id": video_id})

        buckets = {row[0]: row[1] for row in result.fetchall()}

        # Find significant drop-off points
        drop_offs = []
        prev_count = buckets.get(0, 0)

        for bucket in range(10, 110, 10):
            count = buckets.get(bucket, 0)
            if prev_count > 0:
                drop_rate = ((prev_count - count) / prev_count) * 100
                if drop_rate > 20:  # Significant drop
                    drop_offs.append({
                        "percent": bucket,
                        "time_seconds": (bucket / 100) * duration_seconds,
                        "drop_rate": round(drop_rate, 1),
                        "viewers_remaining": count,
                    })
            prev_count = count

        return drop_offs


# Singleton instance
video_hosting_service = VideoHostingService()
