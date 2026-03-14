"""
Completeness Scoring Engine — Application Completion Orchestrator (ACO)

Takes findings from the Application Review Engine and calculates a weighted
completeness score from 0-100. The score DRIVES operational decisions — it is
not informational, it is the execution engine.

Score composition:
    A. Data Completeness   (60 pts) — field-level coverage per section
    B. Data Consistency    (25 pts) — penalty model for inconsistencies
    C. Document Readiness  (15 pts) — doc staging/mapping status

The overall score maps to a score band which determines the resolution method
(text, hybrid, PA call), PA involvement level, and next automation action.
A separate Resolution Complexity Score (0-10) refines routing within each band.

Usage:
    from services.smart_docs.completeness_scoring_engine import CompletenessScoreEngine

    engine = CompletenessScoreEngine(db=db, org_id="42")
    result = engine.calculate_score(loan_id="100", findings=review_findings)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _get_models():
    """Lazy import to avoid circular dependencies at module load time."""
    from database.models.app_completion import (
        ApplicationCompletenessReview, MissingItem, DocumentStagingRequest,
        ApplicationScoreHistory, ReviewStatus, ScoreChangeReason, ActorType,
    )
    return (ApplicationCompletenessReview, MissingItem, DocumentStagingRequest,
            ApplicationScoreHistory, ReviewStatus, ScoreChangeReason, ActorType)


# =============================================================================
# SECTION WEIGHT CONFIGURATION — Data Completeness bucket (60 pts total)
# =============================================================================

SECTION_WEIGHTS: Dict[str, int] = {
    "borrower_identity":  8,   # name, SSN, DOB, contact, demographics
    "housing_history":    8,   # current/prior addresses, rent/own, monthly cost
    "employment_income": 15,   # employer, income, years, type, pay frequency
    "assets":            10,   # accounts, down payment source, reserves
    "liabilities":        8,   # debts, child support, alimony, obligations
    "reo":                6,   # real estate owned (conditional)
    "loan_property":      5,   # subject property address, loan terms, program
}
_DATA_COMPLETENESS_MAX = 60
assert sum(SECTION_WEIGHTS.values()) == _DATA_COMPLETENESS_MAX

CONDITIONALLY_APPLICABLE_SECTIONS = {"reo"}

# =============================================================================
# CONSISTENCY PENALTY MODEL (25 pts — deduct from starting score)
# =============================================================================

_CONSISTENCY_MAX = 25
INCONSISTENCY_PENALTIES = {
    "minor":    2,   # employer listed but no start date
    "moderate": 5,   # housing expense conflicts with declarations
    "major":   10,   # occupancy vs. owned-property usage conflict
}

# =============================================================================
# DOCUMENT READINESS TIERS (15 pts max)
# =============================================================================

_DOCUMENT_READINESS_MAX = 15
DOCUMENT_READINESS_TIERS = {
    "all_core_mapped": 15,  "core_identified": 10,
    "some_identified":  5,  "none_identified":  0,
}

# =============================================================================
# SCORE BANDS & ACTION ROUTING
# =============================================================================

SCORE_BANDS: List[Dict[str, Any]] = [
    {"min_score": 90, "max_score": 100, "label": "Near-complete",
     "action": "SEND_MINOR_FOLLOWUP", "pa_involvement": "none",
     "complexity_threshold": 2,
     "description": "Send minor follow-up by text. AI handles remaining items."},
    {"min_score": 75, "max_score": 89, "label": "Moderate gaps",
     "action": "AI_TEXT_RESOLUTION", "pa_involvement": "optional",
     "complexity_threshold": 5,
     "description": "AI sends intro/contact card, attempts text resolution, stages doc requests."},
    {"min_score": 50, "max_score": 74, "label": "Meaningful gaps",
     "action": "HYBRID_RESOLUTION", "pa_involvement": "likely",
     "complexity_threshold": 7,
     "description": "AI resolves easy items, requests availability for complex ones, books PA call."},
    {"min_score": 0, "max_score": 49, "label": "High-touch needed",
     "action": "SCHEDULE_PA_CALL", "pa_involvement": "required",
     "complexity_threshold": 10,
     "description": "AI introduces team, explains review call needed, schedules PA call."},
]

# =============================================================================
# RESOLUTION COMPLEXITY FACTORS (0-10 scale)
# =============================================================================

_COMPLEXITY_MAX = 10
_CX_MISSING_THRESHOLD = 10   # >10 missing items triggers this factor
_CX_MISSING_PTS = 3
_CX_DEPENDENT_PTS = 2
_CX_SELF_EMPLOYED_PTS = 2
_CX_MULTI_INCOME_PTS = 1
_CX_NON_QM_PTS = 2
_CX_VA_PTS = 1
_CX_JUMBO_PTS = 1
_CX_EXCEPTION_CAP = 3        # per EXCEPTION item, capped
_CX_CRITICAL_CAP = 3         # per CRITICAL severity, capped

COMPLEXITY_LEVELS = {(0, 2): "text_only", (3, 5): "text_with_escalation", (6, 10): "direct_pa_call"}

# =============================================================================
# SECTION ALIAS MAP — fuzzy matching for upstream naming inconsistencies
# =============================================================================

_SECTION_ALIASES: Dict[str, str] = {
    "borrower": "borrower_identity", "identity": "borrower_identity",
    "contact": "borrower_identity", "demographics": "borrower_identity",
    "housing": "housing_history", "residence": "housing_history", "address": "housing_history",
    "employment": "employment_income", "income": "employment_income", "employer": "employment_income",
    "asset": "assets", "bank_accounts": "assets", "down_payment": "assets", "reserves": "assets",
    "liability": "liabilities", "debt": "liabilities", "debts": "liabilities", "obligations": "liabilities",
    "real_estate_owned": "reo", "property_owned": "reo", "properties": "reo",
    "loan": "loan_property", "property": "loan_property",
    "subject_property": "loan_property", "loan_terms": "loan_property",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _fuzzy_map_section(raw: str, finding: Dict[str, Any]) -> Optional[str]:
    """Try to map an unknown section name to a known section key."""
    normalized = raw.lower().replace("-", "_").replace(" ", "_").strip()
    if normalized in _SECTION_ALIASES:
        return _SECTION_ALIASES[normalized]
    field_name = finding.get("field_name", "").lower()
    for alias, section in _SECTION_ALIASES.items():
        if alias in field_name:
            return section
    return None


def _classify_findings_by_section(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings into their application sections."""
    by_section: Dict[str, List[Dict]] = {s: [] for s in SECTION_WEIGHTS}
    unmapped = 0
    for f in findings:
        section = f.get("section", "").lower().strip()
        if section in by_section:
            by_section[section].append(f)
        else:
            mapped = _fuzzy_map_section(section, f)
            if mapped and mapped in by_section:
                by_section[mapped].append(f)
            else:
                unmapped += 1
    if unmapped:
        logger.warning("completeness_scoring: %d findings unmapped to any section", unmapped)
    return by_section


