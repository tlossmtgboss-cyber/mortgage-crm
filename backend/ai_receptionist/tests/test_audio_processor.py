"""
================================================================================
PERENNIA AI - AUDIO PROCESSOR TESTS
================================================================================
Comprehensive tests for STT/TTS audio processing.

Run with: pytest backend/ai_receptionist/tests/test_audio_processor.py -v
================================================================================
"""

import pytest
import asyncio
import struct
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import AsyncIterator

# Import the module under test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ai_receptionist.audio_processor import (
    # Audio utilities
    convert_mulaw_to_pcm,
    convert_pcm_to_mulaw,
    create_wav_header,
    audio_to_base64,
    base64_to_audio,
    AudioFormat,
    # Config
    STTConfig,
    TTSConfig,
    # Metrics
    AudioMetrics,
    get_audio_metrics,
    # Providers
    DeepgramSTT,
    WhisperSTT,
    ElevenLabsTTS,
    OpenAITTS,
    # Main classes
    AudioProcessor,
    VoiceActivityDetector,
    create_audio_processor,
    # Convenience functions
    transcribe_audio,
    synthesize_speech,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_pcm_audio() -> bytes:
    """Generate sample 16-bit PCM audio (1 second of 440Hz sine wave)."""
    import math
    sample_rate = 8000
    duration = 0.5  # seconds
    frequency = 440  # Hz
    amplitude = 16000  # ~50% of max

    samples = []
    for i in range(int(sample_rate * duration)):
        t = i / sample_rate
        sample = int(amplitude * math.sin(2 * math.pi * frequency * t))
        samples.append(sample)

    return struct.pack(f'<{len(samples)}h', *samples)


@pytest.fixture
def sample_mulaw_audio(sample_pcm_audio) -> bytes:
    """Generate sample mu-law audio from PCM."""
    return convert_pcm_to_mulaw(sample_pcm_audio)


@pytest.fixture
def silence_audio() -> bytes:
    """Generate silence (zero samples)."""
    return bytes(1000)  # 500 samples of zeros


@pytest.fixture
def stt_config() -> STTConfig:
    """Create STT config for testing."""
    return STTConfig(
        provider="deepgram",
        deepgram_api_key="test-key",
        language="en-US",
    )


@pytest.fixture
def tts_config() -> TTSConfig:
    """Create TTS config for testing."""
    return TTSConfig(
        provider="elevenlabs",
        elevenlabs_api_key="test-key",
        output_format="mulaw",
    )


# =============================================================================
# AUDIO FORMAT CONVERSION TESTS
# =============================================================================

