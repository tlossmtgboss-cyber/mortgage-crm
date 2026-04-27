"""
Smart Docs Queue Service

Provides client-centric queue view with:
- Completion percentage tracking
- SLA status aggregation
- Prioritized sorting (breaches first, then completion, then activity)
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from models.smart_docs_models import (
    DocumentRequest, SmartDocument, RequestStatus, ClientReminderSettings
)
from services.smart_docs.sla_service import SLAService, SLAStatus

logger = logging.getLogger(__name__)


class QueueService:
    """Service for managing the document queue view."""

    def __init__(self, db: Session, organization_id: int):
        if not organization_id:
            raise ValueError("organization_id is required for QueueService")
        self.db = db
        self.organization_id = organization_id
        self.sla_service = SLAService(db)

    def _get_tenant_loan_ids(self) -> List[int]:
        """Get loan IDs belonging to this organization.

        Used to scope all queries to the current tenant since DocumentRequest
        and SmartDocument tables do not have an organization_id column.
        """
        try:
            rows = self.db.execute(text(
                "SELECT id FROM loans WHERE organization_id = :org_id"
            ), {"org_id": self.organization_id}).fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.exception("Failed to fetch tenant loan IDs for org %s", self.organization_id)
            raise  # Critical path: callers use this for tenant scoping/access control

    def get_queue(
        self,
        page: int = 1,
        limit: int = 20,
        filter_sla_status: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the prioritized client queue.

        Returns clients sorted by:
        1. SLA breaches first
        2. Lowest completion percentage
        3. Most recent activity

        Args:
            page: Page number (1-indexed)
            limit: Items per page
            filter_sla_status: Optional filter by SLA status (GOOD, AT_RISK, BREACHED)
            search_query: Optional search by borrower name or loan number

        Returns:
            Dict with queue items and pagination info
        """
        # Get loan IDs scoped to this organization
        tenant_loan_ids = self._get_tenant_loan_ids()
        if not tenant_loan_ids:
            return {
                "queue": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "total_pages": 1,
                "summary": {"total_clients": 0, "with_breaches": 0, "at_risk": 0},
            }

        # Get unique loan_ids with active document requests, scoped to tenant
        loan_ids_query = self.db.query(
            DocumentRequest.loan_id
        ).filter(
            DocumentRequest.is_active == True,
            DocumentRequest.loan_id.in_(tenant_loan_ids),
        ).distinct()

        loan_ids = [row.loan_id for row in loan_ids_query.all()]

        # Build queue items
        queue_items = []
        for loan_id in loan_ids:
            item = self._build_queue_item(loan_id)
            if item:
                # Apply SLA filter if specified
                if filter_sla_status and item['sla_status'] != filter_sla_status:
                    continue

                # Apply search filter
                if search_query:
                    query_lower = search_query.lower()
                    name_match = item['borrower_name'] and query_lower in item['borrower_name'].lower()
                    loan_match = item['loan_number'] and query_lower in str(item['loan_number']).lower()
                    id_match = query_lower in str(item['loan_id'])
                    if not (name_match or loan_match or id_match):
                        continue

                queue_items.append(item)

        # Sort: breaches first, then by completion (lowest first), then by activity (most recent first)
        queue_items.sort(key=lambda x: (
            0 if x['has_sla_breach'] else 1,      # Breaches first
            x['completion_percentage'],            # Lowest completion first
            -(x['last_activity_ts'] or 0),        # Most recent activity first
        ))

        # Calculate totals before pagination
        total = len(queue_items)

        # Paginate
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_items = queue_items[start_idx:end_idx]

        # Remove internal timestamp field from response
        for item in paginated_items:
            if 'last_activity_ts' in item:
                del item['last_activity_ts']

        return {
            "queue": paginated_items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit > 0 else 1,
            "summary": {
                "total_clients": total,
                "with_breaches": len([i for i in queue_items if i['has_sla_breach']]),
                "at_risk": len([i for i in queue_items if i['sla_status'] == 'AT_RISK']),
            }
        }

    def _build_queue_item(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Build a single queue item for a loan."""

        # Get loan info from loans table
        loan_info = None
        try:
            result = self.db.execute(text("""
                SELECT id, loan_number, borrower_name, borrower_email, stage, created_at
                FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if result:
                loan_info = dict(result._mapping)
        except Exception as e:
            logger.error("Could not fetch from loans table for loan %s: %s", loan_id, e)

        # Fallback to purl_loans if main loans table doesn't have it
        if not loan_info:
            try:
                from models.purl import PURLLoan, PURLWorkspace
                purl_loan = self.db.query(PURLLoan).filter(PURLLoan.id == loan_id).first()
                if purl_loan:
                    workspace = None
                    if purl_loan.workspace_id:
                        workspace = self.db.query(PURLWorkspace).filter(
                            PURLWorkspace.id == purl_loan.workspace_id
                        ).first()

                    loan_info = {
                        'id': loan_id,
                        'loan_number': purl_loan.loan_number,
                        'borrower_name': workspace.display_name if workspace else f"Loan {loan_id}",
                        'borrower_email': None,
                        'stage': getattr(purl_loan, 'stage', None),
                        'created_at': purl_loan.created_at,
                    }
            except Exception as e:
                logger.error("Could not fetch from purl_loans for loan %s: %s", loan_id, e)

        if not loan_info:
            # Create minimal info if no loan found
            loan_info = {
                'id': loan_id,
                'loan_number': None,
                'borrower_name': f"Loan {loan_id}",
                'borrower_email': None,
                'stage': None,
                'created_at': None,
            }

        # Get request stats
        requests = self.db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True
        ).all()

        if not requests:
            return None  # No active requests

        total_requested = len(requests)
        received_valid = len([r for r in requests if r.status == RequestStatus.ACCEPTED])

        completion_pct = (received_valid / total_requested * 100) if total_requested > 0 else 0

        # Get SLA summary
        sla_summary = self.sla_service.get_client_sla_summary(loan_id)

        # Get last activity (most recent document upload)
        last_doc = self.db.query(SmartDocument).filter(
            SmartDocument.loan_id == loan_id
        ).order_by(SmartDocument.created_at.desc()).first()

        last_activity = last_doc.created_at if last_doc else None

        # Get reminder settings
        reminder_settings = self.db.query(ClientReminderSettings).filter(
            ClientReminderSettings.loan_id == loan_id
        ).first()

        return {
            "loan_id": loan_id,
            "loan_number": loan_info.get('loan_number'),
            "borrower_name": loan_info.get('borrower_name') or f"Loan {loan_id}",
            "borrower_email": loan_info.get('borrower_email'),
            "stage": loan_info.get('stage'),

            # Completion tracking
            "total_requested": total_requested,
            "received_valid": received_valid,
            "completion_percentage": round(completion_pct, 1),

            # SLA tracking
            "sla_status": sla_summary['sla_status'],
            "has_sla_breach": sla_summary['has_breach'],
            "breached_count": sla_summary['breached_count'],
            "at_risk_count": sla_summary['at_risk_count'],

            # Activity tracking
            "last_activity": last_activity.isoformat() if last_activity else None,
            "last_activity_ts": last_activity.timestamp() if last_activity else 0,

            # Reminder info
            "reminders_enabled": reminder_settings.reminders_enabled if reminder_settings else True,
            "last_reminder_sent": (
                reminder_settings.last_reminder_sent_at.isoformat()
                if reminder_settings and reminder_settings.last_reminder_sent_at
                else None
            ),
        }

    def get_queue_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for the queue.

        Returns:
            Dict with counts by SLA status
        """
        # Get loan IDs scoped to this organization
        tenant_loan_ids = self._get_tenant_loan_ids()
        if not tenant_loan_ids:
            return {
                "total_clients_in_queue": 0,
                "by_sla_status": {"breached": 0, "at_risk": 0, "good": 0},
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Get all unique loan_ids with active requests, scoped to tenant
        all_loan_ids = self.db.query(
            DocumentRequest.loan_id
        ).filter(
            DocumentRequest.is_active == True,
            DocumentRequest.status.in_([RequestStatus.OPEN, RequestStatus.PENDING_REVIEW]),
            DocumentRequest.loan_id.in_(tenant_loan_ids),
        ).distinct().all()

        breached = 0
        at_risk = 0
        good = 0

        for (loan_id,) in all_loan_ids:
            summary = self.sla_service.get_client_sla_summary(loan_id)
            if summary['sla_status'] == SLAStatus.BREACHED.value:
                breached += 1
            elif summary['sla_status'] == SLAStatus.AT_RISK.value:
                at_risk += 1
            else:
                good += 1

        return {
            "total_clients_in_queue": len(all_loan_ids),
            "by_sla_status": {
                "breached": breached,
                "at_risk": at_risk,
                "good": good,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_client_queue_detail(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed queue information for a specific client.

        Args:
            loan_id: The loan ID to get details for

        Returns:
            Dict with detailed queue information or None if not found
        """
        # Verify this loan belongs to the current tenant
        if loan_id not in self._get_tenant_loan_ids():
            return None

        item = self._build_queue_item(loan_id)
        if not item:
            return None

        # Add request details
        requests = self.db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True
        ).order_by(
            DocumentRequest.sla_due_at.asc().nullslast()
        ).all()

        item['requests'] = [
            {
                "id": req.id,
                "doc_type": req.doc_type.value if req.doc_type else None,
                "title": req.title,
                "status": req.status.value if req.status else None,
                "sla_due_at": req.sla_due_at.isoformat() if req.sla_due_at else None,
                "sla_status": self.sla_service.get_sla_status(req).value,
                "created_at": req.created_at.isoformat() if req.created_at else None,
            }
            for req in requests
        ]

        # Remove internal field
        if 'last_activity_ts' in item:
            del item['last_activity_ts']

        return item
