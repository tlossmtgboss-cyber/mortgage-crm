"""
Pre-Launch Testing Suite: Borrower Flow (End-to-End)
Tests all borrower-facing functionality from login to submission
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Test configuration
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_borrower.db")


class TestSocialLogin:
    """Test Suite: Social login from all 4 providers"""

    def test_google_oauth_initiation(self, client):
        """Test Google OAuth redirect URL generation"""
        response = client.get("/api/v1/auth/borrower/google")
        assert response.status_code in [200, 302]
        # Should contain Google OAuth URL
        if response.status_code == 200:
            data = response.json()
            assert "auth_url" in data or "redirect_url" in data

    def test_google_oauth_callback(self, client):
        """Test Google OAuth callback handling"""
        with patch('services.borrower_auth_service.verify_google_token') as mock_verify:
            mock_verify.return_value = {
                "email": "test@gmail.com",
                "name": "Test User",
                "sub": "google_123456"
            }
            response = client.post("/api/v1/auth/borrower/google/callback", json={
                "token": "mock_google_token"
            })
            # Should return JWT or create account
            assert response.status_code in [200, 201]

    def test_facebook_oauth_initiation(self, client):
        """Test Facebook OAuth redirect URL generation"""
        response = client.get("/api/v1/auth/borrower/facebook")
        assert response.status_code in [200, 302]

    def test_facebook_oauth_callback(self, client):
        """Test Facebook OAuth callback handling"""
        with patch('services.borrower_auth_service.verify_facebook_token') as mock_verify:
            mock_verify.return_value = {
                "email": "test@facebook.com",
                "name": "Test User",
                "id": "fb_123456"
            }
            response = client.post("/api/v1/auth/borrower/facebook/callback", json={
                "token": "mock_fb_token"
            })
            assert response.status_code in [200, 201]

    def test_linkedin_oauth_initiation(self, client):
        """Test LinkedIn OAuth redirect URL generation"""
        response = client.get("/api/v1/auth/borrower/linkedin")
        assert response.status_code in [200, 302]

    def test_apple_oauth_initiation(self, client):
        """Test Apple Sign In redirect URL generation"""
        response = client.get("/api/v1/auth/borrower/apple")
        assert response.status_code in [200, 302]

    def test_invalid_oauth_token(self, client):
        """Test handling of invalid OAuth tokens"""
        response = client.post("/api/v1/auth/borrower/google/callback", json={
            "token": "invalid_token"
        })
        assert response.status_code in [400, 401]


class TestMagicLink:
    """Test Suite: Magic link email delivery"""

    def test_magic_link_request(self, client):
        """Test magic link email request"""
        with patch('services.notification_service.send_email') as mock_send:
            mock_send.return_value = True
            response = client.post("/api/v1/auth/borrower/magic-link", json={
                "email": "test@example.com"
            })
            assert response.status_code == 200
            assert mock_send.called

    def test_magic_link_verification(self, client):
        """Test magic link token verification"""
        # Create a valid magic link token
        test_token = "valid_magic_token_123"
        with patch('services.borrower_auth_service.verify_magic_token') as mock_verify:
            mock_verify.return_value = {"email": "test@example.com", "borrower_id": 1}
            response = client.post("/api/v1/auth/borrower/magic-link/verify", json={
                "token": test_token
            })
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data or "token" in data

    def test_expired_magic_link(self, client):
        """Test expired magic link rejection"""
        with patch('services.borrower_auth_service.verify_magic_token') as mock_verify:
            mock_verify.side_effect = Exception("Token expired")
            response = client.post("/api/v1/auth/borrower/magic-link/verify", json={
                "token": "expired_token"
            })
            assert response.status_code in [400, 401]

    def test_invalid_email_format(self, client):
        """Test invalid email format rejection"""
        response = client.post("/api/v1/auth/borrower/magic-link", json={
            "email": "invalid-email"
        })
        assert response.status_code == 422  # Validation error


class TestFormApplication:
    """Test Suite: Form application completion"""

    def test_start_application(self, client, auth_headers):
        """Test starting a new application"""
        response = client.post("/api/v1/borrower/applications",
            headers=auth_headers,
            json={
                "loan_purpose": "purchase",
                "property_type": "single_family"
            }
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "application_id" in data or "id" in data

    def test_save_personal_info(self, client, auth_headers, application_id):
        """Test saving personal information step"""
        response = client.put(
            f"/api/v1/borrower/applications/{application_id}/personal",
            headers=auth_headers,
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "phone": "555-123-4567",
                "ssn": "123-45-6789",
                "date_of_birth": "1985-06-15"
            }
        )
        assert response.status_code == 200

    def test_save_property_info(self, client, auth_headers, application_id):
        """Test saving property information step"""
        response = client.put(
            f"/api/v1/borrower/applications/{application_id}/property",
            headers=auth_headers,
            json={
                "property_address": "123 Main St",
                "city": "Anytown",
                "state": "CA",
                "zip_code": "90210",
                "property_type": "single_family",
                "occupancy_type": "primary_residence",
                "purchase_price": 500000
            }
        )
        assert response.status_code == 200

    def test_save_income_info(self, client, auth_headers, application_id):
        """Test saving income information step"""
        response = client.put(
            f"/api/v1/borrower/applications/{application_id}/income",
            headers=auth_headers,
            json={
                "employment_status": "employed",
                "employer_name": "Acme Corp",
                "job_title": "Software Engineer",
                "monthly_income": 10000,
                "years_employed": 5
            }
        )
        assert response.status_code == 200

    def test_save_assets_info(self, client, auth_headers, application_id):
        """Test saving assets information step"""
        response = client.put(
            f"/api/v1/borrower/applications/{application_id}/assets",
            headers=auth_headers,
            json={
                "checking_balance": 25000,
                "savings_balance": 50000,
                "investment_balance": 100000,
                "retirement_balance": 150000
            }
        )
        assert response.status_code == 200

    def test_application_progress_tracking(self, client, auth_headers, application_id):
        """Test application progress is tracked correctly"""
        response = client.get(
            f"/api/v1/borrower/applications/{application_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "progress" in data or "completion_percentage" in data

    def test_validation_errors(self, client, auth_headers, application_id):
        """Test validation errors are returned properly"""
        response = client.put(
            f"/api/v1/borrower/applications/{application_id}/personal",
            headers=auth_headers,
            json={
                "first_name": "",  # Empty required field
                "email": "invalid-email"  # Invalid format
            }
        )
        assert response.status_code == 422


class TestConversationalAI:
    """Test Suite: Conversational AI mode completion"""

    def test_start_concierge_session(self, client, auth_headers):
        """Test starting AI concierge session"""
        response = client.post(
            "/api/v1/borrower/concierge/start",
            headers=auth_headers,
            json={"application_id": 1}
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "session_id" in data or "message" in data

    def test_concierge_message_exchange(self, client, auth_headers):
        """Test sending message to concierge"""
        with patch('services.concierge_service.ConciergeService.process_message') as mock_process:
            mock_process.return_value = {
                "response": "I'd be happy to help with your mortgage application.",
                "extracted_data": {},
                "next_stage": "personal_info"
            }
            response = client.post(
                "/api/v1/borrower/concierge/message",
                headers=auth_headers,
                json={
                    "message": "I want to buy a house",
                    "stage": "introduction"
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "response" in data

    def test_concierge_data_extraction(self, client, auth_headers):
        """Test data extraction from conversation"""
        with patch('services.concierge_service.ConciergeService.process_message') as mock_process:
            mock_process.return_value = {
                "response": "Got it, your name is John Doe.",
                "extracted_data": {
                    "first_name": "John",
                    "last_name": "Doe"
                },
                "next_stage": "property_info"
            }
            response = client.post(
                "/api/v1/borrower/concierge/message",
                headers=auth_headers,
                json={
                    "message": "My name is John Doe",
                    "stage": "personal_info"
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "extracted_data" in data
            assert data["extracted_data"]["first_name"] == "John"

    def test_concierge_completion(self, client, auth_headers):
        """Test completing application via concierge"""
        response = client.post(
            "/api/v1/borrower/concierge/complete",
            headers=auth_headers,
            json={
                "application_id": 1,
                "extracted_data": {
                    "first_name": "John",
                    "last_name": "Doe",
                    "loan_purpose": "purchase"
                }
            }
        )
        assert response.status_code == 200


class TestDocumentUpload:
    """Test Suite: Document upload and AI verification"""

    def test_document_upload(self, client, auth_headers, application_id):
        """Test document upload"""
        # Create a mock file
        file_content = b"Mock PDF content"
        response = client.post(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers,
            files={"file": ("test_doc.pdf", file_content, "application/pdf")},
            data={"document_type": "pay_stub"}
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "document_id" in data or "id" in data

    def test_document_ai_verification(self, client, auth_headers, document_id):
        """Test AI document verification"""
        with patch('services.document_service.analyze_document') as mock_analyze:
            mock_analyze.return_value = {
                "verified": True,
                "document_type": "pay_stub",
                "confidence": 0.95,
                "extracted_data": {
                    "employer_name": "Acme Corp",
                    "gross_pay": 5000
                }
            }
            response = client.post(
                f"/api/v1/borrower/documents/{document_id}/verify",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get("verified") == True or data.get("status") == "verified"

    def test_document_type_validation(self, client, auth_headers, application_id):
        """Test invalid document type rejection"""
        file_content = b"Mock content"
        response = client.post(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers,
            files={"file": ("test.exe", file_content, "application/octet-stream")},
            data={"document_type": "pay_stub"}
        )
        assert response.status_code in [400, 415]  # Bad request or unsupported media

    def test_document_list(self, client, auth_headers, application_id):
        """Test listing uploaded documents"""
        response = client.get(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "documents" in data


class TestCoBorrower:
    """Test Suite: Co-borrower invitation and acceptance"""

    def test_send_coborrower_invitation(self, client, auth_headers, application_id):
        """Test sending co-borrower invitation"""
        with patch('services.notification_service.send_email') as mock_send:
            mock_send.return_value = True
            response = client.post(
                f"/api/v1/borrower/applications/{application_id}/coborrower/invite",
                headers=auth_headers,
                json={
                    "email": "coborrower@example.com",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "relationship": "spouse"
                }
            )
            assert response.status_code in [200, 201]
            assert mock_send.called

    def test_coborrower_invitation_acceptance(self, client):
        """Test co-borrower accepting invitation"""
        with patch('services.borrower_auth_service.verify_coborrower_token') as mock_verify:
            mock_verify.return_value = {
                "application_id": 1,
                "email": "coborrower@example.com"
            }
            response = client.post(
                "/api/v1/borrower/coborrower/accept",
                json={
                    "token": "valid_coborrower_token",
                    "password": "SecurePass123!"
                }
            )
            assert response.status_code in [200, 201]

    def test_coborrower_data_submission(self, client, coborrower_auth_headers, application_id):
        """Test co-borrower submitting their data"""
        response = client.put(
            f"/api/v1/borrower/applications/{application_id}/coborrower",
            headers=coborrower_auth_headers,
            json={
                "first_name": "Jane",
                "last_name": "Doe",
                "ssn": "987-65-4321",
                "employment_status": "employed",
                "monthly_income": 8000
            }
        )
        assert response.status_code == 200


class TestReviewCallScheduling:
    """Test Suite: Review call scheduling"""

    def test_get_available_slots(self, client, auth_headers):
        """Test getting available time slots"""
        response = client.get(
            "/api/v1/borrower/review-call/available-slots",
            headers=auth_headers,
            params={"timezone": "America/New_York"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "slots" in data or isinstance(data, list)

    def test_schedule_review_call(self, client, auth_headers, application_id):
        """Test scheduling a review call"""
        response = client.post(
            "/api/v1/borrower/review-call/schedule",
            headers=auth_headers,
            json={
                "application_id": application_id,
                "slot_datetime": "2024-12-15T10:00:00",
                "timezone": "America/New_York",
                "contact_method": "phone",
                "phone_number": "555-123-4567"
            }
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "appointment_id" in data or "id" in data

    def test_reschedule_review_call(self, client, auth_headers, appointment_id):
        """Test rescheduling a review call"""
        response = client.put(
            f"/api/v1/borrower/review-call/{appointment_id}",
            headers=auth_headers,
            json={
                "slot_datetime": "2024-12-16T14:00:00",
                "timezone": "America/New_York"
            }
        )
        assert response.status_code == 200

    def test_cancel_review_call(self, client, auth_headers, appointment_id):
        """Test canceling a review call"""
        response = client.delete(
            f"/api/v1/borrower/review-call/{appointment_id}",
            headers=auth_headers
        )
        assert response.status_code in [200, 204]


class TestFinalSubmission:
    """Test Suite: Final submission"""

    def test_pre_submission_validation(self, client, auth_headers, application_id):
        """Test pre-submission validation"""
        response = client.get(
            f"/api/v1/borrower/applications/{application_id}/validate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data or "is_valid" in data

    def test_submit_application(self, client, auth_headers, application_id):
        """Test final application submission"""
        with patch('services.notification_service.send_email') as mock_email:
            with patch('services.notification_service.send_sms') as mock_sms:
                mock_email.return_value = True
                mock_sms.return_value = True
                response = client.post(
                    f"/api/v1/borrower/applications/{application_id}/submit",
                    headers=auth_headers,
                    json={"confirm": True}
                )
                assert response.status_code == 200
                data = response.json()
                assert data.get("status") == "submitted" or "confirmation" in data

    def test_submission_without_review_call(self, client, auth_headers, application_id_no_call):
        """Test submission blocked without scheduled review call"""
        response = client.post(
            f"/api/v1/borrower/applications/{application_id_no_call}/submit",
            headers=auth_headers,
            json={"confirm": True}
        )
        # Should fail if review call is mandatory
        assert response.status_code in [400, 403]


class TestConfirmationNotifications:
    """Test Suite: Confirmation emails/SMS"""

    def test_submission_email_sent(self, client, auth_headers, application_id):
        """Test confirmation email is sent on submission"""
        with patch('services.notification_service.send_email') as mock_email:
            mock_email.return_value = True
            response = client.post(
                f"/api/v1/borrower/applications/{application_id}/submit",
                headers=auth_headers,
                json={"confirm": True}
            )
            # Verify email was called
            assert mock_email.called
            call_args = mock_email.call_args
            assert "confirmation" in str(call_args).lower() or "submitted" in str(call_args).lower()

    def test_submission_sms_sent(self, client, auth_headers, application_id):
        """Test confirmation SMS is sent on submission"""
        with patch('services.notification_service.send_sms') as mock_sms:
            mock_sms.return_value = True
            response = client.post(
                f"/api/v1/borrower/applications/{application_id}/submit",
                headers=auth_headers,
                json={"confirm": True}
            )
            # Verify SMS was called
            assert mock_sms.called


# Pytest fixtures - using authenticated_client from conftest.py
@pytest.fixture
def client(authenticated_client):
    """Use authenticated client for all tests in this file."""
    return authenticated_client


# These fixtures extend conftest.py fixtures
@pytest.fixture
def auth_headers():
    """Generate auth headers for testing"""
    return {"Authorization": "Bearer test_token_123"}


@pytest.fixture
def coborrower_auth_headers():
    """Generate co-borrower auth headers"""
    return {"Authorization": "Bearer coborrower_token_123"}


@pytest.fixture
def application_id_no_call():
    """Return test application ID without review call"""
    return 2


@pytest.fixture
def document_id():
    """Return test document ID"""
    return 1


@pytest.fixture
def appointment_id():
    """Return test appointment ID"""
    return 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
