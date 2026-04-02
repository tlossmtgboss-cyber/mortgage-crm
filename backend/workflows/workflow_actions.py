"""
Workflow Action Executor - Perennia AI
TL Development, LLC

Executes workflow actions: emails, SMS, tasks, alerts, drip campaigns
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json
import os

logger = logging.getLogger(__name__)


class WorkflowActionExecutor:
    """Executes workflow actions from the engine"""

    def __init__(self, db: Session):
        self.db = db
        self._init_services()

    def _init_services(self):
        """Initialize communication services"""
        try:
            from integrations.sms_service import get_sms_client
            self.sms_client = get_sms_client()
        except Exception as e:
            logger.warning(f"SMS client not available: {e}")
            self.sms_client = None

        try:
            from integrations.email_service import EmailService
            self.email_service = EmailService()
        except Exception as e:
            logger.warning(f"Email service not available: {e}")
            self.email_service = None

    async def execute_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute a list of workflow actions"""
        results = {
            "total": len(actions),
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }

        for action in actions:
            try:
                action_type = action.get("action_type")
                result = await self._execute_single_action(action)

                if result.get("success"):
                    results["successful"] += 1
                elif result.get("skipped"):
                    results["skipped"] += 1
                else:
                    results["failed"] += 1

                results["details"].append({
                    "action_type": action_type,
                    "result": result
                })

            except Exception as e:
                logger.error(f"Error executing action {action}: {e}")
                results["failed"] += 1
                results["details"].append({
                    "action_type": action.get("action_type"),
                    "result": {"success": False, "error": "Internal server error"}
                })

        return results

    async def _execute_single_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single workflow action"""
        action_type = action.get("action_type")
        data = action.get("data", {})

        if action_type == "sms":
            return await self._send_sms(data)
        elif action_type == "email":
            return await self._send_email(data)
        elif action_type == "task":
            return await self._create_task(data)
        elif action_type == "alert":
            return await self._create_alert(data)
        elif action_type == "drip":
            return await self._manage_drip(data)
        elif action_type == "activity":
            return await self._log_activity(data)
        elif action_type == "tag":
            return await self._add_tags(data)
        else:
            logger.warning(f"Unknown action type: {action_type}")
            return {"success": False, "error": f"Unknown action type: {action_type}"}

    async def _send_sms(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send SMS message"""
        if not self.sms_client or not self.sms_client.enabled:
            logger.info(f"SMS skipped (not configured): {data.get('message', '')[:50]}...")
            return {"success": True, "skipped": True, "reason": "SMS not configured"}

        try:
            to_number = data.get("to")
            message = data.get("message")

            if not to_number or not message:
                return {"success": False, "error": "Missing phone or message"}

            sid = await self.sms_client.send_sms(to_number, message)

            if sid:
                logger.info(f"SMS sent to {to_number}: {message[:50]}...")
                return {"success": True, "sid": sid}
            else:
                return {"success": False, "error": "SMS send failed"}

        except Exception as e:
            logger.error(f"SMS error: {e}")
            return {"success": False, "error": "Internal server error"}

    async def _send_email(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send email"""
        if not self.email_service:
            logger.info(f"Email skipped (not configured): {data.get('subject', '')}")
            return {"success": True, "skipped": True, "reason": "Email not configured"}

        try:
            to_email = data.get("to")
            subject = data.get("subject")
            template = data.get("template", "generic")

            if not to_email or not subject:
                return {"success": False, "error": "Missing email or subject"}

            # Generate email content based on template
            html_content = self._generate_email_html(template, data)

            # Send email
            result = self.email_service._send_email(to_email, subject, html_content)

            if result:
                logger.info(f"Email sent to {to_email}: {subject}")
                return {"success": True}
            else:
                return {"success": False, "error": "Email send failed"}

        except Exception as e:
            logger.error(f"Email error: {e}")
            return {"success": False, "error": "Internal server error"}

    def _generate_email_html(self, template: str, data: Dict[str, Any]) -> str:
        """Generate HTML email content based on template"""
        lead_name = data.get("lead_name", "there")
        first_name = lead_name.split()[0] if lead_name else "there"
        lo_name = data.get("loan_officer_name", "Your Loan Officer")

        templates = {
            "welcome_new_lead": f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #18a0a6;">Welcome to Perennia AI!</h2>
                <p>Hi {first_name},</p>
                <p>Thank you for reaching out about your mortgage needs! I'm {lo_name}, and I'll be your dedicated loan officer.</p>
                <p>I'll be in touch within the hour to discuss your goals and answer any questions.</p>
                <p>In the meantime, feel free to reply to this email with any questions.</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """,
            "great_connecting": f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #18a0a6;">Great Connecting with You!</h2>
                <p>Hi {first_name},</p>
                <p>It was great speaking with you today! I'm excited to help you with your mortgage journey.</p>
                <p>Based on our conversation, here's what we'll do next:</p>
                <ul>
                    <li>I'll send you some loan options to review</li>
                    <li>We'll gather some basic financial information</li>
                    <li>I'll provide a pre-qualification estimate</li>
                </ul>
                <p>Please don't hesitate to reach out if you have any questions.</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """,
            "application_started": f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #18a0a6;">Your Application Has Started! 📋</h2>
                <p>Hi {first_name},</p>
                <p>Great news! Your mortgage application is now in progress.</p>
                <p><strong>Next Steps:</strong></p>
                <ol>
                    <li>Upload your documents (paystubs, W2s, bank statements)</li>
                    <li>Complete any missing application sections</li>
                    <li>Review and sign disclosures</li>
                </ol>
                <p>I'll be monitoring your file and will reach out if anything is needed.</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """,
            "application_complete": f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #18a0a6;">Application Complete! ✅</h2>
                <p>Hi {first_name},</p>
                <p>Congratulations! Your mortgage application is complete and we're submitting it to underwriting.</p>
                <p><strong>What happens next:</strong></p>
                <ul>
                    <li>Underwriting review (3-5 business days)</li>
                    <li>You may receive requests for additional documentation</li>
                    <li>Conditional approval</li>
                    <li>Final approval and clear to close</li>
                </ul>
                <p>I'll keep you updated every step of the way!</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """,
            "pre_approved": f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #18a0a6;">🎉 Congratulations - You're Pre-Approved!</h2>
                <p>Hi {first_name},</p>
                <p>I'm thrilled to inform you that you've been <strong>PRE-APPROVED</strong> for your mortgage!</p>
                <p>Your pre-approval letter is attached to this email. You can use this when making offers on properties.</p>
                <p><strong>Next Steps:</strong></p>
                <ul>
                    <li>Share this letter with your real estate agent</li>
                    <li>Start or continue your property search with confidence</li>
                    <li>Contact me when you find a property</li>
                </ul>
                <p>This pre-approval is valid for 90 days. Let's find your dream home!</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """,
            "educational_resources": f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #18a0a6;">Your Mortgage Journey Resources</h2>
                <p>Hi {first_name},</p>
                <p>Here are some helpful resources as you navigate your mortgage journey:</p>
                <ul>
                    <li><strong>Understanding Loan Types</strong> - Fixed vs ARM, conventional vs FHA</li>
                    <li><strong>Credit Preparation</strong> - Tips to optimize your credit score</li>
                    <li><strong>Document Checklist</strong> - What you'll need for your application</li>
                    <li><strong>Timeline Guide</strong> - What to expect and when</li>
                </ul>
                <p>Questions? Just reply to this email!</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """
        }

        return templates.get(template, templates.get("welcome_new_lead"))

    async def _create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task for loan officer"""
        try:
            title = data.get("title")
            description = data.get("description", "")
            due_hours = data.get("due_hours", 24)
            priority = data.get("priority", "medium")
            lead_id = data.get("lead_id")
            assigned_to = data.get("assigned_to")

            if not title or not assigned_to:
                return {"success": False, "error": "Missing title or assigned_to"}

            due_date = datetime.now(timezone.utc) + timedelta(hours=due_hours)

            # Try to insert task into database
            try:
                result = self.db.execute(text("""
                    INSERT INTO tasks (title, description, due_date, priority, status, lead_id, assigned_to, created_at)
                    VALUES (:title, :description, :due_date, :priority, 'pending', :lead_id, :assigned_to, :created_at)
                    RETURNING id
                """), {
                    "title": title,
                    "description": description,
                    "due_date": due_date,
                    "priority": priority,
                    "lead_id": lead_id,
                    "assigned_to": assigned_to,
                    "created_at": datetime.now(timezone.utc)
                })

                task_id = result.fetchone()[0]
                self.db.commit()

                logger.info(f"Task created: {title} (ID: {task_id})")
                return {"success": True, "task_id": task_id}
            except Exception as table_error:
                self.db.rollback()
                # Table might not exist - log the task info instead
                logger.info(f"Task logged (table not available): {title} - {description}")
                return {"success": True, "skipped": True, "reason": f"Task table not available: {str(table_error)[:100]}"}

        except Exception as e:
            logger.error(f"Task creation error: {e}")
            self.db.rollback()
            return {"success": True, "skipped": True, "reason": str(e)}

    async def _create_alert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an alert/notification"""
        try:
            target = data.get("loan_officer_id") or data.get("user_id")
            message = data.get("message")
            lead_id = data.get("lead_id")
            priority = data.get("priority", "normal")

            if not message:
                return {"success": False, "error": "Missing message"}

            # Insert notification into database
            self.db.execute(text("""
                INSERT INTO notifications (user_id, message, type, priority, lead_id, read, created_at)
                VALUES (:user_id, :message, 'workflow_alert', :priority, :lead_id, false, :created_at)
            """), {
                "user_id": target,
                "message": message,
                "priority": priority,
                "lead_id": lead_id,
                "created_at": datetime.now(timezone.utc)
            })
            self.db.commit()

            logger.info(f"Alert created for user {target}: {message[:50]}...")
            return {"success": True}

        except Exception as e:
            logger.error(f"Alert creation error: {e}")
            self.db.rollback()
            # Don't fail the workflow if notifications table doesn't exist
            return {"success": True, "skipped": True, "reason": str(e)}

    async def _manage_drip(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Manage drip campaign enrollment"""
        try:
            lead_id = data.get("lead_id")
            campaign = data.get("campaign")
            stop_campaign = data.get("stop_campaign")

            # Stop previous campaign if specified
            if stop_campaign:
                self.db.execute(text("""
                    UPDATE drip_enrollments
                    SET status = 'stopped', stopped_at = :now
                    WHERE lead_id = :lead_id AND campaign_name = :campaign AND status = 'active'
                """), {
                    "lead_id": lead_id,
                    "campaign": stop_campaign,
                    "now": datetime.now(timezone.utc)
                })

            # Enroll in new campaign
            if campaign:
                self.db.execute(text("""
                    INSERT INTO drip_enrollments (lead_id, campaign_name, status, enrolled_at)
                    VALUES (:lead_id, :campaign, 'active', :now)
                    ON CONFLICT (lead_id, campaign_name) DO UPDATE SET status = 'active', enrolled_at = :now
                """), {
                    "lead_id": lead_id,
                    "campaign": campaign,
                    "now": datetime.now(timezone.utc)
                })

            self.db.commit()
            logger.info(f"Drip campaign updated for lead {lead_id}: {campaign}")
            return {"success": True}

        except Exception as e:
            logger.error(f"Drip management error: {e}")
            self.db.rollback()
            # Don't fail if drip tables don't exist
            return {"success": True, "skipped": True, "reason": str(e)}

    async def _log_activity(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Log activity to lead timeline"""
        try:
            lead_id = data.get("lead_id")
            activity_type = data.get("activity_type", "note")
            note = data.get("note", "")

            self.db.execute(text("""
                INSERT INTO lead_activities (lead_id, activity_type, note, created_at)
                VALUES (:lead_id, :activity_type, :note, :created_at)
            """), {
                "lead_id": lead_id,
                "activity_type": activity_type,
                "note": note,
                "created_at": datetime.now(timezone.utc)
            })
            self.db.commit()

            logger.info(f"Activity logged for lead {lead_id}: {note[:50]}...")
            return {"success": True}

        except Exception as e:
            logger.error(f"Activity logging error: {e}")
            self.db.rollback()
            return {"success": True, "skipped": True, "reason": str(e)}

    async def _add_tags(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add tags to a lead"""
        try:
            lead_id = data.get("lead_id")
            tags = data.get("tags", [])

            for tag in tags:
                self.db.execute(text("""
                    INSERT INTO lead_tags (lead_id, tag, created_at)
                    VALUES (:lead_id, :tag, :created_at)
                    ON CONFLICT (lead_id, tag) DO NOTHING
                """), {
                    "lead_id": lead_id,
                    "tag": tag,
                    "created_at": datetime.now(timezone.utc)
                })

            self.db.commit()
            logger.info(f"Tags added to lead {lead_id}: {tags}")
            return {"success": True}

        except Exception as e:
            logger.error(f"Tag addition error: {e}")
            self.db.rollback()
            return {"success": True, "skipped": True, "reason": str(e)}
