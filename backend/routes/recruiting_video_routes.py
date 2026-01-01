"""
Recruiting Video Routes

Handles video recording and sharing with candidates:
- Presigned URL generation for video uploads
- Video storage and metadata management
- AI notification to candidates when videos are posted
- Video retrieval for candidate portals
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from services.perennia_s3_service import get_s3_service

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


# User proxy class for auth
class UserProxy:
    def __init__(self, row):
        self.id = row[0]
        self.email = row[1]
        self.name = row[2] if len(row) > 2 else None


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from jose import jwt

    # For testing without auth, return demo user
    if not credentials:
        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": "admin@perenniaai.com"}
        )
        user_row = result.fetchone()
        if user_row:
            return {"user_id": user_row[0], "email": user_row[1], "name": user_row[2]}
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user with raw SQL
        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        return {"user_id": user_row[0], "email": user_row[1], "name": user_row[2]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

router = APIRouter(prefix="/api/v1/recruiting/video", tags=["Recruiting Video"])


# =============================================================================
# Pydantic Models
# =============================================================================

class UploadUrlRequest(BaseModel):
    candidate_id: int
    content_type: str = "video/webm"
    filename: Optional[str] = None


class UploadUrlResponse(BaseModel):
    upload_url: str
    video_key: str
    expires_in: int


class CompleteUploadRequest(BaseModel):
    candidate_id: int
    video_key: str
    message: Optional[str] = None
    send_notification: bool = True
    duration_seconds: Optional[int] = None


class VideoMessage(BaseModel):
    id: int
    candidate_id: int
    video_url: str
    message: Optional[str]
    duration_seconds: Optional[int]
    recruiter_name: str
    recruiter_photo: Optional[str]
    created_at: datetime
    viewed_at: Optional[datetime]


# =============================================================================
# Helper Functions
# =============================================================================

def generate_video_key(candidate_id: int, filename: str = None) -> str:
    """Generate a unique S3 key for the video."""
    ext = "webm"
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    unique_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    return f"recruit-videos/{candidate_id}/{timestamp}_{unique_id}.{ext}"


async def send_candidate_notification(
    db,
    candidate_id: int,
    recruiter_id: int,
    message: str,
    video_id: int
):
    """Send AI notification to candidate about new video."""
    try:
        # Get candidate's portal workspace
        workspace_result = db.execute(text("""
            SELECT id, slug FROM recruit_portal_workspaces
            WHERE candidate_id = :candidate_id AND is_active = true
        """), {"candidate_id": candidate_id})
        workspace = workspace_result.fetchone()

        if not workspace:
            logger.warning(f"No portal workspace for candidate {candidate_id}")
            return

        # Get recruiter info
        recruiter_result = db.execute(text("""
            SELECT name FROM users WHERE id = :user_id
        """), {"user_id": recruiter_id})
        recruiter = recruiter_result.fetchone()
        recruiter_name = recruiter.name if recruiter else "Your recruiter"

        # Create AI message in portal chat
        ai_message = f"""🎬 **New Video Message!**

{recruiter_name} just recorded a personalized video message for you!

{message if message else "Check it out in your portal to see what they have to say."}

Watch it now in the Videos section of your portal."""

        db.execute(text("""
            INSERT INTO recruit_portal_messages (workspace_id, role, content, metadata, created_at)
            VALUES (:workspace_id, 'assistant', :content, :metadata, NOW())
        """), {
            "workspace_id": workspace.id,
            "content": ai_message,
            "metadata": f'{{"type": "video_notification", "video_id": {video_id}}}'
        })

        db.commit()
        logger.info(f"Sent video notification to candidate {candidate_id}")

    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


# =============================================================================
# Routes
# =============================================================================

@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    request: UploadUrlRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a presigned URL for uploading a video.

    This URL allows direct upload to S3 from the browser.
    """
    s3_service = get_s3_service()

    # Generate unique video key
    video_key = generate_video_key(request.candidate_id, request.filename)

    # Allow video content types
    allowed_video_types = [
        "video/webm",
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo"
    ]

    if request.content_type not in allowed_video_types:
        raise HTTPException(
            status_code=400,
            detail=f"Content type '{request.content_type}' not allowed for videos"
        )

    # Generate presigned PUT URL (simpler for video uploads)
    try:
        presigned_url = s3_service.s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': s3_service.bucket_name,
                'Key': video_key,
                'ContentType': request.content_type
            },
            ExpiresIn=3600  # 1 hour
        )

        return UploadUrlResponse(
            upload_url=presigned_url,
            video_key=video_key,
            expires_in=3600
        )

    except Exception as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")


