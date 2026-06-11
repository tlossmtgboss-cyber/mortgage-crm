# =============================================================================
# PERENNIA AI — Recording Disclosure Audio Endpoint
# =============================================================================
# Serves the recording-disclosure audio used by the Call Intelligence consent
# gate (browser-mode <audio> playback). The previous S3 asset
# (perennia-assets.s3.amazonaws.com/audio/recording-disclosure.wav) is dead,
# so this endpoint generates the audio via Deepgram TTS (Aura) and caches it
# for the process lifetime (plus a /tmp file cache across restarts).
#
# PUBLIC endpoint by design: it is a compliance notice that must be loadable
# directly by an <audio> element on iOS Safari (no Authorization header).
# On any failure (missing DEEPGRAM_API_KEY, TTS error) it returns 404 so the
# frontend's speech-synthesis fallback engages.
# =============================================================================

import hashlib
import logging
import os
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, Response

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/call-intelligence",
    tags=["Call Intelligence Consent"],
)

DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"
DEEPGRAM_TTS_MODEL = "aura-asteria-en"

# Fixed disclosure text — intentionally not user-controllable via query params.
DEFAULT_DISCLOSURE_TEXT = (
    "This call is being recorded for quality and compliance purposes."
)

# Module-level cache: text hash -> audio bytes (Deepgram called once per process).
_audio_cache: Dict[str, bytes] = {}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _tmp_cache_path(text_hash: str) -> str:
    return f"/tmp/disclosure_audio_{text_hash}.mp3"


async def _generate_disclosure_audio(text: str) -> bytes:
    """Generate MP3 disclosure audio via Deepgram TTS (Aura)."""
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY not configured")

    params = {
        "model": DEEPGRAM_TTS_MODEL,
        # MP3 for broad <audio> compatibility, incl. iOS Safari.
        "encoding": "mp3",
    }
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            DEEPGRAM_SPEAK_URL,
            params=params,
            headers=headers,
            json={"text": text},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Deepgram TTS error: {resp.status_code} - {resp.text[:500]}"
            )
        return resp.content


@router.get("/disclosure-audio")
async def get_disclosure_audio() -> Response:
    """
    Serve the recording-disclosure audio (MP3).

    Public (no auth) — loaded directly by an <audio> element during the
    browser-mode consent flow. Returns 404 if audio cannot be generated so
    the frontend falls back to speech synthesis.
    """
    text = DEFAULT_DISCLOSURE_TEXT
    text_hash = _text_hash(text)

    audio_bytes = _audio_cache.get(text_hash)

    # /tmp file cache (survives process workers / restarts on same host)
    if audio_bytes is None:
        tmp_path = _tmp_cache_path(text_hash)
        try:
            if os.path.isfile(tmp_path):
                with open(tmp_path, "rb") as f:
                    audio_bytes = f.read()
                if audio_bytes:
                    _audio_cache[text_hash] = audio_bytes
                else:
                    audio_bytes = None
        except Exception as e:
            logger.warning(f"Disclosure audio /tmp cache read failed: {e}")
            audio_bytes = None

    if audio_bytes is None:
        try:
            audio_bytes = await _generate_disclosure_audio(text)
        except Exception as e:
            logger.warning(f"Disclosure audio TTS generation failed: {e}")
            raise HTTPException(
                status_code=404,
                detail="Disclosure audio unavailable",
            )

        _audio_cache[text_hash] = audio_bytes
        try:
            tmp_path = _tmp_cache_path(text_hash)
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            logger.warning(f"Disclosure audio /tmp cache write failed: {e}")

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