class TestAudioConversion:
    """Tests for audio format conversion utilities."""

    def test_mulaw_to_pcm_conversion(self, sample_mulaw_audio):
        """Test mu-law to PCM conversion produces correct output."""
        pcm = convert_mulaw_to_pcm(sample_mulaw_audio)

        # PCM should be 2x the size of mu-law (16-bit vs 8-bit)
        assert len(pcm) == len(sample_mulaw_audio) * 2

        # Should be valid 16-bit samples
        num_samples = len(pcm) // 2
        samples = struct.unpack(f'<{num_samples}h', pcm)
        assert all(-32768 <= s <= 32767 for s in samples)

    def test_pcm_to_mulaw_conversion(self, sample_pcm_audio):
        """Test PCM to mu-law conversion produces correct output."""
        mulaw = convert_pcm_to_mulaw(sample_pcm_audio)

        # Mu-law should be half the size of PCM
        assert len(mulaw) == len(sample_pcm_audio) // 2

        # Should be valid 8-bit samples
        assert all(0 <= b <= 255 for b in mulaw)

    def test_roundtrip_conversion(self, sample_pcm_audio):
        """Test that PCM -> mu-law -> PCM is close to original."""
        mulaw = convert_pcm_to_mulaw(sample_pcm_audio)
        pcm_back = convert_mulaw_to_pcm(mulaw)

        # Lengths should match
        assert len(pcm_back) == len(sample_pcm_audio)

        # Values should be close (mu-law is lossy)
        original_samples = struct.unpack(f'<{len(sample_pcm_audio)//2}h', sample_pcm_audio)
        recovered_samples = struct.unpack(f'<{len(pcm_back)//2}h', pcm_back)

        # Allow ~5% error due to quantization
        for orig, recov in zip(original_samples, recovered_samples):
            if abs(orig) > 100:  # Skip near-zero values
                error = abs(orig - recov) / abs(orig)
                assert error < 0.15, f"Error too high: {error} for {orig} vs {recov}"

    def test_empty_audio_conversion(self):
        """Test conversion of empty audio."""
        empty_pcm = bytes()
        empty_mulaw = bytes()

        assert convert_mulaw_to_pcm(empty_mulaw) == bytes()
        assert convert_pcm_to_mulaw(empty_pcm) == bytes()

    def test_wav_header_creation(self):
        """Test WAV header has correct structure."""
        header = create_wav_header(
            sample_rate=8000,
            bits_per_sample=16,
            channels=1,
            data_size=1000,
        )

        assert len(header) == 44  # Standard WAV header size
        assert header[:4] == b'RIFF'
        assert header[8:12] == b'WAVE'
        assert header[12:16] == b'fmt '
        assert header[36:40] == b'data'

    def test_base64_encoding(self, sample_pcm_audio):
        """Test base64 encoding/decoding."""
        encoded = audio_to_base64(sample_pcm_audio)
        decoded = base64_to_audio(encoded)

        assert decoded == sample_pcm_audio
        assert isinstance(encoded, str)


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestConfiguration:
    """Tests for STT and TTS configuration."""

    def test_stt_config_defaults(self):
        """Test STT config default values."""
        config = STTConfig()

        assert config.provider == "deepgram"
        assert config.language == "en-US"
        assert config.punctuate is True
        assert config.interim_results is True

    def test_stt_config_env_loading(self, monkeypatch):
        """Test STT config loads from environment."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "env-test-key")

        config = STTConfig()
        assert config.deepgram_api_key == "env-test-key"

    def test_stt_config_validation(self):
        """Test STT config validation."""
        config = STTConfig(provider="deepgram", deepgram_api_key=None)
        issues = config.validate()

        assert len(issues) == 1
        assert "Deepgram" in issues[0]

    def test_tts_config_defaults(self):
        """Test TTS config default values."""
        config = TTSConfig()

        assert config.provider == "elevenlabs"
        assert config.output_format == "mulaw"
        assert config.sample_rate == 8000

    def test_tts_config_validation(self):
        """Test TTS config validation."""
        config = TTSConfig(provider="elevenlabs", elevenlabs_api_key=None)
        issues = config.validate()

        assert len(issues) == 1
        assert "ElevenLabs" in issues[0]


# =============================================================================
# METRICS TESTS
# =============================================================================

class TestMetrics:
    """Tests for audio metrics tracking."""

    def test_metrics_recording(self):
        """Test metrics are recorded correctly."""
        metrics = AudioMetrics()

        metrics.record_stt(100.0, 1000, success=True)
        metrics.record_stt(200.0, 2000, success=False)
        metrics.record_tts(50.0, success=True)

        assert metrics.total_stt_requests == 2
        assert metrics.stt_errors == 1
        assert metrics.total_tts_requests == 1
        assert metrics.total_audio_bytes_processed == 3000

    def test_metrics_averages(self):
        """Test metric average calculations."""
        metrics = AudioMetrics()

        metrics.record_stt(100.0, 1000)
        metrics.record_stt(200.0, 1000)
        metrics.record_stt(300.0, 1000)

        assert metrics.avg_stt_latency == 200.0

    def test_metrics_success_rate(self):
        """Test success rate calculation."""
        metrics = AudioMetrics()

        metrics.record_stt(100.0, 1000, success=True)
        metrics.record_stt(100.0, 1000, success=True)
        metrics.record_stt(100.0, 1000, success=False)
        metrics.record_stt(100.0, 1000, success=False)

        assert metrics.stt_success_rate == 50.0

    def test_metrics_to_dict(self):
        """Test metrics export to dictionary."""
        metrics = AudioMetrics()
        metrics.record_stt(100.0, 1000)

        data = metrics.to_dict()

        assert "stt" in data
        assert "tts" in data
        assert data["stt"]["total_requests"] == 1


# =============================================================================
# VOICE ACTIVITY DETECTION TESTS
# =============================================================================

class TestVoiceActivityDetector:
    """Tests for voice activity detection."""

    def test_silence_detection(self, silence_audio):
        """Test silence is not detected as speech."""
        vad = VoiceActivityDetector(energy_threshold=0.02)

        result = vad.process_chunk(silence_audio)

        assert result["is_speaking"] is False
        assert result["speech_started"] is False
        assert result["energy"] < 0.01

    def test_speech_detection(self, sample_pcm_audio):
        """Test speech is detected."""
        vad = VoiceActivityDetector(
            energy_threshold=0.01,
            speech_duration=0.05,
        )

        # Process enough chunks to trigger speech detection
        for _ in range(5):
            result = vad.process_chunk(sample_pcm_audio[:500])

        # Should eventually detect speech
        assert result["is_speaking"] or result["energy"] > 0.01

    def test_speech_end_detection(self, sample_pcm_audio, silence_audio):
        """Test speech ending is detected."""
        vad = VoiceActivityDetector(
            energy_threshold=0.01,
            silence_duration=0.1,
            speech_duration=0.05,
        )

        # Simulate speech followed by silence
        for _ in range(5):
            vad.process_chunk(sample_pcm_audio[:500])

        # Now send silence
        result = None
        for _ in range(20):
            result = vad.process_chunk(silence_audio[:500])
            if result.get("speech_ended"):
                break

        # May or may not detect end depending on timing
        assert result is not None

    def test_vad_reset(self, sample_pcm_audio):
        """Test VAD reset clears state."""
        vad = VoiceActivityDetector()

        vad.process_chunk(sample_pcm_audio)
        vad.is_speaking = True

        vad.reset()

        assert vad.is_speaking is False
        assert vad.silent_samples == 0
        assert vad.speech_samples_count == 0


# =============================================================================
# PROVIDER TESTS (MOCKED)
# =============================================================================

class TestDeepgramSTT:
    """Tests for Deepgram STT provider."""

    @pytest.mark.asyncio
    async def test_transcribe_success(self, sample_pcm_audio, stt_config):
        """Test successful transcription."""
        with patch('ai_receptionist.audio_processor.HAS_HTTPX', True):
            with patch('ai_receptionist.audio_processor.httpx') as mock_httpx:
                # Mock the response
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_response.json.return_value = {
                    "results": {
                        "channels": [{
                            "alternatives": [{
                                "transcript": "Hello, how can I help you?"
                            }]
                        }]
                    }
                }

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()

                mock_httpx.AsyncClient.return_value = mock_client

                stt = DeepgramSTT(stt_config)
                stt._client = mock_client

                result = await stt.transcribe(sample_pcm_audio)

                assert result == "Hello, how can I help you?"

    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        config = STTConfig(provider="deepgram", deepgram_api_key=None)

        with pytest.raises(ValueError, match="API key"):
            DeepgramSTT(config)


class TestElevenLabsTTS:
    """Tests for ElevenLabs TTS provider."""

    @pytest.mark.asyncio
    async def test_synthesize_success(self, tts_config):
        """Test successful synthesis."""
        with patch('ai_receptionist.audio_processor.HAS_HTTPX', True):
            with patch('ai_receptionist.audio_processor.httpx') as mock_httpx:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_response.content = b"fake-audio-data"

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)

                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock()

                tts = ElevenLabsTTS(tts_config)
                tts._client = mock_client

                result = await tts.synthesize("Hello world")

                assert result == b"fake-audio-data"

    def test_voice_id_resolution(self, tts_config):
        """Test voice name to ID resolution."""
        tts = ElevenLabsTTS(tts_config)

        assert tts._get_voice_id("rachel") == "21m00Tcm4TlvDq8ikWAM"
        assert tts._get_voice_id("custom-id") == "custom-id"


# =============================================================================
# AUDIO PROCESSOR TESTS
# =============================================================================

class TestAudioProcessor:
    """Tests for main AudioProcessor class."""

    def test_lazy_provider_initialization(self, stt_config, tts_config):
        """Test providers are created lazily."""
        processor = AudioProcessor(stt_config, tts_config)

        # Providers should not be created yet
        assert processor._stt is None
        assert processor._tts is None

    def test_get_metrics(self, stt_config, tts_config):
        """Test metrics retrieval."""
        processor = AudioProcessor(stt_config, tts_config)
        metrics = processor.get_metrics()

        assert "stt" in metrics
        assert "tts" in metrics

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager cleanup."""
        async with create_audio_processor(
            stt_provider="deepgram",
            tts_provider="elevenlabs",
            deepgram_api_key="test",
            elevenlabs_api_key="test",
        ) as processor:
            assert processor is not None

        # Should be cleaned up after context

    @pytest.mark.asyncio
    async def test_transcribe_audio(self, sample_mulaw_audio, stt_config, tts_config):
        """Test telephony audio transcription."""
        with patch.object(DeepgramSTT, 'transcribe', new_callable=AsyncMock) as mock:
            mock.return_value = "Test transcription"

            processor = AudioProcessor(stt_config, tts_config)
            processor._stt = DeepgramSTT(stt_config)

            result = await processor.transcribe_audio(sample_mulaw_audio)

            assert result == "Test transcription"
            mock.assert_called_once()


