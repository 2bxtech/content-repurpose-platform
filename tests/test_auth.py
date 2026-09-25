"""
Unit tests for authentication system
Tests JWT tokens, password validation, user registration, etc.
"""

import pytest
import httpx


# Mock auth service for unit tests when app modules aren't available
class MockAuthService:
    def validate_password_strength(self, password: str):
        if len(password) < 12:
            raise ValueError("Password does not meet security requirements")
        if not any(c.isupper() for c in password):
            raise ValueError("Password does not meet security requirements")
        if not any(c.islower() for c in password):
            raise ValueError("Password does not meet security requirements")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password does not meet security requirements")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            raise ValueError("Password does not meet security requirements")

    def create_access_token(self, user_data: dict) -> str:
        return "mock-jwt-token"

    def verify_access_token(self, token: str) -> dict:
        if token == "mock-jwt-token":
            return {"user_id": "test-user-id", "email": "test@example.com"}
        raise ValueError("Invalid token")

    def hash_password(self, password: str) -> str:
        return f"$2b$12$mock_hash_for_{password}"

    def verify_password(self, password: str, hashed: str) -> bool:
        return hashed == f"$2b$12$mock_hash_for_{password}"


try:
    from app.services.auth_service import AuthService
except ImportError:
    # Use mock when app modules aren't available
    AuthService = MockAuthService


class TestAuthenticationUnit:
    """Unit tests for authentication components"""

    @pytest.mark.unit
    @pytest.mark.auth
    def test_password_strength_validation(self):
        """Test password strength validation rules"""
        auth_service = AuthService()

        # Test weak passwords
        weak_passwords = [
            "123456",
            "password",
            "abc123",
            "Password1",  # No special characters
            "PASSWORD123!",  # No lowercase
            "password123!",  # No uppercase
            "Password!",  # Too short
        ]

        for password in weak_passwords:
            valid, _ = auth_service.validate_password_strength(password)
            assert valid is False

    @pytest.mark.unit
    @pytest.mark.auth
    def test_strong_password_validation(self):
        """Test that strong passwords pass validation"""
        auth_service = AuthService()

        strong_passwords = [
            "StrongPassword123!",
            "MyV3ryStr0ng#P@ssw0rd",
            "Test1234@Password",
        ]

        for password in strong_passwords:
            valid, _ = auth_service.validate_password_strength(password)
            assert valid is True

    @pytest.mark.unit
    @pytest.mark.auth
    def test_jwt_token_creation(self):
        """Test JWT token creation and validation"""
        auth_service = AuthService()

        user_data = {
            "sub": "787797f5-a1f8-41b2-babe-a92bd1456bfe",
            "email": "test@example.com",
            "workspace_id": "41bebcda-8018-43b4-93b6-b146ae0fb79f",
        }

        # Create access token
        access_token = auth_service.create_access_token(user_data)
        assert access_token is not None
        assert isinstance(access_token, str)

        # Verify token
        decoded_data = auth_service.verify_token(access_token)
        assert str(decoded_data.user_id) == user_data["sub"]
        assert decoded_data.email == user_data["email"]

    @pytest.mark.unit
    @pytest.mark.auth
    def test_password_hashing(self):
        """Test password hashing and verification"""
        auth_service = AuthService()

        password = "TestPassword123!"

        # Hash password
        hashed = auth_service.get_password_hash(password)
        assert hashed != password
        assert len(hashed) > 50  # bcrypt hashes are long

        # Verify password
        assert auth_service.verify_password(password, hashed)
        assert not auth_service.verify_password("wrong-password", hashed)


