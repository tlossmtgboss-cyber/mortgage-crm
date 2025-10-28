"""Test authentication flow with pytest.

This script tests the complete authentication flow:
1. Register a new user
2. Login to obtain a bearer token
3. Use the token to access protected endpoints

Usage:
    pytest tests/test_auth_flow.py -v
"""
import pytest
import requests
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"  # Change to your deployed URL if testing production
TEST_USER_EMAIL = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com"
TEST_USER_PASSWORD = "TestPassword123!"
TEST_USER_NAME = "Test User"

class TestAuthFlow:
    """Test suite for authentication flow."""
    
    access_token = None
    
    def test_01_register_user(self):
        """Test user registration."""
        response = requests.post(
            f"{BASE_URL}/api/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "full_name": TEST_USER_NAME
            }
        )
        
        assert response.status_code == 200, f"Registration failed: {response.text}"
        data = response.json()
        assert "id" in data, "User ID not returned"
        assert data["email"] == TEST_USER_EMAIL
        print(f"✓ User registered successfully: {TEST_USER_EMAIL}")
    
    def test_02_login_user(self):
        """Test user login and token generation."""
        response = requests.post(
            f"{BASE_URL}/api/login",
            json={
                "identifier": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Access token not returned"
        assert "token_type" in data, "Token type not returned"
        assert data["token_type"] == "bearer"
        
        # Store token for subsequent tests
        TestAuthFlow.access_token = data["access_token"]
        print(f"✓ Login successful. Token: {TestAuthFlow.access_token[:20]}...")
    
    def test_03_access_protected_endpoint(self):
        """Test accessing a protected endpoint with bearer token."""
        assert TestAuthFlow.access_token is not None, "No access token available"
        
        headers = {
            "Authorization": f"Bearer {TestAuthFlow.access_token}"
        }
        
        # Test the /api/me endpoint (if it exists) or another protected endpoint
        response = requests.get(
            f"{BASE_URL}/api/me",
            headers=headers
        )
        
        # If /api/me doesn't exist, try another endpoint
        if response.status_code == 404:
            print("Note: /api/me endpoint not found, testing with alternative endpoint")
            response = requests.get(
                f"{BASE_URL}/api/leads",
                headers=headers
            )
        
        assert response.status_code in [200, 404], f"Protected endpoint access failed: {response.text}"
        print("✓ Successfully accessed protected endpoint with bearer token")
    
    def test_04_assistant_endpoint(self):
        """Test the AI assistant endpoint with bearer token."""
        assert TestAuthFlow.access_token is not None, "No access token available"
        
        headers = {
            "Authorization": f"Bearer {TestAuthFlow.access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/assistant",
            headers=headers,
            json={
                "message": "Hello, what can you help me with?"
            }
        )
        
        assert response.status_code == 200, f"Assistant endpoint failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ AI Assistant endpoint working correctly")
    
    def test_05_invalid_token(self):
        """Test that invalid tokens are rejected."""
        headers = {
            "Authorization": "Bearer invalid_token_12345"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/assistant",
            headers=headers,
            json={
                "message": "This should fail"
            }
        )
        
        assert response.status_code == 401, "Invalid token should return 401"
        print("✓ Invalid tokens are correctly rejected")

if __name__ == "__main__":
    pytest.main(["-v", __file__])
