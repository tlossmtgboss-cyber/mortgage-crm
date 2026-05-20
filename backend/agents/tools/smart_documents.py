"""
Smart Docs bridge tools for Aria agent system.
Connects AI agents to the Smart Document Collection system.

These tools query the smart_documents, smart_document_requests,
doc_policy_events, and document_followup_campaigns tables — the new
Smart Docs infrastructure — rather than the base documents and
document_requests tables used by the original document tools.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_date, days_between,
)


# =============================================================================
# Tool 1: get_smart_doc_status
# =============================================================================

@mortgage_tool(
    name="get_smart_doc_status",
    description="Get Smart Document collection status for a loan — open requests, fulfilled count, and completion percentage",
    agent_roles=["document_tracker", "pipeline_analyst"],
    risk_level="LOW",
    examples=[
        "get_smart_doc_status(loan_id=123)",
        "get_smart_doc_status(loan_id=456)",
    ],
)
def get_smart_doc_status(loan_id: int) -> ToolResult:
    """
    Query smart_document_requests and smart_documents for a loan to
    produce an overall collection status summary.

    Args:
        loan_id: The loan ID to check
    """
    # Verify loan exists and belongs to tenant
    loan = execute_single("""
        SELECT l.id, l.organization_id,
               l.borrower_first_name, l.borrower_last_name
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get all requests for this loan
    requests = execute_query("""
        SELECT
            sdr.id,
            sdr.doc_type,
            sdr.title,
            sdr.status,
            sdr.priority,
            sdr.is_required,
            sdr.sla_due_at,
            sdr.created_at
        FROM smart_document_requests sdr
        JOIN loans l ON l.id = sdr.loan_id
        WHERE sdr.loan_id = :loan_id
            AND sdr.is_active = true
        ORDER BY sdr.priority DESC, sdr.created_at ASC
    """, {"loan_id": loan_id})

    # Get fulfilled document count
    fulfilled = execute_query("""
        SELECT
            sd.request_id,
            sd.doc_type,
            sd.status,
            sd.decision
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE sd.loan_id = :loan_id
            AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'UPLOAD_FAILED')
    """, {"loan_id": loan_id})

    total_requests = len(requests)
    fulfilled_request_ids = set()
    for doc in fulfilled:
        if doc.get("request_id") and doc.get("decision") in ("ACCEPT", None) and doc.get("status") in ("APPROVED", "UPLOADED", "PENDING_REVIEW", "NEEDS_REVIEW", "PROCESSING", "SCANNING"):
            fulfilled_request_ids.add(doc["request_id"])

    accepted_count = len([r for r in requests if r["status"] == "ACCEPTED"])
    fulfilled_count = accepted_count + len(fulfilled_request_ids - {r["id"] for r in requests if r["status"] == "ACCEPTED"})

    open_requests = []
    for r in requests:
        if r["status"] in ("OPEN", "PENDING_REVIEW"):
            open_requests.append({
                "id": r["id"],
                "doc_type": r["doc_type"],
                "title": r["title"],
                "status": r["status"],
                "priority": r["priority"],
                "is_required": r["is_required"],
                "sla_due_at": format_date(r["sla_due_at"]) if r.get("sla_due_at") else None,
            })

    completion_pct = round((fulfilled_count / total_requests) * 100, 1) if total_requests > 0 else 0.0

    data = {
        "loan_id": loan_id,
        "borrower": f"{loan.get('borrower_first_name', '')} {loan.get('borrower_last_name', '')}".strip(),
        "summary": {
            "total_requests": total_requests,
            "fulfilled": fulfilled_count,
            "open": len([r for r in requests if r["status"] == "OPEN"]),
            "pending_review": len([r for r in requests if r["status"] == "PENDING_REVIEW"]),
            "accepted": accepted_count,
            "rejected": len([r for r in requests if r["status"] == "REJECTED"]),
            "waived": len([r for r in requests if r["status"] == "WAIVED"]),
            "completion_percentage": completion_pct,
        },
        "open_requests": open_requests,
        "total_documents_uploaded": len(fulfilled),
    }

    return ToolResult.success(
        data=data,
        message=f"Smart Docs: {fulfilled_count}/{total_requests} fulfilled ({completion_pct}% complete), {len(open_requests)} open requests",
    )


