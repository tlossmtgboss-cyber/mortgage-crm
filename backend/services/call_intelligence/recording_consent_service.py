# =============================================================================
# PERENNIA AI — Recording Consent Gate Service (v3 — SYNC)
# =============================================================================
# FIXED: Converted from AsyncSession to sync Session (matching db.py)
# FIXED: All DB writes are real — no more silent no-ops
# FIXED: Telnyx API calls use requests (sync)
# FIXED: Consent state list unified — single import from config
# FIXED: datetime.utcnow() → datetime.now(timezone.utc)
# =============================================================================

import logging
import base64
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict

import requests
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from .recording_consent_config import (
    ConsentRequirement,
    ConsentStatus,
    RecordingConsentConfig,
    get_consent_requirement,
    is_felony_state,
    TWO_PARTY_CONSENT_STATES,
)

logger = logging.getLogger(__name__)

_now = lambda: datetime.now(timezone.utc)


class RecordingConsentService:

    def __init__(self, telnyx_api_key: str, db: Session):
        if db is None:
            raise ValueError("RecordingConsentService requires a DB session.")
        self.telnyx_api_key = telnyx_api_key
        self.telnyx_base = "https://api.telnyx.com/v2"
        self.db = db

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def initiate_consent_gate(
        self,
        call_session_id: str,
        borrower_state: Optional[str],
        org_config: RecordingConsentConfig,
        call_control_id: Optional[str] = None,
        is_browser_mode: bool = False,
    ) -> dict:
        effective_state = borrower_state
        requirement = get_consent_requirement(effective_state, org_config)
        felony = is_felony_state(effective_state) if effective_state else False

        self._update_consent(call_session_id, ConsentStatus.PENDING, {
            "consent_requirement": requirement.value,
            "borrower_state": effective_state,
            "is_two_party_state": (
                effective_state.upper() in TWO_PARTY_CONSENT_STATES
                if effective_state else False
            ),
        })

        # WAIVED
        if requirement == ConsentRequirement.WAIVED:
            self._update_consent(call_session_id, ConsentStatus.SKIPPED)
            return {
                "consent_status": ConsentStatus.SKIPPED.value,
                "requirement": requirement.value,
                "awaiting_webhook": False,
                "is_felony_state": False,
                "is_browser_mode": is_browser_mode,
                "disclosure_audio_url": None,
                "message": "One-party consent state. Disclosure skipped per org settings.",
            }

        # BROWSER MODE
        if is_browser_mode or not call_control_id:
            audio_url = org_config.disclosure_audio_url or org_config.default_disclosure_url
            self._update_consent(call_session_id, ConsentStatus.PLAYING, {
                "consent_disclosure_method": "browser_local",
            })
            return {
                "consent_status": "browser_pending",
                "requirement": requirement.value,
                "awaiting_webhook": False,
                "is_felony_state": felony,
                "is_browser_mode": True,
                "disclosure_audio_url": audio_url,
                # Lets the browser fall back to on-device speech synthesis
                # when the audio asset can't be loaded.
                "disclosure_text": org_config.tts_disclosure_text,
                "message": "Play the disclosure audio through the browser before activating mic.",
            }

        # TELNYX MODE
        success = self._play_disclosure(call_control_id, call_session_id, org_config)

        if success:
            self._update_consent(call_session_id, ConsentStatus.PLAYING, {
                "consent_disclosure_method": "audio_playback",
            })
            return {
                "consent_status": ConsentStatus.PLAYING.value,
                "requirement": requirement.value,
                "awaiting_webhook": True,
                "is_felony_state": felony,
                "is_browser_mode": False,
                "disclosure_audio_url": None,
                "message": "Recording disclosure playing. Waiting for completion.",
            }

        # FAILED
        self._update_consent(call_session_id, ConsentStatus.FAILED)

        if requirement == ConsentRequirement.REQUIRED:
            return {
                "consent_status": ConsentStatus.FAILED.value,
                "requirement": requirement.value,
                "awaiting_webhook": False,
                "is_felony_state": felony,
                "is_browser_mode": False,
                "disclosure_audio_url": None,
                "message": "BLOCKED: Disclosure failed in two-party consent state.",
            }

        return {
            "consent_status": ConsentStatus.FAILED.value,
            "requirement": requirement.value,
            "awaiting_webhook": False,
            "is_felony_state": False,
            "is_browser_mode": False,
            "disclosure_audio_url": None,
            "message": "Disclosure failed. Proceed after verbal disclosure.",
        }

    def handle_playback_ended(self, call_control_id: str, call_session_id: str) -> bool:
        status = self._get_consent_status(call_session_id)
        if status == ConsentStatus.PLAYING:
            self._update_consent(call_session_id, ConsentStatus.DISCLOSED, {
                "consent_disclosed_at": _now(),
            })
            logger.info(f"Consent cleared (Telnyx): {call_session_id}")
            return True
        logger.warning(f"playback.ended but status is {status}")
        return False

    def confirm_browser_disclosure(self, call_session_id: str) -> bool:
        status = self._get_consent_status(call_session_id)
        if status == ConsentStatus.PLAYING:
            self._update_consent(call_session_id, ConsentStatus.DISCLOSED, {
                "consent_disclosed_at": _now(),
                "consent_disclosure_method": "browser_local",
            })
            logger.info(f"Consent cleared (browser): {call_session_id}")
            return True
        return False

    def retry_disclosure(
        self,
        call_session_id: str,
        call_control_id: Optional[str],
        org_config: RecordingConsentConfig,
        is_browser_mode: bool = False,
    ) -> dict:
        self._update_consent(call_session_id, ConsentStatus.PENDING)
        borrower_state = self._get_field(call_session_id, "borrower_state")
        return self.initiate_consent_gate(
            call_session_id, borrower_state, org_config,
            call_control_id, is_browser_mode,
        )

    # -----------------------------------------------------------------
    # Telnyx (sync requests)
    # -----------------------------------------------------------------

    def _play_disclosure(
        self, call_control_id: str, call_session_id: str, org_config: RecordingConsentConfig,
    ) -> bool:
        audio_url = org_config.disclosure_audio_url or org_config.default_disclosure_url

        try:
            resp = requests.post(
                f"{self.telnyx_base}/calls/{call_control_id}/actions/playback_start",
                headers={
                    "Authorization": f"Bearer {self.telnyx_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "audio_url": audio_url,
                    "target_legs": "both",
                    "client_state": self._encode_state(call_session_id),
                    "command_id": str(uuid4()),
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Disclosure playing: call {call_control_id}")
                return True
            logger.warning(f"Telnyx playback_start: {resp.status_code}")
        except requests.RequestException as e:
            logger.error(f"Telnyx playback error: {e}")

        # TTS fallback
        if org_config.fallback_to_tts:
            return self._speak_disclosure(call_control_id, call_session_id, org_config)
        return False

    def _speak_disclosure(
        self, call_control_id: str, call_session_id: str, org_config: RecordingConsentConfig,
    ) -> bool:
        try:
            resp = requests.post(
                f"{self.telnyx_base}/calls/{call_control_id}/actions/speak",
                headers={
                    "Authorization": f"Bearer {self.telnyx_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "payload": org_config.tts_disclosure_text,
                    "payload_type": "text",
                    "voice": org_config.tts_voice,
                    "language": org_config.tts_language,
                    "service_level": "premium",
                    "target_legs": "both",
                    "client_state": self._encode_state(call_session_id),
                    "command_id": str(uuid4()),
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"TTS disclosure: call {call_control_id} (fallback)")
                return True
        except requests.RequestException as e:
            logger.error(f"Telnyx speak error: {e}")
        return False

    # -----------------------------------------------------------------
    # DB (sync — matches SessionLocal)
    # -----------------------------------------------------------------

    def _update_consent(
        self, session_id: str, status: ConsentStatus, extra: Optional[Dict] = None,
    ):
        sets = ["recording_consent_status = :status", "updated_at = :now"]
        params = {"session_id": session_id, "status": status.value, "now": _now()}
        if extra:
            for k, v in extra.items():
                sets.append(f"{k} = :{k}")
                params[k] = v
        self.db.execute(
            sa_text(f"UPDATE call_sessions SET {', '.join(sets)} WHERE id = :session_id"),
            params,
        )
        self.db.commit()

    def _get_consent_status(self, session_id: str) -> Optional[ConsentStatus]:
        row = self.db.execute(
            sa_text("SELECT recording_consent_status FROM call_sessions WHERE id = :id"),
            {"id": session_id},
        ).fetchone()
        return ConsentStatus(row[0]) if row and row[0] else None

    def _get_field(self, session_id: str, field: str) -> Optional[str]:
        row = self.db.execute(
            sa_text(f"SELECT {field} FROM call_sessions WHERE id = :id"),
            {"id": session_id},
        ).fetchone()
        return row[0] if row else None

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _encode_state(session_id: str) -> str:
        return base64.b64encode(session_id.encode()).decode()

    @staticmethod
    def decode_client_state(client_state: str) -> str:
        return base64.b64decode(client_state.encode()).decode()
