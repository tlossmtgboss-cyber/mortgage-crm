"""Health check routes for BlueBubbles monitoring."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database import get_db
from .health import get_health_status
from .models import IMessageLine

health_router = APIRouter(prefix="/api/imessage", tags=["imessage-health"])


@health_router.get("/health")
async def imessage_health(db: Session = Depends(get_db)):
    status = get_health_status()
    try:
        line_count = db.execute(
            select(func.count()).select_from(IMessageLine)
        ).scalar() or 0
        enabled_count = db.execute(
            select(func.count()).select_from(IMessageLine).where(IMessageLine.enabled == True)
        ).scalar() or 0
        status["lines_total"] = line_count
        status["lines_enabled"] = enabled_count
    except Exception:
        status["lines_total"] = "error"
    return status
