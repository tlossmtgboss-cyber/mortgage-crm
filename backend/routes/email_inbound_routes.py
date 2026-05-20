"""Inbound email forwarding routes.

Endpoints:
  POST /api/v1/email/inbound/sendgrid   — SendGrid Inbound Parse webhook (no auth)
  POST /api/v1/email/inbound/manual      — Manual email import (authenticated)
  GET  /api/v1/email/inbound/setup       — Get forwarding address + Outlook instructions
  POST /api/v1/email/inbound/test        — Send a test email to verify setup
  GET  /api/v1/email/inbound/stats       — Inbound email processing stats
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ManualEmailImport(BaseModel):
    from_email: str
    from_name: Optional[str] = None
    subject: str
    body: str
    body_html: Optional[str] = None
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None


def register_email_inbound_routes(app, get_db, get_current_user):
    """Register inbound email routes with the FastAPI app."""

    # ------ SendGrid webhook (NO auth) ------
    @app.post("/api/v1/email/inbound/sendgrid", tags=["Email Inbound"])
    async def sendgrid_inbound_webhook(request: Request):
        """Receive forwarded emails from SendGrid Inbound Parse.

        No auth — security via webhook signature + unlisted endpoint.
        Returns 200 to acknowledge; non-200 triggers SendGrid retry.
        """
        db: Session = next(get_db())
        try:
            form = await request.form()
            form_dict = dict(form)

            from services.email_inbound_service import (
                parse_sendgrid_payload,
                process_inbound_email,
            )

            parsed = parse_sendgrid_payload(form_dict)

            attachments: List[Tuple[str, bytes, str]] = []
            attachment_count = int(form_dict.get("attachments", 0))
            for i in range(1, attachment_count + 1):
                att = form_dict.get(f"attachment{i}")
                if att and hasattr(att, "read"):
                    content = await att.read()
                    ct = getattr(att, "content_type", "application/octet-stream") or "application/octet-stream"
                    fn = getattr(att, "filename", f"attachment_{i}") or f"attachment_{i}"
                    attachments.append((fn, content, ct))

            result = await process_inbound_email(parsed, attachments, db)
            return {"ok": True, **result}
        except Exception as e:
            logger.exception("SendGrid inbound webhook failed")
            db.rollback()
            return {"ok": False, "error": "Processing failed"}
        finally:
            db.close()

    # ------ Manual import (authenticated) ------
    @app.post("/api/v1/email/inbound/manual", tags=["Email Inbound"])
    async def manual_email_import(
        body: ManualEmailImport,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Manually import an email for processing.

        For LOs who paste/submit an email rather than forwarding it.
        Pre-fills the LO's forwarding address so entity matching scopes
        to their pipeline.
        """
        from services.email_inbound_service import process_inbound_email

        user_id = current_user.id

        parsed = {
            "email_provider": "manual_import",
            "provider_message_id": None,
            "from_email": body.from_email,
            "from_name": body.from_name,
            "to_emails": [f"loans+{user_id}@inbound.perenniaai.com"],
            "cc_emails": [],
            "subject": body.subject,
            "body_preview": body.body[:500],
            "body_full": body.body,
            "body_html": body.body_html,
            "has_attachments": False,
            "attachment_count": 0,
            "attachment_names": [],
            "received_date": None,
            "direction": "inbound",
            "matched_loan_id": body.loan_id,
            "matched_lead_id": body.lead_id,
        }

        result = await process_inbound_email(parsed, [], db)
        return result

    # ------ Get forwarding setup (authenticated) ------
    @app.get("/api/v1/email/inbound/setup", tags=["Email Inbound"])
    async def get_forwarding_setup(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get the LO's personalized forwarding address and Outlook setup instructions."""
        from services.email_inbound_service import get_outlook_rule_instructions

        user_id = current_user.id
        first = getattr(current_user, "first_name", "") or ""
        last = getattr(current_user, "last_name", "") or ""
        full_name = f"{first} {last}".strip() or getattr(current_user, "email", "")

        return get_outlook_rule_instructions(user_id, full_name)

    # ------ Test forwarding (authenticated) ------
    @app.post("/api/v1/email/inbound/test", tags=["Email Inbound"])
    async def test_forwarding(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Process a synthetic inbound email to verify the pipeline works."""
        from services.email_inbound_service import (
            get_forwarding_address,
            process_inbound_email,
        )
        import time

        user_id = current_user.id
        fwd_addr = get_forwarding_address(user_id)

        parsed = {
            "email_provider": "test",
            "provider_message_id": f"test-{user_id}-{time.time():.0f}",
            "from_email": getattr(current_user, "email", "test@example.com"),
            "from_name": "Forwarding Test",
            "to_emails": [fwd_addr],
            "cc_emails": [],
            "subject": "Perennia Forwarding Test",
            "body_preview": "This is a test email to verify your forwarding setup.",
            "body_full": (
                "This is a test email to verify your forwarding setup. "
                "If you see this in your email intelligence queue, forwarding is working correctly."
            ),
            "body_html": None,
            "has_attachments": False,
            "attachment_count": 0,
            "attachment_names": [],
            "received_date": None,
            "direction": "inbound",
        }

        result = await process_inbound_email(parsed, [], db)
        result["test"] = True
        result["forwarding_address"] = fwd_addr
        return result

    # ------ Stats (authenticated) ------
    @app.get("/api/v1/email/inbound/stats", tags=["Email Inbound"])
    async def get_inbound_stats(
        days: int = 30,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get inbound email processing stats for the current LO."""
        user_id = current_user.id
        row = db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE matched_loan_id IS NOT NULL) AS matched_to_loan,
                    COUNT(*) FILTER (WHERE matched_lead_id IS NOT NULL) AS matched_to_lead,
                    COUNT(*) FILTER (
                        WHERE matched_loan_id IS NULL AND matched_lead_id IS NULL
                    ) AS unmatched,
                    COUNT(*) FILTER (WHERE has_attachments = true) AS with_attachments,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending_review
                FROM email_reconciliation_queue
                WHERE user_id = :uid
                  AND direction = 'inbound'
                  AND received_date >= NOW() - MAKE_INTERVAL(days => :days)
            """),
            {"uid": user_id, "days": days},
        ).first()

        return {
            "period_days": days,
            "total_received": row[0] if row else 0,
            "matched_to_loan": row[1] if row else 0,
            "matched_to_lead": row[2] if row else 0,
            "unmatched": row[3] if row else 0,
            "with_attachments": row[4] if row else 0,
            "pending_review": row[5] if row else 0,
        }

    logger.info("Email inbound routes registered (5 endpoints)")