# =============================================================================
# Tool 2: check_document_freshness
# =============================================================================

@mortgage_tool(
    name="check_document_freshness",
    description="Check for expiring or expired Smart Documents on a loan, including auto-renewal eligibility",
    agent_roles=["document_tracker", "compliance_checker"],
    risk_level="LOW",
    examples=[
        "check_document_freshness(loan_id=123)",
        "check_document_freshness(loan_id=123, days_ahead=60)",
    ],
)
def check_document_freshness(
    loan_id: int,
    days_ahead: int = 30,
) -> ToolResult:
    """
    Query smart_documents for documents with expiration dates.
    Identifies expired, expiring soon, and auto-renew eligible documents.

    Args:
        loan_id: The loan ID to check
        days_ahead: Number of days to look ahead for expiring documents (default 30)
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    documents = execute_query("""
        SELECT
            sd.id,
            sd.doc_type,
            sd.file_name,
            sd.doc_expires_at,
            sd.is_expired,
            sd.days_until_expiration,
            sd.doc_date,
            sd.status,
            sdr.auto_renew,
            sdr.freshness_days,
            sdr.next_expected_available_at,
            sdr.payroll_frequency
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        LEFT JOIN smart_document_requests sdr ON sdr.id = sd.request_id
        WHERE sd.loan_id = :loan_id
            AND sd.doc_expires_at IS NOT NULL
            AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'UPLOAD_FAILED')
        ORDER BY sd.doc_expires_at ASC
    """, {"loan_id": loan_id})

    if not documents:
        return ToolResult.no_data(f"No documents with expiration dates found for loan {loan_id}")

    today = datetime.now()
    threshold = today + timedelta(days=days_ahead)

    expired = []
    expiring_soon = []
    auto_renew_eligible = []

    for doc in documents:
        expires_at = doc["doc_expires_at"]
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except (ValueError, TypeError):
                continue

        if expires_at is None:
            continue

        days_remaining = (expires_at - today).days

        entry = {
            "document_id": doc["id"],
            "doc_type": doc["doc_type"],
            "file_name": doc["file_name"],
            "expiry_date": format_date(expires_at),
            "days_remaining": days_remaining,
            "status": doc["status"],
            "auto_renew": doc.get("auto_renew", False),
            "freshness_days": doc.get("freshness_days"),
        }

        if days_remaining < 0:
            expired.append(entry)
        elif expires_at <= threshold:
            expiring_soon.append(entry)

        if doc.get("auto_renew"):
            auto_renew_eligible.append({
                "document_id": doc["id"],
                "doc_type": doc["doc_type"],
                "payroll_frequency": doc.get("payroll_frequency"),
                "next_expected_available_at": format_date(doc.get("next_expected_available_at")) if doc.get("next_expected_available_at") else None,
                "days_remaining": days_remaining,
            })

    data = {
        "loan_id": loan_id,
        "check_date": today.strftime("%Y-%m-%d"),
        "days_ahead_checked": days_ahead,
        "summary": {
            "total_with_expiration": len(documents),
            "expired": len(expired),
            "expiring_soon": len(expiring_soon),
            "auto_renew_eligible": len(auto_renew_eligible),
        },
        "expired": expired,
        "expiring_soon": expiring_soon,
        "auto_renew_eligible": auto_renew_eligible,
    }

    return ToolResult.success(
        data=data,
        message=f"Freshness check: {len(expired)} expired, {len(expiring_soon)} expiring within {days_ahead} days, {len(auto_renew_eligible)} auto-renew eligible",
    )


# =============================================================================
# Tool 3: get_document_decisions
# =============================================================================

@mortgage_tool(
    name="get_document_decisions",
    description="Get AI review decisions for Smart Documents on a loan — accept, reject, needs-review with reasons",
    agent_roles=["document_tracker"],
    risk_level="LOW",
    examples=[
        "get_document_decisions(loan_id=123)",
        "get_document_decisions(loan_id=123, decision_filter='REJECT')",
    ],
)
def get_document_decisions(
    loan_id: int,
    decision_filter: Optional[str] = None,
) -> ToolResult:
    """
    Query smart_documents for their AI review decisions, rejection categories,
    and fix instructions.

    Args:
        loan_id: The loan ID to check
        decision_filter: Optional filter — ACCEPT, REJECT, or NEEDS_REVIEW
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    params: Dict[str, Any] = {"loan_id": loan_id}
    decision_clause = ""
    if decision_filter:
        decision_clause = "AND sd.decision = :decision_filter"
        params["decision_filter"] = decision_filter

    documents = execute_query(f"""
        SELECT
            sd.id,
            sd.doc_type,
            sd.file_name,
            sd.status,
            sd.decision,
            sd.decision_reasons,
            sd.rejection_reason,
            sd.rejection_category,
            sd.fix_instructions,
            sd.reviewed_at,
            sd.reviewed_by,
            sd.detected_is_screenshot,
            sd.screenshot_confidence
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE sd.loan_id = :loan_id
            AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'UPLOAD_FAILED')
            {decision_clause}
        ORDER BY sd.reviewed_at DESC NULLS LAST, sd.created_at DESC
    """, params)

    if not documents:
        msg = f"No documents found for loan {loan_id}"
        if decision_filter:
            msg += f" with decision={decision_filter}"
        return ToolResult.no_data(msg)

    results = []
    for doc in documents:
        results.append({
            "document_id": doc["id"],
            "doc_type": doc["doc_type"],
            "file_name": doc["file_name"],
            "status": doc["status"],
            "decision": doc["decision"],
            "decision_reasons": doc.get("decision_reasons"),
            "rejection_reason": doc.get("rejection_reason"),
            "rejection_category": doc.get("rejection_category"),
            "fix_instructions": doc.get("fix_instructions"),
            "reviewed_at": format_date(doc["reviewed_at"]) if doc.get("reviewed_at") else None,
            "reviewed_by": doc.get("reviewed_by"),
            "is_screenshot": doc.get("detected_is_screenshot", False),
            "screenshot_confidence": doc.get("screenshot_confidence"),
        })

    # Summary counts
    accept_count = len([d for d in results if d["decision"] == "ACCEPT"])
    reject_count = len([d for d in results if d["decision"] == "REJECT"])
    needs_review_count = len([d for d in results if d["decision"] == "NEEDS_REVIEW"])
    pending_count = len([d for d in results if d["decision"] is None])

    data = {
        "loan_id": loan_id,
        "summary": {
            "total": len(results),
            "accepted": accept_count,
            "rejected": reject_count,
            "needs_review": needs_review_count,
            "pending_decision": pending_count,
        },
        "documents": results,
    }

    return ToolResult.success(
        data=data,
        message=f"Document decisions: {accept_count} accepted, {reject_count} rejected, {needs_review_count} needs review, {pending_count} pending",
    )


