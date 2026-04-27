"""
Perennia AI — URLA 1003 Voice Agent
===================================

Dedicated LiveKit-based voice agent for intake of the full Uniform Residential
Loan Application (Fannie Mae Form 1003 / Freddie Mac Form 65, 2021 redesigned).

Public API:
    URLAAgent              — LiveKit Agent class with section tools
    URLAStateManager       — Redis state persistence
    URLAApplication        — Pydantic model for the full application
    LOKickoffBooking       — Post-finalize calendar booking record
    push_to_bytepro        — BytePro LOS integration
    fetch_available_slots  — Smart Calendar availability lookup
    book_slot              — Smart Calendar booking
    urla_entrypoint        — LiveKit worker entrypoint
"""
from .agent import URLAAgent
from .state import URLAStateManager
from .models import URLAApplication, Borrower, LOKickoffBooking
from .bytepro_adapter import push_to_bytepro, LoanOfficer, PushResult
from .smart_calendar_adapter import (
    fetch_available_slots,
    book_slot,
    AvailableSlot,
    BookingResult,
    SmartCalendarConfig,
)
try:
    from .entrypoint import urla_entrypoint
except ImportError:
    pass

try:
    from .ci_adapter import run_ci_pipeline, trigger_ci_analysis, URLACIResult
except ImportError:
    pass

try:
    from .call_intelligence import analyze_call, trigger_post_finalize_analysis, URLACallIntelligenceResult
except ImportError:
    pass

try:
    from .call_scoring import score_urla_call, URLACallScore, ComplianceFlag
except ImportError:
    pass

try:
    from .lo_briefing import generate_lo_briefing, generate_enhanced_briefing, LOBriefing
except ImportError:
    pass

try:
    from .task_generator import generate_urla_tasks, URLATask
except ImportError:
    pass

try:
    from .call_analytics import compute_analytics, URLACallMetrics
except ImportError:
    pass

try:
    from .sanitizer import sanitize_text, sanitize_name, sanitize_address, sanitize_description
except ImportError:
    pass

try:
    from .mismo_serializer import serialize_to_mismo34, serialize_to_mismo34_bytes
except ImportError:
    pass

__all__ = [
    "URLAAgent",
    "URLAStateManager",
    "URLAApplication",
    "Borrower",
    "LOKickoffBooking",
    "push_to_bytepro",
    "LoanOfficer",
    "PushResult",
    "fetch_available_slots",
    "book_slot",
    "AvailableSlot",
    "BookingResult",
    "SmartCalendarConfig",
    "urla_entrypoint",
    # CI Pipeline Integration
    "run_ci_pipeline",
    "trigger_ci_analysis",
    "URLACIResult",
    # Call Intelligence (supplementary)
    "analyze_call",
    "trigger_post_finalize_analysis",
    "URLACallIntelligenceResult",
    "score_urla_call",
    "URLACallScore",
    "ComplianceFlag",
    "generate_lo_briefing",
    "generate_enhanced_briefing",
    "LOBriefing",
    "generate_urla_tasks",
    "URLATask",
    "compute_analytics",
    "URLACallMetrics",
    # Sanitizer
    "sanitize_text",
    "sanitize_name",
    "sanitize_address",
    "sanitize_description",
    # MISMO 3.4 Serializer
    "serialize_to_mismo34",
    "serialize_to_mismo34_bytes",
]
