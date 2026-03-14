"""
Application Completion Orchestrator (ACO) -- Master Coordination Layer

Ties together the five ACO engines into a single service that the API routes
call. Every operation on an application review -- triggering, scoring, resolving
missing items, staging documents, communicating with borrowers, scheduling PA
calls, and dashboard analytics -- flows through this orchestrator.

Engines coordinated:
    1. ApplicationReviewEngine   -- AI review of submitted applications
    2. CompletenessScoreEngine   -- weighted scoring (0-100) + band routing
    3. AIResolutionEngine        -- item routing, response parsing, auto-fill
    4. DocumentStagingService    -- document lifecycle (stage -> send -> upload)
    5. SMSOrchestrator / CalendarCoordinator -- borrower comms + scheduling

Usage:
    from services.smart_docs.app_completion_orchestrator import (
        AppCompletionOrchestrator,
        trigger_application_review,
    )

    orchestrator = AppCompletionOrchestrator(db)
    result = orchestrator.process_submitted_application(
        loan_id="123", org_id="42", user_id="7",
    )

    # Or use the convenience function:
    result = trigger_application_review(db, loan_id="123")
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# LAZY MODEL IMPORTS
# =============================================================================

def _get_models():
    """Lazy import to avoid circular dependencies at module load time."""
    from database.models.app_completion import (
        ApplicationCompletenessReview,
        ApplicationScoreHistory,
        AppointmentCoordination,
        BorrowerCommunicationLog,
        DocumentStagingRequest,
        MissingItem,
        ActorType,
        BookingStatus,
        CommChannel,
        ComplexityLevel,
        DocStagingStatus,
        MessageIntent,
        MissingItemSeverity,
        MissingItemStatus,
        MissingItemType,
        NextAction,
        ResolutionMethod,
        ReviewStatus,
        ScoreChangeReason,
        SenderType,
    )
    return {
        "ACR": ApplicationCompletenessReview,
        "MI": MissingItem,
        "DSR": DocumentStagingRequest,
        "BCL": BorrowerCommunicationLog,
        "AC": AppointmentCoordination,
        "ASH": ApplicationScoreHistory,
        "ReviewStatus": ReviewStatus,
        "MissingItemType": MissingItemType,
        "MissingItemStatus": MissingItemStatus,
        "MissingItemSeverity": MissingItemSeverity,
        "ResolutionMethod": ResolutionMethod,
        "DocStagingStatus": DocStagingStatus,
        "CommChannel": CommChannel,
        "SenderType": SenderType,
        "MessageIntent": MessageIntent,
        "BookingStatus": BookingStatus,
        "ScoreChangeReason": ScoreChangeReason,
        "ActorType": ActorType,
        "ComplexityLevel": ComplexityLevel,
        "NextAction": NextAction,
    }


# =============================================================================
# SCORE THRESHOLDS
# =============================================================================

SCORE_REVIEW_COMPLETE = 90.0
SCORE_TEXT_RESOLUTION = 75.0
SCORE_HYBRID_RESOLUTION = 50.0


def _determine_next_action(score: float, complexity: int, call_needed: bool) -> str:
    """Map score + complexity to a NextAction enum value."""
    if score >= SCORE_REVIEW_COMPLETE:
        return "REVIEW_COMPLETE"
    if call_needed or complexity >= 6:
        return "SCHEDULE_PA_CALL"
    if score >= SCORE_TEXT_RESOLUTION:
        return "RESOLVE_BY_TEXT"
    if score >= SCORE_HYBRID_RESOLUTION:
        return "SEND_INTRO_SMS"
    return "SCHEDULE_PA_CALL"


# =============================================================================
# ASYNC BRIDGE
# =============================================================================

def _run_async(coro):
    """Execute an async coroutine from synchronous context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# =============================================================================
# SMALL HELPERS
# =============================================================================

