"""
Input Validation & Sanitization Module
======================================
Comprehensive input validation for all user-provided data.

Provides:
- HTML/XSS sanitization using bleach
- File upload validation with MIME type checking
- Pydantic validators for common patterns
- Content length limits
"""

import re
import os
import logging
from typing import Optional, List, Any
from datetime import datetime

try:
    import nh3
    NH3_AVAILABLE = True
except ImportError:
    NH3_AVAILABLE = False
    logging.warning("nh3 not installed - HTML sanitization disabled")

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logging.warning("python-magic not installed - MIME type validation disabled")

from fastapi import UploadFile, HTTPException
from pydantic import BaseModel, validator, Field, constr

logger = logging.getLogger(__name__)


# ============================================================================
# TEXT SANITIZATION
# ============================================================================

def sanitize_text(text: str, max_length: int = 10000) -> str:
    """
    Remove all HTML tags and dangerous content from text.
    Use for titles, names, plain text fields.
    """
    if not text:
        return ""

    if NH3_AVAILABLE:
        # Remove all HTML tags
        cleaned = nh3.clean(text, tags=set())
    else:
        # Fallback: basic HTML tag removal
        cleaned = re.sub(r'<[^>]+>', '', text)

    # Remove javascript: and data: URLs
    cleaned = re.sub(r'javascript:', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'data:', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'vbscript:', '', cleaned, flags=re.IGNORECASE)

    # Remove null bytes
    cleaned = cleaned.replace('\x00', '')

    # Truncate to max length
    return cleaned.strip()[:max_length]


