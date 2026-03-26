"""Tests for P1: CallAudioBridge media stream service."""
import sys, os, uuid, pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1
SESSION_ID = str(uuid.uuid4())


class TestCallAudioBridge:

    @pytest.mark.asyncio
    @patch("services.call_monitoring.media_stream_bridge.text")
    async def test_attach_telephony_call_stores_metadata(self, mock_text):
        from services.call_monitoring.media_stream_bridge import CallAudioBridge
        db = MagicMock()
        bridge = CallAudioBridge(db, ORG_ID)
        result = await bridge.attach_telephony_call(SESSION_ID, "call_123", "telnyx")
        assert result["success"] is True
        assert result["provider"] == "telnyx"
        db.execute.assert_called_once()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_telnyx_recording_missing_key(self):
        from services.call_monitoring.media_stream_bridge import CallAudioBridge
        db = MagicMock()
        bridge = CallAudioBridge(db, ORG_ID)
        with patch.dict(os.environ, {}, clear=True):
            result = await bridge._fetch_telnyx_recording("call_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_twilio_recording_missing_creds(self):
        from services.call_monitoring.media_stream_bridge import CallAudioBridge
        db = MagicMock()
        bridge = CallAudioBridge(db, ORG_ID)
        with patch.dict(os.environ, {}, clear=True):
            result = await bridge._fetch_twilio_recording("CA123")
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_recording_no_api_key(self):
        from services.call_monitoring.media_stream_bridge import CallAudioBridge
        db = MagicMock()
        bridge = CallAudioBridge(db, ORG_ID)
        with patch.dict(os.environ, {}, clear=True):
            result = await bridge.transcribe_recording("http://example.com/audio.mp3", SESSION_ID)
        assert result["success"] is False
        assert "DEEPGRAM" in result["error"]

    @pytest.mark.asyncio
    async def test_process_post_call_no_metadata(self):
        from services.call_monitoring.media_stream_bridge import CallAudioBridge
        db = MagicMock()
        mock_row = MagicMock()
        mock_row.metadata = None
        db.execute.return_value.fetchone.return_value = mock_row
        bridge = CallAudioBridge(db, ORG_ID)
        result = await bridge.process_post_call(SESSION_ID)
        assert result["success"] is False