def _get_score_band(score: float) -> Dict[str, Any]:
    for band in SCORE_BANDS:
        if band["min_score"] <= score <= band["max_score"]:
            return band
    return SCORE_BANDS[-1]


def _get_complexity_level(score: int) -> str:
    for (lo, hi), label in COMPLEXITY_LEVELS.items():
        if lo <= score <= hi:
            return label
    return "direct_pa_call"


def _method_from_complexity(cx: int) -> str:
    if cx <= 2:
        return "TEXT"
    return "HYBRID" if cx <= 5 else "CALL"


# =============================================================================
# COMPLETENESS SCORE ENGINE
# =============================================================================

class CompletenessScoreEngine:
    """
    Calculates and manages application completeness scores.

    Consumes structured findings from the Application Review Engine and
    produces an actionable score that drives the downstream resolution
    workflow (text outreach, hybrid, or PA call scheduling).
    """

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id

    # -----------------------------------------------------------------
    # PUBLIC: calculate_score
    # -----------------------------------------------------------------
    def calculate_score(
        self, loan_id: str, findings: List[Dict[str, Any]], *,
        loan_type: Optional[str] = None, is_self_employed: bool = False,
        has_multiple_income_sources: bool = False, reo_applicable: bool = True,
        document_readiness_tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate completeness score from review findings.

        Each finding dict should have at minimum:
            section, status ("complete"|"missing"|"inconsistent"|"exception"),
            and optionally: severity, field_name, item_type, doc_related,
            doc_staged, dependent, complexity_hint.
        """
        section_scores, data_comp = self._score_data_completeness(findings, reo_applicable)
        consistency_detail, data_cons = self._score_data_consistency(findings)
        doc_detail, doc_ready = self._score_document_readiness(findings, document_readiness_tier)

        overall = round(max(0.0, min(100.0, data_comp + data_cons + doc_ready)), 2)
        band = _get_score_band(overall)

        cx = self._calculate_complexity(
            findings, loan_type=loan_type,
            is_self_employed=is_self_employed,
            has_multiple_income_sources=has_multiple_income_sources,
        )
        resolution = self._build_resolution_recommendation(findings, cx, band)

        return {
            "loan_id": loan_id,
            "org_id": self.org_id,
            "overall_score": overall,
            "data_completeness_score": round(data_comp, 2),
            "data_consistency_score": round(data_cons, 2),
            "document_readiness_score": round(doc_ready, 2),
            "complexity_score": cx,
            "complexity_level": _get_complexity_level(cx),
            "score_band": {
                "label": band["label"], "min_score": band["min_score"],
                "max_score": band["max_score"], "pa_involvement": band["pa_involvement"],
            },
            "next_action": band["action"],
            "next_action_description": band["description"],
            "section_scores": section_scores,
            "consistency_detail": consistency_detail,
            "document_readiness_detail": doc_detail,
            "resolution_recommendation": resolution,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    # -----------------------------------------------------------------
    # PUBLIC: recalculate_after_resolution
    # -----------------------------------------------------------------
    def recalculate_after_resolution(self, review_id: int, resolved_item_id: int) -> Dict[str, Any]:
        """
        Recalculate score after a single item is resolved. Loads the review,
        marks the item, recalculates, records the delta, returns new score.
        """
        (ACR, MI, DSR, ASH, RS, SCR, AT) = _get_models()

        review = (
            self.db.query(ACR)
            .filter(ACR.id == review_id, ACR.organization_id == self.org_id)
            .first()
        )
        if not review:
            logger.warning("recalculate: review %s not found for org %s", review_id, self.org_id)
            return {"error": "review_not_found", "review_id": review_id}

        item = self.db.query(MI).filter(MI.id == resolved_item_id, MI.review_id == review_id).first()
        if not item:
            logger.warning("recalculate: item %s not found in review %s", resolved_item_id, review_id)
            return {"error": "item_not_found", "item_id": resolved_item_id}

        prior_score = float(review.overall_score or 0)

        # Mark resolved
        item.status = "RESOLVED"
        item.resolved_at = datetime.now(timezone.utc)

        # Rebuild findings from all items (resolved ones become status=complete)
        all_items = self.db.query(MI).filter(MI.review_id == review_id).all()
        findings = self._items_to_findings(all_items)

        meta = review.review_metadata or {}
        new_result = self.calculate_score(
            loan_id=str(review.loan_id), findings=findings,
            loan_type=meta.get("loan_type"),
            is_self_employed=meta.get("is_self_employed", False),
            has_multiple_income_sources=meta.get("has_multiple_income_sources", False),
            reo_applicable=meta.get("reo_applicable", True),
        )

        new_score = new_result["overall_score"]
        delta = round(new_score - prior_score, 2)

        # Persist updated scores on the review row
        review.overall_score = new_score
        review.data_completeness_score = new_result["data_completeness_score"]
        review.data_consistency_score = new_result["data_consistency_score"]
        review.document_readiness_score = new_result["document_readiness_score"]
        review.complexity_score = new_result["complexity_score"]
        review.next_action = new_result["next_action"]
        review.last_score_change_at = datetime.now(timezone.utc)

        self.record_score_change(
            review_id=review_id, prior_score=prior_score, new_score=new_score,
            reason=SCR.ITEM_RESOLVED.value,
            reason_detail=f"Item #{resolved_item_id} resolved ({item.field_name or item.item_type})",
            actor_type=AT.SYSTEM.value,
            missing_item_id=resolved_item_id, section_affected=item.section,
        )
        self.db.flush()

        return {
            "review_id": review_id, "resolved_item_id": resolved_item_id,
            "prior_score": prior_score, "new_score": new_score, "delta": delta,
            "new_band": new_result["score_band"], "new_action": new_result["next_action"],
            "new_complexity": new_result["complexity_score"],
            "resolution_recommendation": new_result["resolution_recommendation"],
        }

    # -----------------------------------------------------------------
    # PUBLIC: get_score_trend
    # -----------------------------------------------------------------
    def get_score_trend(self, loan_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get score history for trend display. Returns newest first."""
        (ACR, MI, DSR, ASH, RS, SCR, AT) = _get_models()

        review_ids = (
            self.db.query(ACR.id)
            .filter(ACR.loan_id == loan_id, ACR.organization_id == self.org_id)
            .subquery()
        )
        rows = (
            self.db.query(ASH).filter(ASH.review_id.in_(review_ids))
            .order_by(ASH.changed_at.desc()).limit(limit).all()
        )
        return [
            {
                "id": r.id, "review_id": r.review_id,
                "prior_score": float(r.prior_score) if r.prior_score is not None else None,
                "new_score": float(r.new_score) if r.new_score is not None else None,
                "delta": round(float(r.new_score or 0) - float(r.prior_score or 0), 2),
                "reason": r.reason, "reason_detail": r.reason_detail,
                "actor_type": r.actor_type, "actor_user_id": r.actor_user_id,
                "section_affected": r.section_affected,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ]

    # -----------------------------------------------------------------
    # PUBLIC: record_score_change
    # -----------------------------------------------------------------
    def record_score_change(
        self, review_id: int, prior_score: float, new_score: float,
        reason: str, reason_detail: str, actor_type: str,
        actor_user_id: Optional[str] = None, missing_item_id: Optional[int] = None,
        section_affected: Optional[str] = None,
    ) -> None:
        """Append-only audit trail of every score mutation."""
        (_, _, _, ASH, _, _, _) = _get_models()
        self.db.add(ASH(
            review_id=review_id, prior_score=prior_score, new_score=new_score,
            reason=reason, reason_detail=reason_detail, actor_type=actor_type,
            actor_user_id=actor_user_id, missing_item_id=missing_item_id,
            section_affected=section_affected, changed_at=datetime.now(timezone.utc),
        ))

    # =================================================================
    # INTERNAL: Data Completeness (bucket A — 60 pts max)
    # =================================================================
    def _score_data_completeness(
        self, findings: List[Dict], reo_applicable: bool = True,
    ) -> Tuple[Dict[str, Dict[str, Any]], float]:
        """Score each section based on completed vs required fields."""
        by_section = _classify_findings_by_section(findings)

        # Build effective weights — redistribute REO if not applicable
        eff = dict(SECTION_WEIGHTS)
        if not reo_applicable and "reo" in eff:
            reo_pts = eff.pop("reo")
            rem = sum(eff.values())
            if rem > 0:
                for s in eff:
                    eff[s] = round(eff[s] + reo_pts * (eff[s] / rem), 2)
                # Re-normalize to exactly 60
                scale = _DATA_COMPLETENESS_MAX / sum(eff.values())
                eff = {k: round(v * scale, 2) for k, v in eff.items()}

        section_scores: Dict[str, Dict[str, Any]] = {}
        total = 0.0

        for section, max_pts in eff.items():
            items = by_section.get(section, [])
            n = len(items)
            completed = inconsistent = exception = 0
            for f in items:
                st = (f.get("status") or "").lower()
                if st == "complete":
                    completed += 1
                elif st == "inconsistent":
                    inconsistent += 1
                elif st == "exception":
                    exception += 1
            missing = n - completed - inconsistent - exception

            ratio = (completed / n) if n > 0 else 1.0
            pts = round(ratio * max_pts, 2)
            total += pts
            section_scores[section] = {
                "score": pts, "max": round(max_pts, 2), "pct": round(ratio * 100, 1),
                "completed": completed, "total": n, "missing": missing,
                "inconsistent": inconsistent, "exception": exception,
            }

        if not reo_applicable:
            section_scores["reo"] = {
                "score": 0, "max": 0, "pct": 100.0, "completed": 0, "total": 0,
                "missing": 0, "inconsistent": 0, "exception": 0, "not_applicable": True,
            }

        return section_scores, round(min(total, _DATA_COMPLETENESS_MAX), 2)

    # =================================================================
    # INTERNAL: Data Consistency (bucket B — 25 pts max, penalty model)
    # =================================================================
    def _score_data_consistency(self, findings: List[Dict]) -> Tuple[Dict[str, Any], float]:
        """Start at 25, deduct for each inconsistency finding."""
        score = float(_CONSISTENCY_MAX)
        penalties = []
        for f in findings:
            if (f.get("status") or "").lower() != "inconsistent":
                continue
            sev = (f.get("severity") or "minor").lower()
            pts = INCONSISTENCY_PENALTIES.get(sev, 2)
            score -= pts
            penalties.append({
                "field_name": f.get("field_name"), "section": f.get("section"),
                "severity": sev, "penalty": pts, "description": f.get("description", ""),
            })
        score = max(0.0, score)
        detail = {
            "starting_points": _CONSISTENCY_MAX,
            "total_penalty": round(_CONSISTENCY_MAX - score, 2),
            "final_score": round(score, 2),
            "penalty_count": len(penalties), "penalties": penalties,
        }
        return detail, round(score, 2)

    # =================================================================
    # INTERNAL: Document Readiness (bucket C — 15 pts max)
    # =================================================================
    def _score_document_readiness(
        self, findings: List[Dict], override_tier: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], float]:
        """Score document readiness based on staging status."""
        if override_tier and override_tier in DOCUMENT_READINESS_TIERS:
            s = float(DOCUMENT_READINESS_TIERS[override_tier])
            return {"tier": override_tier, "score": s, "max": _DOCUMENT_READINESS_MAX,
                    "override": True, "doc_findings_analyzed": 0}, s

        doc_findings = [f for f in findings if f.get("doc_related", False)]
        n = len(doc_findings)
        if n == 0:
            tier = "core_identified"
        else:
            staged = sum(1 for f in doc_findings if f.get("doc_staged", False))
            identified = sum(1 for f in doc_findings
                            if f.get("doc_identified", False) or f.get("doc_staged", False))
            sr, ir = staged / n, identified / n
            if sr >= 0.9:
                tier = "all_core_mapped"
            elif ir >= 0.7:
                tier = "core_identified"
            elif ir > 0:
                tier = "some_identified"
            else:
                tier = "none_identified"

        s = float(DOCUMENT_READINESS_TIERS[tier])
        staged_ct = sum(1 for f in doc_findings if f.get("doc_staged", False))
        ident_ct = sum(1 for f in doc_findings
                       if f.get("doc_identified", False) or f.get("doc_staged", False))
        detail = {
            "tier": tier, "score": s, "max": _DOCUMENT_READINESS_MAX,
            "override": False, "doc_findings_analyzed": n,
            "staged_count": staged_ct, "identified_count": ident_ct,
        }
        return detail, s

    # =================================================================
    # INTERNAL: Resolution Complexity Score (0-10)
    # =================================================================
    def _calculate_complexity(
        self, findings: List[Dict], *, loan_type: Optional[str] = None,
        is_self_employed: bool = False, has_multiple_income_sources: bool = False,
    ) -> int:
        """
        Calculate resolution complexity. Drives text vs hybrid vs PA call.

        Factors: missing item count, dependent items, borrower complexity
        (self-employed, multi-income), loan type flags (non-QM, VA, jumbo),
        EXCEPTION items, CRITICAL severity items.
        """
        cx = 0
        missing_ct = sum(1 for f in findings if (f.get("status") or "").lower() == "missing")
        if missing_ct > _CX_MISSING_THRESHOLD:
            cx += _CX_MISSING_PTS
        if any(f.get("dependent", False) for f in findings):
            cx += _CX_DEPENDENT_PTS
        if is_self_employed:
            cx += _CX_SELF_EMPLOYED_PTS
        if has_multiple_income_sources:
            cx += _CX_MULTI_INCOME_PTS

        if loan_type:
            lt = loan_type.lower().replace("-", "_").replace(" ", "_")
            if lt in ("non_qm", "nonqm"):
                cx += _CX_NON_QM_PTS
            elif lt == "va":
                cx += _CX_VA_PTS
            elif lt == "jumbo":
                cx += _CX_JUMBO_PTS

        exc_ct = sum(1 for f in findings
                     if (f.get("item_type") or "").upper() == "EXCEPTION"
                     or (f.get("status") or "").lower() == "exception")
        cx += min(exc_ct, _CX_EXCEPTION_CAP)

        crit_ct = sum(1 for f in findings if (f.get("severity") or "").lower() == "critical")
        cx += min(crit_ct, _CX_CRITICAL_CAP)

        return min(cx, _COMPLEXITY_MAX)

    # =================================================================
    # INTERNAL: Resolution Recommendation
    # =================================================================
    def _build_resolution_recommendation(
        self, findings: List[Dict], cx: int, band: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Classify each unresolved finding by resolution channel."""
        method = _method_from_complexity(cx)
        threshold = band.get("complexity_threshold", 10)
        if cx > threshold:
            method = "HYBRID" if method == "TEXT" else ("CALL" if method == "HYBRID" else method)

        text_ok = call_need = portal = 0
        for f in findings:
            if (f.get("status") or "").lower() == "complete":
                continue
            hint = (f.get("complexity_hint") or "").lower()
            sev = (f.get("severity") or "").lower()
            if f.get("doc_related", False):
                portal += 1
            elif hint == "complex" or sev in ("major", "critical") or f.get("dependent"):
                call_need += 1
            elif hint == "simple" or sev in ("minor", ""):
                text_ok += 1
            elif method == "TEXT":
                text_ok += 1
            else:
                call_need += 1

        parts = []
        if text_ok:
            parts.append(f"{text_ok} items resolvable by text")
        if call_need:
            parts.append(f"{call_need} items need PA call")
        if portal:
            parts.append(f"{portal} documents via borrower portal")

        return {
            "method": method,
            "reason": "; ".join(parts) or "No outstanding items",
            "estimated_text_resolvable": text_ok,
            "estimated_call_needed": call_need,
            "estimated_portal_docs": portal,
            "complexity_score": cx, "band_threshold": threshold,
            "threshold_exceeded": cx > threshold,
        }

    # =================================================================
    # INTERNAL: Convert MissingItem ORM objects to findings dicts
    # =================================================================
    def _items_to_findings(self, items: list) -> List[Dict[str, Any]]:
        """Convert MissingItem ORM objects back into finding dicts for scoring."""
        findings = []
        for item in items:
            st = (item.status or "OPEN").upper()
            if st == "RESOLVED":
                f_status = "complete"
            elif st == "EXCEPTION":
                f_status = "exception"
            elif hasattr(item, "item_type") and (item.item_type or "").upper() == "INCONSISTENCY":
                f_status = "inconsistent"
            else:
                f_status = "missing"
            findings.append({
                "section": item.section or "",
                "status": f_status,
                "severity": getattr(item, "severity", None) or "minor",
                "field_name": getattr(item, "field_name", None) or "",
                "item_type": getattr(item, "item_type", None) or "",
                "doc_related": getattr(item, "doc_related", False) or False,
                "doc_staged": getattr(item, "doc_staged", False) or False,
                "doc_identified": getattr(item, "doc_identified", False) or False,
                "dependent": getattr(item, "dependent", False) or False,
                "complexity_hint": getattr(item, "complexity_hint", None) or "",
                "description": getattr(item, "description", None) or "",
            })
        return findings


# =============================================================================
# STANDALONE HELPERS (no DB access needed)
# =============================================================================

def quick_score(findings: List[Dict[str, Any]], reo_applicable: bool = True) -> float:
    """Quick completeness score without DB. Useful for preview / dry-run."""
    engine = CompletenessScoreEngine.__new__(CompletenessScoreEngine)
    engine.db = None
    engine.org_id = "__preview__"
    _, dc = engine._score_data_completeness(findings, reo_applicable)
    _, cs = engine._score_data_consistency(findings)
    _, dr = engine._score_document_readiness(findings, None)
    return round(max(0.0, min(100.0, dc + cs + dr)), 2)


def get_band_for_score(score: float) -> Dict[str, Any]:
    """Get the score band dict for a raw score value."""
    return _get_score_band(score)


def get_recommended_action(score: float) -> str:
    """Get the recommended next action string for a score."""
    return _get_score_band(score)["action"]
