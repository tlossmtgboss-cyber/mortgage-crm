"""
Perennia Docs Expiration Monitor Worker

Monitors document expiration and triggers notifications.

Features:
- Expiration date tracking
- Warning notifications before expiration
- Status updates for expired documents
- Request status updates
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ExpirationCheck:
    """Result of expiration check for a document."""
    document_id: int
    status: str  # valid, expiring_soon, expired
    days_until_expiration: Optional[int] = None
    action_taken: Optional[str] = None


class PerenniaExpirationMonitor:
    """
    Monitors document expiration dates and triggers actions.

    Checks:
    - Documents expiring within warning window
    - Already expired documents
    - Request status updates based on document expiration
    """

    def __init__(self, db: Session):
        """
        Initialize monitor.

        Args:
            db: Database session
        """
        self.db = db
        self.warning_days = [30, 14, 7, 3, 1]  # Days before expiration to warn
        self.batch_size = 100

    def check_expiring_documents(self) -> List[ExpirationCheck]:
        """Check for documents that are expiring soon."""
        results = []

        for days in self.warning_days:
            # Find documents expiring in exactly N days
            expiring = self.db.execute(text("""
                SELECT d.id, d.loan_id, d.lead_id, d.request_id,
                       d.file_name, d.doc_type, d.expires_at
                FROM perennia_documents d
                WHERE d.status = 'approved'
                  AND d.expires_at IS NOT NULL
                  AND d.expires_at::date = (CURRENT_DATE + :days)
            """), {"days": days})

            for row in expiring:
                doc = dict(row._mapping)
                check = ExpirationCheck(
                    document_id=doc['id'],
                    status='expiring_soon',
                    days_until_expiration=days
                )

                # Create notification
                self._create_expiration_warning(doc, days)
                check.action_taken = f"notification_created_{days}_days"

                results.append(check)

        return results

    def check_expired_documents(self) -> List[ExpirationCheck]:
        """Check for documents that have expired."""
        results = []

        # Find expired documents still marked as approved
        expired = self.db.execute(text("""
            SELECT id, loan_id, lead_id, request_id, file_name, doc_type
            FROM perennia_documents
            WHERE status = 'approved'
              AND expires_at IS NOT NULL
              AND expires_at < CURRENT_TIMESTAMP
        """))

        for row in expired:
            doc = dict(row._mapping)
            doc_id = doc['id']

            # Update status to expired
            self.db.execute(text("""
                UPDATE perennia_documents
                SET status = 'expired', updated_at = NOW()
                WHERE id = :id
            """), {"id": doc_id})

            # Log event
            self.db.execute(text("""
                INSERT INTO perennia_document_events (
                    document_id, loan_id, lead_id, request_id,
                    event_type, event_data, actor_type, created_at
                ) VALUES (
                    :doc_id, :loan_id, :lead_id, :request_id,
                    'document_expired', :event_data, 'system', NOW()
                )
            """), {
                "doc_id": doc_id,
                "loan_id": doc.get('loan_id'),
                "lead_id": doc.get('lead_id'),
                "request_id": doc.get('request_id'),
                "event_data": {"doc_type": doc.get('doc_type'), "file_name": doc.get('file_name')}
            })

            # Update request status if applicable
            if doc.get('request_id'):
                self._update_request_status(doc['request_id'])

            self.db.commit()

            results.append(ExpirationCheck(
                document_id=doc_id,
                status='expired',
                action_taken='status_updated'
            ))

        return results

    def _create_expiration_warning(self, document: Dict[str, Any], days: int):
        """Create a warning notification for expiring document."""
        doc_type = document.get('doc_type', 'document')
        file_name = document.get('file_name', 'Unknown')

        subject = f"Document Expiring Soon: {doc_type}"
        body = f"Your {doc_type} ({file_name}) will expire in {days} day{'s' if days != 1 else ''}. Please upload a new version to avoid delays."

        self.db.execute(text("""
            INSERT INTO perennia_notifications (
                loan_id, lead_id, channel, template,
                subject, body, metadata, status,
                created_at, updated_at
            ) VALUES (
                :loan_id, :lead_id, 'email', 'document_expiring',
                :subject, :body, :metadata, 'pending',
                NOW(), NOW()
            )
        """), {
            "loan_id": document.get('loan_id'),
            "lead_id": document.get('lead_id'),
            "subject": subject,
            "body": body,
            "metadata": {
                "document_id": document['id'],
                "doc_type": doc_type,
                "days_until_expiration": days
            }
        })
        self.db.commit()

    def _update_request_status(self, request_id: int):
        """Update request status based on document expiration."""
        # Check if any approved documents remain
        result = self.db.execute(text("""
            SELECT dr.quantity,
                   COUNT(d.id) FILTER (WHERE d.status = 'approved') as approved_count
            FROM perennia_document_requests dr
            LEFT JOIN perennia_documents d ON d.request_id = dr.id
            WHERE dr.id = :request_id
            GROUP BY dr.id
        """), {"request_id": request_id})

        row = result.fetchone()
        if row and row[1] < row[0]:
            # No longer complete
            self.db.execute(text("""
                UPDATE perennia_document_requests
                SET status = 'in_progress', updated_at = NOW()
                WHERE id = :id AND status = 'complete'
            """), {"id": request_id})
            self.db.commit()

    def check_overdue_requests(self) -> List[Dict[str, Any]]:
        """Check for requests past their due date."""
        results = []

        # Find overdue requests
        overdue = self.db.execute(text("""
            SELECT id, loan_id, lead_id, doc_type, title, expiration_date
            FROM perennia_document_requests
            WHERE status NOT IN ('complete', 'cancelled')
              AND expiration_date IS NOT NULL
              AND expiration_date < CURRENT_TIMESTAMP
        """))

        for row in overdue:
            req = dict(row._mapping)
            req_id = req['id']

            # Update status to overdue
            self.db.execute(text("""
                UPDATE perennia_document_requests
                SET status = 'overdue', updated_at = NOW()
                WHERE id = :id AND status != 'overdue'
            """), {"id": req_id})

            results.append({
                "request_id": req_id,
                "doc_type": req.get('doc_type'),
                "action": "marked_overdue"
            })

        self.db.commit()
        return results

    def run(self) -> Dict[str, Any]:
        """Run all expiration checks."""
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "expiring_soon": [],
            "expired": [],
            "overdue_requests": []
        }

        try:
            results["expiring_soon"] = [
                {"document_id": c.document_id, "days": c.days_until_expiration, "action": c.action_taken}
                for c in self.check_expiring_documents()
            ]

            results["expired"] = [
                {"document_id": c.document_id, "action": c.action_taken}
                for c in self.check_expired_documents()
            ]

            results["overdue_requests"] = self.check_overdue_requests()

            results["summary"] = {
                "expiring_soon_count": len(results["expiring_soon"]),
                "expired_count": len(results["expired"]),
                "overdue_requests_count": len(results["overdue_requests"])
            }

        except Exception as e:
            logger.error(f"Expiration monitor error: {e}")
            results["error"] = str(e)

        return results


def run_expiration_monitor(db: Session) -> Dict[str, Any]:
    """
    Run expiration monitor.

    Args:
        db: Database session

    Returns:
        Dict with monitoring results
    """
    monitor = PerenniaExpirationMonitor(db)
    return monitor.run()
