"""
Avatar API Routes - Manage AI avatar profiles, training, and video generation.

Endpoints:
- POST   /avatars              - Create avatar profile
- GET    /avatars              - List user's avatars
- GET    /avatars/{id}         - Get avatar details
- PUT    /avatars/{id}         - Update avatar profile
- DELETE /avatars/{id}         - Delete avatar
- POST   /avatars/{id}/upload  - Get upload URL for training video
- POST   /avatars/{id}/upload-complete - Mark upload as complete
- POST   /avatars/{id}/train   - Start training process
- GET    /avatars/{id}/status  - Get training status
- POST   /avatars/{id}/preview-voice - Generate voice preview
- POST   /avatars/generate     - Create avatar video generation job
- GET    /avatars/jobs         - List generation jobs
- GET    /avatars/jobs/{id}    - Get job details
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.orm import Session

from models.avatar_models import (
    AvatarProfileCreate,
    AvatarProfileUpdate,
    AvatarProfile,
    AvatarProfileSummary,
    AvatarListResponse,
    TrainingVideoUpload,
    TrainingStatus,
    TrainingStartRequest,
    AvatarJobCreate,
    AvatarJob,
    AvatarJobListResponse,
    VoicePreviewRequest,
    VoicePreviewResponse,
    QuickGenerateRequest,
    QuickGenerateResponse,
    AvatarStatus,
    AvatarJobStatus as AvatarJobStatusEnum,
)
from services.avatar_service import avatar_service
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/video-os/avatars", tags=["avatars"])

# Dependencies - will be injected by main.py
_db_dependency = None
_user_dependency = None


def set_dependencies(db_dep, user_dep):
    """Set dependencies for the router."""
    global _db_dependency, _user_dependency
    _db_dependency = db_dep
    _user_dependency = user_dep


def get_db():
    """Get database session - wrapper that works at request time."""
    if _db_dependency is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    return next(_db_dependency())


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _user_dependency is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _user_dependency(token=token, request=request, db=db)


# =============================================================================
# Avatar Profile CRUD
# =============================================================================

@router.post("", response_model=dict)
async def create_avatar(
    data: AvatarProfileCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new avatar profile."""
    try:
        profile = avatar_service.create_profile(
            db=db,
            data=data,
            user_id=current_user["id"],
            organization_id=current_user.get("organization_id")
        )
        return {"success": True, "avatar": profile}
    except Exception as e:
        logger.error(f"Failed to create avatar: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("", response_model=AvatarListResponse)
async def list_avatars(
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List user's avatar profiles."""
    try:
        avatars, total = avatar_service.list_profiles(
            db=db,
            user_id=current_user["id"],
            organization_id=current_user.get("organization_id"),
            status=status,
            page=page,
            page_size=page_size
        )
        return AvatarListResponse(
            avatars=[AvatarProfileSummary(**a) for a in avatars],
            total=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total
        )
    except Exception as e:
        logger.error(f"Failed to list avatars: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{avatar_id}", response_model=dict)
async def get_avatar(
    avatar_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get avatar profile details."""
    profile = avatar_service.get_profile_by_user(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"]
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return {"success": True, "avatar": profile}


@router.put("/{avatar_id}", response_model=dict)
async def update_avatar(
    avatar_id: int,
    data: AvatarProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update avatar profile."""
    profile = avatar_service.update_profile(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"],
        data=data
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return {"success": True, "avatar": profile}


@router.delete("/{avatar_id}", response_model=dict)
async def delete_avatar(
    avatar_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete avatar profile."""
    success = avatar_service.delete_profile(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"]
    )
    if not success:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return {"success": True, "message": "Avatar deleted"}


# =============================================================================
# Training Video Upload
# =============================================================================

@router.post("/{avatar_id}/upload", response_model=dict)
async def get_upload_url(
    avatar_id: int,
    file_name: str = Query(..., description="Original filename"),
    content_type: str = Query("video/mp4", description="MIME type"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get pre-signed URL for training video upload."""
    result = avatar_service.generate_upload_url(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"],
        file_name=file_name,
        content_type=content_type
    )
    if not result:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return {"success": True, **result}


@router.post("/{avatar_id}/upload-complete", response_model=dict)
async def complete_upload(
    avatar_id: int,
    s3_key: str = Query(..., description="S3 key of uploaded file"),
    duration_seconds: float = Query(..., description="Video duration"),
    size_bytes: int = Query(..., description="File size in bytes"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Mark training video upload as complete and start processing."""
    profile = avatar_service.complete_upload(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"],
        s3_key=s3_key,
        duration_seconds=duration_seconds,
        size_bytes=size_bytes
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Avatar not found")

    # Log analytics event
    avatar_service.log_analytics_event(
        db=db,
        avatar_id=avatar_id,
        event_type="training_video_uploaded",
        event_data={"duration": duration_seconds, "size": size_bytes}
    )

    return {"success": True, "avatar": profile, "message": "Upload complete. Processing will begin shortly."}


@router.post("/{avatar_id}/upload-direct", response_model=dict)
async def upload_direct(
    avatar_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Direct upload for development/testing (bypasses S3)."""
    import os
    import aiofiles

    # Validate file size and type
    MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB for video
    ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.webm', '.avi', '.mkv'}
    file_ext = ('.' + file.filename.split('.')[-1].lower()) if file.filename and '.' in file.filename else '.mp4'
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid video type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    profile = avatar_service.get_profile_by_user(db, avatar_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Avatar not found")

    # Create upload directory
    upload_dir = f"/tmp/avatars/{avatar_id}/training"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = f"{upload_dir}/video{file_ext}"

    # Save file with size check
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 500MB.")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)

    # Update profile
    avatar_service.update_training_status(
        db=db,
        avatar_id=avatar_id,
        status=AvatarStatus.PROCESSING.value,
        progress=0
    )

    return {
        "success": True,
        "message": "File uploaded successfully",
        "file_path": file_path,
        "size_bytes": len(content)
    }


# =============================================================================
# Training
# =============================================================================

@router.post("/{avatar_id}/train", response_model=dict)
async def start_training(
    avatar_id: int,
    request: TrainingStartRequest = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Start or restart avatar training."""
    profile = avatar_service.get_profile_by_user(db, avatar_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Avatar not found")

    if not profile.get("training_video_url"):
        raise HTTPException(status_code=400, detail="No training video uploaded")

    force_retrain = request.force_retrain if request else False

    if profile["status"] == AvatarStatus.READY.value and not force_retrain:
        raise HTTPException(
            status_code=400,
            detail="Avatar is already trained. Use force_retrain=true to retrain."
        )

    if profile["status"] == AvatarStatus.TRAINING.value:
        raise HTTPException(status_code=400, detail="Training is already in progress")

    # Update status to training
    avatar_service.update_training_status(
        db=db,
        avatar_id=avatar_id,
        status=AvatarStatus.TRAINING.value,
        progress=0
    )

    # Queue training job (would be handled by background worker)
    avatar_service.log_analytics_event(
        db=db,
        avatar_id=avatar_id,
        event_type="training_started",
        event_data={"force_retrain": force_retrain}
    )

    return {
        "success": True,
        "message": "Training started",
        "status": AvatarStatus.TRAINING.value
    }


@router.get("/{avatar_id}/status", response_model=dict)
async def get_training_status(
    avatar_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current training status."""
    status = avatar_service.get_training_status(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"]
    )
    if not status:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return {"success": True, "training": status}


# =============================================================================
# Voice Preview
# =============================================================================

@router.post("/{avatar_id}/preview-voice", response_model=dict)
async def preview_voice(
    avatar_id: int,
    request: VoicePreviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Generate a voice preview for the avatar."""
    profile = avatar_service.get_profile_by_user(db, avatar_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Avatar not found")

    if profile["status"] != AvatarStatus.READY.value:
        raise HTTPException(
            status_code=400,
            detail=f"Avatar is not ready. Current status: {profile['status']}"
        )

    result = await avatar_service.generate_voice_preview(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"],
        sample_text=request.sample_text,
        speaking_rate=request.speaking_rate
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to generate voice preview")

    return {"success": True, "preview": result}


# =============================================================================
# Video Generation
# =============================================================================

@router.post("/generate", response_model=dict)
async def generate_avatar_video(
    request: AvatarJobCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create an avatar video generation job."""
    try:
        job = avatar_service.create_generation_job(
            db=db,
            data=request,
            user_id=current_user["id"]
        )
        if not job:
            raise HTTPException(status_code=404, detail="Avatar not found")

        # Estimate duration
        word_count = len(request.script_text.split())
        estimated_duration = (word_count / 150) * 60 / request.speaking_rate
        estimated_completion = estimated_duration * 0.5 + 30  # Rough estimate

        return {
            "success": True,
            "job": job,
            "estimated_duration_seconds": estimated_duration,
            "estimated_completion_seconds": estimated_completion
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Failed to create generation job: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/quick-generate", response_model=dict)
async def quick_generate(
    request: QuickGenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Quick avatar video generation with defaults."""
    job_request = AvatarJobCreate(
        avatar_id=request.avatar_id,
        script_text=request.script_text,
        emotion=request.emotion,
        speaking_rate=request.speaking_rate
    )

    try:
        job = avatar_service.create_generation_job(
            db=db,
            data=job_request,
            user_id=current_user["id"]
        )
        if not job:
            raise HTTPException(status_code=404, detail="Avatar not found")

        word_count = len(request.script_text.split())
        estimated_duration = (word_count / 150) * 60 / request.speaking_rate

        return QuickGenerateResponse(
            job_id=job["job_id"],
            status=AvatarJobStatusEnum(job["status"]),
            estimated_duration_seconds=estimated_duration,
            estimated_completion_seconds=estimated_duration * 0.5 + 30
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")


@router.get("/jobs", response_model=AvatarJobListResponse)
async def list_jobs(
    avatar_id: Optional[int] = Query(None, description="Filter by avatar"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List avatar generation jobs."""
    jobs, total = avatar_service.list_jobs(
        db=db,
        avatar_id=avatar_id,
        user_id=current_user["id"],
        status=status,
        page=page,
        page_size=page_size
    )
    return AvatarJobListResponse(
        jobs=[AvatarJob(**j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total
    )


@router.get("/jobs/{job_id}", response_model=dict)
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get avatar generation job details."""
    job = avatar_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    profile = avatar_service.get_profile_by_user(db, job["avatar_id"], current_user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"success": True, "job": job}


# =============================================================================
# Test Endpoints (Development Only - disabled in production)
# =============================================================================

_IS_PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT", "").lower() == "production" or os.getenv("ENVIRONMENT", "").lower() == "production"

def _check_dev_only():
    """Block test endpoints in production."""
    if _IS_PRODUCTION:
        raise HTTPException(status_code=404, detail="Not found")

@router.post("/test/create", response_model=dict, dependencies=[Depends(_check_dev_only)])
async def test_create_avatar(
    name: str = Query(..., description="Avatar name"),
    description: str = Query("", description="Avatar description"),
    db: Session = Depends(get_db)
):
    """Create a test avatar without authentication (for development/testing)."""
    try:
        from models.avatar_models import AvatarProfileCreate

        data = AvatarProfileCreate(name=name, description=description)
        profile = avatar_service.create_profile(
            db=db,
            data=data,
            user_id=1,  # Default test user
            organization_id=1
        )
        return {"success": True, "avatar": profile, "message": "Test avatar created"}
    except Exception as e:
        logger.error(f"Failed to create test avatar: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/test/list", response_model=dict, dependencies=[Depends(_check_dev_only)])
async def test_list_avatars(
    user_id: int = Query(1, description="User ID to list avatars for"),
    db: Session = Depends(get_db)
):
    """List avatars without authentication (for development/testing)."""
    try:
        avatars, total = avatar_service.list_profiles(
            db=db,
            user_id=user_id,
            organization_id=None,
            status=None,
            page=1,
            page_size=50
        )
        return {"success": True, "avatars": avatars, "total": total}
    except Exception as e:
        logger.error(f"Failed to list test avatars: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/test/{avatar_id}", response_model=dict, dependencies=[Depends(_check_dev_only)])
async def test_get_avatar(
    avatar_id: int,
    db: Session = Depends(get_db)
):
    """Get avatar details without authentication (for development/testing)."""
    try:
        profile = avatar_service.get_profile(db=db, avatar_id=avatar_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Avatar not found")
        return {"success": True, "avatar": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get test avatar: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
