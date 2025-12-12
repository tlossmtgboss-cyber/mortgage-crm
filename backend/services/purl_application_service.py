"""
PURL Application Service

Provides business logic for PURL loan application operations including:
- Application creation and management
- Application data save/update (partial saves)
- Application validation
- Application submission
- Loan creation from applications
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from models.purl import (
    PURLApplication,
    PURLWorkspace,
    PURLLoan,
    PURLMilestoneDefinition,
    PURLLoanMilestone,
    PURLTask,
    PURLEventsOutbox,
    ApplicationType,
    ApplicationStatus,
    WorkspaceStatus,
    LoanStatus,
    MilestoneStatus,
    TaskStatus,
    TaskPriority,
    EventStatus
)

logger = logging.getLogger(__name__)


# Required fields for submission
REQUIRED_APPLICATION_FIELDS = [
    "borrower_first_name",
    "borrower_last_name",
    "borrower_email",
    "borrower_phone",
    "loan_purpose",
    "loan_amount",
]

# Optional validation - warn but don't block
RECOMMENDED_FIELDS = [
    "property_address",
    "employment_status",
    "annual_income",
]


class PURLApplicationService:
    """
    Service for PURL loan application operations.
    Manages application lifecycle from creation to submission.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # APPLICATION CRUD
    # =========================================================================

    def create_application(
        self,
        organization_id: int,
        workspace_id: int,
        application_type: ApplicationType = ApplicationType.FULL,
        initial_data: Optional[Dict[str, Any]] = None
    ) -> PURLApplication:
        """
        Create a new application for a workspace.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            application_type: Type of application
            initial_data: Initial application data

        Returns:
            Created application
        """
        # Check for existing in-progress application
        existing = self.db.query(PURLApplication).filter(
            PURLApplication.workspace_id == workspace_id,
            PURLApplication.status == ApplicationStatus.IN_PROGRESS.value
        ).first()

        if existing:
            # Return existing instead of creating new
            logger.info(f"Returning existing in-progress application {existing.id}")
            return existing

        # Determine version
        max_version = self.db.query(func.max(PURLApplication.version)).filter(
            PURLApplication.workspace_id == workspace_id,
            PURLApplication.application_type == application_type.value
        ).scalar() or 0

        application = PURLApplication(
            organization_id=organization_id,
            workspace_id=workspace_id,
            application_type=application_type.value,
            status=ApplicationStatus.IN_PROGRESS.value,
            version=max_version + 1,
            data=initial_data or {},
            derived={},
            validation_errors=[],
            completeness_pct=0,
            started_at=datetime.now(timezone.utc)
        )

        self.db.add(application)

        # Update workspace status if needed
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        ).first()

        if workspace and workspace.status == WorkspaceStatus.LEAD.value:
            workspace.status = WorkspaceStatus.APPLICATION.value
            workspace.application_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(application)

        # Emit event
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            event_key="application_started",
            payload={
                "application_id": application.id,
                "application_type": application_type.value,
                "version": application.version
            }
        )

        logger.info(f"Created application {application.id} for workspace {workspace_id}")
        return application

    def get_application(
        self,
        application_id: int
    ) -> Optional[PURLApplication]:
        """Get application by ID."""
        return self.db.query(PURLApplication).filter(
            PURLApplication.id == application_id
        ).first()

    def get_workspace_application(
        self,
        workspace_id: int,
        status: Optional[ApplicationStatus] = None
    ) -> Optional[PURLApplication]:
        """
        Get the current application for a workspace.

        Args:
            workspace_id: Workspace ID
            status: Filter by status (default: in_progress)

        Returns:
            Application or None
        """
        query = self.db.query(PURLApplication).filter(
            PURLApplication.workspace_id == workspace_id
        )

        if status:
            query = query.filter(PURLApplication.status == status.value)
        else:
            # Default to in-progress
            query = query.filter(
                PURLApplication.status == ApplicationStatus.IN_PROGRESS.value
            )

        return query.order_by(PURLApplication.version.desc()).first()

    # =========================================================================
    # APPLICATION DATA SAVE
    # =========================================================================

    def save_application(
        self,
        organization_id: int,
        workspace_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Save application data (partial save).
        Creates application if doesn't exist, merges data if exists.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            data: Application data to save

        Returns:
            Dict with application id, version, updated_at, completeness_pct
        """
        # Get or create application
        application = self.get_workspace_application(workspace_id)

        if application:
            # Merge data with existing
            merged_data = {**application.data, **data}
            application.data = merged_data

            # Calculate completeness
            completeness = self._calculate_completeness(merged_data)
            application.completeness_pct = completeness

            # Validate and store errors
            errors = self._validate_application(merged_data, check_required=False)
            application.validation_errors = errors

            # Calculate derived fields
            application.derived = self._calculate_derived_fields(merged_data)

            self.db.commit()
            self.db.refresh(application)

            logger.debug(f"Updated application {application.id}, completeness: {completeness}%")
        else:
            # Create new application
            application = self.create_application(
                organization_id=organization_id,
                workspace_id=workspace_id,
                initial_data=data
            )

        # Emit event (throttled in practice)
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            event_key="application_updated",
            payload={
                "application_id": application.id,
                "completeness_pct": application.completeness_pct
            }
        )

        return {
            "id": application.id,
            "version": application.version,
            "updated_at": application.updated_at.isoformat() if application.updated_at else None,
            "completeness_pct": application.completeness_pct,
            "validation_errors": application.validation_errors
        }

    # =========================================================================
    # APPLICATION SUBMISSION
    # =========================================================================

    def submit_application(
        self,
        organization_id: int,
        workspace_id: int
    ) -> Dict[str, Any]:
        """
        Submit completed application.
        Creates loan record and triggers workflow automation.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID

        Returns:
            Dict with application_id, loan_id, submitted_at

        Raises:
            ValueError: If application is incomplete or invalid
        """
        # Get current application
        application = self.get_workspace_application(workspace_id)

        if not application:
            raise ValueError("No application in progress")

        if application.status != ApplicationStatus.IN_PROGRESS.value:
            raise ValueError(f"Application is {application.status}, cannot submit")

        # Validate completeness
        errors = self._validate_application(application.data, check_required=True)

        if errors:
            raise ValueError(f"Application incomplete: {', '.join(errors)}")

        # Submit application
        now = datetime.now(timezone.utc)
        application.status = ApplicationStatus.SUBMITTED.value
        application.submitted_at = now

        # Create loan record
        loan = PURLLoan(
            organization_id=organization_id,
            workspace_id=workspace_id,
            application_id=application.id,
            status=LoanStatus.ACTIVE.value,
            loan_purpose=application.data.get("loan_purpose"),
            loan_amount=application.data.get("loan_amount"),
            property_address=application.data.get("property_address")
        )

        self.db.add(loan)
        self.db.flush()  # Get loan ID

        # Update workspace status
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        ).first()

        if workspace:
            workspace.status = WorkspaceStatus.ACTIVE_LOAN.value
            workspace.active_loan_at = now

        self.db.commit()
        self.db.refresh(loan)

        # Initialize loan workflow (milestones and tasks)
        self._initialize_loan_workflow(organization_id, loan.id, workspace_id)

        # Emit events
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            event_key="application_submitted",
            payload={
                "application_id": application.id,
                "loan_id": loan.id,
                "submitted_at": now.isoformat()
            }
        )

        logger.info(f"Submitted application {application.id}, created loan {loan.id}")

        return {
            "application_id": application.id,
            "loan_id": loan.id,
            "submitted_at": now.isoformat()
        }

    # =========================================================================
    # VALIDATION & COMPLETENESS
    # =========================================================================

    def _validate_application(
        self,
        data: Dict[str, Any],
        check_required: bool = True
    ) -> List[str]:
        """
        Validate application data.

        Args:
            data: Application data
            check_required: Whether to check required fields

        Returns:
            List of validation error messages
        """
        errors = []

        if check_required:
            for field in REQUIRED_APPLICATION_FIELDS:
                if not data.get(field):
                    errors.append(f"Missing required field: {field}")

        # Email validation
        email = data.get("borrower_email")
        if email and "@" not in email:
            errors.append("Invalid email format")

        # Loan amount validation
        loan_amount = data.get("loan_amount")
        if loan_amount:
            try:
                amount = float(loan_amount)
                if amount <= 0:
                    errors.append("Loan amount must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid loan amount")

        # Phone validation (basic)
        phone = data.get("borrower_phone")
        if phone:
            # Remove non-numeric chars and check length
            digits = "".join(c for c in phone if c.isdigit())
            if len(digits) < 10:
                errors.append("Phone number must have at least 10 digits")

        return errors

    def _calculate_completeness(self, data: Dict[str, Any]) -> int:
        """
        Calculate application completeness percentage.

        Returns:
            Percentage (0-100)
        """
        all_fields = REQUIRED_APPLICATION_FIELDS + RECOMMENDED_FIELDS

        if not all_fields:
            return 100

        filled = sum(1 for field in all_fields if data.get(field))
        return int((filled / len(all_fields)) * 100)

    def _calculate_derived_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate derived fields from application data.

        Returns:
            Dict of derived fields
        """
        derived = {}

        # Calculate DTI if income and loan amount provided
        annual_income = data.get("annual_income")
        loan_amount = data.get("loan_amount")

        if annual_income and loan_amount:
            try:
                income = float(annual_income)
                amount = float(loan_amount)

                if income > 0:
                    # Simple estimated monthly payment (rough approximation)
                    estimated_monthly_payment = amount * 0.006  # ~0.6% of loan amount
                    monthly_income = income / 12
                    derived["estimated_dti"] = round(
                        (estimated_monthly_payment / monthly_income) * 100, 2
                    )
            except (ValueError, TypeError):
                pass

        # Full name
        first_name = data.get("borrower_first_name", "")
        last_name = data.get("borrower_last_name", "")
        if first_name or last_name:
            derived["borrower_full_name"] = f"{first_name} {last_name}".strip()

        return derived

    # =========================================================================
    # WORKFLOW INITIALIZATION
    # =========================================================================

    def _initialize_loan_workflow(
        self,
        organization_id: int,
        loan_id: int,
        workspace_id: int
    ):
        """
        Initialize milestones and tasks for a new loan.
        """
        # Get milestone definitions
        definitions = self.db.query(PURLMilestoneDefinition).filter(
            PURLMilestoneDefinition.organization_id == organization_id,
            PURLMilestoneDefinition.is_active == True
        ).order_by(PURLMilestoneDefinition.order_index).all()

        base_date = datetime.now(timezone.utc)

        # Create milestones
        for definition in definitions:
            due_at = None
            if definition.sla_days:
                due_at = base_date + timedelta(days=definition.sla_days)

            milestone = PURLLoanMilestone(
                organization_id=organization_id,
                loan_id=loan_id,
                milestone_definition_id=definition.id,
                status=MilestoneStatus.PENDING.value,
                due_at=due_at
            )
            self.db.add(milestone)

        # Create initial borrower tasks
        initial_tasks = [
            {
                "title": "Upload pay stubs (last 2 months)",
                "description": "Please upload your most recent pay stubs showing year-to-date earnings.",
                "priority": TaskPriority.HIGH.value,
                "due_days": 3
            },
            {
                "title": "Upload bank statements (last 2 months)",
                "description": "Please upload statements for all accounts you'll use for closing.",
                "priority": TaskPriority.HIGH.value,
                "due_days": 3
            },
            {
                "title": "Upload W-2s (last 2 years)",
                "description": "Please upload your W-2 forms from the last 2 years.",
                "priority": TaskPriority.MEDIUM.value,
                "due_days": 5
            },
            {
                "title": "Upload tax returns (last 2 years)",
                "description": "Please upload your complete tax returns including all schedules.",
                "priority": TaskPriority.MEDIUM.value,
                "due_days": 7
            },
            {
                "title": "Upload driver's license or ID",
                "description": "Please upload a clear copy of your government-issued ID.",
                "priority": TaskPriority.HIGH.value,
                "due_days": 3
            }
        ]

        for task_data in initial_tasks:
            due_at = base_date + timedelta(days=task_data["due_days"])

            task = PURLTask(
                organization_id=organization_id,
                workspace_id=workspace_id,
                loan_id=loan_id,
                title=task_data["title"],
                description=task_data["description"],
                task_type="document_upload",
                status=TaskStatus.OPEN.value,
                priority=task_data["priority"],
                due_at=due_at
            )
            self.db.add(task)

        self.db.commit()

        logger.info(
            f"Initialized workflow for loan {loan_id}: "
            f"{len(definitions)} milestones, {len(initial_tasks)} tasks"
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _emit_event(
        self,
        organization_id: int,
        workspace_id: int,
        event_key: str,
        payload: Dict[str, Any]
    ):
        """Emit event to outbox."""
        event = PURLEventsOutbox(
            organization_id=organization_id,
            workspace_id=workspace_id,
            event_key=event_key,
            payload=payload,
            status=EventStatus.PENDING.value
        )
        self.db.add(event)
