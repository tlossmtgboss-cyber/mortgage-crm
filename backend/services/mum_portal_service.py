"""
MUM (Mortgages Under Management) Portal Service

Provides business logic for MUM client portal operations:
- Creating portal workspaces for funded clients
- Managing post-close client communication
- Video messages, documents, and LO updates
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from models.purl import (
    PURLWorkspace,
    PURLContact,
    PURLWorkspaceMember,
    PURLPortalModule,
    PURLMessage,
    PURLDocument,
    PURLAccessToken,
    WorkspaceStatus,
    ContactType,
    MemberRole,
    PortalModule,
    TokenScope,
    TokenStatus,
    SlugGenerator,
    WorkspaceCreate,
    PURLTokenGenerator,
)
from models.mum_client_profile import MUMClientProfile
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# Portal modules for MUM clients (post-close focused)
MUM_PORTAL_MODULES = [
    {
        "module_key": PortalModule.MESSAGES.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 1,
        "config": {"title": "Messages", "description": "Video and text messages from your loan officer"}
    },
    {
        "module_key": PortalModule.DOCUMENTS.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 2,
        "config": {"title": "Documents", "description": "Important documents and records"}
    },
    {
        "module_key": PortalModule.RESOURCES.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 3,
        "config": {"title": "Resources", "description": "Homeowner resources and guides"}
    },
    {
        "module_key": PortalModule.TIMELINE.value,
        "is_enabled": True,
        "is_visible": True,
        "order_index": 4,
        "config": {"title": "Your Journey", "description": "Your mortgage timeline and milestones"}
    },
]


class MUMPortalService:
    """
    Service for MUM client portal operations.

    MUM (Mortgages Under Management) portals are for post-close clients:
    - Allows LOs to send video messages
    - Enables document sharing (closing docs, tax forms, etc.)
    - Provides home value intelligence and refinance opportunities
    """

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_portal(
        self,
        mum_client_id: str,
        organization_id: int,
        owner_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get existing portal or create a new one for a MUM client.

        Args:
            mum_client_id: UUID of the MUM client
            organization_id: Organization ID
            owner_user_id: Loan officer user ID

        Returns:
            Dict with portal_url, slug, workspace_id, created (bool)
        """
        # Check if portal already exists
        existing = self._get_existing_portal(mum_client_id, organization_id)
        if existing:
            return {
                "portal_url": self._build_portal_url(existing.slug),
                "slug": existing.slug,
                "workspace_id": existing.id,
                "created": False,
                "status": existing.status
            }

        # Create new portal
        return self.create_portal(mum_client_id, organization_id, owner_user_id)

    def create_portal(
        self,
        mum_client_id: str,
        organization_id: int,
        owner_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new portal workspace for a MUM client.

        Args:
            mum_client_id: UUID of the MUM client
            organization_id: Organization ID
            owner_user_id: Loan officer user ID

        Returns:
            Dict with portal_url, slug, workspace_id, created=True
        """
        # Get MUM client
        client = self.db.query(MUMClientProfile).filter(
            MUMClientProfile.id == mum_client_id,
            MUMClientProfile.is_deleted == False
        ).first()

        if not client:
            raise ValueError(f"MUM client {mum_client_id} not found")

        # Determine owner (LO)
        if not owner_user_id and client.loan_officer_email:
            # Try to find LO by email
            try:
                from database.models import User
                lo = self.db.query(User).filter(
                    User.email == client.loan_officer_email
                ).first()
                if lo:
                    owner_user_id = lo.id
            except SQLAlchemyError as e:
                logger.warning(f"Could not find LO by email: {e}")

        # Generate unique slug from client name
        slug = self._generate_unique_slug(client.name, organization_id)

        # Create workspace with POST_CLOSE status
        workspace = PURLWorkspace(
            organization_id=organization_id,
            slug=slug,
            display_name=client.name,
            status=WorkspaceStatus.POST_CLOSE.value,
            source="mum_client",
            owner_user_id=owner_user_id,
            meta_data={
                "mum_client_id": str(mum_client_id),
                "portal_type": "mum",
                "loan_number": client.loan_number,
                "original_close_date": client.original_close_date.isoformat() if client.original_close_date else None,
            },
            post_close_at=datetime.now(timezone.utc)
        )

        self.db.add(workspace)
        self.db.flush()

        # Add owner as workspace member
        if owner_user_id:
            member = PURLWorkspaceMember(
                organization_id=organization_id,
                workspace_id=workspace.id,
                user_id=owner_user_id,
                role=MemberRole.OWNER.value
            )
            self.db.add(member)

        # Add client as primary contact
        contact = PURLContact(
            organization_id=organization_id,
            workspace_id=workspace.id,
            contact_type=ContactType.BORROWER.value,
            first_name=self._extract_first_name(client.name),
            last_name=self._extract_last_name(client.name),
            email=client.email,
            phone=client.phone,
            meta_data={"mum_client_id": str(mum_client_id)}
        )
        self.db.add(contact)
        self.db.flush()

        # Initialize MUM-specific portal modules
        self._initialize_mum_modules(organization_id, workspace.id)

        # Create access token for client
        token_info = self._create_access_token(
            organization_id=organization_id,
            workspace_id=workspace.id,
            contact_id=contact.id,
            scope=TokenScope.WRITE
        )

        self.db.commit()

        logger.info(f"Created MUM portal for client {mum_client_id}: {slug}")

        return {
            "portal_url": self._build_portal_url(slug),
            "slug": slug,
            "workspace_id": workspace.id,
            "contact_id": contact.id,
            "access_token": token_info.get("token"),  # For magic link
            "created": True,
            "status": workspace.status
        }

    def get_portal_data(
        self,
        slug: str,
        organization_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get complete portal data for client view.

        Args:
            slug: Portal workspace slug
            organization_id: Optional org filter

        Returns:
            Complete portal data dict or None
        """
        query = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.slug == slug,
            PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
        )

        if organization_id:
            query = query.filter(PURLWorkspace.organization_id == organization_id)

        workspace = query.first()
        if not workspace:
            return None

        # Get MUM client data
        mum_client = None
        mum_client_id = workspace.meta_data.get("mum_client_id") if workspace.meta_data else None
        if mum_client_id:
            mum_client = self.db.query(MUMClientProfile).filter(
                MUMClientProfile.id == mum_client_id
            ).first()

        # Get contacts
        contacts = self.db.query(PURLContact).filter(
            PURLContact.workspace_id == workspace.id
        ).all()

        # Get video messages (from portal_video_messages table or PURLMessage)
        messages = self.db.query(PURLMessage).filter(
            PURLMessage.workspace_id == workspace.id
        ).order_by(PURLMessage.created_at.desc()).limit(20).all()

        # Get documents
        documents = self.db.query(PURLDocument).filter(
            PURLDocument.workspace_id == workspace.id
        ).order_by(PURLDocument.created_at.desc()).all()

        # Get modules
        modules = self.db.query(PURLPortalModule).filter(
            PURLPortalModule.workspace_id == workspace.id
        ).order_by(PURLPortalModule.order_index).all()

        # Get loan officer info
        loan_officer = None
        if workspace.owner_user_id:
            try:
                from database.models import User
                lo = self.db.query(User).filter(User.id == workspace.owner_user_id).first()
                if lo:
                    loan_officer = {
                        "id": lo.id,
                        "name": lo.full_name or lo.email.split('@')[0] if lo.email else 'Loan Officer',
                        "email": lo.email,
                        "phone": lo.phone,
                        "nmls_id": getattr(lo, 'nmls_id', None),
                        "headshot_url": getattr(lo, 'headshot_url', None),
                        "title": getattr(lo, 'title', None),
                    }
            except SQLAlchemyError as e:
                logger.warning(f"Could not load LO info: {e}")

        # Get unread count
        unread_count = self.db.query(func.count(PURLMessage.id)).filter(
            PURLMessage.workspace_id == workspace.id,
            PURLMessage.is_read_by_borrower == False
        ).scalar() or 0

        return {
            "workspace": {
                "id": workspace.id,
                "slug": workspace.slug,
                "display_name": workspace.display_name,
                "status": workspace.status,
                "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
                "post_close_at": workspace.post_close_at.isoformat() if workspace.post_close_at else None,
            },
            "mum_client": self._mum_client_to_dict(mum_client) if mum_client else None,
            "contacts": [self._contact_to_dict(c) for c in contacts],
            "messages": [self._message_to_dict(m) for m in messages],
            "documents": [self._document_to_dict(d) for d in documents],
            "modules": [self._module_to_dict(m) for m in modules] if modules else self._get_default_mum_modules(),
            "loanOfficer": loan_officer,
            "unread_messages_count": unread_count,
        }

    def post_message(
        self,
        workspace_id: int,
        content: str,
        sender_user_id: int,
        message_type: str = "text",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Post a message from LO to client portal.

        Args:
            workspace_id: Portal workspace ID
            content: Message content
            sender_user_id: LO user ID
            message_type: 'text' or 'video'
            metadata: Additional metadata (video_url, etc.)

        Returns:
            Created message dict
        """
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id
        ).first()

        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        message = PURLMessage(
            organization_id=workspace.organization_id,
            workspace_id=workspace_id,
            message_type=message_type,
            content=content,
            sender_type="user",
            sender_user_id=sender_user_id,
            is_read_by_borrower=False,
            meta_data=metadata or {}
        )

        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        logger.info(f"Posted {message_type} message to workspace {workspace_id}")

        return self._message_to_dict(message)

    def get_portal_by_mum_client(
        self,
        mum_client_id: str,
        organization_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get portal info by MUM client ID.
        """
        workspace = self._get_existing_portal(mum_client_id, organization_id)
        if not workspace:
            return None

        return {
            "portal_url": self._build_portal_url(workspace.slug),
            "slug": workspace.slug,
            "workspace_id": workspace.id,
            "status": workspace.status,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
        }

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _get_existing_portal(
        self,
        mum_client_id: str,
        organization_id: int
    ) -> Optional[PURLWorkspace]:
        """Find existing portal for MUM client."""
        # Search by metadata
        workspaces = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == organization_id,
            PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value
        ).all()

        for ws in workspaces:
            if ws.meta_data and ws.meta_data.get("mum_client_id") == str(mum_client_id):
                return ws

        return None

    def _generate_unique_slug(self, name: str, organization_id: int) -> str:
        """Generate unique slug for MUM portal."""
        # Parse name
        parts = name.strip().split()
        first_name = parts[0] if parts else "client"
        last_name = parts[-1] if len(parts) > 1 else ""

        # Get existing slugs
        existing_slugs = [
            ws.slug for ws in self.db.query(PURLWorkspace.slug).filter(
                PURLWorkspace.organization_id == organization_id
            ).all()
        ]

        # Generate unique slug
        base_slug = SlugGenerator.generate_from_name(first_name, last_name)

        # Add "-mum" suffix to distinguish from active loan portals
        mum_slug = f"{base_slug}-mum"

        if mum_slug not in existing_slugs:
            return mum_slug

        # Find next available
        counter = 2
        while f"{mum_slug}{counter}" in existing_slugs:
            counter += 1

        return f"{mum_slug}{counter}"

    def _initialize_mum_modules(self, organization_id: int, workspace_id: int):
        """Initialize MUM-specific portal modules."""
        for module_config in MUM_PORTAL_MODULES:
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

    def _create_access_token(
        self,
        organization_id: int,
        workspace_id: int,
        contact_id: int,
        scope: TokenScope
    ) -> Dict[str, Any]:
        """Create access token for client."""
        full_token, token_hash, token_prefix = PURLTokenGenerator.generate_token()

        token = PURLAccessToken(
            organization_id=organization_id,
            workspace_id=workspace_id,
            token_hash=token_hash,
            token_prefix=token_prefix,
            scope=scope.value,
            status=TokenStatus.ACTIVE.value,
            contact_id=contact_id
        )

        self.db.add(token)
        self.db.flush()

        return {
            "token_id": token.id,
            "token": full_token,
            "prefix": token_prefix
        }

    def _build_portal_url(self, slug: str) -> str:
        """Build the full portal URL.

        Uses /portal/ route which is handled by PortalContainer that
        automatically routes to MUMPortal based on workspace status.
        """
        base_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
        return f"{base_url}/portal/{slug}"

    def _extract_first_name(self, full_name: str) -> str:
        """Extract first name from full name."""
        parts = full_name.strip().split()
        return parts[0] if parts else "Client"

    def _extract_last_name(self, full_name: str) -> str:
        """Extract last name from full name."""
        parts = full_name.strip().split()
        return parts[-1] if len(parts) > 1 else ""

    def _mum_client_to_dict(self, client: MUMClientProfile) -> Dict[str, Any]:
        """Convert MUM client to dict."""
        return {
            "id": str(client.id),
            "name": client.name,
            "email": client.email,
            "phone": client.phone,
            "loan_number": client.loan_number,
            "original_close_date": client.original_close_date.isoformat() if client.original_close_date else None,
            "original_rate": float(client.original_rate) if client.original_rate else None,
            "current_rate": float(client.current_rate) if client.current_rate else None,
            "loan_balance": float(client.loan_balance) if client.loan_balance else None,
            "estimated_savings": float(client.estimated_savings) if client.estimated_savings else None,
            "refinance_opportunity": client.refinance_opportunity,
            "loan_officer": client.loan_officer,
            "engagement_score": client.engagement_score,
            "last_contact": client.last_contact.isoformat() if client.last_contact else None,
        }

    def _contact_to_dict(self, contact: PURLContact) -> Dict[str, Any]:
        """Convert contact to dict."""
        return {
            "id": contact.id,
            "contact_type": contact.contact_type,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "email": contact.email,
            "phone": contact.phone,
        }

    def _message_to_dict(self, message: PURLMessage) -> Dict[str, Any]:
        """Convert message to dict."""
        return {
            "id": message.id,
            "message_type": message.message_type,
            "content": message.content,
            "sender_type": message.sender_type,
            "sender_user_id": message.sender_user_id,
            "is_read": message.is_read_by_borrower,
            "metadata": message.meta_data,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _document_to_dict(self, doc: PURLDocument) -> Dict[str, Any]:
        """Convert document to dict."""
        return {
            "id": doc.id,
            "doc_type": doc.doc_type,
            "doc_category": doc.doc_category,
            "status": doc.status,
            "file_name": doc.file_name,
            "size_bytes": doc.size_bytes,
            "mime_type": doc.mime_type,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
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
        }

    def _get_default_mum_modules(self) -> List[Dict[str, Any]]:
        """Return default MUM module configuration."""
        return [
            {
                "id": None,
                "module_key": config["module_key"],
                "is_enabled": config["is_enabled"],
                "is_visible": config["is_visible"],
                "order_index": config["order_index"],
                "config": config["config"],
            }
            for config in MUM_PORTAL_MODULES
        ]


def get_mum_portal_service(db: Session) -> MUMPortalService:
    """Factory function to get a MUMPortalService instance."""
    return MUMPortalService(db)