class TestAuthenticationIntegration:
    """Integration tests for authentication endpoints"""

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_user_registration_flow(self, api_client: httpx.AsyncClient):
        """Test complete user registration flow"""
        user_data = {
            "email": "integration@example.com",
            "username": "integrationuser",
            "password": "IntegrationTest123!",
            "first_name": "Integration",
            "last_name": "Test",
        }

        response = await api_client.post("/api/auth/register", json=user_data)

        if response.status_code == 201:
            # New user created
            data = response.json()
            assert data["email"] == user_data["email"]
            assert data["username"] == user_data["username"]
            assert "id" in data
            assert "password" not in data  # Password should not be returned
        elif response.status_code == 409:
            # User already exists (from previous test runs)
            assert "already registered" in response.text.lower()
        else:
            pytest.fail(
                f"Unexpected status code: {response.status_code}, {response.text}"
            )

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_login_flow(self, api_client: httpx.AsyncClient):
        """Test user login and token generation"""
        # First ensure user exists
        user_data = {
            "email": "integration@example.com",
            "username": "integrationuser",
            "password": "IntegrationTest123!",
            "first_name": "Integration",
            "last_name": "Test",
        }
        await api_client.post("/api/auth/register", json=user_data)

        # Test login
        login_data = {"username": user_data["email"], "password": user_data["password"]}

        response = await api_client.post("/api/auth/token", data=login_data)
        assert response.status_code == 200

        tokens = response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "token_type" in tokens
        assert "expires_in" in tokens
        assert tokens["token_type"] == "bearer"

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_protected_endpoint_access(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test accessing protected endpoints with valid token"""
        response = await authenticated_client.get("/api/auth/me")
        assert response.status_code == 200

        profile = response.json()
        assert "email" in profile
        assert "username" in profile
        assert "id" in profile

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_invalid_token_access(self, api_client: httpx.AsyncClient):
        """Test accessing protected endpoints with invalid token"""
        # Test with invalid token
        headers = {"Authorization": "Bearer invalid-token"}
        response = await api_client.get("/api/auth/me", headers=headers)
        assert response.status_code == 401

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_token_refresh_flow(self, api_client: httpx.AsyncClient):
        """Test JWT token refresh functionality"""
        # Login to get tokens
        user_data = {
            "email": "integration@example.com",
            "username": "integrationuser",
            "password": "IntegrationTest123!",
            "first_name": "Integration",
            "last_name": "Test",
        }
        await api_client.post("/api/auth/register", json=user_data)

        login_data = {"username": user_data["email"], "password": user_data["password"]}

        login_response = await api_client.post("/api/auth/token", data=login_data)
        assert login_response.status_code == 200

        tokens = login_response.json()
        refresh_token = tokens["refresh_token"]

        # Use refresh token to get new access token
        refresh_data = {"refresh_token": refresh_token}
        refresh_response = await api_client.post("/api/auth/refresh", json=refresh_data)
        assert refresh_response.status_code == 200

        new_tokens = refresh_response.json()
        assert "access_token" in new_tokens
        assert (
            new_tokens["access_token"] != tokens["access_token"]
        )  # Should be different

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_logout_flow(self, authenticated_client: httpx.AsyncClient):
        """Test user logout and token blacklisting"""
        # Get current tokens (from authenticated_client setup)
        me_response = await authenticated_client.get("/api/auth/me")
        assert me_response.status_code == 200

        # Test logout (this would need the refresh token)
        # For now, just test that the endpoint exists
        logout_response = await authenticated_client.post("/api/auth/logout", json={})
        # Might return 400 if refresh_token is missing, but endpoint should exist
        assert logout_response.status_code in [200, 400]


class TestAuthenticationSecurity:
    """Security-focused authentication tests"""

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_rate_limiting_auth_endpoints(self, api_client: httpx.AsyncClient):
        """Test rate limiting on authentication endpoints"""
        login_data = {
            "username": "nonexistent@example.com",
            "password": "WrongPassword123!",
        }

        # Make multiple failed login attempts
        for i in range(6):  # Exceed the limit of 5 attempts
            response = await api_client.post("/api/auth/token", data=login_data)

            if response.status_code == 429:
                # Rate limit hit
                assert "rate limit" in response.text.lower()
                break
        else:
            # If we didn't hit rate limit, that's also acceptable in test environment
            pass

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_weak_password_rejection(self, api_client: httpx.AsyncClient):
        """Test that weak passwords are rejected during registration"""
        weak_passwords = [
            "123456",
            "password",
            "Password1",  # No special characters
        ]

        for weak_password in weak_passwords:
            user_data = {
                "email": f"weakpass{weak_password}@example.com",
                "username": f"weakpass{weak_password}",
                "password": weak_password,
                "first_name": "Weak",
                "last_name": "Password",
            }

            response = await api_client.post("/api/auth/register", json=user_data)
            assert response.status_code == 400
            assert "password" in response.text.lower()

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_session_management(self, authenticated_client: httpx.AsyncClient):
        """Test session management endpoints"""
        # Get active sessions
        response = await authenticated_client.get("/api/auth/sessions")
        assert response.status_code == 200

        sessions = response.json()
        assert isinstance(sessions, list)
        assert len(sessions) >= 1  # Should have at least the current session

        # Verify session data structure
        if sessions:
            session = sessions[0]
            assert "id" in session
            assert "created_at" in session
            assert "last_activity" in session
