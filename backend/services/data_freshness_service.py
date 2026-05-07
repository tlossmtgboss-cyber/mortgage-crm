"""
Data Freshness Monitoring Service
==================================
Enterprise Readiness Domain 3 — Data Quality: freshness alerts for stale leads,
stale pipeline loans, outdated integration sync timestamps, and required-field
completeness.

All queries filter by organization_id for multi-tenant isolation.

Usage:
    from services.data_freshness_service import (
        check_stale_leads,
        check_stale_pipeline,
        check_sync_freshness,
        check_required_fields,
        generate_data_quality_report,
    )

    report = generate_data_quality_report(db, org_id=1)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import func, and_, or_, case, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Terminal lead stages — leads in these stages are not expected to progress
_TERMINAL_LEAD_STAGES = frozenset({
    "Closed", "Withdrawn", "Does Not Qualify", "Do Not Call", "Funded",
    "CLOSED", "WITHDRAWN", "DOES_NOT_QUALIFY", "DO_NOT_CALL", "FUNDED",
})

# Terminal loan stages — loans in these stages are not expected to progress
_TERMINAL_LOAN_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
})


def check_stale_leads(db: Session, org_id: int, days: int = 30) -> Dict[str, Any]:
    """
    Find leads with no activity in the last N days.

    A lead is considered stale if:
    - It is NOT in a terminal stage (Closed, Withdrawn, etc.)
    - It is NOT soft-deleted
    - Its most recent touchpoint (MAX of last_contact, updated_at, last_workflow_action)
      is older than `days` days ago

    Returns:
        {
            "stale_count": int,
            "stale_lead_ids": list[int],
            "total_active_leads": int,
            "stale_percentage": float,
            "threshold_days": int,
            "checked_at": str (ISO),
        }
    """
    from database.models.lead_loan import Lead

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Base filter: org, not deleted, not terminal
        base_filter = and_(
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
            ~Lead.stage.in_(_TERMINAL_LEAD_STAGES),
        )

        total_active = db.query(func.count(Lead.id)).filter(base_filter).scalar() or 0

        # Stale = most recent touchpoint older than cutoff
        # Use COALESCE across last_contact, updated_at, last_workflow_action, created_at
        latest_touch = func.greatest(
            func.coalesce(Lead.last_contact, Lead.created_at),
            func.coalesce(Lead.updated_at, Lead.created_at),
            func.coalesce(Lead.last_workflow_action, Lead.created_at),
        )

        stale_query = (
            db.query(Lead.id)
            .filter(base_filter)
            .filter(latest_touch < cutoff)
            .order_by(latest_touch.asc())
            .limit(500)
        )
        stale_rows = stale_query.all()
        stale_ids = [row[0] for row in stale_rows]

        # Get true stale count (without limit)
        stale_count = (
            db.query(func.count(Lead.id))
            .filter(base_filter)
            .filter(latest_touch < cutoff)
            .scalar() or 0
        )

        stale_pct = round((stale_count / total_active * 100), 2) if total_active > 0 else 0.0

        return {
            "stale_count": stale_count,
            "stale_lead_ids": stale_ids,
            "total_active_leads": total_active,
            "stale_percentage": stale_pct,
            "threshold_days": days,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"check_stale_leads failed for org {org_id}: {e}")
        return {
            "stale_count": 0,
            "stale_lead_ids": [],
            "total_active_leads": 0,
            "stale_percentage": 0.0,
            "threshold_days": days,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


def check_stale_pipeline(db: Session, org_id: int, days: int = 60) -> Dict[str, Any]:
    """
    Find active loans stuck in the same stage for more than N days.

    A loan is considered stale if:
    - It is NOT in a terminal stage (FUNDED, CANCELLED, etc.)
    - It is NOT soft-deleted
    - Its stage_changed_at (or created_at if stage_changed_at is null) is older
      than `days` days ago

    Returns:
        {
            "stale_count": int,
            "stale_loans": list[{id, loan_number, stage, days_in_current_stage}],
            "total_active_loans": int,
            "stale_percentage": float,
            "threshold_days": int,
            "by_stage": dict[str, int],   # count of stale loans per stage
            "checked_at": str (ISO),
        }
    """
    from database.models.lead_loan import Loan

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    now = datetime.now(timezone.utc)

    try:
        base_filter = and_(
            Loan.organization_id == org_id,
            Loan.deleted_at.is_(None),
            ~Loan.stage.in_(_TERMINAL_LOAN_STAGES),
        )

        total_active = db.query(func.count(Loan.id)).filter(base_filter).scalar() or 0

        # stage_changed_at tracks when the stage last changed; fall back to created_at
        stage_anchor = func.coalesce(Loan.stage_changed_at, Loan.created_at)

        stale_query = (
            db.query(
                Loan.id,
                Loan.loan_number,
                Loan.stage,
                stage_anchor.label("stage_since"),
            )
            .filter(base_filter)
            .filter(stage_anchor < cutoff)
            .order_by(stage_anchor.asc())
            .limit(500)
        )
        stale_rows = stale_query.all()

        stale_loans: List[Dict[str, Any]] = []
        by_stage: Dict[str, int] = {}
        for row in stale_rows:
            stage_since = row.stage_since
            if stage_since and stage_since.tzinfo is None:
                stage_since = stage_since.replace(tzinfo=timezone.utc)
            days_stuck = (now - stage_since).days if stage_since else days
            stale_loans.append({
                "id": row.id,
                "loan_number": row.loan_number,
                "stage": row.stage,
                "days_in_current_stage": days_stuck,
            })
            by_stage[row.stage] = by_stage.get(row.stage, 0) + 1

        # True count without limit
        stale_count = (
            db.query(func.count(Loan.id))
            .filter(base_filter)
            .filter(stage_anchor < cutoff)
            .scalar() or 0
        )

        stale_pct = round((stale_count / total_active * 100), 2) if total_active > 0 else 0.0

        return {
            "stale_count": stale_count,
            "stale_loans": stale_loans,
            "total_active_loans": total_active,
            "stale_percentage": stale_pct,
            "threshold_days": days,
            "by_stage": by_stage,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"check_stale_pipeline failed for org {org_id}: {e}")
        return {
            "stale_count": 0,
            "stale_loans": [],
            "total_active_loans": 0,
            "stale_percentage": 0.0,
            "threshold_days": days,
            "by_stage": {},
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


def check_sync_freshness(db: Session, org_id: int) -> Dict[str, Any]:
    """
    For each integration (Salesforce, Encompass), check last_synced_at vs
    the expected sync interval.

    Data sources:
    - Encompass: EncompassConfig.last_sync_at + sync_frequency_minutes
    - Salesforce: OAuthToken (provider='salesforce') .last_sync_at + sync_frequency_minutes
    - Follow Up Boss: max(Lead.fub_last_synced_at) for leads in the org

    Returns:
        {
            "integrations": {
                "<name>": {
                    "connected": bool,
                    "last_sync_at": str|None,
                    "expected_interval_minutes": int|None,
                    "minutes_since_last_sync": int|None,
                    "is_overdue": bool,
                    "status": "healthy"|"overdue"|"stale"|"disconnected",
                }
            },
            "checked_at": str (ISO),
        }
    """
    now = datetime.now(timezone.utc)
    integrations: Dict[str, Dict[str, Any]] = {}

    # --- Encompass ---
    try:
        from database.models.encompass_config import EncompassConfig

        ec = (
            db.query(EncompassConfig)
            .filter(
                EncompassConfig.organization_id == org_id,
                EncompassConfig.is_active == True,  # noqa: E712
            )
            .first()
        )
        if ec:
            last_sync = ec.last_sync_at
            if last_sync and last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            interval = ec.sync_frequency_minutes or 60
            minutes_since = int((now - last_sync).total_seconds() / 60) if last_sync else None
            is_overdue = (minutes_since is not None and minutes_since > interval * 2)
            integrations["encompass"] = {
                "connected": True,
                "last_sync_at": last_sync.isoformat() if last_sync else None,
                "expected_interval_minutes": interval,
                "minutes_since_last_sync": minutes_since,
                "is_overdue": is_overdue,
                "health_status": ec.health_status,
                "status": (
                    "overdue" if is_overdue else
                    "stale" if (minutes_since and minutes_since > interval) else
                    "healthy"
                ) if last_sync else "never_synced",
            }
        else:
            integrations["encompass"] = {
                "connected": False,
                "last_sync_at": None,
                "expected_interval_minutes": None,
                "minutes_since_last_sync": None,
                "is_overdue": False,
                "status": "disconnected",
            }
    except Exception as e:
        logger.exception(f"check_sync_freshness(encompass) failed for org {org_id}: {e}")
        integrations["encompass"] = {
            "connected": False,
            "status": "error",
            "error": str(e),
        }

    # --- Salesforce (via OAuthToken) ---
    try:
        from database.models.oauth_token import OAuthToken

        sf_token = (
            db.query(OAuthToken)
            .filter(
                OAuthToken.organization_id == org_id,
                OAuthToken.provider == "salesforce",
                OAuthToken.is_active == True,  # noqa: E712
            )
            .first()
        )
        if sf_token:
            last_sync = sf_token.last_sync_at
            if last_sync and last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            interval = sf_token.sync_frequency_minutes or 15
            minutes_since = int((now - last_sync).total_seconds() / 60) if last_sync else None
            is_overdue = (minutes_since is not None and minutes_since > interval * 2)
            integrations["salesforce"] = {
                "connected": True,
                "last_sync_at": last_sync.isoformat() if last_sync else None,
                "expected_interval_minutes": interval,
                "minutes_since_last_sync": minutes_since,
                "is_overdue": is_overdue,
                "status": (
                    "overdue" if is_overdue else
                    "stale" if (minutes_since and minutes_since > interval) else
                    "healthy"
                ) if last_sync else "never_synced",
            }
        else:
            integrations["salesforce"] = {
                "connected": False,
                "last_sync_at": None,
                "expected_interval_minutes": None,
                "minutes_since_last_sync": None,
                "is_overdue": False,
                "status": "disconnected",
            }
    except Exception as e:
        logger.exception(f"check_sync_freshness(salesforce) failed for org {org_id}: {e}")
        integrations["salesforce"] = {
            "connected": False,
            "status": "error",
            "error": str(e),
        }

    # --- Follow Up Boss (last fub_last_synced_at across leads) ---
    try:
        from database.models.lead_loan import Lead

        fub_result = (
            db.query(func.max(Lead.fub_last_synced_at))
            .filter(
                Lead.organization_id == org_id,
                Lead.fub_last_synced_at.isnot(None),
            )
            .scalar()
        )
        if fub_result:
            last_sync = fub_result
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            # FUB has no formal interval config — use 24h as baseline
            interval = 1440  # 24 hours
            minutes_since = int((now - last_sync).total_seconds() / 60)
            is_overdue = minutes_since > interval * 2
            integrations["follow_up_boss"] = {
                "connected": True,
                "last_sync_at": last_sync.isoformat(),
                "expected_interval_minutes": interval,
                "minutes_since_last_sync": minutes_since,
                "is_overdue": is_overdue,
                "status": (
                    "overdue" if is_overdue else
                    "stale" if minutes_since > interval else
                    "healthy"
                ),
            }
        else:
            integrations["follow_up_boss"] = {
                "connected": False,
                "last_sync_at": None,
                "expected_interval_minutes": None,
                "minutes_since_last_sync": None,
                "is_overdue": False,
                "status": "disconnected",
            }
    except Exception as e:
        logger.exception(f"check_sync_freshness(fub) failed for org {org_id}: {e}")
        integrations["follow_up_boss"] = {
            "connected": False,
            "status": "error",
            "error": str(e),
        }

    return {
        "integrations": integrations,
        "checked_at": now.isoformat(),
    }


def check_required_fields(db: Session, org_id: int) -> Dict[str, Any]:
    """
    Percentage of leads with null required fields (email, phone, first_name, last_name).

    Only non-deleted leads are counted.

    Returns:
        {
            "total_leads": int,
            "fields": {
                "email":      {"missing_count": int, "missing_percentage": float},
                "phone":      {"missing_count": int, "missing_percentage": float},
                "first_name": {"missing_count": int, "missing_percentage": float},
                "last_name":  {"missing_count": int, "missing_percentage": float},
            },
            "overall_completeness": float,  # 0-100, average field presence
            "leads_fully_complete": int,     # leads with ALL four fields present
            "fully_complete_percentage": float,
            "checked_at": str (ISO),
        }
    """
    from database.models.lead_loan import Lead

    try:
        base_filter = and_(
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
        )

        total = db.query(func.count(Lead.id)).filter(base_filter).scalar() or 0

        if total == 0:
            empty_field = {"missing_count": 0, "missing_percentage": 0.0}
            return {
                "total_leads": 0,
                "fields": {
                    "email": empty_field.copy(),
                    "phone": empty_field.copy(),
                    "first_name": empty_field.copy(),
                    "last_name": empty_field.copy(),
                },
                "overall_completeness": 100.0,
                "leads_fully_complete": 0,
                "fully_complete_percentage": 100.0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        # Count missing for each field
        # "missing" = NULL or empty string
        def _null_or_empty(col):
            return or_(col.is_(None), col == "")

        missing_email = (
            db.query(func.count(Lead.id))
            .filter(base_filter, _null_or_empty(Lead.email))
            .scalar() or 0
        )
        missing_phone = (
            db.query(func.count(Lead.id))
            .filter(base_filter, _null_or_empty(Lead.phone))
            .scalar() or 0
        )
        missing_first = (
            db.query(func.count(Lead.id))
            .filter(base_filter, _null_or_empty(Lead.first_name))
            .scalar() or 0
        )
        missing_last = (
            db.query(func.count(Lead.id))
            .filter(base_filter, _null_or_empty(Lead.last_name))
            .scalar() or 0
        )

        # Leads with ALL four fields present
        fully_complete = (
            db.query(func.count(Lead.id))
            .filter(
                base_filter,
                ~_null_or_empty(Lead.email),
                ~_null_or_empty(Lead.phone),
                ~_null_or_empty(Lead.first_name),
                ~_null_or_empty(Lead.last_name),
            )
            .scalar() or 0
        )

        def _pct(missing):
            return round(missing / total * 100, 2)

        # Overall completeness: average of (1 - missing_pct) across all four fields
        present_pcts = [
            (total - missing_email) / total * 100,
            (total - missing_phone) / total * 100,
            (total - missing_first) / total * 100,
            (total - missing_last) / total * 100,
        ]
        overall = round(sum(present_pcts) / len(present_pcts), 2)

        return {
            "total_leads": total,
            "fields": {
                "email": {"missing_count": missing_email, "missing_percentage": _pct(missing_email)},
                "phone": {"missing_count": missing_phone, "missing_percentage": _pct(missing_phone)},
                "first_name": {"missing_count": missing_first, "missing_percentage": _pct(missing_first)},
                "last_name": {"missing_count": missing_last, "missing_percentage": _pct(missing_last)},
            },
            "overall_completeness": overall,
            "leads_fully_complete": fully_complete,
            "fully_complete_percentage": round(fully_complete / total * 100, 2),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"check_required_fields failed for org {org_id}: {e}")
        empty_field = {"missing_count": 0, "missing_percentage": 0.0}
        return {
            "total_leads": 0,
            "fields": {
                "email": empty_field.copy(),
                "phone": empty_field.copy(),
                "first_name": empty_field.copy(),
                "last_name": empty_field.copy(),
            },
            "overall_completeness": 0.0,
            "leads_fully_complete": 0,
            "fully_complete_percentage": 0.0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


def generate_data_quality_report(db: Session, org_id: int) -> Dict[str, Any]:
    """
    Aggregate all freshness and completeness checks into a single quality score (0-100).

    Scoring breakdown (100 points total, deductions for issues):
    - Stale leads:          up to -25 points (proportional to stale %)
    - Stale pipeline loans: up to -25 points (proportional to stale %)
    - Sync freshness:       up to -25 points (per-integration penalties)
    - Required fields:      up to -25 points (inverse of completeness)

    Returns:
        {
            "score": int (0-100),
            "grade": "A"|"B"|"C"|"D"|"F",
            "stale_leads": <check_stale_leads result>,
            "stale_pipeline": <check_stale_pipeline result>,
            "sync_freshness": <check_sync_freshness result>,
            "required_fields": <check_required_fields result>,
            "deductions": {
                "stale_leads": float,
                "stale_pipeline": float,
                "sync_freshness": float,
                "required_fields": float,
            },
            "generated_at": str (ISO),
        }
    """
    stale_leads = check_stale_leads(db, org_id)
    stale_pipeline = check_stale_pipeline(db, org_id)
    sync_freshness = check_sync_freshness(db, org_id)
    required_fields = check_required_fields(db, org_id)

    deductions: Dict[str, float] = {}

    # --- Stale leads deduction (up to 25 points) ---
    stale_lead_pct = stale_leads.get("stale_percentage", 0.0)
    deductions["stale_leads"] = round(min(stale_lead_pct / 100 * 25, 25), 2)

    # --- Stale pipeline deduction (up to 25 points) ---
    stale_pipe_pct = stale_pipeline.get("stale_percentage", 0.0)
    deductions["stale_pipeline"] = round(min(stale_pipe_pct / 100 * 25, 25), 2)

    # --- Sync freshness deduction (up to 25 points) ---
    sync_penalty = 0.0
    integrations = sync_freshness.get("integrations", {})
    connected_count = sum(
        1 for v in integrations.values()
        if v.get("connected", False)
    )
    if connected_count > 0:
        per_integration_weight = 25.0 / connected_count
        for name, info in integrations.items():
            if not info.get("connected", False):
                continue
            status = info.get("status", "healthy")
            if status == "overdue":
                sync_penalty += per_integration_weight
            elif status in ("stale", "never_synced"):
                sync_penalty += per_integration_weight * 0.5
    # No connected integrations = no penalty (they just don't use them)
    deductions["sync_freshness"] = round(min(sync_penalty, 25), 2)

    # --- Required fields deduction (up to 25 points) ---
    completeness = required_fields.get("overall_completeness", 100.0)
    deductions["required_fields"] = round((100 - completeness) / 100 * 25, 2)

    total_deductions = sum(deductions.values())
    score = max(0, round(100 - total_deductions))

    grade = (
        "A" if score >= 90 else
        "B" if score >= 80 else
        "C" if score >= 70 else
        "D" if score >= 60 else
        "F"
    )

    return {
        "score": score,
        "grade": grade,
        "stale_leads": stale_leads,
        "stale_pipeline": stale_pipeline,
        "sync_freshness": sync_freshness,
        "required_fields": required_fields,
        "deductions": deductions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
