"""
Perennia AI - Credit Monitoring Tools
======================================
Tools for querying credit monitoring alerts, inquiry events,
and credit score history for borrowers.
2 tools for credit monitoring and recapture intelligence.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
    get_db,
)


# =============================================================================
# Credit Monitoring Tools (2 tools)
# =============================================================================

@mortgage_tool(
    name="get_credit_alerts",
    description="Get credit monitoring alerts, optionally filtered by loan or time window. Includes recapture signals from inquiry alerts.",
    agent_roles=["credit_repair_advisor", "pipeline_analyst", "processor"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "loan_id": "Optional loan ID to filter alerts by associated loan",
        "days_back": "Number of days to look back (default 30)",
    },
)
def get_credit_alerts(
    loan_id: Optional[int] = None,
    days_back: int = 30,
) -> ToolResult:
    """Get credit monitoring alerts."""
    params: Dict[str, Any] = {"days_back": days_back}

    loan_filter = ""
    if loan_id:
        # Filter by alerts linked to a subscription whose contact matches the loan
        loan_filter = """
            AND ca.subscription_id IN (
                SELECT cms.id FROM credit_monitoring_subscriptions cms
                WHERE cms.contact_id = :loan_id
                    AND cms.contact_type = 'loan_contact'
            )
        """
        params["loan_id"] = loan_id

    results = execute_query(f"""
        SELECT
            ca.id,
            ca.alert_type,
            ca.provider,
            ca.credit_score_before,
            ca.credit_score_after,
            ca.score_delta,
            ca.recapture_score,
            ca.is_mortgage_recapture,
            ca.detected_at,
            ca.is_actioned,
            ca.action_taken,
            ca.details,
            cms.first_name,
            cms.last_name,
            cms.contact_type,
            cms.contact_id
        FROM credit_alerts ca
        JOIN credit_monitoring_subscriptions cms ON cms.id = ca.subscription_id
        WHERE ca.detected_at >= CURRENT_DATE - INTERVAL '{days_back} days'
            {loan_filter}
        ORDER BY ca.detected_at DESC
    """, params)

    if not results:
        return ToolResult.no_data(f"No credit alerts in the last {days_back} days")

    alerts = []
    mortgage_recapture_count = 0
    unactioned_count = 0

    for r in results:
        is_recapture = r.get("is_mortgage_recapture", False)
        if is_recapture:
            mortgage_recapture_count += 1
        if not r.get("is_actioned", False):
            unactioned_count += 1

        contact_name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()

        alert_type_raw = r.get("alert_type")
        alert_type = alert_type_raw.value if hasattr(alert_type_raw, "value") else str(alert_type_raw or "")

        provider_raw = r.get("provider")
        provider = provider_raw.value if hasattr(provider_raw, "value") else str(provider_raw or "")

        alerts.append({
            "id": r.get("id"),
            "contact_name": contact_name,
            "contact_type": str(r.get("contact_type", "")),
            "contact_id": r.get("contact_id"),
            "alert_type": alert_type,
            "provider": provider,
            "credit_score_before": r.get("credit_score_before"),
            "credit_score_after": r.get("credit_score_after"),
            "score_delta": r.get("score_delta"),
            "recapture_score": r.get("recapture_score"),
            "is_mortgage_recapture": is_recapture,
            "detected_at": format_date(r.get("detected_at"), "%Y-%m-%d %H:%M"),
            "is_actioned": r.get("is_actioned", False),
            "action_taken": r.get("action_taken"),
        })

    return ToolResult.success(
        data={
            "alerts": alerts,
            "total_count": len(alerts),
            "mortgage_recapture_count": mortgage_recapture_count,
            "unactioned_count": unactioned_count,
            "days_back": days_back,
        },
        message=f"Found {len(alerts)} credit alerts ({mortgage_recapture_count} mortgage recapture, {unactioned_count} unactioned)",
    )


@mortgage_tool(
    name="get_credit_score_history",
    description="Get credit score trend for a borrower by tracking score changes across credit alerts",
    agent_roles=["credit_repair_advisor", "pipeline_analyst", "underwriter"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "loan_id": "Loan ID to look up credit score history for the borrower (required)",
    },
)
def get_credit_score_history(
    loan_id: int,
) -> ToolResult:
    """Get credit score trend for a borrower associated with a loan."""
    # Get subscription info for this loan contact
    subscription = execute_single("""
        SELECT
            cms.id,
            cms.first_name,
            cms.last_name,
            cms.baseline_credit_score,
            cms.enrolled_at,
            cms.provider,
            cms.monitoring_status
        FROM credit_monitoring_subscriptions cms
        WHERE cms.contact_id = :loan_id
            AND cms.contact_type = 'loan_contact'
        ORDER BY cms.enrolled_at DESC
        LIMIT 1
    """, {"loan_id": loan_id})

    if not subscription:
        return ToolResult.no_data(
            f"No credit monitoring subscription found for loan {loan_id}"
        )

    sub_id = subscription.get("id")
    contact_name = f"{subscription.get('first_name', '')} {subscription.get('last_name', '')}".strip()

    # Get score change alerts ordered by time
    score_events = execute_query("""
        SELECT
            ca.detected_at,
            ca.credit_score_before,
            ca.credit_score_after,
            ca.score_delta,
            ca.alert_type,
            ca.provider
        FROM credit_alerts ca
        WHERE ca.subscription_id = :sub_id
            AND ca.credit_score_after IS NOT NULL
        ORDER BY ca.detected_at ASC
    """, {"sub_id": sub_id})

    # Build score timeline
    timeline = []
    baseline = subscription.get("baseline_credit_score")

    if baseline:
        enrolled_at = subscription.get("enrolled_at")
        timeline.append({
            "date": format_date(enrolled_at, "%Y-%m-%d"),
            "score": baseline,
            "delta": 0,
            "event": "enrollment_baseline",
        })

    for event in score_events:
        alert_type_raw = event.get("alert_type")
        alert_type = alert_type_raw.value if hasattr(alert_type_raw, "value") else str(alert_type_raw or "")

        timeline.append({
            "date": format_date(event.get("detected_at"), "%Y-%m-%d"),
            "score": event.get("credit_score_after"),
            "delta": event.get("score_delta"),
            "event": alert_type,
        })

    if not timeline:
        return ToolResult.no_data(
            f"No credit score data available for loan {loan_id}"
        )

    # Calculate summary
    scores = [t["score"] for t in timeline if t["score"] is not None]
    current_score = scores[-1] if scores else None
    min_score = min(scores) if scores else None
    max_score = max(scores) if scores else None
    total_change = (current_score - scores[0]) if len(scores) >= 2 else 0

    monitoring_status_raw = subscription.get("monitoring_status")
    monitoring_status = (
        monitoring_status_raw.value
        if hasattr(monitoring_status_raw, "value")
        else str(monitoring_status_raw or "")
    )

    return ToolResult.success(
        data={
            "loan_id": loan_id,
            "contact_name": contact_name,
            "monitoring_status": monitoring_status,
            "baseline_score": baseline,
            "current_score": current_score,
            "min_score": min_score,
            "max_score": max_score,
            "total_change": total_change,
            "data_points": len(timeline),
            "timeline": timeline,
        },
        message=f"Credit score history for {contact_name}: {current_score} (baseline {baseline}, change {total_change:+d})" if current_score and baseline else f"Credit score history: {len(timeline)} data points",
    )