# =============================================================================
# Tool 4: get_needs_list
# =============================================================================

@mortgage_tool(
    name="get_needs_list",
    description="Get the Smart Docs needs list for a loan — document requests grouped by status",
    agent_roles=["document_tracker", "pipeline_analyst"],
    risk_level="LOW",
    examples=[
        "get_needs_list(loan_id=123)",
    ],
)
def get_needs_list(loan_id: int) -> ToolResult:
    """
    Query smart_document_requests for a loan, grouped by status.
    Returns open, pending_review, accepted, rejected, and waived counts
    with details.

    Args:
        loan_id: The loan ID to check
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id,
               l.borrower_first_name, l.borrower_last_name
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    requests = execute_query("""
        SELECT
            sdr.id,
            sdr.doc_type,
            sdr.title,
            sdr.description,
            sdr.instructions,
            sdr.status,
            sdr.priority,
            sdr.is_required,
            sdr.applies_to,
            sdr.required_count,
            sdr.due_date,
            sdr.sla_due_at,
            sdr.requires_esign,
            sdr.freshness_days,
            sdr.auto_renew,
            sdr.created_at,
            sdr.fulfilled_at
        FROM smart_document_requests sdr
        JOIN loans l ON l.id = sdr.loan_id
        WHERE sdr.loan_id = :loan_id
            AND sdr.is_active = true
        ORDER BY
            CASE sdr.priority
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'NORMAL' THEN 3
                WHEN 'LOW' THEN 4
                ELSE 5
            END,
            sdr.created_at ASC
    """, {"loan_id": loan_id})

    if not requests:
        return ToolResult.no_data(f"No needs list items found for loan {loan_id}")

    grouped: Dict[str, List[Dict]] = {
        "OPEN": [],
        "PENDING_REVIEW": [],
        "ACCEPTED": [],
        "REJECTED": [],
        "WAIVED": [],
    }

    for r in requests:
        entry = {
            "id": r["id"],
            "doc_type": r["doc_type"],
            "title": r["title"],
            "description": r.get("description"),
            "instructions": r.get("instructions"),
            "priority": r["priority"],
            "is_required": r["is_required"],
            "applies_to": r.get("applies_to"),
            "requires_esign": r.get("requires_esign", False),
            "due_date": format_date(r["due_date"]) if r.get("due_date") else None,
            "sla_due_at": format_date(r["sla_due_at"]) if r.get("sla_due_at") else None,
            "created_at": format_date(r["created_at"]) if r.get("created_at") else None,
            "fulfilled_at": format_date(r["fulfilled_at"]) if r.get("fulfilled_at") else None,
        }
        status = r["status"] if r["status"] in grouped else "OPEN"
        grouped[status].append(entry)

    data = {
        "loan_id": loan_id,
        "borrower": f"{loan.get('borrower_first_name', '')} {loan.get('borrower_last_name', '')}".strip(),
        "counts": {
            "open": len(grouped["OPEN"]),
            "pending_review": len(grouped["PENDING_REVIEW"]),
            "accepted": len(grouped["ACCEPTED"]),
            "rejected": len(grouped["REJECTED"]),
            "waived": len(grouped["WAIVED"]),
            "total": len(requests),
        },
        "open": grouped["OPEN"],
        "pending_review": grouped["PENDING_REVIEW"],
        "accepted": grouped["ACCEPTED"],
        "rejected": grouped["REJECTED"],
        "waived": grouped["WAIVED"],
    }

    return ToolResult.success(
        data=data,
        message=f"Needs list: {len(grouped['OPEN'])} open, {len(grouped['PENDING_REVIEW'])} pending review, {len(grouped['ACCEPTED'])} accepted, {len(grouped['REJECTED'])} rejected, {len(grouped['WAIVED'])} waived",
    )


# =============================================================================
# Tool 5: check_document_sla
# =============================================================================

@mortgage_tool(
    name="check_document_sla",
    description="Check Smart Document request SLA status — breached, at-risk (within 24 hours), or on-track",
    agent_roles=["document_tracker", "compliance_checker"],
    risk_level="LOW",
    examples=[
        "check_document_sla(loan_id=123)",
    ],
)
def check_document_sla(loan_id: int) -> ToolResult:
    """
    Query smart_document_requests for SLA due dates that are approaching
    or breached.

    Args:
        loan_id: The loan ID to check
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    requests = execute_query("""
        SELECT
            sdr.id,
            sdr.doc_type,
            sdr.title,
            sdr.status,
            sdr.priority,
            sdr.sla_due_at,
            sdr.created_at
        FROM smart_document_requests sdr
        JOIN loans l ON l.id = sdr.loan_id
        WHERE sdr.loan_id = :loan_id
            AND sdr.is_active = true
            AND sdr.sla_due_at IS NOT NULL
            AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
        ORDER BY sdr.sla_due_at ASC
    """, {"loan_id": loan_id})

    if not requests:
        return ToolResult.no_data(f"No open requests with SLA deadlines found for loan {loan_id}")

    now = datetime.now()
    at_risk_threshold = now + timedelta(hours=24)

    breached = []
    at_risk = []
    on_track = []

    for r in requests:
        sla_due = r["sla_due_at"]
        if isinstance(sla_due, str):
            try:
                sla_due = datetime.fromisoformat(sla_due)
            except (ValueError, TypeError):
                continue

        if sla_due is None:
            continue

        hours_remaining = (sla_due - now).total_seconds() / 3600

        entry = {
            "request_id": r["id"],
            "doc_type": r["doc_type"],
            "title": r["title"],
            "status": r["status"],
            "priority": r["priority"],
            "sla_due_at": format_date(sla_due, "%Y-%m-%d %H:%M"),
            "hours_remaining": round(hours_remaining, 1),
        }

        if hours_remaining < 0:
            entry["hours_overdue"] = round(abs(hours_remaining), 1)
            breached.append(entry)
        elif sla_due <= at_risk_threshold:
            at_risk.append(entry)
        else:
            on_track.append(entry)

    data = {
        "loan_id": loan_id,
        "check_time": now.strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "total_with_sla": len(requests),
            "breached": len(breached),
            "at_risk": len(at_risk),
            "on_track": len(on_track),
        },
        "breached": breached,
        "at_risk": at_risk,
        "on_track": on_track,
    }

    msg_parts = []
    if breached:
        msg_parts.append(f"{len(breached)} BREACHED")
    if at_risk:
        msg_parts.append(f"{len(at_risk)} at risk")
    if on_track:
        msg_parts.append(f"{len(on_track)} on track")

    return ToolResult.success(
        data=data,
        message=f"Document SLA status: {', '.join(msg_parts)}",
    )


