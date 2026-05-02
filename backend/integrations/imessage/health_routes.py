"""Health check routes for BlueBubbles monitoring."""
from fastapi import APIRouter
from .health import get_health_status

health_router = APIRouter(prefix="/api/imessage", tags=["imessage-health"])


@health_router.get("/health")
async def imessage_health():
    return get_health_status()
