"""Tests for P6: DiarizationService."""
import sys, os, pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]


class TestDiarizationService:

    def test_diarize_text_with_labels(self):
        from services.call_monitoring.diarization_service import DiarizationService
        svc = DiarizationService()
        transcript = (
            "[User]: Hi, I want to refinance my home\n"
            "[Assistant]: I'd be happy to help. What's your current rate?\n"
            "[User]: It's 6.875 percent\n"
            "[Assistant]: Based on your situation, I can get you around 5.99"
        )
        result = svc.diarize_text(transcript)
        assert result.success is True
        assert result.speaker_count == 2
        assert len(result.segments) == 4
        assert "refinance" in result.segments[0].text

    def test_diarize_text_empty(self):
        from services.call_monitoring.diarization_service import DiarizationService
        svc = DiarizationService()
        result = svc.diarize_text("")
        assert result.success is False

    def test_role_assignment_borrower_patterns(self):
        from services.call_monitoring.diarization_service import DiarizationService
        svc = DiarizationService()
        transcript = (
            "[Speaker 0]: My credit score is 720 and I make $95,000 a year\n"
            "[Speaker 1]: Based on your credit, I'd recommend an FHA loan"
        )
        result = svc.diarize_text(transcript)
        assert result.success is True
        # Speaker 0 should be identified as borrower
        borrower_segments = [s for s in result.segments if s.speaker_role == "borrower"]
        assert len(borrower_segments) >= 1

    def test_format_transcript_labels(self):
        from services.call_monitoring.diarization_service import DiarizationService, SpeakerSegment
        svc = DiarizationService()
        segments = [
            SpeakerSegment(speaker_id=0, speaker_role="loan_officer", text="How can I help?"),
            SpeakerSegment(speaker_id=1, speaker_role="borrower", text="I want to buy a home."),
        ]
        formatted = svc._format_transcript(segments)
        assert "[LO]:" in formatted
        assert "[Borrower]:" in formatted

    @pytest.mark.asyncio
    async def test_diarize_audio_no_api_key(self):
        from services.call_monitoring.diarization_service import DiarizationService
        svc = DiarizationService()
        with patch.dict(os.environ, {}, clear=True):
            result = await svc.diarize_audio("http://example.com/audio.mp3")
        assert result.success is False
        assert "DEEPGRAM" in result.error
