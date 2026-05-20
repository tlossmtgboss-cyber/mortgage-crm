"""
Perennia AI - Document Tracking Tools
Tools for the Document Tracker agent to manage loan documentation.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_date, days_between,
    LoanStatus, LoanType, DOCUMENT_CATEGORIES,
)


# Document requirement templates by loan type
DOCUMENT_REQUIREMENTS = {
    "conventional": [
        {"name": "W2s", "category": "income", "years_required": 2, "required": True},
        {"name": "Paystubs", "category": "income", "periods_required": 1, "required": True},
        {"name": "Tax Returns", "category": "income", "years_required": 2, "required": True},
        {"name": "Bank Statements", "category": "asset", "months_required": 2, "required": True},
        {"name": "Government ID", "category": "identity", "required": True},
        {"name": "Purchase Contract", "category": "property", "required": True, "purchase_only": True},
    ],
    "fha": [
        {"name": "W2s", "category": "income", "years_required": 2, "required": True},
        {"name": "Paystubs", "category": "income", "periods_required": 1, "required": True},
        {"name": "Tax Returns", "category": "income", "years_required": 2, "required": True},
        {"name": "Bank Statements", "category": "asset", "months_required": 2, "required": True},
        {"name": "Government ID", "category": "identity", "required": True},
        {"name": "FHA Case Number", "category": "compliance", "required": True},
        {"name": "HUD-92900-A", "category": "compliance", "required": True},
    ],
    "va": [
        {"name": "DD-214", "category": "identity", "required": True},
        {"name": "Certificate of Eligibility", "category": "compliance", "required": True},
        {"name": "W2s", "category": "income", "years_required": 2, "required": True},
        {"name": "Paystubs", "category": "income", "periods_required": 1, "required": True},
        {"name": "Bank Statements", "category": "asset", "months_required": 2, "required": True},
    ],
}


@mortgage_tool(
    name="get_missing_documents",
    description="Get list of missing or incomplete documents for a loan",
    agent_roles=["document_tracker", "pipeline_analyst"],
    risk_level="LOW",
    examples=[
        "get_missing_documents(loan_id='L123')",
        "get_missing_documents(loan_id='L123', category='income')",
    ],
)
def get_missing_documents(
    loan_id: str,
    category: Optional[str] = None,
) -> ToolResult:
    """
    Get missing or incomplete documents for a loan file.

    Args:
        loan_id: The loan ID to check
        category: Optional category filter (income, asset, property, etc.)
    """
    loan = execute_single("""
        SELECT l.*, lt.name as loan_type_name
        FROM loans l
        LEFT JOIN loan_types lt ON lt.id = l.loan_type_id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get existing documents
    params = {"loan_id": loan_id}
    category_filter = ""
    if category:
        category_filter = "AND d.doc_category = :category"
        params["category"] = category

    existing = execute_query(f"""
        SELECT
            d.doc_type, d.doc_category, d.status,
            d.uploaded_at, d.updated_at,
            d.notes
        FROM documents d
        WHERE d.loan_id = :loan_id {category_filter}
        ORDER BY d.doc_category, d.doc_type
    """, params)

    existing_map = {}
    for doc in existing:
        key = doc["doc_type"].lower() if doc["doc_type"] else ""
        if key not in existing_map:
            existing_map[key] = doc

    # Determine requirements based on loan type
    loan_type = (loan.get("loan_type") or "conventional").lower()
    requirements = DOCUMENT_REQUIREMENTS.get(loan_type, DOCUMENT_REQUIREMENTS["conventional"])

    missing = []
    incomplete = []
    expiring = []
    rejected = []
    received = []

    for req in requirements:
        if req.get("purchase_only") and loan.get("loan_purpose") != "purchase":
            continue

        doc_name = req["name"]
        doc_key = doc_name.lower().replace(" ", "_")

        existing_doc = existing_map.get(doc_key) or existing_map.get(doc_name.lower())

        if not existing_doc:
            missing.append({
                "document": doc_name,
                "category": req["category"],
                "required": req.get("required", True),
                "notes": _get_document_notes(req),
            })
        elif existing_doc["status"] == "rejected":
            rejected.append({
                "document": doc_name,
                "category": req["category"],
                "reason": existing_doc.get("notes", "Not specified"),
                "rejected_at": format_date(existing_doc.get("updated_at")),
            })
        elif existing_doc["status"] in ("pending_review", "incomplete"):
            incomplete.append({
                "document": doc_name,
                "category": req["category"],
                "status": existing_doc["status"],
                "uploaded_at": format_date(existing_doc["uploaded_at"]),
                "notes": existing_doc.get("notes"),
            })
        else:
            received.append({
                "document": doc_name,
                "category": req["category"],
                "status": existing_doc["status"],
            })

    # Get conditions requiring documents
    conditions = execute_query("""
        SELECT
            condition_type, description, due_date, priority
        FROM loan_conditions
        WHERE loan_id = :loan_id
            AND status = 'open'
            AND category = 'documentation'
        ORDER BY priority DESC, due_date ASC
    """, {"loan_id": loan_id})

    data = {
        "loan_id": loan_id,
        "loan_type": loan_type,
        "borrower": f"{loan.get('borrower_first_name', '')} {loan.get('borrower_last_name', '')}",
        "summary": {
            "total_required": len(requirements),
            "received": len(received),
            "missing": len(missing),
            "incomplete": len(incomplete),
            "rejected": len(rejected),
            "expiring_soon": len(expiring),
            "completion_rate": round((len(received) / len(requirements)) * 100, 1) if requirements else 0,
        },
        "missing_documents": missing,
        "incomplete_documents": incomplete,
        "rejected_documents": rejected,
        "expiring_documents": expiring,
        "outstanding_conditions": [
            {
                "type": c["condition_type"],
                "description": c["description"],
                "due_date": format_date(c["due_date"]) if c.get("due_date") else None,
                "priority": c["priority"],
            }
            for c in conditions
        ],
    }

    total_issues = len(missing) + len(incomplete) + len(rejected)
    return ToolResult.success(
        data=data,
        message=f"Document status: {len(received)}/{len(requirements)} received, {total_issues} issues ({len(missing)} missing, {len(incomplete)} incomplete, {len(rejected)} rejected)",
        total_issues=total_issues,
    )


