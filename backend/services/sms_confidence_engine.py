"""
SMS AI Confidence Engine — Adaptive auto-response scoring.

As loan officers accept more AI-suggested SMS replies, confidence grows.
Once confidence crosses the org/user threshold AND auto-respond is enabled,
Aria can send replies without waiting for human approval.

Confidence ramps gradually via sigmoid smoothing so a handful of early
accepts can't push the score to 90%.  The floor is 5 and the ceiling is 95
-- there is always room for the LO to intervene.

Tables used:
    - sms_ai_confidence   (UPSERT per org/user/category)
    - sms_ai_audit_log    (append-only settings-change + trend history)

Usage:
    from services.sms_confidence_engine import (
        record_outcome,
        get_confidence,
        should_auto_respond,
        calculate_confidence_score,
    )

    updated = record_outcome(db, org_id, user_id, "rate_inquiry", "accepted")
    if should_auto_respond(db, org_id, "rate_inquiry"):
        # send without human approval
        ...
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_SCORE = 20.0
_DEFAULT_THRESHOLD = 80
_MIN_RECOMMENDATIONS_FOR_AUTO = 20
_SCORE_FLOOR = 5.0
_SCORE_CEILING = 95.0
_THRESHOLD_MIN = 50
_THRESHOLD_MAX = 99

# Sigmoid ramp constant — needs ~30+ samples to approach full weight
_SIGMOID_TAU = 15


# ---------------------------------------------------------------------------
# Pure calculation
# ---------------------------------------------------------------------------

def calculate_confidence_score(
    accepted: int,
    edited: int,
    rejected: int,
    total: int,
) -> float:
    """Return a smoothed confidence score between 5.0 and 95.0.

    Weights:
        accepted = 1.0  (LO fully agreed)
        edited   = 0.6  (LO mostly agreed but tweaked)
        rejected = 0.0  (LO disagreed)

    Sigmoid smoothing prevents the score from jumping to 90% after only
    a few accepts.  At ~30 total recommendations the smoothing factor
    is ~0.86; at 50 it is ~0.96.
    """
    denominator = max(total, 1)
    raw = (accepted * 1.0 + edited * 0.6) / denominator * 100.0

    # Sigmoid ramp: 1 - e^(-total / tau)
    smoothing = 1.0 - math.exp(-total / _SIGMOID_TAU)
    smoothed = raw * smoothing

    return max(_SCORE_FLOOR, min(_SCORE_CEILING, round(smoothed, 2)))


# ---------------------------------------------------------------------------
# Record an outcome (accept / edit / reject)
# ---------------------------------------------------------------------------

def record_outcome(
    db: Session,
    organization_id: int,
    user_id: Optional[int],
    category: str,
    outcome: str,
) -> dict:
    """UPSERT a recommendation outcome and recalculate confidence.

    Parameters
    ----------
    outcome : str
        One of ``'accepted'``, ``'edited'``, ``'rejected'``.

    Returns
    -------
    dict  Updated confidence record.
    """
    if outcome not in ("accepted", "edited", "rejected"):
        raise ValueError(f"outcome must be accepted/edited/rejected, got {outcome!r}")

    col = f"{outcome}_count"  # accepted_count | edited_count | rejected_count

    try:
        now = datetime.now(timezone.utc)
        init_score = calculate_confidence_score(
            int(outcome == "accepted"),
            int(outcome == "edited"),
            int(outcome == "rejected"),
            1,
        )

        row = db.execute(
            text("""
                WITH upserted AS (
                    INSERT INTO sms_ai_confidence
                        (organization_id, user_id, category,
                         accepted_count, edited_count, rejected_count,
                         total_recommendations, confidence_score,
                         auto_respond_enabled, auto_respond_threshold,
                         created_at, updated_at)
                    VALUES
                        (:org_id, :user_id, :category,
                         :init_accepted, :init_edited, :init_rejected,
                         1, :init_score,
                         false, :default_threshold,
                         :now, :now)
                    ON CONFLICT (organization_id, COALESCE(user_id, 0), category)
                    DO UPDATE SET
                        {col} = sms_ai_confidence.{col} + 1,
                        total_recommendations = sms_ai_confidence.total_recommendations + 1,
                        updated_at = :now
                    RETURNING accepted_count, edited_count, rejected_count, total_recommendations
                )
                SELECT accepted_count, edited_count, rejected_count, total_recommendations
                FROM upserted
            """.format(col=col)),
            {
                "org_id": organization_id,
                "user_id": user_id,
                "category": category,
                "init_accepted": 1 if outcome == "accepted" else 0,
                "init_edited": 1 if outcome == "edited" else 0,
                "init_rejected": 1 if outcome == "rejected" else 0,
                "init_score": init_score,
                "default_threshold": _DEFAULT_THRESHOLD,
                "now": now,
            },
        ).mappings().fetchone()

        if row:
            new_score = calculate_confidence_score(
                row["accepted_count"],
                row["edited_count"],
                row["rejected_count"],
                row["total_recommendations"],
            )
            db.execute(
                text("""
                    UPDATE sms_ai_confidence
                    SET confidence_score = :score, updated_at = :now
                    WHERE organization_id = :org_id
                      AND COALESCE(user_id, 0) = COALESCE(:user_id, 0)
                      AND category = :category
                """),
                {
                    "score": new_score,
                    "now": now,
                    "org_id": organization_id,
                    "user_id": user_id,
                    "category": category,
                },
            )

        db.flush()
        return get_confidence(db, organization_id, category, user_id=user_id)

    except Exception as e:
        logger.exception(
            "Failed to record SMS confidence outcome org=%s user=%s cat=%s: %s",
            organization_id, user_id, category, e,
        )
        # Return defaults so callers don't crash
        return _default_confidence(category)


# ---------------------------------------------------------------------------
# Read confidence
# ---------------------------------------------------------------------------

def get_confidence(
    db: Session,
    organization_id: int,
    category: str,
    user_id: Optional[int] = None,
) -> dict:
    """Return the confidence record for an org + category (optionally per-user)."""
    try:
        row = db.execute(
            text("""
                SELECT confidence_score, auto_respond_enabled, auto_respond_threshold,
                       total_recommendations, accepted_count, edited_count, rejected_count,
                       category
                FROM sms_ai_confidence
                WHERE organization_id = :org_id
                  AND COALESCE(user_id, 0) = COALESCE(:user_id, 0)
                  AND category = :category
            """),
            {"org_id": organization_id, "user_id": user_id, "category": category},
        ).mappings().fetchone()

        if row:
            return dict(row)
        return _default_confidence(category)

    except Exception as e:
        logger.exception(
            "Failed to read SMS confidence org=%s cat=%s: %s",
            organization_id, category, e,
        )
        return _default_confidence(category)


def get_all_confidence(
    db: Session,
    organization_id: int,
    user_id: Optional[int] = None,
) -> List[dict]:
    """Return confidence records for ALL categories for this org."""
    try:
        rows = db.execute(
            text("""
                SELECT confidence_score, auto_respond_enabled, auto_respond_threshold,
                       total_recommendations, accepted_count, edited_count, rejected_count,
                       category
                FROM sms_ai_confidence
                WHERE organization_id = :org_id
                  AND COALESCE(user_id, 0) = COALESCE(:user_id, 0)
                ORDER BY category
            """),
            {"org_id": organization_id, "user_id": user_id},
        ).mappings().fetchall()

        return [dict(r) for r in rows]

    except Exception as e:
        logger.exception(
            "Failed to read all SMS confidence org=%s: %s",
            organization_id, e,
        )
        return []


# ---------------------------------------------------------------------------
# Auto-respond gate
# ---------------------------------------------------------------------------

def should_auto_respond(
    db: Session,
    organization_id: int,
    category: str,
    user_id: Optional[int] = None,
) -> bool:
    """Return True only when ALL conditions are met:

    1. auto_respond_enabled is True
    2. confidence_score >= auto_respond_threshold
    3. total_recommendations >= 20  (prevent premature automation)
    """
    conf = get_confidence(db, organization_id, category, user_id=user_id)
    if not conf.get("auto_respond_enabled"):
        return False
    if conf.get("total_recommendations", 0) < _MIN_RECOMMENDATIONS_FOR_AUTO:
        return False
    return conf.get("confidence_score", 0) >= conf.get("auto_respond_threshold", _DEFAULT_THRESHOLD)


# ---------------------------------------------------------------------------
# Settings update
# ---------------------------------------------------------------------------

def update_settings(
    db: Session,
    organization_id: int,
    category: str,
    user_id: Optional[int] = None,
    auto_respond_enabled: Optional[bool] = None,
    auto_respond_threshold: Optional[int] = None,
) -> dict:
    """Update auto-respond settings for a category.

    Validates threshold is between 50-99.  Logs every change to
    ``sms_ai_audit_log``.
    """
    if auto_respond_threshold is not None:
        if not (_THRESHOLD_MIN <= auto_respond_threshold <= _THRESHOLD_MAX):
            raise ValueError(
                f"auto_respond_threshold must be between {_THRESHOLD_MIN} and "
                f"{_THRESHOLD_MAX}, got {auto_respond_threshold}"
            )

    try:
        # Ensure a row exists (INSERT ... ON CONFLICT DO NOTHING)
        db.execute(
            text("""
                INSERT INTO sms_ai_confidence
                    (organization_id, user_id, category,
                     accepted_count, edited_count, rejected_count,
                     total_recommendations, confidence_score,
                     auto_respond_enabled, auto_respond_threshold,
                     created_at, updated_at)
                VALUES
                    (:org_id, :user_id, :category,
                     0, 0, 0, 0, :default_score,
                     false, :default_threshold,
                     :now, :now)
                ON CONFLICT (organization_id, COALESCE(user_id, 0), category)
                DO NOTHING
            """),
            {
                "org_id": organization_id,
                "user_id": user_id,
                "category": category,
                "default_score": _DEFAULT_SCORE,
                "default_threshold": _DEFAULT_THRESHOLD,
                "now": datetime.now(timezone.utc),
            },
        )

        # Build dynamic SET clause for only supplied fields
        updates = []
        params: Dict = {
            "org_id": organization_id,
            "user_id": user_id,
            "category": category,
            "now": datetime.now(timezone.utc),
        }

        if auto_respond_enabled is not None:
            updates.append("auto_respond_enabled = :enabled")
            params["enabled"] = auto_respond_enabled

        if auto_respond_threshold is not None:
            updates.append("auto_respond_threshold = :threshold")
            params["threshold"] = auto_respond_threshold

        if updates:
            updates.append("updated_at = :now")
            db.execute(
                text("""
                    UPDATE sms_ai_confidence
                    SET {sets}
                    WHERE organization_id = :org_id
                      AND COALESCE(user_id, 0) = COALESCE(:user_id, 0)
                      AND category = :category
                """.format(sets=", ".join(updates))),
                params,
            )

            # Audit log
            _write_audit_log(
                db,
                organization_id=organization_id,
                user_id=user_id,
                category=category,
                action="settings_change",
                details={
                    **({"auto_respond_enabled": auto_respond_enabled} if auto_respond_enabled is not None else {}),
                    **({"auto_respond_threshold": auto_respond_threshold} if auto_respond_threshold is not None else {}),
                },
            )

        db.flush()
        return get_confidence(db, organization_id, category, user_id=user_id)

    except Exception as e:
        logger.exception(
            "Failed to update SMS confidence settings org=%s cat=%s: %s",
            organization_id, category, e,
        )
        return _default_confidence(category)


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

def get_confidence_trend(
    db: Session,
    organization_id: int,
    category: Optional[str] = None,
    days: int = 30,
) -> List[dict]:
    """Return daily confidence trend from the audit log.

    Each entry: ``{date, score, accepted, edited, rejected}``.
    """
    try:
        cat_filter = "AND category = :category" if category else ""
        params: Dict = {"org_id": organization_id, "days": days}
        if category:
            params["category"] = category

        rows = db.execute(
            text("""
                SELECT
                    DATE(created_at) AS date,
                    COUNT(*) FILTER (WHERE action = 'accepted')  AS accepted,
                    COUNT(*) FILTER (WHERE action = 'edited')    AS edited,
                    COUNT(*) FILTER (WHERE action = 'rejected')  AS rejected
                FROM sms_ai_audit_log
                WHERE organization_id = :org_id
                  AND action IN ('accepted', 'edited', 'rejected')
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :days)
                  {cat_filter}
                GROUP BY DATE(created_at)
                ORDER BY DATE(created_at)
            """.format(cat_filter=cat_filter)),
            params,
        ).mappings().fetchall()

        results = []
        for r in rows:
            acc = r["accepted"]
            edi = r["edited"]
            rej = r["rejected"]
            total = acc + edi + rej
            results.append({
                "date": str(r["date"]),
                "score": calculate_confidence_score(acc, edi, rej, total),
                "accepted": acc,
                "edited": edi,
                "rejected": rej,
            })
        return results

    except Exception as e:
        logger.exception(
            "Failed to read SMS confidence trend org=%s: %s",
            organization_id, e,
        )
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _default_confidence(category: str) -> dict:
    """Return a default confidence dict when no DB record exists."""
    return {
        "category": category,
        "confidence_score": _DEFAULT_SCORE,
        "auto_respond_enabled": False,
        "auto_respond_threshold": _DEFAULT_THRESHOLD,
        "total_recommendations": 0,
        "accepted_count": 0,
        "edited_count": 0,
        "rejected_count": 0,
    }


def _write_audit_log(
    db: Session,
    organization_id: int,
    user_id: Optional[int],
    category: str,
    action: str,
    details: Optional[dict] = None,
) -> None:
    """Append a row to sms_ai_audit_log (best-effort, never raises)."""
    try:
        import json as _json

        db.execute(
            text("""
                INSERT INTO sms_ai_audit_log
                    (organization_id, user_id, category, action, details, created_at)
                VALUES
                    (:org_id, :user_id, :category, :action, :details, :now)
            """),
            {
                "org_id": organization_id,
                "user_id": user_id,
                "category": category,
                "action": action,
                "details": _json.dumps(details) if details else None,
                "now": datetime.now(timezone.utc),
            },
        )
        db.flush()
    except Exception as e:
        logger.warning("Could not write SMS audit log: %s", e)
