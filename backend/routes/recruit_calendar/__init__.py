"""
Recruit Calendar — standalone recruiting scheduling platform.

Prefix: /api/v1/recruit-calendar

Hybrid design: reuses scheduler_appointments + scheduler_booking_links
for all scheduling mechanics (availability, conflict detection, booking
links, reminders). Recruiting-specific metadata (candidate_id, interview
type, outcome, scorecard) lives in recruit_interview_details (1:1 FK).

Sub-routers:
  interviews.py   — Interview CRUD, calendar view, complete endpoint
  milestones.py   — Post-hire milestones (start date, 30/90-day check-ins)
  booking.py      — Candidate-facing booking links (no-auth public endpoints)
  availability.py — Recruiter slot availability (wraps scheduler slot engine)
"""
from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from routes.recruit_calendar import interviews, milestones, booking, availability

router = APIRouter(
    prefix="/api/v1/recruit-calendar",
    tags=["Recruit Calendar"],
    dependencies=[Depends(get_current_user)],
)

router.include_router(interviews.router, prefix="/interviews")
router.include_router(milestones.router, prefix="/milestones")
router.include_router(availability.router, prefix="/availability")

# Booking has mixed auth (some public endpoints) — include without global auth dep
public_router = APIRouter(
    prefix="/api/v1/recruit-calendar",
    tags=["Recruit Calendar"],
)
public_router.include_router(booking.router, prefix="/booking")

__all__ = ["router", "public_router"]
