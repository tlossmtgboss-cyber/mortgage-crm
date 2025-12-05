"""
Services Package
Business logic and processing services
"""

from .email_processor import EmailProcessor, get_email_processor
from .microsoft_graph import (
    MicrosoftGraphUserService,
    EmailParams,
    CalendarEventParams,
    EmailResult,
    CalendarResult,
    send_email_via_graph,
    create_event_via_graph,
    get_user_availability,
)

__all__ = [
    'EmailProcessor',
    'get_email_processor',
    # Microsoft Graph User-Delegated Service
    'MicrosoftGraphUserService',
    'EmailParams',
    'CalendarEventParams',
    'EmailResult',
    'CalendarResult',
    'send_email_via_graph',
    'create_event_via_graph',
    'get_user_availability',
]
