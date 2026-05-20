"""
Automated Outreach Routes
Drip campaigns and trigger-based automatic messaging
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum
import logging
import json

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)

import os
try:
    from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _DEFAULT_ORGANIZER_EMAIL
except ImportError:
    _DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

router = APIRouter(prefix="/api/v1/automated-outreach", tags=["Automated Outreach"], dependencies=[Depends(require_auth)])


# ============================================================================
# Enums
# ============================================================================

class CampaignStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DRAFT = "draft"


class TriggerType(str, Enum):
    NEW_LEAD = "new_lead"
    LEAD_STATUS_CHANGE = "lead_status_change"
    NO_ACTIVITY = "no_activity"
    APPOINTMENT_BOOKED = "appointment_booked"
    APPLICATION_STARTED = "application_started"
    APPLICATION_ABANDONED = "application_abandoned"
    LOAN_STATUS_CHANGE = "loan_status_change"


class ChannelType(str, Enum):
    EMAIL = "email"
    SMS = "sms"


# ============================================================================
# Request/Response Models
# ============================================================================

class CampaignStepCreate(BaseModel):
    step_order: int
    channel: ChannelType
    delay_days: int = 0
    delay_hours: int = 0
    subject: Optional[str] = None  # For email
    message: str


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[CampaignStepCreate]


class TriggerCreate(BaseModel):
    name: str
    trigger_type: TriggerType
    trigger_config: Optional[dict] = None  # e.g., {"old_status": "new", "new_status": "contacted"}
    channel: ChannelType
    subject: Optional[str] = None
    message: str
    is_active: bool = True


class AssignToCampaign(BaseModel):
    lead_ids: List[int]
    campaign_id: int


# ============================================================================
# Database Table Creation
# ============================================================================

def create_automated_outreach_tables(engine):
    """Create tables for automated outreach (PostgreSQL compatible)"""
    with engine.connect() as conn:
        # Campaigns table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS outreach_campaigns (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                status VARCHAR(50) DEFAULT 'draft',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Campaign steps
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS campaign_steps (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER NOT NULL,
                step_order INTEGER NOT NULL,
                channel VARCHAR(20) NOT NULL,
                delay_days INTEGER DEFAULT 0,
                delay_hours INTEGER DEFAULT 0,
                subject VARCHAR(500),
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (campaign_id) REFERENCES outreach_campaigns(id)
            )
        """))

        # Lead campaign assignments
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lead_campaign_assignments (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                current_step INTEGER DEFAULT 1,
                status VARCHAR(50) DEFAULT 'active',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                next_send_at TIMESTAMP,
                completed_at TIMESTAMP,
                paused_at TIMESTAMP,
                FOREIGN KEY (campaign_id) REFERENCES outreach_campaigns(id)
            )
        """))

        # Outreach triggers
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS outreach_triggers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                trigger_type VARCHAR(50) NOT NULL,
                trigger_config TEXT,
                channel VARCHAR(20) NOT NULL,
                subject VARCHAR(500),
                message TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Trigger execution log
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS trigger_execution_log (
                id SERIAL PRIMARY KEY,
                trigger_id INTEGER NOT NULL,
                lead_id INTEGER,
                loan_id INTEGER,
                channel VARCHAR(20),
                recipient VARCHAR(255),
                message TEXT,
                status VARCHAR(50),
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trigger_id) REFERENCES outreach_triggers(id)
            )
        """))

        conn.commit()
        logger.info("Automated outreach tables created/verified")


# ============================================================================
# Campaign Endpoints
# ============================================================================

