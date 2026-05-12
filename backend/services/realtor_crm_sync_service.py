"""
Realtor CRM Sync Service - Real-time CRM synchronization for the Realtor Portal.

Provides:
- WebSocket-based real-time updates to connected realtors
- CRM webhook handling for loan status changes
- Sync state tracking with versioning
- Conflict detection and resolution
- Rate limiting and connection management
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import asyncio
import logging
import json
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RealtorSyncMessage:
    """Typed message for realtor sync operations."""

    # Message types
    LOAN_STATUS_CHANGE = "LOAN_STATUS_CHANGE"
    LOAN_DATA_UPDATE = "LOAN_DATA_UPDATE"
    DOCUMENT_UPDATE = "DOCUMENT_UPDATE"
    MILESTONE_UPDATE = "MILESTONE_UPDATE"
    CONDITION_UPDATE = "CONDITION_UPDATE"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    LETTER_GENERATED = "LETTER_GENERATED"
    CONNECTION_ESTABLISHED = "CONNECTION_ESTABLISHED"
    SYNC_STATE = "SYNC_STATE"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"

    @staticmethod
    def create(
        msg_type: str,
        loan_id: Optional[int],
        data: Dict,
        version: Optional[int] = None
    ) -> Dict:
        """Create a standardized sync message."""
        return {
            "type": msg_type,
            "loan_id": loan_id,
            "data": data,
            "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


class RealtorConnectionManager:
    """
    Manages WebSocket connections for the Realtor Portal.

    Features:
    - Realtor-specific connections (one realtor can view multiple loans)
    - Loan-specific subscriptions
    - Token-based authentication
    - Rate limiting per connection
    """

    def __init__(self):
        # Realtor connections: realtor_id -> WebSocket
        self.realtor_connections: Dict[int, WebSocket] = {}

        # Loan subscriptions: loan_id -> set of realtor_ids
        self.loan_subscriptions: Dict[int, Set[int]] = {}

        # Realtor to loans mapping (reverse index)
        self.realtor_loans: Dict[int, Set[int]] = {}

        # Connection metadata
        self.connection_metadata: Dict[int, Dict] = {}

        # Rate limiting: realtor_id -> message count this minute
        self.rate_limits: Dict[int, int] = {}
        self.rate_limit_reset: Dict[int, datetime] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Max messages per minute per connection
        self.MAX_MESSAGES_PER_MINUTE = 100

    # =========================================================================
    # CONNECTION MANAGEMENT
    # =========================================================================

    async def connect(
        self,
        websocket: WebSocket,
        realtor_id: int,
        loan_ids: List[int],
        metadata: Optional[Dict] = None
    ):
        """Connect a realtor to their loan subscriptions.
        Note: caller must accept() the WebSocket before calling this method.
        """

        async with self._lock:
            # Store connection
            self.realtor_connections[realtor_id] = websocket

            # Initialize loan subscriptions
            self.realtor_loans[realtor_id] = set(loan_ids)

            for loan_id in loan_ids:
                if loan_id not in self.loan_subscriptions:
                    self.loan_subscriptions[loan_id] = set()
                self.loan_subscriptions[loan_id].add(realtor_id)

            # Store metadata
            self.connection_metadata[realtor_id] = {
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "loan_count": len(loan_ids),
                "ip_address": metadata.get("ip_address") if metadata else None,
                "user_agent": metadata.get("user_agent") if metadata else None,
            }

            # Initialize rate limiting
            self.rate_limits[realtor_id] = 0
            self.rate_limit_reset[realtor_id] = datetime.now(timezone.utc)

        logger.info(f"Realtor {realtor_id} connected, subscribed to {len(loan_ids)} loans")

        # Send connection confirmation
        await self._send_to_realtor(realtor_id, RealtorSyncMessage.create(
            RealtorSyncMessage.CONNECTION_ESTABLISHED,
            None,
            {
                "realtor_id": realtor_id,
                "subscribed_loans": loan_ids,
            }
        ))

    async def disconnect(self, realtor_id: int):
        """Disconnect a realtor and clean up subscriptions."""
        async with self._lock:
            # Get subscribed loans before cleanup
            loan_ids = self.realtor_loans.pop(realtor_id, set())

            # Remove from loan subscriptions
            for loan_id in loan_ids:
                if loan_id in self.loan_subscriptions:
                    self.loan_subscriptions[loan_id].discard(realtor_id)
                    # Clean up empty sets
                    if not self.loan_subscriptions[loan_id]:
                        del self.loan_subscriptions[loan_id]

            # Remove connection
            self.realtor_connections.pop(realtor_id, None)
            self.connection_metadata.pop(realtor_id, None)
            self.rate_limits.pop(realtor_id, None)
            self.rate_limit_reset.pop(realtor_id, None)

        logger.info(f"Realtor {realtor_id} disconnected")

    async def subscribe_to_loan(self, realtor_id: int, loan_id: int):
        """Add a loan subscription for a connected realtor."""
        async with self._lock:
            if realtor_id not in self.realtor_connections:
                return False

            # Add to subscriptions
            if loan_id not in self.loan_subscriptions:
                self.loan_subscriptions[loan_id] = set()
            self.loan_subscriptions[loan_id].add(realtor_id)

            if realtor_id not in self.realtor_loans:
                self.realtor_loans[realtor_id] = set()
            self.realtor_loans[realtor_id].add(loan_id)

        logger.debug(f"Realtor {realtor_id} subscribed to loan {loan_id}")
        return True

    async def unsubscribe_from_loan(self, realtor_id: int, loan_id: int):
        """Remove a loan subscription for a connected realtor."""
        async with self._lock:
            if loan_id in self.loan_subscriptions:
                self.loan_subscriptions[loan_id].discard(realtor_id)

            if realtor_id in self.realtor_loans:
                self.realtor_loans[realtor_id].discard(loan_id)

        logger.debug(f"Realtor {realtor_id} unsubscribed from loan {loan_id}")

    # =========================================================================
    # MESSAGE SENDING
    # =========================================================================

    async def _send_to_realtor(self, realtor_id: int, message: Dict) -> bool:
        """Send a message to a specific realtor."""
        websocket = self.realtor_connections.get(realtor_id)
        if not websocket:
            return False

        # Check rate limiting
        if not await self._check_rate_limit(realtor_id):
            logger.warning(f"Rate limit exceeded for realtor {realtor_id}")
            return False

        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to realtor {realtor_id}: {e}")
            await self.disconnect(realtor_id)
            return False

    async def _check_rate_limit(self, realtor_id: int) -> bool:
        """Check if realtor is within rate limits."""
        now = datetime.now(timezone.utc)

        # Reset counter if minute has passed
        if realtor_id in self.rate_limit_reset:
            if now - self.rate_limit_reset[realtor_id] > timedelta(minutes=1):
                self.rate_limits[realtor_id] = 0
                self.rate_limit_reset[realtor_id] = now

        # Check limit
        current = self.rate_limits.get(realtor_id, 0)
        if current >= self.MAX_MESSAGES_PER_MINUTE:
            return False

        # Increment counter
        self.rate_limits[realtor_id] = current + 1
        return True

    async def broadcast_to_loan(self, loan_id: int, message: Dict):
        """Broadcast a message to all realtors subscribed to a loan."""
        realtor_ids = self.loan_subscriptions.get(loan_id, set()).copy()

        if not realtor_ids:
            logger.debug(f"No subscribers for loan {loan_id}")
            return 0

        sent_count = 0
        for realtor_id in realtor_ids:
            if await self._send_to_realtor(realtor_id, message):
                sent_count += 1

        logger.debug(f"Broadcast to loan {loan_id}: {sent_count}/{len(realtor_ids)} recipients")
        return sent_count

    # =========================================================================
    # CRM EVENT HANDLERS
    # =========================================================================

    async def handle_loan_status_change(
        self,
        loan_id: int,
        old_status: str,
        new_status: str,
        changed_by: Optional[str] = None,
        version: int = 1
    ):
        """Handle a loan status change from CRM."""
        message = RealtorSyncMessage.create(
            RealtorSyncMessage.LOAN_STATUS_CHANGE,
            loan_id,
            {
                "previous_status": old_status,
                "new_status": new_status,
                "changed_by": changed_by,
            },
            version
        )
        await self.broadcast_to_loan(loan_id, message)

    async def handle_loan_data_update(
        self,
        loan_id: int,
        updated_fields: Dict[str, Any],
        version: int = 1
    ):
        """Handle loan data updates from CRM."""
        # Filter out sensitive fields that realtors shouldn't see
        safe_fields = self._filter_sensitive_fields(updated_fields)

        message = RealtorSyncMessage.create(
            RealtorSyncMessage.LOAN_DATA_UPDATE,
            loan_id,
            {
                "updated_fields": safe_fields,
            },
            version
        )
        await self.broadcast_to_loan(loan_id, message)

    async def handle_document_update(
        self,
        loan_id: int,
        document_id: int,
        document_type: str,
        status: str,
        is_visible_to_realtor: bool = True,
        version: int = 1
    ):
        """Handle document status updates from CRM."""
        if not is_visible_to_realtor:
            return

        message = RealtorSyncMessage.create(
            RealtorSyncMessage.DOCUMENT_UPDATE,
            loan_id,
            {
                "document_id": document_id,
                "document_type": document_type,
                "status": status,
            },
            version
        )
        await self.broadcast_to_loan(loan_id, message)

    async def handle_milestone_update(
        self,
        loan_id: int,
        milestone_name: str,
        is_completed: bool,
        completed_at: Optional[datetime] = None,
        version: int = 1
    ):
        """Handle milestone updates from CRM."""
        message = RealtorSyncMessage.create(
            RealtorSyncMessage.MILESTONE_UPDATE,
            loan_id,
            {
                "milestone_name": milestone_name,
                "is_completed": is_completed,
                "completed_at": completed_at.isoformat() if completed_at else None,
            },
            version
        )
        await self.broadcast_to_loan(loan_id, message)

    async def handle_condition_update(
        self,
        loan_id: int,
        condition_id: int,
        condition_name: str,
        status: str,
        version: int = 1
    ):
        """Handle condition updates from CRM (when visible to realtors)."""
        message = RealtorSyncMessage.create(
            RealtorSyncMessage.CONDITION_UPDATE,
            loan_id,
            {
                "condition_id": condition_id,
                "condition_name": condition_name,
                "status": status,
            },
            version
        )
        await self.broadcast_to_loan(loan_id, message)

    async def notify_letter_generated(
        self,
        loan_id: int,
        letter_id: int,
        letter_type: str,
        generated_by: str,
        version: int = 1
    ):
        """Notify realtors when a letter is generated."""
        message = RealtorSyncMessage.create(
            RealtorSyncMessage.LETTER_GENERATED,
            loan_id,
            {
                "letter_id": letter_id,
                "letter_type": letter_type,
                "generated_by": generated_by,
            },
            version
        )
        await self.broadcast_to_loan(loan_id, message)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _filter_sensitive_fields(self, fields: Dict) -> Dict:
        """Filter out fields that should not be visible to realtors."""
        sensitive_fields = {
            "ssn", "social_security_number", "date_of_birth", "dob",
            "bank_account", "routing_number", "credit_score",
            "income_details", "employment_details", "assets_details",
            "internal_notes", "underwriter_notes", "pricing_details"
        }

        return {
            k: v for k, v in fields.items()
            if k.lower() not in sensitive_fields
        }

    def get_connection_stats(self) -> Dict:
        """Get connection statistics."""
        return {
            "total_realtors": len(self.realtor_connections),
            "total_loan_subscriptions": sum(
                len(subs) for subs in self.loan_subscriptions.values()
            ),
            "unique_loans_watched": len(self.loan_subscriptions),
            "connections_by_loan_count": {
                realtor_id: len(loans)
                for realtor_id, loans in self.realtor_loans.items()
            }
        }

    async def send_heartbeat(self):
        """Send heartbeat to all connected realtors."""
        disconnected = []

        for realtor_id, websocket in list(self.realtor_connections.items()):
            try:
                await websocket.send_json({
                    "type": RealtorSyncMessage.HEARTBEAT,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            except Exception as e:
                logger.warning(f"Error sending heartbeat to realtor {realtor_id}: {e}")
                disconnected.append(realtor_id)

        for realtor_id in disconnected:
            await self.disconnect(realtor_id)

        return len(self.realtor_connections)


class CRMSyncStateManager:
    """
    Manages sync state for CRM entities.

    Tracks:
    - Last sync time per entity
    - Version numbers for conflict detection
    - Active subscriptions
    """

    def __init__(self, db: Session):
        self.db = db

    def get_sync_state(self, entity_type: str, entity_id: int) -> Optional[Dict]:
        """Get current sync state for an entity."""
        result = self.db.execute(text("""
            SELECT
                last_synced_at, last_sync_version, sync_hash,
                active_connections, has_conflicts, conflict_data
            FROM portal_crm_sync_state
            WHERE entity_type = :entity_type AND entity_id = :entity_id
        """), {"entity_type": entity_type, "entity_id": entity_id}).fetchone()

        if not result:
            return None

        return {
            "last_synced_at": result[0].isoformat() if result[0] else None,
            "version": result[1],
            "sync_hash": result[2],
            "active_connections": result[3],
            "has_conflicts": result[4],
            "conflict_data": result[5]
        }

    def update_sync_state(
        self,
        entity_type: str,
        entity_id: int,
        data_hash: Optional[str] = None,
        increment_version: bool = True
    ):
        """Update sync state after a sync operation."""
        self.db.execute(text("""
            INSERT INTO portal_crm_sync_state (
                entity_type, entity_id, last_synced_at, last_sync_version, sync_hash
            ) VALUES (
                :entity_type, :entity_id, CURRENT_TIMESTAMP, 1, :hash
            )
            ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                last_synced_at = CURRENT_TIMESTAMP,
                last_sync_version = CASE
                    WHEN :increment THEN portal_crm_sync_state.last_sync_version + 1
                    ELSE portal_crm_sync_state.last_sync_version
                END,
                sync_hash = COALESCE(:hash, portal_crm_sync_state.sync_hash),
                updated_at = CURRENT_TIMESTAMP
        """), {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "hash": data_hash,
            "increment": increment_version
        })
        self.db.commit()

    def increment_connections(self, entity_type: str, entity_id: int):
        """Increment active connection count."""
        self.db.execute(text("""
            INSERT INTO portal_crm_sync_state (entity_type, entity_id, active_connections)
            VALUES (:entity_type, :entity_id, 1)
            ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                active_connections = portal_crm_sync_state.active_connections + 1,
                last_connection_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        """), {"entity_type": entity_type, "entity_id": entity_id})
        self.db.commit()

    def decrement_connections(self, entity_type: str, entity_id: int):
        """Decrement active connection count."""
        self.db.execute(text("""
            UPDATE portal_crm_sync_state
            SET active_connections = GREATEST(0, active_connections - 1),
                updated_at = CURRENT_TIMESTAMP
            WHERE entity_type = :entity_type AND entity_id = :entity_id
        """), {"entity_type": entity_type, "entity_id": entity_id})
        self.db.commit()

    def detect_conflict(
        self,
        entity_type: str,
        entity_id: int,
        expected_version: int,
        new_data_hash: str
    ) -> bool:
        """
        Detect if there's a sync conflict.

        Returns True if conflict detected.
        """
        state = self.get_sync_state(entity_type, entity_id)
        if not state:
            return False

        # Version mismatch indicates concurrent modification
        if state["version"] != expected_version:
            return True

        # Hash mismatch indicates data changed
        if state["sync_hash"] and state["sync_hash"] != new_data_hash:
            return True

        return False

    def record_conflict(
        self,
        entity_type: str,
        entity_id: int,
        conflict_data: Dict
    ):
        """Record a sync conflict for later resolution."""
        self.db.execute(text("""
            UPDATE portal_crm_sync_state
            SET has_conflicts = TRUE,
                conflict_data = :conflict_data,
                updated_at = CURRENT_TIMESTAMP
            WHERE entity_type = :entity_type AND entity_id = :entity_id
        """), {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "conflict_data": json.dumps(conflict_data)
        })
        self.db.commit()

    def resolve_conflict(self, entity_type: str, entity_id: int):
        """Mark a conflict as resolved."""
        self.db.execute(text("""
            UPDATE portal_crm_sync_state
            SET has_conflicts = FALSE,
                conflict_data = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE entity_type = :entity_type AND entity_id = :entity_id
        """), {"entity_type": entity_type, "entity_id": entity_id})
        self.db.commit()

    @staticmethod
    def compute_hash(data: Dict) -> str:
        """Compute a hash of data for change detection."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]


