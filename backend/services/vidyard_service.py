"""
Vidyard Integration Service - AI Avatar video generation via Vidyard API.

Vidyard AI Avatars allows text-to-video generation with realistic avatars.
This service provides:
- Avatar management (create, list, get)
- Video generation from scripts
- Video status tracking and retrieval
- Webhook handling for async generation

API Documentation: https://developer.vidyard.com/
AI Avatars: https://www.vidyard.com/products/ai-avatars/

Note: AI Avatar API requires Enterprise plan or AI add-on.
Contact Vidyard for API access to AI Avatar generation endpoints.
"""

import os
import httpx
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class VidyardAvatarStatus(str, Enum):
    """Status of a Vidyard AI Avatar."""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class VidyardVideoStatus(str, Enum):
    """Status of a Vidyard AI video generation job."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VidyardLanguage(str, Enum):
    """Supported languages for Vidyard AI Avatars."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    DUTCH = "nl"
    JAPANESE = "ja"
    CHINESE = "zh"
    KOREAN = "ko"
    ARABIC = "ar"
    HINDI = "hi"
    POLISH = "pl"
    SWEDISH = "sv"
    TURKISH = "tr"
    INDONESIAN = "id"
    FILIPINO = "fil"
    ROMANIAN = "ro"
    CZECH = "cs"
    GREEK = "el"
    FINNISH = "fi"
    DANISH = "da"
    UKRAINIAN = "uk"
    BULGARIAN = "bg"
    CROATIAN = "hr"
    MALAY = "ms"
    SLOVAK = "sk"
    TAMIL = "ta"


