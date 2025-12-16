"""
Video Meeting WebRTC Signaling Server
Handles WebSocket connections for real-time video meeting signaling.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, Set, Optional
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

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
        """Connect a participant to a meeting room"""
        await websocket.accept()

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
            "joined_at": datetime.utcnow().isoformat(),
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
            return None, None

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

        logger.info(f"Participant {participant_id} disconnected from room {room_code}")

        return room_code, participant_id, participant_info

    async def send_to_participant(self, room_code: str, participant_id: str, message: dict):
        """Send a message to a specific participant"""
        if room_code in self.rooms and participant_id in self.rooms[room_code]:
            websocket = self.rooms[room_code][participant_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to {participant_id}: {e}")

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
    # Get display name from query params (falls back to participant_id)
    display_name = websocket.query_params.get("name", f"Guest-{participant_id[:6]}")
    is_host = websocket.query_params.get("host", "false").lower() == "true"

    await meeting_manager.connect(websocket, room_code, participant_id, display_name, is_host)

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
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif message_type == "request_offer":
                # Request an offer from another participant (for new joiners)
                target_id = message.get("target")
                if target_id:
                    await meeting_manager.send_to_participant(room_code, target_id, {
                        "type": "request_offer",
                        "from": participant_id
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
