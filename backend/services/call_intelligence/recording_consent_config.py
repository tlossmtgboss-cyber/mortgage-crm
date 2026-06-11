# =============================================================================
# PERENNIA AI — Recording Consent Configuration (v3 — UNIFIED)
# =============================================================================
# SINGLE SOURCE OF TRUTH for two-party consent states.
# Import TWO_PARTY_CONSENT_STATES from HERE only — nowhere else.
# Delete the duplicate list in recording_consent.py after import.
# =============================================================================

import os
from enum import Enum
from typing import Optional
from pydantic import BaseModel


# Two-party (all-party) consent states — CANONICAL LIST
# Source: Digital Media Law Project / Reporters Committee, verified 2025
# Note: Delaware is ONE-PARTY (11 Del. C. § 2402) — removed from prior versions
# that incorrectly included it. If state law changes, update HERE only.
TWO_PARTY_CONSENT_STATES = frozenset({
    "CA",  # Cal. Penal Code § 632 — FELONY
    "CT",  # Conn. Gen. Stat. § 52-570d
    "FL",  # Fla. Stat. § 934.03 — FELONY
    "IL",  # 720 ILCS 5/14-2 — FELONY
    "MD",  # Md. Code, Cts. & Jud. Proc. § 10-402 — FELONY
    "MA",  # Mass. Gen. Laws ch. 272, § 99 — FELONY
    "MI",  # Mich. Comp. Laws § 750.539c
    "MT",  # Mont. Code Ann. § 45-8-213
    "NV",  # Nev. Rev. Stat. § 200.620
    "NH",  # N.H. Rev. Stat. Ann. § 570-A:2
    "OR",  # Or. Rev. Stat. § 165.540
    "PA",  # 18 Pa. Cons. Stat. § 5703 — FELONY
    "WA",  # Wash. Rev. Code § 9.73.030
})

FELONY_STATES = frozenset({"CA", "FL", "IL", "MD", "MA", "PA"})


class ConsentRequirement(str, Enum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    WAIVED = "waived"


class ConsentStatus(str, Enum):
    PENDING = "pending"
    PLAYING = "playing"
    DISCLOSED = "disclosed"
    SKIPPED = "skipped"
    FAILED = "failed"


class RecordingConsentConfig(BaseModel):
    always_disclose: bool = True
    disclosure_audio_url: Optional[str] = None
    # Served by backend/routes/disclosure_audio_routes.py (TTS-generated, cached).
    # Override with DISCLOSURE_AUDIO_URL env var if hosting the asset elsewhere.
    default_disclosure_url: str = os.getenv(
        "DISCLOSURE_AUDIO_URL",
        "https://api.perenniaai.com/api/v1/call-intelligence/disclosure-audio",
    )
    fallback_to_tts: bool = True
    tts_disclosure_text: str = "This call is now being recorded for quality and compliance purposes."
    tts_voice: str = "female"
    tts_language: str = "en-US"


def get_consent_requirement(
    borrower_state: Optional[str], org_config: RecordingConsentConfig,
) -> ConsentRequirement:
    if borrower_state and borrower_state.upper() in TWO_PARTY_CONSENT_STATES:
        return ConsentRequirement.REQUIRED
    if org_config.always_disclose:
        return ConsentRequirement.RECOMMENDED
    return ConsentRequirement.WAIVED


def is_felony_state(state: str) -> bool:
    return state.upper() in FELONY_STATES if state else False
