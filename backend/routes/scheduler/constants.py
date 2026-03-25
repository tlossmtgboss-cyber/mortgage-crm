"""
Smart Calendar Constants
========================
Central source of truth for all scheduler durations, limits, and defaults.
"""

import os

# Duration defaults (minutes)
DEFAULT_APPOINTMENT_DURATION_MINUTES = 30
MIN_APPOINTMENT_DURATION_MINUTES = 5
MAX_APPOINTMENT_DURATION_MINUTES = 480
ALLOWED_APPOINTMENT_DURATIONS = [15, 30, 45, 60]

# Buffer times (minutes)
DEFAULT_BUFFER_BEFORE_MINUTES = 5
DEFAULT_BUFFER_AFTER_MINUTES = 5

# Timing windows
DEFAULT_MIN_NOTICE_HOURS = 2
DEFAULT_MAX_ADVANCE_DAYS = 60
SLOT_GENERATION_MAX_DAYS = 45

# Notification windows (hours)
NOTIFICATION_LOOKBACK_HOURS = 72
APPOINTMENT_REMINDER_WINDOW_MINUTES = 60
NOTIFICATION_RECENCY_HOURS = 24

# Rate limits
PUBLIC_BOOKING_RATE_LIMIT = 10
PUBLIC_SLOTS_RATE_LIMIT = 20
BOOKING_RATE_LIMIT_PER_EMAIL = 5
BOOKING_RATE_LIMIT_PER_IP = 5
DEMO_CREATE_RATE_LIMIT = 3

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
NOTIFICATION_FETCH_LIMIT = 50
MAX_BULK_OPERATION_SIZE = 50

# Reminder limits
MAX_REMINDERS_PER_APPOINTMENT = 10

# Hold TTL
DEFAULT_HOLD_TTL_SECONDS = 300  # 5 minutes

# Organizer email used in ICS generation, email templates, and calendar invites.
# Override via SCHEDULER_ORGANIZER_EMAIL environment variable.
DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", "sarah@reply.perenniaai.com")

# Timezone — override per deployment via SCHEDULER_DEFAULT_TIMEZONE env var.
# Individual users override this via SchedulerConfig.timezone.
DEFAULT_TIMEZONE = os.environ.get("SCHEDULER_DEFAULT_TIMEZONE", "America/Chicago")

# CAN-SPAM compliance: physical address required in all commercial emails.
# Override via CAN_SPAM_ADDRESS environment variable for white-label deployments.
CAN_SPAM_PHYSICAL_ADDRESS = os.environ.get(
    "CAN_SPAM_ADDRESS",
    "Perennia AI, 123 Main Street, Suite 100, Austin, TX 78701"
)

# NMLS-regulated states: LO must have NMLS number on file to book in these states.
# All US states require NMLS; this set tracks states with active enforcement.
NMLS_REGULATED_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
