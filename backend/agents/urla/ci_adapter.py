"""
URLA → Call Intelligence Pipeline Adapter
==========================================
Thin adapter that converts a finalized URLAApplication + transcript into a
CallIntelligenceRequest and fires it through the existing CI pipeline.

This is the publisher that fires from the URLA agent's session shutdown callback.
The URLA side stays thin — most of the work belongs in the existing pipeline.

Flow:
    1. URLA voice call finalizes → entrypoint calls trigger_ci_analysis()
    2. This adapter flattens URLAApplication into captured_structured_data
    3. Creates a CallIntelligenceRequest with call_type=URLA_INTAKE
    4. Feeds it to CallIntelligenceProcessor.process_transcript()
    5. Runs StructuredDiffComparator on results vs captured data
    6. Agreements → auto-approved. Disagreements → review queue.
    7. Creates VoiceCallSession + CallDisposition records in Postgres.
    8. Returns URlaCIResult with the full analysis.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .models import URLAApplication

logger = logging.getLogger(__name__)


@dataclass
class URLACIResult:
    """Result of running CI pipeline on a URLA voice call."""
    loan_id: str
    tenant_id: str
    call_id: str
    success: bool = True
    extraction_count: int = 0
    agreement_count: int = 0
    disagreement_count: int = 0
    extraction_only_count: int = 0
    review_items_queued: int = 0
    auto_approved_count: int = 0
    processing_time_ms: int = 0
    voice_session_id: Optional[str] = None
    diff_report: Optional[Dict[str, Any]] = None
    ci_response: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "tenant_id": self.tenant_id,
            "call_id": self.call_id,
            "success": self.success,
            "extraction_count": self.extraction_count,
            "agreement_count": self.agreement_count,
            "disagreement_count": self.disagreement_count,
            "extraction_only_count": self.extraction_only_count,
            "review_items_queued": self.review_items_queued,
            "auto_approved_count": self.auto_approved_count,
            "processing_time_ms": self.processing_time_ms,
            "voice_session_id": self.voice_session_id,
            "diff_report": self.diff_report,
            "errors": self.errors,
        }


# ── Public API ────────────────────────────────────────────────────────

async def run_ci_pipeline(
    app: URLAApplication,
    tenant_id: str,
    db_session: Optional["Session"] = None,
) -> URLACIResult:
    """
    Run the full CI pipeline on a finalized URLA application.

    Args:
        app: The finalized URLAApplication with transcript entries
        tenant_id: Organization/tenant identifier
        db_session: Optional SQLAlchemy session for DB persistence

    Returns:
        URLACIResult with analysis details
    """
    import time
    start = time.time()

    call_id = f"urla-{app.loan_id}-{uuid.uuid4().hex[:8]}"
    result = URLACIResult(
        loan_id=app.loan_id,
        tenant_id=tenant_id,
        call_id=call_id,
    )

    try:
        # 1. Build transcript text from URLA call entries
        transcript_text = _build_transcript_text(app)
        if not transcript_text:
            result.errors.append("No transcript data available")
            result.success = False
            return result

        # 2. Flatten URLA application into captured_structured_data
        captured = flatten_urla_application(app)

        # 3. Create CI request
        from services.call_intelligence.data_contracts import (
            CallIntelligenceRequest,
            CallType,
        )

        # CRITICAL: existing_borrower_data must be EMPTY for URLA calls.
        # The extraction agents must see only the transcript — no captured
        # values — to guarantee independence of the two extraction paths.
        # captured_structured_data is used ONLY by the diff comparator.
        ci_request = CallIntelligenceRequest(
            call_id=call_id,
            organization_id=_parse_org_id(tenant_id),
            transcript=transcript_text,
            call_type=CallType.URLA_INTAKE,
            call_duration_seconds=_estimate_duration(app),
            call_timestamp=app.created_at,
            captured_structured_data=captured,
            existing_borrower_data={},
        )

        # 4. Run CI processor
        from services.call_intelligence.processor import CallIntelligenceProcessor
        processor = CallIntelligenceProcessor(
            db_session=db_session,
            use_unified=True,
        )
        ci_response = await processor.process_transcript(ci_request)

        result.extraction_count = ci_response.total_extractions
        result.ci_response = ci_response.to_dict()

        # 5. Run structured diff comparator
        from services.call_intelligence.structured_diff import StructuredDiffComparator
        comparator = StructuredDiffComparator()
        diff = comparator.compare(
            call_id=call_id,
            captured=captured,
            response=ci_response,
        )

        result.agreement_count = len(diff.agreements)
        result.disagreement_count = len(diff.disagreements)
        result.extraction_only_count = len(diff.extraction_only)
        result.diff_report = diff.to_dict()

        # 6. Route to review queue
        if diff.needs_review and db_session:
            review_items = comparator.to_review_queue_items(diff)
            try:
                from services.call_intelligence.review_service import HumanReviewService
                review_svc = HumanReviewService(db_session)
                for item in review_items:
                    await review_svc._save_review_item(item)
                result.review_items_queued = len(review_items)
            except Exception as e:
                logger.warning("Failed to queue review items: %s", e)
                result.errors.append(f"Review queue: {e}")

        result.auto_approved_count = len(diff.agreements)

        # 7. Create VoiceCallSession record
        if db_session:
            result.voice_session_id = await _create_voice_session(
                db_session, app, call_id, tenant_id, ci_response,
            )

        result.success = True

    except ImportError as e:
        logger.warning("CI pipeline import failed (module not available): %s", e)
        result.errors.append(f"Import error: {e}")
        result.success = False

    except Exception as e:
        logger.exception("CI pipeline failed for %s", app.loan_id)
        result.errors.append(str(e))
        result.success = False

    result.processing_time_ms = int((time.time() - start) * 1000)

    logger.info(
        "URLA CI pipeline complete for %s: %d extractions, %d agree, "
        "%d disagree, %d extraction-only, %d queued for review (%dms)",
        app.loan_id,
        result.extraction_count,
        result.agreement_count,
        result.disagreement_count,
        result.extraction_only_count,
        result.review_items_queued,
        result.processing_time_ms,
    )
    return result


def trigger_ci_analysis(app: URLAApplication, tenant_id: str) -> None:
    """
    Fire-and-forget trigger for CI analysis. Called from finalize_urla.
    Creates a background asyncio.Task.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run_ci_background(app, tenant_id))
        logger.info("CI pipeline triggered for %s", app.loan_id)
    except RuntimeError:
        logger.warning("No event loop — CI pipeline not triggered for %s", app.loan_id)


