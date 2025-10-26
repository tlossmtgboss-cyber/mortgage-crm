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
    
    def test_create_access_token_with_expiration(self):
        """Test JWT token creation with custom expiration"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=60)
        token = create_access_token(data, expires_delta=expires_delta)
        
        # Verify token is created
        assert token is not None
        assert isinstance(token, str)
    
    def test_login_success(self):
        """Test successful login"""
        response = client.post(
            "/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        
        # Verify successful login
        assert response.status_code == 200
        json_response = response.json()
        assert "access_token" in json_response
        assert "token_type" in json_response
        assert json_response["token_type"] == "bearer"
        assert len(json_response["access_token"]) > 0
    
    def test_login_invalid_username(self):
        """Test login with invalid username"""
        response = client.post(
            "/token",
            data={
                "username": "invaliduser",
                "password": test_user["password"]
            }
        )
        
        # Verify login fails
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_login_invalid_password(self):
        """Test login with invalid password"""
        response = client.post(
            "/token",
            data={
                "username": test_user["username"],
                "password": "wrongpassword"
            }
        )
        
        # Verify login fails
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_register_user(self):
        """Test user registration"""
        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "newpass123",
                "email": "newuser@example.com"
            }
        )
        
        # Verify registration response
        assert response.status_code == 200
        json_response = response.json()
        assert "message" in json_response
        assert "username" in json_response
        assert json_response["username"] == "newuser"
    
    def test_get_current_user(self):
        """Test getting current user with valid token"""
        # First, login to get token
        login_response = client.post(
            "/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Now test getting current user
        response = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify current user returned
        assert response.status_code == 200
        json_response = response.json()
        assert "username" in json_response
        assert json_response["username"] == test_user["username"]
    
    def test_get_current_user_no_token(self):
        """Test getting current user without token"""
        response = client.get("/users/me")
        
        # Verify unauthorized
        assert response.status_code == 401
    
    def test_get_current_user_invalid_token(self):
        """Test getting current user with invalid token"""
        response = client.get(
            "/users/me",
            headers={"Authorization": "Bearer invalidtoken123"}
        )
        
        # Verify unauthorized
        assert response.status_code == 401
    
    def test_protected_route(self):
        """Test accessing protected route with valid token"""
        # First, login to get token
        login_response = client.post(
            "/token",
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Now test protected route
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify protected route accessible
        assert response.status_code == 200
        json_response = response.json()
        assert "message" in json_response
        assert test_user["username"] in json_response["message"]
    
    def test_protected_route_no_token(self):
        """Test accessing protected route without token"""
        response = client.get("/protected")
        
        # Verify unauthorized
        assert response.status_code == 401

class TestHealthCheck:
    """Test suite for basic API health checks"""
    
    def test_root_endpoint(self):
        """Test root endpoint returns HTML"""
        response = client.get("/")
        
        # Verify response
        assert response.status_code == 200
        # The root endpoint returns HTML file
        assert response.headers["content-type"] in ["text/html", "text/html; charset=utf-8"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
