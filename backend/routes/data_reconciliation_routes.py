"""
Data Reconciliation Engine API Routes

Provides endpoints for:
- Email data ingestion and AI extraction
- Pending/completed reconciliation items
- Approval, rejection, and correction workflows
- Blocked sender management
- Entity matching and rematch operations
- Email response queue and AI learning
- Duplicate lead detection and merging
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import os

from database import get_db
from utils.pii_mask import mask_email

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models (recreated to avoid circular imports)
# =============================================================================

class IncomingDataEventCreate(BaseModel):
    source: str
    raw_text: Optional[str] = None
    raw_html: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    recipients: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class BulkEmailItem(BaseModel):
    subject: Optional[str] = None
    sender: Optional[str] = None
    recipients: Optional[List[str]] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    received_at: Optional[str] = None
    has_attachments: Optional[bool] = False
    external_message_id: Optional[str] = None
    web_link: Optional[str] = None


class BulkEmailSync(BaseModel):
    emails: List[BulkEmailItem]
    user_email: Optional[str] = None


class ReconciliationApproval(BaseModel):
    extracted_data_id: int
    approved_fields: Optional[Dict[str, Any]] = None
    corrections: Optional[Dict[str, Any]] = None
    deleted_fields: Optional[List[str]] = None
    renamed_fields: Optional[Dict[str, str]] = None
    delegate_to_ai: Optional[bool] = False
    email_intent: Optional[str] = None
    recommended_action: Optional[Dict[str, Any]] = None
    target_entity_type: Optional[str] = None
    target_entity_id: Optional[int] = None
    create_new_loan: Optional[bool] = False
    loan_stage: Optional[str] = None
    update_status_to: Optional[str] = None
    delete_from_inbox: Optional[bool] = False
    email_message_id: Optional[str] = None


class ReconciliationRejection(BaseModel):
    extracted_data_id: int
    reason: Optional[str] = None
    delete_from_inbox: Optional[bool] = False
    email_message_id: Optional[str] = None


class BlockSenderRequest(BaseModel):
    sender_email: str
    reason: Optional[str] = "Blocked by user"


class CreateLeadFromExtracted(BaseModel):
    extracted_data_id: int
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    referral_partner_id: Optional[int] = None


class EmailResponseApproval(BaseModel):
    """Schema for approving/rejecting email response recommendations"""
    queue_id: int
    action: str  # 'approve', 'reject', 'modify'
    modified_response: Optional[str] = None
    modified_action: Optional[str] = None
    enable_auto_execute: bool = False

    class Config:
        extra = "allow"


# =============================================================================
# Runtime imports to avoid circular dependencies
# =============================================================================

def get_current_user_dep():
    """Get current user - imports from main at runtime"""
    import main
    return main.get_current_user


def get_models():
    """Get models from main at runtime"""
    import main
    return {
        "IncomingDataEvent": main.IncomingDataEvent,
        "ExtractedData": main.ExtractedData,
        "BlockedSender": main.BlockedSender,
        "AITrainingEvent": main.AITrainingEvent,
        "AIDelegatedTask": main.AIDelegatedTask,
        "User": main.User,
        "Lead": main.Lead,
        "Loan": main.Loan,
        "Task": main.Task,
        "LeadStage": main.LeadStage,
        "LoanStage": main.LoanStage,
        "UserSettings": main.UserSettings,
        "MicrosoftOAuthToken": main.MicrosoftOAuthToken,
        "DuplicatePair": main.DuplicatePair,
        "MergeTrainingEvent": main.MergeTrainingEvent,
        "MergeAIModel": main.MergeAIModel,
    }


def get_helper_functions():
    """Get helper functions from main at runtime"""
    import main
    return {
        "classify_email_content": main.classify_email_content,
        "extract_loan_fields": main.extract_loan_fields,
        "extract_borrower_from_subject": main.extract_borrower_from_subject,
        "match_entity": main.match_entity,
        "get_entity_name": main.get_entity_name,
        "classify_email_intent": main.classify_email_intent,
        "generate_recommended_action": main.generate_recommended_action,
        "apply_extracted_data": main.apply_extracted_data,
        "delete_microsoft_email": main.delete_microsoft_email,
    }


def get_email_body_text(event) -> str:
    """Get email body as plain text, converting HTML if needed"""
    if not event:
        return None

    if event.raw_text:
        return event.raw_text

    if event.raw_html:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(event.raw_html, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            return soup.get_text(separator='\n', strip=True)
        except Exception as e:
            logger.error(f"Error parsing HTML with BeautifulSoup: {e}")
            import re
            text = re.sub(r'<[^>]+>', '', event.raw_html)
            return text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    return None


# =============================================================================
# DATA RECONCILIATION ENGINE - API ENDPOINTS
# =============================================================================

@router.post("/ingest")
async def ingest_email_data(
    event: IncomingDataEventCreate,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Ingest incoming email data for reconciliation"""
    try:
        models = get_models()
        IncomingDataEvent = models["IncomingDataEvent"]
        BlockedSender = models["BlockedSender"]

        # Check if sender is blocked
        if event.sender:
            sender_email = event.sender.lower().strip()
            blocked = db.query(BlockedSender).filter(
                BlockedSender.user_id == current_user.id,
                BlockedSender.sender_email == sender_email
            ).first()

            if blocked:
                logger.info(f"Skipping email from blocked sender: {sender_email}")
                return {
                    "status": "skipped",
                    "message": f"Sender {sender_email} is blocked",
                    "event_id": None
                }

        # Create incoming data event
        db_event = IncomingDataEvent(
            source=event.source,
            raw_text=event.raw_text,
            raw_html=event.raw_html,
            subject=event.subject,
            sender=event.sender,
            recipients=event.recipients,
            attachments=event.attachments,
            user_id=current_user.id,
            processed=False
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)

        logger.info(f"Ingested email data event {db_event.id} for user {current_user.id}")

        return {
            "status": "success",
            "event_id": db_event.id,
            "message": "Email data ingested successfully"
        }
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-sync")
async def bulk_sync_emails(
    payload: BulkEmailSync,
    request: Request,
    db: Session = Depends(get_db)
):
    """Bulk-ingest emails from an external source (MCP, manual, etc.) into the DRE pipeline.
    Deduplicates by external_message_id. Returns count of newly ingested emails.

    Auth: JWT Bearer (normal user) OR X-API-Key header with CRM_API_KEY.
    When using API key, pass user_email in the payload to identify the target user.
    """
    import hmac

    models = get_models()
    User = models["User"]

    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        expected = os.environ.get("CRM_API_KEY", "").strip()
        if not expected or not hmac.compare_digest(api_key, expected):
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not payload.user_email:
            raise HTTPException(status_code=400, detail="user_email required with API key auth")
        current_user = db.query(User).filter(User.email == payload.user_email).first()
        if not current_user:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        import main
        current_user = await main.get_current_user_flexible(request, db)

    try:
        IncomingDataEvent = models["IncomingDataEvent"]
        BlockedSender = models["BlockedSender"]

        blocked_senders = {
            row.sender_email.lower()
            for row in db.query(BlockedSender).filter(
                BlockedSender.user_id == current_user.id
            ).all()
        }

        existing_ids = set()
        ext_ids = [e.external_message_id for e in payload.emails if e.external_message_id]
        if ext_ids:
            rows = db.execute(
                text("""
                    SELECT external_message_id FROM incoming_data_events
                    WHERE user_id = :uid AND external_message_id = ANY(:ids)
                """),
                {"uid": current_user.id, "ids": ext_ids},
            ).fetchall()
            existing_ids = {r[0] for r in rows}

        ingested = 0
        for email in payload.emails:
            if email.external_message_id and email.external_message_id in existing_ids:
                continue
            if email.sender and email.sender.lower().strip() in blocked_senders:
                continue

            db_event = IncomingDataEvent(
                source="outlook_mcp",
                raw_text=email.body_text,
                raw_html=email.body_html,
                subject=email.subject,
                sender=email.sender,
                recipients=email.recipients,
                external_message_id=email.external_message_id,
                user_id=current_user.id,
                processed=False,
            )
            db.add(db_event)
            ingested += 1

        db.commit()
        return {
            "status": "success",
            "processed_count": ingested,
            "skipped_count": len(payload.emails) - ingested,
            "message": f"Synced {ingested} new emails ({len(payload.emails) - ingested} skipped as duplicates or blocked)"
        }
    except Exception as e:
        logger.error(f"Bulk sync error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/extract/{event_id}")
