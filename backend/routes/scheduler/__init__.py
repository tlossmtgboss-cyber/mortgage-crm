"""
Scheduler sub-package: extracted route modules for the scheduler.

Modules:
  - appointments_crud: Appointment CRUD, status transitions, booking links, AI recommendations
  - blocked_time: Blocked time CRUD (lunch breaks, OOO, capacity blocks)
  - booking_links: Booking link CRUD endpoints (superseded by appointments_crud)
  - blocked_times: Blocked time CRUD endpoints (superseded by blocked_time)
  - availability: Availability slots, conflict detection, slot generation engine
  - public_booking: Public booking endpoints (no auth required, rate-limited)
"""
