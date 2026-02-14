"""
User Profile Settings Routes
Comprehensive error handling pattern for user profile management
"""

from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, EmailStr, validator, root_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import re
import os
import uuid

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)

logger = logging.getLogger(__name__)


def _extract_token(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    raise HTTPException(status_code=401, detail="Not authenticated")
router = APIRouter(prefix="/api/v1/user-profile-settings", tags=["User Profile Settings"])

# Will be set by main.py
User = None
get_current_user = None
pwd_context = None


def set_dependencies(user_model, current_user_func, password_context):
    """Set dependencies from main.py"""
    global User, get_current_user, pwd_context
    User = user_model
    get_current_user = current_user_func
    pwd_context = password_context


# =============================================================================
# Pydantic Models with Validation
# =============================================================================

VALID_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


class ProfileUpdate(BaseModel):
    """Profile information update with validation"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50, description="First name")
    last_name: Optional[str] = Field(None, min_length=1, max_length=50, description="Last name")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    job_title: Optional[str] = Field(None, max_length=100, description="Job title")
    nmls_number: Optional[str] = Field(None, max_length=20, description="NMLS license number")
    bio: Optional[str] = Field(None, max_length=500, description="Short bio")
    timezone: Optional[str] = Field(None, description="User timezone")

    @validator('first_name', 'last_name')
    def validate_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError('Name cannot be empty')
        if re.search(r'[<>"\'\\/]', v):
            raise ValueError('Name contains invalid characters')
        return v

    @validator('phone')
    def validate_phone(cls, v):
        if v is None or v == '':
            return None
        # Remove common formatting
        cleaned = re.sub(r'[\s\-\(\)\.]', '', v)
        # Basic validation: should be mostly digits
        if not re.match(r'^\+?[\d]{7,15}$', cleaned):
            raise ValueError('Invalid phone number format')
        return v

    @validator('nmls_number')
    def validate_nmls(cls, v):
        if v is None or v == '':
            return None
        # NMLS numbers are typically 5-10 digits
        cleaned = re.sub(r'[^\d]', '', v)
        if not re.match(r'^\d{5,10}$', cleaned):
            raise ValueError('NMLS number should be 5-10 digits')
        return cleaned

    @validator('timezone')
    def validate_timezone(cls, v):
        if v is None:
            return v
        try:
            import pytz
            if v not in pytz.all_timezones:
                # Check common aliases
                aliases = {
                    'EST': 'America/New_York',
                    'CST': 'America/Chicago',
                    'MST': 'America/Denver',
                    'PST': 'America/Los_Angeles',
                }
                if v.upper() in aliases:
                    return aliases[v.upper()]
                raise ValueError(f'Invalid timezone: {v}')
            return v
        except ImportError:
            return v


class WorkHoursUpdate(BaseModel):
    """Work hours configuration with validation"""
    work_hours_start: Optional[str] = Field(None, description="Start time in HH:MM format")
    work_hours_end: Optional[str] = Field(None, description="End time in HH:MM format")
    work_days: Optional[List[str]] = Field(None, description="Working days")

    @validator('work_hours_start', 'work_hours_end')
    def validate_time_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('Time must be in HH:MM format (e.g., 09:00)')
        return v

    @validator('work_days')
    def validate_work_days(cls, v):
        if v is None:
            return v
        invalid_days = [d for d in v if d.lower() not in VALID_DAYS]
        if invalid_days:
            raise ValueError(f'Invalid days: {", ".join(invalid_days)}')
        return [d.lower() for d in v]

    @root_validator(skip_on_failure=True)
    def validate_time_range(cls, values):
        start = values.get('work_hours_start')
        end = values.get('work_hours_end')

        if start and end:
            start_parts = [int(x) for x in start.split(':')]
            end_parts = [int(x) for x in end.split(':')]
            start_minutes = start_parts[0] * 60 + start_parts[1]
            end_minutes = end_parts[0] * 60 + end_parts[1]

            if end_minutes <= start_minutes:
                raise ValueError('End time must be after start time')

        return values


class PasswordChange(BaseModel):
    """Password change with validation"""
    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")
    confirm_password: str = Field(..., description="Confirm new password")

    @validator('new_password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v

    @root_validator(skip_on_failure=True)
    def validate_passwords_match(cls, values):
        new_pw = values.get('new_password')
        confirm_pw = values.get('confirm_password')
        if new_pw and confirm_pw and new_pw != confirm_pw:
            raise ValueError('Passwords do not match')
        return values


class NotificationPreferences(BaseModel):
    """Notification preferences with validation"""
    email_notifications: bool = Field(True, description="Receive email notifications")
    sms_notifications: bool = Field(False, description="Receive SMS notifications")
    push_notifications: bool = Field(True, description="Receive push notifications")
    daily_digest: bool = Field(True, description="Receive daily digest email")
    task_reminders: bool = Field(True, description="Receive task reminders")
    lead_alerts: bool = Field(True, description="Receive new lead alerts")
    marketing_emails: bool = Field(False, description="Receive marketing emails")


class FullProfileUpdate(BaseModel):
    """Complete profile update combining all sections"""
    # Profile info
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    job_title: Optional[str] = Field(None, max_length=100)
    nmls_number: Optional[str] = Field(None, max_length=20)
    bio: Optional[str] = Field(None, max_length=500)
    timezone: Optional[str] = None

    # Work hours
    work_hours_start: Optional[str] = None
    work_hours_end: Optional[str] = None
    work_days: Optional[List[str]] = None

    # Notification preferences
    email_notifications: Optional[bool] = None
    sms_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    daily_digest: Optional[bool] = None
    task_reminders: Optional[bool] = None
    lead_alerts: Optional[bool] = None

    @validator('first_name', 'last_name')
    def validate_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError('Name cannot be empty')
        if re.search(r'[<>"\'\\/]', v):
            raise ValueError('Name contains invalid characters')
        return v

    @validator('phone')
    def validate_phone(cls, v):
        if v is None or v == '':
            return None
        cleaned = re.sub(r'[\s\-\(\)\.]', '', v)
        if not re.match(r'^\+?[\d]{7,15}$', cleaned):
            raise ValueError('Invalid phone number format')
        return v

    @validator('work_hours_start', 'work_hours_end')
    def validate_time_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('Time must be in HH:MM format')
        return v

    @validator('work_days')
    def validate_work_days(cls, v):
        if v is None:
            return v
        invalid_days = [d for d in v if d.lower() not in VALID_DAYS]
        if invalid_days:
            raise ValueError(f'Invalid days: {", ".join(invalid_days)}')
        return [d.lower() for d in v]


# =============================================================================
# Helper Functions
# =============================================================================

def get_user_profile_data(user) -> Dict[str, Any]:
    """Extract profile data from user object"""
    business_hours = getattr(user, 'business_hours', None) or {}
    notifications = getattr(user, 'notification_preferences', None) or {}

    # Split full_name into first/last
    full_name = user.full_name or ''
    name_parts = full_name.split(' ', 1)
    first_name = name_parts[0] if name_parts else ''
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    return {
        "id": user.id,
        "email": user.email,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "phone": getattr(user, 'phone', None),
        "job_title": getattr(user, 'title', None),
        "nmls_number": getattr(user, 'nmls_number', None),
        "bio": None,
        "timezone": getattr(user, 'timezone', 'America/New_York'),
        "photo_url": getattr(user, 'headshot_url', None) or getattr(user, 'company_logo_url', None),
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "work_hours": {
            "start": business_hours.get('start', '09:00'),
            "end": business_hours.get('end', '17:00'),
            "days": business_hours.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']),
        },
        "notifications": {
            "email": notifications.get('email', True),
            "sms": notifications.get('sms', False),
            "push": notifications.get('push', True),
            "daily_digest": notifications.get('daily_digest', True),
            "task_reminders": notifications.get('task_reminders', True),
            "lead_alerts": notifications.get('lead_alerts', True),
        },
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def validate_profile_completeness(user) -> Dict[str, Any]:
    """Check profile completeness and return warnings"""
    warnings = []
    completeness = 100
    missing_fields = []

    if not user.full_name:
        warnings.append("Full name is not set")
        missing_fields.append("name")
        completeness -= 15

    if not getattr(user, 'phone', None):
        warnings.append("Phone number is not set")
        missing_fields.append("phone")
        completeness -= 10

    if not getattr(user, 'title', None):
        warnings.append("Job title is not set")
        missing_fields.append("job_title")
        completeness -= 10

    if not getattr(user, 'nmls_number', None):
        missing_fields.append("nmls_number")
        completeness -= 5

    if not (getattr(user, 'headshot_url', None) or getattr(user, 'company_logo_url', None)):
        warnings.append("Profile photo is not set")
        missing_fields.append("photo")
        completeness -= 10

    return {
        "completeness_percent": max(0, completeness),
        "missing_fields": missing_fields,
        "warnings": warnings,
    }


# =============================================================================
# Routes
# =============================================================================

@router.get("")
async def get_profile_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current user's profile settings"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        profile_data = get_user_profile_data(current_user)
        completeness = validate_profile_completeness(current_user)

        return success_response(
            data={
                "profile": profile_data,
                "completeness": completeness,
            },
            warnings=completeness.get("warnings", []),
            message="Profile settings retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error fetching profile settings: {e}")
        raise DatabaseException(f"Failed to retrieve profile settings: {str(e)}")


@router.put("")
async def update_profile_settings(
    updates: FullProfileUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update current user's profile settings"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        update_data = updates.dict(exclude_unset=True)

        # Handle name fields → write to first_name/last_name columns
        if 'first_name' in update_data:
            current_user.first_name = update_data['first_name']
        if 'last_name' in update_data:
            current_user.last_name = update_data['last_name']

        # Update direct fields (job_title maps to title column; bio not in model)
        field_map = {'phone': 'phone', 'job_title': 'title', 'nmls_number': 'nmls_number', 'timezone': 'timezone'}
        for api_field, db_field in field_map.items():
            if api_field in update_data:
                setattr(current_user, db_field, update_data[api_field])

        # Update work hours
        if any(k in update_data for k in ['work_hours_start', 'work_hours_end', 'work_days']):
            business_hours = getattr(current_user, 'business_hours', None) or {}
            if 'work_hours_start' in update_data:
                business_hours['start'] = update_data['work_hours_start']
            if 'work_hours_end' in update_data:
                business_hours['end'] = update_data['work_hours_end']
            if 'work_days' in update_data:
                business_hours['days'] = update_data['work_days']
            current_user.business_hours = business_hours

        # Update notification preferences
        notification_fields = ['email_notifications', 'sms_notifications', 'push_notifications',
                              'daily_digest', 'task_reminders', 'lead_alerts']
        if any(k in update_data for k in notification_fields):
            notifications = getattr(current_user, 'notification_preferences', None) or {}
            field_mapping = {
                'email_notifications': 'email',
                'sms_notifications': 'sms',
                'push_notifications': 'push',
                'daily_digest': 'daily_digest',
                'task_reminders': 'task_reminders',
                'lead_alerts': 'lead_alerts',
            }
            for full_key, short_key in field_mapping.items():
                if full_key in update_data:
                    notifications[short_key] = update_data[full_key]
            current_user.notification_preferences = notifications

        db.commit()
        db.refresh(current_user)

        profile_data = get_user_profile_data(current_user)
        completeness = validate_profile_completeness(current_user)

        logger.info(f"Profile updated for user {current_user.email}: {list(update_data.keys())}")

        return success_response(
            data={
                "profile": profile_data,
                "completeness": completeness,
            },
            warnings=completeness.get("warnings", []),
            message="Profile updated successfully"
        )
    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to update profile: {str(e)}")


@router.put("/password")
async def change_password(
    password_data: PasswordChange,
    request: Request,
    db: Session = Depends(get_db)
):
    """Change current user's password"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        # Verify current password
        if not pwd_context.verify(password_data.current_password, current_user.hashed_password):
            raise ValidationException(
                message="Password change failed",
                field_errors={"current_password": "Current password is incorrect"}
            )

        # Hash and save new password
        current_user.hashed_password = pwd_context.hash(password_data.new_password)
        db.commit()

        logger.info(f"Password changed for user {current_user.email}")

        return success_response(
            data={"password_changed": True},
            message="Password changed successfully"
        )
    except ValidationException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error changing password: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to change password: {str(e)}")


@router.post("/photo")
async def upload_profile_photo(
    photo: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Upload profile photo for current user"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if photo.content_type not in allowed_types:
            raise ValidationException(
                message="Invalid file type",
                field_errors={"photo": "Allowed types: JPEG, PNG, GIF, WebP"}
            )

        # Read and validate file size
        contents = await photo.read()
        max_size = 5 * 1024 * 1024  # 5MB
        if len(contents) > max_size:
            raise ValidationException(
                message="File too large",
                field_errors={"photo": f"Maximum size is 5MB, got {len(contents) / 1024 / 1024:.1f}MB"}
            )

        # Generate filename with validated extension
        import re as _re
        raw_ext = photo.filename.rsplit('.', 1)[-1] if '.' in (photo.filename or '') else 'jpg'
        ext = raw_ext.lower() if _re.match(r'^[a-zA-Z0-9]{1,10}$', raw_ext) else 'jpg'
        allowed_img_exts = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'}
        if ext not in allowed_img_exts:
            ext = 'jpg'
        filename = f"profile_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"

        # Save file
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'profiles')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, 'wb') as f:
            f.write(contents)

        # Update user's photo URL
        photo_url = f"/uploads/profiles/{filename}"
        if hasattr(current_user, 'photo_url'):
            current_user.photo_url = photo_url
        elif hasattr(current_user, 'profile_photo'):
            current_user.profile_photo = photo_url

        db.commit()

        logger.info(f"Photo uploaded for user {current_user.id}: {filename}")

        return success_response(
            data={
                "photo_url": photo_url,
                "filename": filename,
                "size_bytes": len(contents),
            },
            message="Photo uploaded successfully"
        )
    except ValidationException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error uploading photo: {e}")
        raise DatabaseException(f"Failed to upload photo: {str(e)}")