# =============================================================================
# Tool 6: get_screenshot_flags
# =============================================================================

@mortgage_tool(
    name="get_screenshot_flags",
    description="Get Smart Documents flagged as screenshots with confidence scores and detection reasons",
    agent_roles=["document_tracker", "compliance_checker"],
    risk_level="LOW",
    examples=[
        "get_screenshot_flags(loan_id=123)",
    ],
)
def get_screenshot_flags(loan_id: int) -> ToolResult:
    """
    Query smart_documents where detected_is_screenshot = true.
    Returns flagged documents with confidence scores and reasons.

    Args:
        loan_id: The loan ID to check
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    flagged = execute_query("""
        SELECT
            sd.id,
            sd.doc_type,
            sd.file_name,
            sd.detected_is_screenshot,
            sd.screenshot_confidence,
            sd.screenshot_reasons,
            sd.status,
            sd.decision,
            sd.rejection_category,
            sd.fix_instructions,
            sd.uploaded_at,
            sd.upload_source
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE sd.loan_id = :loan_id
            AND sd.detected_is_screenshot = true
            AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'UPLOAD_FAILED')
        ORDER BY sd.screenshot_confidence DESC NULLS LAST, sd.uploaded_at DESC
    """, {"loan_id": loan_id})

    if not flagged:
        return ToolResult.no_data(f"No screenshot-flagged documents found for loan {loan_id}")

    results = []
    for doc in flagged:
        results.append({
            "document_id": doc["id"],
            "doc_type": doc["doc_type"],
            "file_name": doc["file_name"],
            "screenshot_confidence": doc.get("screenshot_confidence"),
            "screenshot_reasons": doc.get("screenshot_reasons"),
            "status": doc["status"],
            "decision": doc.get("decision"),
            "rejection_category": doc.get("rejection_category"),
            "fix_instructions": doc.get("fix_instructions"),
            "uploaded_at": format_date(doc["uploaded_at"]) if doc.get("uploaded_at") else None,
            "upload_source": doc.get("upload_source"),
        })

    high_confidence = len([d for d in results if d.get("screenshot_confidence") and d["screenshot_confidence"] >= 0.8])

    data = {
        "loan_id": loan_id,
        "summary": {
            "total_flagged": len(results),
            "high_confidence": high_confidence,
            "already_rejected": len([d for d in results if d["decision"] == "REJECT"]),
        },
        "flagged_documents": results,
    }

    return ToolResult.success(
        data=data,
        message=f"Screenshot detection: {len(results)} flagged ({high_confidence} high confidence)",
    )


# =============================================================================
# Tool 7: get_document_extraction
# =============================================================================

@mortgage_tool(
    name="get_document_extraction",
    description="Get extracted data (dates, names, amounts, employer) from Smart Documents for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
    examples=[
        "get_document_extraction(loan_id=123)",
        "get_document_extraction(loan_id=123, doc_type='PAYSTUB')",
    ],
)
def get_document_extraction(
    loan_id: int,
    doc_type: Optional[str] = None,
) -> ToolResult:
    """
    Query smart_documents for extracted data — dates, names, amounts,
    employer, and OCR confidence.

    Args:
        loan_id: The loan ID to check
        doc_type: Optional document type filter (e.g. PAYSTUB, W2, BANK_STATEMENT)
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    params: Dict[str, Any] = {"loan_id": loan_id}
    type_clause = ""
    if doc_type:
        type_clause = "AND sd.doc_type = :doc_type"
        params["doc_type"] = doc_type

    documents = execute_query(f"""
        SELECT
            sd.id,
            sd.doc_type,
            sd.file_name,
            sd.extracted_dates,
            sd.extracted_names,
            sd.extracted_employer,
            sd.extracted_account_number,
            sd.extracted_amount,
            sd.extraction_confidence,
            sd.doc_date,
            sd.status,
            sd.decision
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE sd.loan_id = :loan_id
            AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'UPLOAD_FAILED')
            {type_clause}
        ORDER BY sd.doc_type, sd.created_at DESC
    """, params)

    if not documents:
        msg = f"No documents found for loan {loan_id}"
        if doc_type:
            msg += f" with type={doc_type}"
        return ToolResult.no_data(msg)

    results = []
    for doc in documents:
        has_extraction = any([
            doc.get("extracted_dates"),
            doc.get("extracted_names"),
            doc.get("extracted_employer"),
            doc.get("extracted_account_number"),
            doc.get("extracted_amount") is not None,
        ])

        results.append({
            "document_id": doc["id"],
            "doc_type": doc["doc_type"],
            "file_name": doc["file_name"],
            "status": doc["status"],
            "decision": doc.get("decision"),
            "has_extraction": has_extraction,
            "extracted_dates": doc.get("extracted_dates"),
            "extracted_names": doc.get("extracted_names"),
            "extracted_employer": doc.get("extracted_employer"),
            "extracted_account_number": doc.get("extracted_account_number"),
            "extracted_amount": float(doc["extracted_amount"]) if doc.get("extracted_amount") is not None else None,
            "extraction_confidence": doc.get("extraction_confidence"),
            "doc_date": format_date(doc["doc_date"]) if doc.get("doc_date") else None,
        })

    docs_with_data = len([d for d in results if d["has_extraction"]])

    data = {
        "loan_id": loan_id,
        "summary": {
            "total_documents": len(results),
            "with_extracted_data": docs_with_data,
            "without_extracted_data": len(results) - docs_with_data,
        },
        "documents": results,
    }

    return ToolResult.success(
        data=data,
        message=f"Extraction data: {docs_with_data}/{len(results)} documents have extracted data",
    )


