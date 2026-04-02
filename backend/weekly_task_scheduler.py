"""
Weekly Task Scheduler Service
Handles scheduling and execution of recurring weekly tasks like Monday updates.

Business Rules:
1. Monday Weekly Update: First update goes out on the Monday FOLLOWING the
   Disclosed date entry (not the same day if added on Monday)
2. Tasks repeat every week until loan is closed, canceled, withdrawn, or denied
3. Stakeholder emails exclude underwriter and closer

This service can be triggered by:
- External cron job calling the API endpoint
- Railway scheduled task
- Manual trigger from admin panel
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging

logger = logging.getLogger(__name__)

# Day of week constants (Python's weekday(): Monday=0, Sunday=6)
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

# Statuses that stop weekly recurring tasks
DEFAULT_STOP_STATUSES = ['closed', 'canceled', 'withdrawn', 'denied', 'funded']

# Roles excluded from stakeholder communications
EXCLUDED_STAKEHOLDER_ROLES = ['underwriter', 'closer']


class WeeklyTaskScheduler:
    """
    Manages weekly recurring tasks for loan workflows.
    """

    def __init__(self, db: Session, models: Dict[str, Any]):
        self.db = db
        self.models = models
        self.Loan = models.get('Loan')
        self.Task = models.get('Task')
        self.User = models.get('User')
        self.WorkflowConfiguration = models.get('WorkflowConfiguration')
        self.WorkflowDayConfig = models.get('WorkflowDayConfig')
        self.WorkflowTaskInstance = models.get('WorkflowTaskInstance')
        self.LoanTeamMember = models.get('LoanTeamMember')

    def get_next_occurrence(self, target_day: int, after_date: datetime) -> datetime:
        """
        Calculate the next occurrence of a specific day of the week AFTER the given date.

        Args:
            target_day: Day of week (0=Monday, 6=Sunday)
            after_date: The date after which to find the next occurrence

        Returns:
            The next occurrence date (always strictly after after_date)

        Example:
            - If after_date is Monday and target_day is Monday, returns NEXT Monday (7 days later)
            - If after_date is Tuesday and target_day is Monday, returns next Monday (6 days later)
        """
        current_day = after_date.weekday()
        days_until_target = (target_day - current_day) % 7

        # If it's the same day, go to next week (rule: not same day if added on target day)
        if days_until_target == 0:
            days_until_target = 7

        next_date = after_date + timedelta(days=days_until_target)
        # Set to start of day
        return next_date.replace(hour=9, minute=0, second=0, microsecond=0)

    def get_loans_for_weekly_update(self, workflow_key: str = 'under_contract') -> List[Any]:
        """
        Get all loans eligible for weekly updates.

        Criteria:
        - Loan is in Disclosed status or later (but not closed/canceled/etc.)
        - Has a disclosed_date set
        - Not in a terminal status
        """
        if not self.Loan:
            logger.error("Loan model not available")
            return []

        # Get active loans that have entered LE Pending
        # Exclude terminal statuses
        terminal_statuses = DEFAULT_STOP_STATUSES

        try:
            loans = self.db.query(self.Loan).filter(
                and_(
                    # Has entered processing (has Disclosed date or equivalent)
                    or_(
                        self.Loan.loan_estimate_sent_date.isnot(None),
                        self.Loan.stage.in_(['PROCESSING', 'SUBMITTED', 'UW_RECEIVED', 'APPROVED', 'SUSPENDED', 'CTC', 'DOCS'])
                    ),
                    # Not in terminal status
                    ~self.Loan.stage.in_(['FUNDED', 'WITHDRAWN', 'DENIED'])
                )
            ).all()

            logger.info(f"Found {len(loans)} loans eligible for weekly updates")
            return loans

        except Exception as e:
            logger.error(f"Error querying loans for weekly update: {e}")
            return []

    def get_loan_stakeholders(self, loan_id: int, exclude_roles: List[str] = None) -> List[Dict]:
        """
        Get all stakeholders for a loan, excluding specified roles.

        Stakeholders include:
        - Borrower(s)
        - Listing Agent
        - Buyer's Agent
        - Closing Coordinator
        - Loan Officer
        - Other team members (except underwriter and closer for weekly updates)
        """
        if exclude_roles is None:
            exclude_roles = EXCLUDED_STAKEHOLDER_ROLES

        stakeholders = []

        try:
            # Get the loan
            loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
            if not loan:
                return []

            # Add borrower
            if loan.borrower_email:
                stakeholders.append({
                    'type': 'borrower',
                    'name': loan.borrower_name,
                    'email': loan.borrower_email,
                    'role': 'borrower'
                })

            # Add co-borrower if exists
            if hasattr(loan, 'co_borrower_email') and loan.co_borrower_email:
                stakeholders.append({
                    'type': 'co_borrower',
                    'name': getattr(loan, 'co_borrower_name', 'Co-Borrower'),
                    'email': loan.co_borrower_email,
                    'role': 'co_borrower'
                })

            # Add loan officer
            if loan.loan_officer_id:
                lo = self.db.query(self.User).filter(self.User.id == loan.loan_officer_id).first()
                if lo and lo.email:
                    stakeholders.append({
                        'type': 'team_member',
                        'name': lo.full_name or lo.email,
                        'email': lo.email,
                        'role': 'loan_officer'
                    })

            # Add team members from LoanTeamMember table (if available)
            if self.LoanTeamMember:
                team_members = self.db.query(self.LoanTeamMember).filter(
                    self.LoanTeamMember.loan_id == loan_id
                ).all()

                for tm in team_members:
                    # Skip excluded roles
                    role_name = tm.role.lower() if tm.role else ''
                    if any(excl in role_name for excl in exclude_roles):
                        continue

                    if tm.email:
                        stakeholders.append({
                            'type': 'team_member',
                            'name': tm.name or tm.email,
                            'email': tm.email,
                            'role': tm.role
                        })

            # Add agents if stored on loan
            if hasattr(loan, 'listing_agent_email') and loan.listing_agent_email:
                stakeholders.append({
                    'type': 'agent',
                    'name': getattr(loan, 'listing_agent_name', 'Listing Agent'),
                    'email': loan.listing_agent_email,
                    'role': 'listing_agent'
                })

            if hasattr(loan, 'buyers_agent_email') and loan.buyers_agent_email:
                stakeholders.append({
                    'type': 'agent',
                    'name': getattr(loan, 'buyers_agent_name', "Buyer's Agent"),
                    'email': loan.buyers_agent_email,
                    'role': 'buyers_agent'
                })

            logger.info(f"Found {len(stakeholders)} stakeholders for loan {loan_id}")
            return stakeholders

        except Exception as e:
            logger.error(f"Error getting stakeholders for loan {loan_id}: {e}")
            return []

    def should_send_weekly_task(self, loan: Any, day_config: Any, today: datetime = None) -> bool:
        """
        Determine if a weekly task should be sent today for a given loan.

        Args:
            loan: The loan object
            day_config: The workflow day configuration
            today: Current date (defaults to now)

        Returns:
            True if the task should be sent today
        """
        if today is None:
            today = datetime.now(timezone.utc)

        # Check if this is a repeat_weekly task
        if not getattr(day_config, 'repeat_weekly', False):
            return False

        # Check if today is the correct day of week
        target_day = getattr(day_config, 'repeat_day_of_week', MONDAY)
        if today.weekday() != target_day:
            return False

        # Check if loan is in a stop status
        stop_statuses = getattr(day_config, 'repeat_until_status', None) or DEFAULT_STOP_STATUSES
        loan_status = loan.stage.value.lower() if hasattr(loan.stage, 'value') else str(loan.stage).lower()
        if loan_status in [s.lower() for s in stop_statuses]:
            return False

        # Get the trigger date (Disclosed date or loan estimate sent date)
        trigger_date = getattr(loan, 'loan_estimate_sent_date', None) or getattr(loan, 'created_at', None)
        if not trigger_date:
            return False

        # Calculate the first valid send date
        first_send_date = self.get_next_occurrence(target_day, trigger_date)

        # If today is before the first valid send date, don't send
        if today.date() < first_send_date.date():
            return False

        return True

    def has_task_been_sent_this_week(self, loan_id: int, day_config_id: int, week_start: datetime) -> bool:
        """
        Check if a weekly task has already been created for this loan this week.
        """
        if not self.WorkflowTaskInstance:
            return False

        week_end = week_start + timedelta(days=7)

        existing = self.db.query(self.WorkflowTaskInstance).filter(
            and_(
                self.WorkflowTaskInstance.loan_id == loan_id,
                self.WorkflowTaskInstance.day_config_id == day_config_id,
                self.WorkflowTaskInstance.scheduled_date >= week_start,
                self.WorkflowTaskInstance.scheduled_date < week_end
            )
        ).first()

        return existing is not None

    def create_weekly_task_instance(
        self,
        loan: Any,
        day_config: Any,
        workflow: Any,
        stakeholders: List[Dict]
    ) -> Optional[Any]:
        """
        Create a workflow task instance for a weekly recurring task.
        """
        if not self.WorkflowTaskInstance:
            logger.error("WorkflowTaskInstance model not available")
            return None

        try:
            now = datetime.now(timezone.utc)

            # Build task description with stakeholder info
            stakeholder_names = [s['name'] for s in stakeholders[:5]]
            if len(stakeholders) > 5:
                stakeholder_names.append(f"and {len(stakeholders) - 5} more")

            task_description = f"Weekly update for {loan.borrower_name}. "
            task_description += f"Recipients: {', '.join(stakeholder_names)}"

            task_instance = self.WorkflowTaskInstance(
                workflow_id=workflow.id,
                day_config_id=day_config.id,
                loan_id=loan.id,
                task_name=day_config.day_label or 'Weekly Update',
                task_description=task_description,
                communication_method='email' if day_config.email_enabled else 'phone',
                scheduled_date=now,
                due_date=now + timedelta(hours=4),  # Due within 4 hours
                status='pending'
            )

            self.db.add(task_instance)
            self.db.flush()  # Get the ID

            logger.info(f"Created weekly task instance {task_instance.id} for loan {loan.id}")
            return task_instance

        except Exception as e:
            logger.error(f"Error creating weekly task instance for loan {loan.id}: {e}")
            return None

    def process_weekly_tasks(self, workflow_key: str = 'under_contract', dry_run: bool = False) -> Dict:
        """
        Process all weekly recurring tasks for a workflow.

        Args:
            workflow_key: The workflow to process
            dry_run: If True, don't actually create tasks, just report what would be done

        Returns:
            Summary of tasks processed
        """
        today = datetime.now(timezone.utc)
        week_start = today - timedelta(days=today.weekday())  # Monday of current week

        results = {
            'workflow_key': workflow_key,
            'date': today.isoformat(),
            'dry_run': dry_run,
            'loans_processed': 0,
            'tasks_created': 0,
            'tasks_skipped': 0,
            'errors': []
        }

        try:
            # Get the workflow configuration
            if not self.WorkflowConfiguration:
                results['errors'].append("WorkflowConfiguration model not available")
                return results

            workflow = self.db.query(self.WorkflowConfiguration).filter(
                self.WorkflowConfiguration.workflow_key == workflow_key
            ).first()

            if not workflow:
                results['errors'].append(f"Workflow '{workflow_key}' not found")
                return results

            # Get day configs that are repeat_weekly
            if not self.WorkflowDayConfig:
                results['errors'].append("WorkflowDayConfig model not available")
                return results

            weekly_days = self.db.query(self.WorkflowDayConfig).filter(
                and_(
                    self.WorkflowDayConfig.workflow_id == workflow.id,
                    self.WorkflowDayConfig.repeat_weekly == True,
                    self.WorkflowDayConfig.is_active == True
                )
            ).all()

            if not weekly_days:
                results['message'] = "No weekly recurring tasks configured for this workflow"
                return results

            logger.info(f"Found {len(weekly_days)} weekly task configurations")

            # Get eligible loans
            loans = self.get_loans_for_weekly_update(workflow_key)
            results['loans_processed'] = len(loans)

            for loan in loans:
                for day_config in weekly_days:
                    try:
                        # Check if task should be sent today
                        if not self.should_send_weekly_task(loan, day_config, today):
                            results['tasks_skipped'] += 1
                            continue

                        # Check if already sent this week
                        if self.has_task_been_sent_this_week(loan.id, day_config.id, week_start):
                            results['tasks_skipped'] += 1
                            continue

                        # Get stakeholders (exclude underwriter and closer)
                        stakeholders = self.get_loan_stakeholders(
                            loan.id,
                            exclude_roles=EXCLUDED_STAKEHOLDER_ROLES
                        )

                        if not stakeholders:
                            results['tasks_skipped'] += 1
                            continue

                        if dry_run:
                            results['tasks_created'] += 1
                            logger.info(f"[DRY RUN] Would create task for loan {loan.id}: {day_config.day_label}")
                        else:
                            # Create the task instance
                            task = self.create_weekly_task_instance(
                                loan, day_config, workflow, stakeholders
                            )
                            if task:
                                results['tasks_created'] += 1
                            else:
                                results['errors'].append(f"Failed to create task for loan {loan.id}")

                    except Exception as e:
                        error_msg = f"Error processing loan {loan.id} for day {day_config.id}: {str(e)}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)

            if not dry_run:
                self.db.commit()

            logger.info(f"Weekly task processing complete: {results['tasks_created']} tasks created")

        except Exception as e:
            error_msg = f"Error in process_weekly_tasks: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            self.db.rollback()

        return results


def get_weekly_task_scheduler(db: Session, models: Dict[str, Any]) -> WeeklyTaskScheduler:
    """Factory function to create a WeeklyTaskScheduler instance."""
    return WeeklyTaskScheduler(db, models)
