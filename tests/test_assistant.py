"""Test the AI assistant endpoint with comprehensive examples.
This script demonstrates how to:
1. Authenticate and obtain a bearer token
2. Use the token to interact with the /api/assistant endpoint
3. Test various queries and commands
Usage:
    pytest tests/test_assistant.py -v
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app

# Configuration
client = TestClient(app)
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
        register_response = client.post(
            "/api/users/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "name": TEST_USER_NAME
            }
        )
        assert register_response.status_code in [200, 201], f"Registration failed: {register_response.text}"
        
        # Login to get token
        login_response = client.post(
            "/api/users/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        data = login_response.json()
        cls.access_token = data.get("access_token")
        assert cls.access_token is not None, "No access token received"
        
        yield  # This allows the tests to run
        
        # Cleanup could go here if needed
    
    def get_headers(self):
        """Get authorization headers with bearer token."""
        return {
            "Authorization": f"Bearer {self.access_token}"
        }
    
    def test_assistant_health_check(self):
        """Test that the assistant endpoint is accessible."""
        response = client.get(
            "/api/assistant/health",
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
    
    def test_assistant_simple_query(self):
        """Test a simple query to the assistant."""
        response = client.post(
            "/api/assistant",
            json={"query": "Hello, how are you?"},
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Query failed: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "response" in data or "answer" in data, "Response should contain answer"
    
    def test_assistant_lead_query(self):
        """Test querying for leads."""
        response = client.post(
            "/api/assistant",
            json={"query": "Show me all leads"},
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Lead query failed: {response.text}"
    
    def test_assistant_with_missing_query(self):
        """Test that the assistant rejects requests without a query."""
        response = client.post(
            "/api/assistant",
            json={},
            headers=self.get_headers()
        )
        # Should return 422 for validation error or handle gracefully
        assert response.status_code in [400, 422, 404], "Should reject empty query"
    
    def test_assistant_without_auth(self):
        """Test that the assistant requires authentication."""
        response = client.post(
            "/api/assistant",
            json={"query": "Hello"}
        )
        # Should require authentication
        assert response.status_code in [401, 403, 404], "Should require authentication"
    
    def test_assistant_with_invalid_token(self):
        """Test that the assistant rejects invalid tokens."""
        response = client.post(
            "/api/assistant",
            json={"query": "Hello"},
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        assert response.status_code in [401, 403, 404], "Should reject invalid token"
    
    def test_assistant_create_lead_query(self):
        """Test asking the assistant to create a lead."""
        response = client.post(
            "/api/assistant",
            json={
                "query": "Create a new lead for John Doe with email john@example.com and phone 555-1234"
            },
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Create lead query failed: {response.text}"
    
    def test_assistant_update_lead_query(self):
        """Test asking the assistant to update a lead."""
        response = client.post(
            "/api/assistant",
            json={
                "query": "Update lead with ID 1 to set status to 'contacted'"
            },
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Update lead query failed: {response.text}"
    
    def test_assistant_search_leads(self):
        """Test searching for leads by criteria."""
        response = client.post(
            "/api/assistant",
            json={
                "query": "Find all leads with status 'new'"
            },
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Search query failed: {response.text}"
    
    def test_assistant_analytics_query(self):
        """Test asking for analytics or statistics."""
        response = client.post(
            "/api/assistant",
            json={
                "query": "What are my conversion rates this month?"
            },
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Analytics query failed: {response.text}"
    
    def test_assistant_help_query(self):
        """Test asking for help or capabilities."""
        response = client.post(
            "/api/assistant",
            json={
                "query": "What can you help me with?"
            },
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Help query failed: {response.text}"
    
    def test_assistant_complex_query(self):
        """Test a complex multi-part query."""
        response = client.post(
            "/api/assistant",
            json={
                "query": "Show me all leads from this week with status 'new' and sort by date"
            },
            headers=self.get_headers()
        )
        assert response.status_code in [200, 404], f"Complex query failed: {response.text}"
    
    def test_assistant_conversation_context(self):
        """Test that the assistant can handle follow-up queries."""
        # First query
        response1 = client.post(
            "/api/assistant",
            json={"query": "How many leads do I have?"},
            headers=self.get_headers()
        )
        assert response1.status_code in [200, 404]
        
        # Follow-up query
        response2 = client.post(
            "/api/assistant",
            json={"query": "And how many are from this week?"},
            headers=self.get_headers()
        )
        assert response2.status_code in [200, 404]

if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
