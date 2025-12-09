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
from .notification_service import NotificationService, notification_service
from .scheduler_service import SchedulerService, scheduler_service, init_scheduler

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
    # Notification Service
    'NotificationService',
    'notification_service',
    # Scheduler Service
    'SchedulerService',
    'scheduler_service',
    'init_scheduler',
]
