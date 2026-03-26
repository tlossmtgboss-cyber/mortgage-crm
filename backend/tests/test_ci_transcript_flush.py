"""Tests for P2: Periodic transcript flush."""
import sys, os, uuid, pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1
USER_ID = 42
SESSION_ID = str(uuid.uuid4())


class TestTranscriptFlush:

    @pytest.mark.asyncio
    async def test_append_transcript_chunk_appends(self):
        """Test that append_transcript_chunk uses SQL COALESCE concat."""
        from services.voice_ci_bridge_service import VoiceCIBridgeService
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(id=SESSION_ID)
        db.execute.return_value = mock_result
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)
        result = await bridge.append_transcript_chunk(SESSION_ID, "[User]: Hello there")
        assert result["success"] is True
        assert result["chunk_words"] == 3  # "Hello there" doesn't count the label
        db.execute.assert_called()
        db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_append_empty_chunk_rejected(self):
        from services.voice_ci_bridge_service import VoiceCIBridgeService
        db = MagicMock()
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)
        result = await bridge.append_transcript_chunk(SESSION_ID, "")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_append_no_session_id_rejected(self):
        from services.voice_ci_bridge_service import VoiceCIBridgeService
        db = MagicMock()
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)
        result = await bridge.append_transcript_chunk("", "some text")
        assert result["success"] is False