@router.post("/complete")
async def complete_upload(
    request: CompleteUploadRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Complete a video upload and optionally notify the candidate.

    This is called after the video has been uploaded to S3.
    """
    s3_service = get_s3_service()
    user_id = current_user.get("user_id") or current_user.get("id") or 1

    # Verify the video exists in S3
    verify_result = s3_service.verify_upload(request.video_key)
    if not verify_result.get("success") or not verify_result.get("exists"):
        raise HTTPException(status_code=400, detail="Video not found in storage")

    # Generate download URL for the video
    download_result = s3_service.get_presigned_download_url(
        request.video_key,
        expires_in=86400 * 7  # 7 days
    )

    if not download_result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to generate video URL")

    try:
        # Get recruiter info
        recruiter_result = db.execute(text("""
            SELECT name, profile_photo_url FROM users WHERE id = :user_id
        """), {"user_id": user_id})
        recruiter = recruiter_result.fetchone()

        # Save video metadata
        result = db.execute(text("""
            INSERT INTO recruit_video_messages (
                candidate_id,
                recruiter_id,
                video_key,
                video_url,
                message,
                duration_seconds,
                created_at
            ) VALUES (
                :candidate_id,
                :recruiter_id,
                :video_key,
                :video_url,
                :message,
                :duration_seconds,
                NOW()
            )
            RETURNING id
        """), {
            "candidate_id": request.candidate_id,
            "recruiter_id": user_id,
            "video_key": request.video_key,
            "video_url": download_result["presigned_url"],
            "message": request.message,
            "duration_seconds": request.duration_seconds
        })

        video_id = result.fetchone().id
        db.commit()

        # Send notification to candidate if requested
        if request.send_notification:
            await send_candidate_notification(
                db,
                request.candidate_id,
                user_id,
                request.message,
                video_id
            )

        # Also create a company update for the portal
        db.execute(text("""
            INSERT INTO recruit_company_updates (
                title,
                content,
                media_url,
                category,
                is_featured,
                is_active,
                published_at,
                created_by,
                metadata
            ) VALUES (
                :title,
                :content,
                :media_url,
                'video_message',
                true,
                true,
                NOW(),
                :created_by,
                :metadata
            )
        """), {
            "title": f"Personal Message from {recruiter.name if recruiter else 'Your Recruiter'}",
            "content": request.message or "Your recruiter recorded a personalized message just for you!",
            "media_url": download_result["presigned_url"],
            "created_by": user_id,
            "metadata": f'{{"candidate_id": {request.candidate_id}, "video_id": {video_id}, "type": "personalized_video"}}'
        })
        db.commit()

        return {
            "success": True,
            "video_id": video_id,
            "message": "Video uploaded and candidate notified" if request.send_notification else "Video uploaded successfully"
        }

    except Exception as e:
        logger.error(f"Failed to complete video upload: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candidate/{candidate_id}")
async def get_candidate_videos(
    candidate_id: int,
    limit: int = Query(default=10, le=50),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get all videos sent to a candidate."""
    try:
        result = db.execute(text("""
            SELECT
                v.id,
                v.candidate_id,
                v.video_key,
                v.video_url,
                v.message,
                v.duration_seconds,
                v.created_at,
                v.viewed_at,
                u.name as recruiter_name,
                u.profile_photo_url as recruiter_photo
            FROM recruit_video_messages v
            LEFT JOIN users u ON u.id = v.recruiter_id
            WHERE v.candidate_id = :candidate_id
            ORDER BY v.created_at DESC
            LIMIT :limit
        """), {"candidate_id": candidate_id, "limit": limit})

        videos = []
        s3_service = get_s3_service()

        for row in result.fetchall():
            # Regenerate presigned URL if needed
            video_url = row.video_url
            if row.video_key:
                download_result = s3_service.get_presigned_download_url(
                    row.video_key,
                    expires_in=86400  # 24 hours
                )
                if download_result.get("success"):
                    video_url = download_result["presigned_url"]

            videos.append({
                "id": row.id,
                "candidate_id": row.candidate_id,
                "video_url": video_url,
                "message": row.message,
                "duration_seconds": row.duration_seconds,
                "recruiter_name": row.recruiter_name or "Recruiter",
                "recruiter_photo": row.recruiter_photo,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "viewed_at": row.viewed_at.isoformat() if row.viewed_at else None
            })

        return {"videos": videos, "count": len(videos)}

    except Exception as e:
        logger.error(f"Failed to get candidate videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-viewed/{video_id}")
async def mark_video_viewed(
    video_id: int,
    db=Depends(get_db)
):
    """Mark a video as viewed by the candidate."""
    try:
        db.execute(text("""
            UPDATE recruit_video_messages
            SET viewed_at = NOW()
            WHERE id = :video_id AND viewed_at IS NULL
        """), {"video_id": video_id})
        db.commit()

        return {"success": True}

    except Exception as e:
        logger.error(f"Failed to mark video viewed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Public Portal Routes (no auth required)
# =============================================================================

@router.post("/admin/run-migration")
async def run_video_migration(
    admin_key: str = Query(...),
    db=Depends(get_db)
):
    """Run migration to create video messages table."""
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_video_messages (
                id SERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                recruiter_id INTEGER,
                video_key VARCHAR(500),
                video_url TEXT,
                message TEXT,
                duration_seconds INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                viewed_at TIMESTAMP
            )
        """))
        logger.info("Created recruit_video_messages table")

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recruit_video_messages_candidate
            ON recruit_video_messages(candidate_id)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recruit_video_messages_recruiter
            ON recruit_video_messages(recruiter_id)
        """))

        db.commit()
        return {"status": "success", "message": "Video messages table created"}

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portal/{slug}/videos")
async def get_portal_videos(
    slug: str,
    token: Optional[str] = Query(default=None),
    db=Depends(get_db)
):
    """
    Get videos for a candidate portal (public endpoint).

    This is accessed from the RecruitPortal page.
    """
    try:
        # Get workspace and candidate
        result = db.execute(text("""
            SELECT w.id, w.candidate_id, c.first_name, c.last_name
            FROM recruit_portal_workspaces w
            JOIN mm_candidates c ON c.id = w.candidate_id
            WHERE w.slug = :slug AND w.is_active = true
        """), {"slug": slug})

        workspace = result.fetchone()
        if not workspace:
            raise HTTPException(status_code=404, detail="Portal not found")

        # Get videos for this candidate
        videos_result = db.execute(text("""
            SELECT
                v.id,
                v.video_key,
                v.video_url,
                v.message,
                v.duration_seconds,
                v.created_at,
                v.viewed_at,
                u.name as recruiter_name,
                u.profile_photo_url as recruiter_photo
            FROM recruit_video_messages v
            LEFT JOIN users u ON u.id = v.recruiter_id
            WHERE v.candidate_id = :candidate_id
            ORDER BY v.created_at DESC
            LIMIT 20
        """), {"candidate_id": workspace.candidate_id})

        videos = []
        s3_service = get_s3_service()

        for row in videos_result.fetchall():
            # Regenerate presigned URL
            video_url = row.video_url
            if row.video_key:
                download_result = s3_service.get_presigned_download_url(
                    row.video_key,
                    expires_in=86400  # 24 hours
                )
                if download_result.get("success"):
                    video_url = download_result["presigned_url"]

            videos.append({
                "id": row.id,
                "video_url": video_url,
                "message": row.message,
                "duration_seconds": row.duration_seconds,
                "recruiter_name": row.recruiter_name or "Your Recruiter",
                "recruiter_photo": row.recruiter_photo,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "is_new": row.viewed_at is None
            })

        return {
            "candidate_name": f"{workspace.first_name} {workspace.last_name}",
            "videos": videos,
            "count": len(videos)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get portal videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))