def _get_document_notes(req: Dict) -> str:
    """Generate helpful notes for a document requirement."""
    notes = []
    if req.get("years_required"):
        notes.append(f"Need {req['years_required']} years")
    if req.get("months_required"):
        notes.append(f"Need {req['months_required']} months")
    if req.get("periods_required"):
        notes.append(f"Most recent {req['periods_required']} pay period(s)")
    return "; ".join(notes) if notes else ""


@mortgage_tool(
    name="get_loan_conditions",
    description="Get all conditions for a loan with status and priority",
    agent_roles=["document_tracker", "compliance_checker"],
    risk_level="LOW",
)
def get_loan_conditions(
    loan_id: str,
    status: Optional[str] = None,
    condition_type: Optional[str] = None,
) -> ToolResult:
    """
    Get loan conditions (Prior to Docs, Prior to Funding, Prior to Closing).

    Args:
        loan_id: The loan ID
        status: Filter by status (open, cleared, waived)
        condition_type: Filter by type (PTD, PTF, PTC, general)
    """
    params = {"loan_id": loan_id}
    filters = ["loan_id = :loan_id"]

    if status:
        filters.append("status = :status")
        params["status"] = status
    if condition_type:
        filters.append("condition_type = :condition_type")
        params["condition_type"] = condition_type

    conditions = execute_query(f"""
        SELECT
            c.*,
            COALESCE(ues.full_name, u.email) as assigned_to_name,
            COALESCE(res.full_name, r.email) as responsible_party_name
        FROM loan_conditions c
        LEFT JOIN users u ON u.id = c.assigned_to
        LEFT JOIN email_signatures ues ON ues.user_id = u.id
        LEFT JOIN users r ON r.id = c.responsible_party
        LEFT JOIN email_signatures res ON res.user_id = r.id
        WHERE {' AND '.join(filters)}
        ORDER BY
            CASE c.condition_type
                WHEN 'PTD' THEN 1
                WHEN 'PTF' THEN 2
                WHEN 'PTC' THEN 3
                ELSE 4
            END,
            c.priority DESC,
            c.due_date ASC
    """, params)

    if not conditions:
        return ToolResult.no_data(f"No conditions found for loan {loan_id}")

    # Group by type
    by_type = {"PTD": [], "PTF": [], "PTC": [], "general": []}
    for c in conditions:
        ctype = c["condition_type"] if c["condition_type"] in by_type else "general"
        by_type[ctype].append({
            "id": c["id"],
            "description": c["description"],
            "category": c.get("category"),
            "status": c["status"],
            "priority": c["priority"],
            "due_date": format_date(c["due_date"]) if c.get("due_date") else None,
            "days_until_due": days_between(date.today(), c["due_date"]) if c.get("due_date") else None,
            "assigned_to": c["assigned_to_name"],
            "responsible_party": c["responsible_party_name"],
            "notes": c.get("notes"),
            "created_at": format_date(c["created_at"]),
        })

    # Summary stats
    open_count = len([c for c in conditions if c["status"] == "open"])
    overdue = len([c for c in conditions if c["status"] == "open" and c.get("due_date") and c["due_date"] < date.today()])

    data = {
        "loan_id": loan_id,
        "summary": {
            "total": len(conditions),
            "open": open_count,
            "cleared": len([c for c in conditions if c["status"] == "cleared"]),
            "waived": len([c for c in conditions if c["status"] == "waived"]),
            "overdue": overdue,
        },
        "by_type": {
            "prior_to_docs": by_type["PTD"],
            "prior_to_funding": by_type["PTF"],
            "prior_to_closing": by_type["PTC"],
            "general": by_type["general"],
        },
        "critical_conditions": [
            c for c in conditions
            if c["status"] == "open" and c["priority"] >= 3
        ][:5],
    }

    return ToolResult.success(
        data=data,
        message=f"Conditions: {open_count} open ({overdue} overdue), {len(conditions)} total",
    )


