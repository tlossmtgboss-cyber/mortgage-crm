"""
Guideline Updates - FastAPI Routes
API endpoints for displaying recent guideline updates from all 5 sources
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

from database import get_db
from guideline_updates_models import GuidelineUpdate, UserUpdateView

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/guideline-updates", tags=["Guideline Updates"])


async def get_current_user_lazy(
    request: Request,
    db: Session = Depends(get_db)
):
    """Lazy import auth dependency to avoid circular imports"""
    from auth.dependencies import get_current_user_flexible as _get_current_user_flexible
    return await _get_current_user_flexible(request, db)


# Pydantic Models
class UpdateResponse(BaseModel):
    """Single guideline update response"""
    id: int
    source: str
    title: str
    section_code: Optional[str] = None
    description: Optional[str] = None
    url: str
    published_date: datetime
    scraped_date: datetime
    is_new: bool

    class Config:
        from_attributes = True


class SourceUpdates(BaseModel):
    """Updates grouped by source"""
    source: str
    source_name: str
    has_new_update: bool
    updates: List[UpdateResponse]


class SidebarResponse(BaseModel):
    """Complete sidebar data response"""
    has_unread: bool
    sources: List[SourceUpdates]


class NewUpdatesCheckResponse(BaseModel):
    """Response for checking new updates"""
    has_new_updates: bool
    unread_count: int


# API Endpoints
@router.get("/sidebar", response_model=SidebarResponse)
async def get_sidebar_updates(
    user_id: int = Query(..., description="Current user ID"),
    limit_per_source: int = Query(5, description="Max updates per source"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_lazy)
):
    """
    Get recent guideline updates for sidebar display
    Returns updates from all 5 sources with read/unread status
    """
    try:
        sources = ['fannie_mae', 'freddie_mac', 'fha', 'va', 'usda']
        sidebar_data = {
            'has_unread': False,
            'sources': []
        }

        for source in sources:
            # Get recent updates for this source
            updates = db.query(GuidelineUpdate).filter(
                GuidelineUpdate.source == source
            ).order_by(
                GuidelineUpdate.published_date.desc()
            ).limit(limit_per_source).all()

            # Check if any are unread
            has_new = False
            for update in updates:
                viewed = db.query(UserUpdateView).filter(
                    UserUpdateView.user_id == user_id,
                    UserUpdateView.update_id == update.id
                ).first()

                if not viewed and update.is_new:
                    has_new = True
                    sidebar_data['has_unread'] = True

            source_data = {
                'source': source,
                'source_name': _get_source_name(source),
                'has_new_update': has_new,
                'updates': [UpdateResponse.from_orm(u) for u in updates]
            }

            sidebar_data['sources'].append(source_data)

        return sidebar_data

    except Exception as e:
        logger.error(f"Error fetching sidebar updates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/check-new", response_model=NewUpdatesCheckResponse)
async def check_for_new_updates(
    user_id: int = Query(..., description="Current user ID"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_lazy)
):
    """
    Check if there are any new unread updates
    Returns count of unread updates
    """
    try:
        # Get all new updates
        new_updates = db.query(GuidelineUpdate).filter(
            GuidelineUpdate.is_new == True
        ).all()

        # Count unread
        unread_count = 0
        for update in new_updates:
            viewed = db.query(UserUpdateView).filter(
                UserUpdateView.user_id == user_id,
                UserUpdateView.update_id == update.id
            ).first()

            if not viewed:
                unread_count += 1

        return {
            'has_new_updates': unread_count > 0,
            'unread_count': unread_count
        }

    except Exception as e:
        logger.error(f"Error checking new updates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/mark-viewed/{update_id}")
async def mark_update_viewed(
    update_id: int,
    user_id: int = Query(..., description="Current user ID"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_lazy)
):
    """
    Mark a specific update as viewed by the user
    """
    try:
        # Check if already viewed
        existing = db.query(UserUpdateView).filter(
            UserUpdateView.user_id == user_id,
            UserUpdateView.update_id == update_id
        ).first()

        if not existing:
            view_record = UserUpdateView(
                user_id=user_id,
                update_id=update_id,
                viewed_at=datetime.now(timezone.utc)
            )
            db.add(view_record)
            db.commit()
            logger.info(f"User {user_id} viewed update {update_id}")

        return {'status': 'success', 'message': 'Update marked as viewed'}

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking update as viewed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/mark-all-viewed")
async def mark_all_viewed(
    user_id: int = Query(..., description="Current user ID"),
    source: Optional[str] = Query(None, description="Optional: mark only this source"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_lazy)
):
    """
    Mark all updates (or all from a specific source) as viewed
    """
    try:
        query = db.query(GuidelineUpdate)
        if source:
            query = query.filter(GuidelineUpdate.source == source)

        updates = query.all()

        marked_count = 0
        for update in updates:
            existing = db.query(UserUpdateView).filter(
                UserUpdateView.user_id == user_id,
                UserUpdateView.update_id == update.id
            ).first()

            if not existing:
                view_record = UserUpdateView(
                    user_id=user_id,
                    update_id=update.id,
                    viewed_at=datetime.now(timezone.utc)
                )
                db.add(view_record)
                marked_count += 1

        db.commit()
        logger.info(f"User {user_id} marked {marked_count} updates as viewed")

        return {
            'status': 'success',
            'marked_count': marked_count,
            'message': f'{marked_count} updates marked as viewed'
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking all as viewed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Helper Functions
def _get_source_name(source: str) -> str:
    """Convert source code to display name"""
    names = {
        'fannie_mae': 'Fannie Mae',
        'freddie_mac': 'Freddie Mac',
        'fha': 'FHA',
        'va': 'VA',
        'usda': 'USDA'
    }
    return names.get(source, source.title())
