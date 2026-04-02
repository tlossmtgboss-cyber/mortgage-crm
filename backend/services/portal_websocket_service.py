"""
Portal WebSocket Service - Real-time updates for borrower and partner portals.

Manages WebSocket connections for:
- Borrower portal (authenticated by loan access token)
- Partner portal (authenticated by partner access token)
- Loan-specific updates (milestones, lifecycle, documents)
- Broadcast notifications
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
import asyncio
import logging
import json

logger = logging.getLogger(__name__)


class PortalConnectionManager:
    """
    Manages WebSocket connections for the portal system.

    Supports:
    - Loan-specific connections (borrowers viewing their loan)
    - Partner connections (realtors viewing shared loans)
    - Token-based authentication
    """

    def __init__(self):
        # Loan-specific connections: loan_id -> list of WebSockets
        self.loan_connections: Dict[int, List[WebSocket]] = {}

        # Partner connections: partner_token -> WebSocket
        self.partner_connections: Dict[str, WebSocket] = {}

        # Token to loan mapping for quick lookup
        self.token_to_loan: Dict[str, int] = {}

        # Connection metadata (for debugging/monitoring)
        self.connection_metadata: Dict[WebSocket, Dict] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    # =========================================================================
    # CONNECTION MANAGEMENT
    # =========================================================================

    async def connect_borrower(
        self,
        websocket: WebSocket,
        loan_id: int,
        access_token: Optional[str] = None
    ):
        """Connect a borrower to their loan's WebSocket channel."""
        await websocket.accept()

        async with self._lock:
            if loan_id not in self.loan_connections:
                self.loan_connections[loan_id] = []

            self.loan_connections[loan_id].append(websocket)

            # Store metadata
            self.connection_metadata[websocket] = {
                "type": "borrower",
                "loan_id": loan_id,
                "access_token": access_token,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            }

            if access_token:
                self.token_to_loan[access_token] = loan_id

        logger.info(f"Borrower connected to loan {loan_id}, total connections: {len(self.loan_connections[loan_id])}")

        # Send connection confirmation
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    async def connect_partner(
        self,
        websocket: WebSocket,
        partner_token: str,
        loan_id: int
    ):
        """Connect a partner (realtor) to view a loan."""
        await websocket.accept()

        async with self._lock:
            # Store partner connection
            self.partner_connections[partner_token] = websocket

            # Also add to loan connections for broadcasts
            if loan_id not in self.loan_connections:
                self.loan_connections[loan_id] = []
            self.loan_connections[loan_id].append(websocket)

            # Store metadata
            self.connection_metadata[websocket] = {
                "type": "partner",
                "loan_id": loan_id,
                "partner_token": partner_token,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            }

            self.token_to_loan[partner_token] = loan_id

        logger.info(f"Partner connected to loan {loan_id}")

        # Send connection confirmation
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "loan_id": loan_id,
            "view_type": "partner",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    async def disconnect(self, websocket: WebSocket):
        """Disconnect a WebSocket and clean up references."""
        async with self._lock:
            metadata = self.connection_metadata.pop(websocket, {})

            # Remove from loan connections
            loan_id = metadata.get("loan_id")
            if loan_id and loan_id in self.loan_connections:
                if websocket in self.loan_connections[loan_id]:
                    self.loan_connections[loan_id].remove(websocket)
                # Clean up empty lists
                if not self.loan_connections[loan_id]:
                    del self.loan_connections[loan_id]

            # Remove from partner connections
            partner_token = metadata.get("partner_token")
            if partner_token and partner_token in self.partner_connections:
                del self.partner_connections[partner_token]

            # Clean up token mapping
            access_token = metadata.get("access_token") or metadata.get("partner_token")
            if access_token and access_token in self.token_to_loan:
                del self.token_to_loan[access_token]

        logger.info(f"WebSocket disconnected: {metadata.get('type', 'unknown')} from loan {loan_id}")

    # =========================================================================
    # MESSAGE BROADCASTING
    # =========================================================================

    async def broadcast_to_loan(self, loan_id: int, message: Dict):
        """Broadcast a message to all connections for a specific loan."""
        connections = self.loan_connections.get(loan_id, [])

        if not connections:
            logger.debug(f"No active connections for loan {loan_id}")
            return

        disconnected = []
        sent_count = 0

        for connection in connections:
            try:
                await connection.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.append(connection)

        # Clean up disconnected
        for conn in disconnected:
            await self.disconnect(conn)

        logger.info(f"Broadcast to loan {loan_id}: {sent_count} recipients")

    async def send_to_partner(self, partner_token: str, message: Dict):
        """Send a message to a specific partner connection."""
        connection = self.partner_connections.get(partner_token)

        if not connection:
            logger.warning(f"No connection for partner token {partner_token[:8]}...")
            return False

        try:
            await connection.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to partner WebSocket: {e}")
            await self.disconnect(connection)
            return False

    async def broadcast_milestone_update(
        self,
        loan_id: int,
        milestone_id: int,
        milestone_name: str,
        status: str,
        completed_at: Optional[str] = None
    ):
        """Broadcast a milestone status update to loan viewers."""
        message = {
            "type": "MILESTONE_UPDATE",
            "loan_id": loan_id,
            "data": {
                "milestone_id": milestone_id,
                "milestone_name": milestone_name,
                "status": status,
                "completed_at": completed_at,
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self.broadcast_to_loan(loan_id, message)

    async def broadcast_lifecycle_change(
        self,
        loan_id: int,
        previous_stage: Optional[str],
        new_stage: str,
        changed_by: Optional[str] = None
    ):
        """Broadcast a lifecycle stage change to loan viewers."""
        message = {
            "type": "LIFECYCLE_CHANGE",
            "loan_id": loan_id,
            "data": {
                "previous_stage": previous_stage,
                "new_stage": new_stage,
                "changed_by": changed_by,
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self.broadcast_to_loan(loan_id, message)

    async def broadcast_document_update(
        self,
        loan_id: int,
        document_id: int,
        document_type: str,
        status: str,
        file_name: Optional[str] = None
    ):
        """Broadcast a document status update to loan viewers."""
        message = {
            "type": "DOCUMENT_UPDATE",
            "loan_id": loan_id,
            "data": {
                "document_id": document_id,
                "document_type": document_type,
                "status": status,
                "file_name": file_name,
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self.broadcast_to_loan(loan_id, message)

    async def broadcast_close_on_time_update(
        self,
        loan_id: int,
        milestone_name: str,
        is_completed: bool,
        business_days_remaining: int
    ):
        """Broadcast a Close On Time milestone update."""
        message = {
            "type": "CLOSE_ON_TIME_UPDATE",
            "loan_id": loan_id,
            "data": {
                "milestone_name": milestone_name,
                "is_completed": is_completed,
                "business_days_remaining": business_days_remaining,
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self.broadcast_to_loan(loan_id, message)

    async def send_notification(
        self,
        loan_id: int,
        title: str,
        message_text: str,
        notification_type: str = "info",
        action_url: Optional[str] = None
    ):
        """Send a notification to all loan viewers."""
        message = {
            "type": "NOTIFICATION",
            "loan_id": loan_id,
            "data": {
                "title": title,
                "message": message_text,
                "notification_type": notification_type,
                "action_url": action_url,
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self.broadcast_to_loan(loan_id, message)

    # =========================================================================
    # CONNECTION STATUS
    # =========================================================================

    def get_loan_connection_count(self, loan_id: int) -> int:
        """Get the number of active connections for a loan."""
        return len(self.loan_connections.get(loan_id, []))

    def get_active_loans(self) -> List[int]:
        """Get list of loan IDs with active connections."""
        return list(self.loan_connections.keys())

    def get_connection_stats(self) -> Dict:
        """Get overall connection statistics."""
        return {
            "total_loans": len(self.loan_connections),
            "total_connections": sum(len(conns) for conns in self.loan_connections.values()),
            "partner_connections": len(self.partner_connections),
            "active_loans": self.get_active_loans(),
        }

    async def ping_all(self):
        """Send ping to all connections to keep them alive."""
        all_connections = []
        for connections in self.loan_connections.values():
            all_connections.extend(connections)

        disconnected = []

        for conn in all_connections:
            try:
                await conn.send_json({"type": "PING", "timestamp": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                logger.exception(f"Failed to send ping to WebSocket connection: {e}")
                disconnected.append(conn)

        for conn in disconnected:
            await self.disconnect(conn)

        return len(all_connections) - len(disconnected)


# Global instance
portal_ws_manager = PortalConnectionManager()


# =============================================================================
# FASTAPI WEBSOCKET ROUTES
# =============================================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(tags=["Portal WebSocket"])


@router.websocket("/ws/loan/{loan_id}")
async def loan_websocket(
    websocket: WebSocket,
    loan_id: int,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time loan updates.
    Requires borrower JWT token.

    Connect via: ws://host/ws/loan/{loan_id}?token={access_token}

    Messages received:
    - MILESTONE_UPDATE: Milestone status changed
    - LIFECYCLE_CHANGE: Loan stage changed
    - DOCUMENT_UPDATE: Document status changed
    - CLOSE_ON_TIME_UPDATE: COT milestone updated
    - NOTIFICATION: General notification
    - PING: Keep-alive ping
    """
    # Validate borrower token before accepting connection
    try:
        from borrower_auth_routes import verify_borrower_token
        payload = verify_borrower_token(token)
        if not payload or payload.get("type") != "borrower":
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

        # Verify borrower has access to this loan
        db = next(get_db())
        try:
            borrower_id = payload.get("sub")
            loan_access = db.execute(text(
                "SELECT id FROM loans WHERE id = :loan_id AND borrower_id = :borrower_id"
            ), {"loan_id": loan_id, "borrower_id": borrower_id}).fetchone()
            if not loan_access:
                await websocket.close(code=4003, reason="Access denied to this loan")
                return
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Loan WebSocket auth error: {e}")
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await portal_ws_manager.connect_borrower(websocket, loan_id, token)

    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                # Handle client messages
                if message.get("type") == "PONG":
                    # Client responded to ping
                    pass
                elif message.get("type") == "SUBSCRIBE":
                    # Client wants to subscribe to additional updates
                    logger.info(f"Subscription request from loan {loan_id}: {message}")

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data[:100]}")

    except WebSocketDisconnect:
        await portal_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error for loan {loan_id}: {e}")
        await portal_ws_manager.disconnect(websocket)


@router.websocket("/ws/partner/{partner_token}")
async def partner_websocket(
    websocket: WebSocket,
    partner_token: str
):
    """
    WebSocket endpoint for partner (realtor) portal updates.

    Partners receive filtered updates appropriate for their view level.
    """
    # Validate partner token and get loan_id
    # In production, this would verify the token against the database
    db = next(get_db())
    try:
        from models.portal_models import PartnerPortalAccess

        access = db.query(PartnerPortalAccess).filter(
            PartnerPortalAccess.access_token == partner_token,
            PartnerPortalAccess.is_active == True
        ).first()

        if not access:
            await websocket.close(code=4001, reason="Invalid or expired partner token")
            return

        loan_id = access.loan_id

    except SQLAlchemyError as e:
        logger.error(f"Error validating partner token: {e}")
        await websocket.close(code=4000, reason="Token validation failed")
        return
    finally:
        db.close()

    await portal_ws_manager.connect_partner(websocket, partner_token, loan_id)

    try:
        while True:
            data = await websocket.receive_text()
            # Partner clients typically only receive, not send
            logger.debug(f"Partner message received: {data[:100]}")

    except WebSocketDisconnect:
        await portal_ws_manager.disconnect(websocket)
    except SQLAlchemyError as e:
        logger.error(f"Partner WebSocket error: {e}")
        await portal_ws_manager.disconnect(websocket)


@router.get("/ws/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics."""
    return portal_ws_manager.get_connection_stats()


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def websocket_keepalive_task():
    """Background task to keep WebSocket connections alive."""
    while True:
        try:
            active = await portal_ws_manager.ping_all()
            logger.debug(f"Keepalive ping sent to {active} connections")
        except Exception as e:
            logger.error(f"Keepalive error: {e}")

        await asyncio.sleep(30)  # Ping every 30 seconds


def start_keepalive_task():
    """Start the keepalive background task."""
    asyncio.create_task(websocket_keepalive_task())
    logger.info("WebSocket keepalive task started")
