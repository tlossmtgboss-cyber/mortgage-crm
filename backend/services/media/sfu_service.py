"""
LiveKit SFU Integration Service

Provides Selective Forwarding Unit (SFU) capabilities for video meetings
with more than 4 participants. Below that threshold, the existing peer-to-peer
WebRTC mesh in video_meeting_signaling.py is used instead.

LiveKit REST API reference:
  - Room Service:  POST /twirp/livekit.RoomService/<Method>
  - Egress Service: POST /twirp/livekit.Egress/<Method>

Auth: every request carries an Authorization header containing a short-lived
JWT signed with LIVEKIT_API_SECRET, with ``iss`` = LIVEKIT_API_KEY and
``video`` grant claims.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests
from jose import jwt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SFU_PARTICIPANT_THRESHOLD = 4
"""When the participant count exceeds this value, meetings should be routed
through the SFU rather than a peer-to-peer mesh."""

_TOKEN_TTL_SECONDS = 6 * 60 * 60  # 6 hours
_API_TOKEN_TTL_SECONDS = 60  # short-lived tokens for server-side API calls


# ===========================================================================
# SFUService
# ===========================================================================

class SFUService:
    """
    Manages LiveKit rooms, participants, and token generation.

    All configuration is read from environment variables:
      - LIVEKIT_API_KEY
      - LIVEKIT_API_SECRET
      - LIVEKIT_URL  (e.g. wss://myproject.livekit.cloud)
    """

    def __init__(self) -> None:
        self.api_key: str = os.getenv("LIVEKIT_API_KEY", "")
        self.api_secret: str = os.getenv("LIVEKIT_API_SECRET", "")
        self.livekit_url: str = os.getenv("LIVEKIT_URL", "")

        # Derive the HTTP base URL from the WebSocket URL.
        self._http_base: str = self._ws_to_http(self.livekit_url) if self.livekit_url else ""

        if self.enabled:
            logger.info("SFU service enabled (LiveKit URL: %s)", self.livekit_url)
        else:
            logger.info("SFU service disabled -- missing LIVEKIT env vars")

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Return True when all required LiveKit configuration is present."""
        return bool(self.api_key and self.api_secret and self.livekit_url)

    # -----------------------------------------------------------------------
    # Token generation
    # -----------------------------------------------------------------------

    def generate_token(
        self,
        room_name: str,
        participant_identity: str,
        is_host: bool = False,
    ) -> Optional[str]:
        """Generate a LiveKit JWT access token for a participant.

        Args:
            room_name: The LiveKit room to grant access to.
            participant_identity: Unique identity string for the participant.
            is_host: When True the token includes admin grants (mute others,
                     remove participants, manage room).

        Returns:
            Encoded JWT string, or None if the service is not enabled.
        """
        if not self.enabled:
            logger.warning("generate_token called but SFU service is not enabled")
            return None

        try:
            now = int(time.time())

            # Build video grant claims following the LiveKit JWT spec.
            video_grant: Dict[str, Any] = {
                "room": room_name,
                "roomJoin": True,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
            }

            if is_host:
                video_grant["roomAdmin"] = True
                video_grant["roomCreate"] = True
                video_grant["roomList"] = True
                video_grant["canPublishSources"] = [
                    "camera",
                    "microphone",
                    "screen_share",
                    "screen_share_audio",
                ]

            claims: Dict[str, Any] = {
                "iss": self.api_key,
                "sub": participant_identity,
                "iat": now,
                "nbf": now,
                "exp": now + _TOKEN_TTL_SECONDS,
                "jti": f"{participant_identity}-{now}",
                "video": video_grant,
                "metadata": "",
                "name": participant_identity,
            }

            token = jwt.encode(claims, self.api_secret, algorithm="HS256")
            logger.debug(
                "Generated LiveKit token for %s in room %s (host=%s)",
                participant_identity,
                room_name,
                is_host,
            )
            return token
        except Exception as e:
            logger.exception(f"Failed to generate LiveKit token: {e}")
            return None

    # -----------------------------------------------------------------------
    # Room management
    # -----------------------------------------------------------------------

    def create_room(
        self,
        room_name: str,
        max_participants: int = 50,
        empty_timeout: int = 300,
    ) -> Optional[Dict[str, Any]]:
        """Create a LiveKit room via the RoomService API.

        Args:
            room_name: Unique name for the room.
            max_participants: Maximum number of allowed participants.
            empty_timeout: Seconds to wait before automatically closing an
                           empty room.

        Returns:
            Parsed JSON response from LiveKit, or None on failure.
        """
        return self._api_request(
            method="POST",
            endpoint="/twirp/livekit.RoomService/CreateRoom",
            data={
                "name": room_name,
                "max_participants": max_participants,
                "empty_timeout": empty_timeout,
            },
        )

    def delete_room(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Delete a LiveKit room."""
        return self._api_request(
            method="POST",
            endpoint="/twirp/livekit.RoomService/DeleteRoom",
            data={"room": room_name},
        )

    # -----------------------------------------------------------------------
    # Participant management
    # -----------------------------------------------------------------------

    def list_participants(self, room_name: str) -> Optional[List[Dict[str, Any]]]:
        """List all participants currently in a room.

        Returns:
            A list of participant dicts, or None on failure.
        """
        result = self._api_request(
            method="POST",
            endpoint="/twirp/livekit.RoomService/ListParticipants",
            data={"room": room_name},
        )
        if result is None:
            return None
        # LiveKit returns {"participants": [...]}
        return result.get("participants", [])

    def remove_participant(
        self,
        room_name: str,
        identity: str,
    ) -> Optional[Dict[str, Any]]:
        """Remove a participant from a room."""
        return self._api_request(
            method="POST",
            endpoint="/twirp/livekit.RoomService/RemoveParticipant",
            data={"room": room_name, "identity": identity},
        )

    def mute_participant(
        self,
        room_name: str,
        identity: str,
        track_sid: str,
        muted: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Mute or unmute a specific track for a participant.

        Args:
            room_name: The room containing the participant.
            identity: Participant identity string.
            track_sid: The SID of the track to mute/unmute.
            muted: True to mute, False to unmute.
        """
        return self._api_request(
            method="POST",
            endpoint="/twirp/livekit.RoomService/MutePublishedTrack",
            data={
                "room": room_name,
                "identity": identity,
                "track_sid": track_sid,
                "muted": muted,
            },
        )

    # -----------------------------------------------------------------------
    # Adaptive routing
    # -----------------------------------------------------------------------

    @staticmethod
    def should_use_sfu(participant_count: int) -> bool:
        """Determine whether to use SFU or peer-to-peer mesh.

        Peer-to-peer mesh works well for small groups (<=4).  Beyond that
        the number of connections grows quadratically, so an SFU is preferred.

        Args:
            participant_count: Current or expected number of participants.

        Returns:
            True if the meeting should be routed through the SFU.
        """
        return participant_count > SFU_PARTICIPANT_THRESHOLD

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _generate_api_token(self) -> str:
        """Generate a short-lived JWT for authenticating server-side API calls."""
        now = int(time.time())
        claims = {
            "iss": self.api_key,
            "iat": now,
            "nbf": now,
            "exp": now + _API_TOKEN_TTL_SECONDS,
            "video": {
                "roomCreate": True,
                "roomList": True,
                "roomAdmin": True,
            },
        }
        return jwt.encode(claims, self.api_secret, algorithm="HS256")

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send an authenticated request to the LiveKit REST API.

        Args:
            method: HTTP method (POST for Twirp endpoints).
            endpoint: API path, e.g. ``/twirp/livekit.RoomService/CreateRoom``.
            data: JSON-serialisable request body.

        Returns:
            Parsed JSON response, or None on failure.
        """
        if not self.enabled:
            logger.warning("_api_request called but SFU service is not enabled")
            return None

        url = f"{self._http_base}{endpoint}"
        token = self._generate_api_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data or {},
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as exc:
            logger.error(
                "LiveKit API HTTP error %s %s: %s - %s",
                method,
                endpoint,
                exc.response.status_code if exc.response is not None else "N/A",
                exc.response.text[:500] if exc.response is not None else str(exc),
            )
            return None
        except requests.exceptions.RequestException:
            logger.exception("LiveKit API request failed: %s %s", method, endpoint)
            return None

    @staticmethod
    def _ws_to_http(ws_url: str) -> str:
        """Convert a WebSocket URL to its HTTP(S) equivalent.

        ``wss://host`` -> ``https://host``
        ``ws://host``  -> ``http://host``
        """
        if ws_url.startswith("wss://"):
            return "https://" + ws_url[len("wss://"):]
        if ws_url.startswith("ws://"):
            return "http://" + ws_url[len("ws://"):]
        # Already an HTTP URL or something unexpected -- return as-is.
        return ws_url.rstrip("/")


# ===========================================================================
# SFURecordingService
# ===========================================================================

class SFURecordingService:
    """
    Manages meeting recordings via the LiveKit Egress API.

    Depends on a configured ``SFUService`` instance for credentials and
    HTTP base URL resolution.
    """

    def __init__(self, sfu: Optional[SFUService] = None) -> None:
        self._sfu = sfu

    @property
    def _service(self) -> SFUService:
        """Resolve the SFU service, falling back to the module-level singleton."""
        if self._sfu is not None:
            return self._sfu
        return sfu_service

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start_composite_recording(
        self,
        room_name: str,
        output_config: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Start a composite recording of all tracks in a room.

        Args:
            room_name: The room to record.
            output_config: Output configuration dict. Typically contains either
                ``file`` (for file output) or ``s3`` / ``gcp`` / ``azure``
                (for direct cloud upload).  Example::

                    {
                        "file": {
                            "filepath": "/recordings/{room_name}-{time}.mp4"
                        }
                    }

                Or for S3::

                    {
                        "s3": {
                            "access_key": "...",
                            "secret": "...",
                            "bucket": "recordings",
                            "region": "us-east-1",
                        },
                        "filepath": "meetings/{room_name}-{time}.mp4",
                    }

        Returns:
            Parsed egress info dict (contains ``egress_id``), or None.
        """
        payload: Dict[str, Any] = {
            "room_name": room_name,
            "layout": "speaker-dark",
            "audio_only": False,
        }

        # Merge output_config into the payload. LiveKit expects the output
        # destination (file, s3, etc.) at the top level of the request.
        if output_config:
            payload.update(output_config)

        return self._egress_request(
            method="POST",
            endpoint="/twirp/livekit.Egress/StartRoomCompositeEgress",
            data=payload,
        )

    def stop_recording(self, egress_id: str) -> Optional[Dict[str, Any]]:
        """Stop an active egress/recording.

        Args:
            egress_id: The ID returned when the egress was started.

        Returns:
            Updated egress info dict, or None on failure.
        """
        return self._egress_request(
            method="POST",
            endpoint="/twirp/livekit.Egress/StopEgress",
            data={"egress_id": egress_id},
        )

    def get_recording_status(self, egress_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of an egress.

        Args:
            egress_id: The egress to query.

        Returns:
            Egress info dict, or None on failure.
        """
        result = self._egress_request(
            method="POST",
            endpoint="/twirp/livekit.Egress/ListEgress",
            data={"egress_id": egress_id},
        )
        if result is None:
            return None
        # ListEgress returns {"items": [...]}
        items = result.get("items", [])
        if not items:
            logger.warning("No egress found with id %s", egress_id)
            return None
        return items[0]

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _egress_request(
        self,
        method: str,
        endpoint: str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Send an authenticated request to the LiveKit Egress API.

        Uses the underlying SFUService for credentials and base URL, but
        issues its own token with egress-specific grants.
        """
        sfu = self._service
        if not sfu.enabled:
            logger.warning("Egress request attempted but SFU service is not enabled")
            return None

        url = f"{sfu._http_base}{endpoint}"
        token = self._generate_egress_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as exc:
            logger.error(
                "LiveKit Egress HTTP error %s %s: %s - %s",
                method,
                endpoint,
                exc.response.status_code if exc.response is not None else "N/A",
                exc.response.text[:500] if exc.response is not None else str(exc),
            )
            return None
        except requests.exceptions.RequestException:
            logger.exception("LiveKit Egress request failed: %s %s", method, endpoint)
            return None

    def _generate_egress_token(self) -> str:
        """Generate a short-lived JWT with egress grants for API calls."""
        sfu = self._service
        now = int(time.time())
        claims = {
            "iss": sfu.api_key,
            "iat": now,
            "nbf": now,
            "exp": now + _API_TOKEN_TTL_SECONDS,
            "video": {
                "roomRecord": True,
                "roomAdmin": True,
            },
        }
        return jwt.encode(claims, sfu.api_secret, algorithm="HS256")


# ===========================================================================
# Module-level singletons
# ===========================================================================

sfu_service = SFUService()
sfu_recording_service = SFURecordingService(sfu=sfu_service)
