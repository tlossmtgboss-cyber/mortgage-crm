"""CIE API — combines webhook + read routers."""
from fastapi import APIRouter

from .webhooks import router as webhook_router
from .reads import router as read_router

router = APIRouter(prefix="/api/v1/cie", tags=["cie"])
router.include_router(webhook_router)
router.include_router(read_router)
