"""
Listing Agent Portal Service
Handles magic link authentication, transaction management, and messaging.
"""

import os
import secrets
import hashlib
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from sqlalchemy.exc import SQLAlchemyError
from models.listing_portal import (
    TransactionSnapshot, validate_no_pii, FORBIDDEN_PII_KEYS
)

logger = logging.getLogger(__name__)


class ListingPortalService:
    """Service for listing agent portal operations"""

    def __init__(self):
        self.frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
        self.magic_link_expiry_hours = int(os.getenv("MAGIC_LINK_EXPIRY_HOURS", "72"))
        self.session_expiry_hours = int(os.getenv("SESSION_EXPIRY_HOURS", "24"))

    # =========================================================================
    # TRANSACTION MANAGEMENT
    # =========================================================================

    def create_transaction(
        self,
        db: Session,
        organization_id: int,
        loan_id: int,
        property_address: str,
        property_city: Optional[str] = None,
        property_state: Optional[str] = None,
        property_zip: Optional[str] = None,
        purchase_price: Optional[float] = None,
        contract_date: Optional[str] = None,
        target_close_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new listing transaction"""
        try:
            result = db.execute(text("""
                INSERT INTO listing_transactions (
                    organization_id, loan_id, property_address,
                    property_city, property_state, property_zip,
                    purchase_price, contract_date, target_close_date
                ) VALUES (
                    :org_id, :loan_id, :address,
                    :city, :state, :zip,
                    :price, :contract_date, :close_date
                )
                RETURNING id, created_at
            """), {
                "org_id": organization_id,
                "loan_id": loan_id,
                "address": property_address,
                "city": property_city,
                "state": property_state,
                "zip": property_zip,
                "price": purchase_price,
                "contract_date": contract_date,
                "close_date": target_close_date
            })
            row = result.fetchone()
            db.commit()

            if row:
                transaction_id = row[0]
                # Create default milestones
                self._create_default_milestones(db, transaction_id, organization_id)
                return self.get_transaction(db, transaction_id)

            return None

        except SQLAlchemyError as e:
            logger.error(f"Error creating transaction: {e}")
            db.rollback()
            return None

    def _create_default_milestones(
        self,
        db: Session,
        transaction_id: int,
        organization_id: int
    ):
        """Create default milestones for a transaction"""
        try:
            # Get milestone templates
            templates = db.execute(text("""
                SELECT milestone_key, milestone_name, description, display_order
                FROM listing_milestone_templates
                WHERE (organization_id = :org_id OR organization_id IS NULL)
                  AND is_default = true
                ORDER BY COALESCE(organization_id, 0) DESC, display_order
            """), {"org_id": organization_id}).fetchall()

            # Dedupe by milestone_key (org-specific overrides system defaults)
            seen_keys = set()
            for template in templates:
                if template.milestone_key in seen_keys:
                    continue
                seen_keys.add(template.milestone_key)

                db.execute(text("""
                    INSERT INTO listing_milestones (
                        transaction_id, milestone_key, milestone_name,
                        description, display_order
                    ) VALUES (
                        :txn_id, :key, :name, :desc, :order
                    )
                    ON CONFLICT (transaction_id, milestone_key) DO NOTHING
                """), {
                    "txn_id": transaction_id,
                    "key": template.milestone_key,
                    "name": template.milestone_name,
                    "desc": template.description,
                    "order": template.display_order
                })

            db.commit()

        except SQLAlchemyError as e:
            logger.error(f"Error creating default milestones: {e}")
            db.rollback()

    def get_transaction(
        self,
        db: Session,
        transaction_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get transaction details"""
        try:
            result = db.execute(text("""
                SELECT
                    t.id, t.organization_id, t.loan_id,
                    t.property_address, t.property_city, t.property_state, t.property_zip,
                    t.purchase_price, t.contract_date, t.target_close_date, t.actual_close_date,
                    t.current_status, t.is_active, t.created_at, t.updated_at
                FROM listing_transactions t
                WHERE t.id = :id
            """), {"id": transaction_id})
            row = result.fetchone()

            if not row:
                return None

            return {
                "id": row.id,
                "organization_id": row.organization_id,
                "loan_id": row.loan_id,
                "property_address": row.property_address,
                "property_city": row.property_city,
                "property_state": row.property_state,
                "property_zip": row.property_zip,
                "purchase_price": float(row.purchase_price) if row.purchase_price else None,
                "contract_date": row.contract_date,
                "target_close_date": row.target_close_date,
                "actual_close_date": row.actual_close_date,
                "current_status": row.current_status,
                "is_active": row.is_active,
                "created_at": row.created_at,
                "updated_at": row.updated_at
            }

        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            return None

    def get_transaction_by_loan(
        self,
        db: Session,
        loan_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get transaction by loan ID"""
        try:
            result = db.execute(text("""
                SELECT id FROM listing_transactions WHERE loan_id = :loan_id
            """), {"loan_id": loan_id})
            row = result.fetchone()

            if row:
                return self.get_transaction(db, row.id)
            return None

        except SQLAlchemyError as e:
            logger.error(f"Error getting transaction by loan: {e}")
            return None

    # =========================================================================
    # PARTY MANAGEMENT
    # =========================================================================

    def add_party(
        self,
        db: Session,
        transaction_id: int,
        role: str,
        email: str,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        company_name: Optional[str] = None,
        license_number: Optional[str] = None,
        notify_weekly: bool = True,
        notify_milestones: bool = True,
        notify_messages: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Add a party to a transaction"""
        try:
            result = db.execute(text("""
                INSERT INTO transaction_parties (
                    transaction_id, role, email, first_name, last_name,
                    phone, company_name, license_number,
                    notify_weekly_updates, notify_milestone_changes, notify_messages
                ) VALUES (
                    :txn_id, :role, :email, :first_name, :last_name,
                    :phone, :company, :license,
                    :notify_weekly, :notify_milestones, :notify_messages
                )
                ON CONFLICT (transaction_id, email)
                DO UPDATE SET
                    role = EXCLUDED.role,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    phone = COALESCE(EXCLUDED.phone, transaction_parties.phone),
                    company_name = COALESCE(EXCLUDED.company_name, transaction_parties.company_name),
                    is_active = true,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, created_at
            """), {
                "txn_id": transaction_id,
                "role": role,
                "email": email.lower(),
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "company": company_name,
                "license": license_number,
                "notify_weekly": notify_weekly,
                "notify_milestones": notify_milestones,
                "notify_messages": notify_messages
            })
            row = result.fetchone()
            db.commit()

            if row:
                return self.get_party(db, row.id)

            return None

        except SQLAlchemyError as e:
            logger.error(f"Error adding party: {e}")
            db.rollback()
            return None

    def get_party(self, db: Session, party_id: int) -> Optional[Dict[str, Any]]:
        """Get party details"""
        try:
            result = db.execute(text("""
                SELECT
                    p.id, p.transaction_id, p.role, p.email,
                    p.first_name, p.last_name, p.phone, p.company_name,
                    p.license_number, p.notify_weekly_updates,
                    p.notify_milestone_changes, p.notify_messages,
                    p.unsubscribed_at, p.is_active, p.created_at
                FROM transaction_parties p
                WHERE p.id = :id
            """), {"id": party_id})
            row = result.fetchone()

            if not row:
                return None

            return {
                "id": row.id,
                "transaction_id": row.transaction_id,
                "role": row.role,
                "email": row.email,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "phone": row.phone,
                "company_name": row.company_name,
                "license_number": row.license_number,
                "notify_weekly_updates": row.notify_weekly_updates,
                "notify_milestone_changes": row.notify_milestone_changes,
                "notify_messages": row.notify_messages,
                "unsubscribed_at": row.unsubscribed_at,
                "is_active": row.is_active,
                "created_at": row.created_at
            }

        except Exception as e:
            logger.error(f"Error getting party: {e}")
            return None

    def get_transaction_parties(
        self,
        db: Session,
        transaction_id: int
    ) -> List[Dict[str, Any]]:
        """Get all parties for a transaction"""
        try:
            result = db.execute(text("""
                SELECT id FROM transaction_parties
                WHERE transaction_id = :txn_id AND is_active = true
                ORDER BY created_at
            """), {"txn_id": transaction_id})

            return [self.get_party(db, row.id) for row in result.fetchall()]

        except SQLAlchemyError as e:
            logger.error(f"Error getting parties: {e}")
            return []

    # =========================================================================
    # MAGIC LINK AUTHENTICATION
    # =========================================================================

    def generate_magic_link_token(self) -> str:
        """Generate a secure magic link token"""
        return secrets.token_urlsafe(32)

    def create_portal_invite(
        self,
        db: Session,
        party_id: int,
        sent_via: str = "email"
    ) -> Optional[Dict[str, Any]]:
        """Create a portal invite with magic link"""
        try:
            token = self.generate_magic_link_token()
            expires_at = datetime.now(timezone.utc) + timedelta(hours=self.magic_link_expiry_hours)

            result = db.execute(text("""
                INSERT INTO listing_portal_invites (
                    party_id, token, expires_at, sent_via
                ) VALUES (
                    :party_id, :token, :expires_at, :sent_via
                )
                RETURNING id, created_at
            """), {
                "party_id": party_id,
                "token": token,
                "expires_at": expires_at,
                "sent_via": sent_via
            })
            row = result.fetchone()
            db.commit()

            if row:
                party = self.get_party(db, party_id)
                portal_url = f"{self.frontend_url}/listing-portal?token={token}"

                return {
                    "id": row.id,
                    "party_id": party_id,
                    "party_name": f"{party['first_name']} {party['last_name']}" if party else "",
                    "party_email": party["email"] if party else "",
                    "token": token,
                    "portal_url": portal_url,
                    "expires_at": expires_at,
                    "sent_via": sent_via,
                    "created_at": row.created_at
                }

            return None

        except Exception as e:
            logger.error(f"Error creating portal invite: {e}")
            db.rollback()
            return None

    def validate_magic_link(
        self,
        db: Session,
        token: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate a magic link token and create a session.
        Returns (session_data, error_message)
        """
        try:
            # Find the invite
            result = db.execute(text("""
                SELECT
                    i.id, i.party_id, i.expires_at, i.used_at, i.revoked_at,
                    i.clicks, i.session_token, i.session_expires_at,
                    p.transaction_id, p.email, p.first_name, p.last_name,
                    p.is_active as party_active
                FROM listing_portal_invites i
                JOIN transaction_parties p ON p.id = i.party_id
                WHERE i.token = :token
            """), {"token": token})
            row = result.fetchone()

            if not row:
                return None, "Invalid token"

            if row.revoked_at:
                return None, "Token has been revoked"

            if row.expires_at < datetime.now(timezone.utc):
                return None, "Token has expired"

            if not row.party_active:
                return None, "Party is no longer active"

            # Update click count
            db.execute(text("""
                UPDATE listing_portal_invites
                SET clicks = clicks + 1, last_clicked_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": row.id})

            # Create or refresh session
            session_token = secrets.token_urlsafe(32)
            session_expires = datetime.now(timezone.utc) + timedelta(hours=self.session_expiry_hours)

            db.execute(text("""
                UPDATE listing_portal_invites
                SET session_token = :session_token,
                    session_expires_at = :session_expires,
                    used_at = COALESCE(used_at, CURRENT_TIMESTAMP)
                WHERE id = :id
            """), {
                "id": row.id,
                "session_token": session_token,
                "session_expires": session_expires
            })
            db.commit()

            party = self.get_party(db, row.party_id)
            transaction = self.get_transaction(db, row.transaction_id)

            return {
                "session_token": session_token,
                "expires_at": session_expires,
                "party": party,
                "transaction": transaction
            }, None

        except SQLAlchemyError as e:
            logger.error(f"Error validating magic link: {e}")
            db.rollback()
            return None, "Internal error"

    def validate_session(
        self,
        db: Session,
        session_token: str
    ) -> Optional[Dict[str, Any]]:
        """Validate a session token and return party/transaction info"""
        try:
            result = db.execute(text("""
                SELECT
                    i.party_id, i.session_expires_at,
                    p.transaction_id, p.is_active
                FROM listing_portal_invites i
                JOIN transaction_parties p ON p.id = i.party_id
                WHERE i.session_token = :token
                  AND i.revoked_at IS NULL
            """), {"token": session_token})
            row = result.fetchone()

            if not row:
                return None

            if row.session_expires_at < datetime.now(timezone.utc):
                return None

            if not row.is_active:
                return None

            party = self.get_party(db, row.party_id)
            transaction = self.get_transaction(db, row.transaction_id)

            return {
                "party": party,
                "transaction": transaction,
                "session_expires_at": row.session_expires_at
            }

        except Exception as e:
            logger.error(f"Error validating session: {e}")
            return None

    # =========================================================================
    # MILESTONE MANAGEMENT
    # =========================================================================

    def get_milestones(
        self,
        db: Session,
        transaction_id: int
    ) -> List[Dict[str, Any]]:
        """Get all milestones for a transaction"""
        try:
            result = db.execute(text("""
                SELECT
                    id, milestone_key, milestone_name, description,
                    status, completed_at, target_date, display_order
                FROM listing_milestones
                WHERE transaction_id = :txn_id
                ORDER BY display_order
            """), {"txn_id": transaction_id})

            return [
                {
                    "id": row.id,
                    "milestone_key": row.milestone_key,
                    "milestone_name": row.milestone_name,
                    "description": row.description,
                    "status": row.status,
                    "completed_at": row.completed_at,
                    "target_date": row.target_date,
                    "display_order": row.display_order
                }
                for row in result.fetchall()
            ]

        except Exception as e:
            logger.error(f"Error getting milestones: {e}")
            return []

    def update_milestone(
        self,
        db: Session,
        milestone_id: int,
        status: str,
        completed_at: Optional[datetime] = None,
        target_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Update a milestone status"""
        try:
            # Auto-set completed_at if status is completed
            if status == "completed" and not completed_at:
                completed_at = datetime.now(timezone.utc)

            db.execute(text("""
                UPDATE listing_milestones
                SET status = :status,
                    completed_at = :completed_at,
                    target_date = :target_date,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {
                "id": milestone_id,
                "status": status,
                "completed_at": completed_at,
                "target_date": target_date
            })
            db.commit()

            # Get updated milestone
            result = db.execute(text("""
                SELECT
                    id, transaction_id, milestone_key, milestone_name,
                    description, status, completed_at, target_date, display_order
                FROM listing_milestones
                WHERE id = :id
            """), {"id": milestone_id})
            row = result.fetchone()

            if row:
                return {
                    "id": row.id,
                    "transaction_id": row.transaction_id,
                    "milestone_key": row.milestone_key,
                    "milestone_name": row.milestone_name,
                    "description": row.description,
                    "status": row.status,
                    "completed_at": row.completed_at,
                    "target_date": row.target_date,
                    "display_order": row.display_order
                }

            return None

        except Exception as e:
            logger.error(f"Error updating milestone: {e}")
            db.rollback()
            return None

    # =========================================================================
    # MESSAGING
    # =========================================================================

    def send_message(
        self,
        db: Session,
        transaction_id: int,
        content: str,
        sender_party_id: Optional[int] = None,
        sender_user_id: Optional[int] = None,
        attachments: Optional[List[Dict]] = None
    ) -> Optional[Dict[str, Any]]:
        """Send a message in a transaction thread"""
        try:
            import json
            attachments_json = json.dumps(attachments or [])

            result = db.execute(text("""
                INSERT INTO listing_portal_messages (
                    transaction_id, sender_party_id, sender_user_id,
                    content, attachments
                ) VALUES (
                    :txn_id, :party_id, :user_id, :content, :attachments::jsonb
                )
                RETURNING id, created_at
            """), {
                "txn_id": transaction_id,
                "party_id": sender_party_id,
                "user_id": sender_user_id,
                "content": content,
                "attachments": attachments_json
            })
            row = result.fetchone()
            db.commit()

            if row:
                return self.get_message(db, row.id)

            return None

        except SQLAlchemyError as e:
            logger.error(f"Error sending message: {e}")
            db.rollback()
            return None

    def get_message(self, db: Session, message_id: int) -> Optional[Dict[str, Any]]:
        """Get a single message"""
        try:
            result = db.execute(text("""
                SELECT
                    m.id, m.transaction_id, m.sender_party_id, m.sender_user_id,
                    m.content, m.attachments, m.read_at, m.created_at,
                    p.first_name as party_first, p.last_name as party_last,
                    u.first_name as user_first, u.last_name as user_last
                FROM listing_portal_messages m
                LEFT JOIN transaction_parties p ON p.id = m.sender_party_id
                LEFT JOIN users u ON u.id = m.sender_user_id
                WHERE m.id = :id
            """), {"id": message_id})
            row = result.fetchone()

            if not row:
                return None

            if row.sender_party_id:
                sender_name = f"{row.party_first} {row.party_last}"
                sender_type = "party"
            else:
                sender_name = f"{row.user_first or ''} {row.user_last or ''}".strip() or "Loan Officer"
                sender_type = "lo"

            return {
                "id": row.id,
                "transaction_id": row.transaction_id,
                "sender_party_id": row.sender_party_id,
                "sender_user_id": row.sender_user_id,
                "sender_name": sender_name,
                "sender_type": sender_type,
                "content": row.content,
                "attachments": row.attachments or [],
                "read_at": row.read_at,
                "created_at": row.created_at
            }

        except Exception as e:
            logger.error(f"Error getting message: {e}")
            return None

    def get_messages(
        self,
        db: Session,
        transaction_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get messages for a transaction"""
        try:
            result = db.execute(text("""
                SELECT id FROM listing_portal_messages
                WHERE transaction_id = :txn_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """), {"txn_id": transaction_id, "limit": limit, "offset": offset})

            return [self.get_message(db, row.id) for row in result.fetchall()]

        except SQLAlchemyError as e:
            logger.error(f"Error getting messages: {e}")
            return []

    def mark_messages_read(
        self,
        db: Session,
        transaction_id: int,
        reader_party_id: Optional[int] = None,
        reader_user_id: Optional[int] = None
    ) -> int:
        """Mark all unread messages as read"""
        try:
            # Only mark messages from the "other side" as read
            if reader_party_id:
                # Party is reading, mark LO messages as read
                filter_clause = "sender_user_id IS NOT NULL"
                reader_clause = "read_by_party_id = :reader_id"
                reader_id = reader_party_id
            else:
                # LO is reading, mark party messages as read
                filter_clause = "sender_party_id IS NOT NULL"
                reader_clause = "read_by_user_id = :reader_id"
                reader_id = reader_user_id

            result = db.execute(text(f"""
                UPDATE listing_portal_messages
                SET read_at = CURRENT_TIMESTAMP,
                    {reader_clause}
                WHERE transaction_id = :txn_id
                  AND {filter_clause}
                  AND read_at IS NULL
            """), {"txn_id": transaction_id, "reader_id": reader_id})
            db.commit()

            return result.rowcount

        except SQLAlchemyError as e:
            logger.error(f"Error marking messages read: {e}")
            db.rollback()
            return 0

    def get_unread_count(
        self,
        db: Session,
        transaction_id: int,
        for_party: bool = True
    ) -> int:
        """Get count of unread messages"""
        try:
            # If for_party, count unread LO messages
            # If for LO, count unread party messages
            filter_clause = "sender_user_id IS NOT NULL" if for_party else "sender_party_id IS NOT NULL"

            result = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM listing_portal_messages
                WHERE transaction_id = :txn_id
                  AND {filter_clause}
                  AND read_at IS NULL
            """), {"txn_id": transaction_id})
            row = result.fetchone()

            return row.cnt if row else 0

        except SQLAlchemyError as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    # =========================================================================
    # UNSUBSCRIBE
    # =========================================================================

    def create_unsubscribe_token(
        self,
        db: Session,
        party_id: int,
        unsubscribe_type: str = "all"
    ) -> str:
        """Create an unsubscribe token for a party"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(days=365)

            db.execute(text("""
                INSERT INTO listing_unsubscribe_tokens (
                    party_id, token, unsubscribe_type, expires_at
                ) VALUES (
                    :party_id, :token, :type, :expires_at
                )
            """), {
                "party_id": party_id,
                "token": token,
                "type": unsubscribe_type,
                "expires_at": expires_at
            })
            db.commit()

            return token

        except SQLAlchemyError as e:
            logger.error(f"Error creating unsubscribe token: {e}")
            db.rollback()
            return ""

    def process_unsubscribe(
        self,
        db: Session,
        token: str
    ) -> Tuple[bool, str]:
        """Process an unsubscribe request"""
        try:
            result = db.execute(text("""
                SELECT id, party_id, unsubscribe_type, used_at, expires_at
                FROM listing_unsubscribe_tokens
                WHERE token = :token
            """), {"token": token})
            row = result.fetchone()

            if not row:
                return False, "Invalid unsubscribe link"

            if row.used_at:
                return False, "This unsubscribe link has already been used"

            if row.expires_at and row.expires_at < datetime.now(timezone.utc):
                return False, "This unsubscribe link has expired"

            # Mark token as used
            db.execute(text("""
                UPDATE listing_unsubscribe_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": row.id})

            # Update party preferences
            if row.unsubscribe_type == "all":
                db.execute(text("""
                    UPDATE transaction_parties
                    SET notify_weekly_updates = false,
                        notify_milestone_changes = false,
                        notify_messages = false,
                        unsubscribed_at = CURRENT_TIMESTAMP
                    WHERE id = :party_id
                """), {"party_id": row.party_id})
            elif row.unsubscribe_type == "weekly_updates":
                db.execute(text("""
                    UPDATE transaction_parties
                    SET notify_weekly_updates = false
                    WHERE id = :party_id
                """), {"party_id": row.party_id})
            elif row.unsubscribe_type == "milestones":
                db.execute(text("""
                    UPDATE transaction_parties
                    SET notify_milestone_changes = false
                    WHERE id = :party_id
                """), {"party_id": row.party_id})
            elif row.unsubscribe_type == "messages":
                db.execute(text("""
                    UPDATE transaction_parties
                    SET notify_messages = false
                    WHERE id = :party_id
                """), {"party_id": row.party_id})

            db.commit()
            return True, "Successfully unsubscribed"

        except SQLAlchemyError as e:
            logger.error(f"Error processing unsubscribe: {e}")
            db.rollback()
            return False, "Error processing unsubscribe"


# Global instance
listing_portal_service = ListingPortalService()