@router.get("/campaigns")
async def get_campaigns(
    status: Optional[CampaignStatus] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """Get all campaigns"""
    try:
        query = "SELECT * FROM outreach_campaigns"
        params = {}

        if status:
            query += " WHERE status = :status"
            params["status"] = status.value

        query += " ORDER BY created_at DESC"

        result = await db.execute(text(query), params)
        campaigns = [dict(row._mapping) for row in result.fetchall()]

        # Get step counts
        for campaign in campaigns:
            step_result = await db.execute(text("""
                SELECT COUNT(*) as count FROM campaign_steps WHERE campaign_id = :id
            """), {"id": campaign["id"]})
            campaign["step_count"] = step_result.scalar() or 0

            # Get active leads count
            lead_result = await db.execute(text("""
                SELECT COUNT(*) as count FROM lead_campaign_assignments
                WHERE campaign_id = :id AND status = 'active'
            """), {"id": campaign["id"]})
            campaign["active_leads"] = lead_result.scalar() or 0

        return {"campaigns": campaigns}
    except SQLAlchemyError as e:
        logger.error(f"Error fetching campaigns: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/campaigns")
async def create_campaign(
    campaign: CampaignCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new drip campaign"""
    try:
        # Create campaign
        result = await db.execute(text("""
            INSERT INTO outreach_campaigns (name, description, status, created_at)
            VALUES (:name, :description, 'draft', CURRENT_TIMESTAMP)
        """), {
            "name": campaign.name,
            "description": campaign.description
        })

        campaign_id = result.lastrowid

        # Create steps
        for step in campaign.steps:
            await db.execute(text("""
                INSERT INTO campaign_steps (
                    campaign_id, step_order, channel, delay_days, delay_hours,
                    subject, message, created_at
                ) VALUES (
                    :campaign_id, :step_order, :channel, :delay_days, :delay_hours,
                    :subject, :message, CURRENT_TIMESTAMP
                )
            """), {
                "campaign_id": campaign_id,
                "step_order": step.step_order,
                "channel": step.channel.value,
                "delay_days": step.delay_days,
                "delay_hours": step.delay_hours,
                "subject": step.subject,
                "message": step.message
            })

        await db.commit()

        return {
            "success": True,
            "campaign_id": campaign_id,
            "message": f"Campaign '{campaign.name}' created with {len(campaign.steps)} steps"
        }
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating campaign: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/campaigns/{campaign_id}")
async def get_campaign_detail(
    campaign_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get campaign details with steps"""
    try:
        # Get campaign
        result = await db.execute(text("""
            SELECT * FROM outreach_campaigns WHERE id = :id
        """), {"id": campaign_id})
        campaign = result.fetchone()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        campaign_dict = dict(campaign._mapping)

        # Get steps
        steps_result = await db.execute(text("""
            SELECT * FROM campaign_steps
            WHERE campaign_id = :id
            ORDER BY step_order
        """), {"id": campaign_id})
        campaign_dict["steps"] = [dict(row._mapping) for row in steps_result.fetchall()]

        # Get assigned leads
        leads_result = await db.execute(text("""
            SELECT
                lca.*,
                l.first_name, l.last_name, l.email, l.phone
            FROM lead_campaign_assignments lca
            JOIN leads l ON l.id = lca.lead_id
            WHERE lca.campaign_id = :id
            ORDER BY lca.started_at DESC
        """), {"id": campaign_id})
        campaign_dict["assigned_leads"] = [dict(row._mapping) for row in leads_result.fetchall()]

        return campaign_dict
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error fetching campaign: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/campaigns/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: int,
    status: CampaignStatus,
    db: AsyncSession = Depends(get_async_db)
):
    """Activate, pause, or complete a campaign"""
    try:
        await db.execute(text("""
            UPDATE outreach_campaigns
            SET status = :status, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": campaign_id, "status": status.value})
        await db.commit()

        return {"success": True, "message": f"Campaign status updated to {status.value}"}
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/campaigns/{campaign_id}/assign")
async def assign_leads_to_campaign(
    campaign_id: int,
    request: AssignToCampaign,
    db: AsyncSession = Depends(get_async_db)
):
    """Assign leads to a campaign"""
    try:
        # Get first step for scheduling
        step_result = await db.execute(text("""
            SELECT delay_days, delay_hours FROM campaign_steps
            WHERE campaign_id = :id ORDER BY step_order LIMIT 1
        """), {"id": campaign_id})
        first_step = step_result.fetchone()

        if not first_step:
            raise HTTPException(status_code=400, detail="Campaign has no steps")

        # Calculate first send time
        delay_minutes = (first_step.delay_days * 24 * 60) + (first_step.delay_hours * 60)
        next_send = datetime.now() + timedelta(minutes=delay_minutes)

        assigned_count = 0
        for lead_id in request.lead_ids:
            # Check if already assigned
            existing = await db.execute(text("""
                SELECT id FROM lead_campaign_assignments
                WHERE lead_id = :lead_id AND campaign_id = :campaign_id AND status = 'active'
            """), {"lead_id": lead_id, "campaign_id": campaign_id})

            if existing.fetchone():
                continue

            await db.execute(text("""
                INSERT INTO lead_campaign_assignments (
                    lead_id, campaign_id, current_step, status, started_at, next_send_at
                ) VALUES (
                    :lead_id, :campaign_id, 1, 'active', CURRENT_TIMESTAMP, :next_send
                )
            """), {
                "lead_id": lead_id,
                "campaign_id": campaign_id,
                "next_send": next_send
            })
            assigned_count += 1

        await db.commit()

        return {
            "success": True,
            "assigned": assigned_count,
            "message": f"{assigned_count} leads assigned to campaign"
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error assigning leads: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Trigger Endpoints
# ============================================================================

@router.get("/triggers")
async def get_triggers(
    is_active: Optional[bool] = None,
    trigger_type: Optional[TriggerType] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """Get all triggers"""
    try:
        query = "SELECT * FROM outreach_triggers WHERE 1=1"
        params = {}

        if is_active is not None:
            query += " AND is_active = :is_active"
            params["is_active"] = is_active

        if trigger_type:
            query += " AND trigger_type = :trigger_type"
            params["trigger_type"] = trigger_type.value

        query += " ORDER BY created_at DESC"

        result = await db.execute(text(query), params)
        triggers = [dict(row._mapping) for row in result.fetchall()]

        return {"triggers": triggers}
    except SQLAlchemyError as e:
        logger.error(f"Error fetching triggers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/triggers")
async def create_trigger(
    trigger: TriggerCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new outreach trigger"""
    try:
        config_json = json.dumps(trigger.trigger_config) if trigger.trigger_config else None

        result = await db.execute(text("""
            INSERT INTO outreach_triggers (
                name, trigger_type, trigger_config, channel, subject, message,
                is_active, created_at
            ) VALUES (
                :name, :trigger_type, :trigger_config, :channel, :subject, :message,
                :is_active, CURRENT_TIMESTAMP
            )
        """), {
            "name": trigger.name,
            "trigger_type": trigger.trigger_type.value,
            "trigger_config": config_json,
            "channel": trigger.channel.value,
            "subject": trigger.subject,
            "message": trigger.message,
            "is_active": trigger.is_active
        })

        await db.commit()

        return {
            "success": True,
            "trigger_id": result.lastrowid,
            "message": f"Trigger '{trigger.name}' created"
        }
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating trigger: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: int,
    trigger: TriggerCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """Update a trigger"""
    try:
        config_json = json.dumps(trigger.trigger_config) if trigger.trigger_config else None

        await db.execute(text("""
            UPDATE outreach_triggers SET
                name = :name,
                trigger_type = :trigger_type,
                trigger_config = :trigger_config,
                channel = :channel,
                subject = :subject,
                message = :message,
                is_active = :is_active,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {
            "id": trigger_id,
            "name": trigger.name,
            "trigger_type": trigger.trigger_type.value,
            "trigger_config": config_json,
            "channel": trigger.channel.value,
            "subject": trigger.subject,
            "message": trigger.message,
            "is_active": trigger.is_active
        })

        await db.commit()

        return {"success": True, "message": "Trigger updated"}
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a trigger"""
    try:
        await db.execute(text("DELETE FROM outreach_triggers WHERE id = :id"), {"id": trigger_id})
        await db.commit()
        return {"success": True, "message": "Trigger deleted"}
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Default Triggers Setup
# ============================================================================

DEFAULT_TRIGGERS = [
    {
        "name": "Welcome New Lead",
        "trigger_type": "new_lead",
        "channel": "sms",
        "message": "Hi {first_name}! Thanks for your interest. I'm Sarah from Perennia AI. Are you looking to buy a new home or refinance? Reply to chat!"
    },
    {
        "name": "Welcome Email - New Lead",
        "trigger_type": "new_lead",
        "channel": "email",
        "subject": "Welcome! Let's find your perfect mortgage",
        "message": """Hi {first_name},

Thank you for reaching out! I'm Sarah, your AI mortgage assistant at Perennia AI.

I'm here to help you find the best mortgage options. Whether you're buying your first home, upgrading, or refinancing - I can guide you through the process.

Just reply to this email with any questions, and I'll get back to you right away.

Looking forward to helping you!

Sarah
AI Mortgage Assistant | Perennia AI"""
    },
    {
        "name": "Follow-up - No Response (7 days)",
        "trigger_type": "no_activity",
        "trigger_config": {"days": 7},
        "channel": "sms",
        "message": "Hi {first_name}, just checking in! Still interested in exploring mortgage options? I'm here whenever you're ready. Reply anytime!"
    },
    {
        "name": "Appointment Confirmation",
        "trigger_type": "appointment_booked",
        "channel": "sms",
        "message": "Hi {first_name}! Your appointment is confirmed. Looking forward to speaking with you soon! Reply if you have any questions."
    },
    # Nurture Status Triggers
    {
        "name": "Nurture Follow-up - Email",
        "trigger_type": "lead_status_change",
        "trigger_config": {"new_status": "nurture"},
        "channel": "email",
        "subject": "Keeping in touch - Your mortgage journey",
        "message": """Hi {first_name},

I wanted to check in and see how things are going! I know timing is everything when it comes to buying a home or refinancing.

Even if you're not ready right now, I'm here to help when the time is right. Here are a few things I can help with:

- Current rate information
- Pre-qualification (no impact to your credit)
- Answering any mortgage questions

Feel free to reply anytime - I'm always happy to help!

Sarah
AI Mortgage Assistant | Perennia AI"""
    },
    {
        "name": "Nurture Follow-up - SMS",
        "trigger_type": "lead_status_change",
        "trigger_config": {"new_status": "nurture"},
        "channel": "sms",
        "message": "Hi {first_name}! Just wanted to check in. Still thinking about your mortgage options? I'm here whenever you're ready - no pressure! Feel free to text back anytime."
    },
    # Loan Status Change Notifications
    {
        "name": "Loan Status - Application Received",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "application"},
        "channel": "email",
        "subject": "Application Received - Next Steps",
        "message": """Hi {first_name},

Great news! We've received your loan application. Here's what happens next:

1. Our team will review your documents
2. We'll reach out if we need any additional information
3. You'll receive updates as your loan progresses

Your loan officer will be in touch soon with more details.

Thank you for choosing us!

Perennia AI Team"""
    },
    {
        "name": "Loan Status - In Processing",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "processing"},
        "channel": "email",
        "subject": "Your Loan is Now in Processing",
        "message": """Hi {first_name},

Your loan is now in processing! This is an exciting step forward.

During this phase, we're:
- Verifying your documentation
- Ordering the appraisal
- Running title searches

We'll keep you updated on any developments. If we need anything from you, we'll reach out right away.

Perennia AI Team"""
    },
    {
        "name": "Loan Status - Submitted to Underwriting",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "submitted"},
        "channel": "email",
        "subject": "Your Loan Has Been Submitted to Underwriting",
        "message": """Hi {first_name},

Great progress! Your loan has been submitted to underwriting for review.

The underwriter will review all your documentation and make a decision. This typically takes a few business days.

We'll notify you immediately once we have an update.

Perennia AI Team"""
    },
    {
        "name": "Loan Status - Approved",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "approved"},
        "channel": "email",
        "subject": "Congratulations! Your Loan is Approved!",
        "message": """Hi {first_name},

CONGRATULATIONS! Your loan has been APPROVED!

This is fantastic news! Here's what's next:
1. We'll finalize the closing date
2. You'll receive your Closing Disclosure
3. We'll schedule the closing

Your loan officer will be in touch with specific details soon.

Congratulations again on this exciting milestone!

Perennia AI Team"""
    },
    {
        "name": "Loan Status - Approved SMS",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "approved"},
        "channel": "sms",
        "message": "Congratulations {first_name}! Your loan has been APPROVED! Your loan officer will be in touch soon with next steps."
    },
    {
        "name": "Loan Status - Clear to Close",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "clear_to_close"},
        "channel": "email",
        "subject": "Clear to Close - Almost There!",
        "message": """Hi {first_name},

Exciting news! You're CLEAR TO CLOSE!

This means all conditions have been satisfied and we can schedule your closing. Your loan officer or closing coordinator will reach out to finalize the date and time.

You're almost at the finish line!

Perennia AI Team"""
    },
    {
        "name": "Loan Status - Funded",
        "trigger_type": "loan_status_change",
        "trigger_config": {"new_status": "funded"},
        "channel": "email",
        "subject": "Congratulations! Your Loan Has Funded!",
        "message": """Hi {first_name},

Your loan has officially FUNDED! Congratulations!

Thank you for trusting us with this important milestone. If you have any questions going forward, please don't hesitate to reach out.

We wish you all the best in your new home!

Perennia AI Team"""
    }
]


