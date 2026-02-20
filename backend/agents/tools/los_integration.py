"""
Perennia AI - LOS Integration & Sync Tools (Module 12)
Tools for managing LOS (Loan Origination System) field mappings,
sync status monitoring, conflict resolution, and bidirectional data push/pull.

Integrates with:
    - services/los_integration/sync_service.py (sync logic)
    - services/los_integration/encompass_client.py (Encompass API)
    - services/los_integration/base.py (abstract LOS interface)
    - database/models/los_sync.py (LosFieldMapping, LosSyncLog)
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_date, days_between, sql_now, sql_date_subtract,
)


# =============================================================================
# SYNC STATUS DEFINITIONS
# =============================================================================

SYNC_STATUSES = {
    "success": "All fields synced successfully",
    "partial": "Some fields synced, some failed — check field_errors",
    "conflict": "Data conflicts detected — manual resolution required",
    "failed": "Sync failed — check error details",
    "pending": "Sync queued, not yet executed",
    "skipped": "No changes detected, sync skipped",
}

# Field categories for organized mapping display
FIELD_CATEGORIES = {
    "borrower": ["first_name", "last_name", "ssn", "dob", "email", "phone", "address"],
    "loan": ["loan_amount", "loan_type", "term", "rate", "ltv", "dti", "purpose"],
    "property": ["property_address", "property_type", "occupancy", "appraisal_value"],
    "status": ["loan_status", "milestone_date", "closing_date", "funding_date"],
    "compliance": ["disclosure_date", "cd_date", "le_date", "trid_status"],
}


# =============================================================================
# LOS INTEGRATION TOOLS (6 tools)
# =============================================================================

@mortgage_tool(
    name="get_sync_status",
    description="Get the current sync status between CRM and LOS for a loan or across all loans",
    agent_roles=["integrations", "pipeline_analyst", "processor"],
    risk_level="low",
    examples=[
        "Is this loan synced with Encompass?",
        "Show me sync status for all active loans",
        "Are there any sync failures?",
    ],
)
def get_sync_status(
    loan_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    days: int = 7,
    limit: int = 50,
) -> ToolResult:
    """
    Get sync status between CRM and LOS.

    Args:
        loan_id: Specific loan to check (None for all)
        status_filter: Filter by status (success/partial/conflict/failed)
        days: Look-back period for sync history
        limit: Max results
    """
    params: Dict[str, Any] = {"days": days, "limit": limit}
    filters = [f"sl.created_at >= {sql_date_subtract(days)}"]

    if loan_id:
        filters.append("sl.loan_id = :loan_id")
        params["loan_id"] = loan_id
    if status_filter:
        filters.append("sl.status = :status")
        params["status"] = status_filter

    where_sql = " AND ".join(filters)

    syncs = execute_query(f"""
        SELECT
            sl.id, sl.loan_id, sl.direction, sl.status,
            sl.fields_synced, sl.fields_failed, sl.field_errors,
            sl.created_at, sl.completed_at,
            l.loan_number, l.borrower_name
        FROM los_sync_logs sl
        JOIN loans l ON l.id = sl.loan_id
        WHERE {where_sql}
        ORDER BY sl.created_at DESC
        LIMIT :limit
    """, params)

    if not syncs:
        return ToolResult.no_data("No sync records found for the specified criteria")

    # Aggregate stats
    total = len(syncs)
    success_count = len([s for s in syncs if s["status"] == "success"])
    conflict_count = len([s for s in syncs if s["status"] == "conflict"])
    failed_count = len([s for s in syncs if s["status"] == "failed"])

    data = {
        "period_days": days,
        "summary": {
            "total_syncs": total,
            "success": success_count,
            "partial": len([s for s in syncs if s["status"] == "partial"]),
            "conflict": conflict_count,
            "failed": failed_count,
            "success_rate": round((success_count / total * 100), 1) if total > 0 else 0,
        },
        "syncs": [
            {
                "id": s["id"],
                "loan_id": s["loan_id"],
                "loan_number": s["loan_number"],
                "borrower": s["borrower_name"],
                "direction": s["direction"],
                "status": s["status"],
                "fields_synced": s["fields_synced"],
                "fields_failed": s["fields_failed"],
                "errors": s["field_errors"],
                "synced_at": format_date(s["created_at"]),
            }
            for s in syncs
        ],
    }

    if conflict_count > 0 or failed_count > 0:
        data["action_required"] = (
            f"{conflict_count} conflicts and {failed_count} failures need attention"
        )

    return ToolResult.success(
        data=data,
        message=f"{total} syncs: {success_count} success, {conflict_count} conflicts, {failed_count} failed",
    )


@mortgage_tool(
    name="get_field_mappings",
    description="Get the current field mapping configuration between CRM and LOS",
    agent_roles=["integrations", "admin"],
    risk_level="low",
    examples=[
        "Show me the field mappings for Encompass",
        "Which CRM fields map to LOS fields?",
        "Are all required fields mapped?",
    ],
)
def get_field_mappings(
    provider: str = "encompass",
    category: Optional[str] = None,
    active_only: bool = True,
) -> ToolResult:
    """
    Get field mapping configuration.

    Args:
        provider: LOS provider name
        category: Filter by field category (borrower/loan/property/status/compliance)
        active_only: Only show active mappings
    """
    params: Dict[str, Any] = {"provider": provider}
    filters = ["fm.provider = :provider"]

    if category:
        filters.append("fm.category = :category")
        params["category"] = category
    if active_only:
        filters.append("fm.is_active = true")

    where_sql = " AND ".join(filters)

    mappings = execute_query(f"""
        SELECT
            fm.id, fm.crm_field, fm.los_field, fm.category,
            fm.direction, fm.transform_rule, fm.is_required,
            fm.is_active, fm.last_synced_at
        FROM los_field_mappings fm
        WHERE {where_sql}
        ORDER BY fm.category, fm.crm_field
    """, params)

    if not mappings:
        return ToolResult.no_data(f"No field mappings found for provider '{provider}'")

    # Group by category
    by_category: Dict[str, List[Dict]] = {}
    unmapped_required = []

    for m in mappings:
        cat = m["category"] or "other"
        if cat not in by_category:
            by_category[cat] = []
        mapping_info = {
            "id": m["id"],
            "crm_field": m["crm_field"],
            "los_field": m["los_field"],
            "direction": m["direction"],
            "transform": m["transform_rule"],
            "required": m["is_required"],
            "last_synced": format_date(m["last_synced_at"]),
        }
        by_category[cat].append(mapping_info)

        if m["is_required"] and not m["los_field"]:
            unmapped_required.append(m["crm_field"])

    data = {
        "provider": provider,
        "total_mappings": len(mappings),
        "active_mappings": len([m for m in mappings if m["is_active"]]),
        "required_mappings": len([m for m in mappings if m["is_required"]]),
        "unmapped_required": unmapped_required,
        "by_category": by_category,
    }

    if unmapped_required:
        data["warning"] = f"{len(unmapped_required)} required fields are unmapped: {', '.join(unmapped_required)}"

    return ToolResult.success(
        data=data,
        message=f"{len(mappings)} mappings for {provider} ({len(unmapped_required)} unmapped required)",
    )


@mortgage_tool(
    name="resolve_sync_conflict",
    description="Resolve a data conflict between CRM and LOS by choosing which value to keep",
    agent_roles=["integrations", "processor", "admin"],
    risk_level="high",
    requires_confirmation=True,
    examples=[
        "Resolve the borrower name conflict on this loan",
        "Keep the CRM value for this field",
        "Use the LOS value and update CRM",
    ],
)
def resolve_sync_conflict(
    sync_log_id: int,
    field_name: str,
    resolution: str,
    resolved_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> ToolResult:
    """
    Resolve a sync conflict for a specific field.

    Args:
        sync_log_id: The sync log entry with the conflict
        field_name: The field with the conflict
        resolution: Which value to keep: 'crm', 'los', or 'manual' (with manual_value)
        resolved_by: Who resolved it
        notes: Resolution notes
    """
    if resolution not in ("crm", "los", "manual"):
        return ToolResult.error("Resolution must be 'crm', 'los', or 'manual'")

    sync_log = execute_single("""
        SELECT sl.*, l.loan_number
        FROM los_sync_logs sl
        JOIN loans l ON l.id = sl.loan_id
        WHERE sl.id = :id
    """, {"id": sync_log_id})

    if not sync_log:
        return ToolResult.no_data(f"Sync log {sync_log_id} not found")

    if sync_log["status"] != "conflict":
        return ToolResult.error(f"Sync log {sync_log_id} is not in conflict status")

    # Record the resolution
    with get_db() as db:
        from sqlalchemy import text as sql_text
        db.execute(sql_text("""
            UPDATE los_sync_logs
            SET status = 'resolved',
                resolution = :resolution,
                resolved_by = :resolved_by,
                resolution_notes = :notes,
                resolved_at = NOW()
            WHERE id = :id
        """), {
            "id": sync_log_id,
            "resolution": f"{resolution}:{field_name}",
            "resolved_by": resolved_by or "system",
            "notes": notes,
        })

    data = {
        "sync_log_id": sync_log_id,
        "loan_number": sync_log["loan_number"],
        "field": field_name,
        "resolution": resolution,
        "status": "resolved",
        "resolved_by": resolved_by,
    }

    return ToolResult.success(
        data=data,
        message=f"Conflict resolved: {field_name} → keep {resolution} value",
    )


@mortgage_tool(
    name="trigger_sync",
    description="Manually trigger a sync between CRM and LOS for a specific loan",
    agent_roles=["integrations", "processor", "admin"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Sync this loan with Encompass",
        "Push CRM data to LOS",
        "Pull latest data from Encompass for this loan",
    ],
)
def trigger_sync(
    loan_id: int,
    direction: str = "bidirectional",
    fields: Optional[List[str]] = None,
    force: bool = False,
) -> ToolResult:
    """
    Trigger a manual sync for a loan.

    Args:
        loan_id: Loan to sync
        direction: Sync direction (push/pull/bidirectional)
        fields: Specific fields to sync (None = all mapped fields)
        force: Force sync even if no changes detected
    """
    if direction not in ("push", "pull", "bidirectional"):
        return ToolResult.error("Direction must be 'push', 'pull', or 'bidirectional'")

    loan = execute_single("""
        SELECT id, loan_number, borrower_name, status
        FROM loans WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Check last sync to avoid rapid re-syncs
    if not force:
        last_sync = execute_single("""
            SELECT created_at, status
            FROM los_sync_logs
            WHERE loan_id = :loan_id
            ORDER BY created_at DESC
            LIMIT 1
        """, {"loan_id": loan_id})

        if last_sync and last_sync["created_at"]:
            minutes_since = (datetime.utcnow() - last_sync["created_at"]).total_seconds() / 60
            if minutes_since < 5:
                return ToolResult.error(
                    f"Last sync was {int(minutes_since)} minutes ago. "
                    "Use force=True to override the 5-minute cooldown."
                )

    # Create sync log entry
    with get_db() as db:
        from sqlalchemy import text as sql_text
        db.execute(sql_text("""
            INSERT INTO los_sync_logs
                (loan_id, direction, status, fields_requested, created_at)
            VALUES
                (:loan_id, :direction, 'pending', :fields, NOW())
        """), {
            "loan_id": loan_id,
            "direction": direction,
            "fields": ",".join(fields) if fields else "all",
        })

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "direction": direction,
        "fields": fields or "all",
        "status": "pending",
        "message": f"Sync triggered for loan {loan['loan_number']} ({direction})",
    }

    return ToolResult.success(
        data=data,
        message=f"Sync triggered: {loan['loan_number']} ({direction})",
    )


