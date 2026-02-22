"""
UVIP - Ultimate Video Intelligence Platform API Routes
Phase 1: Core Meeting Infrastructure

Thin router that imports and includes all sub-routers:
- video_meeting_crud_routes: Room/participant CRUD, waiting room, CRM linking
- video_meeting_realtime_routes: Breakout rooms, SFU endpoints, phone dial-out
- video_meeting_recording_routes: Recording management, screen recordings, Twilio callbacks
- video_meeting_template_routes: Template CRUD
- video_meeting_scheduling_routes: AI analysis, analytics, intelligence, settings, calendar
"""

from fastapi import APIRouter
import logging

from video_meeting_crud_routes import router as crud_router
from video_meeting_realtime_routes import router as realtime_router
from video_meeting_recording_routes import router as recording_router
from video_meeting_template_routes import router as template_router
from video_meeting_scheduling_routes import router as scheduling_router
from video_meeting_shared import set_dependencies  # noqa: F401 -- re-exported for main.py

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

router = APIRouter(prefix="/api/v1/meetings", tags=["Video Meetings"])

# Include all sub-routers (no additional prefix -- sub-routers use paths relative to /api/v1/meetings)
router.include_router(crud_router)
router.include_router(realtime_router)
router.include_router(recording_router)
router.include_router(template_router)
router.include_router(scheduling_router)
