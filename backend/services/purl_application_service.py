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

from sqlalchemy.exc import SQLAlchemyError
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

# Smart Docs integration
try:
    from services.smart_docs.needs_list_generator import NeedsListGenerator
    SMART_DOCS_AVAILABLE = True
except ImportError:
    SMART_DOCS_AVAILABLE = False

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
        status: Optional[ApplicationStatus] = None,
        include_submitted: bool = False
    ) -> Optional[PURLApplication]:
        """
        Get the current application for a workspace.

        Args:
            workspace_id: Workspace ID
            status: Filter by specific status (optional)
            include_submitted: If True and no status specified, include submitted apps

        Returns:
            Application or None
        """
        query = self.db.query(PURLApplication).filter(
            PURLApplication.workspace_id == workspace_id
        )

        if status:
            query = query.filter(PURLApplication.status == status.value)
        elif include_submitted:
            # Return in-progress or submitted applications (for portal viewing)
            query = query.filter(
                PURLApplication.status.in_([
                    ApplicationStatus.IN_PROGRESS.value,
                    ApplicationStatus.SUBMITTED.value
                ])
            )
        else:
            # Default to in-progress only (for save/submit operations)
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

        # Generate Smart Docs needs list automatically
        self._generate_smart_docs_needs_list(loan.id, application, borrower_id=1)

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
        Also creates lead_conditions in CRM if workspace is linked to a lead.
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

        # Define initial borrower document requirements
        initial_conditions = [
            {
                "name": "Pay Stubs (Last 2 Months)",
                "description": "Please upload your most recent pay stubs showing year-to-date earnings.",
                "category": "income",
                "priority": "required",
                "due_days": 3
            },
            {
                "name": "Bank Statements (Last 2 Months)",
                "description": "Please upload statements for all accounts you'll use for closing.",
                "category": "assets",
                "priority": "required",
                "due_days": 3
            },
            {
                "name": "W-2s (Last 2 Years)",
                "description": "Please upload your W-2 forms from the last 2 years.",
                "category": "income",
                "priority": "required",
                "due_days": 5
            },
            {
                "name": "Tax Returns (Last 2 Years)",
                "description": "Please upload your complete tax returns including all schedules.",
                "category": "income",
                "priority": "required",
                "due_days": 7
            },
            {
                "name": "Driver's License or Government ID",
                "description": "Please upload a clear copy of your government-issued ID.",
                "category": "identity",
                "priority": "required",
                "due_days": 3
            }
        ]

        # Create PURL tasks for portal
        for condition in initial_conditions:
            due_at = base_date + timedelta(days=condition["due_days"])
            priority = TaskPriority.HIGH.value if condition["priority"] == "required" else TaskPriority.MEDIUM.value

            task = PURLTask(
                organization_id=organization_id,
                workspace_id=workspace_id,
                loan_id=loan_id,
                title=f"Upload {condition['name']}",
                description=condition["description"],
                task_type="document_upload",
                status=TaskStatus.OPEN.value,
                priority=priority,
                due_at=due_at
            )
            self.db.add(task)

        # Get linked lead_id from workspace and create lead_conditions in CRM
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        ).first()

        lead_id = None
        if workspace and workspace.meta_data:
            lead_id = workspace.meta_data.get('lead_id')

        if lead_id:
            try:
                from sqlalchemy import text
                # Create lead_conditions for CRM sync
                for condition in initial_conditions:
                    due_date = (base_date + timedelta(days=condition["due_days"])).date()

                    self.db.execute(text("""
                        INSERT INTO lead_conditions
                        (lead_id, name, description, category, priority, due_date, status, is_new, created_at, updated_at)
                        VALUES (:lead_id, :name, :description, :category, :priority, :due_date, 'pending', true, NOW(), NOW())
                    """), {
                        "lead_id": int(lead_id),
                        "name": condition["name"],
                        "description": condition["description"],
                        "category": condition["category"],
                        "priority": condition["priority"],
                        "due_date": due_date
                    })

                # Update lead stage to Document Fulfillment
                self.db.execute(text("""
                    UPDATE leads
                    SET stage = 'Document Fulfillment', updated_at = NOW()
                    WHERE id = :lead_id
                """), {"lead_id": int(lead_id)})

                logger.info(f"Created {len(initial_conditions)} lead_conditions for lead {lead_id} and updated stage to Document Fulfillment")
            except SQLAlchemyError as e:
                # Log but don't fail if lead_conditions table doesn't exist
                logger.warning(f"Failed to create lead_conditions for lead {lead_id}: {e}")

        self.db.commit()

        logger.info(
            f"Initialized workflow for loan {loan_id}: "
            f"{len(definitions)} milestones, {len(initial_conditions)} tasks"
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

    def _generate_smart_docs_needs_list(
        self,
        loan_id: int,
        application: PURLApplication,
        borrower_id: int
    ):
        """
        Generate Smart Docs needs list based on application data.
        Maps application fields to Smart Docs parameters and generates requirements.
        """
        if not SMART_DOCS_AVAILABLE:
            logger.warning("Smart Docs not available, skipping needs list generation")
            return

        try:
            data = application.data or {}

            # Map loan purpose to loan program
            loan_purpose = data.get("loan_purpose", "").lower()
            loan_program = self._map_loan_program(loan_purpose, data)

            # Map occupancy type
            occupancy_raw = data.get("occupancy_type", "").upper()
            occupancy_type = self._map_occupancy_type(occupancy_raw)

            # Map employment status to income type
            # Check multiple possible locations for employment info
            declarations = data.get("declarations", {})
            employment_status = data.get("employment_status", "").lower()

            # Check declarations.self_employed (from PurchaseApplication/RefinanceApplication)
            self_employed_value = declarations.get("self_employed", "")
            if self_employed_value in ["yes", "side_business"]:
                employment_status = "self_employed"
            elif not employment_status:
                # Fall back to income_type or default to W2
                employment_status = data.get("income_type", "w2").lower()

            income_type = self._map_income_type(employment_status)

            # Get selected income types from application (new explicit selection)
            selected_income_types = self._get_income_types_from_application(data)
            logger.info(f"Selected income types for loan {loan_id}: {selected_income_types}")

            # Determine flags from application data
            is_self_employed = (
                employment_status in ["self_employed", "self-employed", "business_owner"] or
                self_employed_value in ["yes", "side_business"] or
                any(t in selected_income_types for t in ["SELF_EMPLOYMENT_1084", "BANK_BUSINESS", "BANK_PERSONAL"])
            )
            has_gift_funds = (
                data.get("has_gift_funds", False) or
                data.get("gift_funds", False) or
                declarations.get("gift_funds") == "yes"
            )
            has_bankruptcy = (
                data.get("has_bankruptcy", False) or
                data.get("bankruptcy_history", False) or
                declarations.get("bankruptcy") == "yes"
            )

            # Get co-borrower ID if present
            co_borrower_id = None
            has_coborrower = (
                data.get("has_co_borrower") or
                data.get("co_borrower_first_name") or
                declarations.get("borrower_count") in ["two", "2", "two_of_us", "three", "3", "four_or_more"]
            )
            if has_coborrower:
                co_borrower_id = 2  # Placeholder - in real system, create/lookup co-borrower

            # Create income source records for each selected income type
            self._create_income_sources_from_types(
                loan_id=loan_id,
                borrower_id=borrower_id,
                income_types=selected_income_types,
                application_data=data
            )

            # Generate the needs list
            generator = NeedsListGenerator(self.db)
            result = generator.generate_needs_list(
                loan_id=loan_id,
                loan_program=loan_program,
                occupancy_type=occupancy_type,
                income_type=income_type,
                borrower_id=borrower_id,
                co_borrower_id=co_borrower_id,
                has_gift_funds=has_gift_funds,
                is_self_employed=is_self_employed,
                has_bankruptcy=has_bankruptcy,
                property_type=data.get("property_type"),
                income_types=selected_income_types,  # Pass selected income types
            )

            logger.info(
                f"Generated Smart Docs needs list for loan {loan_id}: "
                f"{result.get('request_count', 0)} document requests created"
            )

        except Exception as e:
            # Log but don't fail the application submission
            logger.error(f"Failed to generate Smart Docs needs list for loan {loan_id}: {e}")

    def _map_loan_program(self, loan_purpose: str, data: Dict[str, Any]) -> str:
        """Map application loan purpose/type to Smart Docs loan program."""
        # Check for explicit loan type
        loan_type = data.get("loan_type", "").upper()
        if loan_type in ["FHA", "VA", "USDA", "CONVENTIONAL"]:
            return loan_type

        # Default based on loan purpose
        if "va" in loan_purpose:
            return "VA"
        elif "fha" in loan_purpose:
            return "FHA"
        elif "usda" in loan_purpose or "rural" in loan_purpose:
            return "USDA"
        else:
            return "CONVENTIONAL"

    def _map_occupancy_type(self, occupancy: str) -> str:
        """Map application occupancy to Smart Docs occupancy type."""
        occupancy_map = {
            "PRIMARY": "PRIMARY",
            "PRIMARY_RESIDENCE": "PRIMARY",
            "PRIMARY RESIDENCE": "PRIMARY",
            "OWNER_OCCUPIED": "PRIMARY",
            "SECOND_HOME": "SECOND_HOME",
            "SECOND HOME": "SECOND_HOME",
            "VACATION": "SECOND_HOME",
            "INVESTMENT": "INVESTMENT",
            "RENTAL": "INVESTMENT",
            "NON_OWNER": "INVESTMENT",
        }
        return occupancy_map.get(occupancy.upper(), "PRIMARY")

    def _map_income_type(self, employment_status: str) -> str:
        """Map application employment status to Smart Docs income type."""
        status_lower = employment_status.lower()
        if status_lower in ["self_employed", "self-employed", "business_owner", "1099"]:
            return "SELF_EMPLOYED"
        elif status_lower in ["retired", "retirement", "pension", "social_security"]:
            return "RETIREMENT"
        else:
            return "W2"

    def _get_income_types_from_application(self, data: Dict[str, Any]) -> List[str]:
        """
        Get selected income types from application data.
        Returns the explicit income_types array if present,
        otherwise maps from employment_status.
        """
        # Check for explicitly selected income types
        income_types = data.get("income_types")
        if income_types and isinstance(income_types, list) and len(income_types) > 0:
            return income_types

        # Fall back to mapping from employment status
        employment_status = data.get("employment_status", "").lower()
        base_type = self._map_income_type(employment_status)

        # Map broad type to specific income types
        if base_type == "SELF_EMPLOYED":
            return ["SELF_EMPLOYMENT_1084"]
        elif base_type == "RETIREMENT":
            return ["NONTAX_SS"]
        else:
            return ["W2_SALARY"]  # Default W2 type

    def _create_income_sources_from_types(
        self,
        loan_id: int,
        borrower_id: int,
        income_types: List[str],
        application_data: Dict[str, Any]
    ):
        """
        Create IncomeSource records for each selected income type.
        These will be populated with actual data when documents are uploaded and extracted.
        """
        try:
            from models.income_models import IncomeSource, IncomeType

            # Map income type IDs to IncomeType enum values
            type_mapping = {
                "W2_HOURLY": IncomeType.W2_EMPLOYMENT,
                "W2_SALARY": IncomeType.W2_EMPLOYMENT,
                "OT_BONUS": IncomeType.W2_EMPLOYMENT,
                "COMMISSION": IncomeType.COMMISSION,
                "NONTAX_SS": IncomeType.SOCIAL_SECURITY,
                "NONTAX_OTHER": IncomeType.PENSION,
                "BANK_PERSONAL": IncomeType.BANK_STATEMENT,
                "BANK_BUSINESS": IncomeType.BANK_STATEMENT,
                "RENTAL_SCHEDULE_E": IncomeType.RENTAL,
                "SELF_EMPLOYMENT_1084": IncomeType.SELF_EMPLOYED_SCHEDULE_C,
            }

            for income_type_id in income_types:
                income_type = type_mapping.get(income_type_id)
                if not income_type:
                    logger.warning(f"Unknown income type: {income_type_id}, skipping")
                    continue

                # Check if income source already exists for this loan/borrower/type
                existing = self.db.query(IncomeSource).filter(
                    IncomeSource.loan_id == loan_id,
                    IncomeSource.borrower_id == borrower_id,
                    IncomeSource.income_type == income_type
                ).first()

                if existing:
                    logger.info(f"Income source already exists for {income_type_id}, skipping")
                    continue

                # Create new income source record
                source_name = self._get_income_source_name(income_type_id, application_data)
                income_source = IncomeSource(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    income_type=income_type,
                    source_name=source_name,
                    is_verified=False,
                    verification_status="pending",
                    monthly_qualifying_income=None,  # Will be populated when docs extracted
                    notes=f"Created from application income type selection: {income_type_id}"
                )
                self.db.add(income_source)
                logger.info(f"Created income source for {income_type_id} on loan {loan_id}")

            self.db.commit()

        except SQLAlchemyError as e:
            logger.error(f"Failed to create income sources: {e}")
            self.db.rollback()

    def _get_income_source_name(self, income_type_id: str, data: Dict[str, Any]) -> str:
        """Get a descriptive name for the income source based on type and application data."""
        name_map = {
            "W2_HOURLY": data.get("employer_name") or "W-2 Hourly Income",
            "W2_SALARY": data.get("employer_name") or "W-2 Salary Income",
            "OT_BONUS": data.get("employer_name") or "Overtime & Bonus",
            "COMMISSION": data.get("employer_name") or "Commission Income",
            "NONTAX_SS": "Social Security Benefits",
            "NONTAX_OTHER": "Other Non-Taxable Income",
            "BANK_PERSONAL": "Personal Bank Statement Income",
            "BANK_BUSINESS": data.get("employer_name") or "Business Bank Statement Income",
            "RENTAL_SCHEDULE_E": "Rental Property Income",
            "SELF_EMPLOYMENT_1084": data.get("employer_name") or "Self-Employment Income",
        }
        return name_map.get(income_type_id, income_type_id)
