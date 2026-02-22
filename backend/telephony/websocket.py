"""
WebSocket manager for real-time dialer updates

Provides real-time communication between the backend and frontend for:
- Call status updates (ringing, answered, completed)
- Session progress updates
- Disposition prompts
- Error notifications
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Optional
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


class WebSocketManager:
    """
    Manages WebSocket connections for real-time dialer updates

    Each agent can have multiple connections (multiple browser tabs)
    Messages are broadcast to all connections for a given agent
    """

    def __init__(self):
        # Map of agent_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, agent_id: str, skip_accept: bool = False):
        """Accept a new WebSocket connection for an agent"""
        if not skip_accept:
            await websocket.accept()

        if agent_id not in self.active_connections:
            self.active_connections[agent_id] = set()

        self.active_connections[agent_id].add(websocket)
        logger.info(f"WebSocket connected for agent {agent_id} (total: {len(self.active_connections[agent_id])})")

    def disconnect(self, websocket: WebSocket, agent_id: str):
        """Remove a WebSocket connection"""
        if agent_id in self.active_connections:
            self.active_connections[agent_id].discard(websocket)

            if not self.active_connections[agent_id]:
                del self.active_connections[agent_id]

        logger.info(f"WebSocket disconnected for agent {agent_id}")

    async def send_to_agent(self, agent_id: str, message: dict):
        """Send a message to all connections for an agent"""
        if agent_id not in self.active_connections:
            logger.debug(f"No active connections for agent {agent_id}")
            return

        disconnected = set()

        for connection in self.active_connections[agent_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection, agent_id)

    def send_to_agent_sync(self, agent_id: str, message: dict):
        """
        Synchronous wrapper for sending messages

        Useful when called from non-async contexts (like webhook handlers)
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.send_to_agent(agent_id, message))
            else:
                loop.run_until_complete(self.send_to_agent(agent_id, message))
        except RuntimeError:
            # No event loop - create a new one
            asyncio.run(self.send_to_agent(agent_id, message))
        except Exception as e:
            logger.error(f"Error in send_to_agent_sync: {e}")

    async def broadcast_to_all(self, message: dict):
        """Broadcast a message to all connected agents"""
        for agent_id in list(self.active_connections.keys()):
            await self.send_to_agent(agent_id, message)

    def get_connected_agents(self) -> list:
        """Get list of currently connected agent IDs"""
        return list(self.active_connections.keys())

    def is_agent_connected(self, agent_id: str) -> bool:
        """Check if an agent has any active connections"""
        return agent_id in self.active_connections and len(self.active_connections[agent_id]) > 0


# Singleton instance
ws_manager = WebSocketManager()


# =============================================================================
# Message Types for Dialer Events
# =============================================================================

class DialerEvent:
    """Helper class for creating standardized dialer event messages"""

    @staticmethod
    def call_initiated(session_id: int, task_id: int, call_sid: str, contact_name: str, contact_phone: str) -> dict:
        return {
            "type": "call_initiated",
            "session_id": session_id,
            "task_id": task_id,
            "call_sid": call_sid,
            "contact_name": contact_name,
            "contact_phone": contact_phone
        }

    @staticmethod
    def call_ringing(session_id: int, task_id: int, call_sid: str) -> dict:
        return {
            "type": "call_ringing",
            "session_id": session_id,
            "task_id": task_id,
            "call_sid": call_sid
        }

    @staticmethod
    def call_answered(session_id: int, task_id: int, call_sid: str, answered_by: Optional[str] = None) -> dict:
        return {
            "type": "call_answered",
            "session_id": session_id,
            "task_id": task_id,
            "call_sid": call_sid,
            "answered_by": answered_by
        }

    @staticmethod
    def call_completed(
        session_id: int,
        task_id: int,
        call_sid: str,
        duration: Optional[int] = None,
        status: str = "completed"
    ) -> dict:
        return {
            "type": "call_completed",
            "session_id": session_id,
            "task_id": task_id,
            "call_sid": call_sid,
            "duration": duration,
            "status": status,
            "needs_disposition": status == "completed"
        }

    @staticmethod
    def call_failed(session_id: int, task_id: int, error: str, error_code: Optional[str] = None) -> dict:
        return {
            "type": "call_failed",
            "session_id": session_id,
            "task_id": task_id,
            "error": error,
            "error_code": error_code
        }

    @staticmethod
    def session_updated(
        session_id: int,
        status: str,
        total_tasks: int,
        completed_tasks: int,
        pending_tasks: int
    ) -> dict:
        return {
            "type": "session_updated",
            "session_id": session_id,
            "status": status,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks
        }

    @staticmethod
    def session_completed(session_id: int, total_calls: int, connected_calls: int) -> dict:
        return {
            "type": "session_completed",
            "session_id": session_id,
            "total_calls": total_calls,
            "connected_calls": connected_calls
        }

    @staticmethod
    def disposition_required(session_id: int, task_id: int, contact_name: str) -> dict:
        return {
            "type": "disposition_required",
            "session_id": session_id,
            "task_id": task_id,
            "contact_name": contact_name
        }

    @staticmethod
    def next_call_ready(session_id: int, task_id: int, contact_name: str, contact_phone: str, delay_seconds: int = 0) -> dict:
        return {
            "type": "next_call_ready",
            "session_id": session_id,
            "task_id": task_id,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "delay_seconds": delay_seconds
        }

    @staticmethod
    def compliance_blocked(phone_number: str, issues: list) -> dict:
        return {
            "type": "compliance_blocked",
            "phone_number": phone_number,
            "issues": issues
        }

    @staticmethod
    def error(message: str, code: Optional[str] = None) -> dict:
        return {
            "type": "error",
            "message": message,
            "code": code
        }