# =============================================================================
# Tool 8: track_portal_activity
# =============================================================================

@mortgage_tool(
    name="track_portal_activity",
    description="Track borrower document upload activity — portal vs web uploads, latest activity, pending e-sign",
    agent_roles=["document_tracker", "lead_nurturer"],
    risk_level="LOW",
    examples=[
        "track_portal_activity(loan_id=123)",
    ],
)
def track_portal_activity(loan_id: int) -> ToolResult:
    """
    Query smart_documents with upload_source for a loan.
    Returns portal vs web vs email uploads, latest activity, and pending
    e-sign requests.

    Args:
        loan_id: The loan ID to check
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id,
               l.borrower_first_name, l.borrower_last_name
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    documents = execute_query("""
        SELECT
            sd.id,
            sd.doc_type,
            sd.file_name,
            sd.upload_source,
            sd.uploaded_at,
            sd.status,
            sd.decision
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE sd.loan_id = :loan_id
            AND sd.status NOT IN ('DELETED', 'UPLOAD_FAILED')
        ORDER BY sd.uploaded_at DESC
    """, {"loan_id": loan_id})

    # Get pending e-sign requests
    esign_requests = execute_query("""
        SELECT
            sdr.id,
            sdr.doc_type,
            sdr.title,
            sdr.status
        FROM smart_document_requests sdr
        JOIN loans l ON l.id = sdr.loan_id
        WHERE sdr.loan_id = :loan_id
            AND sdr.requires_esign = true
            AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
            AND sdr.is_active = true
    """, {"loan_id": loan_id})

    if not documents and not esign_requests:
        return ToolResult.no_data(f"No document activity found for loan {loan_id}")

    # Group by upload source
    by_source: Dict[str, int] = {}
    latest_upload = None
    for doc in documents:
        source = doc.get("upload_source") or "UNKNOWN"
        by_source[source] = by_source.get(source, 0) + 1
        if latest_upload is None:
            latest_upload = doc  # Already sorted DESC

    recent_uploads = []
    for doc in documents[:10]:  # Last 10 uploads
        recent_uploads.append({
            "document_id": doc["id"],
            "doc_type": doc["doc_type"],
            "file_name": doc["file_name"],
            "upload_source": doc.get("upload_source"),
            "uploaded_at": format_date(doc["uploaded_at"]) if doc.get("uploaded_at") else None,
            "status": doc["status"],
            "decision": doc.get("decision"),
        })

    pending_esign = []
    for req in esign_requests:
        pending_esign.append({
            "request_id": req["id"],
            "doc_type": req["doc_type"],
            "title": req["title"],
            "status": req["status"],
        })

    data = {
        "loan_id": loan_id,
        "borrower": f"{loan.get('borrower_first_name', '')} {loan.get('borrower_last_name', '')}".strip(),
        "summary": {
            "total_uploads": len(documents),
            "uploads_by_source": by_source,
            "pending_esign": len(pending_esign),
            "latest_upload_at": format_date(latest_upload["uploaded_at"]) if latest_upload and latest_upload.get("uploaded_at") else None,
        },
        "recent_uploads": recent_uploads,
        "pending_esign_requests": pending_esign,
    }

    source_str = ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items()))
    return ToolResult.success(
        data=data,
        message=f"Portal activity: {len(documents)} uploads ({source_str}), {len(pending_esign)} pending e-sign",
    )


# =============================================================================
# Tool 9: get_followup_campaign_status
# =============================================================================

@mortgage_tool(
    name="get_followup_campaign_status",
    description="Get document follow-up campaign status for a loan — active campaigns, steps completed, next scheduled action",
    agent_roles=["document_tracker", "lead_nurturer"],
    risk_level="LOW",
    examples=[
        "get_followup_campaign_status(loan_id=123)",
        "get_followup_campaign_status(loan_id=123, status_filter='active')",
    ],
)
def get_followup_campaign_status(
    loan_id: int,
    status_filter: Optional[str] = None,
) -> ToolResult:
    """
    Query document_followup_campaigns for a loan.
    Returns active campaigns, steps completed, and next scheduled action.

    Args:
        loan_id: The loan ID to check
        status_filter: Optional status filter (active, paused, completed, cancelled)
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    params: Dict[str, Any] = {"loan_id": loan_id}
    status_clause = ""
    if status_filter:
        status_clause = "AND fc.status = :status_filter"
        params["status_filter"] = status_filter

    campaigns = execute_query(f"""
        SELECT
            fc.id,
            fc.campaign_type,
            fc.status,
            fc.trigger_source,
            fc.linked_request_ids,
            fc.total_steps,
            fc.current_step,
            fc.step_config,
            fc.next_action_at,
            fc.started_at,
            fc.completed_at,
            fc.max_reminders,
            fc.reminders_sent,
            fc.borrower_responded,
            fc.response_date,
            fc.created_at
        FROM document_followup_campaigns fc
        WHERE fc.loan_id = :loan_id
            {status_clause}
        ORDER BY
            CASE fc.status
                WHEN 'active' THEN 1
                WHEN 'paused' THEN 2
                WHEN 'completed' THEN 3
                WHEN 'cancelled' THEN 4
                ELSE 5
            END,
            fc.created_at DESC
    """, params)

    if not campaigns:
        msg = f"No follow-up campaigns found for loan {loan_id}"
        if status_filter:
            msg += f" with status={status_filter}"
        return ToolResult.no_data(msg)

    results = []
    for c in campaigns:
        next_action_str = None
        if c.get("next_action_at"):
            next_action_str = format_date(c["next_action_at"], "%Y-%m-%d %H:%M")

        results.append({
            "campaign_id": c["id"],
            "campaign_type": c["campaign_type"],
            "status": c["status"],
            "trigger_source": c.get("trigger_source"),
            "linked_request_ids": c.get("linked_request_ids"),
            "progress": {
                "current_step": c.get("current_step", 0),
                "total_steps": c.get("total_steps", 0),
                "reminders_sent": c.get("reminders_sent", 0),
                "max_reminders": c.get("max_reminders", 0),
            },
            "next_action_at": next_action_str,
            "borrower_responded": c.get("borrower_responded", False),
            "response_date": format_date(c["response_date"]) if c.get("response_date") else None,
            "started_at": format_date(c["started_at"]) if c.get("started_at") else None,
            "completed_at": format_date(c["completed_at"]) if c.get("completed_at") else None,
            "created_at": format_date(c["created_at"]) if c.get("created_at") else None,
        })

    active_count = len([c for c in results if c["status"] == "active"])
    paused_count = len([c for c in results if c["status"] == "paused"])
    completed_count = len([c for c in results if c["status"] == "completed"])
    responded_count = len([c for c in results if c["borrower_responded"]])

    data = {
        "loan_id": loan_id,
        "summary": {
            "total_campaigns": len(results),
            "active": active_count,
            "paused": paused_count,
            "completed": completed_count,
            "borrower_responded": responded_count,
        },
        "campaigns": results,
    }

    return ToolResult.success(
        data=data,
        message=f"Follow-up campaigns: {active_count} active, {paused_count} paused, {completed_count} completed ({responded_count} with borrower response)",
    )


