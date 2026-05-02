"""Perennia iMessage integration (BlueBubbles-backed, Telnyx fallback)."""
from .config import IMessageSettings, get_imessage_settings  # noqa: F401
from .factory import build_imessage_service, shutdown_clients  # noqa: F401
from .health_routes import health_router  # noqa: F401
from .router import api_router, webhook_router  # noqa: F401
from .schemas import (  # noqa: F401
    Channel,
    ConversationMessage,
    ConversationThread,
    Direction,
    IMessageDetectionResult,
    InboundMessageEvent,
    MessageStatus,
    SendMessageRequest,
    SendMessageResponse,
    SendStyle,
    TapbackRequest,
    TapbackType,
)
from .service import IMessageService  # noqa: F401
