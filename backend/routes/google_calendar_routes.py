"""
Google Calendar Integration Routes - THIN WRAPPER
Original code consolidated into routes/calendar_sync_routes.py (google_calendar_router section).

Re-exports router and set_dependencies for backward compatibility.
"""
from routes.calendar_sync_routes import google_calendar_router as router
from routes.calendar_sync_routes import set_dependencies

__all__ = ["router", "set_dependencies"]
