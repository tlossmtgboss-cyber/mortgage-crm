"""
API V2 Routes - Perennia AI

Aggregator for all V2 endpoints.  All routes under this package are
served at ``/api/v2/`` prefix.

V2 Improvements Over V1
-----------------------
- Consistent response envelope (``V2Envelope``)
- Cursor-based pagination (no offset drift)
- Sparse fieldsets (``?fields=id,title,start_time``)
- Related resource inclusion (``?include=attendees,meeting``)
- RFC 7807 Problem Details for all errors
- ISO 8601 datetimes with mandatory timezone offsets

Version Negotiation
-------------------
Clients may select V2 via:
1. URL path prefix:  ``GET /api/v2/scheduler/appointments``
2. Accept header:    ``Accept: application/vnd.perennia.v2+json``
"""

from fastapi import APIRouter

from routes.api_v2.scheduler_v2 import router as scheduler_v2_router

router = APIRouter(prefix="/api/v2", tags=["API V2"])

router.include_router(scheduler_v2_router)
