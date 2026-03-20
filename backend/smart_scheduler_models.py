"""
Smart Scheduler Models - Perennia AI AI-Native Appointment Scheduling

BACKWARD-COMPATIBLE WRAPPER
============================
The actual SQLAlchemy model classes and enum definitions now live in:
    database/models/scheduler.py

This module remains as a thin wrapper to preserve backward compatibility for:
    - ``from smart_scheduler_models import create_smart_scheduler_models``
    - ``from smart_scheduler_models import AppointmentStatus, MeetingType, ...``
    - ``from smart_scheduler_models import Appointment, BookingLink, ...``
    - ``from smart_scheduler_models import DEFAULT_APPOINTMENT_TYPES, DEFAULT_WORKING_HOURS``

Enums, model classes, and constants are all re-exported from here so that the
100+ existing import sites across the codebase continue to work unchanged.
"""

# ============================================================================
# ENUM RE-EXPORTS (canonical definitions live in database/models/scheduler.py)
# ============================================================================

from database.models.scheduler import (
    # Enums
    AppointmentStatus,
    MeetingType,
    MeetingMode,
    RoutingStrategy,
    ReminderChannel,
    ReminderStatus,
    DayOfWeek,
    SlotPriority,
    SlotHoldStatus,
    # Model classes
    SchedulerConfig,
    AvailabilitySlot,
    SchedulerAppointmentType as AppointmentType,  # backward-compat alias
    Appointment,
    SchedulerRoutingRule as RoutingRule,            # backward-compat alias
    BlockedTime,
    BookingLink,
    AppointmentReminder,
    AppointmentStatusHistory,
    SchedulerAuditLog,
    SlotHold,
)


# ============================================================================
# FACTORY FUNCTION (backward-compatible wrapper)
# ============================================================================

def create_smart_scheduler_models(Base=None):
    """
    Return the scheduler model classes as a dict.

    The ``Base`` parameter is accepted for backward compatibility but is
    ignored -- the real classes already inherit from ``db.Base``.

    Returns a dict keyed by the original short names (e.g. 'AppointmentType',
    'RoutingRule') so that existing code like ``models['Appointment']`` keeps
    working.
    """
    models = {
        'SchedulerConfig': SchedulerConfig,
        'AvailabilitySlot': AvailabilitySlot,
        'AppointmentType': AppointmentType,
        'Appointment': Appointment,
        'RoutingRule': RoutingRule,
        'BlockedTime': BlockedTime,
        'BookingLink': BookingLink,
        'AppointmentReminder': AppointmentReminder,
        'AppointmentStatusHistory': AppointmentStatusHistory,
        'SchedulerAuditLog': SchedulerAuditLog,
        'SlotHold': SlotHold,
    }

    # Add newer models that live in their own files (lazy import to avoid
    # circular dependencies — these modules import from db.Base)
    try:
        from database.models.appointment_location import AppointmentLocation
        models['AppointmentLocation'] = AppointmentLocation
    except ImportError:
        pass
    try:
        from database.models.appointment_template import AppointmentTemplate
        models['AppointmentTemplate'] = AppointmentTemplate
    except ImportError:
        pass
    try:
        from database.models.calendar_event_map import CalendarEventMap
        models['CalendarEventMap'] = CalendarEventMap
    except ImportError:
        pass
    try:
        from database.models.calendar_label import CalendarLabel
        models['CalendarLabel'] = CalendarLabel
    except ImportError:
        pass

    return models


# Aliases for callers that use non-canonical names (latent typos in codebase)
create_scheduler_models = create_smart_scheduler_models
define_models = create_smart_scheduler_models
_define_models = create_smart_scheduler_models


# ============================================================================
# DEFAULT APPOINTMENT TYPES
# ============================================================================

