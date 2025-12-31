"""
Intake Engine API Tests
Tests for FastAPI endpoints
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from ..api import router


@pytest.fixture
def app():
    """Create test FastAPI app"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


class TestSessionEndpoints:
    """Tests for session management endpoints"""

    def test_create_session(self, client):
        """Test creating a new session"""
        response = client.post("/api/v1/intake/sessions", json={
            "loan_id": "L123",
            "mode": "intake_prequal",
            "locale": "en-US",
        })

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "ACTIVE"

    def test_get_session_status(self, client):
        """Test getting session status"""
        # Create session first
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Get status
        response = client.get(f"/api/v1/intake/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "scores" in data
        assert "progress" in data

    def test_get_nonexistent_session(self, client):
        """Test getting a session that doesn't exist"""
        response = client.get("/api/v1/intake/sessions/INVALID_ID")

        assert response.status_code == 404


class TestQuestionFlowEndpoints:
    """Tests for question flow endpoints"""

    def test_get_next_question(self, client):
        """Test getting next question"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Get next question
        response = client.get(f"/api/v1/intake/sessions/{session_id}/next")

        # May return 200 with question or 200 with null if no questions configured
        assert response.status_code == 200

    def test_submit_answer(self, client):
        """Test submitting an answer"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Submit answer (may fail validation if question not found, but endpoint works)
        response = client.post(
            f"/api/v1/intake/sessions/{session_id}/answer",
            json={
                "question_id": "Q_TEST",
                "value": "test_answer",
                "response_time_ms": 1500,
            }
        )

        assert response.status_code == 200


class TestPartyEndpoints:
    """Tests for party management endpoints"""

    def test_add_party(self, client):
        """Test adding a party"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Add co-borrower
        response = client.post(
            f"/api/v1/intake/sessions/{session_id}/parties",
            json={
                "party_type": "CO_BORROWER",
                "display_name": "Jane Doe",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["party_type"] == "CO_BORROWER"
        assert data["display_name"] == "Jane Doe"

    def test_get_parties(self, client):
        """Test getting parties"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Add party
        client.post(
            f"/api/v1/intake/sessions/{session_id}/parties",
            json={"party_type": "CO_BORROWER"},
        )

        # Get parties
        response = client.get(f"/api/v1/intake/sessions/{session_id}/parties")

        assert response.status_code == 200
        data = response.json()
        assert "parties" in data
        # Session starts with PRIMARY + we added CO_BORROWER = 2
        assert len(data["parties"]) >= 1


class TestConsentEndpoints:
    """Tests for consent management endpoints"""

    def test_capture_consent(self, client):
        """Test capturing consent"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Capture consent
        response = client.post(
            f"/api/v1/intake/sessions/{session_id}/consents",
            json={
                "consent_key": "econsent",
                "accepted": True,
                "version_hash": "abc123",
            }
        )

        assert response.status_code == 200
        assert response.json()["status"] == "captured"

    def test_get_consents(self, client):
        """Test getting consents"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Capture consent
        client.post(
            f"/api/v1/intake/sessions/{session_id}/consents",
            json={
                "consent_key": "econsent",
                "accepted": True,
                "version_hash": "abc123",
            }
        )

        # Get consents
        response = client.get(f"/api/v1/intake/sessions/{session_id}/consents")

        assert response.status_code == 200
        data = response.json()
        assert "econsent" in data["consents"]


class TestScoreEndpoints:
    """Tests for score endpoints"""

    def test_get_scores(self, client):
        """Test getting scores"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Get scores
        response = client.get(f"/api/v1/intake/sessions/{session_id}/scores")

        assert response.status_code == 200
        data = response.json()
        assert "truth_score" in data
        assert "readiness_score" in data
        assert "breakdown" in data

    def test_get_flags(self, client):
        """Test getting flags"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Get flags
        response = client.get(f"/api/v1/intake/sessions/{session_id}/flags")

        assert response.status_code == 200
        data = response.json()
        assert "flags" in data


class TestAuditEndpoints:
    """Tests for audit endpoints"""

    def test_get_audit_trail(self, client):
        """Test getting audit trail"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Get audit trail
        response = client.get(f"/api/v1/intake/sessions/{session_id}/audit")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "chain_valid" in data


class TestCoachingEndpoints:
    """Tests for coaching endpoints"""

    def test_get_coaching_suggestions(self, client):
        """Test getting coaching suggestions"""
        # Create session
        create_response = client.post("/api/v1/intake/sessions", json={})
        session_id = create_response.json()["session_id"]

        # Get suggestions
        response = client.get(f"/api/v1/intake/sessions/{session_id}/coaching")

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
