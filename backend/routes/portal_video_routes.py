"""
Portal Video Routes

Handles video recording and sharing with borrowers and realtors:
- Presigned URL generation for video uploads
- Video storage and metadata management
- Video retrieval for client and realtor portals

Supports:
- Client Portal (PURL workspaces)
- Realtor Portal (token-based auth)
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from services.perennia_s3_service import get_s3_service
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

security = HTTPBearer(auto_error=False)


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from auth.tokens import verify_access_token

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        payload = verify_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = db.execute(
            text("SELECT id, email, full_name, organization_id FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        return {"user_id": user_row[0], "email": user_row[1], "name": user_row[2], "organization_id": user_row[3]}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


router = APIRouter(prefix="/api/v1/portal-video", tags=["Portal Video"])


# =============================================================================
# Pydantic Models
# =============================================================================

class UploadUrlRequest(BaseModel):
    portal_type: str  # 'client' or 'realtor'
    recipient_id: int  # workspace_id for client, partner_id for realtor
    content_type: str = "video/webm"
    filename: Optional[str] = None


class UploadUrlResponse(BaseModel):
    upload_url: str
    video_key: str
    expires_in: int


class CompleteUploadRequest(BaseModel):
    portal_type: str
    recipient_id: int
    video_key: str
    message: Optional[str] = None
    send_notification: bool = True
    duration_seconds: Optional[int] = None


# =============================================================================
# Helper Functions
# =============================================================================

def generate_video_key(portal_type: str, recipient_id: int, filename: str = None, organization_id: int = None) -> str:
    """Generate a unique S3 key for the video with tenant prefix."""
    if not organization_id:
        raise ValueError("organization_id is required for tenant-isolated video storage")

    ext = "webm"
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    unique_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    return f"org-{organization_id}/portal-videos/{portal_type}/{recipient_id}/{timestamp}_{unique_id}.{ext}"


# =============================================================================
# Routes - Upload Management
# =============================================================================

@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    request: UploadUrlRequest,
    current_user: dict = Depends(get_current_user)
):
    """Get a presigned URL for uploading a video."""
    s3_service = get_s3_service()

    org_id = current_user.get("organization_id")
    video_key = generate_video_key(request.portal_type, request.recipient_id, request.filename, organization_id=org_id)

    allowed_video_types = ["video/webm", "video/mp4", "video/quicktime", "video/x-msvideo"]

    if request.content_type not in allowed_video_types:
        raise HTTPException(
            status_code=400,
            detail=f"Content type '{request.content_type}' not allowed for videos"
        )

    try:
        presigned_url = s3_service.s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': s3_service.bucket_name,
                'Key': video_key,
                'ContentType': request.content_type
            },
            ExpiresIn=3600
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
    """Complete a video upload and optionally notify the recipient."""
    s3_service = get_s3_service()
    user_id = current_user.get("user_id") or current_user.get("id") or 1

    # Verify the video exists in S3
    verify_result = s3_service.verify_upload(request.video_key)
    if not verify_result.get("success") or not verify_result.get("exists"):
        raise HTTPException(status_code=400, detail="Video not found in storage")

    # Get video URL (try public first, fall back to presigned)
    org_id = current_user.get("organization_id")
    public_result = s3_service.make_public_and_get_url(request.video_key, organization_id=org_id)
    if not public_result.get("success"):
        download_result = s3_service.get_presigned_download_url(
            request.video_key, expires_in=86400 * 7, organization_id=org_id,
        )
        if not download_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to generate video URL")
        video_url = download_result["presigned_url"]
    else:
        video_url = public_result.get("public_url") or public_result.get("presigned_url")

    try:
        # Get sender info
        sender_result = db.execute(text("""
            SELECT full_name FROM users WHERE id = :user_id
        """), {"user_id": user_id})
        sender = sender_result.fetchone()

        # Save video metadata
        result = db.execute(text("""
            INSERT INTO portal_video_messages (
                portal_type,
                recipient_id,
                sender_id,
                video_key,
                video_url,
                message,
                duration_seconds,
                created_at
            ) VALUES (
                :portal_type,
                :recipient_id,
                :sender_id,
                :video_key,
                :video_url,
                :message,
                :duration_seconds,
                NOW()
            )
            RETURNING id
        """), {
            "portal_type": request.portal_type,
            "recipient_id": request.recipient_id,
            "sender_id": user_id,
            "video_key": request.video_key,
            "video_url": video_url,
            "message": request.message,
            "duration_seconds": request.duration_seconds
        })

        video_id = result.fetchone().id
        db.commit()

        return {
            "success": True,
            "video_id": video_id,
            "message": "Video uploaded successfully"
        }

    except SQLAlchemyError as e:
        logger.error(f"Failed to complete video upload: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Routes - Client Portal (PURL Workspace)
# =============================================================================

@router.get("/client/{slug}/videos")
async def get_client_portal_videos(
    slug: str,
    token: Optional[str] = Query(default=None),
    db=Depends(get_db)
):
    """Get videos for a client portal workspace."""
    try:
        # Get workspace with primary borrower contact
        result = db.execute(text("""
            SELECT w.id, w.display_name,
                   c.first_name, c.last_name
            FROM purl_workspaces w
            LEFT JOIN purl_contacts c ON c.workspace_id = w.id AND c.contact_type = 'borrower'
            WHERE w.slug = :slug
        """), {"slug": slug})

        workspace = result.fetchone()
        if not workspace:
            raise HTTPException(status_code=404, detail="Portal not found")

        # Get videos for this workspace
        videos_result = db.execute(text("""
            SELECT
                v.id,
                v.video_key,
                v.video_url,
                v.message,
                v.duration_seconds,
                v.created_at,
                v.viewed_at,
                u.full_name as sender_name
            FROM portal_video_messages v
            LEFT JOIN users u ON u.id = v.sender_id
            WHERE v.portal_type = 'client' AND v.recipient_id = :workspace_id
            ORDER BY v.created_at DESC
            LIMIT 20
        """), {"workspace_id": workspace.id})

        videos = []
        s3_service = get_s3_service()

        for row in videos_result.fetchall():
            video_url = row.video_url
            if row.video_key:
                download_result = s3_service.get_presigned_download_url(row.video_key, expires_in=86400)
                if download_result.get("success"):
                    video_url = download_result["presigned_url"]

            videos.append({
                "id": row.id,
                "video_url": video_url,
                "message": row.message,
                "duration_seconds": row.duration_seconds,
                "sender_name": row.sender_name or "Your Loan Officer",
                "sender_photo": None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "is_new": row.viewed_at is None
            })

        # Build borrower name from contact or fallback to display_name
        if workspace.first_name and workspace.last_name:
            borrower_name = f"{workspace.first_name} {workspace.last_name}"
        else:
            borrower_name = workspace.display_name or "Client"

        return {
            "borrower_name": borrower_name,
            "videos": videos,
            "count": len(videos)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get client portal videos: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/client/mark-viewed/{video_id}")
async def mark_client_video_viewed(
    video_id: int,
    db=Depends(get_db)
):
    """Mark a client portal video as viewed and delete it from the system."""
    try:
        # Get video details before deletion
        video_result = db.execute(text("""
            SELECT id, video_key FROM portal_video_messages
            WHERE id = :video_id
        """), {"video_id": video_id})
        video = video_result.fetchone()

        if not video:
            return {"success": True, "message": "Video not found or already deleted"}

        # Delete from S3 if video_key exists
        if video.video_key:
            try:
                s3_service = get_s3_service()
                s3_service.s3_client.delete_object(
                    Bucket=s3_service.bucket_name,
                    Key=video.video_key
                )
                logger.info(f"Deleted video from S3: {video.video_key}")
            except Exception as s3_err:
                logger.error(f"Failed to delete video from S3: {s3_err}")

        # Delete from database
        db.execute(text("""
            DELETE FROM portal_video_messages
            WHERE id = :video_id
        """), {"video_id": video_id})
        db.commit()

        logger.info(f"Video {video_id} viewed and deleted from system")
        return {"success": True, "message": "Video viewed and removed"}

    except SQLAlchemyError as e:
        logger.error(f"Failed to process video view: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Routes - Realtor Portal
# =============================================================================

@router.get("/realtor/{partner_id}/videos")
async def get_realtor_portal_videos(
    partner_id: int,
    token: Optional[str] = Query(default=None),
    db=Depends(get_db)
):
    """Get videos for a realtor portal."""
    try:
        # Verify partner exists - referral_partners has name, company columns
        partner_result = db.execute(text("""
            SELECT id, name, company
            FROM referral_partners
            WHERE id = :partner_id
        """), {"partner_id": partner_id})

        partner = partner_result.fetchone()
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")

        # Get videos for this realtor
        videos_result = db.execute(text("""
            SELECT
                v.id,
                v.video_key,
                v.video_url,
                v.message,
                v.duration_seconds,
                v.created_at,
                v.viewed_at,
                u.full_name as sender_name
            FROM portal_video_messages v
            LEFT JOIN users u ON u.id = v.sender_id
            WHERE v.portal_type = 'realtor' AND v.recipient_id = :partner_id
            ORDER BY v.created_at DESC
            LIMIT 20
        """), {"partner_id": partner_id})

        videos = []
        s3_service = get_s3_service()

        for row in videos_result.fetchall():
            video_url = row.video_url
            if row.video_key:
                download_result = s3_service.get_presigned_download_url(row.video_key, expires_in=86400)
                if download_result.get("success"):
                    video_url = download_result["presigned_url"]

            videos.append({
                "id": row.id,
                "video_url": video_url,
                "message": row.message,
                "duration_seconds": row.duration_seconds,
                "sender_name": row.sender_name or "Your Loan Officer",
                "sender_photo": None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "is_new": row.viewed_at is None
            })

        return {
            "partner_name": partner.name or "Partner",
            "videos": videos,
            "count": len(videos)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get realtor portal videos: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/realtor/mark-viewed/{video_id}")
async def mark_realtor_video_viewed(
    video_id: int,
    db=Depends(get_db)
):
    """Mark a realtor portal video as viewed and delete it from the system."""
    try:
        # Get video details before deletion
        video_result = db.execute(text("""
            SELECT id, video_key FROM portal_video_messages
            WHERE id = :video_id
        """), {"video_id": video_id})
        video = video_result.fetchone()

        if not video:
            return {"success": True, "message": "Video not found or already deleted"}

        # Delete from S3 if video_key exists
        if video.video_key:
            try:
                s3_service = get_s3_service()
                s3_service.s3_client.delete_object(
                    Bucket=s3_service.bucket_name,
                    Key=video.video_key
                )
                logger.info(f"Deleted video from S3: {video.video_key}")
            except Exception as s3_err:
                logger.error(f"Failed to delete video from S3: {s3_err}")

        # Delete from database
        db.execute(text("""
            DELETE FROM portal_video_messages
            WHERE id = :video_id
        """), {"video_id": video_id})
        db.commit()

        logger.info(f"Video {video_id} viewed and deleted from system")
        return {"success": True, "message": "Video viewed and removed"}

    except SQLAlchemyError as e:
        logger.error(f"Failed to process video view: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Public Video Viewing (for email recipients)
# =============================================================================

@router.get("/view/{video_key:path}")
async def view_video(
    video_key: str,
    db=Depends(get_db)
):
    """Public endpoint for email recipients to view a video.
    Generates a presigned S3 download URL and redirects to it.
    """
    from fastapi.responses import RedirectResponse

    if not video_key:
        raise HTTPException(status_code=400, detail="Video key is required")

    try:
        s3_service = get_s3_service()

        # Generate presigned download URL (valid for 1 hour)
        download_result = s3_service.get_presigned_download_url(video_key, expires_in=3600)

        if not download_result.get("success"):
            raise HTTPException(status_code=404, detail="Video not found")

        return RedirectResponse(url=download_result["presigned_url"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get video view URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to load video")


# =============================================================================
# Admin Routes
# =============================================================================

@router.post("/admin/configure-s3-cors")
async def configure_s3_cors(
    admin_key: str = Header(..., alias="X-Admin-Key")
):
    """Configure S3 bucket CORS to allow browser-based presigned URL uploads."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        s3_service = get_s3_service()

        cors_configuration = {
            'CORSRules': [
                {
                    'AllowedHeaders': ['Content-Type', 'Authorization', 'x-amz-*'],
                    'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                    'AllowedOrigins': [
                        'https://app.perenniaai.com',
                        'https://perenniaai.com',
                        'https://*.railway.app',
                        'http://localhost:3000',
                        'http://localhost:5173',
                    ],
                    'ExposeHeaders': ['ETag', 'x-amz-version-id'],
                    'MaxAgeSeconds': 3600,
                }
            ]
        }

        s3_service.s3_client.put_bucket_cors(
            Bucket=s3_service.bucket_name,
            CORSConfiguration=cors_configuration,
        )

        # Verify
        result = s3_service.s3_client.get_bucket_cors(Bucket=s3_service.bucket_name)
        return {
            "status": "success",
            "bucket": s3_service.bucket_name,
            "cors_rules": len(result['CORSRules']),
            "origins": result['CORSRules'][0]['AllowedOrigins'],
        }

    except Exception as e:
        logger.error(f"Failed to configure S3 CORS: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/run-migration")
async def run_portal_video_migration(
    admin_key: str = Header(..., alias="X-Admin-Key"),
    db=Depends(get_db)
):
    """Run migration to create portal_video_messages table."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS portal_video_messages (
                id SERIAL PRIMARY KEY,
                portal_type VARCHAR(50) NOT NULL,
                recipient_id INTEGER NOT NULL,
                sender_id INTEGER,
                video_key VARCHAR(500),
                video_url TEXT,
                message TEXT,
                duration_seconds INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                viewed_at TIMESTAMP
            )
        """))
        logger.info("Created portal_video_messages table")

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_portal_video_messages_type_recipient
            ON portal_video_messages(portal_type, recipient_id)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_portal_video_messages_sender
            ON portal_video_messages(sender_id)
        """))

        db.commit()
        return {"status": "success", "message": "Portal video messages table created"}

    except SQLAlchemyError as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