async def _run_ci_background(app: URLAApplication, tenant_id: str) -> None:
    """Background wrapper with error isolation."""
    try:
        result = await run_ci_pipeline(app, tenant_id)
        if not result.success:
            logger.warning(
                "CI pipeline completed with errors for %s: %s",
                app.loan_id, result.errors,
            )
    except Exception as e:
        logger.exception("CI background task failed for %s", app.loan_id)


# ── Flattening ────────────────────────────────────���───────────────────

def flatten_urla_application(app: URLAApplication) -> Dict[str, Any]:
    """
    Flatten a URLAApplication into a dot-notation dict matching the
    CI extraction field names via the FIELD_MAP in structured_diff.py.
    """
    data: Dict[str, Any] = {}

    # Section 1a — Primary borrower
    if app.borrowers:
        b = app.borrowers[0]
        s1a = b.section_1a
        if s1a:
            _set(data, "borrower.first_name", s1a.first_name)
            _set(data, "borrower.last_name", s1a.last_name)
            _set(data, "borrower.middle_name", s1a.middle_name)
            _set(data, "borrower.suffix", s1a.suffix)
            if s1a.ssn:
                _set(data, "borrower.ssn_last_four", s1a.ssn[-4:] if len(s1a.ssn) >= 4 else None)
            _set(data, "borrower.date_of_birth", _date_str(s1a.date_of_birth))
            _set(data, "borrower.email", s1a.email)
            _set(data, "borrower.phone", s1a.cell_phone)
            _set(data, "borrower.marital_status", _enum_val(s1a.marital_status))
            _set(data, "borrower.citizenship_status", _enum_val(s1a.citizenship))

        # Employment
        s1b = b.section_1b
        if s1b:
            _set(data, "borrower.employer_name", s1b.employer_name)
            _set(data, "borrower.position", s1b.position_title)
            _set(data, "borrower.self_employed", s1b.self_employed)
            _set(data, "borrower.years_at_job", s1b.years_in_profession)
            income_parts = [
                s1b.base_monthly, s1b.overtime_monthly, s1b.bonus_monthly,
                s1b.commission_monthly, s1b.military_entitlements_monthly,
                s1b.other_monthly,
            ]
            total_monthly = sum(float(p) for p in income_parts if p is not None)
            if total_monthly > 0:
                _set(data, "borrower.monthly_income", total_monthly)
                _set(data, "borrower.monthly_income_total", total_monthly * 12)

    # Section 4 — Loan and property
    if app.section_4:
        s4 = app.section_4
        if s4.section_4a:
            s4a = s4.section_4a
            _set(data, "section_4.loan_amount", _decimal_float(s4a.loan_amount))
            _set(data, "section_4.loan_purpose", _enum_val(s4a.loan_purpose))
            _set(data, "section_4.property_value", _decimal_float(s4a.property_value))
            _set(data, "section_4.number_of_units", s4a.number_of_units)
            _set(data, "section_4.occupancy", _enum_val(s4a.occupancy))
            if s4a.subject_property_address:
                addr = s4a.subject_property_address
                _set(data, "section_4.subject_property_address.street", addr.street)
                _set(data, "section_4.subject_property_address.city", addr.city)
                _set(data, "section_4.subject_property_address.state", addr.state)
                _set(data, "section_4.subject_property_address.zip_code", addr.zip_code)

    # Section 5 — Declarations (per-borrower)
    if app.borrowers:
        b = app.borrowers[0]
        if b.section_5:
            s5a = b.section_5.section_5a
            if s5a:
                _set(data, "section_5.ownership_interest_last_3_years", s5a.had_ownership_interest_last_3_years)
                _set(data, "section_5.borrowed_down_payment", s5a.borrowing_money_for_transaction)
            s5b = b.section_5.section_5b
            if s5b:
                _set(data, "section_5.bankruptcy", s5b.declared_bankruptcy_last_7_years)
                _set(data, "section_5.foreclosure", s5b.foreclosed_last_7_years)
                _set(data, "section_5.outstanding_judgments", s5b.outstanding_judgments)
                _set(data, "section_5.party_to_lawsuit", s5b.party_to_lawsuit)
                _set(data, "section_5.federal_debt_delinquent", s5b.currently_delinquent_on_federal_debt)
                _set(data, "section_5.co_maker_endorser", s5b.co_signer_on_undisclosed_debt)
                _set(data, "section_5.delinquent_on_any_debt", s5b.currently_delinquent_on_federal_debt)

    # Section 7 — Military (per-borrower)
    if app.borrowers:
        b = app.borrowers[0]
        if b.section_7:
            s7 = b.section_7
            _set(data, "section_7.is_veteran", s7.served_in_military)

    # Section 8 — Demographics (voluntary — not extracted from transcript)
    # Intentionally omitted: ECOA/Reg B prohibits using demographics in
    # lending decisions, and extracting them from voice is an ECOA risk.

    return {k: v for k, v in data.items() if v is not None}


