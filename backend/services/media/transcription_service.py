"""
Transcription service for mortgage CRM video meeting platform.

Supports two backends:
  - Deepgram (primary): Nova-2 model with speaker diarization via REST API
  - OpenAI Whisper (fallback): Used when Deepgram API key is not configured

Both services normalize output to a standard transcript format with segments,
speaker labels, confidence scores, and word counts.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


# =============================================================================
# Standard transcript format
# =============================================================================
# {
#     "full_text": str,
#     "segments": [
#         {
#             "speaker": int,
#             "start": float,
#             "end": float,
#             "text": str,
#             "confidence": float,
#         }
#     ],
#     "speakers_detected": int,
#     "word_count": int,
#     "confidence": float,
# }
# =============================================================================


class TranscriptionService:
    """Primary transcription service using the Deepgram REST API.

    Supports pre-recorded audio transcription from both local file paths
    and remote URLs. Includes speaker diarization, punctuation, and
    smart formatting.
    """

    DEEPGRAM_BASE_URL = "https://api.deepgram.com/v1/listen"

    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            logger.warning(
                "DEEPGRAM_API_KEY not set -- TranscriptionService will be disabled"
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Return True if the service has a valid API key configured."""
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe_file(
        self,
        audio_file_path_or_url: str,
        language: str = "en",
        model: str = "nova-2",
    ) -> Dict[str, Any]:
        """Transcribe pre-recorded audio via Deepgram.

        Args:
            audio_file_path_or_url: Either a local file path or an HTTP(S) URL
                pointing to the audio source.
            language: BCP-47 language code (default ``"en"``).
            model: Deepgram model identifier (default ``"nova-2"``).

        Returns:
            Standardised transcript dictionary produced by
            :meth:`format_transcript`.

        Raises:
            RuntimeError: If the service is not enabled.
            FileNotFoundError: If a local file path is provided but does not
                exist.
            requests.HTTPError: If the Deepgram API returns a non-2xx status.
        """
        if not self.enabled:
            raise RuntimeError(
                "TranscriptionService is disabled -- DEEPGRAM_API_KEY not set"
            )

        parsed = urlparse(audio_file_path_or_url)
        is_url = parsed.scheme in ("http", "https")

        if is_url:
            return self._transcribe_from_url(
                audio_file_path_or_url, language=language, model=model
            )
        return self._transcribe_from_file(
            audio_file_path_or_url, language=language, model=model
        )

    def transcribe_url(
        self,
        audio_url: str,
        language: str = "en",
        model: str = "nova-2",
    ) -> Dict[str, Any]:
        """Convenience wrapper to transcribe audio from a URL.

        Equivalent to calling ``transcribe_file`` with a URL string.
        """
        return self.transcribe_file(audio_url, language=language, model=model)

    def format_transcript(
        self, deepgram_response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert a raw Deepgram JSON response to the standard format.

        The standard format is a dictionary with keys ``full_text``,
        ``segments``, ``speakers_detected``, ``word_count``, and
        ``confidence``.
        """
        try:
            results = deepgram_response.get("results", {})
            channels = results.get("channels", [])
            if not channels:
                logger.warning("Deepgram response contained no channels")
                return _empty_transcript()

            first_channel = channels[0]
            alternatives = first_channel.get("alternatives", [])
            if not alternatives:
                logger.warning("Deepgram response contained no alternatives")
                return _empty_transcript()

            best = alternatives[0]
            full_text: str = best.get("transcript", "")
            overall_confidence: float = best.get("confidence", 0.0)
            words: List[Dict[str, Any]] = best.get("words", [])

            # Build segments grouped by speaker turns
            segments = _build_segments_from_words(words)

            # Determine number of unique speakers
            speaker_ids = {
                seg["speaker"] for seg in segments if seg["speaker"] is not None
            }
            speakers_detected = len(speaker_ids) if speaker_ids else 1

            word_count = len(full_text.split()) if full_text else 0

            return {
                "full_text": full_text,
                "segments": segments,
                "speakers_detected": speakers_detected,
                "word_count": word_count,
                "confidence": round(overall_confidence, 4),
            }
        except Exception as e:
            logger.exception(f"Failed to format Deepgram response: {e}")
            return _empty_transcript()

    # ------------------------------------------------------------------
    # NLP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_action_items(transcript_text: str) -> List[str]:
        """Extract likely action items from transcript text.

        Uses simple keyword / phrase pattern matching to identify
        sentences that express commitments or tasks.

        Args:
            transcript_text: Plain-text transcript content.

        Returns:
            Deduplicated list of action-item sentences.
        """
        if not transcript_text:
            return []

        action_patterns = [
            r"\bwill\b",
            r"\bneed to\b",
            r"\bneeds to\b",
            r"\bshould\b",
            r"\blet'?s\b",
            r"\baction item\b",
            r"\bfollow up\b",
            r"\bfollow-up\b",
            r"\bschedule\b",
            r"\bset up\b",
            r"\bmake sure\b",
            r"\bdon'?t forget\b",
            r"\btask\b",
            r"\bto-do\b",
            r"\btodo\b",
            r"\bdeadline\b",
            r"\bresponsible for\b",
            r"\bplease\b.*\b(send|submit|provide|prepare|review|update|check)\b",
            r"\bI'?ll\b",
            r"\bwe'?ll\b",
        ]

        combined_pattern = re.compile(
            "|".join(action_patterns), re.IGNORECASE
        )

        # Split into sentences (rough heuristic)
        sentences = re.split(r"(?<=[.!?])\s+", transcript_text.strip())

        action_items: List[str] = []
        seen: set = set()
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            normalised = sentence.lower()
            if normalised in seen:
                continue
            if combined_pattern.search(sentence):
                action_items.append(sentence)
                seen.add(normalised)

        return action_items

    @staticmethod
    def get_key_topics(transcript_text: str) -> List[Dict[str, Any]]:
        """Extract key topics from transcript using frequency analysis.

        Identifies frequently occurring noun-like phrases (simple bigrams
        and significant unigrams) after filtering out stop words.

        Args:
            transcript_text: Plain-text transcript content.

        Returns:
            List of ``{"topic": str, "count": int}`` dicts sorted by
            descending frequency.
        """
        if not transcript_text:
            return []

        stop_words = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "it", "its", "are",
            "was", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "shall", "can", "this", "that", "these",
            "those", "i", "you", "he", "she", "we", "they", "me", "him",
            "her", "us", "them", "my", "your", "his", "our", "their",
            "what", "which", "who", "whom", "how", "when", "where", "why",
            "not", "no", "so", "if", "then", "than", "too", "very",
            "just", "about", "up", "out", "all", "also", "as", "into",
            "more", "some", "there", "here", "other", "well", "only",
            "um", "uh", "yeah", "yes", "no", "oh", "okay", "ok", "like",
            "right", "know", "think", "going", "got", "get", "go",
            "say", "said", "thing", "things", "one", "two", "don't",
            "really", "much", "actually", "kind", "mean", "because",
            "want", "even", "make", "see", "come", "let", "take",
        }

        # Normalise text
        text_clean = re.sub(r"[^a-zA-Z\s]", " ", transcript_text.lower())
        words = [w for w in text_clean.split() if w not in stop_words and len(w) > 2]

        # Unigram frequency
        unigram_counts = Counter(words)

        # Bigram frequency
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        bigram_counts = Counter(bigrams)

        # Combine: keep bigrams with count >= 2, unigrams with count >= 3
        topics: Dict[str, int] = {}
        for bigram, count in bigram_counts.items():
            if count >= 2:
                topics[bigram] = count
        for word, count in unigram_counts.items():
            if count >= 3 and word not in topics:
                # Only add unigram if it is not already part of a top bigram
                already_covered = any(word in bg for bg in topics)
                if not already_covered:
                    topics[word] = count

        sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
        return [
            {"topic": topic, "count": count}
            for topic, count in sorted_topics[:20]
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_query_params(
        self, language: str, model: str
    ) -> Dict[str, str]:
        """Build Deepgram query parameters."""
        return {
            "model": model,
            "language": language,
            "punctuate": "true",
            "diarize": "true",
            "smart_format": "true",
            "utterances": "true",
        }

    def _headers(self, content_type: str = "application/json") -> Dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
        }

    def _transcribe_from_url(
        self, audio_url: str, language: str, model: str
    ) -> Dict[str, Any]:
        """Send a URL-based transcription request to Deepgram."""
        logger.info("Transcribing audio from URL: %s", audio_url)

        params = self._build_query_params(language, model)
        payload = {"url": audio_url}

        response = requests.post(
            self.DEEPGRAM_BASE_URL,
            headers=self._headers("application/json"),
            params=params,
            json=payload,
            timeout=300,
        )
        response.raise_for_status()

        raw = response.json()
        logger.info("Deepgram transcription complete (URL)")
        return self.format_transcript(raw)

    def _transcribe_from_file(
        self, file_path: str, language: str, model: str
    ) -> Dict[str, Any]:
        """Read a local audio file and send bytes to Deepgram."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        logger.info("Transcribing local audio file: %s", file_path)

        # Determine content type from extension
        content_type = _mime_type_for_extension(path.suffix.lower())

        params = self._build_query_params(language, model)
        data = path.read_bytes()

        response = requests.post(
            self.DEEPGRAM_BASE_URL,
            headers=self._headers(content_type),
            params=params,
            data=data,
            timeout=300,
        )
        response.raise_for_status()

        raw = response.json()
        logger.info("Deepgram transcription complete (file)")
        return self.format_transcript(raw)


class WhisperTranscriptionService:
    """Fallback transcription service using OpenAI Whisper API.

    Used when a Deepgram API key is not available but an OpenAI key is.
    """

    WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning(
                "OPENAI_API_KEY not set -- WhisperTranscriptionService will be disabled"
            )

    @property
    def enabled(self) -> bool:
        """Return True if the service has a valid API key configured."""
        return bool(self.api_key)

    def transcribe_file(
        self,
        audio_file_path: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Transcribe a local audio file using OpenAI Whisper.

        Args:
            audio_file_path: Path to the audio file on disk.
            language: ISO-639-1 language code (default ``"en"``).

        Returns:
            Standardised transcript dictionary produced by
            :meth:`format_transcript`.

        Raises:
            RuntimeError: If the service is not enabled.
            FileNotFoundError: If *audio_file_path* does not exist.
            requests.HTTPError: On non-2xx API response.
        """
        if not self.enabled:
            raise RuntimeError(
                "WhisperTranscriptionService is disabled -- OPENAI_API_KEY not set"
            )

        path = Path(audio_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        logger.info("Transcribing with Whisper: %s", audio_file_path)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": "whisper-1",
            "language": language,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }

        with open(path, "rb") as f:
            files = {"file": (path.name, f, _mime_type_for_extension(path.suffix.lower()))}
            response = requests.post(
                self.WHISPER_URL,
                headers=headers,
                data=data,
                files=files,
                timeout=300,
            )

        response.raise_for_status()

        raw = response.json()
        logger.info("Whisper transcription complete")
        return self.format_transcript(raw)

    def format_transcript(
        self, whisper_response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert a Whisper verbose_json response to the standard format.

        Whisper does not natively provide speaker diarization, so all
        segments are assigned ``speaker: 0``.
        """
        try:
            full_text: str = whisper_response.get("text", "")
            raw_segments: List[Dict[str, Any]] = whisper_response.get("segments", [])

            segments = [
                {
                    "speaker": 0,
                    "start": float(seg.get("start", 0.0)),
                    "end": float(seg.get("end", 0.0)),
                    "text": seg.get("text", "").strip(),
                    "confidence": round(
                        float(seg.get("avg_logprob", 0.0)) * -1
                        if seg.get("avg_logprob") is not None
                        else 0.0,
                        4,
                    ),
                }
                for seg in raw_segments
            ]

            word_count = len(full_text.split()) if full_text else 0

            # Approximate overall confidence from segment log-probs
            if raw_segments:
                avg_logprob = sum(
                    seg.get("avg_logprob", 0.0) for seg in raw_segments
                ) / len(raw_segments)
                # Convert log-prob to a 0-1 confidence-like score
                import math
                overall_confidence = round(math.exp(avg_logprob), 4)
            else:
                overall_confidence = 0.0

            return {
                "full_text": full_text,
                "segments": segments,
                "speakers_detected": 1,  # Whisper does not diarize
                "word_count": word_count,
                "confidence": overall_confidence,
            }
        except Exception as e:
            logger.exception(f"Failed to format Whisper response: {e}")
            return _empty_transcript()

    # Expose the same static helpers so callers can use either service
    get_action_items = staticmethod(TranscriptionService.get_action_items)
    get_key_topics = staticmethod(TranscriptionService.get_key_topics)


# =============================================================================
# Module-level helpers
# =============================================================================


def _empty_transcript() -> Dict[str, Any]:
    """Return an empty transcript in the standard format."""
    return {
        "full_text": "",
        "segments": [],
        "speakers_detected": 0,
        "word_count": 0,
        "confidence": 0.0,
    }


def _build_segments_from_words(
    words: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group Deepgram word-level results into speaker-turn segments.

    Each segment represents a contiguous run of words from the same
    speaker.
    """
    if not words:
        return []

    segments: List[Dict[str, Any]] = []
    current_speaker: Optional[int] = words[0].get("speaker")
    current_start: float = float(words[0].get("start", 0.0))
    current_words: List[str] = []
    current_confidences: List[float] = []
    current_end: float = float(words[0].get("end", 0.0))

    for word_info in words:
        speaker = word_info.get("speaker")
        word_text = word_info.get("punctuated_word") or word_info.get("word", "")
        start = float(word_info.get("start", 0.0))
        end = float(word_info.get("end", 0.0))
        confidence = float(word_info.get("confidence", 0.0))

        if speaker != current_speaker:
            # Flush current segment
            if current_words:
                segments.append({
                    "speaker": current_speaker if current_speaker is not None else 0,
                    "start": round(current_start, 3),
                    "end": round(current_end, 3),
                    "text": " ".join(current_words),
                    "confidence": round(
                        sum(current_confidences) / len(current_confidences), 4
                    ),
                })

            # Start new segment
            current_speaker = speaker
            current_start = start
            current_words = []
            current_confidences = []

        current_words.append(word_text)
        current_confidences.append(confidence)
        current_end = end

    # Flush final segment
    if current_words:
        segments.append({
            "speaker": current_speaker if current_speaker is not None else 0,
            "start": round(current_start, 3),
            "end": round(current_end, 3),
            "text": " ".join(current_words),
            "confidence": round(
                sum(current_confidences) / len(current_confidences), 4
            ),
        })

    return segments


def _mime_type_for_extension(ext: str) -> str:
    """Map common audio file extensions to MIME types."""
    mapping = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".aac": "audio/aac",
        ".wma": "audio/x-ms-wma",
    }
    return mapping.get(ext, "audio/wav")


# =============================================================================
# Factory
# =============================================================================


def get_transcription_service() -> Optional[TranscriptionService | WhisperTranscriptionService]:
    """Return the best available transcription service.

    Prefers Deepgram (supports URLs, diarization). Falls back to OpenAI
    Whisper. Returns ``None`` if neither API key is configured.
    """
    deepgram = TranscriptionService()
    if deepgram.enabled:
        logger.info("Transcription service: Deepgram (primary)")
        return deepgram

    whisper = WhisperTranscriptionService()
    if whisper.enabled:
        logger.info("Transcription service: OpenAI Whisper (fallback)")
        return whisper

    logger.warning(
        "No transcription service available -- set DEEPGRAM_API_KEY or OPENAI_API_KEY"
    )
    return None


# Module-level singleton
transcription_service = get_transcription_service()