@mortgage_tool(
    name="get_sync_health",
    description="Get overall LOS sync health metrics including failure rates, latency, and coverage",
    agent_roles=["integrations", "reporting", "admin"],
    risk_level="low",
    examples=[
        "How healthy is our LOS sync?",
        "Show me sync failure rates",
        "Are there any loans out of sync?",
    ],
)
def get_sync_health(
    days: int = 7,
    provider: str = "encompass",
) -> ToolResult:
    """Get overall sync health metrics."""
    params = {"days": days, "provider": provider}

    # Overall sync stats
    stats = execute_single(f"""
        SELECT
            COUNT(*) as total_syncs,
            COUNT(CASE WHEN status = 'success' THEN 1 END) as success,
            COUNT(CASE WHEN status = 'partial' THEN 1 END) as partial,
            COUNT(CASE WHEN status = 'conflict' THEN 1 END) as conflicts,
            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
            COUNT(DISTINCT loan_id) as loans_synced,
            AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_sync_seconds
        FROM los_sync_logs
        WHERE created_at >= {sql_date_subtract(days)}
    """, params)

    # Loans that haven't synced recently
    stale_loans = execute_query(f"""
        SELECT l.id, l.loan_number, l.borrower_name, l.status,
               MAX(sl.created_at) as last_sync
        FROM loans l
        LEFT JOIN los_sync_logs sl ON sl.loan_id = l.id
        WHERE l.status NOT IN ('Funded', 'Cancelled', 'Denied')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.status
        HAVING MAX(sl.created_at) IS NULL
            OR MAX(sl.created_at) < {sql_date_subtract(days)}
        ORDER BY MAX(sl.created_at) ASC NULLS FIRST
        LIMIT 10
    """, params)

    # Unresolved conflicts
    unresolved = execute_single("""
        SELECT COUNT(*) as cnt
        FROM los_sync_logs
        WHERE status = 'conflict' AND resolved_at IS NULL
    """)

    total = stats["total_syncs"] or 0
    success = stats["success"] or 0

    data = {
        "period_days": days,
        "provider": provider,
        "health_score": round((success / total * 100), 1) if total > 0 else 0,
        "summary": {
            "total_syncs": total,
            "success_rate": round((success / total * 100), 1) if total > 0 else 0,
            "conflicts": stats["conflicts"] or 0,
            "failures": stats["failed"] or 0,
            "loans_synced": stats["loans_synced"] or 0,
            "avg_sync_seconds": round(float(stats["avg_sync_seconds"] or 0), 1),
        },
        "unresolved_conflicts": unresolved["cnt"] if unresolved else 0,
        "stale_loans": [
            {
                "loan_id": s["id"],
                "loan_number": s["loan_number"],
                "borrower": s["borrower_name"],
                "status": s["status"],
                "last_sync": format_date(s["last_sync"]),
            }
            for s in stale_loans
        ],
        "stale_count": len(stale_loans),
    }

    health = data["health_score"]
    status_label = "Healthy" if health >= 95 else "Degraded" if health >= 80 else "Critical"

    return ToolResult.success(
        data=data,
        message=f"Sync health: {health}% ({status_label}) — {len(stale_loans)} stale loans, {data['unresolved_conflicts']} unresolved conflicts",
    )


