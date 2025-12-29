"""
Pydantic models for the AI Avatar system.
Handles avatar profile management, training, and video generation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class AvatarStatus(str, Enum):
    """Status of an avatar profile."""
    PENDING = "pending"           # Created, awaiting training video
    UPLOADING = "uploading"       # Training video being uploaded
    PROCESSING = "processing"     # Extracting audio/frames from video
    TRAINING = "training"         # Training voice model
    READY = "ready"               # Ready for video generation
    FAILED = "failed"             # Training failed


class AvatarJobStatus(str, Enum):
    """Status of an avatar generation job."""
    PENDING = "pending"           # Job created, waiting to start
    GENERATING_VOICE = "generating_voice"   # Synthesizing voice audio
    GENERATING_LIPSYNC = "generating_lipsync"  # Creating lip-synced video
    PROCESSING = "processing"     # Post-processing
    COMPLETED = "completed"       # Done
    FAILED = "failed"             # Failed


class AvatarEmotion(str, Enum):
    """Emotional expression for avatar."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SERIOUS = "serious"
    CONFIDENT = "confident"
    FRIENDLY = "friendly"
    CONCERNED = "concerned"


class CropStyle(str, Enum):
    """How to crop the avatar in the frame."""
    PORTRAIT = "portrait"         # Head and shoulders
    BUST = "bust"                 # Head to chest
    FULL = "full"                 # Full body if available
    CUSTOM = "custom"             # Custom crop region


class LipSyncQuality(str, Enum):
    """Quality level for lip sync generation."""
    FAST = "fast"                 # Quick but lower quality
    BALANCED = "balanced"         # Balance of speed and quality
    HIGH = "high"                 # Best quality, slower


# =============================================================================
# Avatar Profile Models
# =============================================================================

class AvatarProfileBase(BaseModel):
    """Base fields for avatar profile."""
    name: str = Field(..., description="Name for this avatar")
    description: Optional[str] = Field(None, description="Description of the avatar")
    default_background: str = Field("transparent", description="Default background color/type")
    default_resolution: str = Field("1080x1920", description="Default output resolution")
    crop_style: CropStyle = Field(CropStyle.PORTRAIT, description="How to crop the avatar")
    lip_sync_quality: LipSyncQuality = Field(LipSyncQuality.HIGH, description="Lip sync quality level")
    voice_similarity: float = Field(0.85, ge=0.0, le=1.0, description="Voice cloning similarity target")


class AvatarProfileCreate(AvatarProfileBase):
    """Request model for creating an avatar profile."""
    pass


class AvatarProfileUpdate(BaseModel):
    """Request model for updating an avatar profile."""
    name: Optional[str] = None
    description: Optional[str] = None
    default_background: Optional[str] = None
    default_resolution: Optional[str] = None
    crop_style: Optional[CropStyle] = None
    lip_sync_quality: Optional[LipSyncQuality] = None
    voice_similarity: Optional[float] = Field(None, ge=0.0, le=1.0)


class AvatarProfile(AvatarProfileBase):
    """Full avatar profile model."""
    id: int
    organization_id: Optional[int] = None
    user_id: Optional[int] = None

    # Training video
    training_video_url: Optional[str] = None
    training_video_duration_seconds: Optional[float] = None
    training_video_size_bytes: Optional[int] = None

    # Extracted assets
    reference_image_url: Optional[str] = None
    voice_sample_url: Optional[str] = None
    voice_model_id: Optional[str] = None

    # Status
    status: AvatarStatus = AvatarStatus.PENDING
    training_progress: int = 0
    training_started_at: Optional[datetime] = None
    training_completed_at: Optional[datetime] = None
    training_error: Optional[str] = None

    # Usage stats
    total_videos_generated: int = 0
    total_duration_generated_seconds: float = 0
    last_used_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AvatarProfileSummary(BaseModel):
    """Summary view of avatar profile for lists."""
    id: int
    name: str
    status: AvatarStatus
    reference_image_url: Optional[str] = None
    total_videos_generated: int = 0
    last_used_at: Optional[datetime] = None
    created_at: datetime


# =============================================================================
# Training Models
# =============================================================================

class TrainingVideoUpload(BaseModel):
    """Response after uploading training video."""
    avatar_id: int
    upload_url: str
    upload_fields: Dict[str, str] = {}
    max_size_bytes: int = 500_000_000  # 500MB max
    allowed_formats: List[str] = ["mp4", "mov", "webm"]