def _build_transcript_text(app: URLAApplication) -> str:
    """Build a speaker-attributed transcript string from call entries."""
    if not app.transcript:
        return ""

    lines = []
    for entry in app.transcript:
        speaker = getattr(entry, "speaker", "unknown")
        text = getattr(entry, "text", "")
        if text:
            if speaker in ("agent", "ai", "assistant"):
                lines.append(f"Loan Officer: {text}")
            elif speaker in ("user", "borrower", "caller"):
                lines.append(f"Borrower: {text}")
            else:
                lines.append(f"{speaker}: {text}")

    return "\n".join(lines)


def _estimate_duration(app: URLAApplication) -> int:
    """Estimate call duration from timestamps."""
    if app.created_at and app.updated_at:
        delta = app.updated_at - app.created_at
        return max(0, int(delta.total_seconds()))
    return 0


async def _create_voice_session(
    db_session: "Session",
    app: URLAApplication,
    call_id: str,
    tenant_id: str,
    ci_response: Any,
) -> Optional[str]:
    """Create a VoiceCallSession record for this URLA call."""
    try:
        from sqlalchemy import text
        session_uuid = f"urla-{call_id}"

        db_session.execute(
            text("""
                INSERT INTO voice_call_sessions
                (session_uuid, organization_id, user_id, direction, status,
                 started_at, ended_at, duration_seconds, summary, sentiment,
                 outcome, stt_provider, tts_provider, created_at)
                VALUES
                (:session_uuid, :org_id, :user_id, 'inbound', 'completed',
                 :started_at, :ended_at, :duration, :summary, 'neutral',
                 'action_taken', 'deepgram', 'cartesia', :created_at)
                ON CONFLICT (session_uuid) DO NOTHING
            """),
            {
                "session_uuid": session_uuid,
                "org_id": _parse_org_id(tenant_id),
                "user_id": _parse_org_id(tenant_id),
                "started_at": app.created_at,
                "ended_at": app.updated_at or datetime.now(timezone.utc),
                "duration": _estimate_duration(app),
                "summary": f"URLA 1003 voice intake: {app.loan_id}",
                "created_at": datetime.now(timezone.utc),
            },
        )
        db_session.commit()
        return session_uuid

    except Exception as e:
        logger.warning("Failed to create VoiceCallSession: %s", e)
        try:
            db_session.rollback()
        except Exception:
            pass
        return None


# ── Helpers ───────────────────────────────────────────────────────────

def _set(data: Dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        data[key] = value


def _enum_val(v: Any) -> Optional[str]:
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def _date_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _decimal_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_org_id(tenant_id: str) -> Optional[int]:
    try:
        return int(tenant_id)
    except (ValueError, TypeError):
        return None