@mortgage_tool(
    name="update_field_mapping",
    description="Add or update a field mapping between CRM and LOS",
    agent_roles=["integrations", "admin"],
    risk_level="high",
    requires_confirmation=True,
    examples=[
        "Map the CRM borrower_email field to Encompass field 1240",
        "Add a new field mapping for property_type",
        "Disable the SSN field mapping",
    ],
)
def update_field_mapping(
    crm_field: str,
    los_field: str,
    provider: str = "encompass",
    direction: str = "bidirectional",
    category: Optional[str] = None,
    transform_rule: Optional[str] = None,
    is_required: bool = False,
    is_active: bool = True,
) -> ToolResult:
    """
    Add or update a field mapping.

    Args:
        crm_field: CRM field name
        los_field: LOS field identifier
        provider: LOS provider
        direction: Sync direction (push/pull/bidirectional)
        category: Field category for organization
        transform_rule: Optional transformation rule (e.g., 'uppercase', 'date_format')
        is_required: Whether this field is required for sync
        is_active: Whether this mapping is active
    """
    if direction not in ("push", "pull", "bidirectional"):
        return ToolResult.error("Direction must be 'push', 'pull', or 'bidirectional'")

    # Check if mapping already exists
    existing = execute_single("""
        SELECT id FROM los_field_mappings
        WHERE provider = :provider AND crm_field = :crm_field
    """, {"provider": provider, "crm_field": crm_field})

    with get_db() as db:
        from sqlalchemy import text as sql_text
        if existing:
            db.execute(sql_text("""
                UPDATE los_field_mappings
                SET los_field = :los_field,
                    direction = :direction,
                    category = :category,
                    transform_rule = :transform,
                    is_required = :required,
                    is_active = :active,
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": existing["id"],
                "los_field": los_field,
                "direction": direction,
                "category": category,
                "transform": transform_rule,
                "required": is_required,
                "active": is_active,
            })
            action = "updated"
        else:
            db.execute(sql_text("""
                INSERT INTO los_field_mappings
                    (provider, crm_field, los_field, direction, category,
                     transform_rule, is_required, is_active, created_at)
                VALUES
                    (:provider, :crm_field, :los_field, :direction, :category,
                     :transform, :required, :active, NOW())
            """), {
                "provider": provider,
                "crm_field": crm_field,
                "los_field": los_field,
                "direction": direction,
                "category": category,
                "transform": transform_rule,
                "required": is_required,
                "active": is_active,
            })
            action = "created"

    data = {
        "action": action,
        "provider": provider,
        "crm_field": crm_field,
        "los_field": los_field,
        "direction": direction,
        "category": category,
        "is_required": is_required,
        "is_active": is_active,
    }

    return ToolResult.success(
        data=data,
        message=f"Field mapping {action}: {crm_field} ↔ {los_field} ({provider})",
    )
