"""
Phase 2: Async Video Messages (Loom-style Recording)

Database models for async video clip management including:
- Video Clips (Loom-style recordings)
- Clip Templates (mortgage-specific)
- Clip Shares (shareable links)
- Clip Views (view tracking)
- Clip Comments (timestamped)
- Clip Transcripts (AI transcription)
- Clip Notifications
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text, Float, Index
from datetime import datetime, timezone
import enum
import secrets


# ============================================================================
# ENUMS
# ============================================================================

class ClipType(str, enum.Enum):
    SCREEN_CAMERA = "screen_camera"  # Screen + webcam picture-in-picture
    SCREEN_ONLY = "screen_only"       # Screen recording only
    CAMERA_ONLY = "camera_only"       # Webcam only


class ClipStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    TRANSCRIBING = "transcribing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class ClipAccessLevel(str, enum.Enum):
    PRIVATE = "private"      # Only creator can view
    ORG = "org"              # Organization members can view
    LINK = "link"            # Anyone with link can view
    PUBLIC = "public"        # Publicly searchable


class ClipTemplateCategory(str, enum.Enum):
    EXPLANATION = "explanation"       # Explaining concepts
    CHECKLIST = "checklist"           # Document checklists
    NEXT_STEPS = "next_steps"         # What happens next
    CELEBRATION = "celebration"       # Milestone celebrations
    INTRODUCTION = "introduction"     # LO introduction
    RATE_UPDATE = "rate_update"       # Rate lock/market update
    DOCUMENT_REQUEST = "document_request"  # Requesting documents
    CUSTOM = "custom"


class NotificationType(str, enum.Enum):
    VIEWED = "viewed"
    COMMENTED = "commented"
    SHARED = "shared"
    COMPLETED = "completed"  # Watched to end


# ============================================================================
# DEFAULT CLIP TEMPLATES
# ============================================================================

DEFAULT_CLIP_TEMPLATES = [
    {
        "template_key": "rate_lock_explanation",
        "template_name": "Rate Lock Explanation",
        "category": "explanation",
        "description": "Explain current rates and rate lock options to borrowers",
        "suggested_title": "Your Rate Lock Options - {borrower_name}",
        "script_outline": [
            "Greet the borrower by name",
            "Explain current market rates briefly",
            "Present rate lock options (15, 30, 45, 60 days)",
            "Explain float-down option if applicable",
            "Recommend a specific option based on their timeline",
            "Provide clear next steps"
        ],
        "default_duration_seconds": 180,
        "color": "#3b82f6",
        "icon": "lock"
    },
    {
        "template_key": "document_checklist",
        "template_name": "Document Checklist Walkthrough",
        "category": "checklist",
        "description": "Walk borrowers through required documents visually",
        "suggested_title": "Your Document Checklist - {borrower_name}",
        "script_outline": [
            "Greet and explain the purpose of this video",
            "Share your screen showing the checklist",
            "Go through each document category",
            "Explain why each document is needed",
            "Show examples of acceptable formats",
            "Explain how to upload securely"
        ],
        "default_duration_seconds": 300,
        "color": "#10b981",
        "icon": "document"
    },
    {
        "template_key": "pre_approval_next_steps",
        "template_name": "Pre-Approval Next Steps",
        "category": "next_steps",
        "description": "Guide newly pre-approved borrowers on what happens next",
        "suggested_title": "Congratulations on Your Pre-Approval! - {borrower_name}",
        "script_outline": [
            "Congratulate the borrower",
            "Explain what pre-approval means",
            "Outline the home shopping timeline",
            "Explain how to use the pre-approval letter",
            "Set expectations for the full approval process",
            "Provide your direct contact info"
        ],
        "default_duration_seconds": 240,
        "color": "#8b5cf6",
        "icon": "star"
    },
    {
        "template_key": "closing_celebration",
        "template_name": "Closing Day Celebration",
        "category": "celebration",
        "description": "Celebrate the borrower's successful closing",
        "suggested_title": "Congratulations on Your New Home! - {borrower_name}",
        "script_outline": [
            "Express genuine congratulations",
            "Recap the journey together",
            "Thank them for their trust",
            "Explain homeownership tips",
            "Ask for referrals naturally",
            "Provide ongoing support info"
        ],
        "default_duration_seconds": 120,
        "color": "#f59e0b",
        "icon": "home"
    },
    {
        "template_key": "lo_introduction",
        "template_name": "LO Introduction",
        "category": "introduction",
        "description": "Introduce yourself to new leads/borrowers",
        "suggested_title": "Hello {borrower_name} - Let Me Introduce Myself",
        "script_outline": [
            "Greet warmly and introduce yourself",
            "Share your experience and expertise",
            "Explain your approach to mortgages",
            "Set expectations for communication",
            "Provide availability and contact info",
            "Express excitement to work together"
        ],
        "default_duration_seconds": 90,
        "color": "#06b6d4",
        "icon": "user"
    },
    {
        "template_key": "rate_market_update",
        "template_name": "Rate & Market Update",
        "category": "rate_update",
        "description": "Provide market rate updates to active borrowers",
        "suggested_title": "Market Update - {date}",
        "script_outline": [
            "Greet and set context",
            "Share current rate environment",
            "Explain recent market movements",
            "Impact on their specific loan",
            "Recommendation based on situation",
            "Call to action"
        ],
        "default_duration_seconds": 150,
        "color": "#ef4444",
        "icon": "chart"
    },
    {
        "template_key": "document_request",
        "template_name": "Document Request",
        "category": "document_request",
        "description": "Request specific documents from borrowers",
        "suggested_title": "Quick Document Request - {borrower_name}",
        "script_outline": [
            "Greet and keep it brief",
            "Explain what document is needed",
            "Show exactly what to provide",
            "Explain why it's needed",
            "Provide upload instructions",
            "Set timeline expectations"
        ],
        "default_duration_seconds": 90,
        "color": "#f97316",
        "icon": "upload"
    },
    {
        "template_key": "appraisal_explanation",
        "template_name": "Appraisal Explanation",
        "category": "explanation",
        "description": "Explain the appraisal process and what to expect",
        "suggested_title": "Understanding Your Appraisal - {borrower_name}",
        "script_outline": [
            "Explain what an appraisal is",
            "Why it's required",
            "What the appraiser looks for",
            "Timeline expectations",
            "Possible outcomes and next steps",
            "How to prepare the property"
        ],
        "default_duration_seconds": 180,
        "color": "#84cc16",
        "icon": "search"
    }
]


# ============================================================================
# MODEL FACTORY
# ============================================================================

def create_video_clip_models(Base):
    """
    Factory function to create video clip models with the provided SQLAlchemy Base.
    """

    class VideoClip(Base):
        """
        Async video clips (Loom-style recordings)
        Core entity for storing user-created video messages
        """
        __tablename__ = "video_clips"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)

        # Ownership
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
        organization_id = Column(Integer, index=True)

        # Basic info
        title = Column(String(500), nullable=False)
        description = Column(Text)

        # Recording details
        clip_type = Column(String(50), nullable=False, default="screen_camera")
        duration_seconds = Column(Integer)
        file_size_bytes = Column(Integer)

        # Storage - S3 paths
        storage_path = Column(Text, nullable=False)
        storage_provider = Column(String(50), default="s3")
        thumbnail_path = Column(Text)
        video_url = Column(Text)

        # Video specs
        video_width = Column(Integer)
        video_height = Column(Integer)
        video_format = Column(String(20), default="webm")
        video_codec = Column(String(50))

        # Processing status
        status = Column(String(50), default="uploading", index=True)
        processing_progress = Column(Integer, default=0)  # 0-100
        processing_error = Column(Text)
        processing_started_at = Column(DateTime)
        processing_completed_at = Column(DateTime)

        # Transcription
        has_transcript = Column(Boolean, default=False)
        transcript_text = Column(Text)
        transcript_words = Column(JSON)  # Word-level timestamps
        transcript_language = Column(String(10), default="en")

        # Template
        template_id = Column(Integer, ForeignKey("clip_templates.id"))

        # CRM linking
        crm_entity_type = Column(String(50), index=True)  # loan, lead, contact
        crm_entity_id = Column(Integer, index=True)

        # Privacy & sharing
        access_level = Column(String(50), default="private")
        share_token = Column(String(100), unique=True, index=True)
        password_protected = Column(Boolean, default=False)
        password_hash = Column(String(255))

        # Analytics
        view_count = Column(Integer, default=0)
        unique_view_count = Column(Integer, default=0)
        total_watch_time_seconds = Column(Integer, default=0)
        average_completion_rate = Column(Float, default=0.0)

        # Metadata
        clip_metadata = Column(JSON, default=dict)  # Renamed from 'metadata' which is reserved
        tags = Column(JSON, default=list)

        # Branding
        show_branding = Column(Boolean, default=True)
        custom_branding = Column(JSON)  # Logo, colors, etc.

        # Expiration
        expires_at = Column(DateTime)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
        deleted_at = Column(DateTime)

        def generate_share_token(self):
            """Generate unique share token"""
            self.share_token = secrets.token_urlsafe(24)
            return self.share_token

    class ClipTemplate(Base):
        """
        Reusable templates for mortgage-specific clips
        """
        __tablename__ = "clip_templates"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, index=True)
        user_id = Column(Integer, ForeignKey("users.id"))  # Custom templates

        template_key = Column(String(100), unique=True, index=True)
        template_name = Column(String(255), nullable=False)
        category = Column(String(100))
        description = Column(Text)

        # Template content
        suggested_title = Column(String(500))
        suggested_description = Column(Text)
        script_outline = Column(JSON)  # List of talking points

        # Visual settings
        overlay_settings = Column(JSON)  # Logo position, name display, colors
        thumbnail_template = Column(String(255))
        background_options = Column(JSON)  # Background blur, replace, etc.

        # Default settings
        default_duration_seconds = Column(Integer, default=120)
        default_clip_type = Column(String(50), default="screen_camera")

        # Styling
        color = Column(String(20), default="#3b82f6")
        icon = Column(String(50), default="video")

        # Status
        is_system_template = Column(Boolean, default=False)
        is_active = Column(Boolean, default=True)
        usage_count = Column(Integer, default=0)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    class ClipShare(Base):
        """
        Shareable links for clips with custom settings
        """
        __tablename__ = "clip_shares"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        clip_id = Column(Integer, ForeignKey("video_clips.id"), nullable=False, index=True)
        created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

        # Share link
        share_token = Column(String(100), unique=True, index=True, nullable=False)
        share_url = Column(Text)

        # Recipient info
        recipient_email = Column(String(255))
        recipient_name = Column(String(255))

        # Permissions
        allow_download = Column(Boolean, default=False)
        allow_comments = Column(Boolean, default=True)
        require_email = Column(Boolean, default=False)

        # Restrictions
        max_views = Column(Integer)
        expires_at = Column(DateTime)

        # Notification settings
        notify_on_view = Column(Boolean, default=True)
        notify_on_complete = Column(Boolean, default=True)

        # Analytics
        view_count = Column(Integer, default=0)
        last_viewed_at = Column(DateTime)

        # Status
        is_active = Column(Boolean, default=True)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

        def generate_share_token(self):
            """Generate unique share token"""
            self.share_token = secrets.token_urlsafe(24)
            return self.share_token

    class ClipView(Base):
        """
        Track individual views of clips
        """
        __tablename__ = "clip_views"
        __table_args__ = (
            Index('idx_clip_view_clip', 'clip_id'),
            Index('idx_clip_view_session', 'session_id'),
            Index('idx_clip_view_started', 'started_at'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        clip_id = Column(Integer, ForeignKey("video_clips.id"), nullable=False)
        share_id = Column(Integer, ForeignKey("clip_shares.id"))

        # Viewer info
        viewer_email = Column(String(255))
        viewer_name = Column(String(255))
        viewer_user_id = Column(Integer, ForeignKey("users.id"))

        # Session info
        session_id = Column(String(100), index=True)
        ip_address = Column(String(50))
        user_agent = Column(Text)
        referrer = Column(Text)

        # Device info
        device_type = Column(String(50))  # desktop, mobile, tablet
        browser = Column(String(100))
        os = Column(String(100))

        # Viewing behavior
        watch_duration_seconds = Column(Integer, default=0)
        completion_rate = Column(Float, default=0.0)  # 0.0 to 1.0
        watched_to_end = Column(Boolean, default=False)

        # Playback tracking
        play_events = Column(JSON)  # [{time, event_type}]
        pause_points = Column(JSON)  # [time1, time2, ...]
        seek_events = Column(JSON)

        # Timestamps
        started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        ended_at = Column(DateTime)

    class ClipComment(Base):
        """
        Comments on clips (threaded, timestamped)
        """
        __tablename__ = "clip_comments"
        __table_args__ = (
            Index('idx_clip_comment_clip', 'clip_id'),
            Index('idx_clip_comment_timestamp', 'timestamp_seconds'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        clip_id = Column(Integer, ForeignKey("video_clips.id"), nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"))
        parent_comment_id = Column(Integer, ForeignKey("clip_comments.id"))

        # Comment content
        comment_text = Column(Text, nullable=False)
        timestamp_seconds = Column(Integer)  # Comment at specific time in clip

        # For non-logged-in viewers
        commenter_name = Column(String(255))
        commenter_email = Column(String(255))

        # Reactions
        emoji_reaction = Column(String(50))  # thumbs_up, heart, question, etc

        # Status
        is_resolved = Column(Boolean, default=False)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
        deleted_at = Column(DateTime)

    class ClipNotification(Base):
        """
        Notifications for clip events
        """
        __tablename__ = "clip_notifications"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        clip_id = Column(Integer, ForeignKey("video_clips.id"), nullable=False, index=True)
        recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

        notification_type = Column(String(50), nullable=False)  # viewed, commented, shared

        # Event details
        event_data = Column(JSON)  # Viewer info, comment text, etc.

        # Delivery
        sent_via_email = Column(Boolean, default=False)
        sent_via_sms = Column(Boolean, default=False)
        sent_via_push = Column(Boolean, default=False)

        email_sent_at = Column(DateTime)

        # Read status
        is_read = Column(Boolean, default=False)
        read_at = Column(DateTime)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Return all models as a dictionary
    return {
        'VideoClip': VideoClip,
        'ClipTemplate': ClipTemplate,
        'ClipShare': ClipShare,
        'ClipView': ClipView,
        'ClipComment': ClipComment,
        'ClipNotification': ClipNotification
    }
