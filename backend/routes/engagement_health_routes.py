"""Engagement engine health check — reports status of all subsystems."""
import logging
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_async_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/engagement", tags=["Engagement Health"])


@router.get("/health")
async def engagement_health(db: AsyncSession = Depends(get_async_db)):
    """Report health of all engagement subsystems."""
    checks = {}

    # 1. Database connectivity
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {e}"

    # 2. Anthropic API key configured
    checks["anthropic_api_key"] = "configured" if os.getenv("ANTHROPIC_API_KEY") else "missing"

    # 3. Twilio/Vapi configured
    checks["vapi_api_key"] = "configured" if os.getenv("VAPI_API_KEY") else "missing"
    checks["telnyx_api_key"] = "configured" if os.getenv("TELNYX_API_KEY") else "missing"

    # 4. Microsoft Graph configured
    checks["graph_client_id"] = "configured" if os.getenv("MICROSOFT_CLIENT_ID") else "missing"

    # 5. Drip enrollment table exists
    try:
        row = (await db.execute(text("SELECT COUNT(*) FROM drip_enrollments WHERE status = 'active'"))).fetchone()
        checks["drip_enrollments"] = f"healthy ({row[0]} active)"
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        checks["drip_enrollments"] = "table missing"

    # 6. Engagement events table exists
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        row = (await db.execute(text("SELECT COUNT(*) FROM engagement_events WHERE created_at >= :cutoff"), {"cutoff": cutoff})).fetchone()
        checks["engagement_events_24h"] = f"healthy ({row[0]} events)"
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        checks["engagement_events"] = "table missing"

    # 7. Speed-to-lead config
    try:
        row = (await db.execute(text("SELECT COUNT(*) FROM speed_to_lead_config"))).fetchone()
        checks["speed_to_lead_config"] = f"healthy ({row[0]} orgs configured)"
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        checks["speed_to_lead_config"] = "table missing"

    overall = "healthy" if all("healthy" in str(v) or "configured" in str(v) for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