@mortgage_tool(
    name="track_document_request",
    description="Create or update a document request for a borrower",
    agent_roles=["document_tracker"],
    risk_level="MEDIUM",
)
def track_document_request(
    loan_id: str,
    document_type: str,
    request_reason: str,
    priority: int = 2,
    due_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> ToolResult:
    """
    Create a tracked document request.

    Args:
        loan_id: The loan ID
        document_type: Type of document needed
        request_reason: Why the document is needed
        priority: 1-5 (5 is highest)
        due_date: When document is needed (YYYY-MM-DD)
        notes: Additional notes for borrower
    """
    # Validate loan exists
    loan = execute_single("""
        SELECT id, borrower_first_name, borrower_last_name, borrower_email
        FROM loans WHERE id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Check for existing open request
    existing = execute_single("""
        SELECT id, request_count FROM document_requests
        WHERE loan_id = :loan_id
            AND document_type = :document_type
            AND status = 'pending'
    """, {"loan_id": loan_id, "document_type": document_type})

    if existing:
        # Update existing request
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text("""
                UPDATE document_requests
                SET request_count = request_count + 1,
                    last_requested_at = CURRENT_TIMESTAMP,
                    priority = GREATEST(priority, :priority),
                    notes = COALESCE(:notes, notes)
                WHERE id = :request_id
            """), {"request_id": existing["id"], "priority": priority, "notes": notes})

        request_id = existing["id"]
        is_followup = True
        request_count = existing["request_count"] + 1
    else:
        # Create new request
        from sqlalchemy import text
        with get_db() as db:
            result = db.execute(text("""
                INSERT INTO document_requests
                    (loan_id, document_type, request_reason, priority, due_date, notes, status, request_count)
                VALUES
                    (:loan_id, :document_type, :request_reason, :priority, :due_date, :notes, 'pending', 1)
                RETURNING id
            """), {
                "loan_id": loan_id,
                "document_type": document_type,
                "request_reason": request_reason,
                "priority": priority,
                "due_date": due_date,
                "notes": notes,
            })
            request_id = result.fetchone()[0]

        is_followup = False
        request_count = 1

    data = {
        "request_id": request_id,
        "loan_id": loan_id,
        "document_type": document_type,
        "priority": priority,
        "is_followup": is_followup,
        "request_count": request_count,
        "borrower": f"{loan['borrower_first_name']} {loan['borrower_last_name']}",
        "borrower_email": loan["borrower_email"],
        "escalation_status": _get_escalation_status(request_count),
    }

    action = "Follow-up" if is_followup else "Created"
    return ToolResult.success(
        data=data,
        message=f"{action} request for {document_type} (request #{request_count})",
    )


def _get_escalation_status(request_count: int) -> Dict:
    """Determine escalation status based on request count."""
    if request_count >= 4:
        return {"level": "critical", "action": "Escalate to manager and consider alternative documentation"}
    elif request_count >= 3:
        return {"level": "high", "action": "Phone call required, escalate to LO"}
    elif request_count >= 2:
        return {"level": "medium", "action": "Follow-up call recommended"}
    else:
        return {"level": "normal", "action": "Standard request sent"}


@mortgage_tool(
    name="send_document_reminder",
    description="Send a reminder to borrower for outstanding documents",
    agent_roles=["document_tracker"],
    risk_level="HIGH",
)
def send_document_reminder(
    loan_id: str,
    reminder_type: str = "email",
    include_all_missing: bool = True,
    specific_documents: Optional[List[str]] = None,
    custom_message: Optional[str] = None,
) -> ToolResult:
    """
    Send document reminder to borrower.

    Args:
        loan_id: The loan ID
        reminder_type: email, sms, or both
        include_all_missing: Include all missing documents
        specific_documents: List of specific documents to request
        custom_message: Custom message to include
    """
    # Get loan and borrower info
    loan = execute_single("""
        SELECT
            l.*,
            COALESCE(loes.full_name, lo.email) as lo_name, lo.email as lo_email
        FROM loans l
        LEFT JOIN users lo ON lo.id = l.loan_officer_id
        LEFT JOIN email_signatures loes ON loes.user_id = lo.id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get missing documents
    missing_result = get_missing_documents(loan_id)
    if missing_result.status.value != "success":
        return missing_result

    missing_docs = missing_result.data.get("missing_documents", [])
    incomplete_docs = missing_result.data.get("incomplete_documents", [])
    rejected_docs = missing_result.data.get("rejected_documents", [])

    # Determine what to include
    docs_to_request = []
    if specific_documents:
        docs_to_request = [d for d in missing_docs + incomplete_docs + rejected_docs
                          if d["document"] in specific_documents]
    elif include_all_missing:
        docs_to_request = missing_docs + incomplete_docs + rejected_docs

    if not docs_to_request:
        return ToolResult.no_data("No documents to request")

    # TCPA/DNC compliance check before sending SMS
    sms_blocked_reason = None
    if reminder_type in ("sms", "both"):
        borrower_phone = loan.get("borrower_phone")
        if borrower_phone:
            from .notifications import _check_sms_compliance
            compliance_error = _check_sms_compliance(borrower_phone)
            if compliance_error:
                sms_blocked_reason = compliance_error.message
                logger.warning(f"SMS skipped for document reminder on loan {loan_id} (compliance): {sms_blocked_reason}")
                if reminder_type == "sms":
                    return ToolResult.error(f"Cannot send SMS reminder: {sms_blocked_reason}")
                # Downgrade "both" to "email" only
                reminder_type = "email"
        else:
            # No phone on file — if SMS-only, fail; if both, downgrade to email
            if reminder_type == "sms":
                return ToolResult.error("No borrower phone number on file for SMS reminder")
            reminder_type = "email"

    # --- Actually send the SMS if reminder_type is "sms" or "both" ---
    sms_result = None
    if reminder_type in ("sms", "both"):
        borrower_phone = loan.get("borrower_phone")
        borrower_name = f"{loan.get('borrower_first_name', '')} {loan.get('borrower_last_name', '')}".strip()
        lo_name = loan.get("lo_name", "your loan officer")
        doc_names = [d["document"] for d in docs_to_request]

        # Compose SMS body
        if custom_message:
            sms_body = custom_message
        else:
            doc_list_str = ", ".join(doc_names[:5])
            if len(doc_names) > 5:
                doc_list_str += f" (+{len(doc_names) - 5} more)"
            sms_body = (
                f"Hi {borrower_name}, this is a reminder from {lo_name}. "
                f"We still need the following documents for your loan: {doc_list_str}. "
                f"Please upload or reply to this message with any questions."
            )

        try:
            from telephony.sms import send_sms_verified

            sms_result = send_sms_verified(
                to=borrower_phone,
                text=sms_body,
                bypass_compliance=True,  # compliance already checked above
            )

            if sms_result.get("status") == "blocked":
                blocked_reason = sms_result.get("reason", "Unknown")
                logger.warning(
                    "SMS send blocked for loan %s: %s", loan_id, blocked_reason
                )
                if reminder_type == "sms":
                    return ToolResult.error(
                        f"SMS reminder blocked: {blocked_reason}"
                    )
                # "both" — downgrade to email-only, continue
                reminder_type = "email"
                sms_result = None

        except Exception as e:
            logger.exception("SMS send failed for document reminder on loan %s", loan_id)
            if reminder_type == "sms":
                return ToolResult.error(f"SMS send failed: {e}")
            # "both" — downgrade to email-only, continue
            reminder_type = "email"
            sms_result = None

    # Create reminder record
    from sqlalchemy import text
    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO document_reminders
                (loan_id, reminder_type, documents_requested, custom_message, sent_at)
            VALUES
                (:loan_id, :reminder_type, :documents, :custom_message, CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            "loan_id": loan_id,
            "reminder_type": reminder_type,
            "documents": ",".join([d["document"] for d in docs_to_request]),
            "custom_message": custom_message,
        })
        reminder_id = result.fetchone()[0]

    doc_names_requested = [d["document"] for d in docs_to_request]

    data = {
        "reminder_id": reminder_id,
        "loan_id": loan_id,
        "borrower": {
            "name": f"{loan['borrower_first_name']} {loan['borrower_last_name']}",
            "email": loan.get("borrower_email"),
            "phone": loan.get("borrower_phone"),
        },
        "loan_officer": {
            "name": loan["lo_name"],
            "email": loan["lo_email"],
            "phone": loan.get("lo_phone"),
        },
        "reminder_type": reminder_type,
        "documents_requested": doc_names_requested,
        "document_details": docs_to_request,
        "status": "sent",
        "sent_at": datetime.now().isoformat(),
    }

    if sms_result:
        data["sms_message_id"] = sms_result.get("id")

    return ToolResult.success(
        data=data,
        message=f"Reminder sent via {reminder_type} for {len(docs_to_request)} documents",
    )


@mortgage_tool(
    name="escalate_issue",
    description="Escalate a document issue to appropriate party",
    agent_roles=["document_tracker"],
    risk_level="MEDIUM",
)
def escalate_issue(
    loan_id: str,
    document_type: str,
    issue_description: str,
    escalate_to: str = "lo",
    urgency: str = "normal",
) -> ToolResult:
    """
    Escalate a document issue.

    Args:
        loan_id: The loan ID
        document_type: The problematic document
        issue_description: Description of the issue
        escalate_to: lo, processor, manager, underwriter
        urgency: normal, high, critical
    """
    # Get loan and assigned personnel
    loan = execute_single("""
        SELECT
            l.*,
            lo.id as lo_id, COALESCE(loes.full_name, lo.email) as lo_name, lo.email as lo_email,
            p.id as processor_id, COALESCE(pes.full_name, p.email) as processor_name, p.email as processor_email,
            m.id as manager_id, COALESCE(mes.full_name, m.email) as manager_name, m.email as manager_email
        FROM loans l
        LEFT JOIN users lo ON lo.id = l.loan_officer_id
        LEFT JOIN email_signatures loes ON loes.user_id = lo.id
        LEFT JOIN users p ON p.id = l.processor_id
        LEFT JOIN email_signatures pes ON pes.user_id = p.id
        LEFT JOIN users m ON m.id = lo.manager_id
        LEFT JOIN email_signatures mes ON mes.user_id = m.id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Determine recipient
    recipient_map = {
        "lo": {"id": loan["lo_id"], "name": loan["lo_name"], "email": loan["lo_email"]},
        "processor": {"id": loan["processor_id"], "name": loan["processor_name"], "email": loan["processor_email"]},
        "manager": {"id": loan["manager_id"], "name": loan["manager_name"], "email": loan["manager_email"]},
    }
    recipient = recipient_map.get(escalate_to, recipient_map["lo"])

    # Create escalation record
    from sqlalchemy import text
    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO document_escalations
                (loan_id, document_type, issue_description, escalated_to, urgency, status)
            VALUES
                (:loan_id, :document_type, :issue_description, :escalated_to, :urgency, 'open')
            RETURNING id
        """), {
            "loan_id": loan_id,
            "document_type": document_type,
            "issue_description": issue_description,
            "escalated_to": recipient["id"],
            "urgency": urgency,
        })
        escalation_id = result.fetchone()[0]

    data = {
        "escalation_id": escalation_id,
        "loan_id": loan_id,
        "document_type": document_type,
        "issue": issue_description,
        "escalated_to": recipient,
        "urgency": urgency,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "recommended_actions": _get_escalation_actions(urgency, document_type),
    }

    return ToolResult.success(
        data=data,
        message=f"Escalated {document_type} issue to {recipient['name']} ({urgency} priority)",
    )


