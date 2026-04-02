"""
Smart Document Collection - Auto Renewal Scheduler

Manages automatic document renewal requests for time-sensitive documents.
Features:
- Infers payroll frequency from historical data
- Calculates next expected document dates
- Creates renewal requests before expiration
- Sends notifications to borrowers
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent,
    DocType, RequestStatus, PayrollFrequency, DocPolicyEventType
)
from services.smart_docs.freshness_validator import FreshnessValidator
from services.smart_docs.notification_service import SmartDocsNotificationService

logger = logging.getLogger(__name__)


class AutoRenewalScheduler:
    """
    Schedules automatic renewal requests for expiring documents.

    Works with documents marked as auto_renew=True in the needs list.
    Calculates optimal timing based on:
    - Document freshness requirements
    - Inferred payroll frequency (for paystubs)
    - Historical document submission patterns
    """

    # Days before expiration to create renewal request
    RENEWAL_BUFFER_DAYS = 5

    # Days to wait after expected availability before sending reminder
    REMINDER_DELAY_DAYS = 3

    def __init__(self, db: Session):
        self.db = db
        self.freshness_validator = FreshnessValidator()
        self.notification_service = SmartDocsNotificationService(db)

    def _get_notification_context(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get borrower and loan officer info for notifications.

        Args:
            loan_id: Loan ID
            borrower_id: Borrower ID

        Returns:
            Dict with borrower_email, borrower_name, loan_officer_name, portal_url
            or None if borrower info not found
        """
        from sqlalchemy import text

        # Get borrower info (first_name, last_name are separate columns)
        borrower_result = self.db.execute(
            text("SELECT email, first_name, last_name FROM borrower_profiles WHERE id = :borrower_id"),
            {"borrower_id": borrower_id}
        ).fetchone()

        if not borrower_result or not borrower_result[0]:
            logger.warning(f"No email found for borrower {borrower_id}")
            return None

        # Build full name from first_name and last_name
        first_name = borrower_result[1] or ""
        last_name = borrower_result[2] or ""
        borrower_name = f"{first_name} {last_name}".strip() or "Valued Customer"

        # Get loan officer info
        lo_result = self.db.execute(
            text("""
                SELECT u.full_name
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id
            """),
            {"loan_id": loan_id}
        ).fetchone()

        lo_name = lo_result[0] if lo_result and lo_result[0] else "Your Loan Officer"

        return {
            "borrower_email": borrower_result[0],
            "borrower_name": borrower_name,
            "loan_officer_name": lo_name,
            "portal_url": f"/borrower/documents?loan_id={loan_id}",  # Can be configured
        }

    def process_pending_renewals(self) -> Dict[str, Any]:
        """
        Process all documents that need renewal requests.

        Called periodically (e.g., daily via cron job).

        Returns:
            Summary of renewal actions taken
        """
        logger.info("Processing pending document renewals")

        today = date.today()
        created_requests = []
        sent_reminders = []
        errors = []

        # Find all document requests with auto_renew enabled
        # that have at least one accepted document
        auto_renew_requests = self.db.query(DocumentRequest).filter(
            and_(
                DocumentRequest.auto_renew == True,
                DocumentRequest.status == RequestStatus.ACCEPTED,
            )
        ).all()

        for request in auto_renew_requests:
            try:
                result = self._process_single_request(request, today)
                if result.get("renewal_created"):
                    created_requests.append(result)
                if result.get("reminder_sent"):
                    sent_reminders.append(result)
            except Exception as e:
                logger.error(f"Error processing renewal for request {request.id}: {e}")
                errors.append({
                    "request_id": request.id,
                    "error": "Internal server error",
                })

        logger.info(
            f"Renewal processing complete: {len(created_requests)} created, "
            f"{len(sent_reminders)} reminders, {len(errors)} errors"
        )

        return {
            "processed_date": today.isoformat(),
            "requests_processed": len(auto_renew_requests),
            "renewals_created": len(created_requests),
            "reminders_sent": len(sent_reminders),
            "errors": errors,
            "details": {
                "created": created_requests,
                "reminders": sent_reminders,
            },
        }

    def _process_single_request(
        self,
        request: DocumentRequest,
        today: date
    ) -> Dict[str, Any]:
        """Process a single document request for renewal."""
        result = {
            "request_id": request.id,
            "loan_id": request.loan_id,
            "doc_type": request.doc_type.value,
            "renewal_created": False,
            "reminder_sent": False,
        }

        # Get the most recent accepted document for this request
        latest_doc = self.db.query(SmartDocument).filter(
            and_(
                SmartDocument.request_id == request.id,
                SmartDocument.decision == "ACCEPT",
            )
        ).order_by(SmartDocument.doc_date.desc()).first()

        if not latest_doc or not latest_doc.doc_date:
            return result

        doc_date = latest_doc.doc_date
        if isinstance(doc_date, datetime):
            doc_date = doc_date.date()

        # Calculate expiration
        expires_at = self.freshness_validator.get_expiration_date(
            request.doc_type,
            doc_date,
            request.freshness_days,
        )

        if expires_at is None:
            return result

        days_until_expiry = (expires_at - today).days

        # Check if we need to create a renewal request
        if days_until_expiry <= self.RENEWAL_BUFFER_DAYS:
            # Check if there's already a pending renewal
            existing_renewal = self.db.query(DocumentRequest).filter(
                and_(
                    DocumentRequest.loan_id == request.loan_id,
                    DocumentRequest.doc_type == request.doc_type,
                    DocumentRequest.status == RequestStatus.OPEN,
                    DocumentRequest.created_at >= datetime.now() - timedelta(days=30),
                )
            ).first()

            if not existing_renewal:
                renewal = self._create_renewal_request(request, today)
                result["renewal_created"] = True
                result["new_request_id"] = renewal.id

        # Check if we should send a reminder
        if request.next_expected_available_at:
            expected_date = request.next_expected_available_at
            if isinstance(expected_date, datetime):
                expected_date = expected_date.date()

            days_since_expected = (today - expected_date).days

            if days_since_expected >= self.REMINDER_DELAY_DAYS:
                self._send_renewal_reminder(request, today)
                result["reminder_sent"] = True

        return result

    def _create_renewal_request(
        self,
        original_request: DocumentRequest,
        today: date,
    ) -> DocumentRequest:
        """Create a new renewal request based on an existing one."""
        # Calculate next expected date
        next_expected = self._calculate_next_expected(
            original_request.doc_type,
            original_request.payroll_frequency,
            today,
        )

        renewal = DocumentRequest(
            loan_id=original_request.loan_id,
            borrower_id=original_request.borrower_id,
            doc_type=original_request.doc_type,
            title=f"Updated {original_request.title}",
            description=f"Please upload updated {original_request.title}. Previous document is expiring soon.",
            instructions=original_request.instructions,
            required_count=original_request.required_count,
            applies_to=original_request.applies_to,
            priority=original_request.priority,
            freshness_days=original_request.freshness_days,
            auto_renew=True,
            payroll_frequency=original_request.payroll_frequency,
            next_expected_available_at=next_expected,
            status=RequestStatus.OPEN,
        )

        self.db.add(renewal)
        self.db.flush()

        # Log the event
        event = DocPolicyEvent(
            loan_id=original_request.loan_id,
            request_id=renewal.id,
            event_type=DocPolicyEventType.AUTO_REQUEST_CREATED,
            payload={
                "original_request_id": original_request.id,
                "doc_type": original_request.doc_type.value,
                "reason": "auto_renewal",
            },
        )
        self.db.add(event)
        self.db.commit()

        logger.info(
            f"Created renewal request {renewal.id} for loan {original_request.loan_id}, "
            f"doc_type={original_request.doc_type.value}"
        )

        # Send notification email to borrower about new renewal request
        context = self._get_notification_context(renewal.loan_id, renewal.borrower_id)
        if context:
            try:
                self.notification_service.send_document_request_notification(
                    request=renewal,
                    borrower_email=context["borrower_email"],
                    borrower_name=context["borrower_name"],
                    loan_officer_name=context["loan_officer_name"],
                    portal_url=context["portal_url"],
                )
                logger.info("Sent renewal request notification")
            except Exception as e:
                logger.error(f"Failed to send renewal request notification: {e}")

        return renewal

    def _calculate_next_expected(
        self,
        doc_type: DocType,
        payroll_frequency: Optional[PayrollFrequency],
        reference_date: date,
    ) -> Optional[datetime]:
        """Calculate when the next document should be available."""
        if doc_type == DocType.PAYSTUB and payroll_frequency:
            freq_days = {
                PayrollFrequency.WEEKLY: 7,
                PayrollFrequency.BIWEEKLY: 14,
                PayrollFrequency.SEMIMONTHLY: 15,
                PayrollFrequency.MONTHLY: 30,
            }
            days = freq_days.get(payroll_frequency, 14)
            return datetime.combine(
                reference_date + timedelta(days=days),
                datetime.min.time()
            )

        elif doc_type == DocType.BANK_STATEMENT:
            # Statements typically available after month end
            next_month = reference_date.replace(day=1) + timedelta(days=32)
            statement_date = next_month.replace(day=5)  # Usually available by 5th
            return datetime.combine(statement_date, datetime.min.time())

        elif doc_type in [DocType.PROFIT_LOSS, DocType.BALANCE_SHEET]:
            # Monthly financial statements
            next_month = reference_date.replace(day=1) + timedelta(days=32)
            return datetime.combine(next_month.replace(day=10), datetime.min.time())

        elif doc_type in [DocType.W2, DocType.TAX_RETURN, DocType.BUSINESS_TAX_RETURN]:
            # W-2s and Tax Returns are annual documents
            # They become available after January 31 of the following year
            # On Feb 1, we can request the previous year's W-2
            required_years = self.freshness_validator.get_current_required_tax_years(
                num_years=2, reference_date=reference_date
            )
            # Next year's document becomes available Feb 1
            newest_needed = required_years[0]
            # W-2 for year X becomes available Feb 1 of year X+1
            available_date = date(newest_needed + 1, 2, 1)
            return datetime.combine(available_date, datetime.min.time())

        return None

    def _send_renewal_reminder(
        self,
        request: DocumentRequest,
        today: date,
    ) -> None:
        """Send a reminder for pending document renewal."""
        # Log the reminder event
        event = DocPolicyEvent(
            loan_id=request.loan_id,
            request_id=request.id,
            event_type=DocPolicyEventType.EXPIRATION_REMINDER_SENT,
            payload={
                "doc_type": request.doc_type.value,
                "reminder_date": today.isoformat(),
            },
        )
        self.db.add(event)
        self.db.commit()

        logger.info(
            f"Sent renewal reminder for request {request.id}, "
            f"loan {request.loan_id}, doc_type={request.doc_type.value}"
        )

        # Send notification email to borrower
        context = self._get_notification_context(request.loan_id, request.borrower_id)
        if context:
            try:
                self.notification_service.send_document_request_notification(
                    request=request,
                    borrower_email=context["borrower_email"],
                    borrower_name=context["borrower_name"],
                    loan_officer_name=context["loan_officer_name"],
                    portal_url=context["portal_url"],
                )
                logger.info("Sent renewal reminder email")
            except Exception as e:
                logger.error(f"Failed to send renewal reminder email: {e}")

    def infer_payroll_frequency(
        self,
        borrower_id: int,
        recent_paystubs: int = 5,
    ) -> Optional[PayrollFrequency]:
        """
        Infer payroll frequency from historical paystub submissions.

        Analyzes the dates of recent paystubs to determine frequency.

        Args:
            borrower_id: Borrower ID to analyze
            recent_paystubs: Number of recent paystubs to consider

        Returns:
            Inferred PayrollFrequency or None
        """
        # Get recent paystubs with dates
        paystubs = self.db.query(SmartDocument).filter(
            and_(
                SmartDocument.borrower_id == borrower_id,
                SmartDocument.doc_type == DocType.PAYSTUB,
                SmartDocument.doc_date.isnot(None),
            )
        ).order_by(
            SmartDocument.doc_date.desc()
        ).limit(recent_paystubs).all()

        if len(paystubs) < 2:
            return None

        # Calculate intervals between pay dates
        dates = [p.doc_date for p in paystubs if p.doc_date]
        if isinstance(dates[0], datetime):
            dates = [d.date() for d in dates]

        dates = sorted(dates, reverse=True)
        intervals = []

        for i in range(len(dates) - 1):
            interval = (dates[i] - dates[i + 1]).days
            intervals.append(interval)

        if not intervals:
            return None

        avg_interval = sum(intervals) / len(intervals)

        # Classify based on average interval
        if 5 <= avg_interval <= 9:
            return PayrollFrequency.WEEKLY
        elif 12 <= avg_interval <= 16:
            return PayrollFrequency.BIWEEKLY
        elif 14 <= avg_interval <= 17:
            # Could be biweekly or semimonthly, check for consistency
            if all(12 <= i <= 16 for i in intervals):
                return PayrollFrequency.BIWEEKLY
            return PayrollFrequency.SEMIMONTHLY
        elif 28 <= avg_interval <= 33:
            return PayrollFrequency.MONTHLY

        # Can't determine confidently
        return None

    def update_payroll_frequency(
        self,
        loan_id: int,
        borrower_id: int,
        frequency: PayrollFrequency,
    ) -> int:
        """
        Update payroll frequency for all paystub requests.

        Args:
            loan_id: Loan ID
            borrower_id: Borrower ID
            frequency: Payroll frequency to set

        Returns:
            Number of requests updated
        """
        updated = self.db.query(DocumentRequest).filter(
            and_(
                DocumentRequest.loan_id == loan_id,
                DocumentRequest.borrower_id == borrower_id,
                DocumentRequest.doc_type == DocType.PAYSTUB,
            )
        ).update({
            DocumentRequest.payroll_frequency: frequency,
            DocumentRequest.updated_at: datetime.now(timezone.utc),
        })

        self.db.commit()
        logger.info(f"Updated payroll frequency to {frequency.value} for {updated} requests")

        return updated

    def get_upcoming_expirations(
        self,
        loan_id: Optional[int] = None,
        days_ahead: int = 14,
    ) -> List[Dict[str, Any]]:
        """
        Get documents expiring within the specified window.

        Args:
            loan_id: Optional loan ID filter
            days_ahead: Number of days to look ahead

        Returns:
            List of expiring documents with details
        """
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        query = self.db.query(SmartDocument).filter(
            and_(
                SmartDocument.is_expired == False,
                SmartDocument.doc_expires_at.isnot(None),
                SmartDocument.doc_expires_at <= cutoff,
                SmartDocument.doc_expires_at >= today,
            )
        )

        if loan_id:
            query = query.filter(SmartDocument.loan_id == loan_id)

        expiring = query.order_by(SmartDocument.doc_expires_at).all()

        return [
            {
                "document_id": doc.id,
                "loan_id": doc.loan_id,
                "borrower_id": doc.borrower_id,
                "doc_type": doc.doc_type.value if doc.doc_type else None,
                "file_name": doc.file_name,
                "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
                "expires_at": doc.doc_expires_at.isoformat() if doc.doc_expires_at else None,
                "days_until_expiry": (doc.doc_expires_at.date() - today).days if doc.doc_expires_at else None,
            }
            for doc in expiring
        ]

    def mark_document_expired(self, document_id: int) -> bool:
        """
        Mark a document as expired.

        Args:
            document_id: Document ID to mark

        Returns:
            True if updated, False if not found
        """
        doc = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not doc:
            return False

        doc.is_expired = True
        doc.updated_at = datetime.now(timezone.utc)

        # Log the event
        event = DocPolicyEvent(
            loan_id=doc.loan_id,
            document_id=doc.id,
            event_type=DocPolicyEventType.EXPIRED,
            payload={
                "doc_type": doc.doc_type.value if doc.doc_type else None,
                "expired_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.db.add(event)
        self.db.commit()

        logger.info(f"Marked document {document_id} as expired")

        return True

    def run_expiration_check(self) -> Dict[str, Any]:
        """
        Check for and mark expired documents.

        Called periodically to update expiration status.

        Returns:
            Summary of expiration updates
        """
        today = date.today()

        # Find documents that have passed their expiration date
        expired_docs = self.db.query(SmartDocument).filter(
            and_(
                SmartDocument.is_expired == False,
                SmartDocument.doc_expires_at.isnot(None),
                SmartDocument.doc_expires_at < today,
            )
        ).all()

        expired_count = 0
        for doc in expired_docs:
            self.mark_document_expired(doc.id)
            expired_count += 1

        logger.info(f"Expiration check: marked {expired_count} documents as expired")

        return {
            "check_date": today.isoformat(),
            "documents_expired": expired_count,
        }

    # =========================================================================
    # PAY-CYCLE BASED EXPIRATION (Income Extraction Integration)
    # =========================================================================

    # Expiration days based on pay frequency
    PAY_FREQUENCY_EXPIRATION_DAYS = {
        PayrollFrequency.WEEKLY: 7,
        PayrollFrequency.BIWEEKLY: 30,
        PayrollFrequency.SEMIMONTHLY: 30,
        PayrollFrequency.MONTHLY: 45,
    }

    def calculate_paystub_expiration(
        self,
        pay_date: date,
        pay_frequency: PayrollFrequency,
    ) -> date:
        """
        Calculate paystub expiration date based on pay frequency.

        Args:
            pay_date: The pay date from the paystub
            pay_frequency: The payroll frequency

        Returns:
            Expiration date
        """
        days_until_expire = self.PAY_FREQUENCY_EXPIRATION_DAYS.get(pay_frequency, 30)
        return pay_date + timedelta(days=days_until_expire)

    def process_paystub_extraction_expiration(
        self,
        document_id: int,
        pay_date: date,
        pay_frequency: str,
    ) -> Dict[str, Any]:
        """
        Update document expiration based on extracted paystub data.

        Called after AI extracts paystub data to set correct expiration.

        Args:
            document_id: SmartDocument ID
            pay_date: Extracted pay date
            pay_frequency: Extracted pay frequency (WEEKLY, BIWEEKLY, etc.)

        Returns:
            Updated expiration info
        """
        doc = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not doc:
            return {"success": False, "error": "Document not found"}

        # Convert string to enum if needed
        try:
            freq_enum = PayrollFrequency(pay_frequency.upper())
        except ValueError:
            freq_enum = PayrollFrequency.BIWEEKLY  # Default

        expires_at = self.calculate_paystub_expiration(pay_date, freq_enum)

        # Update document
        doc.doc_date = pay_date
        doc.doc_expires_at = expires_at
        doc.is_expired = expires_at < date.today()
        doc.updated_at = datetime.now(timezone.utc)

        # Update the associated request with inferred frequency
        if doc.request_id:
            request = self.db.query(DocumentRequest).filter(
                DocumentRequest.id == doc.request_id
            ).first()
            if request:
                request.payroll_frequency = freq_enum
                request.updated_at = datetime.now(timezone.utc)

        self.db.commit()

        logger.info(
            f"Updated paystub {document_id} expiration: pay_date={pay_date}, "
            f"frequency={freq_enum.value}, expires={expires_at}"
        )

        return {
            "success": True,
            "document_id": document_id,
            "pay_date": pay_date.isoformat(),
            "pay_frequency": freq_enum.value,
            "expires_at": expires_at.isoformat(),
            "is_expired": expires_at < date.today(),
            "days_until_expiry": (expires_at - date.today()).days,
        }

    def trigger_immediate_renewal(
        self,
        loan_id: int,
        borrower_id: int,
        doc_type: DocType,
        reason: str = "expired",
    ) -> Optional[DocumentRequest]:
        """
        Immediately create a renewal request for an expired document.

        Used when a paystub expires based on pay cycle.

        Args:
            loan_id: Loan ID
            borrower_id: Borrower ID
            doc_type: Document type to renew
            reason: Reason for immediate renewal

        Returns:
            New DocumentRequest or None if unable to create
        """
        # Find the most recent request for this doc type
        original = self.db.query(DocumentRequest).filter(
            and_(
                DocumentRequest.loan_id == loan_id,
                DocumentRequest.borrower_id == borrower_id,
                DocumentRequest.doc_type == doc_type,
            )
        ).order_by(DocumentRequest.created_at.desc()).first()

        if not original:
            logger.warning(
                f"No original request found for loan={loan_id}, "
                f"borrower={borrower_id}, doc_type={doc_type.value}"
            )
            return None

        # Check if there's already a pending request
        existing = self.db.query(DocumentRequest).filter(
            and_(
                DocumentRequest.loan_id == loan_id,
                DocumentRequest.borrower_id == borrower_id,
                DocumentRequest.doc_type == doc_type,
                DocumentRequest.status == RequestStatus.OPEN,
            )
        ).first()

        if existing:
            logger.info(f"Pending request already exists: {existing.id}")
            return existing

        # Calculate next expected date
        next_expected = self._calculate_next_expected(
            doc_type,
            original.payroll_frequency,
            date.today(),
        )

        # Create immediate renewal request
        renewal = DocumentRequest(
            loan_id=loan_id,
            borrower_id=borrower_id,
            doc_type=doc_type,
            title=f"Updated {original.title}",
            description=f"Your previous {original.title} has expired. Please upload a new one.",
            instructions=original.instructions,
            required_count=1,
            applies_to=original.applies_to,
            priority=original.priority,
            freshness_days=original.freshness_days,
            auto_renew=True,
            payroll_frequency=original.payroll_frequency,
            next_expected_available_at=next_expected,
            status=RequestStatus.OPEN,
        )

        self.db.add(renewal)
        self.db.flush()

        # Log the event
        event = DocPolicyEvent(
            loan_id=loan_id,
            request_id=renewal.id,
            event_type=DocPolicyEventType.AUTO_REQUEST_CREATED,
            payload={
                "original_request_id": original.id,
                "doc_type": doc_type.value,
                "reason": reason,
                "triggered": "immediate",
            },
        )
        self.db.add(event)
        self.db.commit()

        logger.info(
            f"Created immediate renewal request {renewal.id} for loan {loan_id}, "
            f"doc_type={doc_type.value}, reason={reason}"
        )

        # Send notification
        context = self._get_notification_context(loan_id, borrower_id)
        if context:
            try:
                self.notification_service.send_document_request_notification(
                    request=renewal,
                    borrower_email=context["borrower_email"],
                    borrower_name=context["borrower_name"],
                    loan_officer_name=context["loan_officer_name"],
                    portal_url=context["portal_url"],
                )
            except Exception as e:
                logger.error(f"Failed to send renewal notification: {e}")

        return renewal

    def check_and_renew_expired_paystubs(self) -> Dict[str, Any]:
        """
        Check all paystubs with extracted data for expiration and trigger renewals.

        Uses the PaystubExtraction table to find documents past their
        pay-cycle based expiration date.

        Returns:
            Summary of renewals triggered
        """
        from sqlalchemy import text

        today = date.today()
        renewals_created = []
        errors = []

        # Find expired paystub extractions that haven't been renewed yet
        try:
            expired_paystubs = self.db.execute(text("""
                SELECT pe.id, pe.document_id, pe.borrower_id, pe.loan_id,
                       pe.pay_date, pe.pay_frequency, pe.expires_at
                FROM paystub_extractions pe
                LEFT JOIN document_requests dr ON (
                    dr.loan_id = pe.loan_id
                    AND dr.borrower_id = pe.borrower_id
                    AND dr.doc_type = 'PAYSTUB'
                    AND dr.status = 'OPEN'
                    AND dr.created_at >= pe.expires_at
                )
                WHERE pe.expires_at < :today
                  AND pe.is_expired = false
                  AND dr.id IS NULL
            """), {"today": today}).fetchall()

            for paystub in expired_paystubs:
                try:
                    # Mark as expired
                    self.db.execute(text("""
                        UPDATE paystub_extractions
                        SET is_expired = true, updated_at = :now
                        WHERE id = :id
                    """), {"id": paystub[0], "now": datetime.now(timezone.utc)})

                    # Trigger immediate renewal
                    renewal = self.trigger_immediate_renewal(
                        loan_id=paystub[3],
                        borrower_id=paystub[2],
                        doc_type=DocType.PAYSTUB,
                        reason="pay_cycle_expired",
                    )

                    if renewal:
                        renewals_created.append({
                            "paystub_extraction_id": paystub[0],
                            "document_id": paystub[1],
                            "new_request_id": renewal.id,
                            "expired_at": paystub[6].isoformat() if paystub[6] else None,
                        })

                except Exception as e:
                    errors.append({
                        "paystub_extraction_id": paystub[0],
                        "error": "Internal server error",
                    })

            self.db.commit()

        except Exception as e:
            logger.error(f"Error checking paystub expirations: {e}")
            errors.append({"error": "Internal server error"})

        logger.info(
            f"Paystub expiration check: {len(renewals_created)} renewals, "
            f"{len(errors)} errors"
        )

        return {
            "check_date": today.isoformat(),
            "renewals_created": len(renewals_created),
            "errors": len(errors),
            "details": renewals_created,
            "error_details": errors,
        }
