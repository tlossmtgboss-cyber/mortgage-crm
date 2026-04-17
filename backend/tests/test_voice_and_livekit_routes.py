"""
Tests for mobile voice endpoints and LiveKit token provisioning.

Covers:
  - GET  /api/v1/mobile-voice/calls          (list voice call history)
  - GET  /api/v1/mobile-voice/calls/{uuid}    (call detail with transcript)
  - GET  /api/v1/mobile-voice/analytics       (voice usage KPIs)
  - POST /api/v1/mobile-voice/sessions/save   (persist SSE voice session)
  - POST /api/v1/livekit/token                (LiveKit room token)
  - GET  /api/v1/livekit/health               (LiveKit health check)
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import text


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def voice_session_table(db_session):
    """Create voice_call_sessions table for testing."""
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS voice_call_sessions (
            id SERIAL PRIMARY KEY,
            session_uuid TEXT NOT NULL,
            organization_id INTEGER,
            user_id INTEGER NOT NULL,
            direction TEXT DEFAULT 'inbound',
            status TEXT DEFAULT 'completed',
            voice_mode TEXT DEFAULT 'sse',
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            duration_seconds INTEGER,
            summary TEXT,
            sentiment TEXT,
            outcome TEXT,
            tools_executed JSONB DEFAULT '[]'::jsonb,
            tool_count INTEGER DEFAULT 0,
            transcript JSONB DEFAULT '[]'::jsonb,
            message_count INTEGER DEFAULT 0,
            stt_provider TEXT,
            tts_provider TEXT,
            tts_voice_id TEXT,
            lead_id INTEGER,
            loan_id INTEGER,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))
    db_session.commit()
    return db_session


@pytest.fixture
def sample_voice_sessions(voice_session_table):
    """Insert sample voice sessions for testing."""
    db = voice_session_table
    now = datetime.now(timezone.utc)

    sessions = [
        {
            "uuid": str(uuid.uuid4()),
            "status": "completed",
            "started": now - timedelta(hours=2),
            "ended": now - timedelta(hours=1, minutes=55),
            "duration": 300,
            "summary": "User asked about pipeline status and loan updates",
            "sentiment": "positive",
            "outcome": "info_provided",
            "tools": json.dumps([{"tool": "search_pipeline", "timestamp": now.isoformat()}]),
            "tool_count": 1,
            "transcript": json.dumps([
                {"role": "user", "content": "How's my pipeline looking?"},
                {"role": "assistant", "content": "You have 12 active loans..."},
            ]),
            "msg_count": 2,
        },
        {
            "uuid": str(uuid.uuid4()),
            "status": "completed",
            "started": now - timedelta(hours=5),
            "ended": now - timedelta(hours=4, minutes=50),
            "duration": 600,
            "summary": "Sent a text message to borrower John Smith",
            "sentiment": "neutral",
            "outcome": "action_taken",
            "tools": json.dumps([
                {"tool": "send_sms", "recipient": "John Smith"},
                {"tool": "create_task", "title": "Follow up"},
            ]),
            "tool_count": 2,
            "transcript": json.dumps([
                {"role": "user", "content": "Text John Smith that his docs are ready"},
                {"role": "assistant", "content": "Done — I sent that text to John Smith."},
                {"role": "user", "content": "Create a follow-up task for next week"},
                {"role": "assistant", "content": "Task created: Follow up with John Smith."},
            ]),
            "msg_count": 4,
        },
        {
            "uuid": str(uuid.uuid4()),
            "status": "abandoned",
            "started": now - timedelta(hours=8),
            "ended": None,
            "duration": 10,
            "summary": None,
            "sentiment": None,
            "outcome": "abandoned",
            "tools": json.dumps([]),
            "tool_count": 0,
            "transcript": json.dumps([{"role": "user", "content": "Hello"}]),
            "msg_count": 1,
        },
    ]

    for s in sessions:
        db.execute(text("""
            INSERT INTO voice_call_sessions
                (session_uuid, user_id, status, voice_mode,
                 started_at, ended_at, duration_seconds,
                 summary, sentiment, outcome,
                 tools_executed, tool_count, transcript, message_count,
                 stt_provider, tts_provider)
            VALUES
                (:uuid, 1, :status, 'sse',
                 :started, :ended, :duration,
                 :summary, :sentiment, :outcome,
                 :tools::jsonb, :tool_count, :transcript::jsonb, :msg_count,
                 'deepgram', 'elevenlabs')
        """), {
            "uuid": s["uuid"],
            "status": s["status"],
            "started": s["started"],
            "ended": s["ended"],
            "duration": s["duration"],
            "summary": s["summary"],
            "sentiment": s["sentiment"],
            "outcome": s["outcome"],
            "tools": s["tools"],
            "tool_count": s["tool_count"],
            "transcript": s["transcript"],
            "msg_count": s["msg_count"],
        })

    db.commit()
    return sessions


# =============================================================================
# GET /api/v1/mobile-voice/calls — List voice call history
# =============================================================================

class TestListVoiceCalls:
    def test_returns_paginated_calls(self, authenticated_client, sample_voice_sessions):
        resp = authenticated_client.get("/api/v1/mobile-voice/calls")
        assert resp.status_code == 200
        data = resp.json()
        assert "calls" in data
        assert "total" in data
        assert data["total"] == 3
        assert len(data["calls"]) == 3

    def test_pagination_limit_offset(self, authenticated_client, sample_voice_sessions):
        resp = authenticated_client.get("/api/v1/mobile-voice/calls?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["calls"]) == 1
        assert data["total"] == 3

    def test_filter_by_status(self, authenticated_client, sample_voice_sessions):
        resp = authenticated_client.get("/api/v1/mobile-voice/calls?status=abandoned")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["calls"][0]["status"] == "abandoned"

    def test_empty_result(self, authenticated_client, voice_session_table):
        resp = authenticated_client.get("/api/v1/mobile-voice/calls")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["calls"] == []

    def test_calls_ordered_by_started_at_desc(self, authenticated_client, sample_voice_sessions):
        resp = authenticated_client.get("/api/v1/mobile-voice/calls")
        calls = resp.json()["calls"]
        # Most recent first
        started_times = [c["started_at"] for c in calls if c["started_at"]]
        assert started_times == sorted(started_times, reverse=True)


# =============================================================================
# GET /api/v1/mobile-voice/calls/{uuid} — Call detail
# =============================================================================

class TestGetVoiceCallDetail:
    def test_returns_full_detail(self, authenticated_client, sample_voice_sessions):
        session_uuid = sample_voice_sessions[0]["uuid"]
        resp = authenticated_client.get(f"/api/v1/mobile-voice/calls/{session_uuid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_uuid"] == session_uuid
        assert data["transcript"] is not None
        assert data["tools_executed"] is not None
        assert data["summary"] is not None

    def test_not_found(self, authenticated_client, voice_session_table):
        resp = authenticated_client.get("/api/v1/mobile-voice/calls/nonexistent-uuid")
        assert resp.status_code == 404


# =============================================================================
# GET /api/v1/mobile-voice/analytics — Voice analytics
# =============================================================================

class TestVoiceAnalytics:
    def test_returns_analytics(self, authenticated_client, sample_voice_sessions):
        resp = authenticated_client.get("/api/v1/mobile-voice/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_calls"] == 3
        assert data["completed_calls"] == 2
        assert data["abandoned_calls"] == 1
        assert "sentiment" in data
        assert "outcomes" in data
        assert "daily_volume" in data

    def test_analytics_with_days_param(self, authenticated_client, sample_voice_sessions):
        resp = authenticated_client.get("/api/v1/mobile-voice/analytics?days=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 1

    def test_empty_analytics(self, authenticated_client, voice_session_table):
        resp = authenticated_client.get("/api/v1/mobile-voice/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_calls"] == 0
        assert data["avg_duration_seconds"] == 0


# =============================================================================
# POST /api/v1/mobile-voice/sessions/save — Save SSE voice session
# =============================================================================

class TestSaveVoiceSession:
    @patch("mobile_voice_routes._generate_call_summary", new_callable=AsyncMock)
    def test_saves_session(self, mock_summary, authenticated_client, voice_session_table):
        mock_summary.return_value = {
            "summary": "Test conversation summary",
            "sentiment": "positive",
            "outcome": "info_provided",
        }

        resp = authenticated_client.post("/api/v1/mobile-voice/sessions/save", json={
            "session_id": "aria-voice-test-123",
            "transcript": [
                {"role": "user", "content": "How's my pipeline?"},
                {"role": "assistant", "content": "You have 5 active loans."},
            ],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "voice_mode": "sse",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "session_uuid" in data

    def test_rejects_empty_transcript(self, authenticated_client, voice_session_table):
        resp = authenticated_client.post("/api/v1/mobile-voice/sessions/save", json={
            "session_id": "test-empty",
            "transcript": [],
            "voice_mode": "sse",
        })
        assert resp.status_code == 400

    @patch("mobile_voice_routes._generate_call_summary", new_callable=AsyncMock)
    def test_duplicate_session_returns_already_saved(self, mock_summary, authenticated_client, voice_session_table):
        """Duplicate session_id should return success without re-saving."""
        mock_summary.return_value = {
            "summary": "First save",
            "sentiment": "neutral",
            "outcome": "info_provided",
        }

        payload = {
            "session_id": "aria-voice-dup-test",
            "transcript": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            "voice_mode": "sse",
        }

        # First save
        resp1 = authenticated_client.post("/api/v1/mobile-voice/sessions/save", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True

        # Duplicate save — should succeed without calling summary again
        resp2 = authenticated_client.post("/api/v1/mobile-voice/sessions/save", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True
        assert "already saved" in resp2.json().get("message", "").lower()

    @patch("mobile_voice_routes._generate_call_summary", new_callable=AsyncMock)
    def test_saves_session_with_summary_failure(self, mock_summary, authenticated_client, voice_session_table):
        """Session should still save even if AI summary generation fails."""
        mock_summary.side_effect = Exception("LLM unavailable")

        resp = authenticated_client.post("/api/v1/mobile-voice/sessions/save", json={
            "session_id": "aria-voice-fail-test",
            "transcript": [
                {"role": "user", "content": "Testing"},
                {"role": "assistant", "content": "Response"},
            ],
            "voice_mode": "sse",
        })
        # Should still succeed — summary failure is non-fatal
        assert resp.status_code == 200


# =============================================================================
# GET /api/v1/mobile-voice/calls — Edge cases
# =============================================================================

class TestVoiceCallsEdgeCases:
    def test_invalid_limit(self, authenticated_client, voice_session_table):
        """limit=0 should still return 200 (clamped to min 1) or 400/422 if validated."""
        resp = authenticated_client.get("/api/v1/mobile-voice/calls?limit=0")
        assert resp.status_code == 200  # route clamps via min(limit, 100); 0 returns empty

    def test_negative_offset(self, authenticated_client, voice_session_table):
        """Negative offset should be handled gracefully."""
        resp = authenticated_client.get("/api/v1/mobile-voice/calls?offset=-1")
        assert resp.status_code == 200  # Postgres treats OFFSET -1 as 0

    def test_invalid_analytics_days(self, authenticated_client, voice_session_table):
        """days=0 should return valid (empty) analytics."""
        resp = authenticated_client.get("/api/v1/mobile-voice/analytics?days=0")
        assert resp.status_code == 200


# =============================================================================
# POST /api/v1/livekit/token — LiveKit token provisioning
# =============================================================================

class TestLiveKitToken:
    def test_returns_503_when_not_configured(self, authenticated_client):
        """Without env vars, should return 503."""
        resp = authenticated_client.post("/api/v1/livekit/token", json={})
        assert resp.status_code == 503

    @patch.dict("os.environ", {
        "LIVEKIT_API_KEY": "devkey1234567890",
        "LIVEKIT_API_SECRET": "secret_thats_long_enough_for_hs256_signing_requirements",
        "LIVEKIT_URL": "wss://test.livekit.cloud",
    })
    def test_returns_token_when_configured(self, authenticated_client):
        import routes.livekit_routes as lk_routes
        lk_routes.LIVEKIT_API_KEY = "devkey1234567890"
        lk_routes.LIVEKIT_API_SECRET = "secret_thats_long_enough_for_hs256_signing_requirements"
        lk_routes.LIVEKIT_URL = "wss://test.livekit.cloud"

        try:
            resp = authenticated_client.post("/api/v1/livekit/token", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert "token" in data
            assert "url" in data
            assert "room_name" in data
            assert data["url"] == "wss://test.livekit.cloud"
            assert data["token"].startswith("eyJ")  # JWT
        finally:
            lk_routes.LIVEKIT_API_KEY = ""
            lk_routes.LIVEKIT_API_SECRET = ""
            lk_routes.LIVEKIT_URL = ""

    @patch.dict("os.environ", {
        "LIVEKIT_API_KEY": "devkey1234567890",
        "LIVEKIT_API_SECRET": "secret_thats_long_enough_for_hs256_signing_requirements",
        "LIVEKIT_URL": "wss://test.livekit.cloud",
    })
    def test_custom_room_name(self, authenticated_client):
        import routes.livekit_routes as lk_routes
        lk_routes.LIVEKIT_API_KEY = "devkey1234567890"
        lk_routes.LIVEKIT_API_SECRET = "secret_thats_long_enough_for_hs256_signing_requirements"
        lk_routes.LIVEKIT_URL = "wss://test.livekit.cloud"

        try:
            resp = authenticated_client.post("/api/v1/livekit/token", json={
                "room_name": "custom-room-42"
            })
            assert resp.status_code == 200
            # Room name is now prefixed with user ID for isolation
            assert "custom-room-42" in resp.json()["room_name"]
        finally:
            lk_routes.LIVEKIT_API_KEY = ""
            lk_routes.LIVEKIT_API_SECRET = ""
            lk_routes.LIVEKIT_URL = ""

    @patch.dict("os.environ", {
        "LIVEKIT_API_KEY": "devkey1234567890",
        "LIVEKIT_API_SECRET": "secret_thats_long_enough_for_hs256_signing_requirements",
        "LIVEKIT_URL": "wss://test.livekit.cloud",
    })
    def test_rejects_invalid_room_name(self, authenticated_client):
        """Room names with special characters should be rejected."""
        import routes.livekit_routes as lk_routes
        lk_routes.LIVEKIT_API_KEY = "devkey1234567890"
        lk_routes.LIVEKIT_API_SECRET = "secret_thats_long_enough_for_hs256_signing_requirements"
        lk_routes.LIVEKIT_URL = "wss://test.livekit.cloud"

        try:
            resp = authenticated_client.post("/api/v1/livekit/token", json={
                "room_name": "room with spaces!"
            })
            assert resp.status_code == 400
        finally:
            lk_routes.LIVEKIT_API_KEY = ""
            lk_routes.LIVEKIT_API_SECRET = ""
            lk_routes.LIVEKIT_URL = ""


# =============================================================================
# GET /api/v1/livekit/health — LiveKit health check
# =============================================================================

class TestLiveKitHealth:
    def test_reports_not_configured(self, authenticated_client):
        resp = authenticated_client.get("/api/v1/livekit/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_reports_configured(self, authenticated_client):
        import routes.livekit_routes as lk_routes
        lk_routes.LIVEKIT_API_KEY = "testkey"
        lk_routes.LIVEKIT_API_SECRET = "testsecret"
        lk_routes.LIVEKIT_URL = "wss://test.livekit.cloud"

        try:
            resp = authenticated_client.get("/api/v1/livekit/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is True
            assert data["agent_name"] == "aria-voice"
            # URL is not exposed in health response (security)
            assert "url" not in data
        finally:
            lk_routes.LIVEKIT_API_KEY = ""
            lk_routes.LIVEKIT_API_SECRET = ""
            lk_routes.LIVEKIT_URL = ""
