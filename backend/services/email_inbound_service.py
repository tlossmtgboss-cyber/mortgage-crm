"""Inbound email forwarding service.

Processes emails forwarded by LOs from Outlook (via SendGrid Inbound Parse)
and routes them through the AI classification → entity matching → loan
update pipeline.

Flow:
  1. Parse SendGrid webhook payload (multipart form: envelope, headers, text,
     html, attachments)
  2. Resolve forwarding LO from the recipient address
     (loans+{user_id}@inbound.perenniaai.com)
  3. Classify email content via DRE helpers
  4. Match to loan/lead via EmailIdentityResolver
  5. Upload attachments as Smart Documents
  6. Apply extracted data to the matched loan
  7. Create timeline activity and insert into reconciliation queue
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

INBOUND_DOMAIN = "inbound.perenniaai.com"
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20 MB per attachment
MAX_ATTACHMENTS = 10
ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "image/",
    "application/vnd.openxmlformats",
    "application/vnd.ms-",
    "application/msword",
    "text/plain",
    "text/csv",
)


# ------------------------------------------------------------------ helpers
def _parse_plus_address(to_emails: List[str]) -> Optional[int]:
    """Extract user_id from a plus-addressed recipient.

    Looks for patterns like:
      loans+42@inbound.perenniaai.com
      inbox+42@inbound.perenniaai.com
    """
    for addr in to_emails:
        addr = addr.lower().strip()
        m = re.match(
            r"^(?:loans|inbox)\+(\d+)@" + re.escape(INBOUND_DOMAIN) + r"$",
            addr,
        )
        if m:
            return int(m.group(1))
    return None


def _dedup_key(from_email: str, subject: str, received_date: str) -> str:
    """Deterministic dedup hash for emails without a provider message ID."""
    raw = f"{from_email}|{subject}|{received_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _safe_filename(name: str) -> str:
    """Sanitize an attachment filename."""
    name = re.sub(r"[^\w\s.\-]", "_", name)
    if len(name) > 200:
        name = name[:200]
    return name or "attachment"


# -------------------------------------------------------- SendGrid parsing
def parse_sendgrid_payload(form: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a SendGrid Inbound Parse webhook form into a normalized dict.

    SendGrid posts:
      envelope (JSON string) — {to: [], from: ""}
      from, to, cc, subject, text, html, headers,
      attachments (integer count), attachment1..N (file objects)
      dkim, SPF, sender_ip, charsets (JSON string)

    Returns a dict compatible with import_email_to_queue().
    """
    envelope = json.loads(form.get("envelope", "{}"))
    charsets = json.loads(form.get("charsets", "{}"))

    to_emails = envelope.get("to", [])
    if isinstance(to_emails, str):
        to_emails = [to_emails]

    from_header = form.get("from", envelope.get("from", ""))
    from_name, from_email = _parse_from_header(from_header)

    cc_raw = form.get("cc", "")
    cc_emails = [e.strip() for e in cc_raw.split(",") if e.strip()] if cc_raw else []

    subject = form.get("subject", "(no subject)")
    body_text = form.get("text", "")
    body_html = form.get("html", "")
    received_date = datetime.now(ET).isoformat()

    attachment_count = int(form.get("attachments", 0))
    attachment_names: List[str] = []
    for i in range(1, attachment_count + 1):
        att = form.get(f"attachment{i}")
        if att and hasattr(att, "filename"):
            attachment_names.append(att.filename or f"attachment_{i}")

    return {
        "email_provider": "sendgrid_inbound",
        "provider_message_id": form.get("Message-Id") or _dedup_key(from_email or "", subject, received_date),
        "from_email": from_email,
        "from_name": from_name,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": subject,
        "body_preview": (body_text or "")[:500],
        "body_full": body_text,
        "body_html": body_html,
        "has_attachments": attachment_count > 0,
        "attachment_count": attachment_count,
        "attachment_names": attachment_names,
        "received_date": received_date,
        "direction": "inbound",
        "sender_ip": form.get("sender_ip"),
        "spf": form.get("SPF"),
        "dkim": form.get("dkim"),
        "charsets": charsets,
    }