async def extract_email_data(
    event_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Trigger AI extraction on an ingested email event"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        Loan = models["Loan"]
        Task = models["Task"]

        # Get the event
        event = db.query(IncomingDataEvent).filter(
            IncomingDataEvent.id == event_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        # Classify the email
        content = event.raw_text or event.raw_html or ""
        subject = event.subject or ""

        # Check AI provider setting
        ai_provider = os.getenv("AI_PROVIDER", "openai").lower()

        if ai_provider == "claude":
            from ai_providers.claude_parser import get_claude_parser

            logger.info(f"Using Claude parser for event {event_id}")

            claude_email_data = {
                "id": str(event.id),
                "subject": subject,
                "from_email": event.sender,
                "body_text": event.raw_text,
                "body_html": event.raw_html,
            }

            parser = get_claude_parser()
            profile_type = parser.classify_email(claude_email_data)

            logger.info(f"Event {event_id} classified as: {profile_type}")

            parsed_result = await parser.parse_email(
                claude_email_data,
                profile_type,
                current_profile=None
            )

            extracted_fields = parsed_result.get('extracted_fields', {})
            confidence_scores = parsed_result.get('confidence_scores', {})

            fields = {}
            for field_name, field_value in extracted_fields.items():
                confidence = confidence_scores.get(field_name, 95) / 100.0
                fields[field_name] = {
                    "value": field_value,
                    "confidence": confidence
                }

            avg_confidence = parsed_result.get('overall_confidence', 0) / 100.0
            classification = {
                "category": profile_type,
                "subcategory": parsed_result.get('email_summary', ''),
                "confidence": avg_confidence
            }

            logger.info(f"Claude extracted {len(fields)} fields with {avg_confidence*100:.1f}% confidence")
        else:
            logger.info(f"Using legacy OpenAI parser for event {event_id}")
            classification = helpers["classify_email_content"](content, subject)
            fields = helpers["extract_loan_fields"](content, classification["category"]) if classification["category"] != "unrelated" and classification["confidence"] >= 0.5 else {}
            confidences = [field.get("confidence", 0.0) for field in fields.values()] if fields else []
            avg_confidence = sum(confidences) / len(confidences) if confidences else classification["confidence"]

        if classification["category"] == "unrelated" or classification.get("confidence", 0) < 0.5:
            event.processed = True
            db.commit()
            return {
                "status": "skipped",
                "reason": "Email classified as unrelated or low confidence",
                "classification": classification
            }

        # Fallback: Extract borrower name from subject if not found by AI
        if fields and "borrower_name" not in fields:
            fallback_borrower = helpers["extract_borrower_from_subject"](subject)
            if fallback_borrower:
                logger.info(f"Extracted borrower name from subject: {fallback_borrower}")
                fields["borrower_name"] = {"value": fallback_borrower, "confidence": 0.85}

        if not fields:
            event.processed = True
            db.commit()
            return {
                "status": "no_data",
                "reason": "No extractable fields found",
                "classification": classification
            }

        # Match entity
        entity_match = helpers["match_entity"](fields, db, current_user.id)

        # Determine status based on confidence
        status = "pending_review"
        if avg_confidence < 0.60 or entity_match["confidence"] < 0.50:
            status = "needs_review"

        # Create extracted data record
        extracted = ExtractedData(
            event_id=event.id,
            category=classification["category"],
            subcategory=classification.get("subcategory"),
            fields=fields,
            match_entity_type=entity_match["entity_type"],
            match_entity_id=entity_match["entity_id"],
            match_confidence=entity_match["confidence"],
            ai_confidence=avg_confidence,
            status=status
        )
        db.add(extracted)

        event.processed = True
        db.commit()
        db.refresh(extracted)

        # Create task for loan number updates if needed
        extracted_loan_number = fields.get("loan_number", {}).get("value")
        if extracted_loan_number and entity_match["entity_type"] == "loan" and entity_match["entity_id"]:
            try:
                matched_loan = db.query(Loan).filter(Loan.id == entity_match["entity_id"]).first()
                if matched_loan and (not matched_loan.loan_number or matched_loan.loan_number != extracted_loan_number):
                    borrower_name = matched_loan.borrower_name or "Unknown Borrower"
                    task_title = f"Update loan number for {borrower_name}"
                    task_description = f"""AI extracted loan number '{extracted_loan_number}' from email but the loan record has a different or missing loan number.

Current loan number: {matched_loan.loan_number or 'Not set'}
Extracted loan number: {extracted_loan_number}
Borrower: {borrower_name}
Email subject: {subject}

Please review and update the loan record if needed."""

                    new_task = Task(
                        title=task_title,
                        description=task_description,
                        status="pending",
                        priority="high",
                        source="AI Extraction",
                        entity_type="loan",
                        entity_id=matched_loan.id,
                        owner_id=current_user.id,
                        created_by_id=current_user.id
                    )
                    db.add(new_task)
                    db.commit()
                    logger.info(f"Created task to update loan number for loan {matched_loan.id}: {extracted_loan_number}")
            except Exception as task_error:
                logger.warning(f"Failed to create loan number update task: {task_error}")

        elif extracted_loan_number and entity_match["entity_type"] != "loan" and entity_match["entity_id"]:
            try:
                borrower_name = fields.get("borrower_name", {}).get("value") or fields.get("first_name", {}).get("value", "") + " " + fields.get("last_name", {}).get("value", "")
                borrower_name = borrower_name.strip() if borrower_name else "Unknown"

                task_title = f"Add loan number {extracted_loan_number} to borrower record"
                task_description = f"""AI extracted loan number '{extracted_loan_number}' from email but matched to a {entity_match['entity_type']} instead of a loan.

This may indicate the borrower has converted from lead to active loan.

Extracted loan number: {extracted_loan_number}
Matched entity: {entity_match['entity_type']} (ID: {entity_match['entity_id']})
Borrower name from email: {borrower_name}
Email subject: {subject}

Please:
1. Convert the lead to an active loan if applicable
2. Update the loan record with the extracted loan number"""

                new_task = Task(
                    title=task_title,
                    description=task_description,
                    status="pending",
                    priority="high",
                    source="AI Extraction",
                    entity_type=entity_match["entity_type"],
                    entity_id=entity_match["entity_id"],
                    owner_id=current_user.id,
                    created_by_id=current_user.id
                )
                db.add(new_task)
                db.commit()
                logger.info(f"Created task to add loan number {extracted_loan_number} to {entity_match['entity_type']} {entity_match['entity_id']}")
            except Exception as task_error:
                logger.warning(f"Failed to create loan number task: {task_error}")

        logger.info(f"Extracted data from event {event_id}, status: {extracted.status}")

        return {
            "status": "success",
            "extracted_data_id": extracted.id,
            "category": extracted.category,
            "ai_confidence": extracted.ai_confidence,
            "match_confidence": extracted.match_confidence,
            "extraction_status": extracted.status,
            "fields": extracted.fields,
            "entity_match": {
                "type": extracted.match_entity_type,
                "id": extracted.match_entity_id
            }
        }
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/pending")
async def get_pending_reconciliation(
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get all pending reconciliation items for review"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]

        pending = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            or_(
                IncomingDataEvent.user_id == current_user.id,
                IncomingDataEvent.user_id == None
            ),
            ExtractedData.status.in_(["pending_review", "needs_review"])
        ).order_by(ExtractedData.created_at.desc()).all()

        results = []
        for item in pending:
            event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.id == item.event_id
            ).first()

            entity_name = None
            if item.match_entity_type and item.match_entity_id:
                entity_name = helpers["get_entity_name"](item.match_entity_type, item.match_entity_id, db)

            email_intent = helpers["classify_email_intent"](
                event.subject if event else "",
                event.raw_text if event else "",
                item.fields
            )

            recommended_action = None
            if email_intent.get("confidence", 0) > 0.60:
                recommended_action = helpers["generate_recommended_action"](
                    email_intent,
                    item.match_entity_type,
                    item.fields
                )

            fresh_matches = helpers["match_entity"](item.fields or {}, db, current_user.id)

            display_entity_type = item.match_entity_type
            display_entity_id = item.match_entity_id
            display_confidence = item.match_confidence or 0
            display_entity_name = entity_name

            fresh_confidence = fresh_matches.get("confidence", 0) if fresh_matches else 0
            if fresh_confidence > display_confidence and fresh_matches.get("entity_type"):
                display_entity_type = fresh_matches["entity_type"]
                display_entity_id = fresh_matches["entity_id"]
                display_confidence = fresh_confidence
                display_entity_name = helpers["get_entity_name"](display_entity_type, display_entity_id, db)
                logger.info(f"Using fresh match for item {item.id}: {display_entity_type} {display_entity_id} ({display_confidence*100:.0f}%)")

            results.append({
                "id": item.id,
                "event_id": item.event_id,
                "category": item.category,
                "subcategory": item.subcategory,
                "fields": item.fields,
                "match_entity_type": display_entity_type,
                "match_entity_id": display_entity_id,
                "match_entity_name": display_entity_name,
                "match_confidence": display_confidence,
                "ai_confidence": item.ai_confidence,
                "status": item.status,
                "created_at": item.created_at,
                "email_from": event.sender if event else None,
                "email_subject": event.subject if event else None,
                "email_received_at": event.received_at if event else None,
                "email_body": get_email_body_text(event) if event else None,
                "email": {
                    "subject": event.subject if event else None,
                    "sender": event.sender if event else None,
                    "received_at": event.received_at if event else None,
                    "body": get_email_body_text(event) if event else None
                },
                "email_intent": email_intent.get("intent"),
                "email_intent_description": email_intent.get("description"),
                "recommended_action": recommended_action,
                "matches": fresh_matches
            })

        logger.info(f"Retrieved {len(results)} pending reconciliation items for user {current_user.id}")

        return {
            "status": "success",
            "count": len(results),
            "items": results
        }
    except Exception as e:
        logger.error(f"Get pending error: {e}")
        return {
            "status": "success",
            "count": 0,
            "items": [],
            "note": "Reconciliation data temporarily unavailable"
        }


@router.get("/completed")
async def get_completed_reconciliation(
    limit: int = 50,
    offset: int = 0,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get all completed reconciliation items (approved or rejected)"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        User = models["User"]

        completed = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            IncomingDataEvent.user_id == current_user.id,
            ExtractedData.status.in_(["approved", "applied", "rejected"])
        ).order_by(
            ExtractedData.reviewed_at.desc()
        ).offset(offset).limit(limit).all()

        results = []
        for item in completed:
            event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.id == item.event_id
            ).first()

            reviewer_name = None
            if item.reviewed_by:
                reviewer = db.query(User).filter(User.id == item.reviewed_by).first()
                reviewer_name = reviewer.full_name if reviewer else "Unknown"

            entity_name = None
            if item.match_entity_type and item.match_entity_id:
                entity_name = helpers["get_entity_name"](item.match_entity_type, item.match_entity_id, db)

            email_intent = helpers["classify_email_intent"](
                event.subject if event else "",
                event.raw_text if event else "",
                item.fields
            )

            recommended_action = None
            if email_intent.get("confidence", 0) > 0.60:
                recommended_action = helpers["generate_recommended_action"](
                    email_intent,
                    item.match_entity_type,
                    item.fields
                )

            results.append({
                "id": item.id,
                "event_id": item.event_id,
                "category": item.category,
                "subcategory": item.subcategory,
                "fields": item.fields,
                "match_entity_type": item.match_entity_type,
                "match_entity_id": item.match_entity_id,
                "match_entity_name": entity_name,
                "match_confidence": item.match_confidence,
                "ai_confidence": item.ai_confidence,
                "status": item.status,
                "created_at": item.created_at,
                "reviewed_at": item.reviewed_at,
                "reviewed_by": reviewer_name,
                "email": {
                    "subject": event.subject if event else None,
                    "sender": event.sender if event else None,
                    "received_at": event.received_at if event else None
                },
                "email_intent": email_intent.get("intent"),
                "email_intent_description": email_intent.get("description"),
                "recommended_action": recommended_action
            })

        total_count = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            IncomingDataEvent.user_id == current_user.id,
            ExtractedData.status.in_(["approved", "applied", "rejected"])
        ).count()

        logger.info(f"Retrieved {len(results)} completed reconciliation items for user {current_user.id}")

        return {
            "status": "success",
            "count": len(results),
            "total": total_count,
            "items": results
        }
    except Exception as e:
        logger.error(f"Get completed error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/pre-approval-check/{item_id}")