class CRMWebhookProcessor:
    """
    Processes incoming CRM webhooks and triggers sync updates.
    """

    def __init__(
        self,
        connection_manager: RealtorConnectionManager,
        db: Session
    ):
        self.connection_manager = connection_manager
        self.sync_state = CRMSyncStateManager(db)
        self.db = db

    async def process_webhook(self, webhook_type: str, payload: Dict) -> Dict:
        """Process a CRM webhook and broadcast updates."""
        handlers = {
            "loan.status_changed": self._handle_status_change,
            "loan.updated": self._handle_loan_update,
            "loan.document_added": self._handle_document_add,
            "loan.document_status_changed": self._handle_document_status,
            "loan.milestone_completed": self._handle_milestone,
            "loan.condition_updated": self._handle_condition,
        }

        handler = handlers.get(webhook_type)
        if not handler:
            logger.warning(f"Unknown webhook type: {webhook_type}")
            return {"success": False, "error": "Unknown webhook type"}

        try:
            result = await handler(payload)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Error processing webhook {webhook_type}: {e}")
            return {"success": False, "error": "Internal server error"}

    async def _handle_status_change(self, payload: Dict) -> Dict:
        """Handle loan status change webhook."""
        loan_id = payload.get("loan_id")
        old_status = payload.get("old_status")
        new_status = payload.get("new_status")
        changed_by = payload.get("changed_by")

        # Update sync state
        self.sync_state.update_sync_state("loan", loan_id)
        state = self.sync_state.get_sync_state("loan", loan_id)
        version = state["version"] if state else 1

        # Broadcast to connected realtors
        await self.connection_manager.handle_loan_status_change(
            loan_id, old_status, new_status, changed_by, version
        )

        return {"loan_id": loan_id, "new_status": new_status}

    async def _handle_loan_update(self, payload: Dict) -> Dict:
        """Handle loan data update webhook."""
        loan_id = payload.get("loan_id")
        updated_fields = payload.get("updated_fields", {})

        # Compute new hash
        new_hash = CRMSyncStateManager.compute_hash(updated_fields)

        # Update sync state
        self.sync_state.update_sync_state("loan", loan_id, new_hash)
        state = self.sync_state.get_sync_state("loan", loan_id)
        version = state["version"] if state else 1

        # Broadcast to connected realtors
        await self.connection_manager.handle_loan_data_update(
            loan_id, updated_fields, version
        )

        return {"loan_id": loan_id, "fields_updated": len(updated_fields)}

    async def _handle_document_add(self, payload: Dict) -> Dict:
        """Handle document added webhook."""
        loan_id = payload.get("loan_id")
        document_id = payload.get("document_id")
        document_type = payload.get("document_type")

        # Check if document type is visible to realtors
        visible = self._is_document_visible(document_type)

        await self.connection_manager.handle_document_update(
            loan_id, document_id, document_type, "added", visible
        )

        return {"loan_id": loan_id, "document_id": document_id, "visible": visible}

    async def _handle_document_status(self, payload: Dict) -> Dict:
        """Handle document status change webhook."""
        loan_id = payload.get("loan_id")
        document_id = payload.get("document_id")
        document_type = payload.get("document_type")
        new_status = payload.get("new_status")

        visible = self._is_document_visible(document_type)

        await self.connection_manager.handle_document_update(
            loan_id, document_id, document_type, new_status, visible
        )

        return {"loan_id": loan_id, "document_id": document_id, "status": new_status}

    async def _handle_milestone(self, payload: Dict) -> Dict:
        """Handle milestone completed webhook."""
        loan_id = payload.get("loan_id")
        milestone_name = payload.get("milestone_name")
        completed_at = payload.get("completed_at")

        if completed_at and isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))

        await self.connection_manager.handle_milestone_update(
            loan_id, milestone_name, True, completed_at
        )

        return {"loan_id": loan_id, "milestone": milestone_name}

    async def _handle_condition(self, payload: Dict) -> Dict:
        """Handle condition update webhook."""
        loan_id = payload.get("loan_id")
        condition_id = payload.get("condition_id")
        condition_name = payload.get("condition_name")
        status = payload.get("status")

        await self.connection_manager.handle_condition_update(
            loan_id, condition_id, condition_name, status
        )

        return {"loan_id": loan_id, "condition_id": condition_id, "status": status}

    def _is_document_visible(self, document_type: str) -> bool:
        """Check if a document type should be visible to realtors."""
        # Documents that realtors typically need to see
        visible_types = {
            "pre_approval_letter", "prequal_letter", "commitment_letter",
            "purchase_contract", "appraisal", "title_report",
            "closing_disclosure", "loan_estimate"
        }

        # Internal documents realtors should NOT see
        hidden_types = {
            "credit_report", "bank_statements", "tax_returns",
            "w2", "pay_stubs", "underwriter_notes"
        }

        doc_lower = document_type.lower()

        if doc_lower in hidden_types:
            return False

        if doc_lower in visible_types:
            return True

        # Default to not visible for unlisted types
        return False


# Global connection manager instance
realtor_sync_manager = RealtorConnectionManager()


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def realtor_sync_heartbeat_task():
    """Background task to send heartbeats to connected realtors."""
    while True:
        try:
            active = await realtor_sync_manager.send_heartbeat()
            logger.debug(f"Realtor sync heartbeat: {active} connections")
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

        await asyncio.sleep(30)  # Every 30 seconds


def start_realtor_sync_tasks():
    """Start background tasks for realtor sync."""
    asyncio.create_task(realtor_sync_heartbeat_task())
    logger.info("Realtor sync background tasks started")
