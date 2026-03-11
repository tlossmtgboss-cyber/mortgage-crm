"""
Calendar Events & Assignment Routes - THIN WRAPPER
Original code consolidated into routes/calendar_sync_routes.py (calendar_v1_router section).

Re-exports router for backward compatibility.
The original router had no prefix (full paths specified on each endpoint).
The consolidated file's calendar_v1_router also has no prefix.
"""
from routes.calendar_sync_routes import calendar_v1_router as router

__all__ = ["router"]
