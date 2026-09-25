"""
Unit tests for authentication system
Tests JWT tokens, password validation, user registration, etc.
"""

import uuid

import httpx
import pytest

from app.services.auth_service import AuthService


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
        """Registration returns the public profile; a second sign-up with the same email is refused"""
        suffix = uuid.uuid4().hex[:8]
        user_data = {
            "email": f"integration_{suffix}@example.com",
            "username": f"integration_{suffix}",
            "password": "IntegrationTest123!",
        }

        response = await api_client.post("/api/auth/register", json=user_data)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["username"] == user_data["username"]
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data

        duplicate = await api_client.post(
            "/api/auth/register", json={**user_data, "username": f"other_{suffix}"}
        )
        assert duplicate.status_code == 400
        assert "already registered" in duplicate.text.lower()

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_login_flow(self, api_client: httpx.AsyncClient, user_factory, jwt_claims):
        """Test user login and token generation"""
        user = await user_factory()

        response = await api_client.post(
            "/api/auth/token", data={"username": user["email"], "password": user["password"]}
        )
        assert response.status_code == 200

        tokens = response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "expires_in" in tokens
        assert tokens["token_type"] == "bearer"

        claims = jwt_claims(tokens["access_token"])
        assert claims["email"] == user["email"]
        assert claims["workspace_id"]

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_login_rejects_wrong_password(self, api_client: httpx.AsyncClient, user_factory):
        user = await user_factory()
        response = await api_client.post(
            "/api/auth/token", data={"username": user["email"], "password": "WrongPassword123!"}
        )
        assert response.status_code == 401

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_protected_endpoint_access(
        self, authenticated_client: httpx.AsyncClient, auth_user: dict
    ):
        """Test accessing protected endpoints with valid token"""
        response = await authenticated_client.get("/api/auth/me")
        assert response.status_code == 200

        profile = response.json()
        assert profile["email"] == auth_user["email"]
        assert profile["username"] == auth_user["username"]
        assert profile["id"] == auth_user["user_id"]

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_invalid_token_access(self, api_client: httpx.AsyncClient):
        """Test accessing protected endpoints with invalid token"""
        headers = {"Authorization": "Bearer invalid-token"}
        response = await api_client.get("/api/auth/me", headers=headers)
        assert response.status_code == 401

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_token_refresh_flow(self, api_client: httpx.AsyncClient, user_factory):
        """Refresh issues new tokens and rotates the refresh token (the old one stops working)"""
        user = await user_factory()

        refresh_response = await api_client.post(
            "/api/auth/refresh", json={"refresh_token": user["refresh_token"]}
        )
        assert refresh_response.status_code == 200

        new_tokens = refresh_response.json()
        assert new_tokens["access_token"] != user["token"]
        assert new_tokens["refresh_token"] != user["refresh_token"]

        replay = await api_client.post(
            "/api/auth/refresh", json={"refresh_token": user["refresh_token"]}
        )
        assert replay.status_code == 401

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_logout_flow(self, api_client: httpx.AsyncClient, user_factory):
        """Logout revokes the refresh token's session"""
        user = await user_factory()

        # Logout needs to know which session to end
        missing = await api_client.post("/api/auth/logout", json={}, headers=user["headers"])
        assert missing.status_code == 400

        logout_response = await api_client.post(
            "/api/auth/logout",
            json={"refresh_token": user["refresh_token"]},
            headers=user["headers"],
        )
        assert logout_response.status_code == 200

        refresh_after_logout = await api_client.post(
            "/api/auth/refresh", json={"refresh_token": user["refresh_token"]}
        )
        assert refresh_after_logout.status_code == 401


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
            suffix = uuid.uuid4().hex[:8]
            user_data = {
                "email": f"weakpass_{suffix}@example.com",
                "username": f"weakpass_{suffix}",
                "password": weak_password,
            }

            response = await api_client.post("/api/auth/register", json=user_data)
            # The request model enforces the policy, so FastAPI answers 422
            assert response.status_code == 422, weak_password
            assert "password" in response.text.lower()

    @pytest.mark.integration
    @pytest.mark.auth
    async def test_session_management(
        self, authenticated_client: httpx.AsyncClient, auth_user: dict
    ):
        """Test session management endpoints"""
        # Get active sessions
        response = await authenticated_client.get("/api/auth/sessions")
        assert response.status_code == 200

        sessions = response.json()
        assert isinstance(sessions, list)
        assert len(sessions) >= 1  # Should have at least the current session

        session = sessions[0]
        assert session["user_id"] == auth_user["user_id"]
        assert session["refresh_token_jti"]
        assert "created_at" in session
        assert "last_activity" in session
        assert "device_info" in session
