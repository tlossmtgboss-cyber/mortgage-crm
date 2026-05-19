"""Telephony tools — click-to-dial, SMS, bulk outreach (extracted verbatim)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Match the parent module's tolerant import: PII masking helper used by
# bulk_lead_outreach when logging an SMS failure.
try:
    from utils.pii_mask import mask_phone
except ImportError:  # pragma: no cover — defensive fallback
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"


def build_telephony_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    org_id = ctx["org_id"]

    # ============ Communication Tools ============

    async def execute_click_to_dial(args):
        """
        Initiate an outbound call to a contact using click-to-dial.

        Args:
            phone_number: The phone number to call (required)
            contact_name: Name of the person being called (optional)
            lead_id: Associated lead ID (optional)
            loan_id: Associated loan ID (optional)
        """
        import os
        from telephony.dialer_engine import click_to_dial

        phone_number = args.get("phone_number")
        if not phone_number:
            return {"success": False, "error": "phone_number is required"}

        # Clean phone number - remove any non-digit characters except +
        clean_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")
        if not clean_phone.startswith("+"):
            clean_phone = f"+1{clean_phone}" if len(clean_phone) == 10 else f"+{clean_phone}"

        contact_name = args.get("contact_name", "Contact")
        lead_id = args.get("lead_id")
        loan_id = args.get("loan_id")

        base_url = os.getenv("BASE_URL", "https://app.perenniaai.com")

        try:
            result = click_to_dial(
                db_session=db,
                agent_id=current_user.id,
                phone_number=clean_phone,
                contact_name=contact_name,
                base_url=base_url,
                lead_id=lead_id,
                loan_id=loan_id
            )

            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Call initiated to {contact_name} at {clean_phone}",
                    "call_sid": result.get("call_sid"),
                    "phone_number": clean_phone,
                    "contact_name": contact_name
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to initiate call"),
                    "phone_number": clean_phone
                }
        except Exception as e:
            logger.error(f"Error in click_to_dial: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["click_to_dial"] = execute_click_to_dial
    tools["make_call"] = execute_click_to_dial  # Alias for natural language
    tools["call_contact"] = execute_click_to_dial  # Another alias

    async def execute_send_sms(args):
        """
        Send an SMS message to a phone number.

        Args:
            phone_number: The phone number to text (required)
            message: The message content (required)
            lead_id: Associated lead ID (optional)
            loan_id: Associated loan ID (optional)
        """
        from integrations.sms_service import get_sms_client

        sms_client = get_sms_client(db=db, user_id=current_user.id)
        phone_number = args.get("phone_number") or args.get("to_number")
        message = args.get("message")

        if not phone_number:
            return {"success": False, "error": "phone_number is required"}
        if not message:
            return {"success": False, "error": "message is required"}

        # Clean phone number
        clean_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")
        if not clean_phone.startswith("+"):
            clean_phone = f"+1{clean_phone}" if len(clean_phone) == 10 else f"+{clean_phone}"

        # TCPA compliance: use verified sender with consent + DNC checks
        try:
            from telephony.sms import send_sms_verified
            result = send_sms_verified(
                to=clean_phone,
                text=message,
                user_id=current_user.id,
                organization_id=org_id,
            )
            message_sid = result.get("id") if isinstance(result, dict) else result

            if message_sid and result.get("status") == "sent":
                # Log to database
                try:
                    from database.models import SMSMessage
                    sms_record = SMSMessage(
                        user_id=current_user.id,
                        lead_id=args.get("lead_id"),
                        loan_id=args.get("loan_id"),
                        to_number=clean_phone,
                        from_number=sms_client.from_number,
                        message=message,
                        direction="outbound",
                        status="sent",
                        provider_message_id=message_sid
                    )
                    db.add(sms_record)
                    db.commit()
                except Exception as log_err:
                    logger.warning(f"Failed to log SMS: {log_err}")

                return {
                    "success": True,
                    "message": f"SMS sent to {clean_phone}",
                    "message_sid": message_sid,
                    "phone_number": clean_phone
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send SMS - check telephony provider configuration",
                    "phone_number": clean_phone
                }
        except Exception as e:
            logger.error(f"Error in send_sms: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["send_sms"] = execute_send_sms
    tools["send_text"] = execute_send_sms  # Alias for natural language
    tools["text_contact"] = execute_send_sms  # Another alias

    async def execute_bulk_lead_outreach(args):
        """
        Send bulk text messages to leads and create follow-up tasks.

        Args:
            lead_status: Status of leads to contact (e.g., "NEW", "ATTEMPTED_CONTACT")
            message_template: Message to send (can include {name} placeholder)
            include_calendar_link: Whether to include user's calendar booking link
            create_followup_tasks: Whether to create tasks for non-responders
        """
        from sqlalchemy import text
        from database import SessionLocal

        lead_status = args.get("lead_status", "NEW")
        message_template = args.get("message_template", "")
        include_calendar_link = args.get("include_calendar_link", True)
        create_followup_tasks = args.get("create_followup_tasks", True)

        if not message_template:
            message_template = "Hi {name}, this is your loan officer. I'd love to schedule a time to discuss your mortgage needs. When works best for you?"

        db = SessionLocal()
        results = {
            "leads_found": 0,
            "texts_sent": 0,
            "texts_failed": 0,
            "tasks_created": 0,
            "leads_contacted": [],
            "leads_no_phone": []
        }

        try:
            # Get leads by status — scoped to current user + tenant
            query = text("""
                SELECT id, first_name, last_name, phone, email, stage
                FROM leads
                WHERE stage = :status
                AND owner_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND phone IS NOT NULL
                AND phone != ''
                LIMIT 50
            """)
            leads = db.execute(query, {
                "status": lead_status,
                "user_id": current_user.id,
                "org_id": org_id,
            }).fetchall()
            results["leads_found"] = len(leads)

            if not leads:
                return {
                    "success": True,
                    "message": f"No leads found with status '{lead_status}' that have phone numbers.",
                    "data": results
                }

            # Get calendar booking link for user if available
            booking_link = ""
            if include_calendar_link and current_user and hasattr(current_user, 'id'):
                booking_query = text("""
                    SELECT booking_slug FROM users WHERE id = :user_id
                """)
                user_result = db.execute(booking_query, {"user_id": current_user.id}).fetchone()
                if user_result and user_result.booking_slug:
                    booking_link = f"\n\nBook a time here: https://perenniaai.com/book/{user_result.booking_slug}"

            # TCPA compliance: use verified sender with consent + DNC checks
            from telephony.sms import send_sms_verified

            for lead in leads:
                lead_id, first_name, last_name, phone, email, stage = lead
                name = f"{first_name or ''} {last_name or ''}".strip() or "there"

                if not phone:
                    results["leads_no_phone"].append({"id": lead_id, "name": name})
                    continue

                # Personalize message
                message = message_template.replace("{name}", first_name or name)
                message += booking_link

                try:
                    # Send SMS via TCPA-compliant verified sender
                    sms_result = send_sms_verified(
                        to=phone,
                        text=message,
                        user_id=current_user.id,
                        organization_id=org_id,
                    )
                    sid = sms_result.get("id") if isinstance(sms_result, dict) else sms_result
                    if sid:
                        results["texts_sent"] += 1
                        results["leads_contacted"].append({
                            "id": lead_id,
                            "name": name,
                            "phone": phone,
                            "message_sid": sid
                        })

                        # Log communication
                        log_query = text("""
                            INSERT INTO communications (lead_id, type, direction, content, status, created_at)
                            VALUES (:lead_id, 'sms', 'outbound', :content, 'sent', NOW())
                        """)
                        db.execute(log_query, {"lead_id": lead_id, "content": message})

                        # Create follow-up task if requested
                        if create_followup_tasks:
                            task_query = text("""
                                INSERT INTO tasks (
                                    title, description, due_date, priority, status,
                                    related_to_type, related_to_id, created_at
                                ) VALUES (
                                    :title, :description, NOW() + INTERVAL '2 days',
                                    'medium', 'pending', 'lead', :lead_id, NOW()
                                )
                            """)
                            db.execute(task_query, {
                                "title": f"Follow up with {name} - no SMS response",
                                "description": f"Sent scheduling text on {datetime.now().strftime('%m/%d')}. Follow up if no response.",
                                "lead_id": lead_id
                            })
                            results["tasks_created"] += 1
                    else:
                        results["texts_failed"] += 1
                except Exception as e:
                    logger.error(f"Failed to send SMS to {mask_phone(phone)}: {e}")
                    results["texts_failed"] += 1

            db.commit()

            return {
                "success": True,
                "message": f"Sent {results['texts_sent']} texts to {lead_status} leads. Created {results['tasks_created']} follow-up tasks.",
                "data": results
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error in bulk_lead_outreach: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["bulk_lead_outreach"] = execute_bulk_lead_outreach

    return tools