def _get_escalation_actions(urgency: str, document_type: str) -> List[str]:
    """Get recommended actions based on escalation."""
    actions = ["Review document requirements with borrower"]

    if urgency in ("high", "critical"):
        actions.extend([
            "Call borrower directly within 24 hours",
            "Consider alternative documentation options",
        ])

    if urgency == "critical":
        actions.extend([
            "Notify underwriter of potential delay",
            "Update expected close date if necessary",
        ])

    return actions


@mortgage_tool(
    name="get_document_timeline",
    description="Get timeline of document activity for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_document_timeline(
    loan_id: str,
    days_back: int = 30,
) -> ToolResult:
    """
    Get document activity timeline for a loan.
    """
    events = execute_query("""
        SELECT
            'upload' as event_type,
            d.doc_type as document_type,
            d.uploaded_at as event_date,
            d.status,
            COALESCE(es.full_name, u.email) as actor_name,
            d.notes
        FROM documents d
        LEFT JOIN users u ON u.id = d.uploaded_by_user_id
        LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE d.loan_id = :loan_id
            AND d.uploaded_at >= CURRENT_DATE - :days_back

        UNION ALL

        SELECT
            'request' as event_type,
            dr.document_type,
            dr.last_requested_at as event_date,
            'requested' as status,
            NULL as actor_name,
            dr.request_reason as notes
        FROM document_requests dr
        WHERE dr.loan_id = :loan_id
            AND dr.last_requested_at >= CURRENT_DATE - :days_back

        UNION ALL

        SELECT
            'reminder' as event_type,
            drm.documents_requested as document_type,
            drm.sent_at as event_date,
            drm.reminder_type as status,
            NULL as actor_name,
            drm.custom_message as notes
        FROM document_reminders drm
        WHERE drm.loan_id = :loan_id
            AND drm.sent_at >= CURRENT_DATE - :days_back

        ORDER BY event_date DESC
    """, {"loan_id": loan_id, "days_back": days_back})

    if not events:
        return ToolResult.no_data(f"No document activity in last {days_back} days")

    # Group by date
    by_date = {}
    for e in events:
        date_key = e["event_date"].strftime("%Y-%m-%d")
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append({
            "type": e["event_type"],
            "document": e["document_type"],
            "status": e["status"],
            "actor": e["actor_name"],
            "notes": e["notes"],
            "time": e["event_date"].strftime("%H:%M"),
        })

    data = {
        "loan_id": loan_id,
        "period_days": days_back,
        "total_events": len(events),
        "timeline": [
            {"date": d, "events": by_date[d]}
            for d in sorted(by_date.keys(), reverse=True)
        ],
        "summary": {
            "uploads": len([e for e in events if e["event_type"] == "upload"]),
            "requests": len([e for e in events if e["event_type"] == "request"]),
            "reminders": len([e for e in events if e["event_type"] == "reminder"]),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Document timeline: {len(events)} events in last {days_back} days",
    )


@mortgage_tool(
    name="check_document_expiration",
    description="Check for documents nearing or past expiration",
    agent_roles=["document_tracker", "compliance_checker"],
    risk_level="LOW",
)
def check_document_expiration(
    loan_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days_ahead: int = 30,
) -> ToolResult:
    """
    Check for expiring documents across loans.

    Standard document expirations:
    - Paystubs: 30 days
    - Bank statements: 60 days
    - Credit report: 120 days
    - VOE: 30 days
    - Appraisal: 120 days (180 for certain loans)
    """
    params = {"days_ahead": days_ahead}
    filters = ["d.period_end_date IS NOT NULL"]

    if loan_id:
        filters.append("d.loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id

    documents = execute_query(f"""
        SELECT
            d.loan_id,
            l.borrower_first_name || ' ' || l.borrower_last_name as borrower_name,
            d.doc_type as document_type,
            d.doc_category as category,
            d.period_end_date as expiration_date,
            d.uploaded_at,
            l.target_close_date as expected_close_date,
            l.stage as loan_status
        FROM documents d
        JOIN loans l ON l.id = d.loan_id
        WHERE {' AND '.join(filters)}
            AND d.period_end_date IS NOT NULL
            AND d.period_end_date <= CURRENT_DATE + :days_ahead
            AND l.stage NOT IN ('FUNDED')
        ORDER BY d.period_end_date ASC
    """, params)

    expired = []
    expiring_soon = []

    today = date.today()
    for doc in documents:
        days_until = days_between(today, doc["expiration_date"])
        entry = {
            "loan_id": doc["loan_id"],
            "borrower": doc["borrower_name"],
            "document": doc["document_type"],
            "category": doc["category"],
            "expiration_date": format_date(doc["expiration_date"]),
            "days_until_expiration": days_until,
            "expected_close": format_date(doc["expected_close_date"]) if doc.get("expected_close_date") else None,
            "at_risk": days_until < 0 or (doc.get("expected_close_date") and days_until < days_between(today, doc["expected_close_date"])),
        }

        if days_until < 0:
            expired.append(entry)
        else:
            expiring_soon.append(entry)

    data = {
        "check_date": today.isoformat(),
        "days_ahead_checked": days_ahead,
        "summary": {
            "total_flagged": len(documents),
            "expired": len(expired),
            "expiring_soon": len(expiring_soon),
            "at_risk_loans": len(set(d["loan_id"] for d in expired + expiring_soon if d["at_risk"])),
        },
        "expired_documents": expired,
        "expiring_documents": expiring_soon,
    }

    return ToolResult.success(
        data=data,
        message=f"Document expiration: {len(expired)} expired, {len(expiring_soon)} expiring within {days_ahead} days",
    )


@mortgage_tool(
    name="get_third_party_status",
    description="Get status of third-party orders (appraisal, title, insurance)",
    agent_roles=["document_tracker", "pipeline_analyst"],
    risk_level="LOW",
)
def get_third_party_status(loan_id: str) -> ToolResult:
    """
    Get status of all third-party orders for a loan.
    """
    orders = execute_query("""
        SELECT
            o.order_type,
            o.vendor_name,
            o.status,
            o.ordered_at,
            o.due_date,
            o.received_at,
            o.amount,
            o.rush_fee,
            o.notes,
            o.tracking_number
        FROM third_party_orders o
        WHERE o.loan_id = :loan_id
        ORDER BY
            CASE o.order_type
                WHEN 'appraisal' THEN 1
                WHEN 'title' THEN 2
                WHEN 'insurance' THEN 3
                ELSE 4
            END
    """, {"loan_id": loan_id})

    if not orders:
        return ToolResult.no_data(f"No third-party orders found for loan {loan_id}")

    # Standard order types to check
    expected_orders = ["appraisal", "title", "insurance", "survey", "flood_cert"]
    existing_types = [o["order_type"] for o in orders]
    missing_orders = [t for t in expected_orders if t not in existing_types]

    order_details = []
    overdue = []
    pending = []

    today = date.today()
    for o in orders:
        days_pending = days_between(o["ordered_at"]) if o["ordered_at"] else None
        is_overdue = o.get("due_date") and o["due_date"] < today and not o.get("received_at")

        detail = {
            "type": o["order_type"],
            "vendor": o["vendor_name"],
            "status": o["status"],
            "ordered": format_date(o["ordered_at"]) if o.get("ordered_at") else None,
            "due": format_date(o["due_date"]) if o.get("due_date") else None,
            "received": format_date(o["received_at"]) if o.get("received_at") else None,
            "days_pending": days_pending,
            "is_overdue": is_overdue,
            "cost": float(o["amount"]) if o.get("amount") else None,
            "rush_fee": float(o["rush_fee"]) if o.get("rush_fee") else None,
            "tracking": o.get("tracking_number"),
        }
        order_details.append(detail)

        if is_overdue:
            overdue.append(detail)
        elif o["status"] in ("ordered", "in_progress", "pending"):
            pending.append(detail)

    total_cost = sum(float(o["amount"] or 0) + float(o["rush_fee"] or 0) for o in orders)

    data = {
        "loan_id": loan_id,
        "summary": {
            "total_orders": len(orders),
            "pending": len(pending),
            "overdue": len(overdue),
            "completed": len([o for o in orders if o["status"] == "completed"]),
            "missing_orders": missing_orders,
            "total_cost": total_cost,
        },
        "orders": order_details,
        "overdue_orders": overdue,
        "pending_orders": pending,
        "alerts": [
            f"{len(overdue)} overdue orders require immediate attention" if overdue else None,
            f"Missing orders: {', '.join(missing_orders)}" if missing_orders else None,
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"Third-party orders: {len(orders)} total, {len(pending)} pending, {len(overdue)} overdue",
    )
