"""
PURL Document Service

Provides business logic for PURL document operations including:
- Document upload initialization (presigned URLs)
- Document upload completion and registration
- Document download (presigned URLs)
- Document status management
- Document categorization and OCR processing
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from sqlalchemy.exc import SQLAlchemyError
from models.purl import (
    PURLDocument,
    PURLWorkspace,
    PURLLoan,
    PURLDocumentRequest,
    PURLEventsOutbox,
    PURLTask,
    DocumentCategory,
    DocumentStatus,
    DocumentRequestStatus,
    EventStatus,
    TaskStatus
)

logger = logging.getLogger(__name__)


# Document type mappings for auto-categorization
DOCUMENT_TYPE_CATEGORIES = {
    # Income
    "paystub": DocumentCategory.INCOME.value,
    "pay_stub": DocumentCategory.INCOME.value,
    "w2": DocumentCategory.INCOME.value,
    "1099": DocumentCategory.INCOME.value,
    "tax_return": DocumentCategory.INCOME.value,
    "profit_loss": DocumentCategory.INCOME.value,

    # Assets
    "bank_statement": DocumentCategory.ASSET.value,
    "investment_statement": DocumentCategory.ASSET.value,
    "retirement_statement": DocumentCategory.ASSET.value,
    "gift_letter": DocumentCategory.ASSET.value,

    # Identity
    "drivers_license": DocumentCategory.IDENTITY.value,
    "id": DocumentCategory.IDENTITY.value,
    "passport": DocumentCategory.IDENTITY.value,
    "ssn_card": DocumentCategory.IDENTITY.value,

    # Property
    "purchase_contract": DocumentCategory.PROPERTY.value,
    "appraisal": DocumentCategory.PROPERTY.value,
    "title": DocumentCategory.PROPERTY.value,
    "insurance": DocumentCategory.PROPERTY.value,
    "hoa": DocumentCategory.PROPERTY.value,

    # Closing
    "closing_disclosure": DocumentCategory.CLOSING.value,
    "cd": DocumentCategory.CLOSING.value,
    "deed": DocumentCategory.CLOSING.value,
    "note": DocumentCategory.CLOSING.value,
}


class PURLDocumentService:
    """
    Service for PURL document operations.
    Manages document uploads, downloads, and status.
    """

    def __init__(self, db: Session):
        self.db = db
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy-load S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
        return self._s3_client

    @property
    def bucket_name(self):
        """Get S3 bucket name from environment."""
        return os.getenv('S3_BUCKET_NAME', os.getenv('PURL_S3_BUCKET', 'perennia-purl-documents'))

    # =========================================================================
    # UPLOAD INITIALIZATION
    # =========================================================================

    def generate_upload_url(
        self,
        organization_id: int,
        workspace_id: int,
        filename: str,
        content_type: str,
        document_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a presigned PUT URL for direct S3 upload.

        This is the simpler upload flow using PUT instead of POST:
        1. Client calls this to get a presigned PUT URL
        2. Client PUTs the file directly to S3
        3. Client calls complete_upload when done

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            filename: Original filename
            content_type: MIME type
            document_type: Optional document type

        Returns:
            Dict with upload_url, document_key, expires_in
        """
        # Generate storage key
        upload_id = uuid4().hex
        sanitized_name = self._sanitize_filename(filename)

        document_key = (
            f"org/{organization_id}/"
            f"workspaces/{workspace_id}/"
            f"documents/{upload_id}/{sanitized_name}"
        )

        try:
            # Generate presigned PUT URL
            upload_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': document_key,
                    'ContentType': content_type,
                },
                ExpiresIn=3600  # 1 hour
            )

            logger.info(
                f"Generated upload URL for workspace {workspace_id}: {filename}"
            )

            return {
                "upload_url": upload_url,
                "document_key": document_key,
                "expires_in": 3600
            }

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise ValueError(f"Failed to generate upload URL: {str(e)}")

    def init_upload(
        self,
        organization_id: int,
        workspace_id: int,
        file_name: str,
        file_size: int,
        mime_type: str,
        doc_type: str,
        doc_category: DocumentCategory,
        loan_id: Optional[int] = None,
        contact_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Initialize document upload and get presigned POST URL.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            file_name: Original file name
            file_size: File size in bytes
            mime_type: MIME type
            doc_type: Document type (e.g., "paystub", "w2")
            doc_category: Document category
            loan_id: Optional loan association
            contact_id: Uploading contact ID

        Returns:
            Dict with upload_id, storage_key, presigned_post, expires_in
        """
        # Validate file size (max 100MB)
        max_size = 100 * 1024 * 1024
        if file_size > max_size:
            raise ValueError(f"File size exceeds maximum of {max_size / 1024 / 1024}MB")

        # Generate storage key
        upload_id = uuid4().hex
        file_ext = file_name.split('.')[-1] if '.' in file_name else ''
        sanitized_name = self._sanitize_filename(file_name)

        storage_key = (
            f"org/{organization_id}/"
            f"workspaces/{workspace_id}/"
            f"documents/{upload_id}/{sanitized_name}"
        )

        # Generate presigned POST
        try:
            presigned_post = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=storage_key,
                Fields={
                    "Content-Type": mime_type,
                    "x-amz-meta-workspace-id": str(workspace_id),
                    "x-amz-meta-doc-type": doc_type,
                    "x-amz-meta-upload-id": upload_id
                },
                Conditions=[
                    {"Content-Type": mime_type},
                    ["content-length-range", 0, max_size]
                ],
                ExpiresIn=3600  # 1 hour
            )
        except ClientError as e:
            logger.error(f"Failed to generate presigned POST: {e}")
            raise ValueError("Failed to initialize upload")

        logger.info(
            f"Initialized upload {upload_id} for workspace {workspace_id}: {file_name}"
        )

        return {
            "upload_id": upload_id,
            "storage_key": storage_key,
            "presigned_post": presigned_post,
            "expires_in": 3600
        }

    # =========================================================================
    # UPLOAD COMPLETION
    # =========================================================================

    def complete_upload(
        self,
        organization_id: int,
        workspace_id: int,
        document_key: str,
        filename: str,
        file_size: int,
        content_type: str,
        document_type: Optional[str] = None,
        uploaded_by_contact_id: Optional[int] = None,
        # Legacy parameters for backwards compatibility
        upload_id: Optional[str] = None,
        storage_key: Optional[str] = None,
        doc_type: Optional[str] = None,
        doc_category: Optional[DocumentCategory] = None,
        sha256: Optional[str] = None,
        loan_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        """
        Complete upload and create document record.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            document_key: S3 document key (storage path)
            filename: Original filename
            file_size: File size in bytes
            content_type: MIME type
            document_type: Document type (paystub, w2, etc.)
            uploaded_by_contact_id: Contact ID who uploaded

        Returns:
            PURLDocument object
        """
        # Use document_key or fall back to storage_key for backwards compatibility
        actual_storage_key = document_key or storage_key
        actual_doc_type = document_type or doc_type or "other"
        actual_contact_id = uploaded_by_contact_id or contact_id

        # Try to verify file exists in S3 (optional - may fail if S3 not configured)
        actual_file_size = file_size
        actual_mime_type = content_type

        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=actual_storage_key
            )
            actual_file_size = response.get('ContentLength', file_size)
            actual_mime_type = response.get('ContentType', content_type)
        except ClientError as e:
            # Log but don't fail - S3 might not be configured in dev
            logger.warning(f"Could not verify S3 object (may be expected in dev): {e}")
        except Exception as e:
            logger.warning(f"S3 verification skipped: {e}")

        # Auto-categorize based on document type
        if doc_category and doc_category != DocumentCategory.MISC:
            doc_category_value = doc_category.value
        else:
            doc_category_value = self._auto_categorize(actual_doc_type)

        # Create document record
        document = PURLDocument(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            doc_type=actual_doc_type,
            doc_category=doc_category_value,
            status=DocumentStatus.UPLOADED.value,
            file_name=filename,
            storage_key=actual_storage_key,
            size_bytes=actual_file_size,
            mime_type=actual_mime_type,
            sha256=sha256,
            uploaded_by_contact_id=actual_contact_id,
            uploaded_by_user_id=user_id,
            metadata={"upload_id": upload_id} if upload_id else {}
        )

        self.db.add(document)
        self.db.flush()

        # Check if this fulfills a document request
        self._check_document_requests(
            organization_id, workspace_id, loan_id, actual_doc_type, document.id
        )

        # Check if this completes a task
        self._check_related_tasks(workspace_id, actual_doc_type, document.id)

        self.db.commit()
        self.db.refresh(document)

        # Emit event
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            event_key="document_uploaded",
            payload={
                "document_id": document.id,
                "doc_type": actual_doc_type,
                "doc_category": doc_category_value,
                "file_name": filename,
                "uploaded_by_contact_id": actual_contact_id
            }
        )

        logger.info(f"Created document {document.id} for workspace {workspace_id}")

        # Return the document object (routes expect this)
        return document

    # =========================================================================
    # DOCUMENT RETRIEVAL
    # =========================================================================

    def get_document(
        self,
        document_id: int,
        organization_id: Optional[int] = None
    ) -> Optional[PURLDocument]:
        """Get document by ID."""
        query = self.db.query(PURLDocument).filter(
            PURLDocument.id == document_id
        )

        if organization_id:
            query = query.filter(PURLDocument.organization_id == organization_id)

        return query.first()

    def get_workspace_documents(
        self,
        organization_id: int,
        workspace_id: int,
        category: Optional[DocumentCategory] = None,
        status: Optional[DocumentStatus] = None,
        loan_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all documents for a workspace.

        Returns:
            Tuple of (documents list, total count)
        """
        query = self.db.query(PURLDocument).filter(
            PURLDocument.organization_id == organization_id,
            PURLDocument.workspace_id == workspace_id
        )

        if category:
            query = query.filter(PURLDocument.doc_category == category.value)

        if status:
            query = query.filter(PURLDocument.status == status.value)

        if loan_id:
            query = query.filter(PURLDocument.loan_id == loan_id)

        total = query.count()

        documents = query.order_by(
            PURLDocument.created_at.desc()
        ).offset(offset).limit(limit).all()

        return [self._document_to_dict(d) for d in documents], total

    def get_download_url(
        self,
        organization_id: int,
        workspace_id: int,
        document_id: int,
        expires_in: int = 3600
    ) -> str:
        """
        Get presigned download URL for document.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            document_id: Document ID
            expires_in: URL expiration time in seconds

        Returns:
            Presigned download URL

        Raises:
            ValueError: If document not found
        """
        document = self.db.query(PURLDocument).filter(
            PURLDocument.id == document_id,
            PURLDocument.organization_id == organization_id,
            PURLDocument.workspace_id == workspace_id
        ).first()

        if not document:
            raise ValueError("Document not found")

        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': document.storage_key,
                    'ResponseContentDisposition': f'attachment; filename="{document.file_name}"'
                },
                ExpiresIn=expires_in
            )

            return url

        except ClientError as e:
            logger.error(f"Failed to generate download URL: {e}")
            raise ValueError("Failed to generate download URL")

    # =========================================================================
    # DOCUMENT STATUS MANAGEMENT
    # =========================================================================

    def update_document_status(
        self,
        document_id: int,
        new_status: DocumentStatus,
        reviewed_by: Optional[int] = None,
        review_notes: Optional[str] = None
    ) -> bool:
        """
        Update document status.

        Returns:
            True if successful
        """
        document = self.db.query(PURLDocument).filter(
            PURLDocument.id == document_id
        ).first()

        if not document:
            return False

        old_status = document.status
        document.status = new_status.value

        if new_status in [DocumentStatus.VERIFIED, DocumentStatus.REJECTED]:
            document.reviewed_by = reviewed_by
            document.reviewed_at = datetime.now(timezone.utc)
            document.review_notes = review_notes

        self.db.commit()

        # Emit event
        self._emit_event(
            organization_id=document.organization_id,
            workspace_id=document.workspace_id,
            loan_id=document.loan_id,
            event_key=f"document_status_changed_{new_status.value}",
            payload={
                "document_id": document_id,
                "old_status": old_status,
                "new_status": new_status.value,
                "reviewed_by": reviewed_by
            }
        )

        logger.info(f"Document {document_id} status: {old_status} -> {new_status.value}")
        return True

    def delete_document(
        self,
        document_id: int,
        deleted_by: Optional[int] = None
    ) -> bool:
        """
        Delete a document (soft delete by moving to archived status).
        Does NOT delete from S3 for compliance reasons.

        Returns:
            True if successful
        """
        document = self.db.query(PURLDocument).filter(
            PURLDocument.id == document_id
        ).first()

        if not document:
            return False

        # Check legal hold
        if document.legal_hold:
            raise ValueError("Document is under legal hold and cannot be deleted")

        document.status = DocumentStatus.ARCHIVED.value
        self.db.commit()

        logger.info(f"Archived document {document_id}")
        return True

    # =========================================================================
    # DOCUMENT REQUESTS
    # =========================================================================

    def create_document_request(
        self,
        organization_id: int,
        workspace_id: int,
        document_type: str,
        document_category: DocumentCategory,
        description: Optional[str] = None,
        is_required: bool = True,
        due_date: Optional[datetime] = None,
        loan_id: Optional[int] = None,
        requested_by: Optional[int] = None
    ) -> int:
        """
        Create a document request.

        Returns:
            Document request ID
        """
        request = PURLDocumentRequest(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            document_type=document_type,
            document_category=document_category.value,
            description=description,
            status=DocumentRequestStatus.PENDING.value,
            is_required=is_required,
            due_date=due_date.date() if due_date else None,
            requested_by=requested_by
        )

        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)

        logger.info(f"Created document request {request.id} for {document_type}")
        return request.id

    def get_pending_document_requests(
        self,
        workspace_id: int,
        loan_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get pending document requests for workspace."""
        query = self.db.query(PURLDocumentRequest).filter(
            PURLDocumentRequest.workspace_id == workspace_id,
            PURLDocumentRequest.status == DocumentRequestStatus.PENDING.value
        )

        if loan_id:
            query = query.filter(PURLDocumentRequest.loan_id == loan_id)

        requests = query.order_by(
            PURLDocumentRequest.is_required.desc(),
            PURLDocumentRequest.due_date.asc().nullslast()
        ).all()

        return [
            {
                "id": r.id,
                "document_type": r.document_type,
                "document_category": r.document_category,
                "description": r.description,
                "is_required": r.is_required,
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "requested_at": r.requested_at.isoformat() if r.requested_at else None
            }
            for r in requests
        ]

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for S3 storage."""
        import re
        # Remove path components
        filename = filename.split('/')[-1].split('\\')[-1]
        # Replace spaces and special chars
        filename = re.sub(r'[^\w\-_.]', '_', filename)
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext
        return filename

    def _auto_categorize(self, doc_type: str) -> str:
        """Auto-categorize document based on type."""
        doc_type_lower = doc_type.lower().replace(' ', '_')

        for key, category in DOCUMENT_TYPE_CATEGORIES.items():
            if key in doc_type_lower:
                return category

        return DocumentCategory.MISC.value

    def _check_document_requests(
        self,
        organization_id: int,
        workspace_id: int,
        loan_id: Optional[int],
        doc_type: str,
        document_id: int
    ):
        """Check if uploaded document fulfills any requests."""
        query = self.db.query(PURLDocumentRequest).filter(
            PURLDocumentRequest.workspace_id == workspace_id,
            PURLDocumentRequest.status == DocumentRequestStatus.PENDING.value,
            PURLDocumentRequest.document_type.ilike(f"%{doc_type}%")
        )

        if loan_id:
            query = query.filter(PURLDocumentRequest.loan_id == loan_id)

        matching_request = query.first()

        if matching_request:
            matching_request.status = DocumentRequestStatus.RECEIVED.value
            matching_request.received_document_id = document_id
            matching_request.received_at = datetime.now(timezone.utc)

            logger.info(
                f"Document {document_id} fulfilled request {matching_request.id}"
            )

    def _check_related_tasks(
        self,
        workspace_id: int,
        doc_type: str,
        document_id: int
    ):
        """Check if uploaded document completes any tasks."""
        # Find open document upload tasks that might match
        tasks = self.db.query(PURLTask).filter(
            PURLTask.workspace_id == workspace_id,
            PURLTask.task_type == "document_upload",
            PURLTask.status.in_([TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value])
        ).all()

        doc_type_lower = doc_type.lower()

        for task in tasks:
            # Check if task title mentions this document type
            task_title_lower = task.title.lower()
            if any(term in task_title_lower for term in [doc_type_lower, doc_type_lower.replace('_', ' ')]):
                task.status = TaskStatus.COMPLETED.value
                task.completed_at = datetime.now(timezone.utc)
                task.related_document_id = document_id

                logger.info(f"Document {document_id} completed task {task.id}")

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
            "reviewed_by": doc.reviewed_by,
            "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
            "review_notes": doc.review_notes,
            "retention_policy": doc.retention_policy,
            "legal_hold": doc.legal_hold,
            "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
            "metadata": doc.metadata,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
        }

    def _emit_event(
        self,
        organization_id: int,
        workspace_id: int,
        event_key: str,
        payload: Dict[str, Any],
        loan_id: Optional[int] = None
    ):
        """Emit event to outbox."""
        event = PURLEventsOutbox(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            event_key=event_key,
            payload=payload,
            status=EventStatus.PENDING.value
        )
        self.db.add(event)
