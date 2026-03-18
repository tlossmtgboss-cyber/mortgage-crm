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
  /public/booking/{slug}/meta*  SEO meta / Open Graph for booking pages     (booking_meta.py)
  /public/waitlist/*            Public waitlist join/accept/position         (waitlist.py)
  /public/surveys/respond/*     Public survey response flow                 (surveys.py)
  /public/reschedule/{token}/*  Borrower self-service reschedule            (reschedule.py)
  /public/ab-tests/*            A/B test variant assignment + recording     (ab_testing.py)
  /ai-recommend-slots           AI-powered slot recommendations (POST)      (ai_scheduling.py)
  /analytics/overview           Calendar analytics overview                 (analytics.py)
  /analytics/trends             Booking trend data                          (analytics.py)
  /analytics/by-type            Breakdown by appointment type               (analytics.py)
  /analytics/by-lo              Breakdown by loan officer                   (analytics.py)
  /analytics/no-show-risks      Batch no-show risk for a date              (ai_scheduling.py)
  /analytics/appointment-outcomes       AI vs manual appointment funding conversion  (outcome_tracking.py)
  /analytics/appointment-type-effectiveness  Conversion by appointment type        (outcome_tracking.py)
  /analytics/lo-outcome-comparison      Per-LO appointment outcome breakdown     (outcome_tracking.py)
  /analytics/outcome-timeline           Time-series of appointment outcomes      (outcome_tracking.py)
  /today-summary                Aggregated LO "Today" dashboard summary    (today_summary.py)
  /search                       Full-text appointment search                (search.py)
  /search/suggestions           Search autocomplete suggestions             (search.py)
  /meetings/*                   Virtual meeting provider settings/test      (meetings.py)
  /reminders/*                  Reminder templates, send log, test          (reminders.py)
  /waitlist/*                   Waitlist CRUD, offer, reorder, expire       (waitlist.py)
  /templates/*                  Appointment type templates CRUD             (templates.py)
  /feed/*                       iCal (.ics) feed subscription               (calendar_feed.py)
  /surveys/*                    Post-appointment survey send + results      (surveys.py)
  /labels/*                     Calendar color labels CRUD + assignment     (labels.py)
  /reschedule/*                 LO-initiated reschedule + link generation   (reschedule.py)
  /notifications/*              Calendar notification feed + mark-read      (notifications.py)
  /locations/*                  Appointment location CRUD + default         (locations.py)
  /conflicts/*                  Conflict detection, listing, resolution     (conflicts.py)
  /ab-tests/*                   A/B test CRUD + results                     (ab_testing.py)
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
  /pipeline-triggers/failures   List pipeline trigger failures for LO       (trigger_failures.py)
  /pipeline-triggers/failures/{id}/acknowledge  Acknowledge a failure       (trigger_failures.py)
  /email-service-status         Email service health check                  (email_testing.py)
  /test-email                   Send test email (POST)                      (email_testing.py)
  /maintenance/cleanup-holds    Delete expired SlotHold records (admin)     (maintenance.py)
  /sitemap.xml                  XML sitemap for search engines              (sitemap.py)
  /robots.txt                   Robots.txt for crawler control              (sitemap.py)

Active modules (30):
  appointments.py             Appointment CRUD, status transitions, timeline
  availability.py             Availability slots CRUD, authenticated available-slots
  recurring_availability.py   Recurring weekly patterns, date exceptions, org templates
  blocked_times.py            Blocked time CRUD (lunch breaks, OOO, capacity blocks)
  booking_links.py            Booking link CRUD endpoints
  public_booking.py           Public booking flow (no auth, rate-limited)
  ai_scheduling.py            AI slot recommendations, no-show risk scoring
  email_testing.py            Email service status and test endpoints
  search.py                   Advanced appointment search with full-text, filters, pagination
  meetings.py                 Virtual meeting integration (Zoom, Google Meet, Teams, Perennia)
  reminders.py                Reminder template CRUD, send history, test endpoint
  booking_meta.py             SEO meta endpoint for booking link previews (public)
  sitemap.py                  XML sitemap and robots.txt for search engines (public)
  waitlist.py                 Waiting room / queue management (authenticated + public)
  templates.py                Appointment template CRUD (pre-configured settings)
  calendar_feed.py            iCalendar (.ics) feed subscription (webcal://)
  surveys.py                  Post-appointment surveys (send, respond, aggregate results)
  labels.py                   Calendar color labels CRUD, assign/unassign to appointments
  reschedule.py               Appointment rescheduling (LO + borrower self-service)
  notifications.py            Calendar notification feed (bookings, cancellations, etc.)
  locations.py                Appointment location CRUD (offices, virtual links, phones)
  conflicts.py                Conflict detection, listing, and resolution
  ab_testing.py               A/B testing for public booking page optimization
  cancellation_policy.py      Cancellation policy CRUD, enforcement, and analytics
  analytics.py                Calendar analytics dashboard (overview, trends, by-type, by-LO)
  outcome_tracking.py         Appointment-to-funding conversion analytics (AI vs manual, by-type, by-LO, timeline)
  today_summary.py            Aggregated LO "Today" dashboard (appointments, tasks, leads, SLA)
  data_compliance.py          GDPR/CCPA data export, deletion, retention + TCPA/DNC/contact-hours compliance (admin)
  maintenance.py              Periodic cleanup tasks (expired slot holds)
  calendar_sync_inbound.py   Bidirectional calendar sync (Google/Outlook inbound webhooks)
  trigger_failures.py         Pipeline trigger failure viewing and acknowledgment

Internal helpers (not a router):
  _helpers.py                 Shared auth, rate limiting, sanitization, conflict detection, CRM, slot engine

Removed modules (deleted after decomposition):
  appointments_crud.py        Superseded by appointments + booking_links + ai_scheduling (deleted)
  blocked_time.py             Superseded by blocked_times (deleted)
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
from .email_testing import router as email_testing_router
from .search import router as search_router
from .meetings import router as meetings_router
from .booking_meta import router as booking_meta_router
from .sitemap import router as sitemap_router
from .reminders import router as reminders_router
from .waitlist import router as waitlist_router
from .recurring_availability import router as recurring_availability_router
from .templates import router as templates_router
from .calendar_feed import router as calendar_feed_router
from .surveys import router as surveys_router
from .labels import router as labels_router
from .reschedule import router as reschedule_router
from .notifications import router as notifications_router
from .locations import router as locations_router
from .conflicts import router as conflicts_router
from .ab_testing import router as ab_testing_router
from .cancellation_policy import router as cancellation_policy_router
from .analytics import router as analytics_router
from .outcome_tracking import router as outcome_tracking_router
from .today_summary import router as today_summary_router
from .data_compliance import router as data_compliance_router
from .bulk_operations import router as bulk_operations_router
from .compliance_scheduling import router as compliance_scheduling_router
from .health import router as health_router
from .metrics import router as metrics_router
from .sla import router as sla_router
from .webhooks import router as webhooks_router
from .widget_config import router as widget_config_router
from .maintenance import router as maintenance_router
from .calendar_sync_inbound import router as calendar_sync_inbound_router
from .trigger_failures import router as trigger_failures_router

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
scheduler_router.include_router(email_testing_router)
scheduler_router.include_router(search_router)
scheduler_router.include_router(meetings_router)
scheduler_router.include_router(booking_meta_router)
scheduler_router.include_router(sitemap_router)
scheduler_router.include_router(reminders_router)
scheduler_router.include_router(waitlist_router)
scheduler_router.include_router(recurring_availability_router)
scheduler_router.include_router(templates_router)
scheduler_router.include_router(calendar_feed_router)
scheduler_router.include_router(surveys_router)
scheduler_router.include_router(labels_router)
scheduler_router.include_router(reschedule_router)
scheduler_router.include_router(notifications_router)
scheduler_router.include_router(locations_router)
scheduler_router.include_router(conflicts_router)
scheduler_router.include_router(ab_testing_router)
scheduler_router.include_router(cancellation_policy_router)
scheduler_router.include_router(analytics_router)
scheduler_router.include_router(outcome_tracking_router)
scheduler_router.include_router(today_summary_router)
scheduler_router.include_router(data_compliance_router)
scheduler_router.include_router(bulk_operations_router)
scheduler_router.include_router(compliance_scheduling_router)
scheduler_router.include_router(health_router)
scheduler_router.include_router(metrics_router)
scheduler_router.include_router(sla_router)
scheduler_router.include_router(webhooks_router)
scheduler_router.include_router(widget_config_router)
scheduler_router.include_router(maintenance_router)
scheduler_router.include_router(calendar_sync_inbound_router)
scheduler_router.include_router(trigger_failures_router)
scheduler_router.include_router(_api_versions_router)
