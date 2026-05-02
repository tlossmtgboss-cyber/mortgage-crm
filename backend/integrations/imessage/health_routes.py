"""Health check routes for BlueBubbles monitoring."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database import get_db
from .health import get_health_status
from .models import IMessageLine

logger = logging.getLogger(__name__)

health_router = APIRouter(prefix="/api/imessage", tags=["imessage-health"])


@health_router.get("/health")
async def imessage_health(db: Session = Depends(get_db)):
    status = get_health_status()
    lines = []
    try:
        line_count = db.execute(
            select(func.count()).select_from(IMessageLine)
        ).scalar() or 0
        enabled_count = db.execute(
            select(func.count()).select_from(IMessageLine).where(IMessageLine.enabled == True)
        ).scalar() or 0
        status["lines_total"] = line_count
        status["lines_enabled"] = enabled_count
        lines = db.execute(
            select(
                IMessageLine.id,
                IMessageLine.organization_id,
                IMessageLine.handle,
                IMessageLine.enabled,
                IMessageLine.bb_base_url,
            )
        ).fetchall()
        status["lines"] = [
            {
                "id": str(row[0]),
                "org_id": row[1],
                "handle": row[2],
                "enabled": row[3],
                "bb_base_url": row[4][:30] + "..." if row[4] and len(row[4]) > 30 else row[4],
            }
            for row in lines
        ]
    except Exception as e:
        status["lines_total"] = f"error: {e}"

    # Live BB connectivity check
    try:
        first_line = db.execute(
            select(IMessageLine).where(IMessageLine.enabled == True).limit(1)
        ).scalar_one_or_none()
        if first_line:
            from .client import BlueBubblesClient
            client = BlueBubblesClient(first_line)
            try:
                ok = await client.ping()
                status["bb_ping"] = "ok" if ok else "failed"
            except Exception as ping_err:
                status["bb_ping"] = f"error: {ping_err}"
            finally:
                await client.aclose()
        else:
            status["bb_ping"] = "no_enabled_lines"
    except Exception as e:
        status["bb_ping"] = f"error: {e}"

    return status
