"""
Document Visibility Service

Business logic for managing document visibility to borrowers and partners,
including CRUD operations, auto-release on milestones, and audit logging.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging

from models.document_visibility import (
    DocumentVisibility,
    DocumentVisibilityAudit,
    ReleaseMode,
    ChangeSource
)

logger = logging.getLogger(__name__)


class DocumentVisibilityService:
    """
    Service for managing document visibility settings.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_visibility(
        self,
        document_table: str,
        document_id: int
    ) -> Optional[DocumentVisibility]:
        """
        Get visibility settings for a document.

        Args:
            document_table: The table name (e.g., 'perennia_documents')
            document_id: The document ID in that table

        Returns:
            DocumentVisibility record or None if not set
        """
        return self.db.query(DocumentVisibility).filter(
            DocumentVisibility.document_table == document_table,
            DocumentVisibility.document_id == document_id
        ).first()

    def get_or_create_visibility(
        self,
        document_table: str,
        document_id: int,
        loan_id: int,
        defaults: Optional[Dict[str, Any]] = None
    ) -> DocumentVisibility:
        """
        Get existing visibility or create with defaults.

        Args:
            document_table: The table name
            document_id: The document ID
            loan_id: Associated loan ID
            defaults: Default values for new record

        Returns:
            Existing or newly created DocumentVisibility
        """
        visibility = self.get_visibility(document_table, document_id)
        if visibility:
            return visibility

        # Create new with defaults
        defaults = defaults or {}
        visibility = DocumentVisibility(
            document_table=document_table,
            document_id=document_id,
            loan_id=loan_id,
            visible_to_borrower=defaults.get('visible_to_borrower', True),
            visible_to_partner=defaults.get('visible_to_partner', True),
            visible_to_internal=defaults.get('visible_to_internal', True),
            release_mode=defaults.get('release_mode', ReleaseMode.MANUAL.value),
            release_milestone=defaults.get('release_milestone'),
            hidden_reason=defaults.get('hidden_reason'),
        )
        self.db.add(visibility)
        self.db.flush()
        return visibility

    def set_visibility(
        self,
        document_table: str,
        document_id: int,
        loan_id: int,
        visible_to_borrower: Optional[bool] = None,
        visible_to_partner: Optional[bool] = None,
        visible_to_internal: Optional[bool] = None,
        release_mode: Optional[str] = None,
        release_milestone: Optional[str] = None,
        release_at: Optional[datetime] = None,
        hidden_reason: Optional[str] = None,
        visibility_locked: Optional[bool] = None,
        changed_by_user_id: Optional[int] = None,
        change_source: str = ChangeSource.MANUAL.value,
        change_reason: Optional[str] = None
    ) -> DocumentVisibility:
        """
        Set visibility for a document with full audit logging.

        Args:
            document_table: The table name
            document_id: The document ID
            loan_id: Associated loan ID
            visible_to_borrower: Set borrower visibility
            visible_to_partner: Set partner visibility
            visible_to_internal: Set internal visibility
            release_mode: 'manual', 'milestone', or 'datetime'
            release_milestone: Milestone trigger (e.g., 'funded')
            release_at: Datetime trigger
            hidden_reason: Reason for hiding
            visibility_locked: Lock visibility from auto-changes
            changed_by_user_id: User making the change
            change_source: Source of change (manual, auto_release, system)
            change_reason: Explanation for the change

        Returns:
            Updated DocumentVisibility record
        """
        visibility = self.get_or_create_visibility(document_table, document_id, loan_id)

        # Track changes for audit
        changes = []

        # Update each field and log changes
        if visible_to_borrower is not None and visibility.visible_to_borrower != visible_to_borrower:
            changes.append({
                'field': 'visible_to_borrower',
                'old': visibility.visible_to_borrower,
                'new': visible_to_borrower
            })
            visibility.visible_to_borrower = visible_to_borrower

        if visible_to_partner is not None and visibility.visible_to_partner != visible_to_partner:
            changes.append({
                'field': 'visible_to_partner',
                'old': visibility.visible_to_partner,
                'new': visible_to_partner
            })
            visibility.visible_to_partner = visible_to_partner

        if visible_to_internal is not None and visibility.visible_to_internal != visible_to_internal:
            changes.append({
                'field': 'visible_to_internal',
                'old': visibility.visible_to_internal,
                'new': visible_to_internal
            })
            visibility.visible_to_internal = visible_to_internal

        # Update non-boolean fields (no audit for these)
        if release_mode is not None:
            visibility.release_mode = release_mode
        if release_milestone is not None:
            visibility.release_milestone = release_milestone
        if release_at is not None:
            visibility.release_at = release_at
        if hidden_reason is not None:
            visibility.hidden_reason = hidden_reason
        if visibility_locked is not None:
            visibility.visibility_locked = visibility_locked

        # Update change tracking
        visibility.last_changed_by = changed_by_user_id
        visibility.last_changed_at = datetime.now(timezone.utc)

        # Create audit entries for boolean changes
        for change in changes:
            audit_entry = DocumentVisibilityAudit(
                document_visibility_id=visibility.id,
                loan_id=loan_id,
                field_changed=change['field'],
                old_value=change['old'],
                new_value=change['new'],
                change_source=change_source,
                changed_by=changed_by_user_id,
                change_reason=change_reason
            )
            self.db.add(audit_entry)

        self.db.flush()

        if changes:
            logger.info(
                f"Document visibility changed: {document_table}:{document_id} - "
                f"{len(changes)} fields changed by user {changed_by_user_id}"
            )

        return visibility

    def is_visible_to_borrower(
        self,
        document_table: str,
        document_id: int
    ) -> bool:
        """
        Check if a document is visible to borrowers.

        Returns True if:
        - No visibility record exists (default visible)
        - visible_to_borrower is True
        """
        visibility = self.get_visibility(document_table, document_id)
        if not visibility:
            return True  # Default: visible
        return visibility.visible_to_borrower

    def is_visible_to_partner(
        self,
        document_table: str,
        document_id: int
    ) -> bool:
        """
        Check if a document is visible to partners.

        Returns True if:
        - No visibility record exists (default visible)
        - visible_to_partner is True
        """
        visibility = self.get_visibility(document_table, document_id)
        if not visibility:
            return True  # Default: visible
        return visibility.visible_to_partner

    def get_hidden_document_ids(
        self,
        loan_id: int,
        document_table: str,
        for_borrower: bool = True
    ) -> List[int]:
        """
        Get list of document IDs that are hidden.

        Args:
            loan_id: Loan ID to filter by
            document_table: Document table to filter by
            for_borrower: If True, get borrower-hidden; else partner-hidden

        Returns:
            List of document IDs that should be hidden
        """
        query = self.db.query(DocumentVisibility.document_id).filter(
            DocumentVisibility.loan_id == loan_id,
            DocumentVisibility.document_table == document_table
        )

        if for_borrower:
            query = query.filter(DocumentVisibility.visible_to_borrower == False)
        else:
            query = query.filter(DocumentVisibility.visible_to_partner == False)

        return [row[0] for row in query.all()]

    def process_milestone_release(
        self,
        loan_id: int,
        milestone: str
    ) -> List[DocumentVisibility]:
        """
        Process auto-release for documents scheduled for a milestone.

        Called when loan reaches a milestone (e.g., 'funded', 'clear_to_close').
        Releases all documents scheduled for that milestone.

        Args:
            loan_id: The loan ID
            milestone: The milestone reached (e.g., 'funded')

        Returns:
            List of documents that were released
        """
        # Find documents scheduled for this milestone
        docs_to_release = self.db.query(DocumentVisibility).filter(
            DocumentVisibility.loan_id == loan_id,
            DocumentVisibility.release_mode == ReleaseMode.MILESTONE.value,
            DocumentVisibility.release_milestone == milestone.lower(),
            DocumentVisibility.visibility_locked == False,
            or_(
                DocumentVisibility.visible_to_borrower == False,
                DocumentVisibility.visible_to_partner == False
            )
        ).all()

        released = []
        for doc in docs_to_release:
            changes = []

            # Release to borrower if hidden
            if not doc.visible_to_borrower:
                changes.append({
                    'field': 'visible_to_borrower',
                    'old': False,
                    'new': True
                })
                doc.visible_to_borrower = True

            # Release to partner if hidden
            if not doc.visible_to_partner:
                changes.append({
                    'field': 'visible_to_partner',
                    'old': False,
                    'new': True
                })
                doc.visible_to_partner = True

            # Update tracking
            doc.last_changed_at = datetime.now(timezone.utc)

            # Create audit entries
            for change in changes:
                audit_entry = DocumentVisibilityAudit(
                    document_visibility_id=doc.id,
                    loan_id=loan_id,
                    field_changed=change['field'],
                    old_value=change['old'],
                    new_value=change['new'],
                    change_source=ChangeSource.AUTO_RELEASE.value,
                    changed_by=None,  # System action
                    change_reason=f"Auto-released on milestone: {milestone}"
                )
                self.db.add(audit_entry)

            released.append(doc)

        if released:
            self.db.flush()
            logger.info(
                f"Auto-released {len(released)} documents for loan {loan_id} "
                f"on milestone '{milestone}'"
            )

        return released

    def get_visibility_history(
        self,
        document_table: str,
        document_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get audit history for a document's visibility changes.

        Args:
            document_table: The table name
            document_id: The document ID
            limit: Max records to return

        Returns:
            List of audit entries as dicts
        """
        visibility = self.get_visibility(document_table, document_id)
        if not visibility:
            return []

        entries = self.db.query(DocumentVisibilityAudit).filter(
            DocumentVisibilityAudit.document_visibility_id == visibility.id
        ).order_by(
            DocumentVisibilityAudit.created_at.desc()
        ).limit(limit).all()

        return [entry.to_dict() for entry in entries]

    def bulk_set_visibility(
        self,
        loan_id: int,
        document_ids: List[Dict[str, Any]],  # [{'table': 'x', 'id': 1}, ...]
        visible_to_borrower: Optional[bool] = None,
        visible_to_partner: Optional[bool] = None,
        changed_by_user_id: Optional[int] = None,
        change_reason: Optional[str] = None
    ) -> int:
        """
        Bulk update visibility for multiple documents.

        Args:
            loan_id: The loan ID
            document_ids: List of dicts with 'table' and 'id' keys
            visible_to_borrower: Set borrower visibility
            visible_to_partner: Set partner visibility
            changed_by_user_id: User making the change
            change_reason: Explanation for the change

        Returns:
            Number of documents updated
        """
        updated = 0
        for doc in document_ids:
            self.set_visibility(
                document_table=doc['table'],
                document_id=doc['id'],
                loan_id=loan_id,
                visible_to_borrower=visible_to_borrower,
                visible_to_partner=visible_to_partner,
                changed_by_user_id=changed_by_user_id,
                change_source=ChangeSource.MANUAL.value,
                change_reason=change_reason
            )
            updated += 1

        return updated
