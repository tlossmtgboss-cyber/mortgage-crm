"""
AI Command Email Routes for Perennia AI

This module contains email-related API endpoints for the AI command system:
- send_daily_priorities_email: Send daily priorities report via email
- generate_ai_email: Generate AI-powered email content based on templates
- send_composed_email: Send a composed email via email service (with SF fallback)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import datetime, timezone
import logging
import os
import json

from database import get_db
from ai_command_models import (
    get_main_module,
    get_current_user_dependency,
    SendEmailRequest,
    EmailGenerateRequest,
    EmailSendRequest,
    EMAIL_TEMPLATE_PROMPTS,
)

logger = logging.getLogger(__name__)

email_router = APIRouter()


# ============================================================================
# Email Daily Priorities Report
# ============================================================================

@email_router.post("/send-daily-priorities-email")
async def send_daily_priorities_email(
    request: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dependency)
):
    """
    Send daily priorities report to specified email address
    """
    from email_service import email_service
    from query_executor import QueryExecutor

    # Require authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id
    user_name = f"{current_user.first_name} {current_user.last_name}" if hasattr(current_user, 'first_name') else "User"
    user_email = current_user.email if hasattr(current_user, 'email') else ""

    # Use provided email or fallback to user's email
    to_email = request.email_address or user_email
    if not to_email:
        raise HTTPException(status_code=400, detail="No email address provided")

    try:
        # Execute the daily_focus_priorities query
        priorities = QueryExecutor.execute_query(
            db=db,
            query_type="daily_focus_priorities",
            params={},
            user_id=current_user_id
        )

        logger.info(f"Query result for user {current_user_id}: success={priorities.get('success') if priorities else None}, data_count={len(priorities.get('data', [])) if priorities else 0}")

        if not priorities or not isinstance(priorities, dict) or not priorities.get("data"):
            logger.warning(f"No priorities data found. priorities={priorities}")
            raise HTTPException(status_code=404, detail=f"No priorities data found for user {current_user_id}. Query returned: {len(priorities.get('data', [])) if priorities and isinstance(priorities, dict) else 0} items")

        priorities_data = priorities.get("data", [])

        # If data is empty list, still send email with empty message
        if not priorities_data or len(priorities_data) == 0:
            logger.info(f"No priority items for user {current_user_id}, sending empty report")
            # Create a placeholder message
            priorities_data = [{
                "type": "message",
                "title": "No pending tasks or urgent loans at this time",
                "priority_score": 0,
                "urgency_label": "All Clear"
            }]

        # Send the email
        success = email_service.send_daily_priorities_report(
            to_email=to_email,
            user_name=user_name,
            priorities=priorities_data
        )

        if success:
            return {
                "success": True,
                "message": f"Daily priorities report sent to {to_email}",
                "email": to_email,
                "items_count": len(priorities_data)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send email. Please check SMTP configuration."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending daily priorities email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")


# ============================================================================
# AI Email Generation & Sending
# ============================================================================

@email_router.post("/generate-email")
async def generate_ai_email(
    request: EmailGenerateRequest,
    authorization: str = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dependency)
):
    """Generate AI-powered email content based on template and recipient data"""
    try:
        import anthropic

        # Require authenticated user
        if not current_user or not hasattr(current_user, 'id'):
            raise HTTPException(status_code=401, detail="Authentication required")

        current_user_data = {
            "id": current_user.id,
            "name": current_user.full_name if hasattr(current_user, 'full_name') else "Loan Officer",
            "email": current_user.email if hasattr(current_user, 'email') else "",
            "phone": getattr(current_user, 'phone', ''),
            "title": getattr(current_user, 'current_role', 'Loan Officer'),
            "nmls_id": getattr(current_user, 'nmls_number', '')
        }

        # Get the base prompt for this template
        template_prompt = EMAIL_TEMPLATE_PROMPTS.get(
            request.template_id,
            f"Write a professional mortgage-related email with the topic: {request.template_name}"
        )

        # Get user info for signature
        user_name = current_user_data.get("name", current_user_data.get("email", "Your Loan Officer"))
        user_email = current_user_data.get("email", "")
        user_phone = current_user_data.get("phone", "")
        user_title = current_user_data.get("title", "Loan Officer")
        user_nmls = current_user_data.get("nmls_id", "")

        # Build context about the recipient
        recipient_context = f"Recipient Name: {request.recipient_name}"
        if request.entity_data:
            if request.entity_type == "loan":
                if request.entity_data.get("amount"):
                    recipient_context += f"\nLoan Amount: ${request.entity_data['amount']:,.0f}"
                if request.entity_data.get("property_address"):
                    recipient_context += f"\nProperty: {request.entity_data['property_address']}"
                if request.entity_data.get("stage"):
                    recipient_context += f"\nCurrent Stage: {request.entity_data['stage']}"
                if request.entity_data.get("closing_date"):
                    recipient_context += f"\nClosing Date: {request.entity_data['closing_date']}"
            elif request.entity_type == "lead":
                if request.entity_data.get("source"):
                    recipient_context += f"\nLead Source: {request.entity_data['source']}"
                if request.entity_data.get("stage"):
                    recipient_context += f"\nLead Stage: {request.entity_data['stage']}"

        # Build the full prompt for Claude
        full_prompt = f"""You are a professional mortgage loan officer writing an email to a client/prospect.

