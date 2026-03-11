"""
Unified Calendar Routes - THIN WRAPPER
Original code consolidated into routes/calendar_sync_routes.py (calendar_v1_router section).

The unified endpoint GET /api/v1/calendar/unified is now in the calendar_v1_router.
Re-exports that sub-router for backward compatibility.

Note: The original had prefix="/api/v1/calendar" on the router.
The consolidated calendar_v1_router has no prefix (full paths on endpoints).
Inline_legacy_routes.py includes this with no extra prefix, so the full paths work correctly.
"""
from routes.calendar_sync_routes import calendar_v1_router as router

__all__ = ["router"]