@router.delete("/photo")
async def delete_profile_photo(
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete current user's profile photo"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        # Clear photo URL
        if hasattr(current_user, 'photo_url'):
            current_user.photo_url = None
        elif hasattr(current_user, 'profile_photo'):
            current_user.profile_photo = None

        db.commit()

        logger.info(f"Photo deleted for user {current_user.id}")

        return success_response(
            data={"photo_deleted": True},
            message="Photo deleted successfully"
        )
    except SQLAlchemyError as e:
        logger.error(f"Error deleting photo: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to delete photo: {str(e)}")


@router.get("/timezones")
async def get_timezones():
    """Get list of available timezones"""
    try:
        import pytz

        # Common US timezones first
        us_timezones = [
            {"value": "America/New_York", "label": "Eastern Time (ET)"},
            {"value": "America/Chicago", "label": "Central Time (CT)"},
            {"value": "America/Denver", "label": "Mountain Time (MT)"},
            {"value": "America/Los_Angeles", "label": "Pacific Time (PT)"},
            {"value": "America/Anchorage", "label": "Alaska Time"},
            {"value": "Pacific/Honolulu", "label": "Hawaii Time"},
        ]

        return success_response(
            data={
                "us_timezones": us_timezones,
                "all_timezones": sorted(pytz.all_timezones),
            },
            message="Timezones retrieved"
        )
    except ImportError:
        return success_response(
            data={
                "us_timezones": [
                    {"value": "America/New_York", "label": "Eastern Time"},
                    {"value": "America/Chicago", "label": "Central Time"},
                    {"value": "America/Denver", "label": "Mountain Time"},
                    {"value": "America/Los_Angeles", "label": "Pacific Time"},
                ],
                "all_timezones": [],
            },
            message="Timezones retrieved (pytz not available)"
        )


@router.get("/password-requirements")
async def get_password_requirements():
    """Get password requirements for display"""
    return success_response(
        data={
            "min_length": 8,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_number": True,
            "require_special": False,
            "requirements": [
                "At least 8 characters",
                "At least one uppercase letter",
                "At least one lowercase letter",
                "At least one number",
            ],
        },
        message="Password requirements retrieved"
    )


# =============================================================================
# /api/v1/users/me — Frontend-compatible profile endpoints
# =============================================================================

users_router = APIRouter(prefix="/api/v1/users", tags=["Users"])


class UserMeUpdate(BaseModel):
    """Update model matching what the frontend Settings.js sends"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    nmls_number: Optional[str] = None
    job_title: Optional[str] = None
    work_hours_start: Optional[str] = None
    work_hours_end: Optional[str] = None
    work_days: Optional[List[str]] = None


@users_router.get("/me")
async def get_current_user_profile(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current user's profile — flat JSON for frontend Settings.js"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        business_hours = getattr(current_user, 'business_hours', None) or {}

        return {
            "id": current_user.id,
            "slug": getattr(current_user, 'slug', None) or '',
            "full_name": current_user.full_name or '',
            "email": current_user.email or '',
            "phone": getattr(current_user, 'phone', None) or '',
            "job_title": getattr(current_user, 'title', None) or '',
            "nmls_number": getattr(current_user, 'nmls_number', None) or '',
            "bio": '',
            "timezone": getattr(current_user, 'timezone', 'America/New_York'),
            "photo_url": getattr(current_user, 'headshot_url', None) or getattr(current_user, 'company_logo_url', None),
            "role": current_user.role,
            "work_hours_start": business_hours.get('start', '09:00'),
            "work_hours_end": business_hours.get('end', '17:00'),
            "work_days": business_hours.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']),
        }
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Internal server error")


@users_router.put("/me")
async def update_current_user_profile(
    updates: UserMeUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update current user's profile — accepts flat JSON from frontend Settings.js"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        update_data = updates.dict(exclude_unset=True)

        # Handle full_name → split into first_name and last_name columns
        if 'full_name' in update_data and update_data['full_name']:
            name = update_data['full_name'].strip()
            parts = name.split(' ', 1)
            current_user.first_name = parts[0]
            current_user.last_name = parts[1] if len(parts) > 1 else ''

        # Update direct fields (job_title maps to title column)
        field_map = {'phone': 'phone', 'job_title': 'title', 'nmls_number': 'nmls_number'}
        for api_field, db_field in field_map.items():
            if api_field in update_data:
                setattr(current_user, db_field, update_data[api_field])

        # Update work hours
        if any(k in update_data for k in ['work_hours_start', 'work_hours_end', 'work_days']):
            business_hours = getattr(current_user, 'business_hours', None) or {}
            if 'work_hours_start' in update_data:
                business_hours['start'] = update_data['work_hours_start']
            if 'work_hours_end' in update_data:
                business_hours['end'] = update_data['work_hours_end']
            if 'work_days' in update_data:
                business_hours['days'] = update_data['work_days']
            current_user.business_hours = business_hours

        db.commit()
        db.refresh(current_user)

        logger.info(f"Profile updated for user {current_user.email}: {list(update_data.keys())}")

        business_hours = getattr(current_user, 'business_hours', None) or {}
        return {
            "id": current_user.id,
            "full_name": current_user.full_name or '',
            "email": current_user.email or '',
            "phone": getattr(current_user, 'phone', None) or '',
            "job_title": getattr(current_user, 'title', None) or '',
            "nmls_number": getattr(current_user, 'nmls_number', None) or '',
            "work_hours_start": business_hours.get('start', '09:00'),
            "work_hours_end": business_hours.get('end', '17:00'),
            "work_days": business_hours.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']),
            "message": "Profile updated successfully",
        }
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        db.rollback()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Internal server error")


@users_router.put("/me/password")
async def change_user_password(
    password_data: PasswordChange,
    request: Request,
    db: Session = Depends(get_db)
):
    """Change password — frontend-compatible path at /api/v1/users/me/password"""
    try:
        current_user = await get_current_user(_extract_token(request), request, db)

        if not pwd_context.verify(password_data.current_password, current_user.hashed_password):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        current_user.hashed_password = pwd_context.hash(password_data.new_password)
        db.commit()

        logger.info(f"Password changed for user {current_user.email}")
        return {"message": "Password changed successfully"}
    except Exception as e:
        if "400" in str(type(e)):
            raise
        logger.error(f"Error changing password: {e}")
        db.rollback()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Internal server error")
