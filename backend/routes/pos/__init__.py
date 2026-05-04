"""POS FastAPI routers."""
from .application import router as application_router
from .calendar import router as calendar_router
from .ai_qa import router as ai_qa_router
from .documents import router as documents_router
from .hydration import router as hydration_router
from .messages import router as messages_router
from .resolve_lo import router as resolve_lo_router
from .start import router as start_router
from .tasks import router as tasks_router

__all__ = ["application_router", "calendar_router", "ai_qa_router", "documents_router", "hydration_router", "messages_router", "resolve_lo_router", "start_router", "tasks_router"]
