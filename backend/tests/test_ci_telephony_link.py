"""Tests for P7: Telephony call linking."""
import sys, os, uuid, pytest, json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1
USER_ID = 42
SESSION_ID = str(uuid.uuid4())


class TestTelephonyCallLink:

    @pytest.mark.asyncio
    async def test_start_session_stores_telephony_id(self):
        """Test that start_ci_session accepts and stores telephony_call_id."""
        from services.voice_ci_bridge_service import VoiceCIBridgeService
        db = MagicMock()
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)
        session_id = await bridge.start_ci_session(
            context="Refi call",
            client_name="John",
            telephony_call_id="call_ctrl_abc123",
            call_provider="telnyx",
        )
        assert session_id  # UUID returned
        # Verify the INSERT included telephony fields
        call_args = db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        metadata = json.loads(params.get("metadata", "{}"))
        assert metadata.get("telephony_call_id") == "call_ctrl_abc123"
        assert metadata.get("call_provider") == "telnyx"
