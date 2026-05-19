"""
Video Meeting WebRTC Signaling Server
Handles WebSocket connections for real-time video meeting signaling.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, Set, Optional, Tuple
import json
import logging
import asyncio
import os
from datetime import datetime, timezone
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

logger = logging.getLogger(__name__)


# ============================================================================
# HOST AUTHENTICATION
# ============================================================================

async def resolve_host_status(token: Optional[str], room_code: str) -> Tuple[bool, Optional[int]]:
    """
    Resolve whether a connecting user is the host of a meeting room.
    Decodes JWT token to get user_id, then checks against the room's host_user_id.
    Returns (is_host, user_id). Falls back to (False, None) for guests.
    """
    if not token:
        return False, None

    try:
        from auth.tokens import verify_access_token

        payload = verify_access_token(token)
        if not payload:
            logger.warning("Token invalid/expired/revoked, cannot verify host status")
            return False, None

        email = payload.get("sub")
        if not email:
            return False, None

        # Look up user and room in DB with two indexed queries (not CROSS JOIN)
        from database import SessionLocal
        db = SessionLocal()
        try:
            from sqlalchemy import text
            user_row = db.execute(
                text("SELECT id FROM users WHERE email = :email LIMIT 1"),
                {"email": email}
            ).fetchone()
            if not user_row:
                return False, None

            room_row = db.execute(
                text("SELECT host_user_id FROM video_meeting_rooms WHERE room_code = :room_code LIMIT 1"),
                {"room_code": room_code}
            ).fetchone()
            if not room_row:
                return False, None

            user_id = user_row[0]
            host_user_id = room_row[0]
            return user_id == host_user_id, user_id
        finally:
            db.close()

    except ExpiredSignatureError:
        logger.info(f"Expired token for room {room_code}")
        return False, None
    except InvalidTokenError as e:
        logger.warning(f"JWT error for room {room_code}: {e}")
        return False, None
    except Exception as e:
        logger.error(f"Unexpected error resolving host status: {e}")

    return False, None

router = APIRouter(prefix="/api/v1/meetings", tags=["Video Meeting Signaling"])

# ============================================================================
# CONNECTION MANAGEMENT
# ============================================================================

class MeetingConnectionManager:
    """
    Manages WebSocket connections for video meeting rooms.
    Handles signaling for WebRTC peer connections.
    """

    def __init__(self):
        # room_code -> {participant_id -> websocket}
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}
        # room_code -> {participant_id -> participant_info}
        self.participants: Dict[str, Dict[str, dict]] = {}
        # websocket -> (room_code, participant_id)
        self.connections: Dict[WebSocket, tuple] = {}

    async def connect(
        self,
        websocket: WebSocket,
        room_code: str,
        participant_id: str,
        display_name: str,
        is_host: bool = False
    ):
        """Connect a participant to a meeting room.
        Note: caller must accept() the WebSocket before calling this method.
        """

        # Initialize room if needed
        if room_code not in self.rooms:
            self.rooms[room_code] = {}
            self.participants[room_code] = {}

        # Store connection
        self.rooms[room_code][participant_id] = websocket
        self.participants[room_code][participant_id] = {
            "id": participant_id,
            "display_name": display_name,
            "is_host": is_host,
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "video_enabled": True,
            "audio_enabled": True
        }
        self.connections[websocket] = (room_code, participant_id)

        logger.info(f"Participant {participant_id} ({display_name}) connected to room {room_code}")

        # Notify existing participants about new participant
        await self.broadcast_to_room(room_code, {
            "type": "participant_joined",
            "participant": self.participants[room_code][participant_id],
            "participant_id": participant_id
        }, exclude=participant_id)

        # Send current participants list to new participant
        current_participants = list(self.participants[room_code].values())
        await self.send_to_participant(room_code, participant_id, {
            "type": "participants_list",
            "participants": current_participants
        })

    def disconnect(self, websocket: WebSocket):
        """Disconnect a participant from a meeting room"""
        if websocket not in self.connections:
            return None, None, None

        room_code, participant_id = self.connections[websocket]

        # Get participant info before removing
        participant_info = self.participants.get(room_code, {}).get(participant_id, {})

        # Remove from room
        if room_code in self.rooms and participant_id in self.rooms[room_code]:
            del self.rooms[room_code][participant_id]

        # Remove participant info
        if room_code in self.participants and participant_id in self.participants[room_code]:
            del self.participants[room_code][participant_id]

        # Remove connection mapping
        del self.connections[websocket]

        # Clean up empty rooms
        if room_code in self.rooms and not self.rooms[room_code]:
            del self.rooms[room_code]
            if room_code in self.participants:
                del self.participants[room_code]
            logger.info(f"Room {room_code} emptied and cleaned up")

        logger.info(f"Participant {participant_id} disconnected from room {room_code}")

        return room_code, participant_id, participant_info

    async def send_to_participant(self, room_code: str, participant_id: str, message: dict):
        """Send a message to a specific participant"""
        if room_code in self.rooms and participant_id in self.rooms[room_code]:
            websocket = self.rooms[room_code][participant_id]
            try:
                await websocket.send_json(message)
            except (RuntimeError, ConnectionError, WebSocketDisconnect) as e:
                logger.warning(f"Connection lost sending to {participant_id}: {e}")

    async def broadcast_to_room(self, room_code: str, message: dict, exclude: str = None):
        """Broadcast a message to all participants in a room"""
        if room_code not in self.rooms:
            return

        for participant_id, websocket in self.rooms[room_code].items():
            if participant_id != exclude:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {participant_id}: {e}")

    def get_room_participants(self, room_code: str) -> list:
        """Get list of participants in a room"""
        return list(self.participants.get(room_code, {}).values())

    def get_participant_count(self, room_code: str) -> int:
        """Get number of participants in a room"""
        return len(self.rooms.get(room_code, {}))


# Global connection manager
meeting_manager = MeetingConnectionManager()


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@router.websocket("/ws/{room_code}/{participant_id}")
async def websocket_video_meeting(
    websocket: WebSocket,
    room_code: str,
    participant_id: str
):
    """
    WebSocket endpoint for video meeting signaling.

    Message types:
    - offer: WebRTC SDP offer
    - answer: WebRTC SDP answer
    - ice_candidate: ICE candidate
    - media_state: Audio/video enabled state
    - chat: Chat message
    """
    # Get display name from query params; token via post-connect auth message
    display_name = websocket.query_params.get("name", f"Guest-{participant_id[:6]}")
    token = websocket.query_params.get("token", "")

    await websocket.accept()

    # Security: If no token in URL, read it from the first WebSocket message
    # to avoid leaking JWT into server/proxy access logs and browser history.
    if not token:
        try:
            import asyncio as _asyncio
            raw = await _asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            msg = json.loads(raw)
            if isinstance(msg, dict) and msg.get("type") == "auth":
                token = msg.get("token", "")
        except Exception as _exc:  # noqa: BLE001
            pass  # Token is optional for meetings (guest participants)

    # Server-side host verification via JWT + DB lookup
    is_host, user_id = await resolve_host_status(token, room_code)

    await meeting_manager.connect(websocket, room_code, participant_id, display_name, is_host)

    # Send connection acknowledgement with server-verified host status
    await websocket.send_json({
        "type": "connection_ack",
        "is_host": is_host,
        "participant_id": participant_id,
        "user_id": user_id
    })

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            message_type = message.get("type")

            if message_type == "ping":
                # Respond to ping with pong
                await websocket.send_json({"type": "pong"})

            elif message_type == "offer":
                # WebRTC SDP offer - forward to target participant
                target_id = message.get("target")
                if target_id:
                    await meeting_manager.send_to_participant(room_code, target_id, {
                        "type": "offer",
                        "sdp": message.get("sdp"),
                        "from": participant_id
                    })

            elif message_type == "answer":
                # WebRTC SDP answer - forward to target participant
                target_id = message.get("target")
                if target_id:
                    await meeting_manager.send_to_participant(room_code, target_id, {
                        "type": "answer",
                        "sdp": message.get("sdp"),
                        "from": participant_id
                    })

            elif message_type == "ice_candidate":
                # ICE candidate - forward to target participant
                target_id = message.get("target")
                if target_id:
                    await meeting_manager.send_to_participant(room_code, target_id, {
                        "type": "ice_candidate",
                        "candidate": message.get("candidate"),
                        "from": participant_id
                    })

            elif message_type == "media_state":
                # Update media state (audio/video enabled)
                audio = message.get("audio")
                video = message.get("video")

                if room_code in meeting_manager.participants:
                    if participant_id in meeting_manager.participants[room_code]:
                        if audio is not None:
                            meeting_manager.participants[room_code][participant_id]["audio_enabled"] = audio
                        if video is not None:
                            meeting_manager.participants[room_code][participant_id]["video_enabled"] = video

                # Broadcast state change to others
                await meeting_manager.broadcast_to_room(room_code, {
                    "type": "participant_media_state",
                    "participant_id": participant_id,
                    "audio": audio,
                    "video": video
                }, exclude=participant_id)

            elif message_type == "chat":
                # Chat message - broadcast to room
                await meeting_manager.broadcast_to_room(room_code, {
                    "type": "chat",
                    "from": participant_id,
                    "sender_name": display_name,
                    "message": message.get("message", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            elif message_type == "request_offer":
                # Request an offer from another participant (for new joiners)
                target_id = message.get("target")
                if target_id:
                    await meeting_manager.send_to_participant(room_code, target_id, {
                        "type": "request_offer",
                        "from": participant_id
                    })

            elif message_type == "recording_started":
                # Only hosts can broadcast recording state - validated server-side
                if is_host:
                    recording_id = message.get("recording_id", "")
                    if len(str(recording_id)) > 64:
                        recording_id = str(recording_id)[:64]
                    await meeting_manager.broadcast_to_room(room_code, {
                        "type": "recording_state_changed",
                        "recording": True,
                        "started_by": participant_id,
                        "started_by_name": display_name,
                        "recording_id": recording_id,
                        "consent_type": message.get("consent_type"),
                        "disclosure_script": message.get("disclosure_script"),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, exclude=participant_id)

            elif message_type == "recording_stopped":
                # Only hosts can broadcast recording state - validated server-side
                if is_host:
                    await meeting_manager.broadcast_to_room(room_code, {
                        "type": "recording_state_changed",
                        "recording": False,
                        "stopped_by": participant_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, exclude=participant_id)

            elif message_type == "breakout_created":
                # Host created a breakout room - broadcast to all
                if is_host:
                    await meeting_manager.broadcast_to_room(room_code, {
                        "type": "breakout_update",
                        "action": "created",
                        "room_id": message.get("room_id") or message.get("room"),
                        "room": message.get("room"),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            elif message_type == "breakout_closed":
                # Host closed a breakout room - broadcast to all
                if is_host:
                    await meeting_manager.broadcast_to_room(room_code, {
                        "type": "breakout_update",
                        "action": "closed",
                        "room_id": message.get("room_id"),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            elif message_type == "breakout_join":
                # Participant joined a breakout room - broadcast to all
                await meeting_manager.broadcast_to_room(room_code, {
                    "type": "breakout_update",
                    "action": "participant_joined",
                    "room_id": message.get("room_id"),
                    "participant_id": participant_id,
                    "display_name": display_name,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            elif message_type == "breakout_leave":
                # Participant left a breakout room - broadcast to all
                await meeting_manager.broadcast_to_room(room_code, {
                    "type": "breakout_update",
                    "action": "participant_left",
                    "room_id": message.get("room_id"),
                    "participant_id": participant_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            else:
                logger.warning(f"Unknown message type: {message_type}")

    except WebSocketDisconnect:
        result = meeting_manager.disconnect(websocket)
        if result:
            room_code, participant_id, participant_info = result
            # Notify others about disconnect
            await meeting_manager.broadcast_to_room(room_code, {
                "type": "participant_left",
                "participant_id": participant_id,
                "display_name": participant_info.get("display_name", "Unknown")
            })
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        meeting_manager.disconnect(websocket)


# ============================================================================
# REST ENDPOINTS FOR SIGNALING STATUS
# ============================================================================

@router.get("/rooms/{room_code}/signaling/status")
async def get_signaling_status(room_code: str):
    """Get the current signaling status for a room"""
    return {
        "room_code": room_code,
        "participant_count": meeting_manager.get_participant_count(room_code),
        "participants": meeting_manager.get_room_participants(room_code)
    }


@router.get("/ice-servers")
async def get_ice_servers():
    """
    Get ICE servers for WebRTC connections.
    Priority: 1) Telnyx TURN (if available)
              2) Self-hosted coturn (if configured)
              3) STUN-only (no relay, will fail behind symmetric NAT)
    """
    # STUN servers (always included)
    ice_servers = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
    ]

    turn_available = False

    # Priority 1: Telnyx TURN
    # Telnyx does not provide a standalone TURN token service.
    # Skip to self-hosted coturn or configure a dedicated TURN provider.
    logger.debug("Checking coturn / STUN-only fallback")

    # Priority 2: Self-hosted coturn (if configured)
    if not turn_available:
        coturn_host = os.getenv("COTURN_HOST")
        coturn_user = os.getenv("COTURN_USERNAME")
        coturn_pass = os.getenv("COTURN_PASSWORD")
        coturn_port = os.getenv("COTURN_PORT", "3478")

        if coturn_host and coturn_user and coturn_pass:
            ice_servers.extend([
                {
                    "urls": f"turn:{coturn_host}:{coturn_port}",
                    "username": coturn_user,
                    "credential": coturn_pass
                },
                {
                    "urls": f"turn:{coturn_host}:{coturn_port}?transport=tcp",
                    "username": coturn_user,
                    "credential": coturn_pass
                },
                {
                    "urls": f"turns:{coturn_host}:443?transport=tcp",
                    "username": coturn_user,
                    "credential": coturn_pass
                }
            ])
            turn_available = True
            logger.info(f"TURN: coturn ({coturn_host.split('.')[0]}...)")

    if not turn_available:
        logger.warning(
            "No TURN server configured. Video calls will fail behind symmetric NAT/firewalls. "
            "Set COTURN_HOST/COTURN_USERNAME/COTURN_PASSWORD for reliable video calls."
        )

    return {
        "iceServers": ice_servers,
        "turnAvailable": turn_available
    }


@router.get("/ice-servers/health")
async def ice_servers_health():
    """Check TURN server availability for monitoring."""
    telnyx_ok = bool(os.getenv("TELNYX_API_KEY"))
    coturn_ok = bool(os.getenv("COTURN_HOST") and os.getenv("COTURN_USERNAME"))

    status = "healthy" if (telnyx_ok or coturn_ok) else "degraded"

    return {
        "status": status,
        "telnyx_configured": telnyx_ok,
        "coturn_configured": coturn_ok,
        "recommendation": None if (telnyx_ok or coturn_ok) else "Configure TELNYX or COTURN credentials for reliable video calls"
    }
