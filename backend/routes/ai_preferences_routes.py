"""
AI User Preferences Routes
User personalization context and AI interaction preferences
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import logging
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user_flexible


# Pydantic models
class AIPreferencesUpdate(BaseModel):
    """Schema for updating AI preferences"""
    detail_level: Optional[str] = None  # 'concise', 'moderate', 'detailed'
    tone: Optional[str] = None  # 'casual', 'professional', 'formal'
    focus_areas: Optional[List[str]] = None  # ['revenue', 'compliance', 'efficiency', 'client_satisfaction']
    proactive_suggestions: Optional[bool] = None
    include_metrics: Optional[bool] = None
    preferred_greeting: Optional[str] = None  # 'standard', 'brief', 'personalized'


@router.get("/user-context")
async def get_ai_user_context(
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Get the current user's AI personalization context and preferences.
    Returns profile, performance metrics, learned preferences, and behavioral patterns.
    """
    try:
        from agents.memory.user_context import UserContextManager

        context = await UserContextManager.get_context(
            db,
            current_user.id,
            include_performance=True,
            include_preferences=True,
            include_behavior=True
        )

        return {
            "success": True,
            "context": context
        }

    except Exception as e:
        logger.error(f"Error getting AI user context: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/preferences")
async def update_ai_preferences(
    preferences: AIPreferencesUpdate,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Update user's AI interaction preferences.
    These preferences customize how the AI responds to the user.
    """
    try:
        from agents.memory.user_context import UserContextManager

        updated = []
        prefs_dict = preferences.model_dump(exclude_none=True)

        for key, value in prefs_dict.items():
            success = await UserContextManager.save_preference(db, current_user.id, key, value)
            if success:
                updated.append(key)

        if not updated:
            return {
                "success": True,
                "message": "No preferences to update",
                "updated": []
            }

        return {
            "success": True,
            "message": f"Updated {len(updated)} preference(s)",
            "updated": updated
        }

    except Exception as e:
        logger.error(f"Error updating AI preferences: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/preferences")
async def get_ai_preferences(
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Get user's current AI interaction preferences.
    """
    try:
        from agents.memory.user_context import UserContextManager

        context = await UserContextManager.get_context(
            db,
            current_user.id,
            include_performance=False,
            include_preferences=True,
            include_behavior=False
        )

        return {
            "success": True,
            "preferences": context.get('preferences', {}),
            "defaults": UserContextManager.DEFAULT_PREFERENCES
        }

    except Exception as e:
        logger.error(f"Error getting AI preferences: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
