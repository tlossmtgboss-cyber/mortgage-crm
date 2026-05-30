"""
PURL Workspace Service

Provides business logic for PURL workspace operations including:
- Workspace creation and management
- Contact management
- Team member management
- Portal module configuration
- Workspace lifecycle transitions
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from sqlalchemy.exc import SQLAlchemyError
from models.purl import (
    PURLWorkspace,
    PURLContact,
    PURLWorkspaceMember,
    PURLPortalModule,
    PURLLoan,
    PURLDocument,
    PURLTask,
    PURLMessage,
    PURLEventsOutbox,
    PURLApplication,
    PURLLoanMilestone,
    PURLAuditLog,
    WorkspaceStatus,
    ContactType,
    MemberRole,
    PortalModule,
    TaskStatus,
    EventStatus,
    ApplicationStatus,
    SlugGenerator,
    WorkspaceCreate,
    WorkspaceResponse,
    ContactCreate,
    ContactResponse,
    PortalModuleResponse,
    PURLWorkspaceData,
    ContactType
)

# Try to import Smart Docs models for document requirements
try:
    from models.smart_docs_models import DocumentRequest, RequestStatus
    SMART_DOCS_AVAILABLE = True
except ImportError:
    SMART_DOCS_AVAILABLE = False

logger = logging.getLogger(__name__)


# Default portal module configurations
DEFAULT_PORTAL_MODULES = [
    {
        "module_key": PortalModule.APPLICATION.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 1,
        "config": {"title": "Application", "description": "Complete your loan application"}
    },
    {
        "module_key": PortalModule.DOCUMENTS.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 2,
        "config": {"title": "Documents", "description": "Upload required documents"}
    },
    {
        "module_key": PortalModule.TIMELINE.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 3,
        "config": {"title": "Timeline", "description": "Track your loan progress"}
    },
    {
        "module_key": PortalModule.MESSAGES.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 4,
        "config": {"title": "Messages", "description": "Communicate with your loan team"}
    },
    {
        "module_key": PortalModule.TASKS.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 5,
        "config": {"title": "Tasks", "description": "View and complete action items"}
    },
    {
        "module_key": PortalModule.CLOSING_VAULT.value,
        "is_enabled": False,
        "is_visible": False,
        "order_index": 6,
        "config": {"title": "Closing Vault", "description": "Access your closing documents"}
    },
    {
        "module_key": PortalModule.RESOURCES.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 7,
        "config": {"title": "Resources", "description": "Helpful guides and information"}
    }
]


def calculate_document_requirements_from_application(application_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Calculate required documents based on application declarations.

    This mirrors the frontend logic in PurchaseApplication.js to generate
    a dynamic document checklist based on borrower circumstances.

    Args:
        application_data: The application data containing declarations

    Returns:
        List of document requirement dictionaries (always returns at least base documents)
    """
    # Always initialize with empty dict if no data
    if not application_data:
        application_data = {}

    docs = []
    declarations = application_data.get('declarations', {})

    # Check employment type
    is_self_employed = declarations.get('self_employed') in ['yes', 'side_business']
    has_gift_funds = declarations.get('gift_funds') == 'yes'
    borrower_count = declarations.get('borrower_count', '1')
    has_co_borrower = borrower_count in ['2', '3', '4+']

    # Identity documents (always required) - Government ID only
    docs.append({
        'id': 'id',
        'name': 'Government ID',
        'description': "Driver's license or passport",
        'category': 'identity',
        'status': 'pending'
    })

    # Income documents (varies based on employment type)
    if is_self_employed:
        docs.append({
            'id': 'tax_returns',
            'name': 'Tax Returns',
            'description': 'Personal returns (last 2 years)',
            'category': 'income_verification',
            'status': 'pending'
        })
        docs.append({
            'id': 'business_tax_returns',
            'name': 'Business Tax Returns',
            'description': 'Business returns (last 2 years)',
            'category': 'income_verification',
            'status': 'pending'
        })
        docs.append({
            'id': 'profit_loss',
            'name': 'Profit & Loss Statement',
            'description': 'Year-to-date P&L',
            'category': 'income_verification',
            'status': 'pending'
        })
        docs.append({
            'id': 'business_license',
            'name': 'Business License',
            'description': 'Current business license',
            'category': 'income_verification',
            'status': 'pending'
        })
    else:
        docs.append({
            'id': 'paystubs',
            'name': 'Pay Stubs',
            'description': 'Last 30 days (most recent)',
            'category': 'income_verification',
            'status': 'pending'
        })
        docs.append({
            'id': 'w2',
            'name': 'W-2 Forms',
            'description': 'Last 2 years',
            'category': 'income_verification',
            'status': 'pending'
        })

    # Asset documents (always required)
    docs.append({
        'id': 'bank_statements',
        'name': 'Bank Statements',
        'description': 'Last 2 months (all pages)',
        'category': 'asset_verification',
        'status': 'pending'
    })

    # Gift letter if applicable
    if has_gift_funds:
        docs.append({
            'id': 'gift_letter',
            'name': 'Gift Letter',
            'description': 'Signed gift letter from donor',
            'category': 'asset_verification',
            'status': 'pending'
        })
        docs.append({
            'id': 'gift_donor_statements',
            'name': 'Gift Donor Bank Statements',
            'description': 'Donor bank statements showing funds',
            'category': 'asset_verification',
            'status': 'pending'
        })

    # Co-borrower documents if applicable
    if has_co_borrower:
        docs.append({
            'id': 'coborrower_id',
            'name': 'Co-Borrower Government ID',
            'description': "Co-borrower's driver's license or passport",
            'category': 'identity',
            'status': 'pending'
        })
        docs.append({
            'id': 'coborrower_income',
            'name': 'Co-Borrower Income Documents',
            'description': 'Pay stubs and W-2s for co-borrower',
            'category': 'income_verification',
            'status': 'pending'
        })

    return docs


