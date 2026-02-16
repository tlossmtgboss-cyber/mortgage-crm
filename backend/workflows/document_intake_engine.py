"""
Smart Email Document Intake & Classification Engine
TL Development, LLC

Processes inbound emails with attachments:
1. Parses email metadata and extracts attachments
2. Matches email to borrower/loan using multiple strategies
3. Creates classification task for human review
4. Handles document classification and storage
"""

import re
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
import logging
import mimetypes

# S3 storage service
from services.perennia_s3_service import get_s3_service

logger = logging.getLogger(__name__)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Valid attachment types
VALID_ATTACHMENT_TYPES = {
    'application/pdf': ['.pdf'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/tiff': ['.tiff', '.tif'],
    'application/msword': ['.doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'application/vnd.ms-excel': ['.xls'],
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    'text/csv': ['.csv'],
}

# Minimum file size to process (filter out tiny images like signatures)
MIN_FILE_SIZE_BYTES = 5000  # 5KB

# Maximum file size to process
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25MB

# Patterns to identify loan numbers in email
LOAN_NUMBER_PATTERNS = [
    r'loan\s*#?\s*:?\s*(\d{6,15})',  # "Loan #: 123456"
    r'loan\s+number\s*:?\s*(\d{6,15})',  # "Loan Number: 123456"
    r'file\s*#?\s*:?\s*(\d{6,15})',  # "File #: 123456"
    r'\b([A-Z]{2,4}\d{6,12})\b',  # "ABC123456789"
    r'RCA\d{10}',  # Your loan number format
]

# Document type suggestions based on filename patterns
DOC_TYPE_FILENAME_PATTERNS = {
    'W2': [r'w-?2', r'wage.*tax'],
    'PAYSTUB': [r'paystub', r'pay\s*stub', r'earnings', r'paycheck'],
    'TAX_RETURN_1040': [r'1040', r'tax.*return', r'federal.*tax'],
    'TAX_RETURN_1099': [r'1099'],
    'BANK_STATEMENT': [r'bank.*statement', r'statement.*bank', r'account.*statement'],
    'DRIVERS_LICENSE': [r'driver', r'license', r'dl\d', r'id\s*card'],
    'PURCHASE_CONTRACT': [r'contract', r'purchase.*agreement', r'sales.*contract'],
    'APPRAISAL': [r'appraisal'],
    'TITLE_COMMITMENT': [r'title', r'commitment'],
    'HOMEOWNERS_INSURANCE': [r'insurance', r'hoi', r'hazard'],
}


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class ParsedEmail:
    """Parsed email data"""
    from_email: str
    to_email: str
    cc_emails: List[str]
    subject: str
    body: str
    body_snippet: str
    received_at: datetime
    message_id: str
    in_reply_to: Optional[str] = None
    attachments: List['ParsedAttachment'] = field(default_factory=list)


@dataclass
class ParsedAttachment:
    """Parsed attachment data"""
    filename: str
    original_filename: str
    content: bytes
    size: int
    mime_type: str


@dataclass
class MatchResult:
    """Result of borrower/loan matching"""
    status: str  # MATCHED, MULTIPLE, UNMATCHED
    borrower_id: Optional[int] = None
    loan_id: Optional[int] = None
    confidence: float = 0.0
    match_reason: str = ""
    candidates: List[Dict] = field(default_factory=list)


@dataclass
class DocumentSuggestion:
    """AI suggestion for document classification"""
    doc_type: str
    doc_category: str
    confidence: float
    reason: str


# ==============================================================================
# DOCUMENT INTAKE ENGINE
# ==============================================================================

class DocumentIntakeEngine:
    """Main engine for processing email document intake"""

    def __init__(self, db: Session):
        self.db = db

    async def process_inbound_email(self, raw_email: Dict) -> Dict[str, Any]:
        """
        Main entry point for processing an inbound email.

        Args:
            raw_email: Dict with email data (from email provider webhook)

        Returns:
            Dict with processing result
        """
        from main import (
            EmailIntake, AttachmentIntake, Task,
            EmailIntakeMatchStatus, AttachmentClassificationStatus
        )

        try:
            # 1. Parse the email
            parsed = self._parse_email(raw_email)

            # 2. Filter valid attachments
            valid_attachments = self._filter_attachments(parsed.attachments)

            if not valid_attachments:
                logger.info(f"Email from {parsed.from_email} has no valid attachments, skipping")
                return {
                    "success": True,
                    "skipped": True,
                    "reason": "No valid attachments"
                }

            # 3. Create EmailIntake record
            email_intake = EmailIntake(
                from_email=parsed.from_email,
                to_email=parsed.to_email,
                cc_emails=",".join(parsed.cc_emails) if parsed.cc_emails else None,
                subject=parsed.subject,
                body_snippet=parsed.body_snippet,
                received_at=parsed.received_at,
                raw_message_id=parsed.message_id,
                in_reply_to=parsed.in_reply_to,
                processing_status="processing"
            )
            self.db.add(email_intake)
            self.db.flush()  # Get ID

            # 4. Match to borrower/loan
            match_result = await self._match_email_to_borrower(parsed)

            email_intake.matched_borrower_id = match_result.borrower_id
            email_intake.matched_loan_id = match_result.loan_id
            email_intake.match_status = EmailIntakeMatchStatus(match_result.status.lower())
            email_intake.match_candidates = match_result.candidates if match_result.candidates else None

            # 5. Store attachments and create AttachmentIntake records
            attachment_records = []
            for att in valid_attachments:
                # Store file (implement your storage solution)
                storage_location = await self._store_attachment(att, email_intake.id)

                # Get AI suggestion for doc type
                suggestion = self._suggest_document_type(att)

                att_record = AttachmentIntake(
                    email_intake_id=email_intake.id,
                    filename=att.filename,
                    original_filename=att.original_filename,
                    file_size=att.size,
                    mime_type=att.mime_type,
                    storage_location=storage_location,
                    ai_suggested_doc_type=suggestion.doc_type if suggestion else None,
                    ai_suggested_doc_category=suggestion.doc_category if suggestion else None,
                    ai_confidence=suggestion.confidence if suggestion else None,
                    classification_status=AttachmentClassificationStatus.PENDING
                )
                self.db.add(att_record)
                attachment_records.append(att_record)

            self.db.flush()

            # 6. Create classification task
            task = await self._create_classification_task(email_intake, attachment_records, match_result)

            # 7. Update status
            email_intake.processing_status = "processed"
            email_intake.processed_at = datetime.now(timezone.utc)

            self.db.commit()

            logger.info(f"Processed email intake {email_intake.id} with {len(attachment_records)} attachments")

            return {
                "success": True,
                "email_intake_id": email_intake.id,
                "attachment_count": len(attachment_records),
                "match_status": match_result.status,
                "task_id": task.id if task else None
            }

        except Exception as e:
            logger.error(f"Error processing inbound email: {e}")
            self.db.rollback()
            raise

    def _parse_email(self, raw_email: Dict) -> ParsedEmail:
        """Parse raw email data into ParsedEmail object"""
        body = raw_email.get('body', raw_email.get('text', ''))
        body_snippet = body[:500] if body else ''

        attachments = []
        for att in raw_email.get('attachments', []):
            content = att.get('content', b'')
            if isinstance(content, str):
                import base64
                content = base64.b64decode(content)

            attachments.append(ParsedAttachment(
                filename=self._sanitize_filename(att.get('filename', 'attachment')),
                original_filename=att.get('filename', 'attachment'),
                content=content,
                size=len(content),
                mime_type=att.get('contentType', att.get('mime_type', 'application/octet-stream'))
            ))

        return ParsedEmail(
            from_email=raw_email.get('from', raw_email.get('from_email', '')),
            to_email=raw_email.get('to', raw_email.get('to_email', '')),
            cc_emails=raw_email.get('cc', []),
            subject=raw_email.get('subject', ''),
            body=body,
            body_snippet=body_snippet,
            received_at=datetime.fromisoformat(raw_email.get('date', datetime.now(timezone.utc).isoformat())),
            message_id=raw_email.get('messageId', raw_email.get('message_id', '')),
            in_reply_to=raw_email.get('inReplyTo', raw_email.get('in_reply_to')),
            attachments=attachments
        )

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for storage"""
        # Remove path components
        filename = os.path.basename(filename)
        # Replace dangerous characters
        filename = re.sub(r'[^\w\s\-\.]', '_', filename)
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:195] + ext
        return filename

    def _filter_attachments(self, attachments: List[ParsedAttachment]) -> List[ParsedAttachment]:
        """Filter attachments to valid document types and sizes"""
        valid = []
        for att in attachments:
            # Check size
            if att.size < MIN_FILE_SIZE_BYTES:
                logger.debug(f"Skipping {att.filename}: too small ({att.size} bytes)")
                continue
            if att.size > MAX_FILE_SIZE_BYTES:
                logger.debug(f"Skipping {att.filename}: too large ({att.size} bytes)")
                continue

            # Check mime type
            if att.mime_type not in VALID_ATTACHMENT_TYPES:
                # Try to detect from extension
                ext = os.path.splitext(att.filename)[1].lower()
                valid_ext = False
                for mime, extensions in VALID_ATTACHMENT_TYPES.items():
                    if ext in extensions:
                        att.mime_type = mime
                        valid_ext = True
                        break
                if not valid_ext:
                    logger.debug(f"Skipping {att.filename}: invalid type ({att.mime_type})")
                    continue

            valid.append(att)

        return valid

    async def _match_email_to_borrower(self, email: ParsedEmail) -> MatchResult:
        """
        Attempt to match email to a borrower/loan using multiple strategies.

        Strategies:
        1. From email matches borrower email
        2. From email matches loan contact email
        3. Loan number in subject/body
        4. Thread matching (In-Reply-To header)
        """
        from main import Lead, Loan

        candidates = []

        # Strategy 1: Match by from_email to borrower (Lead) email
        borrower_match = self.db.query(Lead).filter(
            Lead.email.ilike(email.from_email)
        ).first()

        if borrower_match:
            # Check for associated loan
            loan_match = self.db.query(Loan).filter(
                Loan.borrower_name.ilike(f"%{borrower_match.name.split()[0]}%")
            ).first()

            candidates.append({
                "borrower_id": borrower_match.id,
                "borrower_name": borrower_match.name,
                "loan_id": loan_match.id if loan_match else None,
                "loan_number": loan_match.loan_number if loan_match else None,
                "confidence": 0.9,
                "reason": "Email sender matches borrower email"
            })

        # Strategy 2: Match by CC email
        for cc in email.cc_emails:
            cc_match = self.db.query(Lead).filter(
                Lead.email.ilike(cc)
            ).first()
            if cc_match and not any(c['borrower_id'] == cc_match.id for c in candidates):
                candidates.append({
                    "borrower_id": cc_match.id,
                    "borrower_name": cc_match.name,
                    "loan_id": None,
                    "confidence": 0.7,
                    "reason": "CC email matches borrower"
                })

        # Strategy 3: Loan number in subject or body
        combined_text = f"{email.subject} {email.body}"
        for pattern in LOAN_NUMBER_PATTERNS:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                loan = self.db.query(Loan).filter(
                    Loan.loan_number.ilike(f"%{match}%")
                ).first()
                if loan and not any(c.get('loan_id') == loan.id for c in candidates):
                    # Find associated borrower
                    borrower = self.db.query(Lead).filter(
                        Lead.name.ilike(f"%{loan.borrower_name.split()[0]}%")
                    ).first() if loan.borrower_name else None

                    candidates.append({
                        "borrower_id": borrower.id if borrower else None,
                        "borrower_name": loan.borrower_name,
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "confidence": 0.95,
                        "reason": f"Loan number {match} found in email"
                    })

        # Determine result
        if not candidates:
            return MatchResult(
                status="UNMATCHED",
                match_reason="No matching borrower or loan found"
            )
        elif len(candidates) == 1:
            best = candidates[0]
            return MatchResult(
                status="MATCHED",
                borrower_id=best.get('borrower_id'),
                loan_id=best.get('loan_id'),
                confidence=best.get('confidence', 0.5),
                match_reason=best.get('reason', '')
            )
        else:
            # Multiple matches - pick best or let user decide
            best = max(candidates, key=lambda x: x.get('confidence', 0))
            if best.get('confidence', 0) >= 0.9:
                return MatchResult(
                    status="MATCHED",
                    borrower_id=best.get('borrower_id'),
                    loan_id=best.get('loan_id'),
                    confidence=best.get('confidence', 0.5),
                    match_reason=best.get('reason', ''),
                    candidates=candidates
                )
            else:
                return MatchResult(
                    status="MULTIPLE",
                    candidates=candidates,
                    match_reason="Multiple potential matches found"
                )

    def _get_intake_org_id(self, email_intake_id: int) -> Optional[int]:
        """Look up organization_id for an email intake via its matched loan."""
        from sqlalchemy import text
        row = self.db.execute(text("""
            SELECT l.organization_id FROM email_intakes ei
            JOIN loans l ON l.id = ei.matched_loan_id
            WHERE ei.id = :id AND ei.matched_loan_id IS NOT NULL
        """), {"id": email_intake_id}).first()
        return row[0] if row else None

    async def _store_attachment(self, attachment: ParsedAttachment, email_intake_id: int) -> str:
        """
        Store attachment in S3 and return storage key.
        Uses temporary intake folder for initial storage before classification.
        """
        try:
            s3_service = get_s3_service()

            # Look up org for tenant-isolated S3 key
            org_id = self._get_intake_org_id(email_intake_id)

            # Generate storage key for intake (temporary storage)
            storage_key = s3_service.generate_intake_key(email_intake_id, attachment.filename, organization_id=org_id)

            # Upload file content to S3
            result = s3_service.upload_file(
                storage_key=storage_key,
                file_content=attachment.content,
                content_type=attachment.mime_type,
                metadata={
                    "original_filename": attachment.original_filename,
                    "email_intake_id": str(email_intake_id),
                    "upload_source": "document_intake_engine"
                }
            )

            if result.get("success"):
                logger.info(f"Stored attachment in S3: {storage_key} ({attachment.size} bytes)")
                return storage_key
            else:
                logger.error(f"Failed to store attachment: {result.get('error')}")
                raise Exception(f"S3 upload failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error storing attachment {attachment.filename}: {e}")
            # Fall back to placeholder path for development/testing without S3
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            fallback_path = f"document_intake/{email_intake_id}/{timestamp}_{attachment.filename}"
            logger.warning(f"Using fallback path (S3 unavailable): {fallback_path}")
            return fallback_path

    def _suggest_document_type(self, attachment: ParsedAttachment) -> Optional[DocumentSuggestion]:
        """
        Suggest document type based on filename patterns.
        In production, enhance with OCR text analysis.
        """
        filename_lower = attachment.filename.lower()

        for doc_type, patterns in DOC_TYPE_FILENAME_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    # Map doc type to category
                    category_map = {
                        'W2': 'INCOME',
                        'PAYSTUB': 'INCOME',
                        'TAX_RETURN_1040': 'INCOME',
                        'TAX_RETURN_1099': 'INCOME',
                        'BANK_STATEMENT': 'ASSETS',
                        'DRIVERS_LICENSE': 'IDENTITY',
                        'PURCHASE_CONTRACT': 'PROPERTY',
                        'APPRAISAL': 'PROPERTY',
                        'TITLE_COMMITMENT': 'PROPERTY',
                        'HOMEOWNERS_INSURANCE': 'PROPERTY',
                    }

                    return DocumentSuggestion(
                        doc_type=doc_type,
                        doc_category=category_map.get(doc_type, 'MISC'),
                        confidence=0.7,
                        reason=f"Filename matches pattern for {doc_type}"
                    )

        return None

    async def _create_classification_task(
        self,
        email_intake: Any,
        attachments: List[Any],
        match_result: MatchResult
    ) -> Any:
        """Create a task for classifying the documents"""
        from main import Task

        # Determine assignee
        assignee_id = await self._determine_assignee(match_result)

        # Build attachment list for description
        att_list = "\n".join([
            f"  - {att.filename} ({att.file_size // 1024}KB)"
            for att in attachments
        ])

        task = Task(
            title="Classify New Documents from Email",
            description=(
                f"New documents received via email from {email_intake.from_email}.\n\n"
                f"Attachments ({len(attachments)}):\n{att_list}\n\n"
                f"Please review and classify each document:\n"
                f"1. Confirm document type (W2, Bank Statement, etc.)\n"
                f"2. Verify borrower/loan assignment\n"
                f"3. Add period dates if applicable (for statements)\n\n"
                f"Match Status: {match_result.status}"
            ),
            status="pending",
            priority="high" if match_result.status == "UNMATCHED" else "medium",
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
            owner_id=assignee_id,
            lead_id=match_result.borrower_id,
            loan_id=match_result.loan_id,
            email_intake_id=email_intake.id,
            related_type="document_intake_classification"
        )

        self.db.add(task)
        return task

    async def _determine_assignee(self, match_result: MatchResult) -> int:
        """Determine who should be assigned the classification task"""
        from main import Loan, User

        # If matched to a loan, assign to loan officer
        if match_result.loan_id:
            loan = self.db.query(Loan).filter(Loan.id == match_result.loan_id).first()
            if loan and loan.loan_officer_id:
                return loan.loan_officer_id

        # Default to first admin user
        admin = self.db.query(User).filter(User.role == "admin").first()
        if admin:
            return admin.id

        # Fall back to first user
        user = self.db.query(User).first()
        return user.id if user else 1


# ==============================================================================
# CLASSIFICATION HANDLER
# ==============================================================================

class DocumentClassificationHandler:
    """Handles the classification workflow when user completes the task"""

    def __init__(self, db: Session):
        self.db = db

    async def classify_attachment(
        self,
        attachment_id: int,
        user_id: int,
        doc_type: str,
        doc_category: str,
        borrower_id: Optional[int],
        loan_id: Optional[int],
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify an attachment and create the Document record.
        """
        from main import (
            AttachmentIntake, Document, EmailIntake,
            AttachmentClassificationStatus, DocumentType, DocumentCategory
        )

        # Get the attachment
        attachment = self.db.query(AttachmentIntake).filter(
            AttachmentIntake.id == attachment_id
        ).first()

        if not attachment:
            raise ValueError(f"Attachment {attachment_id} not found")

        if attachment.classification_status == AttachmentClassificationStatus.CLASSIFIED:
            raise ValueError("Attachment already classified")

        # Update classification fields
        attachment.classified_doc_type = DocumentType(doc_type)
        attachment.classified_doc_category = DocumentCategory(doc_category)
        attachment.classified_borrower_id = borrower_id
        attachment.classified_loan_id = loan_id
        attachment.classification_notes = notes
        attachment.classified_at = datetime.now(timezone.utc)
        attachment.classified_by_user_id = user_id

        if period_start:
            attachment.period_start_date = datetime.strptime(period_start, '%Y-%m-%d').date()
        if period_end:
            attachment.period_end_date = datetime.strptime(period_end, '%Y-%m-%d').date()

        # Move file from temp to permanent storage
        final_location = await self._move_to_permanent_storage(attachment)

        # Create Document record
        document = Document(
            borrower_id=borrower_id,
            loan_id=loan_id,
            doc_type=DocumentType(doc_type),
            doc_category=DocumentCategory(doc_category),
            filename=attachment.filename,
            original_filename=attachment.original_filename,
            file_size=attachment.file_size,
            mime_type=attachment.mime_type,
            file_location=final_location,
            period_start_date=attachment.period_start_date,
            period_end_date=attachment.period_end_date,
            source="EMAIL_INTAKE",
            source_email_intake_id=attachment.email_intake_id,
            uploaded_by_user_id=user_id,
            notes=notes
        )
        self.db.add(document)
        self.db.flush()

        # Link attachment to document
        attachment.document_id = document.id
        attachment.classification_status = AttachmentClassificationStatus.CLASSIFIED

        self.db.commit()

        logger.info(f"Classified attachment {attachment_id} as {doc_type}, created document {document.id}")

        return {
            "success": True,
            "attachment_id": attachment_id,
            "document_id": document.id,
            "doc_type": doc_type
        }

    async def discard_attachment(
        self,
        attachment_id: int,
        user_id: int,
        reason: str
    ) -> Dict[str, Any]:
        """Mark an attachment as discarded (junk/irrelevant)"""
        from main import AttachmentIntake, AttachmentClassificationStatus

        attachment = self.db.query(AttachmentIntake).filter(
            AttachmentIntake.id == attachment_id
        ).first()

        if not attachment:
            raise ValueError(f"Attachment {attachment_id} not found")

        attachment.classification_status = AttachmentClassificationStatus.DISCARDED
        attachment.discarded_reason = reason
        attachment.classified_at = datetime.now(timezone.utc)
        attachment.classified_by_user_id = user_id

        self.db.commit()

        logger.info(f"Discarded attachment {attachment_id}: {reason}")

        return {
            "success": True,
            "attachment_id": attachment_id,
            "discarded": True,
            "reason": reason
        }

    async def complete_classification_task(self, task_id: int, user_id: int) -> Dict[str, Any]:
        """
        Complete the classification task after all attachments are classified.
        """
        from main import Task, AttachmentIntake, EmailIntake, AttachmentClassificationStatus

        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.email_intake_id:
            raise ValueError("Task is not a document classification task")

        # Check all attachments are classified or discarded
        pending = self.db.query(AttachmentIntake).filter(
            AttachmentIntake.email_intake_id == task.email_intake_id,
            AttachmentIntake.classification_status == AttachmentClassificationStatus.PENDING
        ).count()

        if pending > 0:
            return {
                "success": False,
                "error": f"{pending} attachment(s) still pending classification"
            }

        # Complete the task
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)

        # Update email intake
        email_intake = self.db.query(EmailIntake).filter(
            EmailIntake.id == task.email_intake_id
        ).first()
        if email_intake:
            email_intake.processed_by_user_id = user_id

        self.db.commit()

        logger.info(f"Completed classification task {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "completed": True
        }

    async def _move_to_permanent_storage(self, attachment: Any) -> str:
        """
        Move file from temp intake storage to permanent classified location in S3.
        Organizes by borrower/loan/document type for easy retrieval.
        """
        try:
            s3_service = get_s3_service()

            # Get the classified document type (default to 'other' if not set)
            doc_type = getattr(attachment, 'classified_document_type', None) or 'other'

            # Look up org_id from the classified loan for tenant isolation
            classified_loan_id = getattr(attachment, 'classified_loan_id', None)
            org_id = None
            if classified_loan_id:
                from sqlalchemy import text
                row = self.db.execute(text(
                    "SELECT organization_id FROM loans WHERE id = :id"
                ), {"id": classified_loan_id}).first()
                org_id = row[0] if row else None

            # Generate permanent storage key based on classification
            permanent_key = s3_service.generate_document_key(
                borrower_id=attachment.classified_borrower_id,
                loan_id=classified_loan_id,
                doc_type=doc_type,
                filename=attachment.filename,
                organization_id=org_id,
            )

            # Move file from intake location to permanent location
            source_key = attachment.storage_location
            result = s3_service.move_file(
                source_key=source_key,
                dest_key=permanent_key,
                delete_source=True
            )

            if result.get("success"):
                logger.info(f"Moved document to permanent storage: {source_key} -> {permanent_key}")
                return permanent_key
            else:
                logger.error(f"Failed to move document: {result.get('error')}")
                raise Exception(f"S3 move failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error moving {attachment.filename} to permanent storage: {e}")
            # Fall back to placeholder path if S3 fails
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d')
            fallback_path = f"documents/{attachment.classified_borrower_id or 'unassigned'}/{timestamp}/{attachment.filename}"
            logger.warning(f"Using fallback path (S3 unavailable): {fallback_path}")
            return fallback_path