@router.post("/triggers/setup-defaults")
async def setup_default_triggers(
    db: AsyncSession = Depends(get_async_db)
):
    """Set up default triggers"""
    try:
        created = 0
        for trigger_data in DEFAULT_TRIGGERS:
            # Check if exists
            existing = await db.execute(text("""
                SELECT id FROM outreach_triggers
                WHERE name = :name
            """), {"name": trigger_data["name"]})

            if existing.fetchone():
                continue

            config_json = json.dumps(trigger_data.get("trigger_config")) if trigger_data.get("trigger_config") else None

            await db.execute(text("""
                INSERT INTO outreach_triggers (
                    name, trigger_type, trigger_config, channel, subject, message,
                    is_active, created_at
                ) VALUES (
                    :name, :trigger_type, :trigger_config, :channel, :subject, :message,
                    1, CURRENT_TIMESTAMP
                )
            """), {
                "name": trigger_data["name"],
                "trigger_type": trigger_data["trigger_type"],
                "trigger_config": config_json,
                "channel": trigger_data["channel"],
                "subject": trigger_data.get("subject"),
                "message": trigger_data["message"]
            })
            created += 1

        await db.commit()

        return {
            "success": True,
            "created": created,
            "message": f"Created {created} default triggers"
        }
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error setting up defaults: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Trigger Execution
# ============================================================================

