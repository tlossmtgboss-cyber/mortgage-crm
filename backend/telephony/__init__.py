# Telephony module for Click-to-Dial and Power Dialer

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

from .provider import (
    TelephonyProvider,
    TelnyxProvider,
    get_telephony_provider,
    reset_provider,
    TelephonyError,
    CallResult,
    CallStatus,
)
from .dialer_engine import DialerEngine, click_to_dial
from .compliance import ComplianceChecker, ComplianceError
from .websocket import ws_manager, WebSocketManager, DialerEvent
from .router import router as dialer_router, set_dependencies
from .disposition_router import router as disposition_router, set_dependencies as set_disposition_dependencies
from .analytics_router import router as analytics_router, set_dependencies as set_analytics_dependencies
from .admin_router import router as admin_router, set_dependencies as set_admin_dependencies

# Schemas
from .schemas import (
    AgentTelephonySettingsUpdate,
    ClickToDialRequest,
    ClickToDialResponse,
    StartSessionRequest,
    StartSessionResponse,
    SessionStatusResponse,
    DispositionRequest,
    DispositionResponse,
    VerifyCallerIdRequest,
    VerifyCallerIdResponse,
    ComplianceCheckResponse,
    CallLogEntry,
    CallLogsResponse,
)

__all__ = [
    # Providers
    'TelephonyProvider',
    'TelnyxProvider',
    'get_telephony_provider',
    'reset_provider',
    'TelephonyError',
    'CallResult',
    'CallStatus',
    # Engine
    'DialerEngine',
    'click_to_dial',
    # Compliance
    'ComplianceChecker',
    'ComplianceError',
    # WebSocket
    'ws_manager',
    'WebSocketManager',
    'DialerEvent',
    # Router
    'dialer_router',
    'set_dependencies',
    'disposition_router',
    'set_disposition_dependencies',
    'analytics_router',
    'set_analytics_dependencies',
    'admin_router',
    'set_admin_dependencies',
    # Schemas
    'AgentTelephonySettingsUpdate',
    'ClickToDialRequest',
    'ClickToDialResponse',
    'StartSessionRequest',
    'StartSessionResponse',
    'SessionStatusResponse',
    'DispositionRequest',
    'DispositionResponse',
    'VerifyCallerIdRequest',
    'VerifyCallerIdResponse',
    'ComplianceCheckResponse',
    'CallLogEntry',
    'CallLogsResponse',
]
