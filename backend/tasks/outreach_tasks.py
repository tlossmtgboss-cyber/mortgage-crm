"""
Outreach Tasks
Scheduled jobs for processing drip campaigns and no-activity triggers
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def process_drip_campaigns(db_session):
    """Process scheduled drip campaign messages"""
    try:
        from services.notification_service import notification_service
        from email_service import email_service

        # Get assignments that are due
        result = db_session.execute(text("""
            SELECT
                lca.id as assignment_id,
                lca.lead_id,
                lca.campaign_id,
                lca.current_step,
                cs.channel,
                cs.subject,
                cs.message,
                cs.delay_days,
                cs.delay_hours,
                l.first_name,
                l.email,
                l.phone,
                l.owner_id,
                oc.name as campaign_name
            FROM lead_campaign_assignments lca
            JOIN campaign_steps cs ON cs.campaign_id = lca.campaign_id
                AND cs.step_order = lca.current_step
            JOIN leads l ON l.id = lca.lead_id
            JOIN outreach_campaigns oc ON oc.id = lca.campaign_id
            WHERE lca.status = 'active'
                AND lca.next_send_at <= CURRENT_TIMESTAMP
                AND oc.status = 'active'
        """))

        assignments = [dict(row._mapping) for row in result.fetchall()]

        if not assignments:
            logger.debug("No drip campaign messages to send")
            return {"processed": 0}

        processed = 0
        errors = 0

        for assignment in assignments:
            try:
                first_name = assignment["first_name"] or "there"
                message = assignment["message"].replace("{first_name}", first_name)
                subject = assignment["subject"]
                if subject:
                    subject = subject.replace("{first_name}", first_name)

                # Send based on channel
                success = False
                if assignment["channel"] == "email" and assignment["email"]:
                    import os
                    try:
                        from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _fallback_email
                    except ImportError:
                        _fallback_email = "sarah@reply.perenniaai.com"
                    ai_from_email = os.getenv("AI_FROM_EMAIL", _fallback_email)
                    html_body = f"""<!DOCTYPE html>
