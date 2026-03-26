"""
Speaker Diarization Service — separates speakers in call transcripts.

Supports two modes:
1. Audio diarization: Send audio to Deepgram with diarize=true (best quality)
2. Text diarization: Post-process an existing transcript to infer speaker changes
   based on conversational patterns (fallback when audio unavailable)

Speaker roles are assigned by analyzing conversational patterns:
- The person asking questions about rates/loans is likely the borrower
- The person providing answers/guidance is likely the LO
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """A segment of speech attributed to one speaker."""
    speaker_id: int           # 0, 1, 2, ...
    speaker_role: str         # "loan_officer", "borrower", "unknown"
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    confidence: float = 0.0


@dataclass
class DiarizationResult:
    """Result of diarization processing."""
    success: bool
    segments: List[SpeakerSegment] = field(default_factory=list)
    speaker_count: int = 0
    formatted_transcript: str = ""
    error: Optional[str] = None


# Patterns that suggest a borrower is speaking
_BORROWER_PATTERNS = [
    r"my credit score",
    r"i make \$?[\d,]+",
    r"my income",
    r"we'?re looking to",
    r"i want to (buy|refinance|refi)",
    r"how much (can i|do i) (qualify|afford)",
    r"what('s| is) my (rate|payment)",
    r"i currently (owe|have|pay)",
    r"my (house|home|property|condo)",
    r"we (need|want) to (move|sell|buy)",
    r"my (employer|job|work) is",
    r"i('ve| have) been (at|with)",
]

# Patterns that suggest an LO is speaking
_LO_PATTERNS = [
    r"(based on|looking at) (your|the) (credit|income|numbers)",
    r"(let me|i'?ll) (pull|check|look|run)",
    r"(your|the) (rate|payment|dti|ltv) (would|will|is|comes)",
    r"i('?d| would) recommend",
    r"(we|i) (can|could) (get|offer|do)",
    r"(conventional|fha|va|usda|jumbo) (loan|program|option)",
    r"(down payment|closing costs?) (would|will|of)",
    r"(we|i) need (your|the|some) (documents?|paperwork|paystubs?|w-?2|bank)",
    r"(i'?ll|let me) send (you|over|the)",
    r"pre-?approv(al|ed)",
]


class DiarizationService:
    """Handles speaker diarization for call intelligence."""

    async def diarize_audio(
        self,
        audio_url: str,
        language: str = "en",
    ) -> DiarizationResult:
        """
        Diarize audio via Deepgram API with speaker separation.
        This is the preferred path — produces the best results.
        """
        deepgram_key = os.getenv("DEEPGRAM_API_KEY")
        if not deepgram_key:
            return DiarizationResult(
                success=False,
                error="DEEPGRAM_API_KEY not configured",
            )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    headers={
                        "Authorization": f"Token {deepgram_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "url": audio_url,
                        "model": "nova-2",
                        "language": language,
                        "diarize": True,
                        "punctuate": True,
                        "utterances": True,
                        "smart_format": True,
                    },
                )
                response.raise_for_status()
                data = response.json()

            utterances = data.get("results", {}).get("utterances", [])
            if not utterances:
                return DiarizationResult(
                    success=False,
                    error="No utterances returned from Deepgram",
                )

            # Convert to SpeakerSegments
            segments = []
            speaker_ids = set()
            for utt in utterances:
                speaker_id = utt.get("speaker", 0)
                speaker_ids.add(speaker_id)
                segments.append(SpeakerSegment(
                    speaker_id=speaker_id,
                    speaker_role="unknown",
                    text=utt.get("transcript", ""),
                    start_ms=int(utt.get("start", 0) * 1000),
                    end_ms=int(utt.get("end", 0) * 1000),
                    confidence=utt.get("confidence", 0.0),
                ))

            # Assign roles
            segments = self._assign_roles(segments)

            # Format transcript
            formatted = self._format_transcript(segments)

            return DiarizationResult(
                success=True,
                segments=segments,
                speaker_count=len(speaker_ids),
                formatted_transcript=formatted,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Deepgram diarization error: {e.response.status_code}")
            return DiarizationResult(success=False, error=f"API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return DiarizationResult(success=False, error=str(e))

    def diarize_text(
        self,
        transcript: str,
        known_speakers: Optional[List[Dict[str, str]]] = None,
    ) -> DiarizationResult:
        """
        Fallback: infer speaker changes from an existing text transcript.

        Uses conversational pattern matching to guess who is the LO vs borrower.
        Less accurate than audio diarization but works when we only have text.
        """
        if not transcript or not transcript.strip():
            return DiarizationResult(success=False, error="Empty transcript")

        # If transcript already has speaker labels (e.g., [User]: ..., [Assistant]: ...)
        labeled_pattern = re.compile(r'^\[(User|Assistant|Speaker \d+)\]:\s*(.+)', re.MULTILINE)
        labeled_matches = labeled_pattern.findall(transcript)

        if labeled_matches:
            segments = []
            for label, text_content in labeled_matches:
                if label == "User":
                    speaker_id = 0
                elif label == "Assistant":
                    speaker_id = 1
                else:
                    try:
                        speaker_id = int(label.split()[-1])
                    except (ValueError, IndexError):
                        speaker_id = 0

                segments.append(SpeakerSegment(
                    speaker_id=speaker_id,
                    speaker_role="unknown",
                    text=text_content.strip(),
                ))

            segments = self._assign_roles(segments)
            formatted = self._format_transcript(segments)

            return DiarizationResult(
                success=True,
                segments=segments,
                speaker_count=len(set(s.speaker_id for s in segments)),
                formatted_transcript=formatted,
            )

        # No labels — split by sentences and try to cluster by content patterns
        sentences = re.split(r'(?<=[.!?])\s+', transcript.strip())
        segments = []
        current_speaker = 0

        for sentence in sentences:
            if not sentence.strip():
                continue

            # Check if this sounds like a borrower or LO
            borrower_score = sum(
                1 for p in _BORROWER_PATTERNS if re.search(p, sentence, re.IGNORECASE)
            )
            lo_score = sum(
                1 for p in _LO_PATTERNS if re.search(p, sentence, re.IGNORECASE)
            )

            if borrower_score > lo_score:
                speaker = 0  # borrower
            elif lo_score > borrower_score:
                speaker = 1  # LO
            else:
                speaker = current_speaker  # Same as previous

            # Detect speaker change
            if segments and speaker != current_speaker:
                current_speaker = speaker

            segments.append(SpeakerSegment(
                speaker_id=speaker,
                speaker_role="borrower" if speaker == 0 else "loan_officer",
                text=sentence.strip(),
                confidence=0.3 + (0.3 * max(borrower_score, lo_score)),
            ))
            current_speaker = speaker

        # Merge consecutive segments from same speaker
        merged = self._merge_consecutive(segments)
        formatted = self._format_transcript(merged)

        return DiarizationResult(
            success=True,
            segments=merged,
            speaker_count=len(set(s.speaker_id for s in merged)),
            formatted_transcript=formatted,
        )

    def _assign_roles(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Assign speaker roles (borrower/LO) based on content patterns."""
        speaker_scores: Dict[int, Dict[str, int]] = {}

        for seg in segments:
            if seg.speaker_id not in speaker_scores:
                speaker_scores[seg.speaker_id] = {"borrower": 0, "lo": 0}

            for p in _BORROWER_PATTERNS:
                if re.search(p, seg.text, re.IGNORECASE):
                    speaker_scores[seg.speaker_id]["borrower"] += 1

            for p in _LO_PATTERNS:
                if re.search(p, seg.text, re.IGNORECASE):
                    speaker_scores[seg.speaker_id]["lo"] += 1

        # Assign roles based on aggregate scores
        role_map = {}
        for speaker_id, scores in speaker_scores.items():
            if scores["borrower"] > scores["lo"]:
                role_map[speaker_id] = "borrower"
            elif scores["lo"] > scores["borrower"]:
                role_map[speaker_id] = "loan_officer"
            else:
                role_map[speaker_id] = "unknown"

        # If we have exactly 2 speakers and can't distinguish, assign by speaking order
        # (LO usually speaks first in a professional call)
        if len(role_map) == 2:
            ids = sorted(role_map.keys())
            if all(v == "unknown" for v in role_map.values()):
                role_map[ids[0]] = "loan_officer"
                role_map[ids[1]] = "borrower"

        for seg in segments:
            seg.speaker_role = role_map.get(seg.speaker_id, "unknown")

        return segments

    def _merge_consecutive(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Merge consecutive segments from the same speaker."""
        if not segments:
            return []

        merged = [segments[0]]
        for seg in segments[1:]:
            if seg.speaker_id == merged[-1].speaker_id:
                merged[-1].text += " " + seg.text
                merged[-1].end_ms = seg.end_ms
                merged[-1].confidence = max(merged[-1].confidence, seg.confidence)
            else:
                merged.append(seg)
        return merged

    def _format_transcript(self, segments: List[SpeakerSegment]) -> str:
        """Format segments into a readable labeled transcript."""
        lines = []
        role_labels = {
            "loan_officer": "LO",
            "borrower": "Borrower",
            "unknown": "Speaker",
        }
        for seg in segments:
            label = role_labels.get(seg.speaker_role, f"Speaker {seg.speaker_id}")
            lines.append(f"[{label}]: {seg.text}")
        return "\n".join(lines)
