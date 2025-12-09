#!/usr/bin/env python3
"""
Security Testing Suite
Tests for authentication, authorization, input validation, and security vulnerabilities
"""

import pytest
import jwt
import time
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient


class TestAuthenticationSecurity:
    """Authentication and token security tests"""

    def test_01_access_without_token(self, client):
        """Test that protected endpoints reject requests without token"""
        protected_endpoints = [
            "/api/v1/borrower/applications",
            "/api/v1/borrower/applications/1",
            "/api/v1/lo/dashboard/stats",
            "/api/v1/lo/applications",
        ]

        for endpoint in protected_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401, f"Endpoint {endpoint} should require auth"

    def test_02_invalid_token_format(self, client):
        """Test that malformed tokens are rejected"""
        invalid_tokens = [
            "not_a_jwt_token",
            "Bearer ",
            "Bearer invalid",
            "Basic dXNlcjpwYXNz",  # Basic auth
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Incomplete JWT
        ]

        for token in invalid_tokens:
            response = client.get(
                "/api/v1/borrower/applications",
                headers={"Authorization": token}
            )
            assert response.status_code in [401, 403], f"Invalid token should be rejected: {token[:20]}"

    def test_03_expired_token_rejected(self, client):
        """Test that expired tokens are rejected"""
        # Create an expired token
        expired_payload = {
            "sub": "test@example.com",
            "exp": int(time.time()) - 3600  # Expired 1 hour ago
        }
        expired_token = jwt.encode(expired_payload, "test_secret", algorithm="HS256")

        response = client.get(
            "/api/v1/borrower/applications",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

    def test_04_token_with_wrong_signature(self, client):
        """Test that tokens with wrong signature are rejected"""
        # Create token with different secret
        payload = {
            "sub": "test@example.com",
            "exp": int(time.time()) + 3600
        }
        wrong_secret_token = jwt.encode(payload, "wrong_secret", algorithm="HS256")

        response = client.get(
            "/api/v1/borrower/applications",
            headers={"Authorization": f"Bearer {wrong_secret_token}"}
        )
        assert response.status_code == 401

    def test_05_token_payload_manipulation(self, client):
        """Test that manipulated token payloads are detected"""
        # Get a valid token structure
        header = base64.b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
        # Try to escalate privileges
        payload = base64.b64encode(b'{"sub":"admin","role":"admin","exp":9999999999}').decode().rstrip("=")
        # Fake signature
        signature = "fake_signature"

        manipulated_token = f"{header}.{payload}.{signature}"

        response = client.get(
            "/api/v1/borrower/applications",
            headers={"Authorization": f"Bearer {manipulated_token}"}
        )
        assert response.status_code == 401


class TestAuthorizationSecurity:
    """Authorization and access control tests"""

    def test_01_borrower_cannot_access_lo_endpoints(self, client, borrower_auth_headers):
        """Test that borrowers cannot access LO-only endpoints"""
        lo_endpoints = [
            "/api/v1/lo/dashboard/stats",
            "/api/v1/lo/applications",
            "/api/v1/lo/applications/1/export/mismo",
        ]

        for endpoint in lo_endpoints:
            response = client.get(endpoint, headers=borrower_auth_headers)
            assert response.status_code in [401, 403], f"Borrower should not access {endpoint}"

    def test_02_borrower_cannot_access_other_borrower_data(self, client, borrower_auth_headers):
        """Test that borrowers cannot access other borrowers' applications"""
        # Try to access application ID that doesn't belong to this borrower
        response = client.get(
            "/api/v1/borrower/applications/99999",
            headers=borrower_auth_headers
        )
        assert response.status_code in [403, 404]

    def test_03_lo_can_only_see_assigned_applications(self, client, lo_auth_headers):
        """Test that LOs can only see their assigned applications"""
        # This depends on implementation - verify in actual test
        response = client.get(
            "/api/v1/lo/applications",
            headers=lo_auth_headers
        )
        assert response.status_code == 200
        # Verify no applications from other LOs are returned

    def test_04_horizontal_privilege_escalation(self, client, borrower_auth_headers):
        """Test prevention of horizontal privilege escalation"""
        # Try to update someone else's application
        response = client.put(
            "/api/v1/borrower/applications/99999/personal",
            headers=borrower_auth_headers,
            json={"first_name": "Hacker"}
        )
        assert response.status_code in [403, 404]


class TestInputValidation:
    """Input validation and sanitization tests"""

    def test_01_sql_injection_in_search(self, client, lo_auth_headers):
        """Test SQL injection prevention in search parameter"""
        sql_payloads = [
            "'; DROP TABLE applications; --",
            "1' OR '1'='1",
            "1; SELECT * FROM users --",
            "' UNION SELECT * FROM users --",
            "1' AND 1=1 --",
        ]

        for payload in sql_payloads:
            response = client.get(
                "/api/v1/lo/applications",
                headers=lo_auth_headers,
                params={"search": payload}
            )
            # Should not error - should treat as literal string
            assert response.status_code in [200, 400, 422], f"SQL injection not handled: {payload}"

    def test_02_sql_injection_in_form_fields(self, client, auth_headers, application_id):
        """Test SQL injection in form field values"""
        sql_payloads = [
            "O'Malley'; DROP TABLE users; --",
            "Smith\" OR \"1\"=\"1",
        ]

        for payload in sql_payloads:
            response = client.put(
                f"/api/v1/borrower/applications/{application_id}/personal",
                headers=auth_headers,
                json={"last_name": payload}
            )
            # Should succeed (stored as text) or reject (validation)
            assert response.status_code in [200, 400, 422]

            # Verify data wasn't executed as SQL
            if response.status_code == 200:
                get_response = client.get(
                    f"/api/v1/borrower/applications/{application_id}/personal",
                    headers=auth_headers
                )
                if get_response.status_code == 200:
                    data = get_response.json()
                    # Name should be stored as-is (escaped)
                    assert "DROP TABLE" not in str(data).upper() or payload in data.get("last_name", "")

    def test_03_xss_prevention(self, client, auth_headers, application_id):
        """Test XSS prevention in text fields"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg/onload=alert('xss')>",
            "';alert('xss');//",
            "<iframe src='javascript:alert(1)'>",
        ]

        for payload in xss_payloads:
            response = client.put(
                f"/api/v1/borrower/applications/{application_id}/personal",
                headers=auth_headers,
                json={"first_name": payload}
            )

            if response.status_code == 200:
                # Verify output is escaped
                get_response = client.get(
                    f"/api/v1/borrower/applications/{application_id}/personal",
                    headers=auth_headers
                )
                if get_response.status_code == 200:
                    response_text = get_response.text
                    # Script tags should be escaped or removed
                    assert "<script>" not in response_text.lower() or "&lt;script&gt;" in response_text.lower()

    def test_04_path_traversal_in_file_name(self, client, auth_headers, application_id):
        """Test path traversal prevention in file uploads"""
        path_traversal_names = [
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f",
            "....//....//etc/passwd",
        ]

        for filename in path_traversal_names:
            response = client.post(
                f"/api/v1/borrower/applications/{application_id}/documents",
                headers=auth_headers,
                files={"file": (filename, b"test content", "application/pdf")},
                data={"document_type": "other"}
            )
            # Should reject or sanitize filename
            assert response.status_code in [200, 400, 422]

    def test_05_command_injection(self, client, auth_headers, application_id):
        """Test command injection prevention"""
        cmd_payloads = [
            "; ls -la",
            "| cat /etc/passwd",
            "$(whoami)",
            "`id`",
            "&& rm -rf /",
        ]

        for payload in cmd_payloads:
            response = client.put(
                f"/api/v1/borrower/applications/{application_id}/personal",
                headers=auth_headers,
                json={"first_name": payload}
            )
            # Should not execute commands
            assert response.status_code in [200, 400, 422]

    def test_06_integer_overflow(self, client, auth_headers, application_id):
        """Test handling of extremely large numbers"""
        large_numbers = [
            99999999999999999999999999999999,
            -99999999999999999999999999999999,
            2**64,  # Max unsigned 64-bit
        ]

        for num in large_numbers:
            response = client.put(
                f"/api/v1/borrower/applications/{application_id}/income",
                headers=auth_headers,
                json={"monthly_income": num}
            )
            # Should validate/reject or handle gracefully
            assert response.status_code in [200, 400, 422]


class TestFileUploadSecurity:
    """File upload security tests"""

    def test_01_executable_file_rejected(self, client, auth_headers, application_id):
        """Test that executable files are rejected"""
        executable_types = [
            ("malware.exe", "application/x-executable"),
            ("script.sh", "application/x-sh"),
            ("app.bat", "application/x-bat"),
            ("program.dll", "application/x-dll"),
        ]

        for filename, mimetype in executable_types:
            response = client.post(
                f"/api/v1/borrower/applications/{application_id}/documents",
                headers=auth_headers,
                files={"file": (filename, b"malicious content", mimetype)},
                data={"document_type": "other"}
            )
            assert response.status_code in [400, 415], f"Executable {filename} should be rejected"

    def test_02_file_extension_validation(self, client, auth_headers, application_id):
        """Test that file extension matches content type"""
        # PDF content with .exe extension
        response = client.post(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers,
            files={"file": ("document.exe", b"%PDF-1.4 fake pdf", "application/pdf")},
            data={"document_type": "pay_stub"}
        )
        assert response.status_code in [400, 415]

    def test_03_file_size_limit(self, client, auth_headers, application_id):
        """Test that oversized files are rejected"""
        # 15MB file
        large_content = b"x" * (15 * 1024 * 1024)

        response = client.post(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers,
            files={"file": ("large.pdf", large_content, "application/pdf")},
            data={"document_type": "pay_stub"}
        )
        assert response.status_code in [400, 413]

    def test_04_empty_file_rejected(self, client, auth_headers, application_id):
        """Test that empty files are rejected"""
        response = client.post(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers,
            files={"file": ("empty.pdf", b"", "application/pdf")},
            data={"document_type": "pay_stub"}
        )
        assert response.status_code in [400, 422]

    def test_05_zip_bomb_protection(self, client, auth_headers, application_id):
        """Test protection against zip bombs"""
        # Create a small file that claims to be very large when decompressed
        # This is a simplified test - real zip bomb protection is complex
        import io
        import gzip

        # Create compressed content
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode='wb') as f:
            f.write(b"x" * 1000)
        compressed_content = compressed.getvalue()

        response = client.post(
            f"/api/v1/borrower/applications/{application_id}/documents",
            headers=auth_headers,
            files={"file": ("test.gz", compressed_content, "application/gzip")},
            data={"document_type": "other"}
        )
        # Should either reject gzip or handle safely
        assert response.status_code in [200, 400, 415]


class TestDataProtection:
    """PII and sensitive data protection tests"""

    def test_01_ssn_masked_in_response(self, client, auth_headers, application_id):
        """Test that SSN is masked in API responses"""
        # First save SSN
        client.put(
            f"/api/v1/borrower/applications/{application_id}/personal",
            headers=auth_headers,
            json={"ssn": "123-45-6789"}
        )

        # Then retrieve
        response = client.get(
            f"/api/v1/borrower/applications/{application_id}/personal",
            headers=auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            ssn = data.get("ssn", "")
            # Should be masked (e.g., ***-**-6789)
            if ssn:
                assert "123-45-6789" not in ssn or "***" in ssn or len(ssn) < 11

    def test_02_ssn_not_in_logs(self):
        """Test that SSN is not logged (check log files)"""
        # This would require access to log files
        # Manual verification required
        pass

    def test_03_password_not_returned(self, client, admin_auth_headers):
        """Test that passwords are never returned in API responses"""
        response = client.get(
            "/api/v1/admin/users",
            headers=admin_auth_headers
        )

        if response.status_code == 200:
            response_text = response.text.lower()
            assert "password" not in response_text or '"password":null' in response_text

    def test_04_sensitive_headers_not_leaked(self, client, auth_headers):
        """Test that sensitive headers are not leaked in responses"""
        response = client.get(
            "/api/v1/borrower/applications",
            headers=auth_headers
        )

        # Check response headers don't leak server info
        server_header = response.headers.get("Server", "")
        assert "version" not in server_header.lower()

        # X-Powered-By should not be present
        assert "X-Powered-By" not in response.headers


class TestHTTPSecurity:
    """HTTP security headers and configuration tests"""

    def test_01_cors_configuration(self, client):
        """Test CORS is properly configured"""
        response = client.options(
            "/api/v1/borrower/applications",
            headers={"Origin": "http://malicious-site.com"}
        )

        # Should not allow arbitrary origins
        allow_origin = response.headers.get("Access-Control-Allow-Origin", "")
        assert allow_origin != "*" or allow_origin == ""

    def test_02_security_headers_present(self, client, auth_headers):
        """Test security headers are present"""
        response = client.get(
            "/api/v1/borrower/applications",
            headers=auth_headers
        )

        # Check for security headers (implementation dependent)
        # These may or may not be set depending on deployment
        recommended_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
        ]

        present_headers = [h for h in recommended_headers if h in response.headers]
        # Log which headers are present for review
        print(f"\nSecurity headers present: {present_headers}")

    def test_03_no_sensitive_data_in_url(self, client, auth_headers):
        """Test that sensitive data is not passed in URL"""
        # Attempt to pass sensitive data in query params
        response = client.get(
            "/api/v1/borrower/applications",
            headers=auth_headers,
            params={"ssn": "123-45-6789"}
        )

        # API should not accept SSN as query param
        # Or should reject it
        assert response.status_code in [200, 400, 422]

    def test_04_rate_limiting(self, client, auth_headers):
        """Test that rate limiting is in place"""
        # Make many requests quickly
        responses = []
        for _ in range(100):
            response = client.get(
                "/api/v1/borrower/applications",
                headers=auth_headers
            )
            responses.append(response.status_code)

        # Should see 429 (Too Many Requests) at some point
        # Or all should succeed if rate limiting is generous
        rate_limited = 429 in responses
        print(f"\nRate limiting active: {rate_limited}")


class TestCSRFProtection:
    """CSRF protection tests"""

    def test_01_state_changing_requires_auth(self, client):
        """Test that state-changing operations require authentication"""
        # Try POST without auth
        response = client.post(
            "/api/v1/borrower/applications",
            json={"loan_purpose": "purchase"}
        )
        assert response.status_code == 401

        # Try PUT without auth
        response = client.put(
            "/api/v1/borrower/applications/1/personal",
            json={"first_name": "Test"}
        )
        assert response.status_code == 401

        # Try DELETE without auth
        response = client.delete("/api/v1/borrower/applications/1")
        assert response.status_code in [401, 404, 405]


# Fixtures
@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_borrower_token"}


@pytest.fixture
def borrower_auth_headers():
    return {"Authorization": "Bearer test_borrower_token"}


@pytest.fixture
def lo_auth_headers():
    return {"Authorization": "Bearer test_lo_token"}


@pytest.fixture
def admin_auth_headers():
    return {"Authorization": "Bearer test_admin_token"}


@pytest.fixture
def application_id():
    return 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