TASK: {template_prompt}

RECIPIENT INFORMATION:
{recipient_context}

SENDER INFORMATION:
Name: {user_name}
Title: {user_title}
Email: {user_email}
Phone: {user_phone}
NMLS#: {user_nmls if user_nmls else "N/A"}

GUIDELINES:
1. Be professional but warm and personable
2. Use the recipient's first name if available
3. Keep the email concise but complete
4. Include a clear call-to-action when appropriate
5. End with a professional signature block
6. Do NOT include the subject line in the body
7. Use proper paragraph breaks for readability

OUTPUT FORMAT:
Return ONLY a JSON object with exactly these two fields:
{{"subject": "Email subject line here", "body": "Full email body here with proper formatting"}}

Generate the email now:"""

        # Call Claude API
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            temperature=0.7,  # Some creativity for email writing
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )

        # Parse the response
        response_text = response.content[0].text.strip()

        # Try to parse as JSON
        try:
            # Clean up the response if it has markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            email_data = json.loads(response_text)

            return {
                "success": True,
                "subject": email_data.get("subject", request.template_name),
                "body": email_data.get("body", "")
            }
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract subject and body manually
            logger.warning(f"Failed to parse email JSON, attempting manual extraction")

            # Return the whole response as body with a default subject
            return {
                "success": True,
                "subject": request.template_name,
                "body": response_text
            }

    except Exception as e:
        logger.error(f"Error generating email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate email")


@email_router.post("/send-composed-email")
async def send_composed_email(
    request: EmailSendRequest,
    fastapi_request: Request,
    authorization: str = None,
    db: Session = Depends(get_db),
):
    """Send a composed email via the email service"""
    try:
        from email_service import email_service
        import re

        # Resolve auth dependency manually (get_current_user_dependency returns the function)
        get_current_user_fn = get_current_user_dependency()
        current_user = await get_current_user_fn(
            token=fastapi_request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=fastapi_request,
            db=db,
        )

        # Require authenticated user
        if not current_user or not hasattr(current_user, 'id'):
            raise HTTPException(status_code=401, detail="Authentication required")

        # Get sender info
        sender_name = current_user.full_name if hasattr(current_user, 'full_name') else "The Tim Loss Team"
        sender_email = current_user.email if hasattr(current_user, 'email') else ""

        # Process the email body: detect video and calendar markers
        body_text = request.body

        # Replace [VIDEO MESSAGE - Click to watch: URL] with styled HTML card
        def render_video_card(match):
            video_url = match.group(1)
            return (
                '<div style="background:#f0fdfa; border:1px solid #218D8D; border-radius:8px; '
                'padding:16px; margin:16px 0; text-align:center;">'
                '<p style="font-size:16px; font-weight:600; color:#1f2937; margin:0 0 12px 0;">'
                '&#127909; Video Message</p>'
                f'<a href="{video_url}" style="display:inline-block; padding:10px 24px; '
                'background:#218D8D; color:white; border-radius:6px; text-decoration:none; '
                'font-weight:500; font-size:14px;" target="_blank">Watch Video</a></div>'
            )

        body_text = re.sub(
            r'\[VIDEO MESSAGE - Click to watch:\s*(https?://[^\]]+)\]',
            render_video_card,
            body_text
        )

        # Replace "Schedule a time to talk: URL" with styled calendar CTA
        def render_calendar_card(match):
            booking_url = match.group(1)
            return (
                '<div style="background:#f0fdfa; border:1px solid #218D8D; border-radius:8px; '
                'padding:16px; margin:16px 0; text-align:center;">'
                '<p style="font-size:16px; font-weight:600; color:#1f2937; margin:0 0 12px 0;">'
                '&#128197; Schedule a Meeting</p>'
                f'<a href="{booking_url}" style="display:inline-block; padding:10px 24px; '
                'background:#218D8D; color:white; border-radius:6px; text-decoration:none; '
                'font-weight:500; font-size:14px;" target="_blank">Book a Time</a></div>'
            )

        body_text = re.sub(
            r'Schedule a time to talk:\s*(https?://\S+)',
            render_calendar_card,
            body_text
        )

        # Convert remaining newlines to <br>
        body_html_content = body_text.replace(chr(10), '<br>')

        # Format the email body as HTML
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .email-content {{
            white-space: pre-wrap;
            font-size: 15px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="email-content">{body_html_content}</div>
    <div class="footer">
        <p>Sent via The Tim Loss Team</p>
    </div>
</body>
</html>
"""

        # Try sending via Salesforce first if the user has a connected SF profile
        send_method = "sendgrid"
        sf_contact_linked = False
        sf_send_attempted = False

        try:
            from salesforce_integration_models import IntegrationProfile
            from services.salesforce.email_sync_service import salesforce_email_sync

            sf_profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.user_id == current_user.id,
                IntegrationProfile.provider == "salesforce",
                IntegrationProfile.status.in_(["connected", "active"])
            ).first()

            if sf_profile:
                sf_send_attempted = True
                sf_result = await salesforce_email_sync.send_email_via_salesforce(
                    db=db,
                    integration_profile_id=sf_profile.id,
                    to_email=request.to_email,
                    subject=request.subject,
                    html_body=html_body
                )

                if sf_result.get("success"):
                    send_method = "salesforce"
                    sf_contact_linked = sf_result.get("sf_contact_id") is not None
                    logger.info(f"Email sent via Salesforce to {request.to_email} (contact_linked={sf_contact_linked})")
                else:
                    logger.warning(f"Salesforce email send failed, falling back to SendGrid: {sf_result.get('message')}")
        except Exception as sf_err:
            logger.warning(f"Salesforce email attempt failed, falling back to SendGrid: {sf_err}")

        # Fall back to SendGrid if Salesforce didn't send
        if send_method != "salesforce":
            success = email_service.send_html_email(
                to_email=request.to_email,
                subject=request.subject,
                html_body=html_body,
                plain_text_body=request.body
            )
            if not success:
                raise HTTPException(status_code=500, detail="Failed to send email - email service returned error")

        # Log the email activity
        try:
            from models import Activity, Lead, Loan

            activity_data = {
                "organization_id": 1,
                "activity_type": "email_sent",
                "subject": f"Email: {request.subject}",
                "description": f"Email sent to {request.to_name or request.to_email}: {request.subject} (via {send_method})",
                "completed": True,
                "completed_at": datetime.now(timezone.utc),
                "user_id": current_user.id,
            }

            if request.entity_type == "lead" and request.entity_id:
                activity_data["lead_id"] = request.entity_id
            elif request.entity_type == "loan" and request.entity_id:
                activity_data["loan_id"] = request.entity_id

            activity = Activity(**activity_data)
            db.add(activity)
            db.commit()
        except Exception as log_err:
            logger.warning(f"Failed to log email activity: {log_err}")

        return {
            "success": True,
            "message": f"Email sent successfully to {request.to_email}",
            "send_method": send_method,
            "sf_contact_linked": sf_contact_linked
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")
