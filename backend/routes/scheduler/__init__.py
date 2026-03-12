"""
Scheduler sub-package: focused route modules for the appointment scheduling system.

Modules:
  - _helpers:        Shared helpers (auth, rate limiting, sanitization, conflict detection, CRM, slot engine)
  - appointments:    Appointment CRUD, status transitions, timeline
  - availability:    Availability slots CRUD, authenticated available-slots endpoint
  - blocked_times:   Blocked time CRUD (lunch breaks, OOO, capacity blocks)
  - booking_links:   Booking link CRUD endpoints
  - public_booking:  Public booking endpoints (no auth required, rate-limited)
  - ai_scheduling:   AI slot recommendations, no-show risk scoring
  - email_testing:   Email service status and test endpoints
  - search:          Advanced appointment search with full-text, filters, pagination
  - meetings:        Virtual meeting integration (Zoom, Google Meet, Teams, Perennia Meet)
  - reminders:       Reminder template CRUD, send history, test endpoint
  - booking_meta:    SEO meta endpoint for booking link previews (public, no auth)
  - sitemap:         XML sitemap and robots.txt for search engine discovery (public)
  - waitlist:        Waiting room / queue management (authenticated + public)
  - recurring_availability: Recurring weekly patterns, date exceptions, org templates

Superseded modules (kept for backward compat, not included in scheduler_router):
  - appointments_crud: Original combined module (superseded by appointments + booking_links + ai_scheduling)
  - blocked_time:      Original blocked time module (superseded by blocked_times)
"""

from fastapi import APIRouter

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