def sanitize_html(html: str, max_length: int = 50000) -> str:
    """
    Allow basic HTML formatting but remove dangerous tags/attributes.
    Use for rich text descriptions, comments with formatting.
    """
    if not html:
        return ""

    if NH3_AVAILABLE:
        allowed_tags = {'p', 'br', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li', 'a', 'span'}
        allowed_attrs = {
            'a': {'href', 'title'},  # No target="_blank" onclick etc
            'span': {'class'},
        }

        cleaned = nh3.clean(
            html,
            tags=allowed_tags,
            attributes=allowed_attrs,
            link_rel="noopener noreferrer",
        )
    else:
        # Fallback: remove all HTML
        cleaned = re.sub(r'<[^>]+>', '', html)

    return cleaned.strip()[:max_length]


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks.
    """
    if not filename:
        return "unnamed"

    # Remove path components
    filename = os.path.basename(filename)

    # Remove potentially dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '', filename)

    # Prevent hidden files
    filename = filename.lstrip('.')

    # Limit length
    name, ext = os.path.splitext(filename)
    name = name[:100]
    ext = ext[:10]

    return f"{name}{ext}" if name else "unnamed"


# ============================================================================
# FILE UPLOAD VALIDATION
# ============================================================================

class FileUploadValidator:
    """Validate file uploads for security and type compliance"""

    # Allowed MIME types by category
    ALLOWED_VIDEO_MIMES = {
        'video/webm',
        'video/mp4',
        'video/quicktime',
        'video/x-msvideo',
        'video/x-matroska',
    }

    ALLOWED_IMAGE_MIMES = {
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif',
    }

    ALLOWED_DOCUMENT_MIMES = {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }

    # File size limits (bytes)
    MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB
    MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10 MB
    MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50 MB

    # Extension to MIME type mapping
    VIDEO_EXTENSIONS = {'.webm', '.mp4', '.mov', '.avi', '.mkv'}
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}

    @classmethod
    async def validate_video(cls, file: UploadFile) -> dict:
        """Validate video file upload"""
        return await cls._validate_file(
            file,
            allowed_mimes=cls.ALLOWED_VIDEO_MIMES,
            allowed_extensions=cls.VIDEO_EXTENSIONS,
            max_size=cls.MAX_VIDEO_SIZE,
            file_type="video"
        )

    @classmethod
    async def validate_image(cls, file: UploadFile) -> dict:
        """Validate image file upload"""
        return await cls._validate_file(
            file,
            allowed_mimes=cls.ALLOWED_IMAGE_MIMES,
            allowed_extensions=cls.IMAGE_EXTENSIONS,
            max_size=cls.MAX_IMAGE_SIZE,
            file_type="image"
        )

    @classmethod
    async def validate_document(cls, file: UploadFile) -> dict:
        """Validate document file upload"""
        return await cls._validate_file(
            file,
            allowed_mimes=cls.ALLOWED_DOCUMENT_MIMES,
            allowed_extensions=cls.DOCUMENT_EXTENSIONS,
            max_size=cls.MAX_DOCUMENT_SIZE,
            file_type="document"
        )

    @classmethod
    async def _validate_file(
        cls,
        file: UploadFile,
        allowed_mimes: set,
        allowed_extensions: set,
        max_size: int,
        file_type: str
    ) -> dict:
        """Internal file validation logic"""

        # Check filename
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename required")

        # Sanitize filename
        safe_filename = sanitize_filename(file.filename)

        # Check extension
        ext = os.path.splitext(safe_filename)[1].lower()
        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {file_type} type. Allowed: {', '.join(allowed_extensions)}"
            )

        # Read file content with bounded read to prevent memory exhaustion
        content = await file.read(max_size + 1)

        # Check file size
        file_size = len(content)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {max_mb:.0f}MB"
            )

        await file.seek(0)  # Reset for later use

        # Verify MIME type using python-magic
        detected_mime = None
        if MAGIC_AVAILABLE:
            try:
                detected_mime = magic.from_buffer(content, mime=True)
                if detected_mime not in allowed_mimes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid {file_type} format. Detected: {detected_mime}"
                    )
            except Exception as e:
                logger.warning(f"MIME detection failed: {e}")

        return {
            "valid": True,
            "filename": safe_filename,
            "size": file_size,
            "mime_type": detected_mime or file.content_type,
            "extension": ext
        }


# ============================================================================
# PYDANTIC VALIDATORS
# ============================================================================

def create_text_validator(max_length: int = 500, allow_empty: bool = False):
    """Create a Pydantic validator for text fields"""
    def validator_func(cls, v):
        if not v:
            if allow_empty:
                return ""
            raise ValueError("Field cannot be empty")

        cleaned = sanitize_text(v, max_length)
        if not cleaned and not allow_empty:
            raise ValueError("Field cannot be empty after sanitization")

        return cleaned

    return validator_func


def create_html_validator(max_length: int = 5000, allow_empty: bool = True):
    """Create a Pydantic validator for HTML fields"""
    def validator_func(cls, v):
        if not v:
            return "" if allow_empty else None

        return sanitize_html(v, max_length)

    return validator_func


# ============================================================================
# COMMON VALIDATION PATTERNS
# ============================================================================

# Email validation regex
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# Phone number validation (E.164 format)
PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'

# UUID validation
UUID_REGEX = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'

# Slug validation (URL-safe string)
SLUG_REGEX = r'^[a-z0-9]+(?:-[a-z0-9]+)*$'


def validate_email(email: str) -> str:
    """Validate and normalize email address"""
    if not email:
        raise ValueError("Email required")

    email = email.strip().lower()

    if not re.match(EMAIL_REGEX, email):
        raise ValueError("Invalid email format")

    if len(email) > 254:
        raise ValueError("Email too long")

    return email


def validate_phone(phone: str) -> str:
    """Validate and normalize phone number"""
    if not phone:
        raise ValueError("Phone number required")

    # Remove formatting characters
    phone = re.sub(r'[\s\-\(\)\.]', '', phone)

    # Ensure starts with + for international format
    if not phone.startswith('+'):
        phone = '+1' + phone  # Assume US if no country code

    if not re.match(PHONE_REGEX, phone):
        raise ValueError("Invalid phone number format")

    return phone


def validate_url(url: str, allowed_schemes: set = {'http', 'https'}) -> str:
    """Validate URL is safe"""
    if not url:
        raise ValueError("URL required")

    url = url.strip()

    # Parse URL
    from urllib.parse import urlparse
    parsed = urlparse(url)

    # Check scheme
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError(f"Invalid URL scheme. Allowed: {', '.join(allowed_schemes)}")

    # Check for dangerous patterns
    dangerous_patterns = ['javascript:', 'data:', 'vbscript:', 'file:']
    if any(url.lower().startswith(p) for p in dangerous_patterns):
        raise ValueError("Unsafe URL")

    return url


# ============================================================================
# RATE LIMIT HELPERS
# ============================================================================

def get_rate_limit_key(request, user_id: int = None) -> str:
    """Generate rate limit key from request"""
    if user_id:
        return f"user:{user_id}"

    # Fallback to IP
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


# ============================================================================
# VALIDATION SCHEMAS FOR UVIP
# ============================================================================

class ClipCreateSchema(BaseModel):
    """Schema for creating a video clip"""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    clip_type: str = Field("screen_camera", pattern=r'^(screen_camera|screen_only|camera_only)$')
    template_id: Optional[int] = None
    crm_entity_type: Optional[str] = Field(None, pattern=r'^(loan|lead|contact)$')
    crm_entity_id: Optional[int] = None
    tags: Optional[List[str]] = Field(None, max_items=10)

    _sanitize_title = validator('title', allow_reuse=True)(
        create_text_validator(max_length=500, allow_empty=False)
    )
    _sanitize_description = validator('description', allow_reuse=True)(
        create_html_validator(max_length=5000, allow_empty=True)
    )

    @validator('tags')
    def sanitize_tags(cls, v):
        if not v:
            return []
        cleaned = []
        for tag in v[:10]:  # Max 10 tags
            clean_tag = sanitize_text(tag, max_length=50)
            if clean_tag:
                cleaned.append(clean_tag)
        return cleaned


class ClipCommentSchema(BaseModel):
    """Schema for clip comments"""
    comment_text: str = Field(..., min_length=1, max_length=1000)
    timestamp_seconds: Optional[int] = Field(None, ge=0, le=86400)
    emoji_reaction: Optional[str] = Field(None, pattern=r'^(thumbs_up|heart|question|confused|celebrate)$')

    @validator('comment_text')
    def sanitize_comment(cls, v):
        if not v or not v.strip():
            raise ValueError("Comment cannot be empty")

        # Strip all HTML for comments (plain text only)
        cleaned = sanitize_text(v, max_length=1000)

        if not cleaned:
            raise ValueError("Comment cannot be empty after sanitization")

        return cleaned


class ClipShareSchema(BaseModel):
    """Schema for creating share links"""
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = Field(None, max_length=200)
    allow_download: bool = False
    allow_comments: bool = True
    require_email: bool = False
    max_views: Optional[int] = Field(None, ge=1, le=10000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    password: Optional[str] = Field(None, min_length=6, max_length=100)

    @validator('recipient_email')
    def validate_recipient_email(cls, v):
        if v:
            return validate_email(v)
        return None

    @validator('recipient_name')
    def sanitize_recipient_name(cls, v):
        if v:
            return sanitize_text(v, max_length=200)
        return None


class MeetingRoomCreateSchema(BaseModel):
    """Schema for creating meeting rooms"""
    room_name: str = Field(..., min_length=1, max_length=500)
    room_description: Optional[str] = Field(None, max_length=2000)
    provider: str = Field("internal", pattern=r'^(internal|zoom|teams|google_meet)$')
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    max_participants: Optional[int] = Field(None, ge=2, le=100)
    recording_enabled: bool = False
    waiting_room_enabled: bool = False

    _sanitize_name = validator('room_name', allow_reuse=True)(
        create_text_validator(max_length=500, allow_empty=False)
    )
    _sanitize_description = validator('room_description', allow_reuse=True)(
        create_html_validator(max_length=2000, allow_empty=True)
    )

    @validator('scheduled_end')
    def validate_end_after_start(cls, v, values):
        start = values.get('scheduled_start')
        if start and v and v <= start:
            raise ValueError("End time must be after start time")
        return v


class ParticipantAddSchema(BaseModel):
    """Schema for adding meeting participants"""
    email: Optional[str] = None
    phone: Optional[str] = None
    display_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field("participant", pattern=r'^(host|co-host|participant|guest)$')

    @validator('email')
    def validate_email_field(cls, v):
        if v:
            return validate_email(v)
        return None

    @validator('phone')
    def validate_phone_field(cls, v):
        if v:
            return validate_phone(v)
        return None

    @validator('display_name')
    def sanitize_display_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Display name required")
        return sanitize_text(v, max_length=100)


class ViewProgressSchema(BaseModel):
    """Schema for view progress updates"""
    watch_duration_seconds: int = Field(..., ge=0, le=86400)
    completion_rate: float = Field(..., ge=0.0, le=1.0)
    play_events: Optional[List[dict]] = Field(None, max_items=100)

    @validator('play_events')
    def validate_play_events(cls, v):
        if not v:
            return []
        # Limit event data
        cleaned = []
        for event in v[:100]:
            if isinstance(event, dict):
                cleaned.append({
                    'type': str(event.get('type', ''))[:50],
                    'timestamp': float(event.get('timestamp', 0)),
                })
        return cleaned
