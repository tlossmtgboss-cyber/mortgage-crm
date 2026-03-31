"""
Workflow Task Generator Service

Generates workflow tasks based on workflow day configurations.
Handles task creation, routing, role assignment, and AI eligibility.

Key responsibilities:
- Generate tasks for due workflow days
- Create task group keys for sibling cancellation
- Route tasks to appropriate destinations (task list, dialer, AI)
- Assign tasks to users based on role assignments
- Track AI eligibility and confidence
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
import uuid
from sqlalchemy.exc import SQLAlchemyError

from services.workflow_constants import TASK_TYPE_ROUTES, AI_ELIGIBLE_TASK_TYPES

logger = logging.getLogger(__name__)


class TaskGeneratorService:
    """
    Generates workflow tasks from workflow configurations.

    Converts workflow day configurations into actual task instances,
    handling routing, role assignment, and scheduling.
    """

    # Imported from workflow_constants (canonical source of truth)
    TASK_TYPE_ROUTES = TASK_TYPE_ROUTES
    AI_ELIGIBLE_TYPES = AI_ELIGIBLE_TASK_TYPES

    def __init__(self, db: Session):
        self.db = db
        self._load_models()

    def _load_models(self):
        """Load required models."""
        from database.models import Lead, Loan, Task, User
        from models.user_onboarding import Role

        self.Lead = Lead
        self.Loan = Loan
        self.Task = Task
        self.User = User
        self.Role = Role

    def generate_tasks_for_instance(
        self,
        instance_id: int,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Generate all due tasks for a workflow instance.

        Args:
            instance_id: Workflow instance ID
            force_regenerate: If True, regenerate already generated days

        Returns:
            Dict with generation results
        """
        try:
            # Get workflow instance
            instance = self._get_instance(instance_id)
            if not instance:
                return {"success": False, "error": "Workflow instance not found"}

            if instance['status'] != 'active':
                return {"success": False, "error": f"Instance not active: {instance['status']}"}

            # Get workflow configuration and day configs
            config = self._get_workflow_config(instance['workflow_configuration_id'])
            if not config:
                return {"success": False, "error": "Workflow configuration not found"}

            day_configs = self._get_day_configs(instance['workflow_configuration_id'])
            if not day_configs:
                return {"success": False, "error": "No day configurations found"}

            # Calculate days since workflow started
            started_at = instance['started_at']
            if not started_at:
                started_at = datetime.now(timezone.utc)
            days_elapsed = (datetime.now(timezone.utc) - started_at).days

            # Get contact info for the entity
            contact_info = self._get_contact_info(instance['lead_id'], instance['loan_id'])

            tasks_created = []
            # Use -1 as default so day 0 tasks are generated for new instances
            last_day_generated = instance['last_task_generated_day'] if instance['last_task_generated_day'] is not None else -1

            for day_config in day_configs:
                day_value = day_config['day_value'] or 0

                # Skip if already generated (unless force)
                if not force_regenerate and day_value <= last_day_generated:
                    continue

                # Skip if not yet due
                if day_value > days_elapsed:
                    continue

                # Skip if day config is not active
                if not day_config.get('is_active', True):
                    continue

                # Generate tasks for this day
                day_tasks = self._generate_day_tasks(
                    instance=instance,
                    day_config=day_config,
                    contact_info=contact_info,
                    config=config
                )
                tasks_created.extend(day_tasks)

                # Update last generated day
                if day_value > last_day_generated:
                    last_day_generated = day_value

            # Update instance's last_task_generated_day
            self._update_instance_progress(instance_id, last_day_generated)

            # CRITICAL: Commit all changes to persist tasks to database
            self.db.commit()

            logger.info(f"Generated {len(tasks_created)} tasks for instance {instance_id}")

            return {
                "success": True,
                "tasks_created": len(tasks_created),
                "task_ids": tasks_created,
                "last_day_generated": last_day_generated
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Task generation failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def generate_scheduled_tasks(self) -> Dict[str, Any]:
        """
        Generate tasks for all active workflows that have due tasks.

        Called by the scheduler to process all workflows.
        """
        try:
            # Get all active workflow instances
            instances = self.db.execute(text("""
                SELECT id FROM workflow_instances
                WHERE status = 'active'
                AND (next_task_due_at IS NULL OR next_task_due_at <= NOW())
            """)).fetchall()

            total_tasks = 0
            instances_processed = 0
            errors = []

            for (instance_id,) in instances:
                result = self.generate_tasks_for_instance(instance_id)
                if result['success']:
                    total_tasks += result.get('tasks_created', 0)
                    instances_processed += 1
                else:
                    errors.append({"instance_id": instance_id, "error": result.get('error')})

            logger.info(f"Scheduled generation: {total_tasks} tasks for {instances_processed} instances")

            return {
                "success": True,
                "instances_processed": instances_processed,
                "total_tasks_created": total_tasks,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Scheduled task generation failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _generate_day_tasks(
        self,
        instance: Dict,
        day_config: Dict,
        contact_info: Dict,
        config: Dict
    ) -> List[int]:
        """Generate all tasks for a specific day configuration."""
        tasks_created = []
        day_order = day_config['day_order']
        day_label = day_config['day_label']

        # Generate a group key for sibling cancellation
        # Tasks on the same day for the same entity share a group key
        group_key = f"wf_{instance['id']}_day_{day_order}_{uuid.uuid4().hex[:8]}"

        # Determine which task types are enabled
        task_types = self._get_enabled_task_types(day_config)

        # Get role assignments for this entity
        role_assignments = self._get_role_assignments(
            lead_id=instance['lead_id'],
            loan_id=instance['loan_id'],
            organization_id=instance['organization_id']
        )

        for task_type in task_types:
            # Determine route
            route = self.TASK_TYPE_ROUTES.get(task_type, 'task_list')

            # Determine AI eligibility
            ai_eligible = task_type in self.AI_ELIGIBLE_TYPES and day_config.get('ai_responsible', False)

            # Get assigned user based on role responsibilities
            assigned_user_id, assigned_role_id = self._determine_assignment(
                day_config=day_config,
                role_assignments=role_assignments,
                task_type=task_type
            )

            # Calculate due date
            started_at = instance['started_at'] or datetime.now(timezone.utc)
            due_date = started_at + timedelta(days=day_config['day_value'] or 0)

            # Handle AM/PM timing
            if task_type.endswith('_am'):
                due_date = due_date.replace(hour=9, minute=0, second=0)
            elif task_type.endswith('_pm'):
                due_date = due_date.replace(hour=14, minute=0, second=0)

            # Create task instance
            task_instance_id = self._create_task_instance(
                instance=instance,
                day_config=day_config,
                task_type=task_type,
                route=route,
                group_key=group_key,
                assigned_user_id=assigned_user_id,
                assigned_role_id=assigned_role_id,
                ai_eligible=ai_eligible,
                due_date=due_date,
                contact_info=contact_info,
                config=config
            )

            if task_instance_id:
                tasks_created.append(task_instance_id)

                # Create linked task in main tasks table for ALL workflow tasks
                # This provides visibility into all workflow activities in the task list UI
                logger.info(f"Creating linked task for instance {task_instance_id}, type={task_type}")
                linked_task_id = self._create_linked_task(
                    task_instance_id=task_instance_id,
                    instance=instance,
                    day_config=day_config,
                    task_type=task_type,
                    assigned_user_id=assigned_user_id,
                    due_date=due_date,
                    contact_info=contact_info,
                    group_key=group_key
                )
                if linked_task_id:
                    logger.info(f"Created linked task {linked_task_id} for workflow instance {task_instance_id}")
                else:
                    logger.warning(f"Failed to create linked task for workflow instance {task_instance_id}")

        return tasks_created

    def _calculate_scheduled_date(
        self,
        enrollment_date: datetime,
        day_value: int,
        time_of_day: str = None
    ) -> datetime:
        """
        Calculate the scheduled date for a task based on enrollment date and day value.

        Args:
            enrollment_date: The date the workflow was started/enrolled
            day_value: The number of days from enrollment (1 = next day)
            time_of_day: Optional time indicator ('morning', 'afternoon', 'am', 'pm')

        Returns:
            datetime: The calculated scheduled date with appropriate time
        """
        from datetime import date as date_type

        # Handle date vs datetime
        if isinstance(enrollment_date, date_type) and not isinstance(enrollment_date, datetime):
            enrollment_date = datetime.combine(enrollment_date, datetime.min.time())

        # Ensure timezone aware
        if enrollment_date.tzinfo is None:
            enrollment_date = enrollment_date.replace(tzinfo=timezone.utc)

        # Calculate base date (day_value days from enrollment)
        scheduled = enrollment_date + timedelta(days=day_value)

        # Apply time of day
        if time_of_day:
            time_lower = time_of_day.lower()
            if time_lower in ('morning', 'am'):
                scheduled = scheduled.replace(hour=9, minute=0, second=0, microsecond=0)
            elif time_lower in ('afternoon', 'pm'):
                scheduled = scheduled.replace(hour=14, minute=0, second=0, microsecond=0)

        return scheduled

    def _generate_task_group_key(
        self,
        instance_id: int,
        sibling_group: str = None,
        day_order: int = None
    ) -> str:
        """
        Generate a unique task group key for sibling cancellation.

        Tasks with the same group key can be cancelled together when one is completed.

        Args:
            instance_id: The workflow instance ID
            sibling_group: Optional sibling group identifier (e.g., 'day1_contact')
            day_order: Optional day order for the workflow

        Returns:
            str: A unique task group key
        """
        if sibling_group:
            return f"wf_{instance_id}_{sibling_group}_{uuid.uuid4().hex[:8]}"
        elif day_order is not None:
            return f"wf_{instance_id}_day_{day_order}_{uuid.uuid4().hex[:8]}"
        else:
            return f"wf_{instance_id}_{uuid.uuid4().hex[:8]}"

    def _get_enabled_task_types(self, day_config: Dict) -> List[str]:
        """Determine which task types are enabled for a day config."""
        types = []

        if day_config.get('phone_enabled'):
            types.append('phone')
        if day_config.get('phone_am_enabled'):
            types.append('phone_am')
        if day_config.get('phone_pm_enabled'):
            types.append('phone_pm')
        if day_config.get('text_enabled'):
            types.append('text')
        if day_config.get('text_am_enabled'):
            types.append('text_am')
        if day_config.get('text_pm_enabled'):
            types.append('text_pm')
        if day_config.get('email_enabled'):
            types.append('email')
        if day_config.get('referral_partner_enabled'):
            types.append('referral_partner')

        return types

    def _determine_assignment(
        self,
        day_config: Dict,
        role_assignments: Dict[int, int],
        task_type: str
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Determine task assignment based on role responsibilities.

        Returns (assigned_user_id, assigned_role_id)
        """
        # Check role responsibilities from day_config
        role_responsibilities = day_config.get('role_responsibilities', {})

        # Legacy field support
        legacy_mappings = {
            'lo_responsible': 'Loan Officer',
            'jr_lo_responsible': 'Junior Loan Officer',
            'production_asst_responsible': 'Production Assistant',
            'concierge_responsible': 'Concierge',
            'ai_responsible': 'AI Assistant',
        }

        # Get responsible roles
        responsible_role_ids = []

        # Check dynamic role responsibilities (role_id -> bool)
        for role_id_str, is_responsible in role_responsibilities.items():
            if is_responsible:
                try:
                    responsible_role_ids.append(int(role_id_str))
                except ValueError:
                    pass

        # Check legacy fields and map to role IDs
        for legacy_field, role_name in legacy_mappings.items():
            if day_config.get(legacy_field):
                role = self.db.query(self.Role).filter(self.Role.name == role_name).first()
                if role and role.id not in responsible_role_ids:
                    responsible_role_ids.append(role.id)

        # RL-003: Find first role with an assigned user under capacity
        first_available = None
        for role_id in responsible_role_ids:
            if role_id in role_assignments:
                user_id = role_assignments[role_id]
                if first_available is None:
                    first_available = (user_id, role_id)
                # Check capacity
                try:
                    pending_count = self.db.execute(text("""
                        SELECT COUNT(*) FROM tasks
                        WHERE owner_id = :uid AND status IN ('pending', 'in_progress')
                    """), {"uid": user_id}).scalar() or 0
                    if pending_count < self.MAX_PENDING_TASKS_PER_USER:
                        return user_id, role_id
                except Exception as e:
                    logger.warning(f"Error checking task capacity for user {user_id}: {e}")
                    # On error, allow assignment anyway
                    return user_id, role_id

        # All users over capacity — assign to the first one anyway (better overloaded than unassigned)
        if first_available:
            logger.warning(f"All assigned users over capacity ({self.MAX_PENDING_TASKS_PER_USER}), assigning to first available")
            return first_available

        # If no specific assignment, return first responsible role without user
        if responsible_role_ids:
            return None, responsible_role_ids[0]

        return None, None

    # Maximum pending tasks per user before capacity overflow
    MAX_PENDING_TASKS_PER_USER = 50

    def _create_task_instance(
        self,
        instance: Dict,
        day_config: Dict,
        task_type: str,
        route: str,
        group_key: str,
        assigned_user_id: int,
        assigned_role_id: int,
        ai_eligible: bool,
        due_date: datetime,
        contact_info: Dict,
        config: Dict
    ) -> Optional[int]:
        """Create a workflow task instance."""
        try:
            # AT-005: Dedup check - skip if identical active task already exists
            existing = self.db.execute(text("""
                SELECT id FROM workflow_task_instances
                WHERE workflow_instance_id = :iid
                AND day_config_id = :did
                AND task_type = :type
                AND status NOT IN ('cancelled', 'failed')
                LIMIT 1
            """), {
                "iid": instance['id'],
                "did": day_config['id'],
                "type": task_type
            }).fetchone()
            if existing:
                logger.info(f"Dedup: task already exists (id={existing[0]}) for instance {instance['id']}, day {day_config['id']}, type {task_type}")
                return existing[0]

            # Build task name
            contact_name = contact_info.get('name', 'Contact')
            task_name = f"{task_type.replace('_', ' ').title()} - {contact_name} ({day_config['day_label']})"

            # Build description
            description = day_config.get('task_description', '')
            if not description:
                description = f"{config.get('workflow_name', 'Workflow')} - {day_config['day_label']}"

            self.db.execute(text("""
                INSERT INTO workflow_task_instances (
                    workflow_instance_id, workflow_id, day_config_id,
                    lead_id, loan_id, organization_id,
                    task_name, task_description,
                    task_type, route, task_group_key,
                    assigned_user_id, assigned_role_id,
                    ai_eligible, status,
                    scheduled_date, due_date,
                    created_at, updated_at
                ) VALUES (
                    :instance_id, :workflow_id, :day_config_id,
                    :lead_id, :loan_id, :org_id,
                    :task_name, :description,
                    :task_type, :route, :group_key,
                    :assigned_user_id, :assigned_role_id,
                    :ai_eligible, 'scheduled',
                    :scheduled_date, :due_date,
                    NOW(), NOW()
                )
            """), {
                "instance_id": instance['id'],
                "workflow_id": instance['workflow_configuration_id'],
                "day_config_id": day_config['id'],
                "lead_id": instance['lead_id'],
                "loan_id": instance['loan_id'],
                "org_id": instance['organization_id'],
                "task_name": task_name,
                "description": description,
                "task_type": task_type,
                "route": route,
                "group_key": group_key,
                "assigned_user_id": assigned_user_id,
                "assigned_role_id": assigned_role_id,
                "ai_eligible": ai_eligible,
                "scheduled_date": due_date,
                "due_date": due_date
            })
            self.db.flush()

            # Get the created ID
            result = self.db.execute(text("""
                SELECT id FROM workflow_task_instances
                WHERE workflow_instance_id = :instance_id
                AND task_group_key = :group_key
                AND task_type = :task_type
                ORDER BY id DESC LIMIT 1
            """), {
                "instance_id": instance['id'],
                "group_key": group_key,
                "task_type": task_type
            }).fetchone()

            return result[0] if result else None

        except SQLAlchemyError as e:
            logger.error(f"Failed to create task instance: {e}")
            return None

    def _create_linked_task(
        self,
        task_instance_id: int,
        instance: Dict,
        day_config: Dict,
        task_type: str,
        assigned_user_id: int,
        due_date: datetime,
        contact_info: Dict,
        group_key: str
    ) -> Optional[int]:
        """Create a linked task in the main tasks table."""
        try:
            logger.info(f"_create_linked_task called: task_instance_id={task_instance_id}, task_type={task_type}")

            # AT-005: Dedup check - skip if linked task already exists for this instance
            existing_linked = self.db.execute(text("""
                SELECT id FROM tasks
                WHERE workflow_task_instance_id = :tid
                AND status NOT IN ('cancelled', 'deleted')
                LIMIT 1
            """), {"tid": task_instance_id}).fetchone()
            if existing_linked:
                logger.info(f"Dedup: linked task already exists (id={existing_linked[0]}) for task instance {task_instance_id}")
                return existing_linked[0]

            # If no assigned user, get the owner from the lead or loan
            owner_id = assigned_user_id
            if not owner_id:
                # Try to get owner from lead (column is owner_id, not assigned_to)
                if instance.get('lead_id'):
                    lead_owner = self.db.execute(text("""
                        SELECT owner_id FROM leads WHERE id = :lead_id
                    """), {"lead_id": instance['lead_id']}).fetchone()
                    if lead_owner and lead_owner[0]:
                        owner_id = lead_owner[0]
                        logger.info(f"Got owner_id={owner_id} from lead {instance['lead_id']}")

                # Try to get owner from loan if still no owner
                if not owner_id and instance.get('loan_id'):
                    loan_owner = self.db.execute(text("""
                        SELECT loan_officer_id FROM loans WHERE id = :loan_id
                    """), {"loan_id": instance['loan_id']}).fetchone()
                    if loan_owner and loan_owner[0]:
                        owner_id = loan_owner[0]
                        logger.info(f"Got owner_id={owner_id} from loan {instance['loan_id']}")

                # If still no owner, skip creating the linked task
                if not owner_id:
                    logger.warning(f"No owner found for task instance {task_instance_id}, skipping linked task")
                    return None

            # Build title
            contact_name = contact_info.get('name', 'Contact')
            title = f"[Workflow] {task_type.replace('_', ' ').title()} - {contact_name}"

            logger.info(f"Creating task: title='{title}', lead_id={instance.get('lead_id')}, loan_id={instance.get('loan_id')}, owner_id={owner_id}")

            # Build description
            description = f"""Workflow Task: {day_config['day_label']}
Contact: {contact_name}
Phone: {contact_info.get('phone', 'N/A')}
Email: {contact_info.get('email', 'N/A')}

{day_config.get('task_description', '')}"""

            # Determine priority based on day
            priority = 'medium'
            day_value = day_config.get('day_value', 0)
            if day_value <= 1:
                priority = 'high'
            elif day_value >= 30:
                priority = 'low'

            self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, status, priority,
                    due_date, owner_id, lead_id, loan_id,
                    related_contact_name, related_type,
                    workflow_task_instance_id, task_group_key,
                    created_at, updated_at
                ) VALUES (
                    :title, :description, 'pending', :priority,
                    :due_date, :owner_id, :lead_id, :loan_id,
                    :contact_name, :related_type,
                    :task_instance_id, :group_key,
                    NOW(), NOW()
                )
            """), {
                "title": title,
                "description": description,
                "priority": priority,
                "due_date": due_date,
                "owner_id": owner_id,  # Use resolved owner_id (from assigned_user_id, lead, or loan)
                "lead_id": instance['lead_id'],
                "loan_id": instance['loan_id'],
                "contact_name": contact_name,
                "related_type": 'lead' if instance['lead_id'] else 'loan',
                "task_instance_id": task_instance_id,
                "group_key": group_key
            })
            self.db.flush()

            # Get the task ID and update the task instance
            result = self.db.execute(text("""
                SELECT id FROM tasks
                WHERE workflow_task_instance_id = :task_instance_id
                ORDER BY id DESC LIMIT 1
            """), {"task_instance_id": task_instance_id}).fetchone()

            if result:
                task_id = result[0]
                self.db.execute(text("""
                    UPDATE workflow_task_instances
                    SET linked_task_id = :task_id
                    WHERE id = :instance_id
                """), {"task_id": task_id, "instance_id": task_instance_id})

                return task_id

            return None

        except SQLAlchemyError as e:
            logger.error(f"Failed to create linked task: {e}")
            return None

    def _get_instance(self, instance_id: int) -> Optional[Dict]:
        """Get workflow instance data."""
        result = self.db.execute(text("""
            SELECT id, organization_id, workflow_configuration_id,
                   lead_id, loan_id, status, started_at,
                   last_task_generated_day
            FROM workflow_instances
            WHERE id = :id
        """), {"id": instance_id}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "organization_id": result[1],
            "workflow_configuration_id": result[2],
            "lead_id": result[3],
            "loan_id": result[4],
            "status": result[5],
            "started_at": result[6],
            "last_task_generated_day": result[7]
        }

    def _get_workflow_config(self, config_id: int) -> Optional[Dict]:
        """Get workflow configuration."""
        result = self.db.execute(text("""
            SELECT id, workflow_key, workflow_name, description, objective
            FROM workflow_configurations
            WHERE id = :id
        """), {"id": config_id}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "workflow_key": result[1],
            "workflow_name": result[2],
            "description": result[3],
            "objective": result[4]
        }

    def _get_day_configs(self, workflow_config_id: int) -> List[Dict]:
        """Get day configurations for a workflow."""
        results = self.db.execute(text("""
            SELECT id, day_label, day_order, day_value, is_active,
                   phone_enabled, phone_am_enabled, phone_pm_enabled,
                   text_enabled, text_am_enabled, text_pm_enabled,
                   email_enabled, referral_partner_enabled,
                   lo_responsible, jr_lo_responsible, production_asst_responsible,
                   concierge_responsible, ai_responsible,
                   role_responsibilities, task_description
            FROM workflow_day_configs
            WHERE workflow_id = :config_id
            ORDER BY day_order
        """), {"config_id": workflow_config_id}).fetchall()

        return [
            {
                "id": row[0],
                "day_label": row[1],
                "day_order": row[2],
                "day_value": row[3],
                "is_active": row[4] if row[4] is not None else True,
                "phone_enabled": row[5],
                "phone_am_enabled": row[6],
                "phone_pm_enabled": row[7],
                "text_enabled": row[8],
                "text_am_enabled": row[9],
                "text_pm_enabled": row[10],
                "email_enabled": row[11],
                "referral_partner_enabled": row[12],
                "lo_responsible": row[13],
                "jr_lo_responsible": row[14],
                "production_asst_responsible": row[15],
                "concierge_responsible": row[16],
                "ai_responsible": row[17],
                "role_responsibilities": row[18] or {},
                "task_description": row[19]
            }
            for row in results
        ]

    def _get_contact_info(self, lead_id: int = None, loan_id: int = None) -> Dict:
        """Get contact information for the entity."""
        if lead_id:
            result = self.db.execute(text("""
                SELECT first_name, last_name, email, phone
                FROM leads WHERE id = :id
            """), {"id": lead_id}).fetchone()

            if result:
                return {
                    "name": f"{result[0] or ''} {result[1] or ''}".strip() or "Lead",
                    "email": result[2],
                    "phone": result[3]
                }

        if loan_id:
            result = self.db.execute(text("""
                SELECT l.borrower_first_name, l.borrower_last_name,
                       l.borrower_email, l.borrower_phone
                FROM loans l WHERE l.id = :id
            """), {"id": loan_id}).fetchone()

            if result:
                return {
                    "name": f"{result[0] or ''} {result[1] or ''}".strip() or "Borrower",
                    "email": result[2],
                    "phone": result[3]
                }

        return {"name": "Contact", "email": None, "phone": None}

    def _get_role_assignments(
        self,
        lead_id: int = None,
        loan_id: int = None,
        organization_id: int = None
    ) -> Dict[int, int]:
        """
        Get role-to-user assignments for an entity.

        Uses the RoleAssignmentService for consistent role resolution.
        Returns dict of role_id -> user_id
        """
        from services.workflow_role_assignment import get_role_assignment_service

        assignments = {}

        try:
            service = get_role_assignment_service(self.db)

            if lead_id:
                # Get all active role assignments for the lead
                lead_assignments = service.get_lead_role_assignments(lead_id)
                for assignment in lead_assignments:
                    assignments[assignment['role_id']] = assignment['user_id']

                # Also get owner as default Loan Officer
                lead = self.db.query(self.Lead).filter(self.Lead.id == lead_id).first()
                if lead and lead.owner_id:
                    lo_role = self.db.query(self.Role).filter(self.Role.name == 'Loan Officer').first()
                    if lo_role and lo_role.id not in assignments:
                        assignments[lo_role.id] = lead.owner_id

            if loan_id:
                # Get all active role assignments for the loan
                loan_assignments = service.get_loan_role_assignments(loan_id)
                for assignment in loan_assignments:
                    # Don't overwrite lead assignments (loan takes precedence if both exist)
                    assignments[assignment['role_id']] = assignment['user_id']

                # Also get loan officer as default
                loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
                if loan and loan.loan_officer_id:
                    lo_role = self.db.query(self.Role).filter(self.Role.name == 'Loan Officer').first()
                    if lo_role and lo_role.id not in assignments:
                        assignments[lo_role.id] = loan.loan_officer_id

            # Log role assignments for debugging
            if assignments:
                logger.debug(f"Role assignments for lead={lead_id}, loan={loan_id}: {assignments}")

        except SQLAlchemyError as e:
            logger.warning(f"Error getting role assignments: {e}")
            # Fall back to basic owner/LO assignment
            if lead_id:
                lead = self.db.query(self.Lead).filter(self.Lead.id == lead_id).first()
                if lead and lead.owner_id:
                    lo_role = self.db.query(self.Role).filter(self.Role.name == 'Loan Officer').first()
                    if lo_role:
                        assignments[lo_role.id] = lead.owner_id

            if loan_id:
                loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
                if loan and loan.loan_officer_id:
                    lo_role = self.db.query(self.Role).filter(self.Role.name == 'Loan Officer').first()
                    if lo_role:
                        assignments[lo_role.id] = loan.loan_officer_id

        return assignments

    def _update_instance_progress(self, instance_id: int, last_day: int):
        """Update instance's last_task_generated_day."""
        self.db.execute(text("""
            UPDATE workflow_instances
            SET last_task_generated_day = :last_day,
                updated_at = NOW()
            WHERE id = :instance_id
        """), {"instance_id": instance_id, "last_day": last_day})


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_task_generator(db: Session) -> TaskGeneratorService:
    """Factory function to get a TaskGeneratorService instance."""
    return TaskGeneratorService(db)
