"""
User Settings Routes
Email processing and other user preference settings
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
import logging
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/user-settings")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'UserSettings': main.UserSettings,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


# Pydantic models
class EmailProcessingSettingsRequest(BaseModel):
    delete_from_inbox_after_processing: bool = False


class EmailProcessingSettingsResponse(BaseModel):
    delete_from_inbox_after_processing: bool = False


@router.get("/email-processing", response_model=EmailProcessingSettingsResponse)
async def get_email_processing_settings(
    current_user = Depends(current_user_dep),
    db: Session = Depends(lambda: get_db_dep())
):
    """Get user's email processing settings"""
    models = get_models()
    UserSettings = models['UserSettings']

    try:
        setting = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id,
            UserSettings.setting_key == "delete_from_inbox_after_processing"
        ).first()

        return EmailProcessingSettingsResponse(
            delete_from_inbox_after_processing=setting.setting_value == "true" if setting else False
        )
    except Exception as e:
        logger.error(f"Error getting email processing settings: {e}")
        return EmailProcessingSettingsResponse(delete_from_inbox_after_processing=False)


@router.put("/email-processing", response_model=EmailProcessingSettingsResponse)
async def update_email_processing_settings(
    settings: EmailProcessingSettingsRequest,
    current_user = Depends(current_user_dep),
    db: Session = Depends(lambda: get_db_dep())
):
    """Update user's email processing settings"""
    models = get_models()
    UserSettings = models['UserSettings']

    try:
        # Find or create the setting
        existing = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id,
            UserSettings.setting_key == "delete_from_inbox_after_processing"
        ).first()

        if existing:
            existing.setting_value = "true" if settings.delete_from_inbox_after_processing else "false"
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_setting = UserSettings(
                user_id=current_user.id,
                setting_key="delete_from_inbox_after_processing",
                setting_value="true" if settings.delete_from_inbox_after_processing else "false"
            )
            db.add(new_setting)

        db.commit()

        return EmailProcessingSettingsResponse(
            delete_from_inbox_after_processing=settings.delete_from_inbox_after_processing
        )
    except Exception as e:
        logger.error(f"Error updating email processing settings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
