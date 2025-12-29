"""
Video OS Pydantic Models
Models for the internal video generation, hosting, and analytics system.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class VideoSourceType(str, Enum):
    THOUGHT = "thought"
    BLOG = "blog"
    PODCAST = "podcast"
    SCRIPT = "script"
    UPLOAD = "upload"


class VideoProjectStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class RenderJobState(str, Enum):
    CREATED = "created"
    SCRIPTED = "scripted"
    VOICED = "voiced"
    STORYBOARDED = "storyboarded"
    VISUALIZED = "visualized"
    RENDERING = "rendering"
    RENDERED = "rendered"
    PUBLISHED = "published"
    FAILED = "failed"


class VideoFormat(str, Enum):
    PORTRAIT_9X16 = "portrait_9x16"
    SQUARE_1X1 = "square_1x1"
    LANDSCAPE_16X9 = "landscape_16x9"


class VideoVisibility(str, Enum):
    PRIVATE = "private"
    INTERNAL = "internal"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class VisualSourceType(str, Enum):
    AI_IMAGE = "ai_image"
    STOCK = "stock"
    UPLOADED = "uploaded"
    SCREEN_RECORDING = "screen_recording"
    AVATAR = "avatar"


class MotionStyle(str, Enum):
    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    KEN_BURNS = "ken_burns"
    CUT = "cut"
    FADE = "fade"
    SLIDE = "slide"


class CaptionStyle(str, Enum):
    CLASSIC = "classic"
    KARAOKE = "karaoke"
    POP = "pop"
    HIGHLIGHT = "highlight"
    MINIMAL = "minimal"
    BOLD = "bold"


class CTAType(str, Enum):
    BUTTON = "button"
    FORM = "form"
    CALENDAR = "calendar"
    PHONE = "phone"
    TEXT_KEYWORD = "text_keyword"


class AnalyticsEventType(str, Enum):
    PLAY = "play"
    PAUSE = "pause"
    SEEK = "seek"
    RESUME = "resume"
    QUARTILE_25 = "quartile_25"
    QUARTILE_50 = "quartile_50"
    QUARTILE_75 = "quartile_75"
    COMPLETE = "complete"
    CTA_SHOWN = "cta_shown"
    CTA_CLICKED = "cta_clicked"
    FORM_SUBMITTED = "form_submitted"
    SHARE = "share"
    DOWNLOAD = "download"


# =============================================================================
# BRAND TEMPLATE MODELS
# =============================================================================

class BrandTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    primary_color: str = "#1a365d"
    secondary_color: str = "#2b6cb0"
    accent_color: str = "#ed8936"
    background_color: str = "#000000"
    text_color: str = "#ffffff"
    heading_font: str = "Montserrat"
    body_font: str = "Open Sans"
    caption_font: str = "Roboto"
    logo_url: Optional[str] = None
    watermark_url: Optional[str] = None
    watermark_position: str = "bottom_right"
    watermark_opacity: float = 0.7
    intro_video_url: Optional[str] = None
    outro_video_url: Optional[str] = None
    background_music_url: Optional[str] = None
    music_volume: float = 0.15
    caption_style: CaptionStyle = CaptionStyle.POP
    caption_position: str = "center"
    caption_background: bool = True
    caption_max_words: int = 3
    nmls_number: Optional[str] = None
    disclaimer_text: Optional[str] = None
    show_disclaimer: bool = False


class BrandTemplateCreate(BrandTemplateBase):
    pass


class BrandTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    watermark_url: Optional[str] = None
    caption_style: Optional[CaptionStyle] = None
    nmls_number: Optional[str] = None
    disclaimer_text: Optional[str] = None
    show_disclaimer: Optional[bool] = None


class BrandTemplateResponse(BrandTemplateBase):
    id: int
    organization_id: Optional[int] = None
    is_default: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# VOICE PROFILE MODELS
# =============================================================================

class VoiceProfileBase(BaseModel):
    name: str
    description: Optional[str] = None
    voice_engine: str = "local_tts"
    voice_id: Optional[str] = None
    language: str = "en-US"
    speaking_rate: float = 1.0
    pitch: float = 1.0
    volume_gain_db: float = 0.0


class VoiceProfileCreate(VoiceProfileBase):
    pass


class VoiceProfileResponse(VoiceProfileBase):
    id: int
    organization_id: Optional[int] = None
    user_id: Optional[int] = None
    is_clone: bool = False
    total_characters_used: int = 0
    last_used_at: Optional[datetime] = None
    is_default: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# VIDEO PROJECT MODELS
# =============================================================================

class VideoProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    source_type: VideoSourceType = VideoSourceType.THOUGHT
    source_text: str
    source_url: Optional[str] = None
    brand_template_id: Optional[int] = None
    voice_profile_id: Optional[int] = None
    target_duration_seconds: int = 60
    target_formats: List[VideoFormat] = [VideoFormat.PORTRAIT_9X16]
    tags: List[str] = []
    category: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    campaign_id: Optional[int] = None


class VideoProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source_text: Optional[str] = None
    brand_template_id: Optional[int] = None
    voice_profile_id: Optional[int] = None
    target_duration_seconds: Optional[int] = None
    target_formats: Optional[List[VideoFormat]] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class VideoProjectResponse(BaseModel):
    id: int
    organization_id: Optional[int] = None
    created_by: int
    title: str
    description: Optional[str] = None
    source_type: str
    source_text: Optional[str] = None
    source_url: Optional[str] = None
    brand_template_id: Optional[int] = None
    voice_profile_id: Optional[int] = None
    target_duration_seconds: int
    target_formats: List[str] = []
    generated_script: Optional[str] = None
    generated_blog: Optional[str] = None
    generated_podcast_notes: Optional[str] = None
    hook_variants: List[str] = []
    status: str
    error_message: Optional[str] = None
    tags: List[str] = []
    category: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    campaign_id: Optional[int] = None
    published_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# STORYBOARD SCENE MODELS
# =============================================================================

class CaptionWord(BaseModel):
    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0


class StoryboardSceneCreate(BaseModel):
    scene_index: int
    duration_seconds: float
    voiceover_text: str
    on_screen_text: Optional[str] = None
    caption_style: CaptionStyle = CaptionStyle.POP
    visual_source: VisualSourceType = VisualSourceType.AI_IMAGE
    visual_prompt: Optional[str] = None
    visual_url: Optional[str] = None
    motion_style: MotionStyle = MotionStyle.KEN_BURNS
    transition_in: str = "fade"
    transition_out: str = "fade"
    hook_text: Optional[str] = None
    cta_overlay_id: Optional[int] = None
    show_lower_third: bool = False
    lower_third_text: Optional[str] = None
    scene_type: str = "content"


class StoryboardSceneUpdate(BaseModel):
    duration_seconds: Optional[float] = None
    voiceover_text: Optional[str] = None
    on_screen_text: Optional[str] = None
    visual_source: Optional[VisualSourceType] = None
    visual_prompt: Optional[str] = None
    visual_url: Optional[str] = None
    motion_style: Optional[MotionStyle] = None


class StoryboardSceneResponse(BaseModel):
    id: int
    project_id: int
    scene_index: int
    duration_seconds: float
    voiceover_text: str
    voiceover_start_time: Optional[float] = None
    voiceover_end_time: Optional[float] = None
    on_screen_text: Optional[str] = None
    caption_words: List[CaptionWord] = []
    caption_style: str
    visual_source: str
    visual_prompt: Optional[str] = None
    visual_url: Optional[str] = None
    visual_thumbnail_url: Optional[str] = None
    motion_style: str
    transition_in: str
    transition_out: str
    hook_text: Optional[str] = None
    cta_overlay_id: Optional[int] = None
    show_lower_third: bool
    lower_third_text: Optional[str] = None
    scene_type: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# RENDER JOB MODELS
# =============================================================================

class RenderJobCreate(BaseModel):
    project_id: int
    format: VideoFormat
    resolution: str = "1080x1920"
    fps: int = 30


class RenderJobResponse(BaseModel):
    id: int
    job_id: str
    project_id: int
    format: str
    resolution: str
    fps: int
    state: str
    progress: int
    current_step: Optional[str] = None
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    gpu_seconds: float = 0
    cpu_seconds: float = 0
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    output_duration_seconds: Optional[float] = None
    output_file_size_bytes: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RenderArtifactResponse(BaseModel):
    id: int
    render_job_id: int
    artifact_type: str
    file_url: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    resolution: Optional[str] = None
    word_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# VIDEO LIBRARY MODELS
# =============================================================================

class VideoLibraryCreate(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[int] = None
    render_job_id: Optional[int] = None
    video_url: str
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    format: Optional[VideoFormat] = None
    resolution: Optional[str] = None
    visibility: VideoVisibility = VideoVisibility.PRIVATE
    password: Optional[str] = None
    expires_at: Optional[datetime] = None
    allow_embed: bool = True
    allowed_domains: List[str] = []
    cta_enabled: bool = False
    cta_config: Dict[str, Any] = {}
    folder_path: str = "/"
    tags: List[str] = []


class VideoLibraryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[VideoVisibility] = None
    password: Optional[str] = None
    expires_at: Optional[datetime] = None
    allow_embed: Optional[bool] = None
    allowed_domains: Optional[List[str]] = None
    cta_enabled: Optional[bool] = None
    cta_config: Optional[Dict[str, Any]] = None
    folder_path: Optional[str] = None
    tags: Optional[List[str]] = None


class VideoLibraryResponse(BaseModel):
    id: int
    organization_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    project_id: Optional[int] = None
    render_job_id: Optional[int] = None
    video_url: str
    thumbnail_url: Optional[str] = None
    preview_gif_url: Optional[str] = None
    poster_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    format: Optional[str] = None
    resolution: Optional[str] = None
    share_token: Optional[str] = None
    visibility: str
    expires_at: Optional[datetime] = None
    allow_embed: bool
    allowed_domains: List[str] = []
    cta_enabled: bool
    cta_config: Dict[str, Any] = {}
    view_count: int = 0
    unique_viewer_count: int = 0
    total_watch_time_seconds: int = 0
    avg_watch_percent: float = 0
    folder_path: str
    tags: List[str] = []
    published_at: Optional[datetime] = None
    last_viewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# VIEWER SESSION & ANALYTICS MODELS
# =============================================================================

class ViewerSessionCreate(BaseModel):
    video_id: int
    session_id: str
    viewer_id: Optional[str] = None
    lead_id: Optional[int] = None
    contact_id: Optional[int] = None
    viewer_name: Optional[str] = None
    viewer_email: Optional[str] = None
    viewer_company: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    referrer: Optional[str] = None


class ViewerSessionResponse(BaseModel):
    id: int
    video_id: int
    session_id: str
    viewer_id: Optional[str] = None
    lead_id: Optional[int] = None
    contact_id: Optional[int] = None
    user_id: Optional[int] = None
    viewer_name: Optional[str] = None
    viewer_email: Optional[str] = None
    viewer_company: Optional[str] = None
    watch_time_seconds: int = 0
    max_percent_watched: float = 0
    completed: bool = False
    cta_shown: bool = False
    cta_clicked: bool = False
    cta_clicked_at: Optional[datetime] = None
    started_at: datetime
    last_activity_at: datetime
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnalyticsEventCreate(BaseModel):
    video_id: int
    session_id: Optional[int] = None
    event_type: AnalyticsEventType
    event_data: Dict[str, Any] = {}
    video_time_seconds: Optional[float] = None
    percent_watched: Optional[float] = None
    client_timestamp: Optional[datetime] = None


class AnalyticsEventResponse(BaseModel):
    id: int
    video_id: int
    session_id: Optional[int] = None
    event_type: str
    event_data: Dict[str, Any] = {}
    video_time_seconds: Optional[float] = None
    percent_watched: Optional[float] = None
    client_timestamp: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# CTA OVERLAY MODELS
# =============================================================================

class CTAOverlayCreate(BaseModel):
    name: str
    cta_type: CTAType
    show_at_percent: Optional[float] = None
    show_at_seconds: Optional[float] = None
    show_on_pause: bool = False
    show_on_end: bool = True
    headline: Optional[str] = None
    description: Optional[str] = None
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    button_color: Optional[str] = None
    form_fields: List[Dict[str, Any]] = []
    position: str = "center"
    animation: str = "fade_in"
    action_type: Optional[str] = None
    action_config: Dict[str, Any] = {}


class CTAOverlayResponse(BaseModel):
    id: int
    organization_id: Optional[int] = None
    name: str
    cta_type: str
    show_at_percent: Optional[float] = None
    show_at_seconds: Optional[float] = None
    show_on_pause: bool
    show_on_end: bool
    headline: Optional[str] = None
    description: Optional[str] = None
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    button_color: Optional[str] = None
    form_fields: List[Dict[str, Any]] = []
    position: str
    animation: str
    action_type: Optional[str] = None
    action_config: Dict[str, Any] = {}
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# ASSET LIBRARY MODELS
# =============================================================================

class AssetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    asset_type: str
    file_url: str
    thumbnail_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    folder_path: str = "/"
    tags: List[str] = []


class AssetResponse(BaseModel):
    id: int
    organization_id: Optional[int] = None
    uploaded_by: Optional[int] = None
    name: str
    description: Optional[str] = None
    asset_type: str
    file_url: str
    thumbnail_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    folder_path: str
    tags: List[str] = []
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# CONTENT VAULT MODELS
# =============================================================================

class ContentVaultCreate(BaseModel):
    content_type: str
    title: str
    content: str
    category: Optional[str] = None
    tags: List[str] = []


class ContentVaultResponse(BaseModel):
    id: int
    organization_id: Optional[int] = None
    created_by: Optional[int] = None
    content_type: str
    title: str
    content: str
    category: Optional[str] = None
    tags: List[str] = []
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    is_approved: bool
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# ANALYTICS AGGREGATION MODELS
# =============================================================================

class VideoAnalyticsSummary(BaseModel):
    video_id: int
    title: str
    total_views: int
    unique_viewers: int
    total_watch_time_seconds: int
    avg_watch_percent: float
    completion_rate: float
    cta_click_rate: float
    top_drop_off_points: List[Dict[str, Any]] = []
    views_by_day: List[Dict[str, Any]] = []
    viewer_locations: List[Dict[str, Any]] = []


class WatchHeatmap(BaseModel):
    video_id: int
    segments: List[Dict[str, Any]]
    duration_seconds: float


class ViewerEngagement(BaseModel):
    viewer_email: Optional[str] = None
    viewer_name: Optional[str] = None
    lead_id: Optional[int] = None
    total_videos_watched: int
    total_watch_time_seconds: int
    avg_watch_percent: float
    cta_clicks: int
    last_watched_at: datetime
    videos: List[Dict[str, Any]] = []


# =============================================================================
# GENERATION REQUEST MODELS
# =============================================================================

class GenerateScriptRequest(BaseModel):
    thought: str
    target_duration_seconds: int = 60
    tone: str = "professional"
    include_hook: bool = True
    include_cta: bool = True


class GenerateStoryboardRequest(BaseModel):
    project_id: int
    script: Optional[str] = None
    visual_style: str = "modern"
    include_b_roll: bool = True


class GenerateVisualsRequest(BaseModel):
    project_id: int
    scene_ids: Optional[List[int]] = None
    style: str = "professional"
    quality: str = "high"


class StartRenderRequest(BaseModel):
    project_id: int
    formats: List[VideoFormat] = [VideoFormat.PORTRAIT_9X16]
    priority: str = "normal"


class PublishVideoRequest(BaseModel):
    render_job_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    visibility: VideoVisibility = VideoVisibility.UNLISTED
    folder_path: str = "/"
    tags: List[str] = []
    cta_overlay_id: Optional[int] = None
