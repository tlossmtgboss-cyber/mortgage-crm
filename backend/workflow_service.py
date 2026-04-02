"""
Perennia AI - Active Loan Workflow Engine (LEGACY)

DEPRECATED: This module is superseded by the SLA-driven workflow system:
  - services/workflow_sla_service.py (enrollment & lifecycle)
  - services/workflow_task_generator.py (task creation)
  - services/workflow_scheduler.py (scheduling & escalation)
  - workflows/lead_workflow_engine.py (lead status change automation)

This module is retained for backward compatibility with existing
ThemeDayService, LastMileService, and PostClosingService consumers.
The WorkflowEngine class should not be used for new integrations.
"""

import warnings
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
import logging
import json

logger = logging.getLogger(__name__)

warnings.warn(
    "workflow_service.WorkflowEngine is deprecated. Use services/workflow_sla_service.py "
    "and services/workflow_task_generator.py instead.",
    DeprecationWarning,
    stacklevel=2,
)


class WorkflowEngine:
    """Core workflow automation engine"""

    @staticmethod
    def evaluate_loan_workflows(db: Session, loan_id: int) -> Dict[str, Any]:
        """Evaluate all workflow rules for a loan and create tasks/alerts"""
        results = {"tasks_created": 0, "alerts_created": 0, "rules_processed": 0}

        try:
            # Get loan details
            loan = db.execute(text("""
                SELECT id, lead_id, loan_stage, loan_amount, estimated_closing_date,
                       appraisal_ordered_date, appraisal_received_date,
                       title_ordered_date, title_received_date,
                       survey_ordered_date, survey_received_date,
                       hoi_ordered_date, hoi_received_date,
                       conditions_sent_date, conditions_received_date,
                       closing_disclosure_sent_date, clear_to_close_date
                FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return {"error": "Loan not found"}

            # Get active workflow rules (table may not exist in newer deployments)
            try:
                rules = db.execute(text("""
                    SELECT id, rule_name, trigger_type, trigger_config,
                           action_type, action_config, priority
                    FROM workflow_rules
                    WHERE is_active = TRUE
                    ORDER BY priority DESC
                """)).fetchall()
            except Exception as e:
                logger.info(f"workflow_rules table not available (expected in new deployments): {e}")
                return results

            for rule in rules:
                rule_id, name, trigger_type, trigger_config, action_type, action_config, priority = rule

                # Evaluate trigger
                should_fire = WorkflowEngine._evaluate_trigger(
                    loan, trigger_type, trigger_config
                )

                if should_fire:
                    # Check if already executed recently
                    existing = db.execute(text("""
                        SELECT id FROM workflow_execution_log
                        WHERE loan_id = :loan_id AND rule_id = :rule_id
                        AND executed_at > NOW() - INTERVAL '24 hours'
                    """), {"loan_id": loan_id, "rule_id": rule_id}).fetchone()

                    if not existing:
                        # Execute action
                        try:
                            if action_type == 'create_task':
                                WorkflowEngine._create_workflow_task(
                                    db, loan_id, loan[1], rule_id, action_config
                                )
                                results["tasks_created"] += 1
                            elif action_type == 'create_alert':
                                WorkflowEngine._create_workflow_alert(
                                    db, loan_id, loan[1], rule_id, action_config
                                )
                                results["alerts_created"] += 1

                            # Log execution
                            db.execute(text("""
                                INSERT INTO workflow_execution_log
                                (rule_id, loan_id, lead_id, trigger_data, result_data)
                                VALUES (:rule_id, :loan_id, :lead_id, :trigger, :result)
                            """), {
                                "rule_id": rule_id,
                                "loan_id": loan_id,
                                "lead_id": loan[1],
                                "trigger": json.dumps({"type": trigger_type}),
                                "result": json.dumps({"action": action_type})
                            })
                        except Exception as e:
                            logger.warning(f"Legacy workflow action failed for rule {rule_id}: {e}")

                results["rules_processed"] += 1

            db.commit()
            return results

        except Exception as e:
            logger.error(f"Workflow evaluation error: {e}")
            db.rollback()
            return {"error": "Internal server error"}

    @staticmethod
    def _evaluate_trigger(loan, trigger_type: str, config: Dict) -> bool:
        """Evaluate if a trigger condition is met"""
        try:
            if trigger_type == 'stage_entered':
                return loan[2] == config.get('stage')

            elif trigger_type == 'days_in_stage':
                # Would need stage_entered_date tracking
                return False

            elif trigger_type == 'date_approaching':
                field = config.get('date_field')
                days_before = config.get('days_before', 7)

                # Map field names to loan tuple indices
                date_fields = {
                    'estimated_closing_date': 4,
                    'appraisal_ordered_date': 5,
                    'title_ordered_date': 7,
                }

                if field in date_fields:
                    loan_date = loan[date_fields[field]]
                    if loan_date:
                        target = loan_date - timedelta(days=days_before)
                        return date.today() >= target.date() if hasattr(target, 'date') else date.today() >= target

            elif trigger_type == 'missing_document':
                # Check if required date field is null
                field = config.get('document_field')
                date_fields = {
                    'appraisal_received_date': 6,
                    'title_received_date': 8,
                    'survey_received_date': 10,
                    'hoi_received_date': 12,
                }
                if field in date_fields:
                    return loan[date_fields[field]] is None

            return False

        except Exception as e:
            logger.error(f"Trigger evaluation error: {e}")
            return False

    @staticmethod
    def _create_workflow_task(db: Session, loan_id: int, lead_id: int,
                              rule_id, config: Dict):
        """Create a task from workflow rule"""
        due_date = datetime.now(timezone.utc) + timedelta(days=config.get('due_in_days', 1))

        db.execute(text("""
            INSERT INTO workflow_tasks
            (loan_id, lead_id, rule_id, task_type, title, description,
             priority, due_date, status)
            VALUES (:loan_id, :lead_id, :rule_id, :task_type, :title, :desc,
                    :priority, :due_date, 'pending')
        """), {
            "loan_id": loan_id,
            "lead_id": lead_id,
            "rule_id": rule_id,
            "task_type": config.get('task_type', 'general'),
            "title": config.get('title', 'Workflow Task'),
            "desc": config.get('description', ''),
            "priority": config.get('priority', 'normal'),
            "due_date": due_date
        })

    @staticmethod
    def _create_workflow_alert(db: Session, loan_id: int, lead_id: int,
                               rule_id, config: Dict):
        """Create an alert from workflow rule"""
        db.execute(text("""
            INSERT INTO workflow_alerts
            (loan_id, lead_id, rule_id, alert_type, message, severity)
            VALUES (:loan_id, :lead_id, :rule_id, :alert_type, :message, :severity)
        """), {
            "loan_id": loan_id,
            "lead_id": lead_id,
            "rule_id": rule_id,
            "alert_type": config.get('alert_type', 'general'),
            "message": config.get('message', 'Workflow Alert'),
            "severity": config.get('severity', 'medium')
        })


class ThemeDayService:
    """Manages weekly theme day communications"""

    THEME_DAYS = {
        'monday': {'name': 'Motivation Monday', 'focus': 'inspiration'},
        'tuesday': {'name': 'Tip Tuesday', 'focus': 'education'},
        'wednesday': {'name': 'Wisdom Wednesday', 'focus': 'advice'},
        'thursday': {'name': 'Thankful Thursday', 'focus': 'gratitude'},
        'friday': {'name': 'Fun Fact Friday', 'focus': 'entertainment'}
    }

    @staticmethod
    def get_today_theme() -> Dict[str, Any]:
        """Get today's theme configuration"""
        day_name = date.today().strftime('%A').lower()
        return ThemeDayService.THEME_DAYS.get(day_name, {
            'name': f'{day_name.title()} Update',
            'focus': 'general'
        })

    @staticmethod
    def schedule_theme_messages(db: Session, organization_id: int = 1) -> Dict[str, Any]:
        """Schedule theme day messages for all active loans"""
        results = {"scheduled": 0, "skipped": 0}

        try:
            theme = ThemeDayService.get_today_theme()
            today = date.today()

            # Get all active loans with borrower contact info
            loans = db.execute(text("""
                SELECT l.id, l.lead_id, le.first_name, le.email, le.phone,
                       l.loan_stage, l.estimated_closing_date
                FROM loans l
                JOIN leads le ON l.lead_id = le.id
                WHERE l.loan_stage IN ('processing', 'underwriting',
                    'conditional_approval', 'clear_to_close', 'closing')
                AND le.organization_id = :org_id
            """), {"org_id": organization_id}).fetchall()

            for loan in loans:
                loan_id, lead_id, first_name, email, phone, stage, closing_date = loan

                # Check if already scheduled today
                existing = db.execute(text("""
                    SELECT id FROM theme_day_schedule
                    WHERE loan_id = :loan_id AND scheduled_date = :today
                """), {"loan_id": loan_id, "today": today}).fetchone()

                if existing:
                    results["skipped"] += 1
                    continue

                # Generate personalized message
                message = ThemeDayService._generate_theme_message(
                    theme, first_name, stage, closing_date
                )

                # Schedule the message
                db.execute(text("""
                    INSERT INTO theme_day_schedule
                    (loan_id, lead_id, theme_name, scheduled_date,
                     message_content, channel)
                    VALUES (:loan_id, :lead_id, :theme, :date, :message, :channel)
                """), {
                    "loan_id": loan_id,
                    "lead_id": lead_id,
                    "theme": theme['name'],
                    "date": today,
                    "message": message,
                    "channel": "email" if email else "sms"
                })

                results["scheduled"] += 1

            db.commit()
            return results

        except Exception as e:
            logger.error(f"Theme scheduling error: {e}")
            db.rollback()
            return {"error": "Internal server error"}

    @staticmethod
    def _generate_theme_message(theme: Dict, first_name: str,
                                stage: str, closing_date) -> str:
        """Generate a theme-appropriate message"""
        focus = theme.get('focus', 'general')

        if focus == 'inspiration':
            return f"Happy {theme['name']}, {first_name}! Your loan is progressing well in {stage}. Stay positive - homeownership is within reach!"
        elif focus == 'education':
            return f"{theme['name']}, {first_name}! Here's a tip: Keep all your financial documents organized and avoid major purchases until closing."
        elif focus == 'advice':
            return f"{theme['name']}, {first_name}! Remember: Respond promptly to any lender requests to keep your loan on track."
        elif focus == 'gratitude':
            return f"{theme['name']}, {first_name}! Thank you for trusting us with your home loan journey. We're here for you every step of the way!"
        elif focus == 'entertainment':
            return f"{theme['name']}, {first_name}! Did you know the average American moves 11.7 times in their lifetime? Your new home awaits!"
        else:
            return f"Hello {first_name}! Your loan is currently in {stage}. Contact us if you have any questions."


class LastMileService:
    """Manages the 7-day pre-closing coordination process"""

    LAST_MILE_SCHEDULE = [
        {'day': -7, 'task': 'Initial coordination call', 'parties': ['borrower', 'realtor']},
        {'day': -5, 'task': 'Document verification', 'parties': ['borrower']},
        {'day': -3, 'task': 'Final walkthrough reminder', 'parties': ['borrower', 'realtor']},
        {'day': -2, 'task': 'Wire instructions', 'parties': ['borrower']},
        {'day': -1, 'task': 'Closing confirmation', 'parties': ['borrower', 'realtor', 'title']},
        {'day': 0, 'task': 'Closing day support', 'parties': ['borrower']},
    ]

    @staticmethod
    def initialize_last_mile(db: Session, loan_id: int) -> Dict[str, Any]:
        """Initialize Last Mile process for a loan approaching closing"""
        try:
            # Get loan details
            loan = db.execute(text("""
                SELECT l.id, l.lead_id, l.estimated_closing_date,
                       le.first_name, le.email, le.phone
                FROM loans l
                JOIN leads le ON l.lead_id = le.id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return {"error": "Loan not found"}

            loan_id, lead_id, closing_date, first_name, email, phone = loan

            if not closing_date:
                return {"error": "No closing date set"}

            # Create Last Mile tasks
            tasks_created = 0
            for item in LastMileService.LAST_MILE_SCHEDULE:
                task_date = closing_date + timedelta(days=item['day'])

                db.execute(text("""
                    INSERT INTO last_mile_tasks
                    (loan_id, lead_id, task_name, task_date, parties_involved, status)
                    VALUES (:loan_id, :lead_id, :task, :date, :parties, 'pending')
                """), {
                    "loan_id": loan_id,
                    "lead_id": lead_id,
                    "task": item['task'],
                    "date": task_date,
                    "parties": json.dumps(item['parties'])
                })
                tasks_created += 1

            db.commit()
            return {"success": True, "tasks_created": tasks_created}

        except Exception as e:
            logger.error(f"Last Mile init error: {e}")
            db.rollback()
            return {"error": "Internal server error"}

    @staticmethod
    def get_today_tasks(db: Session) -> List[Dict]:
        """Get all Last Mile tasks due today"""
        try:
            today = date.today()

            tasks = db.execute(text("""
                SELECT lmt.id, lmt.loan_id, lmt.lead_id, lmt.task_name,
                       lmt.parties_involved, le.first_name, le.phone, le.email
                FROM last_mile_tasks lmt
                JOIN leads le ON lmt.lead_id = le.id
                WHERE lmt.task_date = :today AND lmt.status = 'pending'
            """), {"today": today}).fetchall()

            return [{
                "task_id": str(t[0]),
                "loan_id": t[1],
                "lead_id": t[2],
                "task_name": t[3],
                "parties": t[4],
                "borrower_name": t[5],
                "phone": t[6],
                "email": t[7]
            } for t in tasks]

        except Exception as e:
            logger.error(f"Error getting today's tasks: {e}")
            return []

    @staticmethod
    def complete_task(db: Session, task_id: str, notes: str = None) -> Dict[str, Any]:
        """Mark a Last Mile task as completed"""
        try:
            db.execute(text("""
                UPDATE last_mile_tasks
                SET status = 'completed', completed_at = NOW(), notes = :notes
                WHERE id = :task_id
            """), {"task_id": task_id, "notes": notes})

            db.commit()
            return {"success": True}

        except Exception as e:
            logger.error(f"Task completion error: {e}")
            db.rollback()
            return {"error": "Internal server error"}


class PostClosingService:
    """Manages post-closing follow-up calls"""

    CALL_SCHEDULE = [
        {'days_after': 7, 'purpose': 'satisfaction_check'},
        {'days_after': 30, 'purpose': 'settlement_followup'},
        {'days_after': 90, 'purpose': 'referral_request'},
        {'days_after': 180, 'purpose': 'annual_review_reminder'},
    ]

    @staticmethod
    def schedule_post_closing_calls(db: Session, loan_id: int) -> Dict[str, Any]:
        """Schedule post-closing follow-up calls"""
        try:
            # Get loan with funding date
            loan = db.execute(text("""
                SELECT l.id, l.lead_id, l.funding_date
                FROM loans l WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan or not loan[2]:
                return {"error": "Loan not found or no funding date"}

            loan_id, lead_id, funding_date = loan

            calls_scheduled = 0
            for call in PostClosingService.CALL_SCHEDULE:
                call_date = funding_date + timedelta(days=call['days_after'])

                db.execute(text("""
                    INSERT INTO post_closing_calls
                    (loan_id, lead_id, call_purpose, scheduled_date, status)
                    VALUES (:loan_id, :lead_id, :purpose, :date, 'scheduled')
                """), {
                    "loan_id": loan_id,
                    "lead_id": lead_id,
                    "purpose": call['purpose'],
                    "date": call_date
                })
                calls_scheduled += 1

            db.commit()
            return {"success": True, "calls_scheduled": calls_scheduled}

        except Exception as e:
            logger.error(f"Post-closing scheduling error: {e}")
            db.rollback()
            return {"error": "Internal server error"}


class AIWorkflowAnalyzer:
    """AI-powered workflow analysis and recommendations"""

    @staticmethod
    def analyze_loan_risk(db: Session, loan_id: int) -> Dict[str, Any]:
        """Analyze loan for potential risks and delays"""
        try:
            # Get loan details
            loan = db.execute(text("""
                SELECT id, loan_stage, estimated_closing_date,
                       appraisal_received_date, title_received_date,
                       conditions_received_date, clear_to_close_date,
                       created_at
                FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return {"error": "Loan not found"}

            risks = []
            recommendations = []

            # Check closing date proximity
            if loan[2]:  # estimated_closing_date
                days_to_close = (loan[2] - date.today()).days if hasattr(loan[2], 'days') else (loan[2].date() - date.today()).days

                if days_to_close <= 7 and not loan[6]:  # No clear_to_close
                    risks.append({
                        "type": "closing_at_risk",
                        "severity": "high",
                        "message": f"Closing in {days_to_close} days but not yet clear to close"
                    })
                    recommendations.append("Expedite remaining conditions and underwriting")

            # Check missing documents
            if not loan[3]:  # appraisal_received_date
                risks.append({
                    "type": "missing_appraisal",
                    "severity": "medium",
                    "message": "Appraisal not yet received"
                })
                recommendations.append("Follow up on appraisal status")

            if not loan[4]:  # title_received_date
                risks.append({
                    "type": "missing_title",
                    "severity": "medium",
                    "message": "Title work not yet received"
                })
                recommendations.append("Contact title company for status update")

            # Calculate overall risk score
            risk_score = sum(10 if r['severity'] == 'high' else 5 for r in risks)

            # Store analysis
            db.execute(text("""
                INSERT INTO ai_analysis
                (loan_id, analysis_type, risk_score, findings, recommendations)
                VALUES (:loan_id, 'risk_assessment', :score, :findings, :recs)
            """), {
                "loan_id": loan_id,
                "score": risk_score,
                "findings": json.dumps(risks),
                "recs": json.dumps(recommendations)
            })
            db.commit()

            return {
                "loan_id": loan_id,
                "risk_score": risk_score,
                "risk_level": "high" if risk_score >= 15 else "medium" if risk_score >= 5 else "low",
                "risks": risks,
                "recommendations": recommendations
            }

        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            db.rollback()
            return {"error": "Internal server error"}

    @staticmethod
    def get_priority_loans(db: Session, organization_id: int = 1) -> List[Dict]:
        """Get loans requiring immediate attention"""
        try:
            # Find loans with upcoming closings or overdue tasks
            loans = db.execute(text("""
                SELECT DISTINCT l.id, l.loan_stage, l.estimated_closing_date,
                       le.first_name, le.last_name,
                       (SELECT COUNT(*) FROM workflow_tasks wt
                        WHERE wt.loan_id = l.id AND wt.status = 'pending'
                        AND wt.due_date < NOW()) as overdue_tasks
                FROM loans l
                JOIN leads le ON l.lead_id = le.id
                WHERE le.organization_id = :org_id
                AND l.loan_stage IN ('processing', 'underwriting',
                    'conditional_approval', 'clear_to_close', 'closing')
                AND (
                    l.estimated_closing_date <= NOW() + INTERVAL '7 days'
                    OR EXISTS (
                        SELECT 1 FROM workflow_tasks wt
                        WHERE wt.loan_id = l.id AND wt.status = 'pending'
                        AND wt.due_date < NOW()
                    )
                )
                ORDER BY l.estimated_closing_date ASC
                LIMIT 20
            """), {"org_id": organization_id}).fetchall()

            return [{
                "loan_id": l[0],
                "stage": l[1],
                "closing_date": l[2].isoformat() if l[2] else None,
                "borrower": f"{l[3]} {l[4]}",
                "overdue_tasks": l[5]
            } for l in loans]

        except Exception as e:
            logger.error(f"Priority loans error: {e}")
            return []