<html><body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt;">
{message.replace(chr(10), '<br>')}
</body></html>"""

                    success = await email_service.send_html_email_sf(
                        to_email=assignment["email"],
                        subject=subject or "Message from Perennia AI",
                        html_body=html_body,
                        plain_text_body=message,
                        from_email=ai_from_email,
                        reply_to=ai_from_email,
                        db=db_session,
                        user_id=assignment.get("owner_id"),
                    )

                elif assignment["channel"] == "sms" and assignment["phone"]:
                    result = notification_service.send_sms(
                        to_phone=assignment["phone"],
                        message=message
                    )
                    success = result and result.get("success", False)

                if success:
                    # Get next step
                    next_step_result = db_session.execute(text("""
                        SELECT step_order, delay_days, delay_hours FROM campaign_steps
                        WHERE campaign_id = :campaign_id AND step_order > :current_step
                        ORDER BY step_order LIMIT 1
                    """), {
                        "campaign_id": assignment["campaign_id"],
                        "current_step": assignment["current_step"]
                    })
                    next_step = next_step_result.fetchone()

                    if next_step:
                        # Schedule next step
                        delay_minutes = (next_step.delay_days * 24 * 60) + (next_step.delay_hours * 60)
                        next_send = datetime.now() + timedelta(minutes=delay_minutes)

                        db_session.execute(text("""
                            UPDATE lead_campaign_assignments
                            SET current_step = :next_step, next_send_at = :next_send
                            WHERE id = :id
                        """), {
                            "id": assignment["assignment_id"],
                            "next_step": next_step.step_order,
                            "next_send": next_send
                        })
                    else:
                        # Campaign completed for this lead
                        db_session.execute(text("""
                            UPDATE lead_campaign_assignments
                            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                        """), {"id": assignment["assignment_id"]})

                    processed += 1
                else:
                    errors += 1

            except Exception as e:
                logger.error(f"Error processing campaign for lead {assignment['lead_id']}: {e}")
                errors += 1

        db_session.commit()

        logger.info(f"Drip campaigns: {processed} messages sent, {errors} errors")
        return {"processed": processed, "errors": errors}

    except Exception as e:
        logger.error(f"Error in process_drip_campaigns: {e}")
        return {"processed": 0, "error": "Internal server error"}


async def process_no_activity_triggers(db_session):
    """Check for leads with no activity and trigger follow-ups"""
    try:
        from routes.automated_outreach_routes import execute_trigger, TriggerType

        # Get no_activity triggers
        result = db_session.execute(text("""
            SELECT * FROM outreach_triggers
            WHERE trigger_type = 'no_activity' AND is_active = TRUE
        """))
        triggers = [dict(row._mapping) for row in result.fetchall()]

        if not triggers:
            return {"processed": 0}

        processed = 0
        for trigger in triggers:
            try:
                import json
                config = json.loads(trigger["trigger_config"]) if trigger["trigger_config"] else {}
                days_threshold = config.get("days", 7)

                # Find leads with no activity in X days
                # Exclude leads already contacted by this trigger recently
                inactive_result = db_session.execute(text("""
                    SELECT l.id, l.first_name, l.email, l.phone
                    FROM leads l
                    WHERE l.stage NOT IN ('converted', 'closed', 'dead')
                    AND l.updated_at < CURRENT_TIMESTAMP - CAST(:days_ago AS INTEGER) * INTERVAL '1 day'
                    AND l.id NOT IN (
                        SELECT DISTINCT lead_id FROM trigger_execution_log
                        WHERE trigger_id = :trigger_id
                        AND executed_at > CURRENT_TIMESTAMP - CAST(:cooldown AS INTEGER) * INTERVAL '1 day'
                    )
                    LIMIT 50
                """), {
                    "days_ago": days_threshold,
                    "trigger_id": trigger["id"],
                    "cooldown": days_threshold
                })

                inactive_leads = inactive_result.fetchall()

                for lead in inactive_leads:
                    await execute_trigger(
                        trigger_type=TriggerType.NO_ACTIVITY,
                        lead_id=lead.id,
                        db=db_session
                    )
                    processed += 1

            except Exception as e:
                logger.error(f"Error processing no_activity trigger {trigger['id']}: {e}")

        logger.info(f"No-activity triggers: {processed} follow-ups sent")
        return {"processed": processed}

    except Exception as e:
        logger.error(f"Error in process_no_activity_triggers: {e}")
        return {"processed": 0, "error": "Internal server error"}


def setup_outreach_scheduler(scheduler, SessionLocal):
    """Set up scheduler jobs for outreach.

    Uses tenant-scoped sessions per-org to enforce RLS.
    """

    def run_drip_campaigns():
        """Wrapper to run drip campaigns with tenant-scoped DB sessions, per org."""
        import asyncio
        from database import get_db_with_tenant
        from sqlalchemy import text as sa_text

        # Get org list with un-scoped session
        db = SessionLocal()
        try:
            org_ids = [
                row[0] for row in
                db.execute(sa_text(
                    "SELECT id FROM organizations WHERE is_active = true ORDER BY id"
                )).fetchall()
            ]
        finally:
            db.close()

        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    asyncio.run(process_drip_campaigns(tenant_db))
            except Exception as e:
                logger.error("Drip campaigns failed for org_id=%d: %s", org_id, e)

    def run_no_activity_triggers():
        """Wrapper to run no-activity triggers with tenant-scoped DB sessions, per org."""
        import asyncio
        from database import get_db_with_tenant
        from sqlalchemy import text as sa_text

        # Get org list with un-scoped session
        db = SessionLocal()
        try:
            org_ids = [
                row[0] for row in
                db.execute(sa_text(
                    "SELECT id FROM organizations WHERE is_active = true ORDER BY id"
                )).fetchall()
            ]
        finally:
            db.close()

        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    asyncio.run(process_no_activity_triggers(tenant_db))
            except Exception as e:
                logger.error("No-activity triggers failed for org_id=%d: %s", org_id, e)

    # Process drip campaigns every 15 minutes
    scheduler.add_job(
        run_drip_campaigns,
        'interval',
        minutes=15,
        id='process_drip_campaigns',
        name='Process Drip Campaign Messages',
        replace_existing=True
    )

    # Check no-activity triggers once per day
    scheduler.add_job(
        run_no_activity_triggers,
        'cron',
        hour=9,  # Run at 9 AM
        id='process_no_activity_triggers',
        name='Process No-Activity Follow-up Triggers',
        replace_existing=True
    )

    logger.info("Outreach scheduler jobs configured")
