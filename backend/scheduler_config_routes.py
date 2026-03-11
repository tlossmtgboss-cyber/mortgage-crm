"""
Scheduler Configuration Routes - THIN WRAPPER
Original code consolidated into routes/scheduler_routes.py

Re-exports router and set_dependencies for backward compatibility.
"""
from routes.scheduler_routes import router, set_dependencies

__all__ = ["router", "set_dependencies"]
