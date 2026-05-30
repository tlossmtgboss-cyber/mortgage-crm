"""
agents/tools/document_tools.py
Perennia AI — Document Generation Tools for Aria Voice Agent

@mortgage_tool registration for generating and sending pre-approval letters
and other documents on voice command.
"""

import base64
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from .base import (
    mortgage_tool,
    ToolResult,
    execute_single,
    db_session,
)

logger = logging.getLogger(__name__)


@mortgage_tool(
    name="generate_pre_approval_letter",
    description="Generate a pre-approval letter PDF for a borrower and email it to them. Looks up borrower and LO details from the CRM.",
    agent_roles=["voice_os", "document_tracker", "lead_nurturer"],
    risk_level="MEDIUM",
    requires_confirmation=True,
    parameters={
        "lead_id": "Lead/borrower ID in the CRM",
        "approval_amount": "Pre-approval dollar amount",
        "loan_type": "Loan type: Conventional, FHA, VA, USDA, Jumbo",
        "property_address": "Optional property address for the letter",
        "recipient_email": "Optional email to send the letter to (defaults to borrower's email)",
        "user_id": "LO user ID (for letterhead and signature)",
    },
)
def generate_pre_approval_letter(
    lead_id: str,
    approval_amount: str,
    loan_type: str = "Conventional",
    property_address: Optional[str] = None,
    recipient_email: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ToolResult:
    """Generate pre-approval letter PDF and email to borrower."""

    # Parse approval amount
    try:
        amount = float(str(approval_amount).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return ToolResult.error(f"Invalid approval amount: {approval_amount}")

    if amount <= 0 or amount > 50_000_000:
        return ToolResult.error("Approval amount must be between $1 and $50,000,000")

    # Look up lead/borrower
    lead = execute_single(
        """SELECT id, first_name, last_name, email, phone,
                  organization_id
           FROM leads WHERE id = :lead_id""",
        {"lead_id": int(lead_id)},
    )
    if not lead:
        return ToolResult.error(f"Lead {lead_id} not found")

    borrower_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    borrower_email = recipient_email or lead.get("email", "")

    if not borrower_email:
        return ToolResult.error(f"No email address for {borrower_name}. Provide recipient_email.")

    # Look up LO info
    lo = {}
    if user_id:
        lo = execute_single(
            """SELECT id, full_name, email, phone, nmls_id,
                      organization_id
               FROM users WHERE id = :uid""",
            {"uid": int(user_id)},
        ) or {}

    lo_name = lo.get("full_name", "Loan Officer")
    lo_email = lo.get("email", "")
    lo_nmls = lo.get("nmls_id", "")
    org_id = lead.get("organization_id") or lo.get("organization_id")

    # Look up org branding
    org_name = "The Tim Loss Team"
    if org_id:
        org = execute_single(
            "SELECT name FROM organizations WHERE id = :oid",
            {"oid": org_id},
        )
        if org:
            org_name = org.get("name", org_name)

    # Generate the letter using DocumentGenerator
    try:
        from aria.documents.document_generator import DocumentGenerator
        import asyncio

        generator = DocumentGenerator()

        borrower_dict = {
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "full_name": borrower_name,
        }
        loan_dict = {
            "loan_type": loan_type,
            "loan_amount": amount,
        }
        lo_dict = {
            "full_name": lo_name,
            "email": lo_email,
            # Generator reads `nmls_number` / `org_name` (see document_generator
            # .generate_preapproval_letter). Supplying the old `nmls_id` /
            # `organization_name` keys rendered a BLANK NMLS# and org on the
            # letter — a regulatory defect on a mortgage solicitation.
            "nmls_number": lo_nmls,
            "nmls_id": lo_nmls,
            "org_name": org_name,
            "organization_name": org_name,
        }

        # Run the async generator in a new event loop (we're in a thread)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                generator.generate_preapproval_letter(
                    borrower=borrower_dict,
                    loan=loan_dict,
                    lo=lo_dict,
                    approval_amount=amount,
                    property_address=property_address,
                    expiry_days=30,
                )
            )
        finally:
            loop.close()

        pdf_bytes = result.get("pdf_bytes")
        if not pdf_bytes:
            return ToolResult.error("PDF generation returned empty document")

    except ImportError:
        return ToolResult.error("Document generator not available")
    except Exception as e:
        logger.error(f"Pre-approval letter generation failed: {e}", exc_info=True)
        return ToolResult.error(f"Letter generation failed: {e}")

    # Email the letter
    try:
        from services.email_delivery_service import EmailDeliveryService
        import asyncio

        email_service = EmailDeliveryService()

        subject = f"Pre-Approval Letter — {borrower_name}"
        body = (
            f"Hi {lead.get('first_name', 'there')},\n\n"
            f"Please find your pre-approval letter attached. "
            f"You have been pre-approved for up to ${amount:,.0f} "
            f"for a {loan_type} mortgage.\n\n"
            f"This pre-approval is valid for 30 days. "
            f"Please don't hesitate to reach out with any questions.\n\n"
            f"Best regards,\n{lo_name}\n{org_name}"
        )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                email_service.send_email(
                    to=borrower_email,
                    subject=subject,
                    text_body=body,
                    from_email=lo_email or None,
                    from_name=lo_name,
                    attachments=[{
                        "filename": f"Pre-Approval-Letter-{borrower_name.replace(' ', '-')}.pdf",
                        "content": base64.b64encode(pdf_bytes).decode("utf-8"),
                        "content_type": "application/pdf",
                    }],
                    organization_id=org_id,
                    user_id=str(user_id) if user_id else None,
                )
            )
        finally:
            loop.close()

        email_sent = True
    except Exception as e:
        logger.warning(f"Pre-approval letter generated but email failed: {e}")
        email_sent = False

    return ToolResult.success(
        data={
            "borrower_name": borrower_name,
            "borrower_email": borrower_email,
            "approval_amount": f"${amount:,.0f}",
            "loan_type": loan_type,
            "property_address": property_address or "TBD",
            "lo_name": lo_name,
            "organization": org_name,
            "email_sent": email_sent,
            "document_id": result.get("document_id", ""),
            "expiry_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%B %d, %Y"),
        },
        message=(
            f"Pre-approval letter generated for {borrower_name} — ${amount:,.0f} {loan_type}. "
            + (f"Emailed to {borrower_email}." if email_sent else "Email delivery failed — letter generated but not sent.")
        ),
    )