# =============================================================================
# Tool 10: get_policy_events
# =============================================================================

@mortgage_tool(
    name="get_policy_events",
    description="Get document policy events for a loan — auto-renewal, screenshot rejection, expiration, and compliance audit trail",
    agent_roles=["document_tracker", "compliance_checker"],
    risk_level="LOW",
    examples=[
        "get_policy_events(loan_id=123)",
        "get_policy_events(loan_id=123, event_type='SCREENSHOT_REJECTED')",
        "get_policy_events(loan_id=123, limit=50)",
    ],
)
def get_policy_events(
    loan_id: int,
    event_type: Optional[str] = None,
    limit: int = 25,
) -> ToolResult:
    """
    Query doc_policy_events for a loan.
    Returns recent events with type and payload, ordered by created_at desc.

    Args:
        loan_id: The loan ID to check
        event_type: Optional filter by event type (e.g. SCREENSHOT_REJECTED, EXPIRED, AUTO_REQUEST_CREATED)
        limit: Max events to return (default 25)
    """
    loan = execute_single("""
        SELECT l.id, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    params: Dict[str, Any] = {"loan_id": loan_id, "limit": limit}
    type_clause = ""
    if event_type:
        type_clause = "AND dpe.event_type = :event_type"
        params["event_type"] = event_type

    events = execute_query(f"""
        SELECT
            dpe.id,
            dpe.event_type,
            dpe.request_id,
            dpe.document_id,
            dpe.payload,
            dpe.created_at
        FROM doc_policy_events dpe
        WHERE dpe.loan_id = :loan_id
            {type_clause}
        ORDER BY dpe.created_at DESC
        LIMIT :limit
    """, params)

    if not events:
        msg = f"No policy events found for loan {loan_id}"
        if event_type:
            msg += f" with type={event_type}"
        return ToolResult.no_data(msg)

    results = []
    for e in events:
        results.append({
            "event_id": e["id"],
            "event_type": e["event_type"],
            "request_id": e.get("request_id"),
            "document_id": e.get("document_id"),
            "payload": e.get("payload"),
            "created_at": format_date(e["created_at"], "%Y-%m-%d %H:%M") if e.get("created_at") else None,
        })

    # Count by type
    type_counts: Dict[str, int] = {}
    for e in results:
        t = e["event_type"] or "unknown"
        type_counts[t] = type_counts.get(t, 0) + 1

    data = {
        "loan_id": loan_id,
        "summary": {
            "total_events": len(results),
            "by_type": type_counts,
        },
        "events": results,
    }

    type_str = ", ".join(f"{k}: {v}" for k, v in sorted(type_counts.items()))
    return ToolResult.success(
        data=data,
        message=f"Policy events: {len(results)} events ({type_str})",
    )
