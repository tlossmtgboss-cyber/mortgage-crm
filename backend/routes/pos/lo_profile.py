"""Public LO profile endpoint for POS entry page personalization."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from database.models.core import User, EmailSignature
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos")

# ── L2: Simple in-memory rate limiter (max 30 requests/min per IP) ────
# Same caveat as start.py: resets on deploy. Redis-backed is the future path.
_LO_PROFILE_RATE_LIMIT = 30
_LO_PROFILE_RATE_WINDOW = 60  # seconds
_profile_ip_tracker: dict[str, list[float]] = defaultdict(list)
_profile_ip_lock = Lock()


def _check_lo_profile_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - _LO_PROFILE_RATE_WINDOW
    with _profile_ip_lock:
        timestamps = [t for t in _profile_ip_tracker.get(ip, []) if t > cutoff]
        if not timestamps:
            _profile_ip_tracker.pop(ip, None)
        else:
            _profile_ip_tracker[ip] = timestamps
        if len(_profile_ip_tracker.get(ip, [])) >= _LO_PROFILE_RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again shortly.",
            )
        _profile_ip_tracker.setdefault(ip, []).append(now)


class LOProfileResponse(BaseModel):
    name: str
    title: Optional[str] = None
    headshot_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    nmls: Optional[str] = None
    company_logo_url: Optional[str] = None
    tagline: Optional[str] = None
    schedule_url: Optional[str] = None


@router.get("/lo-profile/{lo_slug}", response_model=LOProfileResponse)
def get_lo_profile(
    lo_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    _check_lo_profile_rate_limit(request)
    user = (
        db.query(User)
        .filter(User.slug == lo_slug, User.is_active == True)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan officer not found")

    sig = (
        db.query(EmailSignature)
        .filter(EmailSignature.user_id == user.id, EmailSignature.is_active == True)
        .first()
    )

    if sig:
        return LOProfileResponse(
            name=sig.full_name or user.full_name,
            title=sig.title or user.title,
            headshot_url=sig.headshot_url or user.headshot_url,
            phone=sig.cell_phone or sig.office_phone or user.phone,
            email=sig.email or user.email,
            address=sig.address or user.business_address,
            nmls=sig.nmls_id or user.nmls_number or user.nmls_id,
            company_logo_url=sig.company_logo_url or user.company_logo_url,
            tagline=sig.tagline,
            schedule_url=sig.schedule_url,
        )

    return LOProfileResponse(
        name=user.full_name,
        title=user.title,
        headshot_url=user.headshot_url,
        phone=user.phone,
        email=user.email,
        address=user.business_address,
        nmls=user.nmls_number or user.nmls_id,
        company_logo_url=user.company_logo_url,
    )
