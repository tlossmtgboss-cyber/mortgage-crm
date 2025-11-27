# Telephony module for Click-to-Dial and Power Dialer
from .provider import TelephonyProvider, TwilioProvider, get_telephony_provider, TelephonyError, CallResult, CallStatus
from .dialer_engine import DialerEngine, click_to_dial
from .compliance import ComplianceChecker, ComplianceError
from .websocket import ws_manager, WebSocketManager, DialerEvent

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
    'TwilioProvider',
    'get_telephony_provider',
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
