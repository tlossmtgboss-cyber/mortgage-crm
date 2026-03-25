"""
Smart Calendar -- Scheduler Router Assembly
============================================

URL Prefix Map (all under /api/v1/scheduler):
----------------------------------------------

  /appointments/*               Appointment CRUD, cancel, timeline          (appointments.py)
  /availability/*               Slots CRUD, available-slots query           (availability.py)
  /availability/schedule        Recurring weekly patterns (GET/PUT)         (recurring_availability.py)
  /availability/exceptions/*    Date-specific overrides                     (recurring_availability.py)
  /availability/templates/*     Org availability templates                  (recurring_availability.py)
  /availability/effective       Merged effective schedule                   (recurring_availability.py)
  /available-slots              Authenticated slot query (POST)             (availability.py)
  /blocked-times/*              Block/unblock time ranges                   (blocked_times.py)
  /booking-links/*              Booking link CRUD + admin list              (booking_links.py)
  /public/book/{slug}/*         Public booking flow (no auth)               (public_booking.py)
  /public/available-slots       Public slot query (POST, rate-limited)      (public_booking.py)
  /public/book-demo/confirm     Demo booking confirmation                   (public_booking.py)
  /public/waitlist/*            Public waitlist join/accept/position         (waitlist.py)
  /public/surveys/respond/*     Public survey response flow                 (surveys.py)
  /public/reschedule/{token}/*  Borrower self-service reschedule            (reschedule.py)
  /ai-recommend-slots           AI-powered slot recommendations (POST)      (ai_scheduling.py)
  /analytics/overview           Calendar analytics overview                 (analytics.py)
  /analytics/trends             Booking trend data                          (analytics.py)
  /analytics/by-type            Breakdown by appointment type               (analytics.py)
  /analytics/by-lo              Breakdown by loan officer                   (analytics.py)
  /analytics/no-show-risks      Batch no-show risk for a date              (ai_scheduling.py)
  /meetings/*                   Virtual meeting provider settings/test      (meetings.py)
  /reminders/*                  Reminder templates, send log, test          (reminders.py)
  /waitlist/*                   Waitlist CRUD, offer, reorder, expire       (waitlist.py)
  /templates/*                  Appointment type templates CRUD             (templates.py)
  /feed/*                       iCal (.ics) feed subscription               (calendar_feed.py)
  /surveys/*                    Post-appointment survey send + results      (surveys.py)
  /reschedule/*                 LO-initiated reschedule + link generation   (reschedule.py)
  /notifications/*              Calendar notification feed + mark-read      (notifications.py)
  /locations/*                  Appointment location CRUD + default         (locations.py)
  /conflicts/*                  Conflict detection, listing, resolution     (conflicts.py)
  /cancellation-policy*         Cancellation policy CRUD + enforcement      (cancellation_policy.py)
  /cancel/{appointment_id}      Cancel with policy enforcement (POST)       (cancellation_policy.py)
  /cancellation-stats           Cancellation analytics                      (cancellation_policy.py)
  /data-export/{email}          GDPR data export for a borrower (admin)     (data_compliance.py)
  /data-delete/{email}          GDPR data deletion for a borrower (admin)   (data_compliance.py)
  /data-retention/report        Data retention status report (admin)         (data_compliance.py)
  /compliance/status            TCPA/DNC/contact-hours compliance dashboard (data_compliance.py)
  /compliance/opt-outs          Recent opt-out requests across channels     (data_compliance.py)
  /compliance/consent-audit     SMS consent coverage for scheduler contacts (data_compliance.py)
  /compliance/contact-hours-violations  Contact-hours violation detail      (data_compliance.py)
  /calendar/sync/google/webhook  Google Calendar push notification receiver   (calendar_sync_inbound.py)
  /calendar/sync/outlook/webhook Outlook/Graph change notification receiver  (calendar_sync_inbound.py)
  /calendar/sync/google/register Register Google Calendar watch channel      (calendar_sync_inbound.py)
  /calendar/sync/outlook/register Register Outlook Graph subscription        (calendar_sync_inbound.py)
  /booking-links/{id}/analytics  Per-link performance analytics             (booking_links.py)
  /booking-links/analytics/summary  Org-wide booking link analytics (admin) (booking_links.py)
  /settings/all                 Get all scheduler settings                  (settings.py)
  /settings/{section}           Update settings by section (PUT, admin)     (settings.py)

Active modules (23):
  appointments.py             Appointment CRUD, status transitions, timeline
  availability.py             Availability slots CRUD, authenticated available-slots
  recurring_availability.py   Recurring weekly patterns, date exceptions, org templates
  blocked_times.py            Blocked time CRUD (lunch breaks, OOO, capacity blocks)
  booking_links.py            Booking link CRUD endpoints
  public_booking.py           Public booking flow (no auth, rate-limited)
  ai_scheduling.py            AI slot recommendations, no-show risk scoring
  meetings.py                 Virtual meeting integration (Zoom, Google Meet, Teams, Perennia)
  reminders.py                Reminder template CRUD, send history, test endpoint
  waitlist.py                 Waiting room / queue management (authenticated + public)
  templates.py                Appointment template CRUD (pre-configured settings)
  calendar_feed.py            iCalendar (.ics) feed subscription (webcal://)
  surveys.py                  Post-appointment surveys (send, respond, aggregate results)
  reschedule.py               Appointment rescheduling (LO + borrower self-service)
  notifications.py            Calendar notification feed (bookings, cancellations, etc.)
  locations.py                Appointment location CRUD (offices, virtual links, phones)
  conflicts.py                Conflict detection, listing, and resolution
  cancellation_policy.py      Cancellation policy CRUD, enforcement, and analytics
  analytics.py                Calendar analytics dashboard (overview, trends, by-type, by-LO)
  data_compliance.py          GDPR/CCPA data export, deletion, retention + TCPA/DNC/contact-hours compliance (admin)
  calendar_sync_inbound.py   Bidirectional calendar sync (Google/Outlook inbound webhooks)
  settings.py                 Scheduler config CRUD (availability, notifications, etc.)
  error_responses.py          Standardized error response helpers (not a router, re-exported)

Internal helpers (not routers):
  _helpers.py                 Re-export layer for backward compatibility
  _core.py                    Dependency injection storage
  _auth.py                    Auth helpers (get_current_user, _get_org_id, _is_scheduler_admin)
  _rate_limiting.py           Rate limiting (Redis + in-memory fallback), IP extraction
  _input_validation.py        Input sanitization, URL/phone validation, Turnstile CAPTCHA
  _audit.py                   Audit logging
  _conflicts.py               Appointment conflict & duplicate booking detection
  _crm_integration.py         CRM helpers (lead creation, activity logging, tasks)
  _availability.py            Cross-source conflicts, timezone, unified slot engine

Removed modules:
  appointments_crud.py        Superseded by appointments + booking_links + ai_scheduling
  blocked_time.py             Superseded by blocked_times
  sitemap.py                  XML sitemap — unnecessary for mortgage vertical (deleted Mar 2026)
  outcome_tracking.py         Outcome analytics — premature feature (deleted Mar 2026)
  labels.py                   Calendar labels — low usage (deleted Mar 2026)
  search.py                   Appointment search — low usage (deleted Mar 2026)
  email_events.py             Email event tracking — low usage (deleted Mar 2026)
  booking_meta.py             Booking link SEO meta — unnecessary (deleted Mar 2026)
  widget_config.py            Widget configuration — low usage (deleted Mar 2026)
  maintenance.py              Maintenance utilities — low usage (deleted Mar 2026)
  today_summary.py            Today summary — low usage (deleted Mar 2026)
"""

