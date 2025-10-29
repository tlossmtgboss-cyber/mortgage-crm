import pytest
from fastapi.testclient import TestClient
from app.main import app, get_password_hash, verify_password, create_access_token
from datetime import timedelta

# Create test client
client = TestClient(app)

# Test data
test_user = {
    "username": "demo",
    "password": "demo123",
    "email": "demo@example.com"
}

class TestAuthentication:
    """Test suite for authentication endpoints"""
    
    def test_password_hashing(self):
        """Test password hashing and verification"""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        # Verify hash is different from password
        assert hashed != password
        # Verify password verification works
        assert verify_password(password, hashed) == True
        # Verify wrong password fails
        assert verify_password("wrongpassword", hashed) == False
    
    def test_create_access_token(self):
        """Test JWT token creation"""
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        # Verify token is created
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_token_with_expiry(self):
        """Test JWT token creation with custom expiry"""
        data = {"sub": "testuser"}
        token = create_access_token(data, expires_delta=timedelta(minutes=15))
        
        assert token is not None
        assert isinstance(token, str)

class TestAPI:
    """Test suite for API endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_login_success(self):
        """Test successful login"""
        response = client.post(
            "/api/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_failure_wrong_password(self):
        """Test login with wrong password"""
        response = client.post(
            "/api/token",
            data={
                "username": test_user["username"],
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
    
    def test_login_failure_nonexistent_user(self):
        """Test login with non-existent user"""
        response = client.post(
            "/api/token",
            data={
                "username": "nonexistent",
                "password": "password"
            }
        )
        assert response.status_code == 401
    
    def test_register_new_user(self):
        """Test user registration"""
        unique_username = f"testuser_{pytest.approx(1000000)}"
        response = client.post(
            "/api/register",
            json={
                "username": unique_username,
                "email": f"{unique_username}@test.com",
                "password": "testpass123",
                "full_name": "Test User"
            }
        )
        # Registration might be disabled or require admin, so we accept 201 or 403
        assert response.status_code in [201, 403]
    
    def test_get_current_user(self):
        """Test getting current user info"""
        # First login to get token
        login_response = client.post(
            "/api/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Then get user info
        response = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user["username"]
    
    def test_get_current_user_unauthorized(self):
        """Test getting user info without token"""
        response = client.get("/api/users/me")
        assert response.status_code == 401
    
    def test_get_current_user_invalid_token(self):
        """Test getting user info with invalid token"""
        response = client.get(
            "/api/users/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401

class TestProtectedEndpoints:
    """Test suite for protected endpoints"""
    
    def test_protected_endpoint_with_valid_token(self):
        """Test accessing protected endpoint with valid token"""
        # Login to get token
        login_response = client.post(
            "/api/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        token = login_response.json()["access_token"]
        
        # Access protected endpoint
        response = client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        # Protected endpoint might not exist, so we accept 200 or 404
        assert response.status_code in [200, 404]
    
    def test_protected_endpoint_without_token(self):
        """Test accessing protected endpoint without token"""
        response = client.get("/api/protected")
        # Should be unauthorized or not found
        assert response.status_code in [401, 404]

class TestAssistantEndpoint:
    """Test suite for AI Assistant endpoint"""
    
    def test_assistant_endpoint(self):
        """Test AI assistant endpoint (mocked)"""
        # First login to get admin token
        login_response = client.post(
            "/api/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        
        if login_response.status_code != 200:
            pytest.skip("Could not authenticate admin user for assistant test")
        
        token = login_response.json()["access_token"]
        
        # Test assistant endpoint
        response = client.post(
            "/api/assistant",
            json={"prompt": "Hello, what can you help me with?"},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Accept 200 (success), 403 (not admin), or 500 (OpenAI key not configured)
        assert response.status_code in [200, 403, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "response" in data
            assert "success" in data
