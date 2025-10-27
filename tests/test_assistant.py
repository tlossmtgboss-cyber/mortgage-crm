"""Test the AI assistant endpoint with comprehensive examples.

This script demonstrates how to:
1. Authenticate and obtain a bearer token
2. Use the token to interact with the /api/assistant endpoint
3. Test various queries and commands

Usage:
    pytest tests/test_assistant.py -v
"""

import pytest
import requests
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"  # Change to your deployed URL if testing production
TEST_USER_EMAIL = f"assistant_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com"
TEST_USER_PASSWORD = "TestPassword123!"
TEST_USER_NAME = "Assistant Test User"


class TestAssistant:
    """Test suite for the AI assistant endpoint."""
    
    access_token = None
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_class(cls):
        """Set up test user and obtain access token."""
        # Register user
        register_response = requests.post(
            f"{BASE_URL}/api/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "full_name": TEST_USER_NAME
            }
        )
        
        assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
        print(f"\n✓ Test user registered: {TEST_USER_EMAIL}")
        
        # Login to get token
        login_response = requests.post(
            f"{BASE_URL}/api/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
        )
        
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        data = login_response.json()
        cls.access_token = data["access_token"]
        print(f"✓ Access token obtained: {cls.access_token[:20]}...")
    
    def _make_assistant_request(self, message):
        """Helper method to make requests to the assistant endpoint."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/assistant",
            headers=headers,
            json={"message": message}
        )
        
        return response
    
    def test_01_simple_greeting(self):
        """Test a simple greeting to the assistant."""
        response = self._make_assistant_request("Hello!")
        
        assert response.status_code == 200, f"Assistant request failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ Simple greeting test passed")
    
    def test_02_lead_query(self):
        """Test querying about leads."""
        response = self._make_assistant_request("Show me all leads from this month")
        
        assert response.status_code == 200, f"Lead query failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ Lead query test passed")
    
    def test_03_help_request(self):
        """Test requesting help from the assistant."""
        response = self._make_assistant_request("What can you help me with?")
        
        assert response.status_code == 200, f"Help request failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ Help request test passed")
    
    def test_04_lead_creation(self):
        """Test asking the assistant to create a lead."""
        message = "Create a new lead for John Doe with email john@example.com"
        response = self._make_assistant_request(message)
        
        assert response.status_code == 200, f"Lead creation request failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ Lead creation test passed")
    
    def test_05_stats_query(self):
        """Test querying for statistics."""
        response = self._make_assistant_request("How many leads do I have?")
        
        assert response.status_code == 200, f"Stats query failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ Statistics query test passed")
    
    def test_06_search_leads(self):
        """Test searching for specific leads."""
        response = self._make_assistant_request("Find all leads with high priority")
        
        assert response.status_code == 200, f"Lead search failed: {response.text}"
        data = response.json()
        assert "response" in data or "message" in data, "No response from assistant"
        print("✓ Lead search test passed")
    
    def test_07_empty_message(self):
        """Test sending an empty message."""
        response = self._make_assistant_request("")
        
        # Should either return 400 or handle gracefully
        assert response.status_code in [200, 400, 422], f"Unexpected response: {response.text}"
        print("✓ Empty message handling test passed")
    
    def test_08_long_conversation(self):
        """Test multiple consecutive messages."""
        messages = [
            "Hello",
            "What's my first task today?",
            "Thanks for your help!"
        ]
        
        for message in messages:
            response = self._make_assistant_request(message)
            assert response.status_code == 200, f"Conversation failed at: {message}"
        
        print("✓ Long conversation test passed")
    
    def test_09_without_authorization(self):
        """Test that the endpoint requires authorization."""
        response = requests.post(
            f"{BASE_URL}/api/assistant",
            json={"message": "This should fail"}
        )
        
        assert response.status_code == 401, "Endpoint should require authorization"
        print("✓ Authorization requirement test passed")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
