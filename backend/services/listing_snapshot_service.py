"""
Listing Transaction Snapshot Service
Generates PII-safe snapshots of transaction status for weekly updates.
"""

import hashlib
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

from sqlalchemy.exc import SQLAlchemyError
from models.listing_portal import (
    TransactionSnapshot, validate_no_pii, FORBIDDEN_PII_KEYS
)

logger = logging.getLogger(__name__)


class ListingSnapshotService:
    """Service for creating PII-safe transaction snapshots"""

    def __init__(self):
        pass

    def create_snapshot(
        self,
        db: Session,
        transaction_id: int,
        snapshot_type: str = "automatic",
        triggered_by: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a PII-safe snapshot of the transaction state.
        Used for weekly updates and change detection.
        """
        try:
            # Get transaction details
            result = db.execute(text("""
                SELECT
                    t.id, t.property_address, t.property_city, t.property_state,
                    t.property_zip, t.purchase_price, t.target_close_date,
                    t.current_status, t.contract_date
                FROM listing_transactions t
                WHERE t.id = :id
            """), {"id": transaction_id})
            txn = result.fetchone()

            if not txn:
                return None

            # Calculate days until close
            days_until_close = None
            if txn.target_close_date:
                if isinstance(txn.target_close_date, str):
                    close_date = datetime.strptime(txn.target_close_date, "%Y-%m-%d").date()
                else:
                    close_date = txn.target_close_date
                days_until_close = (close_date - date.today()).days

            # Get milestones
            milestones_result = db.execute(text("""
                SELECT
                    milestone_key, milestone_name, status, completed_at, display_order
                FROM listing_milestones
                WHERE transaction_id = :id
                ORDER BY display_order
            """), {"id": transaction_id})

            milestones = []
            completed_count = 0
            total_count = 0

            for m in milestones_result.fetchall():
                milestones.append({
                    "key": m.milestone_key,
                    "name": m.milestone_name,
                    "status": m.status,
                    "completed_at": m.completed_at.isoformat() if m.completed_at else None
                })
                total_count += 1
                if m.status == "completed":
                    completed_count += 1

            # Get recent activity (last 7 days)
            recent_activity = self._get_recent_activity(db, transaction_id)

            # Build snapshot data
            snapshot_data = {
                "transaction_id": transaction_id,
                "property_address": txn.property_address,
                "property_city": txn.property_city,
                "property_state": txn.property_state,
                "purchase_price": float(txn.purchase_price) if txn.purchase_price else None,
                "target_close_date": txn.target_close_date.isoformat() if txn.target_close_date else None,
                "current_status": txn.current_status,
                "days_until_close": days_until_close,
                "milestones": milestones,
                "milestone_progress": {
                    "completed": completed_count,
                    "total": total_count
                },
                "recent_activity": recent_activity,
                "snapshot_at": datetime.now(timezone.utc).isoformat()
            }

            # Validate no PII slipped through
            snapshot_data = validate_no_pii(snapshot_data)

            # Calculate content hash for change detection
            content_hash = self._calculate_hash(snapshot_data)

            # Check if snapshot has changed from last one
            last_snapshot = db.execute(text("""
                SELECT content_hash FROM listing_transaction_snapshots
                WHERE transaction_id = :id
                ORDER BY created_at DESC
                LIMIT 1
            """), {"id": transaction_id}).fetchone()

            if last_snapshot and last_snapshot.content_hash == content_hash:
                # No change, return existing data without creating new snapshot
                return {
                    "data": snapshot_data,
                    "hash": content_hash,
                    "changed": False
                }

            # Store new snapshot
            db.execute(text("""
                INSERT INTO listing_transaction_snapshots (
                    transaction_id, snapshot_data, snapshot_type,
                    triggered_by, content_hash
                ) VALUES (
                    :id, :data::jsonb, :type, :triggered_by, :hash
                )
            """), {
                "id": transaction_id,
                "data": json.dumps(snapshot_data),
                "type": snapshot_type,
                "triggered_by": triggered_by,
                "hash": content_hash
            })
            db.commit()

            return {
                "data": snapshot_data,
                "hash": content_hash,
                "changed": True
            }

        except SQLAlchemyError as e:
            logger.error(f"Error creating snapshot: {e}")
            db.rollback()
            return None

    def _get_recent_activity(
        self,
        db: Session,
        transaction_id: int,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get recent activity for a transaction (last N days)"""
        activity = []

        try:
            # Recent milestone changes
            milestones = db.execute(text("""
                SELECT milestone_name, status, updated_at
                FROM listing_milestones
                WHERE transaction_id = :id
                  AND updated_at >= CURRENT_TIMESTAMP - INTERVAL ':days days'
                ORDER BY updated_at DESC
                LIMIT 10
            """.replace(":days", str(days))), {"id": transaction_id})

            for m in milestones.fetchall():
                activity.append({
                    "type": "milestone",
                    "description": f"{m.milestone_name}: {m.status}",
                    "timestamp": m.updated_at.isoformat() if m.updated_at else None
                })

            # Recent messages (count only, not content)
            msg_count = db.execute(text("""
                SELECT COUNT(*) as cnt
                FROM listing_portal_messages
                WHERE transaction_id = :id
                  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            """), {"id": transaction_id}).fetchone()

            if msg_count and msg_count.cnt > 0:
                activity.append({
                    "type": "messages",
                    "description": f"{msg_count.cnt} new message(s) this week",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

        except SQLAlchemyError as e:
            logger.error(f"Error getting recent activity: {e}")

        return activity

    def _calculate_hash(self, data: Dict[str, Any]) -> str:
        """Calculate SHA256 hash of snapshot data for change detection"""
        # Remove timestamp for hash calculation (it always changes)
        data_copy = data.copy()
        data_copy.pop("snapshot_at", None)

        json_str = json.dumps(data_copy, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def get_parties_for_weekly_update(
        self,
        db: Session,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all parties that should receive weekly updates.
        Returns parties grouped by email (one email = one update with all their transactions)
        """
        try:
            params = {}
            org_filter = ""
            if organization_id:
                org_filter = "AND t.organization_id = :org_id"
                params["org_id"] = organization_id

            sql = """
                SELECT DISTINCT
                    p.id as party_id,
                    p.email,
                    p.first_name,
                    p.last_name,
                    p.transaction_id,
                    t.organization_id
                FROM transaction_parties p
                JOIN listing_transactions t ON t.id = p.transaction_id
                WHERE p.is_active = true
                  AND p.notify_weekly_updates = true
                  AND p.unsubscribed_at IS NULL
                  AND t.is_active = true
                  AND t.current_status NOT IN ('closed', 'cancelled')
            """
            if org_filter:
                sql += "                  " + org_filter + "\n"
            sql += """                ORDER BY p.email, p.transaction_id
            """
            result = db.execute(text(sql), params)

            # Group by email
            parties_by_email = {}
            for row in result.fetchall():
                email = row.email.lower()
                if email not in parties_by_email:
                    parties_by_email[email] = {
                        "party_id": row.party_id,
                        "email": email,
                        "first_name": row.first_name,
                        "last_name": row.last_name,
                        "transaction_ids": []
                    }
                parties_by_email[email]["transaction_ids"].append(row.transaction_id)

            return list(parties_by_email.values())

        except Exception as e:
            logger.error(f"Error getting parties for weekly update: {e}")
            return []

    def generate_weekly_update_data(
        self,
        db: Session,
        party_email: str,
        transaction_ids: List[int]
    ) -> Optional[Dict[str, Any]]:
        """Generate data for a weekly update email"""
        try:
            # Get party info
            party = db.execute(text("""
                SELECT id, email, first_name, last_name
                FROM transaction_parties
                WHERE email = :email AND is_active = true
                LIMIT 1
            """), {"email": party_email.lower()}).fetchone()

            if not party:
                return None

            # Generate snapshots for all transactions
            transactions = []
            for txn_id in transaction_ids:
                snapshot_result = self.create_snapshot(db, txn_id, "weekly_update")
                if snapshot_result:
                    transactions.append(snapshot_result["data"])

            if not transactions:
                return None

            # Create unsubscribe token
            from services.listing_portal_service import listing_portal_service
            unsubscribe_token = listing_portal_service.create_unsubscribe_token(
                db, party.id, "weekly_updates"
            )

            frontend_url = listing_portal_service.frontend_url

            return {
                "party_id": party.id,
                "party_name": f"{party.first_name} {party.last_name}",
                "party_email": party.email,
                "transaction_count": len(transactions),
                "transactions": transactions,
                "unsubscribe_token": unsubscribe_token,
                "unsubscribe_url": f"{frontend_url}/listing-portal/unsubscribe?token={unsubscribe_token}",
                "portal_url": frontend_url + "/listing-portal",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating weekly update data: {e}")
            return None

    def record_delivery(
        self,
        db: Session,
        party_id: int,
        transaction_id: int,
        delivery_type: str,
        snapshot_data: Dict[str, Any],
        channel: str = "email",
        external_message_id: Optional[str] = None
    ) -> Optional[int]:
        """Record a delivery attempt"""
        try:
            result = db.execute(text("""
                INSERT INTO listing_update_deliveries (
                    party_id, transaction_id, delivery_type, channel,
                    snapshot_data, status, external_message_id
                ) VALUES (
                    :party_id, :txn_id, :type, :channel,
                    :snapshot::jsonb, 'pending', :msg_id
                )
                RETURNING id
            """), {
                "party_id": party_id,
                "txn_id": transaction_id,
                "type": delivery_type,
                "channel": channel,
                "snapshot": json.dumps(snapshot_data),
                "msg_id": external_message_id
            })
            row = result.fetchone()
            db.commit()

            return row.id if row else None

        except SQLAlchemyError as e:
            logger.error(f"Error recording delivery: {e}")
            db.rollback()
            return None

    def update_delivery_status(
        self,
        db: Session,
        delivery_id: int,
        status: str,
        error_message: Optional[str] = None
    ):
        """Update delivery status"""
        try:
            timestamp_field = ""
            if status == "sent":
                timestamp_field = ", sent_at = CURRENT_TIMESTAMP"
            elif status == "delivered":
                timestamp_field = ", delivered_at = CURRENT_TIMESTAMP"
            elif status == "opened":
                timestamp_field = ", opened_at = CURRENT_TIMESTAMP"
            elif status == "clicked":
                timestamp_field = ", clicked_at = CURRENT_TIMESTAMP"
            elif status == "bounced":
                timestamp_field = ", bounced_at = CURRENT_TIMESTAMP"
            elif status == "failed":
                timestamp_field = ", retry_count = retry_count + 1"

            sql = "UPDATE listing_update_deliveries SET status = :status, error_message = :error" + timestamp_field + " WHERE id = :id"
            db.execute(text(sql), {
                "id": delivery_id,
                "status": status,
                "error": error_message
            })
            db.commit()

        except SQLAlchemyError as e:
            logger.error(f"Error updating delivery status: {e}")
            db.rollback()


# Global instance
listing_snapshot_service = ListingSnapshotService()