def _parse_from_header(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse 'Display Name <email>' or plain email."""
    if not raw:
        return None, None
    m = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    m2 = re.match(r"^<?([^<>\s]+@[^<>\s]+)>?$", raw.strip())
    if m2:
        return None, m2.group(1).lower()
    return None, raw.strip().lower()


# -------------------------------------------------------- LO resolution
def resolve_lo_from_address(
    to_emails: List[str], db: Session
) -> Optional[Dict[str, Any]]:
    """Resolve the loan officer from the plus-addressed recipient.

    Returns {user_id, organization_id, email, name} or None.
    """
    user_id = _parse_plus_address(to_emails)
    if user_id is None:
        return None

    row = db.execute(
        text("""
            SELECT id, organization_id, email,
                   COALESCE(first_name || ' ' || last_name, email) AS name
            FROM users
            WHERE id = :uid AND is_active = true
        """),
        {"uid": user_id},
    ).first()

    if not row:
        return None

    return {
        "user_id": row[0],
        "organization_id": row[1],
        "email": row[2],
        "name": row[3],
    }


# -------------------------------------------------------- main pipeline
async def process_inbound_email(
    parsed: Dict[str, Any],
    attachments: List[Tuple[str, bytes, str]],
    db: Session,
) -> Dict[str, Any]:
    """Full inbound email processing pipeline.

    Args:
        parsed: Normalized email dict from parse_sendgrid_payload().
        attachments: List of (filename, content_bytes, content_type).
        db: Active SQLAlchemy session.

    Returns:
        Processing result dict with status, matched entity info, etc.
    """
    result: Dict[str, Any] = {
        "status": "processed",
        "email_id": None,
        "matched_loan_id": None,
        "matched_lead_id": None,
        "classification": None,
        "extracted_fields": None,
        "documents_created": [],
        "activity_id": None,
        "errors": [],
    }

    # --- Step 1: Resolve LO ---
    lo = resolve_lo_from_address(parsed.get("to_emails", []), db)
    if not lo:
        result["status"] = "unresolved_lo"
        result["errors"].append(
            "Could not resolve loan officer from recipient address"
        )
        _insert_queue_record(parsed, db, status="needs_review")
        return result

    user_id = lo["user_id"]
    org_id = lo["organization_id"]

    # --- Step 2: Dedup check ---
    msg_id = parsed.get("provider_message_id")
    if msg_id:
        existing = db.execute(
            text("""
                SELECT id FROM email_reconciliation_queue
                WHERE provider_message_id = :mid
            """),
            {"mid": msg_id},
        ).first()
        if existing:
            return {"status": "duplicate", "existing_id": existing[0]}

    # --- Step 3: Classify ---
    classification = None
    extracted_fields = None
    try:
        from services.dre_helpers import classify_email_content, extract_loan_fields

        classification = classify_email_content(
            content=parsed.get("body_full") or parsed.get("body_preview", ""),
            subject=parsed.get("subject", ""),
        )
        result["classification"] = classification

        category = classification.get("category", "unrelated")
        if category != "unrelated":
            extracted_fields = extract_loan_fields(
                content=parsed.get("body_full") or parsed.get("body_preview", ""),
                category=category,
            )
            result["extracted_fields"] = extracted_fields
    except Exception as e:
        logger.error("Email classification failed: %s", e)
        result["errors"].append(f"Classification failed: {e}")

    # --- Step 4: Entity matching ---
    match_result = None
    try:
        from services.email_identity_resolver import get_email_identity_resolver

        resolver = get_email_identity_resolver(db)
        enriched = {**parsed}
        if extracted_fields:
            enriched["extracted_data"] = {
                k: v.get("value") if isinstance(v, dict) else v
                for k, v in extracted_fields.items()
            }
        match_result = resolver.resolve(enriched, user_id)
    except Exception as e:
        logger.error("Entity matching failed: %s", e)
        result["errors"].append(f"Entity matching failed: {e}")

    matched_loan_id = None
    matched_lead_id = None
    matched_contact_id = None
    if match_result:
        matched_loan_id = match_result.get("matched_loan_id")
        matched_lead_id = match_result.get("matched_lead_id")
        matched_contact_id = match_result.get("matched_contact_id")
        result["matched_loan_id"] = matched_loan_id
        result["matched_lead_id"] = matched_lead_id

    # --- Step 5: Insert into reconciliation queue ---
    email_id = _insert_queue_record(
        parsed,
        db,
        user_id=user_id,
        matched_loan_id=matched_loan_id,
        matched_lead_id=matched_lead_id,
        matched_contact_id=matched_contact_id,
        match_result=match_result,
        classification=classification,
    )
    result["email_id"] = email_id

    # --- Step 6: Upload attachments as Smart Docs (if matched to loan) ---
    if matched_loan_id and attachments:
        borrower_id = _get_primary_borrower_id(db, matched_loan_id)
        docs = await _upload_attachments_as_docs(
            attachments=attachments,
            loan_id=matched_loan_id,
            borrower_id=borrower_id,
            org_id=org_id,
            email_id=email_id,
            db=db,
        )
        result["documents_created"] = docs

    # --- Step 7: Apply extracted data ---
    if matched_loan_id and extracted_fields:
        try:
            from services.dre_helpers import apply_extracted_data

            apply_extracted_data(extracted_fields, db)
        except Exception as e:
            logger.error("Data application failed: %s", e)
            result["errors"].append(f"Data application failed: {e}")

    # --- Step 8: Create activity ---
    activity_id = _create_email_activity(
        db=db,
        user_id=user_id,
        org_id=org_id,
        loan_id=matched_loan_id,
        lead_id=matched_lead_id,
        parsed=parsed,
        classification=classification,
    )
    result["activity_id"] = activity_id

    # --- Step 9: Create DRE records for Reconciliation page ---
    try:
        _create_reconciliation_records(
            db=db,
            user_id=user_id,
            parsed=parsed,
            classification=classification,
            extracted_fields=extracted_fields,
            matched_loan_id=matched_loan_id,
            matched_lead_id=matched_lead_id,
            match_result=match_result,
        )
    except Exception as e:
        logger.error("Reconciliation record creation failed: %s", e)
        result["errors"].append(f"Reconciliation record failed: {e}")

    db.commit()
    return result


# ------------------------------------------------------- queue insert
def _insert_queue_record(
    parsed: Dict[str, Any],
    db: Session,
    *,
    user_id: Optional[int] = None,
    matched_loan_id: Optional[int] = None,
    matched_lead_id: Optional[int] = None,
    matched_contact_id: Optional[int] = None,
    match_result: Optional[Dict] = None,
    classification: Optional[Dict] = None,
    status: str = "pending",
) -> int:
    """Insert email into reconciliation queue."""
    row = db.execute(
        text("""
            INSERT INTO email_reconciliation_queue (
                email_provider, provider_message_id, thread_id,
                from_email, from_name, to_emails, cc_emails, subject,
                body_preview, body_full, body_html,
                has_attachments, attachment_count, attachment_names,
                received_date, direction,
                matched_loan_id, matched_lead_id, matched_contact_id,
                match_method, match_confidence,
                status, user_id
            ) VALUES (
                :provider, :msg_id, :thread_id,
                :from_email, :from_name, :to_emails, :cc_emails, :subject,
                :body_preview, :body_full, :body_html,
                :has_attachments, :attachment_count, :attachment_names,
                :received_date, 'inbound',
                :matched_loan_id, :matched_lead_id, :matched_contact_id,
                :match_method, :match_confidence,
                :status, :user_id
            ) RETURNING id
        """),
        {
            "provider": parsed.get("email_provider"),
            "msg_id": parsed.get("provider_message_id"),
            "thread_id": parsed.get("thread_id"),
            "from_email": parsed.get("from_email"),
            "from_name": parsed.get("from_name"),
            "to_emails": json.dumps(parsed.get("to_emails", [])),
            "cc_emails": json.dumps(parsed.get("cc_emails", [])),
            "subject": parsed.get("subject"),
            "body_preview": (parsed.get("body_preview") or "")[:500],
            "body_full": parsed.get("body_full"),
            "body_html": parsed.get("body_html"),
            "has_attachments": parsed.get("has_attachments", False),
            "attachment_count": parsed.get("attachment_count", 0),
            "attachment_names": json.dumps(parsed.get("attachment_names", [])),
            "received_date": parsed.get("received_date"),
            "matched_loan_id": matched_loan_id,
            "matched_lead_id": matched_lead_id,
            "matched_contact_id": matched_contact_id,
            "match_method": match_result.get("match_method") if match_result else None,
            "match_confidence": match_result.get("match_confidence") if match_result else None,
            "status": status,
            "user_id": user_id,
        },
    )
    email_id = row.fetchone()[0]
    db.flush()
    return email_id


# ------------------------------------------------------- attachment upload
def _get_primary_borrower_id(db: Session, loan_id: int) -> Optional[int]:
    """Look up primary borrower_id for a loan."""
    row = db.execute(
        text("SELECT borrower_id FROM loans WHERE id = :lid"),
        {"lid": loan_id},
    ).first()
    return row[0] if row else None


async def _upload_attachments_as_docs(
    attachments: List[Tuple[str, bytes, str]],
    loan_id: int,
    borrower_id: Optional[int],
    org_id: Optional[int],
    email_id: int,
    db: Session,
) -> List[Dict[str, Any]]:
    """Upload email attachments to S3 and create SmartDocument records.

    Returns list of {document_id, filename, status}.
    """
    from models.smart_docs_models import SmartDocument, DocumentStatus, DocType
    from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

    s3 = get_smart_docs_s3_service()
    created = []

    for filename, content, content_type in attachments[:MAX_ATTACHMENTS]:
        if len(content) > MAX_ATTACHMENT_SIZE:
            created.append({
                "filename": filename,
                "status": "skipped",
                "reason": "exceeds_size_limit",
            })
            continue

        if not any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
            created.append({
                "filename": filename,
                "status": "skipped",
                "reason": f"unsupported_type:{content_type}",
            })
            continue

        safe_name = _safe_filename(filename)
        storage_key = s3.generate_storage_key(
            loan_id=loan_id,
            borrower_id=borrower_id or 0,
            file_name=safe_name,
            organization_id=org_id,
        )

        doc = SmartDocument(
            organization_id=org_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            file_name=safe_name,
            mime_type=content_type,
            file_size=len(content),
            storage_key=storage_key,
            status=DocumentStatus.UPLOADED.value,
            upload_source="EMAIL",
        )
        db.add(doc)
        db.flush()

        upload_result = s3.upload_file(
            file_content=content,
            storage_key=storage_key,
            content_type=content_type,
            metadata={
                "loan_id": str(loan_id),
                "borrower_id": str(borrower_id or 0),
                "document_id": str(doc.id),
                "original_filename": safe_name,
                "upload_source": "EMAIL",
                "email_queue_id": str(email_id),
            },
        )

        if upload_result.get("success"):
            created.append({
                "document_id": doc.id,
                "filename": safe_name,
                "status": "uploaded",
            })
            # Trigger review pipeline
            try:
                from services.smart_docs.document_review_pipeline import (
                    DocumentReviewPipeline,
                )

                pipeline = DocumentReviewPipeline(db)
                pipeline.process_document(
                    document_id=doc.id,
                    file_content=content,
                    mime_type=content_type,
                    filename=safe_name,
                )
            except Exception as e:
                logger.error("Review pipeline failed for doc %d: %s", doc.id, e)
        else:
            doc.status = DocumentStatus.UPLOAD_FAILED.value
            created.append({
                "document_id": doc.id,
                "filename": safe_name,
                "status": "upload_failed",
            })

    return created


# ------------------------------------------------------- activity log
def _create_email_activity(
    db: Session,
    user_id: int,
    org_id: int,
    loan_id: Optional[int],
    lead_id: Optional[int],
    parsed: Dict[str, Any],
    classification: Optional[Dict] = None,
) -> Optional[int]:
    """Create a timeline activity for the inbound email."""
    from_label = parsed.get("from_name") or parsed.get("from_email") or "Unknown"
    subject = parsed.get("subject", "(no subject)")
    category = classification.get("category", "email") if classification else "email"

    content = f"Inbound email from {from_label}: \"{subject}\""
    if category != "email" and category != "unrelated":
        content += f" [{category}]"

    try:
        row = db.execute(
            text("""
                INSERT INTO activities (
                    organization_id, user_id, type, content,
                    loan_id, lead_id, created_at
                ) VALUES (
                    :org_id, :user_id, 'EMAIL', :content,
                    :loan_id, :lead_id, NOW() AT TIME ZONE 'America/New_York'
                ) RETURNING id
            """),
            {
                "org_id": org_id,
                "user_id": user_id,
                "content": content,
                "loan_id": loan_id,
                "lead_id": lead_id,
            },
        )
        return row.fetchone()[0]
    except Exception as e:
        logger.error("Activity creation failed: %s", e)
        return None


# ---------------------------------------- DRE reconciliation records
def _create_reconciliation_records(
    db: Session,
    user_id: int,
    parsed: Dict[str, Any],
    classification: Optional[Dict],
    extracted_fields: Optional[Dict],
    matched_loan_id: Optional[int],
    matched_lead_id: Optional[int],
    match_result: Optional[Dict],
) -> None:
    """Create IncomingDataEvent + ExtractedData so forwarded emails appear
    on the Reconciliation Center page alongside Microsoft-synced emails."""
    from database.models.data_reconciliation import IncomingDataEvent, ExtractedData

    attachment_names = parsed.get("attachment_names", [])
    event = IncomingDataEvent(
        source="email_forward",
        external_message_id=parsed.get("provider_message_id"),
        raw_text=parsed.get("body_full") or parsed.get("body_preview"),
        raw_html=parsed.get("body_html"),
        subject=parsed.get("subject"),
        sender=parsed.get("from_email"),
        recipients=parsed.get("to_emails"),
        attachments=attachment_names if attachment_names else None,
        processed=True,
        user_id=user_id,
    )
    db.add(event)
    db.flush()

    category = "unrelated"
    subcategory = ""
    ai_confidence = 0.0
    if classification:
        category = classification.get("category", "unrelated")
        subcategory = classification.get("subcategory", "")
        ai_confidence = classification.get("confidence", 0.0)

    fields = {}
    if extracted_fields:
        fields = extracted_fields

    match_entity_type = None
    match_entity_id = None
    match_confidence = None
    if matched_loan_id:
        match_entity_type = "loan"
        match_entity_id = matched_loan_id
        match_confidence = match_result.get("confidence", 0.9) if match_result else 0.9
    elif matched_lead_id:
        match_entity_type = "lead"
        match_entity_id = matched_lead_id
        match_confidence = match_result.get("confidence", 0.9) if match_result else 0.9

    status = "pending_review"
    if category == "unrelated":
        status = "needs_review"

    extracted = ExtractedData(
        event_id=event.id,
        category=category,
        subcategory=subcategory,
        fields=fields,
        match_entity_type=match_entity_type,
        match_entity_id=match_entity_id,
        match_confidence=match_confidence,
        ai_confidence=ai_confidence,
        status=status,
    )
    db.add(extracted)


# ---------------------------------------- forwarding address generation
def get_forwarding_address(user_id: int) -> str:
    """Return the personalized forwarding address for an LO."""
    return f"loans+{user_id}@{INBOUND_DOMAIN}"


def get_outlook_rule_instructions(user_id: int, lo_name: str) -> Dict[str, Any]:
    """Generate Outlook forwarding setup instructions for an LO."""
    addr = get_forwarding_address(user_id)
    return {
        "forwarding_address": addr,
        "instructions": [
            f"1. Open Outlook and go to Settings → Mail → Rules",
            f"2. Click \"Add new rule\"",
            f"3. Name it: \"Forward to Perennia\"",
            f"4. Set condition: \"Apply to all messages\" (or filter by sender/subject)",
            f"5. Set action: \"Forward to\" → {addr}",
            f"6. Click Save",
        ],
        "notes": [
            "Forwarded emails are processed automatically by Aria",
            "Attachments (PDF, images, Word docs) are uploaded to Smart Docs",
            "Emails are matched to loans by borrower name, loan number, or sender",
            "Unmatched emails appear in your email intelligence queue for manual review",
        ],
        "test_subject": f"Test forward from {lo_name}",
    }
