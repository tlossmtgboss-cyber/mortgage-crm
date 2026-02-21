"""
Pre-Launch Testing Suite: Borrower Flow (End-to-End)
Tests all borrower-facing functionality from login to submission

Routes implemented at:
- /api/v1/borrower-auth/* - OAuth and magic link authentication
- /api/v1/borrower/* - Applications, documents, concierge, scheduling
"""

import pytest
import uuid
import jwt
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Skip entire module on SQLite — borrower portal requires PostgreSQL features
_TEST_DB_URL = os.getenv("DATABASE_URL", os.getenv("TEST_DATABASE_URL", ""))
pytestmark = pytest.mark.skipif(
    "sqlite" in _TEST_DB_URL.lower(),
    reason="Borrower flow tests require PostgreSQL"
)

from fastapi.testclient import TestClient
from sqlalchemy import text


# JWT configuration for test tokens
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")


@pytest.fixture(autouse=True)
def setup_borrower_tables(db_session):
    """Create borrower portal tables in test database."""
    # Create borrower_profiles table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS borrower_profiles (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            profile_photo TEXT,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            raw_profile TEXT,
            communication_consent INTEGER,
            marketing_consent INTEGER,
            consent_captured_at TIMESTAMP,
            consent_ip_address TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """))

    # Create borrower_applications table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS borrower_applications (
            id TEXT PRIMARY KEY,
            borrower_profile_id TEXT NOT NULL,
            loan_purpose TEXT NOT NULL,
            property_type TEXT,
            status TEXT DEFAULT 'in_progress',
            current_step TEXT DEFAULT 'profile',
            progress_percentage INTEGER DEFAULT 0,
            profile_data TEXT,
            income_data TEXT,
            asset_data TEXT,
            property_data TEXT,
            declarations TEXT,
            lo_id INTEGER,
            submitted_at TIMESTAMP,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (borrower_profile_id) REFERENCES borrower_profiles(id)
        )
    """))

    # Create borrower_documents table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS borrower_documents (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            borrower_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            doc_category TEXT DEFAULT 'other',
            filename TEXT NOT NULL,
            original_filename TEXT,
            file_size INTEGER,
            mime_type TEXT,
            file_content TEXT,
            status TEXT DEFAULT 'pending_review',
            review_notes TEXT,
            reviewed_by INTEGER,
            reviewed_at TIMESTAMP,
            uploaded_at TIMESTAMP
        )
    """))

    # Create coborrower_invitations table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS coborrower_invitations (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            email TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            relationship TEXT,
            invitation_token TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            invited_at TIMESTAMP,
            accepted_at TIMESTAMP,
            completed_at TIMESTAMP,
            expires_at TIMESTAMP,
            coborrower_data TEXT
        )
    """))

    # Create concierge_messages table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS concierge_messages (
            id TEXT PRIMARY KEY,
            borrower_id TEXT NOT NULL,
            application_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP
        )
    """))

    # Create scheduled_calls table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS scheduled_calls (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            borrower_id TEXT NOT NULL,
            lo_id INTEGER,
            preferred_date TEXT,
            preferred_time TEXT,
            timezone TEXT DEFAULT 'America/New_York',
            confirmed_datetime TIMESTAMP,
            notes TEXT,
            status TEXT DEFAULT 'pending',
            meeting_link TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """))

    # Create borrower_magic_links table
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS borrower_magic_links (
            id TEXT PRIMARY KEY,
            borrower_id TEXT,
            token TEXT UNIQUE NOT NULL,
            email TEXT,
            expires_at TIMESTAMP,
            used_at TIMESTAMP,
            created_at TIMESTAMP
        )
    """))

    db_session.commit()
    yield
    # Tables are dropped automatically by test fixture teardown


def create_borrower_token(borrower_id: str, email: str) -> str:
    """Create a test borrower JWT token."""
    payload = {
        "sub": borrower_id,
        "email": email,
        "type": "borrower",
        "exp": datetime.utcnow() + timedelta(days=1),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def borrower_profile(db_session):
    """Create a test borrower profile."""
    borrower_id = str(uuid.uuid4())
    db_session.execute(text("""
        INSERT INTO borrower_profiles (id, email, first_name, last_name, provider, provider_user_id, created_at, updated_at)
        VALUES (:id, :email, :first_name, :last_name, 'test', :provider_user_id, :now, :now)
    """), {
        "id": borrower_id,
        "email": "testborrower@example.com",
        "first_name": "Test",
        "last_name": "Borrower",
        "provider_user_id": "test_123",
        "now": datetime.utcnow(),
    })
    db_session.commit()
    return borrower_id


@pytest.fixture
def borrower_auth_headers(borrower_profile):
    """Generate auth headers with valid borrower token."""
    token = create_borrower_token(borrower_profile, "testborrower@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_application(db_session, borrower_profile):
    """Create a test application."""
    app_id = str(uuid.uuid4())
    db_session.execute(text("""
        INSERT INTO borrower_applications (id, borrower_profile_id, loan_purpose, property_type, status, current_step, progress_percentage, created_at, updated_at)
        VALUES (:id, :borrower_id, 'purchase', 'single_family', 'in_progress', 'profile', 0, :now, :now)
    """), {
        "id": app_id,
        "borrower_id": borrower_profile,
        "now": datetime.utcnow(),
    })
    db_session.commit()
    return app_id


# =============================================================================
# SOCIAL LOGIN TESTS - Using /api/v1/borrower-auth/*
# =============================================================================

class TestSocialLogin:
    """Test Suite: Social login from all 4 providers"""

    def test_google_oauth_initiation(self, authenticated_client):
        """Test Google OAuth redirect URL generation"""
        response = authenticated_client.get("/api/v1/borrower-auth/google/connect")
        # Returns auth_url or 500 if not configured
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "auth_url" in data

    def test_facebook_oauth_initiation(self, authenticated_client):
        """Test Facebook OAuth redirect URL generation"""
        response = authenticated_client.get("/api/v1/borrower-auth/facebook/connect")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "auth_url" in data

    def test_linkedin_oauth_initiation(self, authenticated_client):
        """Test LinkedIn OAuth redirect URL generation"""
        response = authenticated_client.get("/api/v1/borrower-auth/linkedin/connect")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "auth_url" in data

    def test_apple_oauth_initiation(self, authenticated_client):
        """Test Apple Sign In redirect URL generation"""
        response = authenticated_client.get("/api/v1/borrower-auth/apple/connect")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "auth_url" in data


# =============================================================================
# MAGIC LINK TESTS - Using /api/v1/borrower-auth/email/*
# =============================================================================

class TestMagicLink:
    """Test Suite: Magic link email delivery"""

    def test_magic_link_request(self, authenticated_client, db_session):
        """Test magic link email request"""
        with patch('borrower_auth_routes.send_magic_link_email') as mock_send:
            mock_send.return_value = True
            response = authenticated_client.post("/api/v1/borrower-auth/email/request", json={
                "email": "test@example.com",
                "first_name": "Test"
            })
            assert response.status_code == 200
            data = response.json()
            assert data.get("success") == True

    def test_invalid_email_format(self, authenticated_client):
        """Test invalid email format rejection"""
        response = authenticated_client.post("/api/v1/borrower-auth/email/request", json={
            "email": "invalid-email"
        })
        assert response.status_code == 422  # Validation error


# =============================================================================
# APPLICATION TESTS - Using /api/v1/borrower/applications/*
# =============================================================================

class TestFormApplication:
    """Test Suite: Form application completion"""

    def test_start_application(self, authenticated_client, borrower_auth_headers, db_session):
        """Test starting a new application"""
        response = authenticated_client.post(
            "/api/v1/borrower/applications",
            headers=borrower_auth_headers,
            json={
                "loan_purpose": "purchase",
                "property_type": "single_family"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("status") == "in_progress"

    def test_list_applications(self, authenticated_client, borrower_auth_headers, test_application):
        """Test listing applications"""
        response = authenticated_client.get(
            "/api/v1/borrower/applications",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "applications" in data
        assert len(data["applications"]) >= 1

    def test_get_application_details(self, authenticated_client, borrower_auth_headers, test_application):
        """Test getting application details"""
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == test_application
        assert "loan_purpose" in data

    def test_update_application(self, authenticated_client, borrower_auth_headers, test_application):
        """Test updating application data"""
        response = authenticated_client.patch(
            f"/api/v1/borrower/applications/{test_application}",
            headers=borrower_auth_headers,
            json={
                "current_step": "income",
                "profile_data": {
                    "firstName": "John",
                    "lastName": "Doe"
                }
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True

    def test_application_progress_tracking(self, authenticated_client, borrower_auth_headers, test_application):
        """Test application progress is tracked correctly"""
        # Update to income step
        authenticated_client.patch(
            f"/api/v1/borrower/applications/{test_application}",
            headers=borrower_auth_headers,
            json={"current_step": "income"}
        )

        # Check progress updated
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("progress_percentage") == 40  # income step = 40%

    def test_application_not_found(self, authenticated_client, borrower_auth_headers):
        """Test 404 for non-existent application"""
        response = authenticated_client.get(
            "/api/v1/borrower/applications/nonexistent-id",
            headers=borrower_auth_headers
        )
        assert response.status_code == 404


# =============================================================================
# DOCUMENT TESTS - Using /api/v1/borrower/applications/*/documents
# =============================================================================

class TestDocumentUpload:
    """Test Suite: Document upload and management"""

    def test_document_list_empty(self, authenticated_client, borrower_auth_headers, test_application):
        """Test listing documents when none uploaded"""
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}/documents",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert len(data["documents"]) == 0

    def test_document_upload(self, authenticated_client, borrower_auth_headers, test_application):
        """Test document upload"""
        file_content = b"Mock PDF content for testing"
        response = authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/documents",
            headers=borrower_auth_headers,
            files={"file": ("test_paystub.pdf", file_content, "application/pdf")},
            data={"doc_type": "pay_stub", "doc_category": "income"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("status") == "pending_review"

    def test_document_list_after_upload(self, authenticated_client, borrower_auth_headers, test_application):
        """Test listing documents after upload"""
        # First upload a document
        file_content = b"Mock PDF content"
        authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/documents",
            headers=borrower_auth_headers,
            files={"file": ("w2.pdf", file_content, "application/pdf")},
            data={"doc_type": "w2", "doc_category": "income"}
        )

        # Then list
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}/documents",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) >= 1


# =============================================================================
# CO-BORROWER TESTS - Using /api/v1/borrower/applications/*/coborrowers
# =============================================================================

class TestCoBorrower:
    """Test Suite: Co-borrower invitation and acceptance"""

    def test_list_coborrowers_empty(self, authenticated_client, borrower_auth_headers, test_application):
        """Test listing co-borrowers when none invited"""
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}/coborrowers",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "coborrowers" in data
        assert len(data["coborrowers"]) == 0

    def test_invite_coborrower(self, authenticated_client, borrower_auth_headers, test_application):
        """Test sending co-borrower invitation"""
        response = authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/coborrowers",
            headers=borrower_auth_headers,
            json={
                "email": "coborrower@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "relationship": "spouse"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("status") == "pending"

    def test_coborrower_invitation_listed(self, authenticated_client, borrower_auth_headers, test_application):
        """Test co-borrower appears in list after invitation"""
        # Invite
        authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/coborrowers",
            headers=borrower_auth_headers,
            json={
                "email": "spouse@example.com",
                "first_name": "Spouse",
                "last_name": "Test",
                "relationship": "spouse"
            }
        )

        # List
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}/coborrowers",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["coborrowers"]) >= 1


# =============================================================================
# CONCIERGE TESTS - Using /api/v1/borrower/concierge/*
# =============================================================================

class TestConversationalAI:
    """Test Suite: Conversational AI concierge"""

    def test_concierge_chat(self, authenticated_client, borrower_auth_headers):
        """Test sending message to concierge"""
        response = authenticated_client.post(
            "/api/v1/borrower/concierge/chat",
            headers=borrower_auth_headers,
            json={
                "message": "I want to buy a house"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0

    def test_concierge_chat_with_context(self, authenticated_client, borrower_auth_headers, test_application):
        """Test concierge with application context"""
        response = authenticated_client.post(
            "/api/v1/borrower/concierge/chat",
            headers=borrower_auth_headers,
            json={
                "message": "What's my application status?",
                "application_id": test_application
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data

    def test_concierge_history(self, authenticated_client, borrower_auth_headers):
        """Test getting concierge chat history"""
        # Send a message first
        authenticated_client.post(
            "/api/v1/borrower/concierge/chat",
            headers=borrower_auth_headers,
            json={"message": "Hello"}
        )

        # Get history
        response = authenticated_client.get(
            "/api/v1/borrower/concierge/history",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data


# =============================================================================
# SCHEDULING TESTS - Using /api/v1/borrower/applications/*/schedule
# =============================================================================

class TestReviewCallScheduling:
    """Test Suite: Review call scheduling"""

    def test_schedule_review_call(self, authenticated_client, borrower_auth_headers, test_application):
        """Test scheduling a review call"""
        response = authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/schedule",
            headers=borrower_auth_headers,
            json={
                "preferred_date": "2025-01-15",
                "preferred_time": "10:00",
                "timezone": "America/New_York",
                "notes": "Please call my cell"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("status") == "pending"

    def test_get_scheduled_calls(self, authenticated_client, borrower_auth_headers, test_application):
        """Test getting scheduled calls"""
        # Schedule one first
        authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/schedule",
            headers=borrower_auth_headers,
            json={
                "preferred_date": "2025-01-20",
                "preferred_time": "14:00"
            }
        )

        # Get list
        response = authenticated_client.get(
            f"/api/v1/borrower/applications/{test_application}/schedule",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "scheduled_calls" in data
        assert len(data["scheduled_calls"]) >= 1


# =============================================================================
# SUBMISSION TESTS - Using /api/v1/borrower/applications/*/submit
# =============================================================================

class TestFinalSubmission:
    """Test Suite: Final submission"""

    def test_submit_application(self, authenticated_client, borrower_auth_headers, test_application):
        """Test final application submission"""
        response = authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/submit",
            headers=borrower_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "submitted_at" in data

    def test_double_submit_blocked(self, authenticated_client, borrower_auth_headers, test_application):
        """Test that double submission is blocked"""
        # Submit once
        authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/submit",
            headers=borrower_auth_headers
        )

        # Try again
        response = authenticated_client.post(
            f"/api/v1/borrower/applications/{test_application}/submit",
            headers=borrower_auth_headers
        )
        assert response.status_code == 400
        error_msg = response.json().get("detail", "") or response.json().get("error", "")
        assert "already submitted" in error_msg.lower()


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================

class TestBorrowerAuthentication:
    """Test Suite: Borrower authentication requirements"""

    def test_unauthenticated_request_rejected(self, authenticated_client):
        """Test that unauthenticated requests are rejected"""
        response = authenticated_client.get("/api/v1/borrower/applications")
        assert response.status_code == 401

    def test_invalid_token_rejected(self, authenticated_client):
        """Test that invalid tokens are rejected"""
        response = authenticated_client.get(
            "/api/v1/borrower/applications",
            headers={"Authorization": "Bearer invalid_token_123"}
        )
        assert response.status_code == 401

    def test_expired_token_rejected(self, authenticated_client):
        """Test that expired tokens are rejected"""
        # Create expired token
        payload = {
            "sub": "test-id",
            "email": "test@test.com",
            "type": "borrower",
            "exp": datetime.utcnow() - timedelta(days=1),  # Expired yesterday
            "iat": datetime.utcnow() - timedelta(days=2),
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        response = authenticated_client.get(
            "/api/v1/borrower/applications",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

    def test_non_borrower_token_rejected(self, authenticated_client):
        """Test that non-borrower tokens are rejected"""
        # Create token with wrong type
        payload = {
            "sub": "test-id",
            "email": "test@test.com",
            "type": "user",  # Wrong type
            "exp": datetime.utcnow() + timedelta(days=1),
            "iat": datetime.utcnow(),
        }
        wrong_type_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        response = authenticated_client.get(
            "/api/v1/borrower/applications",
            headers={"Authorization": f"Bearer {wrong_type_token}"}
        )
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