# Mapping from application-generated doc IDs to Smart Docs DocType enum values
_APP_ID_TO_DOC_TYPE = {
    "id": "DRIVERS_LICENSE",
    "tax_returns": "TAX_RETURN",
    "business_tax_returns": "BUSINESS_TAX_RETURN",
    "profit_loss": "PROFIT_LOSS",
    "business_license": "OTHER",
    "paystubs": "PAYSTUB",
    "w2": "W2",
    "bank_statements": "BANK_STATEMENT",
    "gift_letter": "GIFT_LETTER",
    "gift_donor_statements": "BANK_STATEMENT",
    "coborrower_id": "DRIVERS_LICENSE",
    "coborrower_income": "PAYSTUB",
}


def _map_app_id_to_doc_type(app_id: str) -> str:
    """Map application-generated document ID to a Smart Docs DocType value."""
    return _APP_ID_TO_DOC_TYPE.get(app_id, "OTHER")


class PURLWorkspaceService:
    """
    Service for PURL workspace operations.
    Manages workspaces, contacts, members, and modules.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # WORKSPACE CRUD
    # =========================================================================

    def create_workspace(
        self,
        organization_id: int,
        data: WorkspaceCreate,
        owner_user_id: Optional[int] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new workspace with initial setup.

        Args:
            organization_id: Organization ID
            data: Workspace creation data
            owner_user_id: Owner user ID (LO)
            first_name: Borrower's first name for slug generation (firstname.lastname format)
            last_name: Borrower's last name for slug generation (firstname.lastname format)

        Returns:
            Dict with workspace id, slug, and created_at
        """
        # Generate slug - prefer firstname.lastname format if names provided
        if data.slug:
            slug = data.slug
        elif first_name and last_name:
            # Get all existing slugs for this org to ensure uniqueness
            existing_slugs = [
                ws.slug for ws in self.db.query(PURLWorkspace.slug).filter(
                    PURLWorkspace.organization_id == organization_id
                ).all()
            ]
            slug = SlugGenerator.generate_unique_from_name(first_name, last_name, existing_slugs)
        else:
            slug = SlugGenerator.generate(data.display_name)

        # Ensure slug is unique (double-check for race conditions)
        existing = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == organization_id,
            PURLWorkspace.slug == slug
        ).first()

        if existing:
            # Add extra random suffix
            slug = SlugGenerator.generate(data.display_name, suffix_length=12)

        # Create workspace
        workspace = PURLWorkspace(
            organization_id=organization_id,
            slug=slug,
            display_name=data.display_name,
            status=WorkspaceStatus.LEAD.value,
            source=data.source,
            owner_user_id=owner_user_id or data.owner_user_id,
            meta_data=data.metadata or {},
            lead_at=datetime.now(timezone.utc)
        )

        self.db.add(workspace)
        self.db.flush()  # Get ID without committing

        # Add owner as workspace member
        if workspace.owner_user_id:
            member = PURLWorkspaceMember(
                organization_id=organization_id,
                workspace_id=workspace.id,
                user_id=workspace.owner_user_id,
                role=MemberRole.OWNER.value
            )
            self.db.add(member)

        # Initialize portal modules
        self._initialize_portal_modules(organization_id, workspace.id)

        self.db.commit()
        self.db.refresh(workspace)

        # Emit event
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace.id,
            event_key="workspace_created",
            payload={
                "workspace_id": workspace.id,
                "slug": slug,
                "display_name": data.display_name,
                "owner_user_id": workspace.owner_user_id
            }
        )

        logger.info(f"Created workspace {workspace.id}: {slug}")

        return {
            "id": workspace.id,
            "slug": workspace.slug,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None
        }

    def get_workspace_by_id(
        self,
        workspace_id: int,
        organization_id: Optional[int] = None
    ) -> Optional[PURLWorkspace]:
        """Get workspace by ID."""
        query = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        )

        if organization_id:
            query = query.filter(PURLWorkspace.organization_id == organization_id)

        return query.first()

    def get_workspace_by_slug(
        self,
        organization_id: int,
        slug: str
    ) -> Optional[PURLWorkspace]:
        """Get workspace by slug."""
        return self.db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == organization_id,
            PURLWorkspace.slug == slug
        ).first()

    def update_workspace(
        self,
        workspace_id: int,
        updates: Dict[str, Any]
    ) -> Optional[PURLWorkspace]:
        """Update workspace fields."""
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        ).first()

        if not workspace:
            return None

        # Update allowed fields
        allowed_fields = ["display_name", "source", "owner_user_id", "metadata"]
        for field in allowed_fields:
            if field in updates and updates[field] is not None:
                setattr(workspace, field, updates[field])

        self.db.commit()
        self.db.refresh(workspace)

        return workspace

    def update_workspace_status(
        self,
        workspace_id: int,
        new_status: WorkspaceStatus
    ) -> bool:
        """
        Update workspace lifecycle status with timestamp tracking.

        Returns:
            True if successful
        """
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        ).first()

        if not workspace:
            return False

        old_status = workspace.status
        workspace.status = new_status.value
        now = datetime.now(timezone.utc)

        # Update appropriate timestamp
        if new_status == WorkspaceStatus.APPLICATION:
            workspace.application_at = now
        elif new_status == WorkspaceStatus.ACTIVE_LOAN:
            workspace.active_loan_at = now
        elif new_status == WorkspaceStatus.CLOSING:
            workspace.closing_at = now
            # Enable closing vault module
            self._enable_module(workspace_id, PortalModule.CLOSING_VAULT)
        elif new_status == WorkspaceStatus.POST_CLOSE:
            workspace.post_close_at = now

        self.db.commit()

        # Emit event
        self._emit_event(
            organization_id=workspace.organization_id,
            workspace_id=workspace_id,
            event_key=f"workspace_status_changed_{new_status.value}",
            payload={
                "workspace_id": workspace_id,
                "old_status": old_status,
                "new_status": new_status.value
            }
        )

        logger.info(f"Workspace {workspace_id} status: {old_status} -> {new_status.value}")
        return True

    # =========================================================================
    # COMPLETE WORKSPACE DATA
    # =========================================================================

    def get_complete_workspace_data(
        self,
        organization_id: int,
        workspace_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get complete workspace data for borrower portal.

        Returns comprehensive workspace data including contacts,
        loans, documents, tasks, and module configuration.
        """
        try:
            logger.info(f"get_complete_workspace_data: Starting for workspace_id={workspace_id}, org_id={organization_id}")

            workspace = self.db.query(PURLWorkspace).filter(
                PURLWorkspace.id == workspace_id,
                PURLWorkspace.organization_id == organization_id
            ).first()

            if not workspace:
                logger.warning(f"get_complete_workspace_data: Workspace not found")
                return None

            logger.debug(f"get_complete_workspace_data: Found workspace {workspace.slug}")

            # Get contacts
            contacts = self.db.query(PURLContact).filter(
                PURLContact.workspace_id == workspace_id
            ).all()
            logger.debug(f"get_complete_workspace_data: Found {len(contacts)} contacts")

            # Get application (in-progress or submitted)
            application = self.db.query(PURLApplication).filter(
                PURLApplication.workspace_id == workspace_id,
                PURLApplication.status.in_([
                    ApplicationStatus.IN_PROGRESS.value,
                    ApplicationStatus.SUBMITTED.value
                ])
            ).order_by(PURLApplication.version.desc()).first()
            logger.debug(f"get_complete_workspace_data: Application found: {application is not None}")

            # Get loans
            loans = self.db.query(PURLLoan).filter(
                PURLLoan.workspace_id == workspace_id
            ).order_by(PURLLoan.created_at.desc()).all()
            logger.debug(f"get_complete_workspace_data: Found {len(loans)} loans")

            # Get current active loan
            current_loan = next(
                (l for l in loans if l.status in ["active", "processing", "underwriting", "closing"]),
                None
            )

            # Get portal modules - initialize if none exist
            modules = []
            try:
                modules = self.db.query(PURLPortalModule).filter(
                    PURLPortalModule.workspace_id == workspace_id
                ).order_by(PURLPortalModule.order_index).all()

                if not modules:
                    # Initialize default modules for workspaces created before module system
                    logger.info(f"Initializing default portal modules for workspace {workspace_id}")
                    self._initialize_portal_modules(organization_id, workspace_id)
                    self.db.commit()
                    # Re-fetch modules after initialization
                    modules = self.db.query(PURLPortalModule).filter(
                        PURLPortalModule.workspace_id == workspace_id
                    ).order_by(PURLPortalModule.order_index).all()
            except SQLAlchemyError as e:
                logger.warning(f"Failed to query/initialize portal modules: {e}")
                self.db.rollback()
                # Return default modules as fallback (without persisting)
                modules = []

            logger.debug(f"get_complete_workspace_data: Found {len(modules)} modules")

            # Get tasks (all, not just pending)
            tasks = self.db.query(PURLTask).filter(
                PURLTask.workspace_id == workspace_id
            ).order_by(PURLTask.due_at.asc().nullslast()).all()
            logger.debug(f"get_complete_workspace_data: Found {len(tasks)} tasks")

            # Get documents
            documents = self.db.query(PURLDocument).filter(
                PURLDocument.workspace_id == workspace_id
            ).order_by(PURLDocument.created_at.desc()).all()
            logger.debug(f"get_complete_workspace_data: Found {len(documents)} documents")

            # Get document requirements from Smart Docs if available
            document_requirements = []
            if SMART_DOCS_AVAILABLE and current_loan:
                try:
                    requests = self.db.query(DocumentRequest).filter(
                        DocumentRequest.loan_id == current_loan.id
                    ).order_by(DocumentRequest.priority.desc(), DocumentRequest.created_at).all()

                    document_requirements = [
                        self._document_request_to_dict(req)
                        for req in requests
                    ]
                    logger.info(f"Loaded {len(document_requirements)} document requirements for loan {current_loan.id}")
                except Exception as e:
                    logger.warning(f"Failed to load document requirements: {e}")

            # If no Smart Docs requests exist, generate from application and persist
            if not document_requirements and SMART_DOCS_AVAILABLE and current_loan:
                try:
                    app_data = {}
                    if application:
                        app_data = application.data if hasattr(application, 'data') else {}
                        logger.info(f"Generating document requirements from application data: {app_data.get('declarations', {})}")
                    else:
                        logger.info("No application found, generating default document requirements")
                    app_requirements = calculate_document_requirements_from_application(app_data)
                    logger.info(f"Generated {len(app_requirements)} document requirements from application data")

                    # Persist each as a DocumentRequest so Smart Docs becomes the single source of truth
                    persisted_requests = []
                    for req_data in app_requirements:
                        doc_type = _map_app_id_to_doc_type(req_data.get("id", ""))
                        applies_to_val = "CO_BORROWER" if "coborrower" in req_data.get("id", "") else "BORROWER"
                        new_req = DocumentRequest(
                            organization_id=current_loan.organization_id,
                            loan_id=current_loan.id,
                            doc_type=doc_type,
                            title=req_data.get("name", req_data.get("id", "Document")),
                            description=req_data.get("description"),
                            status="OPEN",
                            is_required=True,
                            priority="NORMAL",
                            applies_to=applies_to_val,
                        )
                        self.db.add(new_req)
                        persisted_requests.append(new_req)

                    self.db.flush()  # Assign IDs without committing full transaction

                    # Re-query to get the persisted versions with IDs
                    document_requirements = [
                        self._document_request_to_dict(req)
                        for req in persisted_requests
                    ]
                    logger.info(f"Persisted {len(document_requirements)} document requirements as Smart Docs requests for loan {current_loan.id}")
                except Exception as e:
                    logger.error(f"Failed to generate/persist document requirements from application: {e}", exc_info=True)
                    # Rollback to clear the failed transaction state so subsequent queries can proceed
                    self.db.rollback()

            # If still no requirements (Smart Docs not available or persistence failed), use fallback
            if not document_requirements:
                try:
                    app_data = {}
                    if application:
                        app_data = application.data if hasattr(application, 'data') else {}
                    document_requirements = calculate_document_requirements_from_application(app_data)
                except Exception as e:
                    logger.error(f"Failed to generate fallback document requirements: {e}", exc_info=True)
                    self.db.rollback()
                    # Provide default documents as ultimate fallback
                    document_requirements = [
                        {'id': 'id', 'name': 'Government ID', 'description': "Driver's license or passport", 'category': 'identity', 'status': 'pending'},
                        {'id': 'paystubs', 'name': 'Pay Stubs', 'description': 'Last 30 days (most recent)', 'category': 'income_verification', 'status': 'pending'},
                        {'id': 'w2', 'name': 'W-2 Forms', 'description': 'Last 2 years', 'category': 'income_verification', 'status': 'pending'},
                        {'id': 'bank_statements', 'name': 'Bank Statements', 'description': 'Last 2 months (all pages)', 'category': 'asset_verification', 'status': 'pending'},
                    ]

            # Get milestones if loan exists
            milestones = []
            if current_loan:
                try:
                    milestone_records = self.db.query(PURLLoanMilestone).filter(
                        PURLLoanMilestone.loan_id == current_loan.id
                    ).order_by(PURLLoanMilestone.id).all()
                    milestones = [self._milestone_to_dict(m) for m in milestone_records]
                except SQLAlchemyError as e:
                    logger.warning(f"Failed to load milestones: {e}")
                    self.db.rollback()
            logger.debug(f"get_complete_workspace_data: Found {len(milestones)} milestones")

            # Get timeline (audit log entries)
            timeline_records = self.db.query(PURLAuditLog).filter(
                PURLAuditLog.workspace_id == workspace_id
            ).order_by(PURLAuditLog.created_at.desc()).limit(20).all()

            timeline = [
                {
                    "id": t.id,
                    "action": t.action,
                    "actor_type": t.actor_type,
                    "resource_type": t.resource_type,
                    "resource_id": t.resource_id,
                    "metadata": t.meta_data,
                    "created_at": t.created_at.isoformat() if t.created_at else None
                }
                for t in timeline_records
            ]
            logger.debug(f"get_complete_workspace_data: Built {len(timeline)} timeline entries")

            # Get unread message count
            unread_count = self.db.query(func.count(PURLMessage.id)).filter(
                PURLMessage.workspace_id == workspace_id,
                PURLMessage.is_read_by_borrower == False
            ).scalar() or 0

            # Get linked lead information if available
            lead_data = None
            lead_id = workspace.meta_data.get('lead_id') if workspace.meta_data else None
            if lead_id:
                try:
                    from database.models import Lead
                    lead = self.db.query(Lead).filter(Lead.id == int(lead_id)).first()
                    if lead:
                        lead_data = {
                            "id": lead.id,
                            "stage": lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None,
                            "name": lead.name,
                            "first_name": lead.first_name,
                            "last_name": lead.last_name
                        }
                except SQLAlchemyError as e:
                    logger.warning(f"Failed to fetch linked lead {lead_id}: {e}")

            # Get loan officer info from workspace owner
            loan_officer_data = None
            if workspace.owner_user_id:
                try:
                    from database.models import User
                    lo_user = self.db.query(User).filter(User.id == workspace.owner_user_id).first()
                    if lo_user:
                        loan_officer_data = {
                            "id": lo_user.id,
                            "name": lo_user.full_name or lo_user.email.split('@')[0] if lo_user.email else 'Loan Officer',
                            "email": lo_user.email,
                            "phone": lo_user.phone,
                            "nmls_id": getattr(lo_user, 'nmls_id', None),
                            "headshot_url": getattr(lo_user, 'headshot_url', None),
                            "company_logo_url": getattr(lo_user, 'company_logo_url', None),
                            "title": getattr(lo_user, 'title', None),
                            "team_name": getattr(lo_user, 'team_name', None),
                        }
                        logger.info(f"Loaded LO info for workspace {workspace.id}: {loan_officer_data.get('name')}")
                except SQLAlchemyError as e:
                    logger.warning(f"Failed to fetch loan officer {workspace.owner_user_id}: {e}")

            logger.debug(f"get_complete_workspace_data: Building final response dict")

            result = {
                "workspace": self._workspace_to_dict(workspace),
                "contacts": [self._contact_to_dict(c) for c in contacts],
                "application": self._application_to_dict(application) if application else None,
                "loan": self._loan_to_dict(current_loan) if current_loan else None,
                "lead": lead_data,  # Include linked lead data for milestone sync
                "loanOfficer": loan_officer_data,  # Include LO info for portal display
                "documents": [self._document_to_dict(d) for d in documents],
                "document_requirements": document_requirements,  # Smart Docs needs list
                "tasks": [self._task_to_dict(t) for t in tasks],
                "milestones": milestones,
                "timeline": timeline,
                "modules": [self._module_to_dict(m) for m in modules] if modules else self._get_default_modules(),
                # Extra fields for backwards compatibility
                "unread_messages_count": unread_count
            }
            logger.info(f"get_complete_workspace_data: Successfully built response for workspace {workspace_id}")
            return result

        except Exception as e:
            logger.error(f"get_complete_workspace_data: Error for workspace {workspace_id}: {e}", exc_info=True)
            raise

    # =========================================================================
    # CONTACT MANAGEMENT
    # =========================================================================

    def add_contact(
        self,
        organization_id: int,
        workspace_id: int,
        data: ContactCreate
    ) -> int:
        """
        Add a contact to workspace.

        Returns:
            Contact ID
        """
        contact = PURLContact(
            organization_id=organization_id,
            workspace_id=workspace_id,
            contact_type=data.contact_type.value,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            meta_data=data.metadata or {}
        )

        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)

        # Emit event
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            event_key="contact_added",
            payload={
                "contact_id": contact.id,
                "contact_type": data.contact_type.value,
                "email": data.email
            }
        )

        logger.info(f"Added contact {contact.id} to workspace {workspace_id}")
        return contact.id

    def get_workspace_contacts(self, workspace_id: int) -> List[PURLContact]:
        """Get all contacts for a workspace."""
        return self.db.query(PURLContact).filter(
            PURLContact.workspace_id == workspace_id
        ).all()

    def update_contact(
        self,
        contact_id: int,
        updates: Dict[str, Any]
    ) -> Optional[PURLContact]:
        """Update contact fields."""
        contact = self.db.query(PURLContact).filter(
            PURLContact.id == contact_id
        ).first()

        if not contact:
            return None

        allowed_fields = ["first_name", "last_name", "email", "phone", "metadata"]
        for field in allowed_fields:
            if field in updates and updates[field] is not None:
                setattr(contact, field, updates[field])

        self.db.commit()
        self.db.refresh(contact)

        return contact

    # =========================================================================
    # MEMBER MANAGEMENT
    # =========================================================================

    def add_member(
        self,
        organization_id: int,
        workspace_id: int,
        user_id: int,
        role: MemberRole
    ) -> int:
        """Add a team member to workspace."""
        # Check if already a member
        existing = self.db.query(PURLWorkspaceMember).filter(
            PURLWorkspaceMember.workspace_id == workspace_id,
            PURLWorkspaceMember.user_id == user_id
        ).first()

        if existing:
            # Update role
            existing.role = role.value
            self.db.commit()
            return existing.id

        member = PURLWorkspaceMember(
            organization_id=organization_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role.value
        )

        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)

        logger.info(f"Added member {user_id} to workspace {workspace_id} as {role.value}")
        return member.id

    def remove_member(self, workspace_id: int, user_id: int) -> bool:
        """Remove a team member from workspace."""
        result = self.db.query(PURLWorkspaceMember).filter(
            PURLWorkspaceMember.workspace_id == workspace_id,
            PURLWorkspaceMember.user_id == user_id
        ).delete()

        self.db.commit()
        return result > 0

    def get_workspace_members(self, workspace_id: int) -> List[Dict[str, Any]]:
        """Get all team members for a workspace."""
        members = self.db.query(PURLWorkspaceMember).filter(
            PURLWorkspaceMember.workspace_id == workspace_id
        ).all()

        return [
            {
                "id": m.id,
                "user_id": m.user_id,
                "role": m.role,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in members
        ]

    def user_has_workspace_access(
        self,
        user_id: int,
        workspace_id: int
    ) -> bool:
        """Check if user has access to workspace."""
        return self.db.query(PURLWorkspaceMember).filter(
            PURLWorkspaceMember.workspace_id == workspace_id,
            PURLWorkspaceMember.user_id == user_id
        ).first() is not None

    # =========================================================================
    # PORTAL MODULE MANAGEMENT
    # =========================================================================

    def _initialize_portal_modules(
        self,
        organization_id: int,
        workspace_id: int
    ):
        """Initialize default portal modules for new workspace."""
        for module_config in DEFAULT_PORTAL_MODULES:
            module = PURLPortalModule(
                organization_id=organization_id,
                workspace_id=workspace_id,
                module_key=module_config["module_key"],
                is_enabled=module_config["is_enabled"],
                is_visible=module_config["is_visible"],
                order_index=module_config["order_index"],
                config=module_config["config"]
            )
            self.db.add(module)

    def _enable_module(self, workspace_id: int, module: PortalModule):
        """Enable a specific portal module."""
        self.db.query(PURLPortalModule).filter(
            PURLPortalModule.workspace_id == workspace_id,
            PURLPortalModule.module_key == module.value
        ).update({
            "is_enabled": True,
            "is_visible": True
        })
        self.db.commit()

    def update_module_config(
        self,
        workspace_id: int,
        module_key: str,
        config: Dict[str, Any]
    ) -> bool:
        """Update module configuration."""
        module = self.db.query(PURLPortalModule).filter(
            PURLPortalModule.workspace_id == workspace_id,
            PURLPortalModule.module_key == module_key
        ).first()

        if not module:
            return False

        module.config = config
        module.config_version += 1
        self.db.commit()

        return True

    # =========================================================================
    # SEARCH & LISTING
    # =========================================================================

    def search_workspaces(
        self,
        organization_id: int,
        query: Optional[str] = None,
        status: Optional[WorkspaceStatus] = None,
        owner_user_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[PURLWorkspace], int]:
        """
        Search workspaces with filtering.

        Returns:
            Tuple of (workspaces, total_count)
        """
        base_query = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == organization_id
        )

        if query:
            search_term = f"%{query}%"
            base_query = base_query.filter(
                or_(
                    PURLWorkspace.display_name.ilike(search_term),
                    PURLWorkspace.slug.ilike(search_term)
                )
            )

        if status:
            base_query = base_query.filter(PURLWorkspace.status == status.value)

        if owner_user_id:
            base_query = base_query.filter(PURLWorkspace.owner_user_id == owner_user_id)

        total = base_query.count()

        workspaces = base_query.order_by(
            PURLWorkspace.updated_at.desc()
        ).offset(offset).limit(limit).all()

        return workspaces, total

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _workspace_to_dict(self, workspace: PURLWorkspace) -> Dict[str, Any]:
        """Convert workspace to dict."""
        return {
            "id": workspace.id,
            "organization_id": workspace.organization_id,
            "slug": workspace.slug,
            "status": workspace.status,
            "display_name": workspace.display_name,
            "source": workspace.source,
            "owner_user_id": workspace.owner_user_id,
            "lead_at": workspace.lead_at.isoformat() if workspace.lead_at else None,
            "application_at": workspace.application_at.isoformat() if workspace.application_at else None,
            "active_loan_at": workspace.active_loan_at.isoformat() if workspace.active_loan_at else None,
            "closing_at": workspace.closing_at.isoformat() if workspace.closing_at else None,
            "post_close_at": workspace.post_close_at.isoformat() if workspace.post_close_at else None,
            "metadata": workspace.meta_data,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
            "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None
        }

    def _contact_to_dict(self, contact: PURLContact) -> Dict[str, Any]:
        """Convert contact to dict."""
        return {
            "id": contact.id,
            "organization_id": contact.organization_id,
            "workspace_id": contact.workspace_id,
            "contact_type": contact.contact_type,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "email": contact.email,
            "phone": contact.phone,
            "auth_user_id": contact.auth_user_id,
            "auth_provider": contact.auth_provider,
            "metadata": contact.meta_data,
            "created_at": contact.created_at.isoformat() if contact.created_at else None,
            "updated_at": contact.updated_at.isoformat() if contact.updated_at else None
        }

    def _loan_to_dict(self, loan: PURLLoan) -> Dict[str, Any]:
        """Convert loan to dict."""
        return {
            "id": loan.id,
            # CRM loan id (= PURLLoan.main_loan_id). This is the id-space the
            # borrower dashboard endpoints resolve against (PortalLoan.crm_deal_id).
            # The frontend MUST use this — NOT `id` (PURLLoan.id) — when calling
            # /api/v1/portal/borrower/{loan_id}/dashboard. Exposed under both keys:
            # `crm_loan_id` (canonical) and `main_loan_id` (raw column name).
            "crm_loan_id": loan.main_loan_id,
            "main_loan_id": loan.main_loan_id,
            "organization_id": loan.organization_id,
            "workspace_id": loan.workspace_id,
            "application_id": loan.application_id,
            "loan_number": loan.loan_number,
            "status": loan.status,
            "loan_purpose": loan.loan_purpose,
            "product_type": loan.product_type,
            "loan_amount": float(loan.loan_amount) if loan.loan_amount else None,
            "interest_rate": float(loan.interest_rate) if loan.interest_rate else None,
            "property_address": loan.property_address,
            "property_type": loan.property_type,
            "target_close_date": loan.target_close_date.isoformat() if loan.target_close_date else None,
            "actual_close_date": loan.actual_close_date.isoformat() if loan.actual_close_date else None,
            "los_loan_id": loan.los_loan_id,
            "metadata": loan.meta_data,
            "created_at": loan.created_at.isoformat() if loan.created_at else None,
            "updated_at": loan.updated_at.isoformat() if loan.updated_at else None
        }

    def _module_to_dict(self, module: PURLPortalModule) -> Dict[str, Any]:
        """Convert module to dict."""
        return {
            "id": module.id,
            "module_key": module.module_key,
            "is_enabled": module.is_enabled,
            "is_visible": module.is_visible,
            "order_index": module.order_index,
            "config": module.config,
            "config_version": module.config_version
        }

    def _get_default_modules(self) -> List[Dict[str, Any]]:
        """Return default module configuration when database table doesn't exist."""
        return [
            {
                "id": None,
                "module_key": config["module_key"],
                "is_enabled": config["is_enabled"],
                "is_visible": config["is_visible"],
                "order_index": config["order_index"],
                "config": config["config"],
                "config_version": 1
            }
            for config in DEFAULT_PORTAL_MODULES
        ]

    def _task_to_dict(self, task: PURLTask) -> Dict[str, Any]:
        """Convert task to dict."""
        return {
            "id": task.id,
            "organization_id": task.organization_id,
            "workspace_id": task.workspace_id,
            "loan_id": task.loan_id,
            "title": task.title,
            "description": task.description,
            "task_type": task.task_type,
            "status": task.status,
            "priority": task.priority,
            "assigned_to_user_id": task.assigned_to_user_id,
            "assigned_to_contact_id": task.assigned_to_contact_id,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "metadata": task.meta_data,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }

    def _document_to_dict(self, doc: PURLDocument) -> Dict[str, Any]:
        """Convert document to dict."""
        return {
            "id": doc.id,
            "organization_id": doc.organization_id,
            "workspace_id": doc.workspace_id,
            "loan_id": doc.loan_id,
            "doc_type": doc.doc_type,
            "doc_category": doc.doc_category,
            "status": doc.status,
            "file_name": doc.file_name,
            "size_bytes": doc.size_bytes,
            "mime_type": doc.mime_type,
            "sha256": doc.sha256,
            "uploaded_by_contact_id": doc.uploaded_by_contact_id,
            "uploaded_by_user_id": doc.uploaded_by_user_id,
            "retention_policy": doc.retention_policy,
            "legal_hold": doc.legal_hold,
            "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
        }

    def _application_to_dict(self, application: PURLApplication) -> Dict[str, Any]:
        """Convert application to dict."""
        return {
            "id": application.id,
            "organization_id": application.organization_id,
            "workspace_id": application.workspace_id,
            "application_type": application.application_type,
            "status": application.status,
            "version": application.version,
            "data": application.data,
            "derived": application.derived,
            "validation_errors": application.validation_errors,
            "completeness_pct": application.completeness_pct,
            "started_at": application.started_at.isoformat() if application.started_at else None,
            "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None,
            "created_at": application.created_at.isoformat() if application.created_at else None,
            "updated_at": application.updated_at.isoformat() if application.updated_at else None
        }

    def _milestone_to_dict(self, milestone: PURLLoanMilestone) -> Dict[str, Any]:
        """Convert milestone to dict."""
        return {
            "id": milestone.id,
            "organization_id": milestone.organization_id,
            "loan_id": milestone.loan_id,
            "milestone_definition_id": milestone.milestone_definition_id,
            "status": milestone.status,
            "started_at": milestone.started_at.isoformat() if milestone.started_at else None,
            "completed_at": milestone.completed_at.isoformat() if milestone.completed_at else None,
            "due_at": milestone.due_at.isoformat() if milestone.due_at else None,
            "metadata": milestone.meta_data if hasattr(milestone, 'meta_data') else {},
            "created_at": milestone.created_at.isoformat() if milestone.created_at else None
        }

    def _document_request_to_dict(self, req) -> Dict[str, Any]:
        """Convert a DocumentRequest model to a dictionary for the PURL portal.

        Uses the new is_required and fulfilled_at columns, with safe fallbacks
        for rows that were created before the migration ran.
        """
        # Safe access for is_required: defaults to True if column doesn't exist yet
        is_required = getattr(req, 'is_required', True)
        if is_required is None:
            is_required = True

        # Safe access for fulfilled_at: fall back to completed_at if fulfilled_at not set
        fulfilled_at = getattr(req, 'fulfilled_at', None) or getattr(req, 'completed_at', None)

        return {
            "id": req.id,
            "doc_type": req.doc_type.value if hasattr(req.doc_type, 'value') else str(req.doc_type),
            "title": req.title,
            "description": req.description,
            "instructions": req.instructions,
            "status": req.status.value if hasattr(req.status, 'value') else str(req.status),
            "priority": req.priority.value if hasattr(req.priority, 'value') else str(req.priority),
            "due_date": req.due_date.isoformat() if req.due_date else None,
            "applies_to": req.applies_to.value if hasattr(req.applies_to, 'value') else str(req.applies_to),
            "is_required": is_required,
            "fulfilled_at": fulfilled_at.isoformat() if fulfilled_at else None,
        }

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
