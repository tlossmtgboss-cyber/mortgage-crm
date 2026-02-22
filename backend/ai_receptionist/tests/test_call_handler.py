"""
================================================================================
PERENNIA AI - CALL HANDLER TESTS
================================================================================
Tests for Telnyx stream handling and conversation management.

Run with: pytest backend/ai_receptionist/tests/test_call_handler.py -v
================================================================================
"""

import pytest
import asyncio
import json
import os
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import the module under test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ai_receptionist.call_handler import (
    CallState,
    CallDirection,
    CallContext,
    TelnyxStreamHandler,
    RealtimeConversation,
    create_call_handler,
    handle_voice_stream_websocket,
)
from ai_receptionist.audio_processor import (
    AudioProcessor,
    STTConfig,
    TTSConfig,
    audio_to_base64,
    base64_to_audio,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def call_context() -> CallContext:
    """Create a sample call context."""
    return CallContext(
        call_sid="CA123456",
        stream_sid="ST789",
        direction=CallDirection.INBOUND,
        caller_number="+15551234567",
        called_number="+15559876543",
    )


@pytest.fixture
def mock_audio_processor():
    """Create a mock audio processor."""
    processor = Mock(spec=AudioProcessor)
    processor.transcribe_audio = AsyncMock(return_value="Hello")
    processor.synthesize_for_telephony = AsyncMock(return_value=b"audio-data")
    processor.vad = Mock()
    return processor


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.iter_text = Mock(return_value=AsyncMock())
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def telnyx_start_message() -> str:
    """Create a Telnyx start message."""
    return json.dumps({
        "event": "start",
        "start": {
            "callSid": "CA123456",
            "streamSid": "ST789",
            "customParameters": {
                "From": "+15551234567",
                "To": "+15559876543",
            },
        },
    })


@pytest.fixture
def telnyx_media_message() -> str:
    """Create a Telnyx media message."""
    # Small chunk of silence as mu-law
    audio_data = bytes([0x7F] * 100)  # mu-law silence
    payload = audio_to_base64(audio_data)

    return json.dumps({
        "event": "media",
        "media": {
            "payload": payload,
        },
    })


@pytest.fixture
def telnyx_stop_message() -> str:
    """Create a Telnyx stop message."""
    return json.dumps({
        "event": "stop",
    })


# =============================================================================
# CALL CONTEXT TESTS
# =============================================================================

class TestCallContext:
    """Tests for CallContext class."""

    def test_initial_state(self, call_context):
        """Test initial context state."""
        assert call_context.state == CallState.CONNECTING
        assert call_context.call_sid == "CA123456"
        assert call_context.direction == CallDirection.INBOUND

    def test_add_message(self, call_context):
        """Test adding messages to history."""
        call_context.add_message("user", "Hello")
        call_context.add_message("assistant", "Hi there!")

        assert len(call_context.conversation_history) == 2
        assert call_context.conversation_history[0]["role"] == "user"
        assert call_context.total_turns == 2

    def test_get_duration(self, call_context):
        """Test duration calculation."""
        # Just started
        duration = call_context.get_duration_seconds()
        assert duration >= 0

        # After ending
        call_context.end_time = datetime.now(timezone.utc)
        duration = call_context.get_duration_seconds()
        assert duration >= 0

    def test_to_dict(self, call_context):
        """Test dictionary export."""
        call_context.add_message("user", "Test")

        data = call_context.to_dict()

        assert data["call_sid"] == "CA123456"
        assert data["direction"] == "inbound"
        assert len(data["conversation_history"]) == 1


# =============================================================================
# CALL STATE TESTS
# =============================================================================

class TestCallState:
    """Tests for CallState enum."""

    def test_state_values(self):
        """Test all state values exist."""
        states = [
            CallState.CONNECTING,
            CallState.CONNECTED,
            CallState.GREETING,
            CallState.LISTENING,
            CallState.PROCESSING,
            CallState.SPEAKING,
            CallState.TRANSFERRING,
            CallState.ENDING,
            CallState.ENDED,
            CallState.ERROR,
        ]

        assert len(states) == 10

    def test_state_string_value(self):
        """Test state string values."""
        assert CallState.LISTENING.value == "listening"
        assert CallState.PROCESSING.value == "processing"


# =============================================================================
# TELNYX STREAM HANDLER TESTS
# =============================================================================

class TestTelnyxStreamHandler:
    """Tests for TelnyxStreamHandler class."""

    @pytest.mark.asyncio
    async def test_handle_start_message(
        self,
        mock_audio_processor,
        telnyx_start_message,
    ):
        """Test handling Telnyx start event."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        response = await handler.handle_message(telnyx_start_message)

        assert handler.context is not None
        assert handler.context.call_sid == "CA123456"
        assert handler.context.caller_number == "+15551234567"
        assert handler.context.state == CallState.GREETING

    @pytest.mark.asyncio
    async def test_handle_stop_message(
        self,
        mock_audio_processor,
        telnyx_start_message,
        telnyx_stop_message,
    ):
        """Test handling Telnyx stop event."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        # First start the call
        await handler.handle_message(telnyx_start_message)

        # Then stop it
        await handler.handle_message(telnyx_stop_message)

        assert handler.context.state == CallState.ENDED
        assert handler.context.end_time is not None

    @pytest.mark.asyncio
    async def test_handle_media_message(
        self,
        mock_audio_processor,
        telnyx_start_message,
        telnyx_media_message,
    ):
        """Test handling Telnyx media event."""
        # Setup VAD mock
        mock_audio_processor.vad = Mock()

        handler = TelnyxStreamHandler(mock_audio_processor)
        handler.vad = Mock()
        handler.vad.process_chunk = Mock(return_value={
            "is_speaking": False,
            "speech_started": False,
            "speech_ended": False,
            "energy": 0.01,
        })

        # Start call first
        await handler.handle_message(telnyx_start_message)

        # Process media
        response = await handler.handle_message(telnyx_media_message)

        # Should have processed audio
        handler.vad.process_chunk.assert_called()

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self, mock_audio_processor):
        """Test handling invalid JSON."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        response = await handler.handle_message("not valid json")

        assert response is None

    @pytest.mark.asyncio
    async def test_handle_unknown_event(self, mock_audio_processor):
        """Test handling unknown event type."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        response = await handler.handle_message(json.dumps({
            "event": "unknown_event",
        }))

        assert response is None

    @pytest.mark.asyncio
    async def test_callbacks_triggered(
        self,
        mock_audio_processor,
        telnyx_start_message,
    ):
        """Test that callbacks are triggered."""
        state_callback = AsyncMock()

        handler = TelnyxStreamHandler(
            mock_audio_processor,
            on_state_change=state_callback,
        )

        await handler.handle_message(telnyx_start_message)

        # Should have called state change for GREETING
        state_callback.assert_called()

    @pytest.mark.asyncio
    async def test_create_media_response(
        self,
        mock_audio_processor,
        telnyx_start_message,
    ):
        """Test media response creation."""
        handler = TelnyxStreamHandler(mock_audio_processor)
        await handler.handle_message(telnyx_start_message)

        audio = b"test-audio"
        response = handler._create_media_response(audio)

        assert response["event"] == "media"
        assert response["streamSid"] == "ST789"
        assert "payload" in response["media"]
        assert response["mark"]["name"] == "ai_response_end"

    @pytest.mark.asyncio
    async def test_get_response_text(self, mock_audio_processor):
        """Test response text generation."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        # Test rate question
        response = await handler._get_response_text("What are your rates?")
        assert "rate" in response.lower()

        # Test refinance question
        response = await handler._get_response_text("I want to refinance")
        assert "refinanc" in response.lower()

        # Test appointment request
        response = await handler._get_response_text("Can I schedule an appointment?")
        assert "appointment" in response.lower() or "schedule" in response.lower()

        # Test transfer request
        response = await handler._get_response_text("Can I talk to a human?")
        assert "transfer" in response.lower()

        # Test default
        response = await handler._get_response_text("Something random")
        assert len(response) > 0


# =============================================================================
# REALTIME CONVERSATION TESTS
# =============================================================================

class TestRealtimeConversation:
    """Tests for RealtimeConversation class."""

    def test_initialization(self, mock_websocket, mock_audio_processor):
        """Test conversation initialization."""
        conversation = RealtimeConversation(
            websocket=mock_websocket,
            audio_processor=mock_audio_processor,
        )

        assert conversation.websocket == mock_websocket
        assert conversation.processor == mock_audio_processor
        assert conversation.handler is not None

    @pytest.mark.asyncio
    async def test_send_audio(self, mock_websocket, mock_audio_processor):
        """Test sending audio through conversation."""
        conversation = RealtimeConversation(
            websocket=mock_websocket,
            audio_processor=mock_audio_processor,
        )

        # Setup context
        conversation.handler.context = CallContext(
            call_sid="CA123",
            stream_sid="ST456",
        )

        await conversation.send_audio(b"test-audio")

        mock_websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self, mock_websocket, mock_audio_processor):
        """Test stopping conversation."""
        conversation = RealtimeConversation(
            websocket=mock_websocket,
            audio_processor=mock_audio_processor,
        )

        conversation._running = True
        await conversation.stop()

        assert conversation._running is False


# =============================================================================
# INTEGRATION HELPER TESTS
# =============================================================================

class TestIntegrationHelpers:
    """Tests for integration helper functions."""

    @pytest.mark.asyncio
    async def test_create_call_handler_context_manager(self, mock_websocket):
        """Test call handler context manager."""
        with patch('ai_receptionist.call_handler.AudioProcessor') as MockProcessor:
            MockProcessor.return_value.close = AsyncMock()

            async with create_call_handler(
                mock_websocket,
                stt_provider="deepgram",
                tts_provider="elevenlabs",
            ) as conversation:
                assert conversation is not None

            # Cleanup should be called
            MockProcessor.return_value.close.assert_called_once()


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_media_before_start(self, mock_audio_processor, telnyx_media_message):
        """Test media received before start event."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        # Media before start should not crash
        response = await handler.handle_message(telnyx_media_message)

        assert response is None
        assert handler.context is None

    @pytest.mark.asyncio
    async def test_multiple_start_events(
        self,
        mock_audio_processor,
        telnyx_start_message,
    ):
        """Test handling multiple start events."""
        handler = TelnyxStreamHandler(mock_audio_processor)

        # First start
        await handler.handle_message(telnyx_start_message)
        first_context = handler.context

        # Second start (should create new context)
        await handler.handle_message(telnyx_start_message)
        second_context = handler.context

        # Should be different contexts
        assert first_context != second_context

    @pytest.mark.asyncio
    async def test_echo_prevention(
        self,
        mock_audio_processor,
        telnyx_start_message,
        telnyx_media_message,
    ):
        """Test that audio is not processed while AI is speaking."""
        handler = TelnyxStreamHandler(mock_audio_processor)
        handler.vad = Mock()
        handler.vad.process_chunk = Mock(return_value={
            "is_speaking": True,
            "speech_started": True,
            "speech_ended": False,
            "energy": 0.5,
        })

        # Start call
        await handler.handle_message(telnyx_start_message)

        # Mark AI as speaking
        handler.context.is_ai_speaking = True

        # Process media - should be ignored
        response = await handler.handle_message(telnyx_media_message)

        # Should not process (echo prevention)
        assert response is None


# =============================================================================
# STATE TRANSITION TESTS
# =============================================================================

class TestStateTransitions:
    """Tests for call state transitions."""

    @pytest.mark.asyncio
    async def test_state_flow(self, mock_audio_processor, telnyx_start_message):
        """Test normal state flow."""
        states_seen = []

        async def track_state(state, context):
            states_seen.append(state)

        handler = TelnyxStreamHandler(
            mock_audio_processor,
            on_state_change=track_state,
        )

        # Start call
        await handler.handle_message(telnyx_start_message)

        # Should have transitioned to GREETING
        assert CallState.GREETING in states_seen

    @pytest.mark.asyncio
    async def test_state_on_stop(
        self,
        mock_audio_processor,
        telnyx_start_message,
        telnyx_stop_message,
    ):
        """Test state on call stop."""
        states_seen = []

        async def track_state(state, context):
            states_seen.append(state)

        handler = TelnyxStreamHandler(
            mock_audio_processor,
            on_state_change=track_state,
        )

        await handler.handle_message(telnyx_start_message)
        await handler.handle_message(telnyx_stop_message)

        assert CallState.ENDED in states_seen


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