DEFAULT_APPOINTMENT_TYPES = [
    {
        'type_key': 'discovery_call',
        'type_name': 'Discovery Call',
        'description': 'Initial conversation to understand your home buying goals',
        'meeting_type': MeetingType.DISCOVERY_CALL,
        'default_duration_minutes': 30,
        'allowed_durations': [15, 30],
        'requires_lead_id': False,
        'requires_loan_id': False,
        'intake_questions': [
            {'key': 'timeline', 'question': 'When are you looking to buy?', 'type': 'select', 'options': ['ASAP', '1-3 months', '3-6 months', '6+ months']},
            {'key': 'first_time', 'question': 'Is this your first home purchase?', 'type': 'boolean'},
            {'key': 'preapproved', 'question': 'Have you been pre-approved before?', 'type': 'boolean'}
        ],
        'color': '#3b82f6',
        'icon': 'phone'
    },
    {
        'type_key': 'pre_approval_review',
        'type_name': 'Pre-Approval Review',
        'description': 'Review your pre-approval letter and discuss next steps',
        'meeting_type': MeetingType.PRE_APPROVAL_REVIEW,
        'default_duration_minutes': 45,
        'allowed_durations': [30, 45, 60],
        'requires_lead_id': True,
        'requires_loan_id': False,
        'intake_questions': [
            {'key': 'price_range', 'question': 'What price range are you considering?', 'type': 'text'},
            {'key': 'down_payment', 'question': 'Estimated down payment amount?', 'type': 'text'}
        ],
        'color': '#8b5cf6',
        'icon': 'document'
    },
    {
        'type_key': 'application_walkthrough',
        'type_name': 'Application Walkthrough',
        'description': 'Step-by-step guidance through your mortgage application',
        'meeting_type': MeetingType.APPLICATION_WALKTHROUGH,
        'default_duration_minutes': 60,
        'allowed_durations': [45, 60, 90],
        'requires_lead_id': True,
        'requires_loan_id': False,
        'intake_questions': [
            {'key': 'employment_type', 'question': 'Employment type?', 'type': 'select', 'options': ['W-2 Employee', 'Self-Employed', 'Retired', 'Other']},
            {'key': 'documents_ready', 'question': 'Do you have tax returns and pay stubs ready?', 'type': 'boolean'}
        ],
        'color': '#10b981',
        'icon': 'clipboard'
    },
    {
        'type_key': 'document_review',
        'type_name': 'Document Review',
        'description': 'Review submitted documents and address any questions',
        'meeting_type': MeetingType.DOCUMENT_REVIEW,
        'default_duration_minutes': 30,
        'allowed_durations': [15, 30, 45],
        'requires_lead_id': False,
        'requires_loan_id': True,
        'intake_questions': [
            {'key': 'specific_docs', 'question': 'Which documents do you have questions about?', 'type': 'text'}
        ],
        'color': '#f59e0b',
        'icon': 'folder'
    },
    {
        'type_key': 'rate_lock_discussion',
        'type_name': 'Rate Lock Discussion',
        'description': 'Discuss current rates and lock strategy',
        'meeting_type': MeetingType.RATE_LOCK_DISCUSSION,
        'default_duration_minutes': 20,
        'allowed_durations': [15, 20, 30],
        'requires_lead_id': False,
        'requires_loan_id': True,
        'intake_questions': [
            {'key': 'closing_date', 'question': 'Expected closing date?', 'type': 'date'},
            {'key': 'rate_preference', 'question': 'Rate preference?', 'type': 'select', 'options': ['Lowest rate', 'Lowest payment', 'Balanced']}
        ],
        'color': '#ef4444',
        'icon': 'lock'
    },
    {
        'type_key': 'closing_prep',
        'type_name': 'Closing Preparation',
        'description': 'Final review before your closing day',
        'meeting_type': MeetingType.CLOSING_PREP,
        'default_duration_minutes': 45,
        'allowed_durations': [30, 45, 60],
        'requires_lead_id': False,
        'requires_loan_id': True,
        'intake_questions': [
            {'key': 'closing_date_confirmed', 'question': 'Is your closing date confirmed?', 'type': 'boolean'},
            {'key': 'questions', 'question': 'Any specific questions or concerns?', 'type': 'text'}
        ],
        'color': '#22c55e',
        'icon': 'home'
    },
    {
        'type_key': 'referral_partner',
        'type_name': 'Referral Partner Meeting',
        'description': 'Business development meeting with referral partners',
        'meeting_type': MeetingType.REFERRAL_PARTNER_MEETING,
        'default_duration_minutes': 30,
        'allowed_durations': [30, 45, 60],
        'requires_lead_id': False,
        'requires_loan_id': False,
        'intake_questions': [
            {'key': 'company', 'question': 'Company/Brokerage name?', 'type': 'text'},
            {'key': 'role', 'question': 'Your role?', 'type': 'text'},
            {'key': 'referral_volume', 'question': 'Estimated monthly referral volume?', 'type': 'select', 'options': ['1-5', '5-10', '10-20', '20+']}
        ],
        'color': '#ec4899',
        'icon': 'users'
    }
]


# ============================================================================
# DEFAULT WORKING HOURS
# ============================================================================

DEFAULT_WORKING_HOURS = {
    'monday': {'start': '09:00', 'end': '17:00', 'enabled': True},
    'tuesday': {'start': '09:00', 'end': '17:00', 'enabled': True},
    'wednesday': {'start': '09:00', 'end': '17:00', 'enabled': True},
    'thursday': {'start': '09:00', 'end': '17:00', 'enabled': True},
    'friday': {'start': '09:00', 'end': '17:00', 'enabled': True},
    'saturday': {'start': '10:00', 'end': '14:00', 'enabled': False},
    'sunday': {'start': '10:00', 'end': '14:00', 'enabled': False}
}
