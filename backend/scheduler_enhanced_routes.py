"""
Enhanced Scheduler Routes - THIN WRAPPER
Original code consolidated into routes/scheduler_appointment_routes.py (enhanced section).

Re-exports router and set_enhanced_dependencies for backward compatibility.
The enhanced routes are now appended to the main appointment routes file.
"""
from routes.scheduler_appointment_routes import (
    router,
    set_enhanced_dependencies,
)

__all__ = ["router", "set_enhanced_dependencies"]
