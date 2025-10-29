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
from app.db import create_db

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
        
        # Initialize database
        create_db()
        
        # Try to login with demo user (should already exist from seed data)
        login_response = client.post(
            "/api/token",
            data={
                "username": "demo",
                "password": "demo123"
            }
        )
        
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        data = login_response.json()
        TestAssistant.access_token = data["access_token"]
        
        print(f"\n✓ Setup complete. Token obtained for {TEST_USER_EMAIL}")
    
    def test_01_assistant_greeting(self):
        """Test basic greeting query."""
        assert TestAssistant.access_token is not None, "No access token available"
        
        response = client.post(
            "/api/assistant",
            headers={"Authorization": f"Bearer {TestAssistant.access_token}"},
            json={"prompt": "Hello! Can you help me?"}
        )
        
        assert response.status_code == 200, f"Assistant request failed: {response.text}"
        data = response.json()
        assert "response" in data
        print(f"\n✓ Assistant greeting test passed")
        print(f"Response: {data['response'][:100]}...")
    
    def test_02_assistant_mortgage_info(self):
        """Test mortgage-related query."""
        assert TestAssistant.access_token is not None
        
        response = client.post(
            "/api/assistant",
            headers={"Authorization": f"Bearer {TestAssistant.access_token}"},
            json={"prompt": "What documents do I need for a mortgage application?"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        print(f"\n✓ Mortgage info test passed")
        print(f"Response: {data['response'][:100]}...")
    
    def test_03_assistant_lead_status(self):
        """Test lead status query."""
        assert TestAssistant.access_token is not None
        
        response = client.post(
            "/api/assistant",
            headers={"Authorization": f"Bearer {TestAssistant.access_token}"},
            json={"prompt": "What's the status of my leads?"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        print(f"\n✓ Lead status test passed")
        print(f"Response: {data['response'][:100]}...")

if __name__ == "__main__":
    pytest.main(["-v", __file__])
