"""
Vidyard API Routes - AI Avatar video generation endpoints.

Provides REST API for:
- Avatar management (list, create, get, delete)
- Video generation from scripts
- Video status tracking
- Webhook handling
"""

import hmac
import logging
import os

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

from services.vidyard_service import (
    get_vidyard_service,
    VidyardService,
    VidyardLanguage,
)
from routes.auth_deps import require_auth

router = APIRouter(prefix="/api/v1/vidyard", tags=["Vidyard"], dependencies=[Depends(require_auth)])


# =============================================================================
# Request/Response Models
# =============================================================================

class VidyardLanguageEnum(str, Enum):
    """Supported languages for video generation."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    JAPANESE = "ja"
    CHINESE = "zh"
    KOREAN = "ko"


class CreateAvatarRequest(BaseModel):
    """Request to create a custom AI avatar."""
    name: str = Field(..., min_length=1, max_length=100)
    training_video_url: str = Field(..., description="URL to 90-second training video")
    description: Optional[str] = Field(None, max_length=500)


class GenerateVideoRequest(BaseModel):
    """Request to generate AI avatar video."""
    avatar_id: str = Field(..., description="Avatar ID to use")
    script: str = Field(..., min_length=1, max_length=1000, description="Script text (max 1000 chars)")
    language: VidyardLanguageEnum = Field(VidyardLanguageEnum.ENGLISH)
    title: Optional[str] = Field(None, max_length=200)
    background_url: Optional[str] = Field(None, description="Custom background image/video URL")


class UploadVideoRequest(BaseModel):
    """Request to upload a video to Vidyard."""
    video_url: str = Field(..., description="URL of video file")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)


class ValidateScriptRequest(BaseModel):
    """Request to validate script before generation."""
    script: str


# =============================================================================
# Dependency
# =============================================================================

def get_service() -> VidyardService:
    """Get Vidyard service instance."""
    return get_vidyard_service()


# =============================================================================
# Health & Status
# =============================================================================

@router.get("/health")
async def health_check(service: VidyardService = Depends(get_service)):
    """Check Vidyard API connectivity."""
    return await service.health_check()


# =============================================================================
# Avatar Endpoints
# =============================================================================

@router.get("/avatars")
async def list_avatars(service: VidyardService = Depends(get_service)):
    """
    List available AI avatars.

    Returns custom avatars (if AI Avatar API configured) or stock avatars.
    """
    return await service.list_avatars()


@router.post("/avatars")
async def create_avatar(
    request: CreateAvatarRequest,
    service: VidyardService = Depends(get_service)
):
    """
    Create a custom AI avatar from training video.

    Requires:
    - 90-second training video of you speaking clearly
    - Video Agent add-on or Enterprise plan

    Training takes 3-4 hours to complete.
    """
    result = await service.create_avatar(
        name=request.name,
        training_video_url=request.training_video_url,
        description=request.description
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.get("/avatars/{avatar_id}")
async def get_avatar(
    avatar_id: str,
    service: VidyardService = Depends(get_service)
):
    """Get avatar details by ID."""
    avatar = await service.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return avatar


@router.delete("/avatars/{avatar_id}")
async def delete_avatar(
    avatar_id: str,
    service: VidyardService = Depends(get_service)
):
    """Delete a custom avatar."""
    success = await service.delete_avatar(avatar_id)
    if not success:
        raise HTTPException(status_code=404, detail="Avatar not found or delete failed")
    return {"message": "Avatar deleted", "avatar_id": avatar_id}


# =============================================================================
# Video Generation Endpoints
# =============================================================================

@router.post("/videos/generate")
async def generate_video(
    request: GenerateVideoRequest,
    service: VidyardService = Depends(get_service)
):
    """
    Generate AI avatar video from script.

    - Max script length: 1000 characters (~1 minute video)
    - Generation time: ~10 minutes per minute of video
    - Avoid line breaks in script (can cause filler words)
    """
    # Map enum to service enum
    language = VidyardLanguage(request.language.value)

    result = await service.generate_video(
        avatar_id=request.avatar_id,
        script=request.script,
        language=language,
        title=request.title,
        background_url=request.background_url
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.get("/videos/{job_id}/status")
async def get_video_status(
    job_id: str,
    service: VidyardService = Depends(get_service)
):
    """
    Get video generation job status.

    Returns video URL when generation is complete.
    """
    result = await service.get_video_status(job_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/videos")
async def list_videos(
    page: int = 1,
    per_page: int = 25,
    avatar_id: Optional[str] = None,
    service: VidyardService = Depends(get_service)
):
    """List generated AI videos."""
    return await service.list_videos(page=page, per_page=per_page, avatar_id=avatar_id)


# =============================================================================
# Standard Video Upload (Dashboard API)
# =============================================================================

@router.post("/videos/upload")
async def upload_video(
    request: UploadVideoRequest,
    service: VidyardService = Depends(get_service)
):
    """
    Upload a video to Vidyard.

    This uses the standard Dashboard API for video hosting,
    not AI avatar generation.
    """
    result = await service.upload_video(
        video_url=request.video_url,
        name=request.name,
        description=request.description
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.get("/videos/{video_id}")
async def get_video(
    video_id: str,
    service: VidyardService = Depends(get_service)
):
    """Get video details by ID."""
    video = await service.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


# =============================================================================
# Utility Endpoints
# =============================================================================

@router.post("/scripts/validate")
async def validate_script(
    request: ValidateScriptRequest,
    service: VidyardService = Depends(get_service)
):
    """
    Validate script before generating video.

    Returns validation result with any issues or warnings.
    """
    return service.validate_script(request.script)


@router.get("/languages")
async def list_languages():
    """Get list of supported languages for AI video generation."""
    return {
        "languages": [
            {"code": lang.value, "name": lang.name.replace("_", " ").title()}
            for lang in VidyardLanguage
        ]
    }


# =============================================================================
# Webhook Handler
# =============================================================================

@router.post("/webhooks")
async def handle_webhook(
    request: Request,
    service: VidyardService = Depends(get_service)
):
    """
    Handle Vidyard webhook callbacks.

    Receives notifications for:
    - Avatar training complete/failed
    - Video generation complete/failed

    Requires VIDYARD_WEBHOOK_SECRET env var. Fails closed when not configured.
    """
    expected = os.environ.get("VIDYARD_WEBHOOK_SECRET", "")
    provided = (
        request.headers.get("X-Webhook-Secret", "")
        or request.headers.get("Authorization", "").removeprefix("Bearer ")
    )
    if not expected or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Unauthorized webhook")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Error parsing JSON in handle_webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    result = service.handle_webhook(payload)
    return result