async def execute_trigger(
    trigger_type: TriggerType,
    lead_id: int = None,
    loan_id: int = None,
    context: dict = None,
    db: Session = None
):
    """Execute matching triggers for an event"""
    try:
        from services.notification_service import notification_service

        # Get active triggers of this type
        result = db.execute(text("""
            SELECT * FROM outreach_triggers
            WHERE trigger_type = :trigger_type AND is_active = true
        """), {"trigger_type": trigger_type.value})

        triggers = [dict(row._mapping) for row in result.fetchall()]

        if not triggers:
            return {"executed": 0}

        # Get contact info based on lead or loan
        first_name = "there"
        email = None
        phone = None

        trigger_user_id = None

        if lead_id:
            lead_result = db.execute(text("""
                SELECT first_name, last_name, email, phone, owner_id FROM leads WHERE id = :id
            """), {"id": lead_id})
            lead = lead_result.fetchone()
            if lead:
                first_name = lead.first_name or "there"
                email = lead.email
                phone = lead.phone
                trigger_user_id = lead.owner_id

        if loan_id:
            # Get borrower info from loan
            loan_result = db.execute(text("""
                SELECT borrower_name, borrower_email, borrower_phone, loan_officer_id FROM loans WHERE id = :id
            """), {"id": loan_id})
            loan = loan_result.fetchone()
            if loan:
                first_name = (loan.borrower_name or "").split()[0] if loan.borrower_name else "there"
                email = loan.borrower_email or email
                phone = loan.borrower_phone or phone
                trigger_user_id = trigger_user_id or loan.loan_officer_id

        # Override with context if provided
        if context:
            first_name = context.get("first_name", first_name)
            email = context.get("email", email)
            phone = context.get("phone", phone)

        if not email and not phone:
            return {"executed": 0, "error": "No contact info available"}

        executed = 0
        new_status = context.get("new_status") if context else None
        old_status = context.get("old_status") if context else None

        for trigger in triggers:
            try:
                # Check if trigger config matches the status change
                if trigger.get("trigger_config"):
                    try:
                        config = json.loads(trigger["trigger_config"]) if isinstance(trigger["trigger_config"], str) else trigger["trigger_config"]

                        # Check new_status filter
                        if "new_status" in config and new_status:
                            if config["new_status"].lower() != new_status.lower():
                                continue  # Skip this trigger, status doesn't match

                        # Check old_status filter (optional)
                        if "old_status" in config and old_status:
                            if config["old_status"].lower() != old_status.lower():
                                continue
                    except (json.JSONDecodeError, TypeError):
                        pass  # No valid config, execute anyway

                # Personalize message
                message = trigger["message"].replace("{first_name}", first_name)
                subject = trigger.get("subject", "").replace("{first_name}", first_name) if trigger.get("subject") else None

                # Send based on channel
                if trigger["channel"] == "email" and email:
                    from email_service import email_service
                    import os
                    ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

                    html_body = f"""<!DOCTYPE html>
<html><body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt;">
{message.replace(chr(10), '<br>')}
</body></html>"""

                    await email_service.send_html_email_sf(
                        to_email=email,
                        subject=subject or "Message from Perennia AI",
                        html_body=html_body,
                        plain_text_body=message,
                        from_email=ai_from_email,
                        reply_to=ai_from_email,
                        db=db,
                        user_id=trigger_user_id,
                    )
                    executed += 1
                    logger.info(f"Trigger {trigger['id']} sent email to {email}")

                elif trigger["channel"] == "sms" and phone:
                    notification_service.send_sms(to_phone=phone, message=message)
                    executed += 1
                    logger.info(f"Trigger {trigger['id']} sent SMS to {phone}")

                # Log execution
                db.execute(text("""
                    INSERT INTO trigger_execution_log (
                        trigger_id, lead_id, loan_id, channel, recipient, message, status, executed_at
                    ) VALUES (
                        :trigger_id, :lead_id, :loan_id, :channel, :recipient, :message, 'sent', CURRENT_TIMESTAMP
                    )
                """), {
                    "trigger_id": trigger["id"],
                    "lead_id": lead_id,
                    "loan_id": loan_id,
                    "channel": trigger["channel"],
                    "recipient": email if trigger["channel"] == "email" else phone,
                    "message": message
                })

            except SQLAlchemyError as e:
                logger.error(f"Error executing trigger {trigger['id']}: {e}")

        db.commit()
        return {"executed": executed}

    except SQLAlchemyError as e:
        logger.error(f"Error in execute_trigger: {e}")
        return {"executed": 0, "error": "Internal server error"}