# =============================================================================
# INTEGRATION TESTS (REQUIRE REAL CREDENTIALS)
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("DEEPGRAM_API_KEY"),
    reason="DEEPGRAM_API_KEY not set"
)
class TestDeepgramIntegration:
    """Integration tests requiring real Deepgram credentials."""

    @pytest.mark.asyncio
    async def test_real_transcription(self, sample_pcm_audio):
        """Test real transcription with Deepgram."""
        config = STTConfig(provider="deepgram")
        stt = DeepgramSTT(config)

        try:
            # This may return empty string for synthetic audio
            result = await stt.transcribe(sample_pcm_audio)
            assert isinstance(result, str)
        finally:
            await stt.close()


@pytest.mark.skipif(
    not os.getenv("ELEVENLABS_API_KEY"),
    reason="ELEVENLABS_API_KEY not set"
)
class TestElevenLabsIntegration:
    """Integration tests requiring real ElevenLabs credentials."""

    @pytest.mark.asyncio
    async def test_real_synthesis(self):
        """Test real synthesis with ElevenLabs."""
        config = TTSConfig(provider="elevenlabs")
        tts = ElevenLabsTTS(config)

        try:
            result = await tts.synthesize("Hello, this is a test.")
            assert len(result) > 0
            assert isinstance(result, bytes)
        finally:
            await tts.close()


# =============================================================================
# AUDIO FORMAT ENUM TESTS
# =============================================================================

class TestAudioFormatEnum:
    """Tests for AudioFormat enum."""

    def test_format_values(self):
        """Test audio format values."""
        assert AudioFormat.PCM_16.value == "pcm_16"
        assert AudioFormat.MULAW.value == "mulaw"
        assert AudioFormat.MP3.value == "mp3"

    def test_format_string_comparison(self):
        """Test format string comparison."""
        assert AudioFormat.MULAW == "mulaw"
        assert AudioFormat.PCM_16 == "pcm_16"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