def _now():
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _f(val) -> Optional[float]:
    """Safe float conversion."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# =============================================================================
# MASTER ORCHESTRATOR
# =============================================================================

class AppCompletionOrchestrator:
    """Single coordination layer between routes and the five ACO engines.

    Constructor accepts only ``db`` so that routes can instantiate it
    without needing org/user context upfront.  Tenant-scoped data is
    resolved from the loan record as needed.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Internal: loan helpers
    # ------------------------------------------------------------------

    def _loan(self, loan_id) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            text(
                "SELECT id, loan_number, organization_id, borrower_name, "
                "borrower_email, borrower_phone, preferred_communication, "
                "stage, loan_type, loan_purpose, amount, loan_officer_id, "
                "loan_officer_name, user_metadata, coborrower_name "
                "FROM loans WHERE id = :id"
            ),
            {"id": str(loan_id)},
        ).mappings().first()
        return dict(row) if row else None

    def _org_for_loan(self, loan_id) -> Optional[str]:
        row = self.db.execute(
            text("SELECT organization_id FROM loans WHERE id = :id"),
            {"id": str(loan_id)},
        ).first()
        return str(row[0]) if row and row[0] else None

    # ------------------------------------------------------------------
    # Internal: engine factories (lazy)
    # ------------------------------------------------------------------

    def _review_eng(self, org_id):
        from services.smart_docs.app_review_engine import ApplicationReviewEngine
        return ApplicationReviewEngine(self.db, org_id)

    def _score_eng(self, org_id):
        from services.smart_docs.completeness_scoring_engine import CompletenessScoreEngine
        return CompletenessScoreEngine(self.db, org_id)

    def _resolution_eng(self, org_id, user_id="system"):
        from services.smart_docs.ai_resolution_engine import AIResolutionEngine
        return AIResolutionEngine(self.db, org_id, user_id)

    def _staging_svc(self, org_id):
        from services.smart_docs.document_staging_service import DocumentStagingService
        return DocumentStagingService(self.db, org_id)

    def _sms(self, org_id, review_id=None):
        from services.smart_docs.communication_orchestrator import SMSOrchestrator
        return SMSOrchestrator(self.db, org_id, review_id=review_id)

    def _cal(self, org_id):
        from services.smart_docs.communication_orchestrator import CalendarCoordinator
        return CalendarCoordinator(self.db, org_id)

    # ------------------------------------------------------------------
    # Internal: ORM -> dict serializers
    # ------------------------------------------------------------------

    @staticmethod
    def _ser_review(r) -> dict:
        return {
            "id": r.id,
            "organization_id": r.organization_id,
            "loan_id": r.loan_id,
            "review_status": r.review_status,
            "overall_score": _f(r.overall_score),
            "data_completeness_score": _f(r.data_completeness_score),
            "data_consistency_score": _f(r.data_consistency_score),
            "document_readiness_score": _f(r.document_readiness_score),
            "complexity_score": r.complexity_score,
            "complexity_level": r.complexity_level,
            "next_recommended_action": r.next_recommended_action,
            "total_missing_items": r.total_missing_items,
            "total_clarifications_needed": r.total_clarifications_needed,
            "total_documents_needed": r.total_documents_needed,
            "total_escalations": r.total_escalations,
            "items_resolved_by_ai": r.items_resolved_by_ai,
            "items_resolved_by_staff": r.items_resolved_by_staff,
            "review_summary": r.review_summary,
            "section_scores": r.section_scores,
            "triggered_by": r.triggered_by,
            "assigned_to_user_id": r.assigned_to_user_id,
            "assigned_to_queue": r.assigned_to_queue,
            "completed_at": _iso(r.completed_at),
            "created_at": _iso(r.created_at),
            "updated_at": _iso(r.updated_at),
        }

    @staticmethod
    def _ser_item(i) -> dict:
        return {
            "id": i.id,
            "review_id": i.review_id,
            "loan_id": i.loan_id,
            "item_type": i.item_type,
            "severity": i.severity,
            "field_path": i.field_path,
            "field_section": i.field_section,
            "borrower_question": i.borrower_question,
            "internal_note": i.internal_note,
            "resolution_method": i.resolution_method,
            "status": i.status,
            "source_engine": i.source_engine,
            "ai_confidence": _f(i.ai_confidence),
            "current_value": i.current_value,
            "resolved_value": i.resolved_value,
            "resolved_by_user_id": i.resolved_by_user_id,
            "resolved_by_type": i.resolved_by_type,
            "sent_at": _iso(i.sent_at),
            "responded_at": _iso(i.responded_at),
            "resolved_at": _iso(i.resolved_at),
            "created_at": _iso(i.created_at),
        }

    @staticmethod
    def _ser_staging(d) -> dict:
        return {
            "id": d.id,
            "review_id": d.review_id,
            "loan_id": d.loan_id,
            "doc_type": d.doc_type,
            "doc_label": d.doc_label,
            "reason_code": d.reason_code,
            "status": d.status,
            "priority": d.priority,
            "staged_at": _iso(d.staged_at),
            "sent_at": _iso(d.sent_at),
            "uploaded_at": _iso(d.uploaded_at),
            "waived_at": _iso(d.waived_at),
            "waived_reason": d.waived_reason,
            "portal_published": d.portal_published,
            "created_at": _iso(d.created_at),
        }

    @staticmethod
    def _ser_comm(c) -> dict:
        return {
            "id": c.id,
            "loan_id": c.loan_id,
            "review_id": c.review_id,
            "missing_item_id": c.missing_item_id,
            "channel": c.channel,
            "sender_type": c.sender_type,
            "message_intent": c.message_intent,
            "message_body": c.message_body,
            "recipient_phone": c.recipient_phone,
            "delivery_status": c.delivery_status,
            "response_detected": c.response_detected,
            "response_body": c.response_body,
            "sentiment": c.sentiment,
            "created_at": _iso(c.created_at),
        }

    @staticmethod
    def _ser_appt(a) -> dict:
        return {
            "id": a.id,
            "loan_id": a.loan_id,
            "review_id": a.review_id,
            "assigned_pa_user_id": a.assigned_pa_user_id,
            "borrower_name": a.borrower_name,
            "borrower_phone": a.borrower_phone,
            "booked_start": _iso(a.booked_start),
            "booked_end": _iso(a.booked_end),
            "duration_minutes": a.duration_minutes,
            "booking_status": a.booking_status,
            "pre_call_brief": a.pre_call_brief,
            "unresolved_items_count": a.unresolved_items_count,
            "call_notes": a.call_notes,
            "items_resolved_in_call": a.items_resolved_in_call,
            "completed_at": _iso(a.completed_at),
            "cancelled_at": _iso(a.cancelled_at),
            "cancel_reason": a.cancel_reason,
            "created_at": _iso(a.created_at),
        }

    # ==================================================================
    # 1. FULL WORKFLOW
    # ==================================================================

    def process_submitted_application(
        self,
        loan_id,
        org_id: str,
        user_id: str = "system",
        triggered_by: str = "APPLICATION_SUBMITTED",
    ) -> Dict[str, Any]:
        """Run the complete review pipeline for a submitted application."""
        m = _get_models()
        ACR, MI = m["ACR"], m["MI"]

        lid = str(loan_id)
        t0 = time.monotonic()
        loan = self._loan(lid)
        if not loan:
            return {"error": "loan_not_found", "loan_id": lid}
        org_id = str(org_id or loan.get("organization_id", ""))

        # --- 1. AI Review ---
        try:
            findings = _run_async(self._review_eng(org_id).review_application(lid)).get("findings", [])
        except Exception as e:
            logger.exception("Review engine failed for loan %s", lid)
            return {"error": "review_failed", "detail": str(e)}

        # --- 2. Score ---
        meta = loan.get("user_metadata") or {}
        score_result = self._score_eng(org_id).calculate_score(
            loan_id=lid, findings=findings,
            loan_type=loan.get("loan_type", ""),
            is_self_employed=bool(meta.get("self_employed")),
            has_multiple_income_sources=bool(meta.get("multiple_income_sources")),
        )
        score = score_result["overall_score"]
        cx = score_result["complexity_score"]
        cx_level = score_result["complexity_level"]

        # --- 3. Create review ---
        review = ACR(
            organization_id=org_id, loan_id=lid,
            review_status="COMPLETED",
            overall_score=score,
            data_completeness_score=score_result["data_completeness_score"],
            data_consistency_score=score_result["data_consistency_score"],
            document_readiness_score=score_result["document_readiness_score"],
            complexity_score=cx, complexity_level=cx_level,
            total_missing_items=len(findings),
            total_clarifications_needed=sum(1 for f in findings if f.get("item_type") == "CLARIFICATION"),
            total_documents_needed=sum(1 for f in findings if f.get("item_type") == "DOCUMENT"),
            section_scores=score_result.get("section_scores"),
            triggered_by=triggered_by,
            review_duration_ms=int((time.monotonic() - t0) * 1000),
            completed_at=_now(),
        )
        self.db.add(review)
        self.db.flush()

        # --- 4. Create MissingItem records ---
        items = []
        for f in findings:
            item = MI(
                organization_id=org_id, review_id=review.id, loan_id=lid,
                item_type=f.get("item_type", "FIELD"),
                severity=f.get("severity", "MEDIUM"),
                field_path=f.get("field_path"),
                field_section=f.get("field_section"),
                borrower_question=f.get("borrower_question"),
                internal_note=f.get("internal_note"),
                source_engine=f.get("source_engine"),
                ai_confidence=f.get("ai_confidence"),
                current_value=str(f["current_value"]) if f.get("current_value") is not None else None,
                status="IDENTIFIED",
            )
            self.db.add(item)
            items.append(item)
        self.db.flush()

        # --- 5. Route items ---
        text_resolvable = 0
        call_needed = cx_level == "direct_pa_call"
        text_ids, call_ids, portal_ids = set(), set(), set()
        try:
            plan = _run_async(self._resolution_eng(org_id, user_id).route_missing_items(
                review.id,
                [{"id": i.id, "item_type": i.item_type, "section": i.field_section or "",
                  "field_path": i.field_path or "", "description": i.internal_note or "",
                  "severity": i.severity} for i in items],
            ))
            text_resolvable = len(plan.text_items)
            call_needed = call_needed or plan.call_recommended
            text_ids = {r.get("item_id") for r in plan.text_items}
            call_ids = {r.get("item_id") for r in plan.call_items}
            portal_ids = {r.get("item_id") for r in plan.portal_items}
        except Exception:
            logger.exception("Resolution routing failed for review %s", review.id)

        for item in items:
            if item.id in text_ids:
                item.resolution_method = "TEXT_SMS"
            elif item.id in call_ids:
                item.resolution_method = "PA_CALL"
            elif item.id in portal_ids:
                item.resolution_method = "PORTAL_UPLOAD"
            else:
                item.resolution_method = "MANUAL_ENTRY"

        # --- 6. Stage documents ---
        docs_staged = 0
        try:
            svc = self._staging_svc(org_id)
            reqs = _run_async(svc.identify_required_documents(
                loan_id=lid, loan_type=loan.get("loan_type", "conventional"),
                loan_purpose=loan.get("loan_purpose", "purchase"),
                is_self_employed=bool(meta.get("self_employed")),
            ))
            if reqs:
                staged = _run_async(svc.stage_documents(lid, review.id, reqs))
                docs_staged = len(staged) if isinstance(staged, list) else 0
        except Exception:
            logger.exception("Document staging failed for review %s", review.id)

        # --- 7. Determine next action and queue ---
        next_action = _determine_next_action(score, cx, call_needed)
        review.next_recommended_action = next_action
        review.assigned_to_queue = "PA_QUEUE" if next_action == "SCHEDULE_PA_CALL" else "AI_QUEUE"
        review.total_escalations = len(call_ids)
        review.review_summary = (
            f"Score: {score:.1f}/100. {len(findings)} items: "
            f"{text_resolvable} text, {docs_staged} docs, "
            f"{'PA call recommended' if call_needed else 'no call needed'}."
        )

        # --- 8. Record initial score ---
        self._score_eng(org_id).record_score_change(
            review_id=review.id, prior_score=0.0, new_score=score,
            reason="INITIAL_REVIEW",
            reason_detail=f"Initial: {len(findings)} findings, score {score}",
            actor_type="SYSTEM",
        )

        self.db.commit()
        return {
            "review_id": review.id, "loan_id": lid,
            "overall_score": score, "complexity_level": cx_level,
            "next_action": next_action, "missing_items_count": len(findings),
            "documents_staged": docs_staged, "text_resolvable": text_resolvable,
            "call_needed": call_needed,
        }

    # ==================================================================
    # 2. REVIEW ACCESS
    # ==================================================================

    def get_latest_review(self, loan_id) -> Optional[Dict[str, Any]]:
        """Most recent review with attached items."""
        m = _get_models()
        review = (self.db.query(m["ACR"])
                  .filter(m["ACR"].loan_id == str(loan_id))
                  .order_by(m["ACR"].created_at.desc()).first())
        if not review:
            return None
        data = self._ser_review(review)
        items = (self.db.query(m["MI"]).filter(m["MI"].review_id == review.id)
                 .order_by(m["MI"].severity.desc(), m["MI"].created_at).all())
        data["missing_items"] = [self._ser_item(i) for i in items]
        return data

    def get_review_history(self, loan_id, limit=20, offset=0) -> dict:
        m = _get_models()
        lid = str(loan_id)
        total = self.db.query(m["ACR"]).filter(m["ACR"].loan_id == lid).count()
        rows = (self.db.query(m["ACR"]).filter(m["ACR"].loan_id == lid)
                .order_by(m["ACR"].created_at.desc()).offset(offset).limit(limit).all())
        return {"loan_id": lid, "total": total, "offset": offset, "limit": limit,
                "reviews": [self._ser_review(r) for r in rows]}

    # ==================================================================
    # 3. SCORING PAGE
    # ==================================================================

    def get_scoring_page_data(self, loan_id) -> Optional[Dict[str, Any]]:
        """Single-call aggregation for the scoring page."""
        m = _get_models()
        lid = str(loan_id)
        review = (self.db.query(m["ACR"]).filter(m["ACR"].loan_id == lid)
                  .order_by(m["ACR"].created_at.desc()).first())
        if not review:
            return None

        loan = self._loan(lid)
        items = (self.db.query(m["MI"]).filter(m["MI"].review_id == review.id)
                 .order_by(m["MI"].severity.desc(), m["MI"].created_at).all())
        by_type: Dict[str, list] = {"FIELD": [], "CLARIFICATION": [], "DOCUMENT": [], "EXCEPTION": []}
        for i in items:
            by_type.setdefault(i.item_type or "FIELD", []).append(self._ser_item(i))
        staged = (self.db.query(m["DSR"]).filter(m["DSR"].loan_id == lid)
                  .order_by(m["DSR"].priority.desc(), m["DSR"].created_at).all())
        comms = (self.db.query(m["BCL"]).filter(m["BCL"].loan_id == lid)
                 .order_by(m["BCL"].created_at.desc()).limit(20).all())
        appt = (self.db.query(m["AC"]).filter(m["AC"].loan_id == lid)
                .order_by(m["AC"].created_at.desc()).first())
        history = (self.db.query(m["ASH"]).filter(m["ASH"].loan_id == lid)
                   .order_by(m["ASH"].created_at.desc()).limit(20).all())

        resolved = sum(1 for i in items if i.status == "RESOLVED")
        return {
            "header": {
                "loan_id": lid,
                "loan_number": loan.get("loan_number") if loan else None,
                "borrower_name": loan.get("borrower_name") if loan else None,
                "loan_officer_name": loan.get("loan_officer_name") if loan else None,
                "loan_type": loan.get("loan_type") if loan else None,
                "stage": loan.get("stage") if loan else None,
            },
            "review": self._ser_review(review),
            "items_by_type": by_type,
            "items_summary": {
                "total": len(items), "resolved": resolved,
                "deferred": sum(1 for i in items if i.status == "DEFERRED"),
                "escalated": sum(1 for i in items if i.status == "ESCALATED"),
                "pending": len(items) - resolved,
            },
            "staged_documents": [self._ser_staging(d) for d in staged],
            "communications": [self._ser_comm(c) for c in comms],
            "appointment": self._ser_appt(appt) if appt else None,
            "score_history": [
                {"id": h.id, "prior_score": _f(h.prior_score), "new_score": _f(h.new_score),
                 "score_delta": _f(h.score_delta), "reason": h.reason,
                 "created_at": _iso(h.created_at)}
                for h in history
            ],
        }

    def get_score_trend(self, loan_id, days=30) -> dict:
        m = _get_models()
        lid = str(loan_id)
        cutoff = _now() - timedelta(days=days)
        entries = (self.db.query(m["ASH"])
                   .filter(m["ASH"].loan_id == lid, m["ASH"].created_at >= cutoff)
                   .order_by(m["ASH"].created_at.asc()).all())
        return {
            "loan_id": lid, "days": days,
            "data_points": [
                {"timestamp": _iso(e.created_at), "score": _f(e.new_score),
                 "delta": _f(e.score_delta), "reason": e.reason}
                for e in entries
            ],
        }

    # ==================================================================
    # 4. MISSING ITEMS
    # ==================================================================

    def get_missing_items(self, loan_id, item_type=None, severity=None, status=None) -> dict:
        m = _get_models()
        MI = m["MI"]
        q = self.db.query(MI).filter(MI.loan_id == str(loan_id))
        if item_type:
            q = q.filter(MI.item_type == item_type.upper())
        if severity:
            q = q.filter(MI.severity == severity.upper())
        if status:
            su = status.upper()
            if su == "OPEN":
                q = q.filter(MI.status.in_(["IDENTIFIED", "STAGED", "SENT_TO_BORROWER", "BORROWER_RESPONDED"]))
            else:
                q = q.filter(MI.status == su)
        items = q.order_by(MI.severity.desc(), MI.created_at).all()
        return {"loan_id": str(loan_id), "total": len(items),
                "items": [self._ser_item(i) for i in items]}

    def get_item_loan_id(self, item_id: int) -> Optional[dict]:
        MI = _get_models()["MI"]
        item = self.db.query(MI).filter(MI.id == item_id).first()
        return {"loan_id": item.loan_id} if item else None

    def resolve_item(self, item_id, value, notes=None, resolved_by=None) -> dict:
        m = _get_models()
        MI = m["MI"]
        item = self.db.query(MI).filter(MI.id == item_id).first()
        if not item:
            return {"error": "item_not_found"}
        prior = item.status
        item.status = "RESOLVED"
        item.resolved_value = value
        item.resolved_at = _now()
        item.resolved_by_user_id = resolved_by
        item.resolved_by_type = "STAFF"
        if not item.resolution_method:
            item.resolution_method = "MANUAL_ENTRY"
        if notes:
            item.internal_note = f"{item.internal_note or ''}\n[Note: {notes}]".strip()
        recalc = self._score_eng(item.organization_id).recalculate_after_resolution(item.review_id, item_id)
        review = self.db.query(m["ACR"]).filter(m["ACR"].id == item.review_id).first()
        if review:
            review.items_resolved_by_staff = (review.items_resolved_by_staff or 0) + 1
        self.db.commit()
        return {"item_id": item_id, "status": "resolved", "prior_status": prior, "score_update": recalc}

    def escalate_item(self, item_id, escalated_by=None) -> dict:
        m = _get_models()
        MI = m["MI"]
        item = self.db.query(MI).filter(MI.id == item_id).first()
        if not item:
            return {"error": "item_not_found"}
        prior = item.status
        item.status = "ESCALATED"
        item.resolution_method = "PA_CALL"
        review = self.db.query(m["ACR"]).filter(m["ACR"].id == item.review_id).first()
        if review:
            review.total_escalations = (review.total_escalations or 0) + 1
            esc_count = self.db.query(MI).filter(MI.review_id == item.review_id, MI.status == "ESCALATED").count()
            if esc_count >= 3:
                review.next_recommended_action = "SCHEDULE_PA_CALL"
        self.db.commit()
        return {"item_id": item_id, "status": "escalated", "prior_status": prior}

    def defer_item(self, item_id, deferred_by=None) -> dict:
        MI = _get_models()["MI"]
        item = self.db.query(MI).filter(MI.id == item_id).first()
        if not item:
            return {"error": "item_not_found"}
        prior = item.status
        item.status = "DEFERRED"
        self.db.commit()
        return {"item_id": item_id, "status": "deferred", "prior_status": prior}

    def ask_borrower(self, item_id, sent_by=None, custom_message=None) -> dict:
        m = _get_models()
        MI, BCL = m["MI"], m["BCL"]
        item = self.db.query(MI).filter(MI.id == item_id).first()
        if not item:
            return {"error": "item_not_found"}
        loan = self._loan(item.loan_id)
        if not loan:
            return {"error": "loan_not_found"}
        phone = loan.get("borrower_phone")
        if not phone:
            return {"error": "no_borrower_phone"}
        question = custom_message or item.borrower_question or \
            f"Could you provide your {(item.field_path or 'information').replace('_', ' ')}?"
        org = item.organization_id
        try:
            result = _run_async(self._sms(org, item.review_id).send_question(
                loan_id=item.loan_id, borrower_phone=phone,
                question_text=question, missing_item_id=item.id,
            ))
        except Exception as e:
            logger.exception("SMS send failed for item %s", item_id)
            self.db.add(BCL(
                organization_id=org, loan_id=item.loan_id, review_id=item.review_id,
                missing_item_id=item.id, channel="SMS", sender_type="AI_AGENT",
                message_intent="QUESTION", message_body=question,
                recipient_phone=phone, delivery_status="FAILED", error_message=str(e),
            ))
            self.db.commit()
            return {"error": "sms_send_failed", "detail": str(e)}
        item.status = "SENT_TO_BORROWER"
        item.sent_at = _now()
        self.db.commit()
        return {"item_id": item_id, "status": "sent_to_borrower", "question": question}

    # ==================================================================
    # 5. DOCUMENT STAGING
    # ==================================================================

    def get_staged_documents(self, loan_id) -> dict:
        DSR = _get_models()["DSR"]
        lid = str(loan_id)
        docs = (self.db.query(DSR).filter(DSR.loan_id == lid)
                .order_by(DSR.priority.desc(), DSR.created_at).all())
        by_status: Dict[str, list] = {}
        for d in docs:
            by_status.setdefault(d.status or "UNKNOWN", []).append(self._ser_staging(d))
        return {"loan_id": lid, "total": len(docs), "by_status": by_status,
                "documents": [self._ser_staging(d) for d in docs]}

    def stage_document(self, loan_id, doc_type, doc_label, reason="manual", priority="MEDIUM", staged_by=None) -> dict:
        m = _get_models()
        DSR = m["DSR"]
        lid = str(loan_id)
        org = self._org_for_loan(lid)
        if not org:
            return {"error": "loan_not_found"}
        review = (self.db.query(m["ACR"]).filter(m["ACR"].loan_id == lid)
                  .order_by(m["ACR"].created_at.desc()).first())
        dsr = DSR(
            organization_id=org, review_id=review.id if review else None,
            loan_id=lid, doc_type=doc_type, doc_label=doc_label,
            reason_code=reason, reason_description=f"Manually staged: {reason}",
            status="STAGED", priority=priority.upper(),
            staged_by_user_id=staged_by, staged_at=_now(),
        )
        self.db.add(dsr)
        self.db.commit()
        return self._ser_staging(dsr)

    def get_staging_loan_id(self, staging_id: int) -> Optional[dict]:
        DSR = _get_models()["DSR"]
        d = self.db.query(DSR).filter(DSR.id == staging_id).first()
        return {"loan_id": d.loan_id} if d else None

    def select_documents(self, staging_ids, selected_by=None) -> dict:
        DSR = _get_models()["DSR"]
        updated = 0
        for sid in staging_ids:
            d = self.db.query(DSR).filter(DSR.id == sid).first()
            if d and d.status in ("IDENTIFIED", "STAGED"):
                d.status = "SELECTED"
                updated += 1
        self.db.commit()
        return {"selected_count": updated, "total_requested": len(staging_ids)}

    def select_all_documents(self, loan_id, selected_by=None) -> dict:
        DSR = _get_models()["DSR"]
        lid = str(loan_id)
        docs = (self.db.query(DSR)
                .filter(DSR.loan_id == lid, DSR.status.in_(["IDENTIFIED", "STAGED"])).all())
        for d in docs:
            d.status = "SELECTED"
        self.db.commit()
        return {"loan_id": lid, "selected_count": len(docs)}

    def send_documents(self, loan_id, staging_ids=None, notify_sms=True, notify_email=True, sent_by=None) -> dict:
        DSR = _get_models()["DSR"]
        lid = str(loan_id)
        if staging_ids:
            docs = self.db.query(DSR).filter(DSR.id.in_(staging_ids), DSR.loan_id == lid).all()
        else:
            docs = self.db.query(DSR).filter(DSR.loan_id == lid, DSR.status == "SELECTED").all()
        if not docs:
            return {"loan_id": lid, "sent_count": 0}
        now = _now()
        for d in docs:
            d.status = "SENT"
            d.sent_at = now
            d.portal_published = True
            d.borrower_notified = True
            ch = []
            if notify_sms:
                ch.append("SMS")
            if notify_email:
                ch.append("EMAIL")
            d.sent_channel = ",".join(ch) or "PORTAL"
        loan = self._loan(lid)
        notif = {}
        if loan and loan.get("organization_id"):
            try:
                notif = _run_async(self._sms(loan["organization_id"]).send_doc_request_notification(
                    loan_id=lid, borrower_phone=loan.get("borrower_phone", ""),
                    borrower_name=loan.get("borrower_name", ""),
                    borrower_email=loan.get("borrower_email"),
                    doc_count=len(docs), lo_name=loan.get("loan_officer_name", ""),
                    send_sms=notify_sms, send_email=notify_email,
                )) or {}
            except Exception as e:
                logger.exception("Doc notification failed for loan %s", lid)
                notif = {"error": str(e)}
        self.db.commit()
        return {"loan_id": lid, "sent_count": len(docs), "notification": notif}

    def waive_document(self, staging_id, reason, waived_by=None) -> dict:
        DSR = _get_models()["DSR"]
        d = self.db.query(DSR).filter(DSR.id == staging_id).first()
        if not d:
            return {"error": "staging_not_found"}
        prior = d.status
        d.status = "WAIVED"
        d.waived_at = _now()
        d.waived_reason = reason
        self.db.commit()
        return {"staging_id": staging_id, "status": "waived", "prior_status": prior}

    def get_portal_tasks(self, loan_id) -> dict:
        DSR = _get_models()["DSR"]
        lid = str(loan_id)
        docs = (self.db.query(DSR)
                .filter(DSR.loan_id == lid,
                        DSR.status.in_(["SENT", "UPLOADED", "REVIEWED"]),
                        DSR.portal_published == True)
                .order_by(DSR.priority.desc(), DSR.created_at).all())
        tasks = []
        for d in docs:
            done = d.status in ("UPLOADED", "REVIEWED", "CLEARED")
            tasks.append({"id": d.id, "doc_type": d.doc_type, "label": d.doc_label,
                          "priority": d.priority, "status": "complete" if done else "pending",
                          "due_date": _iso(d.due_date), "uploaded_at": _iso(d.uploaded_at)})
        completed = sum(1 for t in tasks if t["status"] == "complete")
        return {"loan_id": lid, "total_tasks": len(tasks), "completed": completed,
                "pending": len(tasks) - completed, "tasks": tasks}

    # ==================================================================
    # 6. COMMUNICATION
    # ==================================================================

    def get_communication_log(self, loan_id, limit=50, offset=0) -> dict:
        BCL = _get_models()["BCL"]
        lid = str(loan_id)
        total = self.db.query(BCL).filter(BCL.loan_id == lid).count()
        comms = (self.db.query(BCL).filter(BCL.loan_id == lid)
                 .order_by(BCL.created_at.desc()).offset(offset).limit(limit).all())
        return {"loan_id": lid, "total": total, "offset": offset, "limit": limit,
                "messages": [self._ser_comm(c) for c in comms]}

    def send_intro_sequence(self, loan_id, triggered_by=None) -> dict:
        lid = str(loan_id)
        loan = self._loan(lid)
        if not loan:
            return {"error": "loan_not_found"}
        org = loan.get("organization_id")
        phone = loan.get("borrower_phone")
        if not org:
            return {"error": "no_organization"}
        if not phone:
            return {"error": "no_borrower_phone"}
        ACR = _get_models()["ACR"]
        review = (self.db.query(ACR).filter(ACR.loan_id == lid)
                  .order_by(ACR.created_at.desc()).first())
        try:
            result = _run_async(self._sms(org, review.id if review else None).send_intro_sequence(
                loan_id=lid, borrower_phone=phone,
                borrower_name=loan.get("borrower_name", ""),
                lo_name=loan.get("loan_officer_name", ""),
            ))
            self.db.commit()
            return {"loan_id": lid, "status": "sent",
                    "messages_sent": len(result) if isinstance(result, list) else 1}
        except Exception as e:
            logger.exception("Intro sequence failed for loan %s", lid)
            return {"error": "send_failed", "detail": str(e)}

    def handle_borrower_response(self, from_number, to_number, message_body, raw_payload=None) -> dict:
        """Match inbound SMS to a loan/item, parse, and potentially auto-resolve."""
        m = _get_models()
        MI, BCL, ACR = m["MI"], m["BCL"], m["ACR"]

        # Match phone to loan
        digits = from_number.strip().replace("-", "").replace(" ", "")
        last10 = digits[-10:] if len(digits) >= 10 else digits
        loan_row = self.db.execute(
            text("SELECT id, organization_id, borrower_name FROM loans "
                 "WHERE borrower_phone LIKE :ph ORDER BY created_at DESC LIMIT 1"),
            {"ph": f"%{last10}"},
        ).first()
        if not loan_row:
            return {"status": "no_match", "from_number": from_number}

        lid, org, bname = str(loan_row[0]), str(loan_row[1]), loan_row[2] or ""
        review = (self.db.query(ACR).filter(ACR.loan_id == lid)
                  .order_by(ACR.created_at.desc()).first())
        rid = review.id if review else None

        pending = (self.db.query(MI)
                   .filter(MI.loan_id == lid, MI.status == "SENT_TO_BORROWER")
                   .order_by(MI.sent_at.desc()).first())

        # Log inbound
        comm = BCL(
            organization_id=org, loan_id=lid, review_id=rid,
            missing_item_id=pending.id if pending else None,
            channel="SMS", sender_type="BORROWER", message_intent="ANSWER",
            message_body=message_body, recipient_phone=to_number, delivery_status="RECEIVED",
        )
        self.db.add(comm)

        result: Dict[str, Any] = {"status": "received", "loan_id": lid,
                                   "matched_item_id": pending.id if pending else None}
        if pending:
            pending.status = "BORROWER_RESPONDED"
            pending.responded_at = _now()
            try:
                parsed = _run_async(self._resolution_eng(org).parse_borrower_response(
                    {"field_path": pending.field_path or "", "field_hint": pending.field_section or "",
                     "question_text": pending.borrower_question or "", "expected_format": "text"},
                    message_body,
                ))
                comm.response_detected = True
                comm.response_body = message_body
                comm.response_confidence = parsed.confidence
                comm.sentiment = parsed.sentiment
                result["confidence"] = parsed.confidence

                if parsed.escalate:
                    pending.status = "ESCALATED"
                    result["action"] = "escalated"
                elif parsed.confidence >= 0.8 and parsed.parsed_value:
                    pending.status = "RESOLVED"
                    pending.resolved_value = parsed.parsed_value
                    pending.resolved_at = _now()
                    pending.resolved_by_type = "BORROWER"
                    pending.resolution_method = "TEXT_SMS"
                    self._score_eng(org).recalculate_after_resolution(pending.review_id, pending.id)
                    result["action"] = "auto_resolved"
                elif parsed.needs_confirmation:
                    result["action"] = "needs_confirmation"
                else:
                    result["action"] = "manual_review_needed"
            except Exception as e:
                logger.exception("Parse failed for item %s", pending.id)
                result["action"] = "parse_failed"
        else:
            result["action"] = "no_pending_item"

        self.db.commit()
        return result

    # ==================================================================
    # 7. APPOINTMENTS
    # ==================================================================

    def get_appointment(self, loan_id) -> Optional[dict]:
        AC = _get_models()["AC"]
        a = (self.db.query(AC).filter(AC.loan_id == str(loan_id))
             .order_by(AC.created_at.desc()).first())
        return self._ser_appt(a) if a else None

    def get_appointment_loan_id(self, appointment_id: int) -> Optional[dict]:
        AC = _get_models()["AC"]
        a = self.db.query(AC).filter(AC.id == appointment_id).first()
        return {"loan_id": a.loan_id} if a else None

    def schedule_appointment(self, loan_id, pa_user_id, start_time, duration_minutes=15, scheduled_by=None) -> dict:
        lid = str(loan_id)
        loan = self._loan(lid)
        if not loan:
            return {"error": "loan_not_found"}
        org = loan.get("organization_id")
        if not org:
            return {"error": "no_organization"}
        if isinstance(start_time, str):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        else:
            start_dt = start_time
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        ACR = _get_models()["ACR"]
        review = (self.db.query(ACR).filter(ACR.loan_id == lid)
                  .order_by(ACR.created_at.desc()).first())
        try:
            r = _run_async(self._cal(org).book_appointment(
                loan_id=lid, pa_user_id=pa_user_id,
                borrower_name=loan.get("borrower_name", ""),
                borrower_phone=loan.get("borrower_phone", ""),
                start_time=start_dt, duration_minutes=duration_minutes,
                review_id=review.id if review else None,
                borrower_email=loan.get("borrower_email"),
                lo_name=loan.get("loan_officer_name", ""),
            ))
            self.db.commit()
            return {"loan_id": lid, "status": "booked", "scheduled_by": scheduled_by, **r}
        except Exception as e:
            logger.exception("Scheduling failed for loan %s", lid)
            return {"error": "scheduling_failed", "detail": str(e)}

    def complete_appointment(self, appointment_id, items_resolved=None, call_notes="", completed_by=None) -> dict:
        m = _get_models()
        AC, MI = m["AC"], m["MI"]
        appt = self.db.query(AC).filter(AC.id == appointment_id).first()
        if not appt:
            return {"error": "appointment_not_found"}
        org = appt.organization_id
        try:
            _run_async(self._cal(org).mark_completed(
                appointment_id, len(items_resolved) if items_resolved else 0, call_notes))
        except Exception:
            logger.exception("Calendar mark_completed failed for %s", appointment_id)
            appt.booking_status = "COMPLETED"
            appt.completed_at = _now()
            appt.items_resolved_in_call = len(items_resolved) if items_resolved else 0
            appt.call_notes = call_notes
        count = 0
        if items_resolved:
            for iid in items_resolved:
                item = self.db.query(MI).filter(MI.id == iid).first()
                if item and item.status != "RESOLVED":
                    item.status = "RESOLVED"
                    item.resolved_at = _now()
                    item.resolved_by_user_id = completed_by
                    item.resolved_by_type = "STAFF"
                    item.resolution_method = "PA_CALL"
                    count += 1
            if count and appt.review_id:
                try:
                    eng = self._score_eng(org)
                    for iid in items_resolved:
                        eng.recalculate_after_resolution(appt.review_id, iid)
                except Exception:
                    logger.exception("Score recalc failed after call completion")
        self.db.commit()
        return {"appointment_id": appointment_id, "status": "completed", "items_resolved_count": count}

    def cancel_appointment(self, appointment_id, reason="", cancelled_by=None) -> dict:
        AC = _get_models()["AC"]
        appt = self.db.query(AC).filter(AC.id == appointment_id).first()
        if not appt:
            return {"error": "appointment_not_found"}
        try:
            _run_async(self._cal(appt.organization_id).cancel_appointment(appointment_id, reason or "cancelled"))
        except Exception:
            logger.exception("Calendar cancel failed for %s", appointment_id)
            appt.booking_status = "CANCELLED"
            appt.cancelled_at = _now()
            appt.cancel_reason = reason
        self.db.commit()
        return {"appointment_id": appointment_id, "status": "cancelled", "reason": reason}

    # ==================================================================
    # 8. DASHBOARD & QUEUE
    # ==================================================================

    def get_dashboard_stats(self, organization_id=None, days=30) -> dict:
        cutoff = _now() - timedelta(days=days)
        p: Dict[str, Any] = {"cutoff": cutoff}
        org_filt = ""
        if organization_id:
            org_filt = "AND acr.organization_id = :org"
            p["org"] = organization_id

        stats = self.db.execute(text(f"""
            SELECT COUNT(*) total,
                   COUNT(CASE WHEN review_status='COMPLETED' THEN 1 END) completed,
                   AVG(overall_score) avg_score,
                   COUNT(CASE WHEN overall_score >= 90 THEN 1 END) near_complete,
                   COUNT(CASE WHEN overall_score >= 50 AND overall_score < 90 THEN 1 END) moderate,
                   COUNT(CASE WHEN overall_score < 50 THEN 1 END) high_touch
            FROM application_completeness_reviews acr
            WHERE created_at >= :cutoff {org_filt}
        """), p).mappings().first()

        items = self.db.execute(text(f"""
            SELECT COUNT(*) total,
                   COUNT(CASE WHEN mi.status='RESOLVED' THEN 1 END) resolved,
                   COUNT(CASE WHEN mi.resolved_by_type='AI' OR mi.resolution_method='AI_AUTO_FILL' THEN 1 END) ai,
                   COUNT(CASE WHEN mi.status='ESCALATED' THEN 1 END) escalated,
                   COUNT(CASE WHEN mi.status IN ('IDENTIFIED','STAGED','SENT_TO_BORROWER','BORROWER_RESPONDED') THEN 1 END) pending
            FROM missing_items mi JOIN application_completeness_reviews acr ON acr.id=mi.review_id
            WHERE acr.created_at >= :cutoff {org_filt}
        """), p).mappings().first()

        top = self.db.execute(text(f"""
            SELECT mi.field_section, mi.item_type, COUNT(*) cnt
            FROM missing_items mi JOIN application_completeness_reviews acr ON acr.id=mi.review_id
            WHERE acr.created_at >= :cutoff AND mi.status != 'RESOLVED' {org_filt}
            GROUP BY mi.field_section, mi.item_type ORDER BY cnt DESC LIMIT 10
        """), p).mappings().all()

        ti = int(items["total"] or 0) if items else 0
        ri = int(items["resolved"] or 0) if items else 0
        ai = int(items["ai"] or 0) if items else 0

        return {
            "period_days": days,
            "reviews": {
                "total": int(stats["total"] or 0) if stats else 0,
                "completed": int(stats["completed"] or 0) if stats else 0,
                "avg_score": round(_f(stats["avg_score"]) or 0, 1) if stats else 0,
            },
            "score_distribution": {
                "near_complete": int(stats["near_complete"] or 0) if stats else 0,
                "moderate_gaps": int(stats["moderate"] or 0) if stats else 0,
                "high_touch": int(stats["high_touch"] or 0) if stats else 0,
            },
            "items": {
                "total": ti, "resolved": ri, "ai_resolved": ai,
                "escalated": int(items["escalated"] or 0) if items else 0,
                "pending": int(items["pending"] or 0) if items else 0,
                "resolution_rate": round(ri / ti * 100, 1) if ti else 0,
                "ai_rate": round(ai / ri * 100, 1) if ri else 0,
            },
            "top_missing": [{"section": r["field_section"], "type": r["item_type"],
                             "count": int(r["cnt"])} for r in (top or [])],
        }

    def get_review_queue(self, organization_id=None, assigned_to=None, status=None,
                         min_score=None, max_score=None, sort_by="score_asc",
                         limit=25, offset=0) -> dict:
        conds, p = [], {"lim": limit, "off": offset}
        if organization_id:
            conds.append("acr.organization_id = :org")
            p["org"] = organization_id
        if assigned_to:
            conds.append("acr.assigned_to_user_id = :asgn")
            p["asgn"] = assigned_to
        if status:
            conds.append("acr.review_status = :st")
            p["st"] = status.upper()
        else:
            conds.append("acr.review_status IN ('PENDING','IN_PROGRESS','COMPLETED')")
        if min_score is not None:
            conds.append("acr.overall_score >= :mins")
            p["mins"] = min_score
        if max_score is not None:
            conds.append("acr.overall_score <= :maxs")
            p["maxs"] = max_score
        where = "WHERE " + " AND ".join(conds) if conds else ""
        order = {"score_asc": "acr.overall_score ASC NULLS LAST",
                 "score_desc": "acr.overall_score DESC NULLS LAST",
                 "created_desc": "acr.created_at DESC",
                 "updated_desc": "acr.updated_at DESC"}.get(sort_by, "acr.overall_score ASC NULLS LAST")

        total = self.db.execute(text(
            f"SELECT COUNT(*) FROM application_completeness_reviews acr {where}"), p).scalar() or 0

        rows = self.db.execute(text(f"""
            SELECT acr.id, acr.loan_id, acr.review_status, acr.overall_score,
                   acr.complexity_level, acr.next_recommended_action, acr.total_missing_items,
                   acr.assigned_to_user_id, acr.assigned_to_queue,
                   acr.created_at, acr.updated_at,
                   l.loan_number, l.borrower_name, l.loan_officer_name, l.loan_type, l.stage
            FROM application_completeness_reviews acr
            LEFT JOIN loans l ON l.id = acr.loan_id
            {where} ORDER BY {order} LIMIT :lim OFFSET :off
        """), p).mappings().all()

        queue = []
        for r in rows:
            open_ct = self.db.execute(text(
                "SELECT COUNT(*) FROM missing_items WHERE review_id = :rid "
                "AND status IN ('IDENTIFIED','STAGED','SENT_TO_BORROWER','BORROWER_RESPONDED')"
            ), {"rid": r["id"]}).scalar() or 0
            days_since = None
            if r["updated_at"]:
                ua = r["updated_at"]
                if ua.tzinfo is None:
                    ua = ua.replace(tzinfo=timezone.utc)
                days_since = round((_now() - ua).total_seconds() / 86400, 1)
            queue.append({
                "review_id": r["id"], "loan_id": r["loan_id"],
                "loan_number": r["loan_number"], "borrower_name": r["borrower_name"],
                "loan_officer_name": r["loan_officer_name"], "loan_type": r["loan_type"],
                "loan_stage": r["stage"], "review_status": r["review_status"],
                "overall_score": _f(r["overall_score"]),
                "complexity_level": r["complexity_level"],
                "next_action": r["next_recommended_action"],
                "total_missing_items": r["total_missing_items"],
                "open_items": open_ct,
                "assigned_to": r["assigned_to_user_id"],
                "assigned_queue": r["assigned_to_queue"],
                "days_since_update": days_since,
                "created_at": _iso(r["created_at"]),
            })
        return {"total": total, "offset": offset, "limit": limit, "sort_by": sort_by, "queue": queue}


# =============================================================================
# TOP-LEVEL CONVENIENCE FUNCTION
# =============================================================================

def trigger_application_review(
    db: Session,
    loan_id,
    triggered_by: str = "APPLICATION_SUBMITTED",
) -> Dict[str, Any]:
    """Top-level entry point called by routes.

    Looks up the loan's organization, creates an orchestrator, and runs
    the full review pipeline.
    """
    lid = str(loan_id)
    row = db.execute(
        text("SELECT organization_id, loan_officer_id FROM loans WHERE id = :id"),
        {"id": lid},
    ).first()
    if not row:
        return {"error": "loan_not_found", "loan_id": lid}

    org_id = str(row[0]) if row[0] else ""
    user_id = str(row[1]) if row[1] else "system"

    return AppCompletionOrchestrator(db).process_submitted_application(
        loan_id=lid, org_id=org_id, user_id=user_id, triggered_by=triggered_by,
    )
