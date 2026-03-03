"""
UVIP - Ultimate Video Intelligence Platform Models
Phase 1: Core Meeting Infrastructure

Database models for AI-powered video meeting management including:
- Video Meeting Rooms
- Meeting Participants
- Meeting Recordings
- Recording Transcripts
- Meeting Analytics
- Integration with Smart Scheduler
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text, Float, Time, Date, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime, time
import enum


# ============================================================================
# ENUMS
# ============================================================================

class MeetingRoomStatus(str, enum.Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    ENDED = "ended"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class ParticipantRole(str, enum.Enum):
    HOST = "host"
    CO_HOST = "co_host"
    PARTICIPANT = "participant"
    PRESENTER = "presenter"
    OBSERVER = "observer"


class ParticipantStatus(str, enum.Enum):
    INVITED = "invited"
    WAITING = "waiting"
    JOINED = "joined"
    LEFT = "left"
    REMOVED = "removed"


class RecordingStatus(str, enum.Enum):
    PENDING = "pending"
    RECORDING = "recording"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class TranscriptStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MeetingProvider(str, enum.Enum):
    INTERNAL = "internal"           # Built-in WebRTC
    ZOOM = "zoom"                   # Zoom integration
    GOOGLE_MEET = "google_meet"     # Google Meet
    TEAMS = "teams"                 # Microsoft Teams
    WEBEX = "webex"                 # Cisco Webex
    CHIME = "chime"              # Amazon Chime SDK


class AIAnalysisType(str, enum.Enum):
    TRANSCRIPTION = "transcription"
    SUMMARY = "summary"
    ACTION_ITEMS = "action_items"
    SENTIMENT = "sentiment"
    KEY_TOPICS = "key_topics"
    SPEAKER_ANALYSIS = "speaker_analysis"
    FOLLOW_UP = "follow_up"


# ============================================================================
# MODEL FACTORY
# ============================================================================

def create_video_meeting_models(Base):
    """
    Factory function to create video meeting models with the provided SQLAlchemy Base.
    """

    class VideoMeetingRoom(Base):
        """
        Core video meeting room entity.
        Represents a scheduled or instant meeting room.
        """
        __tablename__ = "video_meeting_rooms"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)

        # Room identification
        room_code = Column(String(20), unique=True, index=True, nullable=False)  # e.g., "MTG-ABC123"
        room_name = Column(String(255), nullable=False)
        room_description = Column(Text)

        # Meeting provider
        provider = Column(String(50), default="internal")  # internal, zoom, google_meet, etc.
        external_meeting_id = Column(String(255))  # ID from external provider
        external_meeting_url = Column(String(1000))  # Join URL from external provider

        # Amazon Chime SDK
        chime_meeting_id = Column(String(255), index=True)
        chime_media_region = Column(String(50), default="us-east-1")

        # Host information
        host_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        organization_id = Column(Integer, nullable=True, index=True)

        # Scheduling
        scheduled_start = Column(DateTime)
        scheduled_end = Column(DateTime)
        actual_start = Column(DateTime)
        actual_end = Column(DateTime)
        duration_minutes = Column(Integer, default=30)

        # Room status
        status = Column(String(20), default="scheduled")

        # Room settings
        waiting_room_enabled = Column(Boolean, default=True)
        recording_enabled = Column(Boolean, default=True)
        transcription_enabled = Column(Boolean, default=True)
        ai_assistant_enabled = Column(Boolean, default=True)
        chat_enabled = Column(Boolean, default=True)
        screen_share_enabled = Column(Boolean, default=True)

        # Security
        password_protected = Column(Boolean, default=False)
        room_password = Column(String(100))  # Hashed
        max_participants = Column(Integer, default=50)
        require_authentication = Column(Boolean, default=False)

        # Links to CRM entities
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        contact_id = Column(Integer, nullable=True)
        appointment_id = Column(Integer, nullable=True)  # Link to Smart Scheduler

        # Meeting type
        meeting_type = Column(String(50), default="general")  # discovery_call, document_review, etc.

        # Recurring meeting support
        is_recurring = Column(Boolean, default=False)
        recurrence_pattern = Column(JSON)  # {"frequency": "weekly", "days": ["monday"], "end_date": "2024-12-31"}
        parent_meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=True)

        # Metadata
        settings = Column(JSON, default={})  # Additional configurable settings
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        created_by = Column(Integer, ForeignKey("users.id"))

        # AI-generated content
        ai_summary = Column(Text)
        ai_action_items = Column(JSON)  # List of action items
        ai_key_topics = Column(JSON)  # List of discussed topics
        ai_follow_up_recommended = Column(Boolean, default=False)

        # Relationships (will be defined at runtime)
        # participants = relationship("MeetingParticipant", back_populates="meeting")
        # recordings = relationship("MeetingRecording", back_populates="meeting")

    class MeetingParticipant(Base):
        """
        Tracks meeting participants and their activity.
        """
        __tablename__ = "meeting_participants"
        __table_args__ = (
            UniqueConstraint('meeting_id', 'user_id', 'email', name='uq_meeting_participant'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=False, index=True)

        # Participant identity (internal user or external guest)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        email = Column(String(255), nullable=True)
        display_name = Column(String(255))

        # Role and status
        role = Column(String(20), default="participant")  # host, co_host, participant, observer
        status = Column(String(20), default="invited")  # invited, waiting, joined, left, removed

        # Timing
        invited_at = Column(DateTime, default=datetime.utcnow)
        joined_at = Column(DateTime)
        left_at = Column(DateTime)
        total_duration_seconds = Column(Integer, default=0)

        # Engagement metrics
        video_on_duration_seconds = Column(Integer, default=0)
        audio_on_duration_seconds = Column(Integer, default=0)
        screen_share_duration_seconds = Column(Integer, default=0)
        chat_messages_count = Column(Integer, default=0)
        reactions_count = Column(Integer, default=0)

        # Device info
        device_type = Column(String(50))  # desktop, mobile, tablet
        browser = Column(String(100))
        operating_system = Column(String(100))
        connection_quality = Column(String(20))  # excellent, good, fair, poor

        # Permissions
        can_share_screen = Column(Boolean, default=True)
        can_unmute = Column(Boolean, default=True)
        can_chat = Column(Boolean, default=True)
        can_record = Column(Boolean, default=False)

        # Recording consent
        recording_consent_given = Column(Boolean, default=False)
        recording_consent_at = Column(DateTime)
        recording_consent_method = Column(String(20))  # "dialog_click", "verbal", "implied"

        # AI analysis
        speaking_time_seconds = Column(Integer, default=0)
        sentiment_score = Column(Float)  # -1 to 1
        engagement_score = Column(Float)  # 0 to 100

        # Link to CRM entities
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        contact_id = Column(Integer, nullable=True)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class MeetingRecording(Base):
        """
        Stores information about meeting recordings.
        """
        __tablename__ = "meeting_recordings"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=False, index=True)

        # Recording identification
        recording_uuid = Column(String(100), unique=True, index=True)
        recording_name = Column(String(255))

        # Storage
        storage_provider = Column(String(50), default="s3")  # s3, gcs, azure, local
        storage_path = Column(String(1000))
        storage_bucket = Column(String(255))

        # Amazon Chime SDK recording
        chime_pipeline_id = Column(String(255))
        s3_key = Column(String(1000))

        file_size_bytes = Column(Integer)

        # Format
        video_format = Column(String(20), default="mp4")  # mp4, webm
        audio_format = Column(String(20), default="mp3")  # mp3, wav
        resolution = Column(String(20))  # 1080p, 720p, etc.
        duration_seconds = Column(Integer)

        # Status
        status = Column(String(20), default="pending")  # pending, recording, processing, ready, failed
        error_message = Column(Text)

        # Processing timestamps
        recording_started_at = Column(DateTime)
        recording_ended_at = Column(DateTime)
        processing_started_at = Column(DateTime)
        processing_completed_at = Column(DateTime)

        # AI Processing flags
        transcription_requested = Column(Boolean, default=True)
        summary_requested = Column(Boolean, default=True)
        action_items_requested = Column(Boolean, default=True)

        # Privacy and retention
        retention_days = Column(Integer, default=1825)  # 5 years per TILA/Reg Z
        auto_delete_at = Column(DateTime)
        is_deleted = Column(Boolean, default=False)
        deleted_at = Column(DateTime)

        # Recording consent
        consent_obtained = Column(Boolean, default=False)
        consent_type = Column(String(20))  # "all_party" or "one_party"
        consent_state_code = Column(String(2))
        disclosure_script_shown = Column(Text)
        consent_obtained_at = Column(DateTime)

        # Access control
        is_shared = Column(Boolean, default=False)
        shared_with_users = Column(JSON, default=[])  # List of user IDs
        share_link = Column(String(500))
        share_link_password = Column(String(100))

        # Download tracking
        download_count = Column(Integer, default=0)
        last_downloaded_at = Column(DateTime)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        created_by = Column(Integer, ForeignKey("users.id"))

    class RecordingTranscript(Base):
        """
        Stores meeting transcripts with speaker diarization.
        """
        __tablename__ = "recording_transcripts"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        recording_id = Column(Integer, ForeignKey("meeting_recordings.id"), nullable=False, index=True)
        meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=False, index=True)

        # Transcript status
        status = Column(String(20), default="pending")  # pending, processing, completed, failed
        error_message = Column(Text)

        # Full transcript
        full_transcript = Column(Text)  # Plain text version
        transcript_json = Column(JSON)  # Structured with timestamps and speakers

        # Processing info
        transcription_provider = Column(String(50))  # whisper, deepgram, assembly_ai
        language = Column(String(10), default="en")
        confidence_score = Column(Float)

        # Speaker diarization
        speakers_detected = Column(Integer, default=0)
        speaker_mapping = Column(JSON)  # {"speaker_1": "John Doe", "speaker_2": "Jane Smith"}

        # Word-level data
        word_count = Column(Integer)
        segments_count = Column(Integer)

        # Timestamps
        processing_started_at = Column(DateTime)
        processing_completed_at = Column(DateTime)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class MeetingAIAnalysis(Base):
        """
        Stores AI-generated analysis of meetings.
        """
        __tablename__ = "meeting_ai_analyses"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=False, index=True)
        recording_id = Column(Integer, ForeignKey("meeting_recordings.id"), nullable=True)
        transcript_id = Column(Integer, ForeignKey("recording_transcripts.id"), nullable=True)

        # Analysis type
        analysis_type = Column(String(50), nullable=False)  # summary, action_items, sentiment, etc.

        # Status
        status = Column(String(20), default="pending")
        error_message = Column(Text)

        # Analysis content
        content = Column(Text)  # Main analysis content
        structured_content = Column(JSON)  # Structured data

        # AI model info
        model_provider = Column(String(50))  # openai, anthropic
        model_name = Column(String(100))  # gpt-4, claude-3
        model_version = Column(String(50))

        # Quality metrics
        confidence_score = Column(Float)
        relevance_score = Column(Float)

        # Processing
        tokens_used = Column(Integer)
        processing_time_ms = Column(Integer)

        # User feedback
        user_rating = Column(Integer)  # 1-5
        user_feedback = Column(Text)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        created_by = Column(Integer, ForeignKey("users.id"))

    class MeetingChat(Base):
        """
        Stores in-meeting chat messages.
        """
        __tablename__ = "meeting_chats"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=False, index=True)
        participant_id = Column(Integer, ForeignKey("meeting_participants.id"), nullable=False)

        # Message content
        message = Column(Text, nullable=False)
        message_type = Column(String(20), default="text")  # text, file, reaction

        # Target (for direct messages)
        is_private = Column(Boolean, default=False)
        recipient_participant_id = Column(Integer, ForeignKey("meeting_participants.id"), nullable=True)

        # File attachment (if message_type is file)
        file_name = Column(String(255))
        file_path = Column(String(1000))
        file_type = Column(String(100))
        file_size_bytes = Column(Integer)

        # AI analysis
        sentiment = Column(String(20))  # positive, negative, neutral
        is_question = Column(Boolean, default=False)
        is_action_item = Column(Boolean, default=False)

        created_at = Column(DateTime, default=datetime.utcnow)
        is_deleted = Column(Boolean, default=False)
        deleted_at = Column(DateTime)

    class MeetingTemplate(Base):
        """
        Reusable meeting templates with predefined settings.
        """
        __tablename__ = "meeting_templates"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)

        # Template identification
        template_name = Column(String(255), nullable=False)
        template_key = Column(String(100), unique=True)  # e.g., "discovery_call", "closing_prep"
        description = Column(Text)

        # Organization
        organization_id = Column(Integer, nullable=True, index=True)
        is_system_template = Column(Boolean, default=False)  # Built-in templates

        # Meeting settings
        default_duration_minutes = Column(Integer, default=30)
        waiting_room_enabled = Column(Boolean, default=True)
        recording_enabled = Column(Boolean, default=True)
        transcription_enabled = Column(Boolean, default=True)
        ai_assistant_enabled = Column(Boolean, default=True)

        # Default agenda
        default_agenda = Column(JSON)  # List of agenda items

        # AI configuration
        summary_prompt = Column(Text)  # Custom prompt for AI summary
        action_items_enabled = Column(Boolean, default=True)
        follow_up_email_enabled = Column(Boolean, default=False)
        follow_up_email_template = Column(Text)

        # Intake questions for participants
        intake_questions = Column(JSON, default=[])

        # Visual
        color = Column(String(20), default="#3b82f6")
        icon = Column(String(50), default="video")

        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        created_by = Column(Integer, ForeignKey("users.id"))

    class ParticipantAnalytics(Base):
        """
        Detailed analytics for meeting participants.
        Tracks conversation metrics, engagement, and coaching opportunities.
        """
        __tablename__ = "participant_analytics"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        recording_id = Column(Integer, ForeignKey("meeting_recordings.id"), nullable=False, index=True)
        participant_id = Column(Integer, ForeignKey("meeting_participants.id"), nullable=False, index=True)

        # Talk metrics
        talk_time_seconds = Column(Integer, default=0)
        listen_time_seconds = Column(Integer, default=0)
        talk_listen_ratio = Column(Float)
        longest_monologue_seconds = Column(Integer, default=0)

        # Engagement metrics
        interruption_count = Column(Integer, default=0)
        question_count = Column(Integer, default=0)
        filler_word_count = Column(Integer, default=0)
        speaking_pace_wpm = Column(Integer)  # Words per minute

        # Sentiment analysis
        sentiment_positive_pct = Column(Float, default=0.0)
        sentiment_negative_pct = Column(Float, default=0.0)
        sentiment_neutral_pct = Column(Float, default=0.0)

        # Overall score (0-1)
        engagement_score = Column(Float)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class CoachingRecommendation(Base):
        """
        AI-generated coaching recommendations based on analytics.
        Provides actionable feedback for mortgage professionals.
        """
        __tablename__ = "coaching_recommendations"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        analytics_id = Column(Integer, ForeignKey("participant_analytics.id"), nullable=False, index=True)

        # Recommendation details
        category = Column(String(100), nullable=False)  # listening, questioning, pacing, clarity, mortgage_knowledge
        recommendation = Column(Text, nullable=False)
        priority = Column(String(20), default="medium")  # low, medium, high
        evidence = Column(JSON)  # Specific examples and metrics

        # Tracking
        is_acknowledged = Column(Boolean, default=False)
        acknowledged_at = Column(DateTime)

        created_at = Column(DateTime, default=datetime.utcnow)

    class MortgageIntelligence(Base):
        """
        Mortgage-specific intelligence extracted from meeting recordings.
        Detects borrower concerns, compliance risks, competitor mentions, and more.
        """
        __tablename__ = "mortgage_intelligence"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        recording_id = Column(Integer, ForeignKey("meeting_recordings.id"), nullable=False, index=True)

        # Borrower concerns detected
        borrower_concerns = Column(JSON)  # List of concerns with timestamps and severity

        # Compliance risk flags
        compliance_risks = Column(JSON)  # List of potential compliance issues

        # Competitor mentions
        competitor_mentions = Column(JSON)  # Competitors mentioned and context

        # Objection tracking
        objections = Column(JSON)  # Objections raised and how handled

        # Explanation effectiveness
        explanation_effectiveness = Column(JSON)  # Did borrower understand?

        # Loan details extracted
        loan_details = Column(JSON)  # Amount, type, rate mentioned, etc.

        # Next steps clarity
        next_steps_clarity = Column(JSON)  # Were next steps clearly communicated?

        # Overall risk score
        overall_risk_score = Column(Float)  # 0-1, higher = more risk
        priority_flags = Column(JSON)  # High priority items for review

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class OrganizationVideoSettings(Base):
        """
        Organization-level video meeting settings and policies.
        Controls recording permissions, consent requirements, and provider access.
        """
        __tablename__ = "organization_video_settings"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, unique=True, nullable=False, index=True)

        # Recording policies
        recording_allowed = Column(Boolean, default=True)
        recording_consent_required = Column(Boolean, default=True)
        default_consent_type = Column(String(20), default="one_party")  # "all_party" or "one_party"

        # Room defaults
        default_waiting_room = Column(Boolean, default=True)
        max_participants = Column(Integer, default=50)

        # Provider restrictions
        allowed_providers = Column(JSON, default=["internal", "zoom", "teams"])

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class BreakoutRoom(Base):
        """
        Breakout rooms within a meeting session.
        Hosts can create sub-rooms and assign participants.
        """
        __tablename__ = "breakout_rooms"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        meeting_id = Column(Integer, ForeignKey("video_meeting_rooms.id"), nullable=False, index=True)

        # Room identification
        room_name = Column(String(255), nullable=False)
        room_index = Column(Integer, default=0)  # ordering

        # Status
        status = Column(String(20), default="open")  # open, closed
        max_participants = Column(Integer, default=10)

        # Timing
        opened_at = Column(DateTime, default=datetime.utcnow)
        closed_at = Column(DateTime)
        duration_limit_minutes = Column(Integer)  # auto-close after N minutes

        # Participants (JSON list of participant IDs currently in the room)
        participant_ids = Column(JSON, default=[])

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        created_by = Column(Integer, ForeignKey("users.id"))

    # Return all models as a dictionary
    return {
        'VideoMeetingRoom': VideoMeetingRoom,
        'MeetingParticipant': MeetingParticipant,
        'MeetingRecording': MeetingRecording,
        'RecordingTranscript': RecordingTranscript,
        'MeetingAIAnalysis': MeetingAIAnalysis,
        'MeetingChat': MeetingChat,
        'MeetingTemplate': MeetingTemplate,
        'ParticipantAnalytics': ParticipantAnalytics,
        'CoachingRecommendation': CoachingRecommendation,
        'MortgageIntelligence': MortgageIntelligence,
        'OrganizationVideoSettings': OrganizationVideoSettings,
        'BreakoutRoom': BreakoutRoom
    }


# ============================================================================
# DEFAULT TEMPLATES
# ============================================================================

DEFAULT_MEETING_TEMPLATES = [
    {
        "template_key": "discovery_call",
        "template_name": "Discovery Call",
        "description": "Initial consultation with prospective borrowers",
        "default_duration_minutes": 30,
        "recording_enabled": True,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Introduction", "duration_minutes": 5},
            {"title": "Understand Goals", "duration_minutes": 10},
            {"title": "Financial Overview", "duration_minutes": 10},
            {"title": "Next Steps", "duration_minutes": 5}
        ],
        "color": "#10b981",
        "icon": "phone"
    },
    {
        "template_key": "pre_approval_review",
        "template_name": "Pre-Approval Review",
        "description": "Review pre-approval documents and discuss terms",
        "default_duration_minutes": 45,
        "recording_enabled": True,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Pre-Approval Status", "duration_minutes": 10},
            {"title": "Document Review", "duration_minutes": 20},
            {"title": "Rate Discussion", "duration_minutes": 10},
            {"title": "Questions & Next Steps", "duration_minutes": 5}
        ],
        "color": "#3b82f6",
        "icon": "document"
    },
    {
        "template_key": "document_review",
        "template_name": "Document Review Session",
        "description": "Screen share session to review and collect documents",
        "default_duration_minutes": 30,
        "recording_enabled": True,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Document Checklist Review", "duration_minutes": 5},
            {"title": "Document Upload Assistance", "duration_minutes": 20},
            {"title": "Missing Items Discussion", "duration_minutes": 5}
        ],
        "color": "#8b5cf6",
        "icon": "folder"
    },
    {
        "template_key": "rate_lock_discussion",
        "template_name": "Rate Lock Discussion",
        "description": "Discuss rate options and lock strategy",
        "default_duration_minutes": 20,
        "recording_enabled": True,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Current Market Conditions", "duration_minutes": 5},
            {"title": "Rate Options", "duration_minutes": 10},
            {"title": "Lock Decision", "duration_minutes": 5}
        ],
        "color": "#f59e0b",
        "icon": "lock"
    },
    {
        "template_key": "closing_prep",
        "template_name": "Closing Preparation",
        "description": "Pre-closing review and preparation session",
        "default_duration_minutes": 45,
        "recording_enabled": True,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Closing Disclosure Review", "duration_minutes": 20},
            {"title": "Wire Instructions", "duration_minutes": 10},
            {"title": "What to Expect at Closing", "duration_minutes": 10},
            {"title": "Final Questions", "duration_minutes": 5}
        ],
        "color": "#ef4444",
        "icon": "clipboard"
    },
    {
        "template_key": "post_close_review",
        "template_name": "Post-Close Review",
        "description": "Follow-up after closing to ensure satisfaction",
        "default_duration_minutes": 15,
        "recording_enabled": False,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Experience Feedback", "duration_minutes": 5},
            {"title": "Referral Discussion", "duration_minutes": 5},
            {"title": "Future Needs", "duration_minutes": 5}
        ],
        "color": "#06b6d4",
        "icon": "users"
    },
    {
        "template_key": "team_sync",
        "template_name": "Team Sync",
        "description": "Internal team meeting",
        "default_duration_minutes": 30,
        "recording_enabled": False,
        "ai_assistant_enabled": True,
        "default_agenda": [
            {"title": "Pipeline Review", "duration_minutes": 15},
            {"title": "Blockers & Issues", "duration_minutes": 10},
            {"title": "Action Items", "duration_minutes": 5}
        ],
        "color": "#64748b",
        "icon": "users"
    }
]
