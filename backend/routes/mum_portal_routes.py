"""
MUM Portal Public Routes

Public API routes for MUM (Mortgages Under Management) client portals.
These routes are accessible without authentication for client-facing portals.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from database import get_db
from services.mum_portal_service import get_mum_portal_service
from sqlalchemy.exc import SQLAlchemyError
from models.purl import (
    PURLWorkspace,
    PURLAccessToken,
    PURLTokenGenerator,
    TokenStatus,
    WorkspaceStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mum-portal", tags=["MUM Portal (Public)"])


@router.get("/{slug}")
async def get_mum_portal(
    slug: str,
    token: Optional[str] = Query(None, description="Access token for authenticated access"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get MUM portal data for client view.

    This is a public endpoint accessible by clients with their portal URL.
    If a token is provided, validates it and records the visit.
    """
    try:
        service = get_mum_portal_service(db)
        data = service.get_portal_data(slug=slug)

        if not data:
            raise HTTPException(status_code=404, detail="Portal not found")

        # If token provided, validate and record access
        if token:
            token_valid = _validate_and_record_token_access(db, token, data["workspace"]["id"])
            if token_valid:
                data["authenticated"] = True
            else:
                data["authenticated"] = False
        else:
            data["authenticated"] = False

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching MUM portal {slug}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load portal")


@router.get("/{slug}/videos")
async def get_mum_portal_videos(
    slug: str,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get video messages for a MUM portal.
    """
    # Get workspace
    workspace = (await db.execute(select(PURLWorkspace).where(
        PURLWorkspace.slug == slug,
        PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
    ))).scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Get video messages from portal_video_messages table
    try:
        from sqlalchemy import text
        videos = await db.execute(text("""
            SELECT
                id, video_url, thumbnail_url, title, description,
                duration_seconds, sender_name, sender_avatar_url,
                is_viewed, viewed_at, created_at
            FROM portal_video_messages
            WHERE workspace_id = :workspace_id
            ORDER BY created_at DESC
            LIMIT 50
        """), {"workspace_id": workspace.id}).fetchall()

        return {
            "videos": [
                {
                    "id": v.id,
                    "video_url": v.video_url,
                    "thumbnail_url": v.thumbnail_url,
                    "title": v.title,
                    "description": v.description,
                    "duration_seconds": v.duration_seconds,
                    "sender_name": v.sender_name,
                    "sender_avatar_url": v.sender_avatar_url,
                    "is_viewed": v.is_viewed,
                    "viewed_at": v.viewed_at.isoformat() if v.viewed_at else None,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in videos
            ]
        }
    except Exception as e:
        logger.warning(f"Failed to fetch videos for {slug}: {e}")
        # Return empty list if table doesn't exist or other error
        return {"videos": []}


@router.get("/{slug}/documents")
async def get_mum_portal_documents(
    slug: str,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get documents for a MUM portal.
    """
    from models.purl import PURLDocument

    # Get workspace
    workspace = (await db.execute(select(PURLWorkspace).where(
        PURLWorkspace.slug == slug,
        PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
    ))).scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Get documents
    documents = db.query(PURLDocument).filter(
        PURLDocument.workspace_id == workspace.id
    ).order_by(PURLDocument.created_at.desc()).all()

    return {
        "documents": [
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "doc_category": d.doc_category,
                "status": d.status,
                "file_name": d.file_name,
                "size_bytes": d.size_bytes,
                "mime_type": d.mime_type,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents
        ]
    }


@router.get("/{slug}/messages")
async def get_mum_portal_messages(
    slug: str,
    token: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get text messages for a MUM portal.
    """
    from models.purl import PURLMessage

    # Get workspace
    workspace = (await db.execute(select(PURLWorkspace).where(
        PURLWorkspace.slug == slug,
        PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
    ))).scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Get messages
    messages = db.query(PURLMessage).filter(
        PURLMessage.workspace_id == workspace.id
    ).order_by(PURLMessage.created_at.desc()).limit(limit).all()

    return {
        "messages": [
            {
                "id": m.id,
                "message_type": m.message_type,
                "content": m.content,
                "sender_type": m.sender_type,
                "is_read": m.is_read_by_borrower,
                "metadata": m.meta_data,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    }


@router.post("/{slug}/heartbeat")
async def mum_portal_heartbeat(
    slug: str,
    token: Optional[str] = Body(None, embed=True),
    page: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Record client activity/heartbeat on the portal.
    Used for engagement tracking.
    """
    # Get workspace
    workspace = (await db.execute(select(PURLWorkspace).where(
        PURLWorkspace.slug == slug,
        PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
    ))).scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Record the heartbeat
    try:
        from sqlalchemy import text
        await db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, resource_type, actor_type, meta_data, created_at
            ) VALUES (
                :org_id, :workspace_id, 'portal_heartbeat', 'mum_portal', 'contact',
                :metadata, NOW()
            )
        """), {
            "org_id": workspace.organization_id,
            "workspace_id": workspace.id,
            "metadata": {"page": page or "home"}
        })
        await db.commit()
    except SQLAlchemyError as e:
        logger.warning(f"Failed to record heartbeat: {e}")

    return {"success": True}


@router.post("/{slug}/messages/{message_id}/read")
async def mark_message_read(
    slug: str,
    message_id: int,
    token: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Mark a message as read by the client.
    """
    from models.purl import PURLMessage

    # Get workspace
    workspace = (await db.execute(select(PURLWorkspace).where(
        PURLWorkspace.slug == slug,
        PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
    ))).scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Get and update message
    message = (await db.execute(select(PURLMessage).where(
        PURLMessage.id == message_id,
        PURLMessage.workspace_id == workspace.id
    ))).scalars().first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    message.is_read_by_borrower = True
    message.read_at = datetime.now(timezone.utc)
    await db.commit()

    return {"success": True}


@router.post("/{slug}/videos/{video_id}/viewed")
async def mark_video_viewed(
    slug: str,
    video_id: int,
    token: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Mark a video as viewed by the client.
    """
    # Get workspace
    workspace = (await db.execute(select(PURLWorkspace).where(
        PURLWorkspace.slug == slug,
        PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
    ))).scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Update video viewed status
    try:
        from sqlalchemy import text
        await db.execute(text("""
            UPDATE portal_video_messages
            SET is_viewed = true, viewed_at = NOW()
            WHERE id = :video_id AND workspace_id = :workspace_id
        """), {"video_id": video_id, "workspace_id": workspace.id})
        await db.commit()
    except SQLAlchemyError as e:
        logger.warning(f"Failed to mark video viewed: {e}")

    return {"success": True}


def _validate_and_record_token_access(
    db: Session,
    token: str,
    workspace_id: int
) -> bool:
    """
    Validate token and record access.
    Returns True if token is valid.
    """
    try:
        if not PURLTokenGenerator.is_valid_format(token):
            return False

        token_hash = PURLTokenGenerator.hash_token(token)

        access_token = db.query(PURLAccessToken).filter(
            PURLAccessToken.token_hash == token_hash,
            PURLAccessToken.workspace_id == workspace_id,
            PURLAccessToken.status == TokenStatus.ACTIVE.value
        ).first()

        if not access_token:
            return False

        # Check expiration
        if access_token.expires_at and access_token.expires_at < datetime.now(timezone.utc):
            return False

        # Update last used
        access_token.last_used_at = datetime.now(timezone.utc)
        db.commit()

        return True

    except SQLAlchemyError as e:
        logger.warning(f"Token validation failed: {e}")
        return False