async def pre_approval_check(
    item_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Check if reconciliation data suggests a status mismatch before approval."""
    try:
        models = get_models()
        ExtractedData = models["ExtractedData"]
        Lead = models["Lead"]
        Loan = models["Loan"]
        LoanStage = models["LoanStage"]

        extracted = db.query(ExtractedData).filter(ExtractedData.id == item_id).first()
        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        fields = extracted.fields or {}
        current_entity_type = extracted.match_entity_type
        current_entity_id = extracted.match_entity_id

        result = {
            "needs_status_update": False,
            "current_status": None,
            "current_status_label": None,
            "suggested_status": None,
            "suggested_status_label": None,
            "reason": None,
            "entity_type": current_entity_type,
            "entity_name": None,
            "fields_to_apply": []
        }

        def get_val(field_name):
            if field_name in fields and isinstance(fields[field_name], dict):
                return fields[field_name].get("value")
            return None

        for field_name, field_data in fields.items():
            if isinstance(field_data, dict) and field_data.get("value"):
                result["fields_to_apply"].append({
                    "field": field_name,
                    "value": field_data.get("value"),
                    "confidence": field_data.get("confidence", 0)
                })

        if current_entity_type == "lead" and current_entity_id:
            lead = db.query(Lead).filter(Lead.id == current_entity_id).first()
            if lead:
                result["entity_name"] = lead.name
                current_stage = lead.stage.name if lead.stage else "NEW"
                result["current_status"] = current_stage

                stage_labels = {
                    "NEW": "New Lead",
                    "ATTEMPTED_CONTACT": "Attempted Contact",
                    "PROSPECT": "Prospect",
                    "APPLICATION": "Application",
                    "APPLICATION_STARTED": "Application Started",
                    "PRE_QUALIFIED": "Pre-Qualified",
                    "PRE_APPROVED": "Pre-Approved",
                    "UNDER_CONTRACT": "Under Contract",
                    "LONG_TERM_NURTURE": "Long-Term Nurture",
                    "DISCLOSED": "Disclosed",
                    "PROCESSING": "Processing",
                    "SUBMITTED": "Submitted",
                    "UW_RECEIVED": "Underwriting Received",
                    "APPROVED": "Approved",
                    "SUSPENDED": "Suspended",
                    "CTC": "Clear to Close",
                    "DOCS": "Docs Out",
                    "FUNDED": "Funded",
                }
                result["current_status_label"] = stage_labels.get(current_stage, current_stage)

                has_appraisal_ordered = get_val("appraisal_ordered_date")
                has_appraisal_received = get_val("appraisal_received_date") or get_val("appraisal_completed_date")
                has_appraisal_value = get_val("appraisal_value")
                has_disclosure_sent = get_val("initial_disclosures_sent_date")
                has_disclosure_signed = get_val("initial_disclosures_signed_date")
                has_property_address = get_val("property_address")

                early_stages = ["NEW", "ATTEMPTED_CONTACT", "PROSPECT"]

                if current_stage in early_stages:
                    if has_appraisal_received or has_appraisal_value:
                        result["needs_status_update"] = True
                        result["suggested_status"] = "PROCESSING"
                        result["suggested_status_label"] = "Processing"
                        result["reason"] = "Appraisal has been completed. This borrower should be in Processing or later stage."
                    elif has_appraisal_ordered:
                        result["needs_status_update"] = True
                        result["suggested_status"] = "PROCESSING"
                        result["suggested_status_label"] = "Processing"
                        result["reason"] = "Appraisal has been ordered. This borrower should be in Processing stage."
                    elif has_disclosure_signed:
                        result["needs_status_update"] = True
                        result["suggested_status"] = "PROCESSING"
                        result["suggested_status_label"] = "Processing"
                        result["reason"] = "Disclosures have been signed. This borrower should be in Processing stage."
                    elif has_disclosure_sent:
                        result["needs_status_update"] = True
                        result["suggested_status"] = "DISCLOSED"
                        result["suggested_status_label"] = "Disclosed"
                        result["reason"] = "Initial disclosures have been sent. This borrower should be in Disclosed stage."
                    elif has_property_address:
                        result["needs_status_update"] = True
                        result["suggested_status"] = "UNDER_CONTRACT"
                        result["suggested_status_label"] = "Under Contract"
                        result["reason"] = "Property address found. This borrower may be under contract."

        elif current_entity_type == "loan" and current_entity_id:
            loan = db.query(Loan).filter(Loan.id == current_entity_id).first()
            if loan:
                result["entity_name"] = loan.borrower_name
                current_stage = str(loan.stage) if loan.stage else "PROCESSING"
                result["current_status"] = current_stage
                result["current_status_label"] = current_stage

                has_ctc = get_val("clear_to_close_date") or get_val("ctc_date")
                has_closing_docs = get_val("closing_docs_sent_date") or get_val("final_closing_package_sent_date")
                has_funded = get_val("funded_date")
                has_uw_approval = get_val("underwriting_approval_date")

                if has_funded and loan.stage != LoanStage.FUNDED:
                    result["needs_status_update"] = True
                    result["suggested_status"] = "FUNDED"
                    result["suggested_status_label"] = "Funded"
                    result["reason"] = "Loan has been funded. Status should be updated to Funded."
                elif has_closing_docs and loan.stage not in [LoanStage.DOCS, LoanStage.FUNDED]:
                    result["needs_status_update"] = True
                    result["suggested_status"] = "DOCS"
                    result["suggested_status_label"] = "Docs Out"
                    result["reason"] = "Closing docs have been sent. Status should be Docs Out."
                elif has_ctc and loan.stage not in [LoanStage.CTC, LoanStage.DOCS, LoanStage.FUNDED]:
                    result["needs_status_update"] = True
                    result["suggested_status"] = "CTC"
                    result["suggested_status_label"] = "Clear to Close"
                    result["reason"] = "Loan is clear to close. Status should be CTC."
                elif has_uw_approval and loan.stage not in [LoanStage.APPROVED, LoanStage.CTC, LoanStage.DOCS, LoanStage.FUNDED]:
                    result["needs_status_update"] = True
                    result["suggested_status"] = "APPROVED"
                    result["suggested_status_label"] = "Approved"
                    result["reason"] = "Underwriting approval received. Status should be Approved."

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pre-approval check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/approve")
async def approve_reconciliation(
    approval: ReconciliationApproval,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Approve extracted data and apply to CRM"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        AITrainingEvent = models["AITrainingEvent"]
        AIDelegatedTask = models["AIDelegatedTask"]
        Lead = models["Lead"]
        Loan = models["Loan"]
        LeadStage = models["LeadStage"]
        LoanStage = models["LoanStage"]
        UserSettings = models["UserSettings"]
        MicrosoftOAuthToken = models["MicrosoftOAuthToken"]

        # Get extracted data
        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == approval.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == approval.extracted_data_id
            ).first()

            if extracted:
                event = db.query(IncomingDataEvent).filter(
                    IncomingDataEvent.id == extracted.event_id
                ).first()
                if event and not event.user_id:
                    event.user_id = current_user.id

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        # Apply corrections if provided
        if approval.corrections:
            for field_name, corrected_value in approval.corrections.items():
                if field_name in extracted.fields:
                    original = extracted.fields[field_name]["value"]

                    training = AITrainingEvent(
                        extracted_data_id=extracted.id,
                        field_name=field_name,
                        original_value=str(original),
                        corrected_value=str(corrected_value),
                        label="corrected",
                        user_id=current_user.id
                    )
                    db.add(training)

                    extracted.fields[field_name]["value"] = corrected_value
                    extracted.fields[field_name]["confidence"] = 1.0
                else:
                    extracted.fields[field_name] = {
                        "value": corrected_value,
                        "confidence": 1.0
                    }

                    training = AITrainingEvent(
                        extracted_data_id=extracted.id,
                        field_name=field_name,
                        original_value="[NEW_FIELD]",
                        corrected_value=str(corrected_value),
                        label="added",
                        user_id=current_user.id
                    )
                    db.add(training)
                    logger.info(f"Added new field {field_name}={corrected_value} to extracted data {extracted.id}")

        # Apply field deletions
        if approval.deleted_fields:
            for field_name in approval.deleted_fields:
                if field_name in extracted.fields:
                    training = AITrainingEvent(
                        extracted_data_id=extracted.id,
                        field_name=field_name,
                        original_value=str(extracted.fields[field_name].get("value", "")),
                        corrected_value="[DELETED]",
                        label="deleted",
                        user_id=current_user.id
                    )
                    db.add(training)
                    del extracted.fields[field_name]
                    logger.info(f"Deleted field {field_name} from extracted data {extracted.id}")

        # Apply field renames
        if approval.renamed_fields:
            for old_key, new_key in approval.renamed_fields.items():
                if old_key in extracted.fields:
                    training = AITrainingEvent(
                        extracted_data_id=extracted.id,
                        field_name=old_key,
                        original_value=old_key,
                        corrected_value=new_key,
                        label="renamed",
                        user_id=current_user.id
                    )
                    db.add(training)
                    extracted.fields[new_key] = extracted.fields.pop(old_key)
                    logger.info(f"Renamed field {old_key} -> {new_key} in extracted data {extracted.id}")

        # Apply partial approval
        if approval.approved_fields:
            original_fields = extracted.fields.copy()
            extracted.fields = {k: v for k, v in original_fields.items() if k in approval.approved_fields}

        # Handle entity type override
        if approval.target_entity_type:
            extracted.match_entity_type = approval.target_entity_type
            if approval.target_entity_id:
                extracted.match_entity_id = approval.target_entity_id

        # Mark fields as modified
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(extracted, "fields")
        db.flush()

        # Handle "Create New Loan" option
        if approval.create_new_loan:
            fields = extracted.fields or {}

            def get_val(field_name, default=None):
                if field_name in fields and isinstance(fields[field_name], dict):
                    return fields[field_name].get("value", default)
                return default

            loan_number = get_val("loan_number")

            borrower_name = get_val("borrower_name")
            if not borrower_name:
                first_name = get_val("first_name", "")
                last_name = get_val("last_name", "")
                borrower_name = f"{first_name} {last_name}".strip() or "Unknown"

            coborrower_name = get_val("coborrower_name")
            if not coborrower_name:
                coborrower_first = get_val("coborrower_first_name", "") or get_val("coborrower first name", "")
                coborrower_last = get_val("coborrower_last_name", "") or get_val("coborrower last name", "")
                if coborrower_first or coborrower_last:
                    coborrower_name = f"{coborrower_first} {coborrower_last}".strip()

            coborrower_email = get_val("coborrower_email") or get_val("co_borrower_email")
            borrower_email = get_val("borrower_email") or get_val("email")
            borrower_phone = get_val("borrower_phone") or get_val("phone")

            if not loan_number:
                import random
                loan_number = f"NEW{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
                logger.info(f"Generated loan number {loan_number} for borrower {borrower_name}")

            result = db.execute(
                text("SELECT id FROM loans WHERE loan_number = :loan_number"),
                {"loan_number": loan_number}
            ).first()

            if result:
                existing_loan_id = result[0]
                extracted.match_entity_type = "loan"
                extracted.match_entity_id = existing_loan_id
                logger.info(f"Found existing loan {loan_number}, using it instead of creating new")
            else:
                stage_str = approval.loan_stage or "PROCESSING"
                loan_stage_map = {
                    "DISCLOSED": LoanStage.DISCLOSED,
                    "PROCESSING": LoanStage.PROCESSING,
                    "SUBMITTED": LoanStage.SUBMITTED,
                    "UW_RECEIVED": LoanStage.UW_RECEIVED,
                    "APPROVED": LoanStage.APPROVED,
                    "SUSPENDED": LoanStage.SUSPENDED,
                    "CTC": LoanStage.CTC,
                    "DOCS": LoanStage.DOCS,
                    "FUNDED": LoanStage.FUNDED,
                }

                lead_stage_map = {
                    "NEW": LeadStage.NEW,
                    "ATTEMPTED_CONTACT": LeadStage.ATTEMPTED_CONTACT,
                    "PROSPECT": LeadStage.PROSPECT,
                    "APPLICATION": LeadStage.APPLICATION,
                    "APPLICATION_STARTED": LeadStage.APPLICATION_STARTED,
                    "PRE_QUALIFIED": LeadStage.PRE_QUALIFIED,
                    "PRE_APPROVED": LeadStage.PRE_APPROVED,
                    "UNDER_CONTRACT": LeadStage.UNDER_CONTRACT,
                    "LONG_TERM_NURTURE": LeadStage.LONG_TERM_NURTURE,
                    "CLOSED": LeadStage.CLOSED,
                    "AMR": LeadStage.AMR,
                    "REFERRAL_SOURCE": LeadStage.REFERRAL_SOURCE,
                    "WITHDRAWN": LeadStage.WITHDRAWN,
                    "DOES_NOT_QUALIFY": LeadStage.DOES_NOT_QUALIFY,
                }

                stage_upper = stage_str.upper()
                if stage_upper in lead_stage_map:
                    lead_stage_enum = lead_stage_map[stage_upper]
                    new_lead = Lead(
                        name=borrower_name,
                        email=borrower_email,
                        phone=borrower_phone,
                        source="reconciliation",
                        owner_id=current_user.id,
                        lead_received_date=datetime.now(timezone.utc),
                    )
                    db.add(new_lead)
                    db.flush()

                    from services.client_file_service import ensure_client_file
                    ensure_client_file(db, new_lead)

                    db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                               {"stage": lead_stage_enum.name, "id": new_lead.id})
                    db.flush()

                    extracted.match_entity_type = "lead"
                    extracted.match_entity_id = new_lead.id

                    logger.info(f"Created new lead {borrower_name} (ID: {new_lead.id}) in {lead_stage_enum.name} stage")

                    extracted.status = "approved"
                    extracted.reviewed_by = current_user.id
                    extracted.reviewed_at = datetime.now(timezone.utc)
                    db.commit()
                    return {
                        "status": "approved",
                        "entity_type": "lead",
                        "entity_id": new_lead.id,
                        "message": f"Created new lead {borrower_name} in {lead_stage_enum.name} stage"
                    }

                stage = loan_stage_map.get(stage_upper, LoanStage.PROCESSING)
                amount = float(get_val("amount", 0) or get_val("loan_amount", 0) or 0)

                result = db.execute(
                    text("""
                        INSERT INTO loans (
                            loan_number, borrower_name, borrower_email, borrower_phone,
                            coborrower_name, co_borrower_email, program, amount, property_address,
                            property_city, property_state, property_zip, processor, lender,
                            loan_officer_id, stage, days_in_stage, sla_status, created_at, updated_at
                        ) VALUES (
                            :loan_number, :borrower_name, :borrower_email, :borrower_phone,
                            :coborrower_name, :co_borrower_email, :program, :amount, :property_address,
                            :property_city, :property_state, :property_zip, :processor, :lender,
                            :loan_officer_id, :stage, 0, 'on-track', NOW(), NOW()
                        ) RETURNING id
                    """),
                    {
                        "loan_number": loan_number,
                        "borrower_name": borrower_name,
                        "borrower_email": borrower_email,
                        "borrower_phone": borrower_phone,
                        "coborrower_name": coborrower_name,
                        "co_borrower_email": coborrower_email,
                        "program": get_val("program"),
                        "amount": amount,
                        "property_address": get_val("property_address"),
                        "property_city": get_val("property_city"),
                        "property_state": get_val("property_state"),
                        "property_zip": get_val("property_zip"),
                        "processor": get_val("processor"),
                        "lender": get_val("lender"),
                        "loan_officer_id": current_user.id,
                        "stage": stage.name
                    }
                )
                new_loan_id = result.scalar()
                logger.info(f"Created loan via raw SQL, ID: {new_loan_id}, stage: {stage.name}")

                extracted.match_entity_type = "loan"
                extracted.match_entity_id = new_loan_id

                logger.info(f"Created new loan {loan_number} (ID: {new_loan_id}) in {stage.name} stage")

        # Handle status update
        status_updated = False
        old_status = None
        new_status = None

        if approval.update_status_to and extracted.match_entity_id:
            if extracted.match_entity_type == "lead":
                lead = db.query(Lead).filter(Lead.id == extracted.match_entity_id).first()
                if lead:
                    old_status = lead.stage.name if lead.stage else "NEW"
                    lead_stage_map = {
                        "NEW": LeadStage.NEW,
                        "ATTEMPTED_CONTACT": LeadStage.ATTEMPTED_CONTACT,
                        "PROSPECT": LeadStage.PROSPECT,
                        "APPLICATION": LeadStage.APPLICATION,
                        "APPLICATION_STARTED": LeadStage.APPLICATION_STARTED,
                        "PRE_QUALIFIED": LeadStage.PRE_QUALIFIED,
                        "PRE_APPROVED": LeadStage.PRE_APPROVED,
                        "UNDER_CONTRACT": LeadStage.UNDER_CONTRACT,
                        "LONG_TERM_NURTURE": LeadStage.LONG_TERM_NURTURE,
                        "CLOSED": LeadStage.CLOSED,
                        "AMR": LeadStage.AMR,
                        "REFERRAL_SOURCE": LeadStage.REFERRAL_SOURCE,
                        "WITHDRAWN": LeadStage.WITHDRAWN,
                        "DOES_NOT_QUALIFY": LeadStage.DOES_NOT_QUALIFY,
                    }

                    status_upper = approval.update_status_to.upper()
                    if status_upper in lead_stage_map:
                        new_stage = lead_stage_map[status_upper]
                        db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                                   {"stage": new_stage.name, "id": lead.id})
                        new_status = new_stage.name
                        status_updated = True
                        logger.info(f"Updated lead {lead.id} stage from {old_status} to {new_status}")
                    else:
                        logger.warning(f"Attempted to set loan stage '{status_upper}' on lead {lead.id}.")

            elif extracted.match_entity_type == "loan":
                loan = db.query(Loan).filter(Loan.id == extracted.match_entity_id).first()
                if loan:
                    old_status = str(loan.stage) if loan.stage else "PROCESSING"
                    loan_stage_map = {
                        "DISCLOSED": LoanStage.DISCLOSED,
                        "PROCESSING": LoanStage.PROCESSING,
                        "SUBMITTED": LoanStage.SUBMITTED,
                        "UW_RECEIVED": LoanStage.UW_RECEIVED,
                        "APPROVED": LoanStage.APPROVED,
                        "SUSPENDED": LoanStage.SUSPENDED,
                        "CTC": LoanStage.CTC,
                        "DOCS": LoanStage.DOCS,
                        "FUNDED": LoanStage.FUNDED,
                    }
                    if approval.update_status_to.upper() in loan_stage_map:
                        new_stage = loan_stage_map[approval.update_status_to.upper()]
                        db.execute(text("UPDATE loans SET stage = :stage WHERE id = :id"),
                                   {"stage": new_stage.value, "id": loan.id})
                        new_status = new_stage.name
                        status_updated = True
                        logger.info(f"Updated loan {loan.id} stage from {old_status} to {new_status}")

        # Apply to CRM
        applied_fields = []
        if approval.create_new_loan:
            applied = True
            logger.info(f"Skipping apply_extracted_data for new loan - data already set during creation")
        else:
            applied = helpers["apply_extracted_data"](extracted, db)
            fields = extracted.fields or {}
            for field_name, field_data in fields.items():
                if isinstance(field_data, dict) and field_data.get("value"):
                    conf = field_data.get("confidence", 0)
                    if conf >= 0.70:
                        applied_fields.append({
                            "field": field_name,
                            "value": field_data.get("value"),
                            "confidence": conf
                        })

        if applied:
            extracted.status = "approved"
            extracted.reviewed_by = current_user.id
            extracted.reviewed_at = datetime.now(timezone.utc)

            # Handle AI delegation
            if approval.delegate_to_ai and approval.email_intent and approval.recommended_action:
                existing_delegation = db.query(AIDelegatedTask).filter(
                    AIDelegatedTask.user_id == current_user.id,
                    AIDelegatedTask.email_intent == approval.email_intent,
                    AIDelegatedTask.action_type == approval.recommended_action.get("action_type"),
                    AIDelegatedTask.is_active == True
                ).first()

                if existing_delegation:
                    existing_delegation.approval_count += 1
                    existing_delegation.last_approved_at = datetime.now(timezone.utc)
                    logger.info(f"Updated AI delegation {existing_delegation.id} - approval count: {existing_delegation.approval_count}")
                else:
                    new_delegation = AIDelegatedTask(
                        user_id=current_user.id,
                        email_intent=approval.email_intent,
                        action_type=approval.recommended_action.get("action_type", "unknown"),
                        action_value=approval.recommended_action.get("action_value", ""),
                        action_title=approval.recommended_action.get("title", f"Auto-handle {approval.email_intent}"),
                        action_description=approval.recommended_action.get("description", ""),
                        approval_count=1,
                        is_active=True
                    )
                    db.add(new_delegation)
                    logger.info(f"Created new AI delegation for user {current_user.id}: {approval.email_intent}")

            db.commit()

            logger.info(f"Approved and applied extracted data {extracted.id} by user {current_user.id}")

            entity_name = None
            if extracted.match_entity_type == "loan" and extracted.match_entity_id:
                loan_entity = db.query(Loan).filter(Loan.id == extracted.match_entity_id).first()
                if loan_entity:
                    entity_name = loan_entity.borrower_name
            elif extracted.match_entity_type == "lead" and extracted.match_entity_id:
                lead_entity = db.query(Lead).filter(Lead.id == extracted.match_entity_id).first()
                if lead_entity:
                    entity_name = lead_entity.name

            # Delete email from inbox if requested
            email_deleted = False
            should_delete_email = approval.delete_from_inbox

            if not should_delete_email and approval.email_message_id:
                user_delete_setting = db.query(UserSettings).filter(
                    UserSettings.user_id == current_user.id,
                    UserSettings.setting_key == "delete_from_inbox_after_processing"
                ).first()
                if user_delete_setting and user_delete_setting.setting_value == "true":
                    should_delete_email = True
                    logger.info(f"User {current_user.id} has auto-delete enabled, will delete email from inbox")

            if should_delete_email and approval.email_message_id:
                try:
                    oauth_record = db.query(MicrosoftOAuthToken).filter(
                        MicrosoftOAuthToken.user_id == current_user.id
                    ).first()

                    if oauth_record and oauth_record.access_token:
                        delete_result = await helpers["delete_microsoft_email"](oauth_record, approval.email_message_id, db)
                        if delete_result.get("success"):
                            email_deleted = True
                            logger.info(f"Deleted email {approval.email_message_id} from inbox after approval")
                        else:
                            logger.warning(f"Failed to delete email from inbox: {delete_result.get('error')}")
                    else:
                        logger.warning("No Microsoft OAuth token found for email deletion")
                except Exception as del_err:
                    logger.error(f"Error deleting email from inbox: {del_err}")

            return {
                "status": "success",
                "message": "Data approved and applied to CRM",
                "extracted_data_id": extracted.id,
                "entity_type": extracted.match_entity_type,
                "entity_id": extracted.match_entity_id,
                "entity_name": entity_name,
                "ai_delegation_enabled": approval.delegate_to_ai if approval.delegate_to_ai else False,
                "applied_fields": applied_fields,
                "status_updated": status_updated,
                "old_status": old_status,
                "new_status": new_status,
                "email_deleted_from_inbox": email_deleted
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to apply data to CRM")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approval error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reject")
async def reject_reconciliation(
    rejection: ReconciliationRejection,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Reject extracted data"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        AITrainingEvent = models["AITrainingEvent"]
        UserSettings = models["UserSettings"]
        MicrosoftOAuthToken = models["MicrosoftOAuthToken"]

        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == rejection.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == rejection.extracted_data_id
            ).first()

            if extracted:
                event = db.query(IncomingDataEvent).filter(
                    IncomingDataEvent.id == extracted.event_id
                ).first()
                if event and not event.user_id:
                    event.user_id = current_user.id

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        for field_name, field_data in extracted.fields.items():
            training = AITrainingEvent(
                extracted_data_id=extracted.id,
                field_name=field_name,
                original_value=str(field_data.get("value", "")),
                corrected_value=rejection.reason or "",
                label="rejected",
                user_id=current_user.id
            )
            db.add(training)

        extracted.status = "rejected"
        extracted.reviewed_by = current_user.id
        extracted.reviewed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Rejected extracted data {extracted.id} by user {current_user.id}: {rejection.reason}")

        email_deleted = False
        should_delete_email = rejection.delete_from_inbox

        if not should_delete_email and rejection.email_message_id:
            user_delete_setting = db.query(UserSettings).filter(
                UserSettings.user_id == current_user.id,
                UserSettings.setting_key == "delete_from_inbox_after_processing"
            ).first()
            if user_delete_setting and user_delete_setting.setting_value == "true":
                should_delete_email = True
                logger.info(f"User {current_user.id} has auto-delete enabled, will delete email from inbox")

        if should_delete_email and rejection.email_message_id:
            try:
                oauth_record = db.query(MicrosoftOAuthToken).filter(
                    MicrosoftOAuthToken.user_id == current_user.id
                ).first()

                if oauth_record and oauth_record.access_token:
                    delete_result = await helpers["delete_microsoft_email"](oauth_record, rejection.email_message_id, db)
                    if delete_result.get("success"):
                        email_deleted = True
                        logger.info(f"Deleted email {rejection.email_message_id} from inbox after rejection")
                    else:
                        logger.warning(f"Failed to delete email from inbox: {delete_result.get('error')}")
                else:
                    logger.warning("No Microsoft OAuth token found for email deletion")
            except Exception as del_err:
                logger.error(f"Error deleting email from inbox: {del_err}")

        return {
            "status": "success",
            "message": "Data rejected",
            "extracted_data_id": extracted.id,
            "email_deleted_from_inbox": email_deleted
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rejection error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{extracted_data_id}/rematch")
async def rematch_single_item(
    extracted_data_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Re-run entity matching for a single reconciliation item"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        ExtractedData = models["ExtractedData"]

        extracted = db.query(ExtractedData).filter(
            ExtractedData.id == extracted_data_id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        fields = extracted.fields or {}
        if not fields:
            return {
                "status": "error",
                "message": "No fields to match",
                "match_confidence": 0
            }

        entity_match = helpers["match_entity"](fields, db, current_user.id)

        if entity_match["entity_type"] and entity_match["confidence"] > 0:
            extracted.match_entity_type = entity_match["entity_type"]
            extracted.match_entity_id = entity_match["entity_id"]
            extracted.match_confidence = entity_match["confidence"]
            db.commit()

            entity_name = helpers["get_entity_name"](entity_match["entity_type"], entity_match["entity_id"], db)

            logger.info(f"Rematched extracted_data {extracted.id}: {entity_match['entity_type']} {entity_match['entity_id']} ({entity_match['confidence']:.2f})")

            return {
                "status": "success",
                "message": f"Matched to {entity_match['entity_type']}",
                "match_entity_type": entity_match["entity_type"],
                "match_entity_id": entity_match["entity_id"],
                "match_entity_name": entity_name,
                "match_confidence": entity_match["confidence"],
                "candidates": entity_match.get("candidates", [])
            }
        else:
            return {
                "status": "no_match",
                "message": "No matching entity found",
                "match_confidence": 0,
                "candidates": entity_match.get("candidates", [])
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rematch error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rematch-all")
async def rematch_all_pending(
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Re-run entity matching for all pending reconciliation items for current user"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]

        pending = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            or_(
                IncomingDataEvent.user_id == current_user.id,
                IncomingDataEvent.user_id == None
            ),
            ExtractedData.status.in_(["pending_review", "needs_review"])
        ).all()

        logger.info(f"Re-matching {len(pending)} pending items for user {current_user.id}")

        matched_count = 0
        improved_count = 0
        results = []

        for extracted in pending:
            fields = extracted.fields or {}
            if not fields:
                continue

            old_confidence = extracted.match_confidence or 0
            entity_match = helpers["match_entity"](fields, db, current_user.id)

            if entity_match["entity_type"] and entity_match["confidence"] > old_confidence:
                extracted.match_entity_type = entity_match["entity_type"]
                extracted.match_entity_id = entity_match["entity_id"]
                extracted.match_confidence = entity_match["confidence"]

                if old_confidence == 0:
                    matched_count += 1
                else:
                    improved_count += 1

                results.append({
                    "id": extracted.id,
                    "match_type": entity_match["entity_type"],
                    "match_id": entity_match["entity_id"],
                    "old_confidence": old_confidence,
                    "new_confidence": entity_match["confidence"]
                })

        db.commit()
        logger.info(f"Re-matched: {matched_count} new matches, {improved_count} improved matches")

        return {
            "status": "success",
            "total_pending": len(pending),
            "newly_matched": matched_count,
            "improved": improved_count,
            "results": results
        }

    except Exception as e:
        logger.error(f"Rematch all error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/items/bulk")
async def bulk_delete_reconciliation_items(
    item_ids: List[int],
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Permanently delete multiple extracted data items"""
    try:
        models = get_models()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        AITrainingEvent = models["AITrainingEvent"]

        deleted_count = 0
        event_ids_to_check = set()

        for extracted_data_id in item_ids:
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == extracted_data_id
            ).first()

            if extracted:
                event_ids_to_check.add(extracted.event_id)

                db.query(AITrainingEvent).filter(
                    AITrainingEvent.extracted_data_id == extracted_data_id
                ).delete(synchronize_session=False)

                db.delete(extracted)
                deleted_count += 1

        for event_id in event_ids_to_check:
            if event_id:
                other_extracted = db.query(ExtractedData).filter(
                    ExtractedData.event_id == event_id,
                    ~ExtractedData.id.in_(item_ids)
                ).first()
                if not other_extracted:
                    event = db.query(IncomingDataEvent).filter(
                        IncomingDataEvent.id == event_id
                    ).first()
                    if event:
                        db.delete(event)

        db.commit()

        logger.info(f"Bulk deleted {deleted_count} items by user {current_user.id}")

        return {
            "status": "success",
            "message": f"Deleted {deleted_count} items",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/items/{extracted_data_id}")
async def delete_reconciliation_item(
    extracted_data_id: int,
    delete_from_inbox: bool = False,
    email_message_id: Optional[str] = None,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Permanently delete an extracted data item and its associated event"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        AITrainingEvent = models["AITrainingEvent"]
        UserSettings = models["UserSettings"]
        MicrosoftOAuthToken = models["MicrosoftOAuthToken"]

        extracted = db.query(ExtractedData).filter(
            ExtractedData.id == extracted_data_id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Item not found")

        event_id = extracted.event_id

        db.query(AITrainingEvent).filter(
            AITrainingEvent.extracted_data_id == extracted_data_id
        ).delete(synchronize_session=False)

        db.delete(extracted)

        other_extracted = db.query(ExtractedData).filter(
            ExtractedData.event_id == event_id,
            ExtractedData.id != extracted_data_id
        ).first()

        if not other_extracted and event_id:
            event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.id == event_id
            ).first()
            if event:
                db.delete(event)

        db.commit()

        logger.info(f"Deleted extracted data {extracted_data_id} by user {current_user.id}")

        email_deleted = False
        should_delete_email = delete_from_inbox

        if not should_delete_email and email_message_id:
            user_delete_setting = db.query(UserSettings).filter(
                UserSettings.user_id == current_user.id,
                UserSettings.setting_key == "delete_from_inbox_after_processing"
            ).first()
            if user_delete_setting and user_delete_setting.setting_value == "true":
                should_delete_email = True
                logger.info(f"User {current_user.id} has auto-delete enabled, will delete email from inbox")

        if should_delete_email and email_message_id:
            try:
                oauth_record = db.query(MicrosoftOAuthToken).filter(
                    MicrosoftOAuthToken.user_id == current_user.id
                ).first()

                if oauth_record and oauth_record.access_token:
                    delete_result = await helpers["delete_microsoft_email"](oauth_record, email_message_id, db)
                    if delete_result.get("success"):
                        email_deleted = True
                        logger.info(f"Deleted email {email_message_id} from inbox after item deletion")
                    else:
                        logger.warning(f"Failed to delete email from inbox: {delete_result.get('error')}")
                else:
                    logger.warning("No Microsoft OAuth token found for email deletion")
            except Exception as del_err:
                logger.error(f"Error deleting email from inbox: {del_err}")

        return {
            "status": "success",
            "message": "Item permanently deleted",
            "extracted_data_id": extracted_data_id,
            "email_deleted_from_inbox": email_deleted
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/block-sender")
async def block_sender(
    request: BlockSenderRequest,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Block a sender from future email processing"""
    try:
        models = get_models()
        BlockedSender = models["BlockedSender"]

        sender_email = request.sender_email.lower().strip()

        existing = db.query(BlockedSender).filter(
            BlockedSender.user_id == current_user.id,
            BlockedSender.sender_email == sender_email
        ).first()

        if existing:
            return {
                "status": "success",
                "message": "Sender already blocked",
                "sender_email": sender_email
            }

        blocked = BlockedSender(
            user_id=current_user.id,
            sender_email=sender_email,
            reason=request.reason
        )
        db.add(blocked)
        db.commit()

        logger.info(f"User {current_user.id} blocked sender: {mask_email(sender_email)}")

        return {
            "status": "success",
            "message": "Sender blocked",
            "sender_email": sender_email
        }
    except Exception as e:
        logger.error(f"Error blocking sender: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/blocked-senders")
async def get_blocked_senders(
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get list of blocked senders for current user"""
    try:
        models = get_models()
        BlockedSender = models["BlockedSender"]

        blocked = db.query(BlockedSender).filter(
            BlockedSender.user_id == current_user.id
        ).order_by(BlockedSender.created_at.desc()).all()

        return {
            "blocked_senders": [
                {
                    "id": b.id,
                    "sender_email": b.sender_email,
                    "reason": b.reason,
                    "created_at": b.created_at.isoformat() if b.created_at else None
                }
                for b in blocked
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching blocked senders: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/blocked-senders/{sender_id}")
async def unblock_sender(
    sender_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Unblock a sender"""
    try:
        models = get_models()
        BlockedSender = models["BlockedSender"]

        blocked = db.query(BlockedSender).filter(
            BlockedSender.id == sender_id,
            BlockedSender.user_id == current_user.id
        ).first()

        if not blocked:
            raise HTTPException(status_code=404, detail="Blocked sender not found")

        sender_email = blocked.sender_email
        db.delete(blocked)
        db.commit()

        logger.info(f"User {current_user.id} unblocked sender: {sender_email}")

        return {
            "status": "success",
            "message": "Sender unblocked",
            "sender_email": sender_email
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unblocking sender: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/create-lead")
async def create_lead_from_extracted(
    request: CreateLeadFromExtracted,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Create a new lead from extracted email data when no match is found"""
    try:
        models = get_models()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        Lead = models["Lead"]
        LeadStage = models["LeadStage"]

        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == request.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        full_name = f"{request.first_name} {request.last_name}"

        fields = extracted.fields or {}

        email = request.email
        if not email and "email" in fields:
            email = fields["email"].get("value")

        phone = request.phone
        if not phone and "phone" in fields:
            phone = fields["phone"].get("value")

        new_lead = Lead(
            name=full_name,
            email=email,
            phone=phone,
            stage=LeadStage.NEW,
            source="Email Import",
            referral_partner_id=request.referral_partner_id,
            owner_id=current_user.id,
            notes=f"Created from email extraction on {datetime.now().strftime('%Y-%m-%d')}",
            lead_received_date=datetime.now(timezone.utc),
        )

        if "loan_amount" in fields:
            try:
                new_lead.preapproval_amount = float(fields["loan_amount"]["value"])
            except (ValueError, TypeError, KeyError):
                pass

        if "credit_score" in fields:
            try:
                new_lead.credit_score = int(fields["credit_score"]["value"])
            except (ValueError, TypeError, KeyError):
                pass

        if "loan_type" in fields:
            new_lead.loan_type = fields["loan_type"]["value"]

        if "address" in fields:
            new_lead.address = fields["address"]["value"]

        if "property_value" in fields:
            try:
                new_lead.property_value = float(fields["property_value"]["value"])
            except (ValueError, TypeError, KeyError):
                pass

        db.add(new_lead)
        db.flush()

        from services.client_file_service import ensure_client_file
        ensure_client_file(db, new_lead)

        extracted.match_entity_type = "lead"
        extracted.match_entity_id = new_lead.id
        extracted.match_confidence = 1.0
        extracted.status = "approved"
        extracted.reviewed_by = current_user.id
        extracted.reviewed_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(f"Created new lead {new_lead.id} from extracted data {extracted.id} by user {current_user.id}")

        return {
            "status": "success",
            "message": f"Created new lead: {full_name}",
            "lead_id": new_lead.id,
            "extracted_data_id": extracted.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating lead from extracted data: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/check-match/{extracted_id}")
async def check_match_status(
    extracted_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Check if extracted data has a match before approving"""
    try:
        models = get_models()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]

        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == extracted_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        has_match = bool(extracted.match_entity_type and extracted.match_entity_id)

        fields = extracted.fields or {}
        extracted_name = None
        if "borrower_name" in fields:
            extracted_name = fields["borrower_name"].get("value")
        elif "name" in fields:
            extracted_name = fields["name"].get("value")

        return {
            "has_match": has_match,
            "match_entity_type": extracted.match_entity_type,
            "match_entity_id": extracted.match_entity_id,
            "match_confidence": extracted.match_confidence,
            "extracted_name": extracted_name,
            "fields": extracted.fields
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking match status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/correct")
async def correct_and_train(
    correction: ReconciliationApproval,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Correct extracted data and train AI"""
    try:
        models = get_models()
        helpers = get_helper_functions()
        IncomingDataEvent = models["IncomingDataEvent"]
        ExtractedData = models["ExtractedData"]
        AITrainingEvent = models["AITrainingEvent"]

        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == correction.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        if not correction.corrections:
            raise HTTPException(status_code=400, detail="No corrections provided")

        for field_name, corrected_value in correction.corrections.items():
            if field_name in extracted.fields:
                original = extracted.fields[field_name]["value"]

                training = AITrainingEvent(
                    extracted_data_id=extracted.id,
                    field_name=field_name,
                    original_value=str(original),
                    corrected_value=str(corrected_value),
                    label="corrected",
                    user_id=current_user.id
                )
                db.add(training)

                extracted.fields[field_name]["value"] = corrected_value
                extracted.fields[field_name]["confidence"] = 1.0

        applied = helpers["apply_extracted_data"](extracted, db)

        if applied:
            extracted.status = "corrected_and_applied"
            db.commit()

            logger.info(f"Corrected and applied extracted data {extracted.id}")

            return {
                "status": "success",
                "message": "Data corrected and applied. AI will learn from this correction.",
                "extracted_data_id": extracted.id,
                "corrections_count": len(correction.corrections)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to apply corrected data")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Correction error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