class TrainingStatus(BaseModel):
    """Current training status for an avatar."""
    avatar_id: int
    status: AvatarStatus
    progress: int = Field(0, ge=0, le=100)
    current_step: Optional[str] = None
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    error: Optional[str] = None


class TrainingStartRequest(BaseModel):
    """Request to start training an avatar."""
    force_retrain: bool = Field(False, description="Force retraining even if already trained")


# =============================================================================
# Avatar Job Models
# =============================================================================

class AvatarJobCreate(BaseModel):
    """Request to create an avatar generation job."""
    avatar_id: int = Field(..., description="ID of the avatar to use")
    script_text: str = Field(..., min_length=1, max_length=10000, description="Text for the avatar to speak")
    emotion: AvatarEmotion = Field(AvatarEmotion.NEUTRAL, description="Emotional expression")
    speaking_rate: float = Field(1.0, ge=0.5, le=2.0, description="Speaking speed multiplier")
    duration_hint_seconds: Optional[float] = Field(None, description="Target duration hint")

    # Optional project/scene linking
    project_id: Optional[int] = None
    scene_id: Optional[int] = None


class AvatarJob(BaseModel):
    """Full avatar generation job model."""
    id: int
    job_id: str
    avatar_id: int
    project_id: Optional[int] = None
    scene_id: Optional[int] = None

    # Input
    script_text: str
    emotion: AvatarEmotion = AvatarEmotion.NEUTRAL
    speaking_rate: float = 1.0
    duration_hint_seconds: Optional[float] = None

    # Output
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    duration_seconds: Optional[float] = None

    # Status
    status: AvatarJobStatus = AvatarJobStatus.PENDING
    progress: int = 0
    current_step: Optional[str] = None
    error_message: Optional[str] = None

    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Performance metrics
    voice_generation_ms: Optional[int] = None
    lip_sync_generation_ms: Optional[int] = None

    class Config:
        from_attributes = True


class AvatarJobStatus(BaseModel):
    """Status update for an avatar job."""
    job_id: str
    status: AvatarJobStatus
    progress: int = 0
    current_step: Optional[str] = None
    video_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


# =============================================================================
# Quick Generation Models
# =============================================================================

class QuickGenerateRequest(BaseModel):
    """Request for quick avatar video generation."""
    avatar_id: int
    script_text: str = Field(..., min_length=1, max_length=5000)
    emotion: AvatarEmotion = AvatarEmotion.NEUTRAL
    speaking_rate: float = Field(1.0, ge=0.5, le=2.0)
    resolution: Optional[str] = None  # Override avatar default
    background: Optional[str] = None  # Override avatar default


class QuickGenerateResponse(BaseModel):
    """Response for quick generation request."""
    job_id: str
    status: AvatarJobStatus
    estimated_duration_seconds: float
    estimated_completion_seconds: float


# =============================================================================
# Voice Preview Models
# =============================================================================

class VoicePreviewRequest(BaseModel):
    """Request to preview avatar's voice with sample text."""
    avatar_id: int
    sample_text: str = Field(
        "Hello, this is a preview of my AI avatar voice.",
        min_length=1,
        max_length=500
    )
    speaking_rate: float = Field(1.0, ge=0.5, le=2.0)


class VoicePreviewResponse(BaseModel):
    """Response with voice preview audio."""
    avatar_id: int
    audio_url: str
    duration_seconds: float
    sample_text: str


# =============================================================================
# Analytics Models
# =============================================================================

class AvatarAnalyticsEvent(BaseModel):
    """Analytics event for avatar usage."""
    avatar_id: int
    event_type: str  # "video_generated", "training_started", "training_completed", etc.
    event_data: Dict[str, Any] = {}
    created_at: datetime


class AvatarUsageStats(BaseModel):
    """Usage statistics for an avatar."""
    avatar_id: int
    total_videos: int
    total_duration_seconds: float
    average_duration_seconds: float
    videos_this_month: int
    most_used_emotion: Optional[str] = None
    last_used_at: Optional[datetime] = None


# =============================================================================
# List Response Models
# =============================================================================

class AvatarListResponse(BaseModel):
    """Paginated list of avatars."""
    avatars: List[AvatarProfileSummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class AvatarJobListResponse(BaseModel):
    """Paginated list of avatar jobs."""
    jobs: List[AvatarJob]
    total: int
    page: int
    page_size: int
    has_more: bool
