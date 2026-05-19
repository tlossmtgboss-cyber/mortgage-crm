"""Communications tools — email send/read + push notifications (extracted verbatim)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_comms_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    # ctx fields not used in this module — kept for signature parity
    _ = ctx

    async def execute_send_email(args):
        """
        Send an email to an external contact via Microsoft Graph.

        CALENDAR-AWARE: If the email is about scheduling (detected via keywords),
        automatically checks the user's calendar and injects available time slots
        into the email body before sending.

        Args:
            to_email: Recipient email address (required)
            subject: Email subject line (required)
            body: Email body content (required)
            user_id: User ID for OAuth token lookup (optional, uses current_user if not provided)
            skip_availability: Set to True to skip auto-injecting availability (optional)
        """
        import httpx
        import os
        import re
        from datetime import datetime, timedelta

        to_email = args.get("to_email")
        subject = args.get("subject", "Message from your Loan Officer")
        body = args.get("body", "")
        skip_availability = args.get("skip_availability", False)

        if not to_email:
            return {"success": False, "error": "to_email is required"}
        if not body:
            return {"success": False, "error": "body is required"}

        # Track if we injected availability
        availability_injected = False
        injected_slots = []

        # Helper: Detect if email is about scheduling
        def is_scheduling_email(subj: str, content: str) -> bool:
            scheduling_keywords = [
                r'\bschedul\w*\b', r'\bmeet\w*\b', r'\bappointment\b', r'\bcall\b',
                r'\bavailab\w*\b', r'\bset up a time\b', r'\bfind a time\b',
                r'\bwhen.*free\b', r'\bwhen.*available\b', r'\bdiscuss\b',
                r'\bchat\b', r'\bconnect\b', r'\bconsultation\b'
            ]
            combined = f"{subj} {content}".lower()
            return any(re.search(p, combined, re.IGNORECASE) for p in scheduling_keywords)

        # Helper: Calculate free slots from busy periods
        def calculate_free_slots(busy_slots, days_ahead=5, slots_needed=4):
            free_slots = []
            now = datetime.now()
            start_date = now.date() + timedelta(days=1) if now.hour >= 16 else now.date()

            for day_offset in range(days_ahead):
                check_date = start_date + timedelta(days=day_offset)
                if check_date.weekday() >= 5:  # Skip weekends
                    continue

                for hour in range(9, 17):  # 9 AM to 5 PM
                    for minute in [0, 30]:
                        slot_start = datetime.combine(check_date, datetime.min.time().replace(hour=hour, minute=minute))
                        slot_end = slot_start + timedelta(minutes=30)

                        if slot_start <= now + timedelta(hours=1):
                            continue

                        is_free = True
                        for busy in busy_slots:
                            busy_start = busy.get('start')
                            busy_end = busy.get('end')
                            if isinstance(busy_start, str):
                                busy_start = datetime.fromisoformat(busy_start.replace('Z', '+00:00').replace('+00:00', ''))
                            if isinstance(busy_end, str):
                                busy_end = datetime.fromisoformat(busy_end.replace('Z', '+00:00').replace('+00:00', ''))
                            if hasattr(busy_start, 'replace'):
                                busy_start = busy_start.replace(tzinfo=None)
                            if hasattr(busy_end, 'replace'):
                                busy_end = busy_end.replace(tzinfo=None)
                            if slot_start < busy_end and slot_end > busy_start:
                                is_free = False
                                break

                        if is_free:
                            free_slots.append({
                                'date': check_date.strftime('%A, %B %d'),
                                'start': slot_start.strftime('%I:%M %p'),
                            })
                            if len(free_slots) >= slots_needed:
                                return free_slots
            return free_slots

        # Helper: Inject availability into email body
        def inject_availability(content: str, slots: list) -> str:
            if not slots:
                return content
            avail_text = "\n\nHere are some times I'm available:\n"
            for slot in slots:
                avail_text += f"• {slot['date']} at {slot['start']}\n"
            avail_text += "\nLet me know which time works best for you, or suggest another time that's convenient.\n"

            # Try to insert before sign-off
            for pattern in [r'\n\s*(Best|Best regards|Regards|Thanks|Thank you|Sincerely)', r'\n\s*--\s*\n']:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return content[:match.start()] + avail_text + content[match.start():]
            return content + avail_text

        try:
            # Check for Microsoft OAuth token in microsoft_oauth_tokens table
            user_id = current_user.id
            logger.info(f"[send_email] Looking up OAuth token for user_id={user_id} (type: {type(user_id).__name__})")

            oauth = db.execute(text("""
                SELECT access_token, refresh_token, token_expires_at
                FROM microsoft_oauth_tokens
                WHERE user_id = :user_id
                AND access_token IS NOT NULL
            """), {"user_id": int(user_id)}).fetchone()

            if not oauth:
                return {
                    "success": False,
                    "error": "Microsoft account not connected. Please connect your Microsoft 365 account in Settings > Outlook Email.",
                    "requires_oauth": True
                }

            access_token = oauth.access_token
            refresh_token = oauth.refresh_token
            expires_at = oauth.token_expires_at

            # Decrypt token if encrypted (tokens are encrypted using SECRET_KEY)
            if access_token and access_token.startswith("gAAAAA"):
                try:
                    from cryptography.fernet import Fernet
                    import base64
                    secret_key = os.getenv("SECRET_KEY", "")
                    key_material = secret_key.encode()[:32].ljust(32, b'0')
                    encryption_key = base64.urlsafe_b64encode(key_material)
                    f = Fernet(encryption_key)
                    access_token = f.decrypt(access_token.encode()).decode()
                    if refresh_token and refresh_token.startswith("gAAAAA"):
                        refresh_token = f.decrypt(refresh_token.encode()).decode()
                except Exception as decrypt_err:
                    logger.error(f"Token decryption failed: {decrypt_err}")
                    return {
                        "success": False,
                        "error": "Failed to decrypt email token. Please reconnect your Microsoft account in Settings > Outlook Email.",
                        "requires_oauth": True
                    }

            # Check if token needs refresh
            if expires_at and expires_at < datetime.now(timezone.utc):
                logger.info("Access token expired, attempting refresh...")
                client_id = os.getenv("MICROSOFT_CLIENT_ID")
                client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

                if refresh_token and client_id and client_secret:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        refresh_response = await client.post(
                            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                            data={
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "refresh_token": refresh_token,
                                "grant_type": "refresh_token",
                                "scope": "Mail.Send Mail.ReadWrite offline_access"
                            },
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            timeout=30.0
                        )

                        if refresh_response.status_code == 200:
                            tokens = refresh_response.json()
                            access_token = tokens["access_token"]
                            new_refresh = tokens.get("refresh_token", refresh_token)
                            new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

                            # Store new tokens (encrypted using SECRET_KEY)
                            try:
                                from cryptography.fernet import Fernet
                                import base64
                                secret_key = os.getenv("SECRET_KEY", "")
                                key_material = secret_key.encode()[:32].ljust(32, b'0')
                                enc_key = base64.urlsafe_b64encode(key_material)
                                f = Fernet(enc_key)
                                enc_access = f.encrypt(access_token.encode()).decode()
                                enc_refresh = f.encrypt(new_refresh.encode()).decode()

                                db.execute(text("""
                                    UPDATE microsoft_oauth_tokens
                                    SET access_token = :access_token,
                                        refresh_token = :refresh_token,
                                        token_expires_at = :expires_at,
                                        updated_at = :updated_at
                                    WHERE user_id = :user_id
                                """), {
                                    "access_token": enc_access,
                                    "refresh_token": enc_refresh,
                                    "expires_at": new_expires,
                                    "updated_at": datetime.now(timezone.utc),
                                    "user_id": int(user_id)
                                })
                                db.commit()
                            except Exception as store_err:
                                logger.warning(f"Failed to store refreshed token: {store_err}")
                        else:
                            return {
                                "success": False,
                                "error": "Microsoft token expired and refresh failed. Please reconnect your account.",
                                "requires_oauth": True
                            }

            # Auto-inject calendar availability for scheduling emails
            if not skip_availability and is_scheduling_email(subject, body):
                logger.info(f"[send_email] Detected scheduling email - checking calendar availability")
                try:
                    # Get busy slots from Microsoft Graph calendar
                    async with httpx.AsyncClient(timeout=15.0) as cal_client:
                        # First get the user's email
                        me_response = await cal_client.get(
                            "https://graph.microsoft.com/v1.0/me",
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=15.0
                        )

                        if me_response.status_code == 200:
                            me_data = me_response.json()
                            user_email = me_data.get("mail") or me_data.get("userPrincipalName")

                            if user_email:
                                # Get calendar schedule for next 7 days
                                start_time = datetime.now(timezone.utc)
                                end_time = start_time + timedelta(days=7)

                                schedule_response = await cal_client.post(
                                    "https://graph.microsoft.com/v1.0/me/calendar/getSchedule",
                                    headers={
                                        "Authorization": f"Bearer {access_token}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "schedules": [user_email],
                                        "startTime": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
                                        "endTime": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
                                        "availabilityViewInterval": 30
                                    },
                                    timeout=30.0
                                )

                                if schedule_response.status_code == 200:
                                    schedule_data = schedule_response.json()
                                    busy_slots = []
                                    for schedule in schedule_data.get("value", []):
                                        for item in schedule.get("scheduleItems", []):
                                            busy_slots.append({
                                                "start": item["start"]["dateTime"],
                                                "end": item["end"]["dateTime"]
                                            })

                                    # Calculate free slots
                                    free_slots = calculate_free_slots(busy_slots, days_ahead=5, slots_needed=4)

                                    if free_slots:
                                        body = inject_availability(body, free_slots)
                                        availability_injected = True
                                        injected_slots = free_slots
                                        logger.info(f"[send_email] Injected {len(free_slots)} available time slots into email")
                                    else:
                                        logger.info("[send_email] No free slots found to inject")
                                else:
                                    logger.warning(f"[send_email] Calendar API returned {schedule_response.status_code}")

                except Exception as cal_err:
                    logger.warning(f"[send_email] Could not get calendar availability: {cal_err}")
                    # Continue without availability - don't block the email

            # Send email via Microsoft Graph
            async with httpx.AsyncClient(timeout=30.0) as client:
                email_data = {
                    "message": {
                        "subject": subject,
                        "body": {
                            "contentType": "Text",
                            "content": body
                        },
                        "toRecipients": [
                            {"emailAddress": {"address": to_email}}
                        ]
                    },
                    "saveToSentItems": "true"
                }

                response = await client.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=email_data,
                    timeout=30.0
                )

                if response.status_code == 202:
                    # Log the sent email
                    try:
                        db.execute(text("""
                            INSERT INTO communications (
                                type, direction, user_id, to_address,
                                subject, body_preview, status, sent_at, created_at
                            ) VALUES (
                                'email', 'outbound', :user_id, :to_email,
                                :subject, :body_preview, 'sent', NOW(), NOW()
                            )
                        """), {
                            "user_id": current_user.id,
                            "to_email": to_email,
                            "subject": subject,
                            "body_preview": body[:500]
                        })
                        db.commit()
                    except Exception as log_err:
                        logger.warning(f"Failed to log email: {log_err}")

                    result = {
                        "success": True,
                        "message": f"Email sent successfully to {to_email}",
                        "to_email": to_email,
                        "subject": subject
                    }

                    # Include availability injection info
                    if availability_injected:
                        result["availability_injected"] = True
                        result["injected_slots"] = [f"{s['date']} at {s['start']}" for s in injected_slots]
                        result["message"] += f" (included {len(injected_slots)} available time slots)"

                    return result
                else:
                    error_text = response.text
                    logger.error(f"Microsoft Graph sendMail failed: {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "error": f"Failed to send email: {error_text}",
                        "status_code": response.status_code
                    }

        except Exception as e:
            logger.error(f"Error in send_email: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["send_email"] = execute_send_email

    # ============ Email Intelligence Tools ============
    # Tool to check inbox for emails needing response

    from ..tools.email_intel import get_emails_needing_response as _get_emails_needing_response

    async def execute_get_emails_needing_response(args):
        """Get emails from inbox that need a response."""
        # Pass the current user's ID for email lookup
        user_id = current_user.id if hasattr(current_user, 'id') else None
        days = args.get("days", 7)
        unread_only = args.get("unread_only", True)
        limit = args.get("limit", 20)

        try:
            result = _get_emails_needing_response(
                user_id=user_id,
                days=days,
                unread_only=unread_only,
                limit=limit
            )
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in get_emails_needing_response: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["get_emails_needing_response"] = execute_get_emails_needing_response

    # Tool to search user's email inbox via Microsoft Graph
    from ..tools.email_intel import search_email_inbox as _search_email_inbox

    async def execute_search_email_inbox(args):
        """Search user's Microsoft 365 email inbox for messages."""
        user_id = current_user.id if hasattr(current_user, 'id') else None
        search_query = args.get("search_query", "")
        limit = args.get("limit", 10)
        folder = args.get("folder", "all")

        try:
            result = _search_email_inbox(
                search_query=search_query,
                user_id=user_id,
                limit=limit,
                folder=folder
            )
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in search_email_inbox: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["search_email_inbox"] = execute_search_email_inbox

    # -----------------------------------------------------------------
    # sendPushNotification — Push notification to user's mobile device
    # -----------------------------------------------------------------

    async def execute_send_push_notification(
        user_id: int,
        title: str,
        body: str,
        notification_type: str = "general",
        priority: str = "normal",
        loan_id: int = None,
    ) -> Dict[str, Any]:
        """Send a push notification to a user's registered mobile devices.

        Respects rate limits (max 5/user/hour), quiet hours, and user preferences.
        """
        try:
            from services.agent_notification_service import get_agent_notification_service
            push_svc = get_agent_notification_service()

            data_payload = {"type": notification_type}
            if loan_id:
                data_payload["entity_id"] = str(loan_id)
                data_payload["entity_type"] = "loan"
                data_payload["route"] = f"/loans/{loan_id}"

            result = push_svc.notify_user(
                db=db,
                user_id=user_id,
                title=title,
                body=body,
                notification_type=notification_type,
                data=data_payload,
                priority=priority,
            )

            return {
                "status": "success",
                "sent": result.get("sent", 0),
                "failed": result.get("failed", 0),
                "skipped": result.get("skipped", 0),
                "reason": result.get("reason"),
            }
        except Exception as e:
            logger.error(f"Error in sendPushNotification: {e}")
            return {"status": "error", "error": str(e), "sent": 0}

    tools["sendPushNotification"] = execute_send_push_notification

    return tools