class VidyardService:
    """
    Service for Vidyard AI Avatar video generation.

    Features:
    - Create and manage AI avatars from training videos
    - Generate videos from text scripts (up to 1000 chars / ~1 min)
    - Multi-language support (25+ languages)
    - Async video generation with webhooks

    Usage:
        service = VidyardService()

        # Create avatar from training video
        avatar = await service.create_avatar(
            name="Sales Rep",
            training_video_url="https://..."
        )

        # Generate video from script
        video = await service.generate_video(
            avatar_id=avatar["id"],
            script="Hello, I'm excited to show you..."
        )
    """

    # API endpoints
    BASE_URL = "https://api.vidyard.com/dashboard/v1"
    AI_AVATAR_URL = "https://api.vidyard.com/ai-avatars/v1"  # Placeholder - confirm with Vidyard

    # Limits
    MAX_SCRIPT_LENGTH = 1000  # characters
    MAX_VIDEO_DURATION = 60  # seconds (~1 min)

    def __init__(
        self,
        api_token: Optional[str] = None,
        ai_avatar_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        """
        Initialize Vidyard service.

        Args:
            api_token: Vidyard Dashboard API token
            ai_avatar_token: Vidyard AI Avatar API token (if different)
            webhook_url: URL for async video generation callbacks
        """
        self.api_token = api_token or os.getenv("VIDYARD_API_TOKEN")
        self.ai_avatar_token = ai_avatar_token or os.getenv("VIDYARD_AI_AVATAR_TOKEN", self.api_token)
        self.webhook_url = webhook_url or os.getenv("VIDYARD_WEBHOOK_URL")

        if not self.api_token:
            logger.warning("VIDYARD_API_TOKEN not set - Vidyard integration will not work")

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"Content-Type": "application/json"}
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    # =========================================================================
    # Health & Status
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Check Vidyard API connectivity."""
        if not self.api_token:
            return {
                "status": "not_configured",
                "message": "VIDYARD_API_TOKEN not set"
            }

        try:
            response = await self.client.get(
                f"{self.BASE_URL}/players",
                params={"auth_token": self.api_token, "per_page": 1}
            )

            if response.status_code == 200:
                return {"status": "healthy", "message": "Vidyard API connected"}
            elif response.status_code == 401:
                return {"status": "unauthorized", "message": "Invalid API token"}
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.exception("Vidyard health check failed")
            return {"status": "error", "message": "Internal server error"}

    # =========================================================================
    # Avatar Management
    # =========================================================================

    async def list_avatars(self) -> Dict[str, Any]:
        """
        List available AI avatars.

        Returns:
            Dict with 'avatars' list and 'total' count

        Note: This endpoint may require AI Avatar API access.
        Falls back to returning empty list if not available.
        """
        if not self.ai_avatar_token:
            return {"avatars": [], "total": 0, "message": "AI Avatar API not configured"}

        try:
            response = await self.client.get(
                f"{self.AI_AVATAR_URL}/avatars",
                params={"auth_token": self.ai_avatar_token}
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "avatars": data.get("avatars", []),
                    "total": data.get("total", len(data.get("avatars", [])))
                }
            elif response.status_code == 404:
                # AI Avatar endpoint not available - use stock avatars
                return await self._get_stock_avatars()
            else:
                logger.warning(f"Failed to list avatars: {response.status_code}")
                return {"avatars": [], "total": 0, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.exception("Failed to list Vidyard avatars")
            return {"avatars": [], "total": 0, "error": "Internal server error"}

    async def _get_stock_avatars(self) -> Dict[str, Any]:
        """Get list of stock avatars (free tier)."""
        # Stock avatars available on free tier
        stock_avatars = [
            {"id": "stock_1", "name": "Alex", "type": "stock", "gender": "male"},
            {"id": "stock_2", "name": "Sarah", "type": "stock", "gender": "female"},
            {"id": "stock_3", "name": "Michael", "type": "stock", "gender": "male"},
            {"id": "stock_4", "name": "Emma", "type": "stock", "gender": "female"},
        ]
        return {"avatars": stock_avatars, "total": len(stock_avatars), "type": "stock"}

    async def get_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        Get avatar details by ID.

        Args:
            avatar_id: Vidyard avatar ID

        Returns:
            Avatar details dict or None
        """
        if not self.ai_avatar_token:
            return None

        try:
            response = await self.client.get(
                f"{self.AI_AVATAR_URL}/avatars/{avatar_id}",
                params={"auth_token": self.ai_avatar_token}
            )

            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.exception(f"Failed to get avatar {avatar_id}")
            return None

    async def create_avatar(
        self,
        name: str,
        training_video_url: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a custom AI avatar from training video.

        Args:
            name: Avatar name
            training_video_url: URL to 90-second training video
            description: Optional description

        Returns:
            Created avatar details

        Note: Training takes 3-4 hours to complete.
        Requires Video Agent add-on or Enterprise plan.
        """
        if not self.ai_avatar_token:
            return {
                "error": "AI Avatar API not configured",
                "message": "Set VIDYARD_AI_AVATAR_TOKEN or contact Vidyard for API access"
            }

        try:
            payload = {
                "name": name,
                "training_video_url": training_video_url,
                "webhook_url": self.webhook_url,
            }
            if description:
                payload["description"] = description

            response = await self.client.post(
                f"{self.AI_AVATAR_URL}/avatars",
                params={"auth_token": self.ai_avatar_token},
                json=payload
            )

            if response.status_code in (200, 201):
                data = response.json()
                logger.info(f"Created Vidyard avatar: {data.get('id')}")
                return {
                    "id": data.get("id"),
                    "name": name,
                    "status": VidyardAvatarStatus.PROCESSING.value,
                    "message": "Avatar training started. This takes 3-4 hours.",
                    "data": data
                }
            else:
                error_msg = response.text
                logger.error(f"Failed to create avatar: {response.status_code} - {error_msg}")
                return {"error": f"HTTP {response.status_code}", "message": error_msg}
        except Exception as e:
            logger.exception("Failed to create Vidyard avatar")
            return {"error": "Internal server error"}

    async def delete_avatar(self, avatar_id: str) -> bool:
        """Delete a custom avatar."""
        if not self.ai_avatar_token:
            return False

        try:
            response = await self.client.delete(
                f"{self.AI_AVATAR_URL}/avatars/{avatar_id}",
                params={"auth_token": self.ai_avatar_token}
            )
            return response.status_code in (200, 204)
        except Exception as e:
            logger.exception(f"Failed to delete avatar {avatar_id}")
            return False

    # =========================================================================
    # Video Generation
    # =========================================================================

    async def generate_video(
        self,
        avatar_id: str,
        script: str,
        language: VidyardLanguage = VidyardLanguage.ENGLISH,
        title: Optional[str] = None,
        background_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate AI avatar video from script.

        Args:
            avatar_id: ID of avatar to use
            script: Text script (max 1000 chars, ~1 min video)
            language: Script language
            title: Optional video title
            background_url: Optional custom background image/video URL

        Returns:
            Video generation job details

        Note: Generation takes ~10 min per minute of video.
        """
        if not self.ai_avatar_token:
            return {
                "error": "AI Avatar API not configured",
                "message": "Set VIDYARD_AI_AVATAR_TOKEN to enable video generation"
            }

        # Validate script length
        if len(script) > self.MAX_SCRIPT_LENGTH:
            return {
                "error": "Script too long",
                "message": f"Script must be {self.MAX_SCRIPT_LENGTH} characters or less",
                "length": len(script),
                "max_length": self.MAX_SCRIPT_LENGTH
            }

        # Warn about line breaks
        if "\n" in script:
            logger.warning("Script contains line breaks - may affect avatar speech quality")

        try:
            payload = {
                "avatar_id": avatar_id,
                "script": script,
                "language": language.value,
                "webhook_url": self.webhook_url,
            }
            if title:
                payload["title"] = title
            if background_url:
                payload["background_url"] = background_url

            response = await self.client.post(
                f"{self.AI_AVATAR_URL}/videos",
                params={"auth_token": self.ai_avatar_token},
                json=payload
            )

            if response.status_code in (200, 201, 202):
                data = response.json()
                job_id = data.get("job_id") or data.get("id")

                logger.info(f"Started Vidyard video generation: {job_id}")

                return {
                    "job_id": job_id,
                    "status": VidyardVideoStatus.QUEUED.value,
                    "message": "Video generation started. Takes ~10 min per minute of video.",
                    "estimated_duration_seconds": self._estimate_duration(script),
                    "data": data
                }
            else:
                error_msg = response.text
                logger.error(f"Failed to generate video: {response.status_code} - {error_msg}")
                return {"error": f"HTTP {response.status_code}", "message": error_msg}
        except Exception as e:
            logger.exception("Failed to generate Vidyard video")
            return {"error": "Internal server error"}

    async def get_video_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get video generation job status.

        Args:
            job_id: Video generation job ID

        Returns:
            Job status with video URL when complete
        """
        if not self.ai_avatar_token:
            return {"error": "AI Avatar API not configured"}

        try:
            response = await self.client.get(
                f"{self.AI_AVATAR_URL}/videos/{job_id}",
                params={"auth_token": self.ai_avatar_token}
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "job_id": job_id,
                    "status": data.get("status", "unknown"),
                    "progress": data.get("progress", 0),
                    "video_url": data.get("video_url"),
                    "player_url": data.get("player_url"),
                    "thumbnail_url": data.get("thumbnail_url"),
                    "duration_seconds": data.get("duration"),
                    "data": data
                }
            elif response.status_code == 404:
                return {"job_id": job_id, "status": "not_found"}
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.exception(f"Failed to get video status {job_id}")
            return {"error": "Internal server error"}

    async def list_videos(
        self,
        page: int = 1,
        per_page: int = 25,
        avatar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List generated AI videos.

        Args:
            page: Page number (1-indexed)
            per_page: Results per page
            avatar_id: Filter by avatar

        Returns:
            Paginated video list
        """
        if not self.ai_avatar_token:
            return {"videos": [], "total": 0}

        try:
            params = {
                "auth_token": self.ai_avatar_token,
                "page": page,
                "per_page": per_page,
            }
            if avatar_id:
                params["avatar_id"] = avatar_id

            response = await self.client.get(
                f"{self.AI_AVATAR_URL}/videos",
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "videos": data.get("videos", []),
                    "total": data.get("total", 0),
                    "page": page,
                    "per_page": per_page
                }
            return {"videos": [], "total": 0}
        except Exception as e:
            logger.exception("Failed to list Vidyard videos")
            return {"videos": [], "total": 0, "error": "Internal server error"}

    # =========================================================================
    # Standard Video API (Dashboard API)
    # =========================================================================

    async def upload_video(
        self,
        video_url: str,
        name: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a video to Vidyard (standard API).

        Args:
            video_url: URL of video file to upload
            name: Video title
            description: Optional description

        Returns:
            Created video details
        """
        if not self.api_token:
            return {"error": "API token not configured"}

        try:
            payload = {
                "upload_url": video_url,
                "name": name,
            }
            if description:
                payload["description"] = description
            if self.webhook_url:
                payload["webhook_url"] = self.webhook_url

            response = await self.client.post(
                f"{self.BASE_URL}/videos",
                params={"auth_token": self.api_token},
                json=payload
            )

            if response.status_code == 201:
                data = response.json()
                return {
                    "id": data.get("id"),
                    "uuid": data.get("uuid"),
                    "name": name,
                    "status": "processing",
                    "data": data
                }
            else:
                return {"error": f"HTTP {response.status_code}", "message": response.text}
        except Exception as e:
            logger.exception("Failed to upload video")
            return {"error": "Internal server error"}

    async def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video details by ID."""
        if not self.api_token:
            return None

        try:
            response = await self.client.get(
                f"{self.BASE_URL}/videos/{video_id}",
                params={"auth_token": self.api_token}
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.exception(f"Failed to get video {video_id}")
            return None

    # =========================================================================
    # Webhooks
    # =========================================================================

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Vidyard webhook callback.

        Args:
            payload: Webhook payload from Vidyard

        Returns:
            Processed event data
        """
        event_type = payload.get("event_type") or payload.get("type")

        if event_type == "avatar.training.completed":
            return {
                "event": "avatar_ready",
                "avatar_id": payload.get("avatar_id"),
                "status": VidyardAvatarStatus.READY.value
            }
        elif event_type == "avatar.training.failed":
            return {
                "event": "avatar_failed",
                "avatar_id": payload.get("avatar_id"),
                "status": VidyardAvatarStatus.FAILED.value,
                "error": payload.get("error")
            }
        elif event_type == "video.generation.completed":
            return {
                "event": "video_ready",
                "job_id": payload.get("job_id"),
                "video_url": payload.get("video_url"),
                "player_url": payload.get("player_url"),
                "status": VidyardVideoStatus.COMPLETED.value
            }
        elif event_type == "video.generation.failed":
            return {
                "event": "video_failed",
                "job_id": payload.get("job_id"),
                "status": VidyardVideoStatus.FAILED.value,
                "error": payload.get("error")
            }
        else:
            logger.info(f"Unknown Vidyard webhook event: {event_type}")
            return {"event": "unknown", "raw": payload}

    # =========================================================================
    # Utilities
    # =========================================================================

    def _estimate_duration(self, script: str) -> int:
        """Estimate video duration from script length."""
        # ~150 words per minute, ~5 chars per word
        words = len(script) / 5
        minutes = words / 150
        return int(minutes * 60)

    def validate_script(self, script: str) -> Dict[str, Any]:
        """
        Validate script for AI video generation.

        Returns validation result with warnings.
        """
        issues = []
        warnings = []

        if not script or not script.strip():
            issues.append("Script cannot be empty")

        if len(script) > self.MAX_SCRIPT_LENGTH:
            issues.append(f"Script exceeds {self.MAX_SCRIPT_LENGTH} character limit")

        if "\n" in script:
            warnings.append("Line breaks may cause filler words (umm, uhh) in speech")

        if len(script) < 20:
            warnings.append("Very short scripts may produce awkward results")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "length": len(script),
            "max_length": self.MAX_SCRIPT_LENGTH,
            "estimated_duration_seconds": self._estimate_duration(script)
        }


# Singleton instance
_vidyard_service: Optional[VidyardService] = None


def get_vidyard_service() -> VidyardService:
    """Get or create Vidyard service singleton."""
    global _vidyard_service
    if _vidyard_service is None:
        _vidyard_service = VidyardService()
    return _vidyard_service