from fastapi import APIRouter

from .middleware import (
    CURRENT_API_VERSION,
    SUPPORTED_API_VERSIONS,
    ENDPOINT_VERSIONS,
)
from .appointments import router as appointments_router
from .availability import router as availability_router
from .blocked_times import router as blocked_times_router
from .booking_links import router as booking_links_router
from .public_booking import router as public_booking_router
from .ai_scheduling import router as ai_scheduling_router
from .meetings import router as meetings_router
from .reminders import router as reminders_router
from .waitlist import router as waitlist_router
from .recurring_availability import router as recurring_availability_router
from .templates import router as templates_router
from .calendar_feed import router as calendar_feed_router
from .surveys import router as surveys_router
from .reschedule import router as reschedule_router
from .notifications import router as notifications_router
from .locations import router as locations_router
from .conflicts import router as conflicts_router
from .cancellation_policy import router as cancellation_policy_router
from .analytics import router as analytics_router
from .data_compliance import router as data_compliance_router
from .bulk_operations import router as bulk_operations_router
from .compliance_scheduling import router as compliance_scheduling_router
from .health import router as health_router
from .metrics import router as metrics_router
from .sla import router as sla_router
from .webhooks import router as webhooks_router
from .calendar_sync_inbound import router as calendar_sync_inbound_router
from .confirmation import router as confirmation_router
from .settings import router as settings_router
from .error_responses import (  # noqa: F401 — re-export for other modules
    scheduler_error, validation_error, not_found_error,
    conflict_error, rate_limit_error, internal_error,
    forbidden_error, unauthorized_error, service_unavailable_error,
)

# ============================================================================
# API VERSION INTROSPECTION ENDPOINT
# ============================================================================

_api_versions_router = APIRouter()


@_api_versions_router.get("/api-versions")
async def get_api_versions():
    """Return the scheduler API version registry.

    Useful for API consumers to discover which endpoints exist, when they
    were introduced, and which API version is currently active.
    """
    return {
        "current_version": CURRENT_API_VERSION,
        "supported_versions": SUPPORTED_API_VERSIONS,
        "endpoints": ENDPOINT_VERSIONS,
    }


# ============================================================================
# ROUTER ASSEMBLY
# ============================================================================

scheduler_router = APIRouter()
scheduler_router.include_router(appointments_router)
scheduler_router.include_router(availability_router)
scheduler_router.include_router(blocked_times_router)
scheduler_router.include_router(booking_links_router)
scheduler_router.include_router(public_booking_router)
scheduler_router.include_router(ai_scheduling_router)
scheduler_router.include_router(meetings_router)
scheduler_router.include_router(reminders_router)
scheduler_router.include_router(waitlist_router)
scheduler_router.include_router(recurring_availability_router)
scheduler_router.include_router(templates_router)
scheduler_router.include_router(calendar_feed_router)
scheduler_router.include_router(surveys_router)
scheduler_router.include_router(reschedule_router)
scheduler_router.include_router(notifications_router)
scheduler_router.include_router(locations_router)
scheduler_router.include_router(conflicts_router)
scheduler_router.include_router(cancellation_policy_router)
scheduler_router.include_router(analytics_router)
scheduler_router.include_router(data_compliance_router)
scheduler_router.include_router(bulk_operations_router)
scheduler_router.include_router(compliance_scheduling_router)
scheduler_router.include_router(health_router)
scheduler_router.include_router(metrics_router)
scheduler_router.include_router(sla_router)
scheduler_router.include_router(webhooks_router)
scheduler_router.include_router(calendar_sync_inbound_router)
scheduler_router.include_router(confirmation_router)
scheduler_router.include_router(settings_router)
scheduler_router.include_router(_api_versions_router)
