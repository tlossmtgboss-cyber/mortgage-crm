"""
Pipeline Alerts Routes

GET /api/v1/pipeline/alerts — Returns urgent pipeline alerts:
  - Rate lock expirations (within 7 days)
  - Stale loans (stuck in stage > 10 days)
  - Loans approaching closing with missing documents

Used by MobileHomeDashboard.jsx.
"""

# NOTE: All date comparisons use naive UTC datetimes for consistency with
# timezone-naive date columns in the loans table.

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_async_db
from routes.auth_deps import require_auth, current_user_dep

router = APIRouter(
    prefix="/api/v1/pipeline",
    tags=["Pipeline Alerts"],
    dependencies=[Depends(require_auth)],
)

# Stages considered terminal — excluded from active pipeline alerts
_TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"
)


@router.get("/alerts")
async def get_pipeline_alerts(
    limit: int = Query(default=10, ge=1, le=50),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Return urgent pipeline alerts for the authenticated user's loans."""
    user_id = current_user.id
    organization_id = getattr(current_user, "organization_id", None)
    role = getattr(current_user, "role", "")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alerts = []

    # Determine filter: admins see org-wide, LOs see their own loans
    is_admin = role in ("admin", "site_admin", "platform_admin", "owner", "manager")

    # Build parameterized IN clause for terminal stages
    # SQLAlchemy text() doesn't expand tuples, so we create :t0, :t1, ... params
    terminal_params = {f"t{i}": s for i, s in enumerate(_TERMINAL_STAGES)}
    terminal_placeholders = ", ".join(f":t{i}" for i in range(len(_TERMINAL_STAGES)))

    # Build the owner/org filter clause once (reused by all three queries)
    if is_admin and organization_id:
        owner_clause = "AND l.organization_id = :org_id"
        owner_params = {"org_id": organization_id}
    else:
        owner_clause = "AND l.loan_officer_id = :user_id"
        owner_params = {"user_id": user_id}

    # ---------------------------------------------------------------
    # 1. Rate lock expirations (within next 7 days or already expired)
    # ---------------------------------------------------------------
    lock_params = {
        "window_start": now - timedelta(days=1),
        "window_end": now + timedelta(days=7),
        **terminal_params,
        **owner_params,
    }

    lock_sql = text(
        "SELECT"
        "    l.id AS loan_id,"
        "    l.loan_number,"
        "    l.borrower_name,"
        "    l.lock_expiration_date,"
        "    l.amount,"
        "    l.stage "
        "FROM loans l "
        "WHERE l.lock_expiration_date IS NOT NULL"
        "  AND l.lock_expiration_date BETWEEN :window_start AND :window_end"
        f"  AND l.stage NOT IN ({terminal_placeholders})"
        f"  {owner_clause} "
        "ORDER BY l.lock_expiration_date ASC"
    )

    try:
        lock_rows = (await db.execute(lock_sql, lock_params)).fetchall()
    except Exception as _exc:  # noqa: BLE001
        lock_rows = []

    for row in lock_rows:
        row_dict = dict(row._mapping)
        exp_date = row_dict["lock_expiration_date"]
        if exp_date is not None and isinstance(exp_date, date) and not isinstance(exp_date, datetime):
            exp_date = datetime.combine(exp_date, datetime.min.time())
        days_left = (exp_date - now).days if exp_date else 0

        if days_left < 0:
            severity = "critical"
            title = f"Rate lock EXPIRED ({abs(days_left)}d ago)"
        elif days_left <= 2:
            severity = "critical"
            title = f"Rate lock expires in {days_left} day{'s' if days_left != 1 else ''}"
        else:
            severity = "high"
            title = f"Rate lock expires in {days_left} days"

        alerts.append({
            "id": f"lock-{row_dict['loan_id']}",
            "type": "rate_lock_expiring",
            "severity": severity,
            "title": title,
            "message": f"{row_dict['borrower_name']} — Loan #{row_dict['loan_number']}",
            "borrower_name": row_dict["borrower_name"],
            "loan_number": row_dict["loan_number"],
            "loan_id": row_dict["loan_id"],
        })

    # ---------------------------------------------------------------
    # 2. Stale loans — stuck in stage > 10 days
    # ---------------------------------------------------------------
    stale_params = {
        "stale_threshold": now - timedelta(days=10),
        **terminal_params,
        **owner_params,
    }

    stale_sql = text(
        "SELECT"
        "    l.id AS loan_id,"
        "    l.loan_number,"
        "    l.borrower_name,"
        "    l.stage,"
        "    l.stage_changed_at "
        "FROM loans l "
        "WHERE l.stage_changed_at IS NOT NULL"
        "  AND l.stage_changed_at < :stale_threshold"
        f"  AND l.stage NOT IN ({terminal_placeholders})"
        f"  {owner_clause} "
        "ORDER BY l.stage_changed_at ASC"
    )

    try:
        stale_rows = (await db.execute(stale_sql, stale_params)).fetchall()
    except Exception as _exc:  # noqa: BLE001
        stale_rows = []

    for row in stale_rows:
        row_dict = dict(row._mapping)
        changed = row_dict["stage_changed_at"]
        if changed is not None and isinstance(changed, date) and not isinstance(changed, datetime):
            changed = datetime.combine(changed, datetime.min.time())
        days_stuck = (now - changed).days if changed else 0

        alerts.append({
            "id": f"stale-{row_dict['loan_id']}",
            "type": "stale_loan",
            "severity": "critical" if days_stuck > 20 else "high",
            "title": f"Stuck in {row_dict['stage']} for {days_stuck} days",
            "message": f"{row_dict['borrower_name']} — Loan #{row_dict['loan_number']}",
            "borrower_name": row_dict["borrower_name"],
            "loan_number": row_dict["loan_number"],
            "loan_id": row_dict["loan_id"],
        })

    # ---------------------------------------------------------------
    # 3. Loans closing soon with missing documents
    # ---------------------------------------------------------------
    closing_params = {
        "closing_window": now + timedelta(days=14),
        "now": now,
        **terminal_params,
        **owner_params,
    }

    closing_sql = text(
        "SELECT"
        "    l.id AS loan_id,"
        "    l.loan_number,"
        "    l.borrower_name,"
        "    l.closing_date,"
        "    ("
        "        SELECT COUNT(*) FROM documents d"
        "        WHERE d.loan_id = l.id AND d.status = 'active'"
        "    ) AS doc_count "
        "FROM loans l "
        "WHERE l.closing_date IS NOT NULL"
        "  AND l.closing_date BETWEEN :now AND :closing_window"
        f"  AND l.stage NOT IN ({terminal_placeholders})"
        f"  {owner_clause} "
        "ORDER BY l.closing_date ASC"
    )

    try:
        closing_rows = (await db.execute(closing_sql, closing_params)).fetchall()
    except Exception as _exc:  # noqa: BLE001
        closing_rows = []

    # Flag loans closing soon with fewer than 5 active documents
    for row in closing_rows:
        row_dict = dict(row._mapping)
        doc_count = row_dict.get("doc_count") or 0
        if doc_count < 5:
            close_dt = row_dict["closing_date"]
            if close_dt is not None and isinstance(close_dt, date) and not isinstance(close_dt, datetime):
                close_dt = datetime.combine(close_dt, datetime.min.time())
            days_to_close = (close_dt - now).days if close_dt else 0
            alerts.append({
                "id": f"docs-{row_dict['loan_id']}",
                "type": "missing_documents",
                "severity": "high" if days_to_close <= 7 else "medium",
                "title": f"Only {doc_count} docs on file — closing in {days_to_close} days",
                "message": f"{row_dict['borrower_name']} — Loan #{row_dict['loan_number']}",
                "borrower_name": row_dict["borrower_name"],
                "loan_number": row_dict["loan_number"],
                "loan_id": row_dict["loan_id"],
            })

    # Sort all alerts: critical first, then high, then by type
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 9))

    return {"alerts": alerts[:limit]}
