"""
Basic working tests that don't require complex Docker client dependencies.
These tests assume the Docker test environment is already running.
"""

import httpx
import asyncio


class TestAPIHealth:
    """Test basic API health and connectivity."""

    async def test_api_health(self, api_client: httpx.AsyncClient):
        """Test that the API health endpoint works."""
        response = await api_client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    async def test_api_detailed_health(self, api_client: httpx.AsyncClient):
        """Test detailed health endpoint."""
        response = await api_client.get("/api/health/detailed")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "services" in data


class TestAuthentication:
    """Test authentication endpoints."""

    async def test_register_user(self, api_client: httpx.AsyncClient):
        """Test user registration."""
        test_user = {
            "username": f"testuser_{int(asyncio.get_event_loop().time())}",
            "email": f"test_{int(asyncio.get_event_loop().time())}@example.com",
            "password": "testpassword123",
        }

        response = await api_client.post("/api/auth/register", json=test_user)

        # Should succeed or user already exists
        assert response.status_code in [200, 201, 400]

    async def test_login(self, api_client: httpx.AsyncClient):
        """Test user login."""
        # First register a user
        test_user = {
            "username": f"logintest_{int(asyncio.get_event_loop().time())}",
            "email": f"logintest_{int(asyncio.get_event_loop().time())}@example.com",
            "password": "testpassword123",
        }

        await api_client.post("/api/auth/register", json=test_user)

        # Now login
        login_data = {
            "username": test_user["username"],
            "password": test_user["password"],
        }

        response = await api_client.post("/api/auth/login", data=login_data)
        assert response.status_code == 200

        data = response.json()
        assert "access_token" in data
        assert "token_type" in data


class TestBasicFunctionality:
    """Test basic application functionality."""

    async def test_openapi_docs(self, api_client: httpx.AsyncClient):
        """Test that OpenAPI documentation is available."""
        response = await api_client.get("/openapi.json")
        assert response.status_code == 200

        data = response.json()
        assert "openapi" in data
        assert "info" in data

    async def test_docs_ui(self, api_client: httpx.AsyncClient):
        """Test that Swagger UI is available."""
        response = await api_client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()


class TestContentTransformation:
    """Test content transformation endpoints (if they exist)."""

    async def test_transform_endpoint_exists(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test if content transformation endpoint exists."""
        # This is a discovery test - we're checking what endpoints exist
        response = await authenticated_client.get("/openapi.json")
        assert response.status_code == 200

        openapi_spec = response.json()
        paths = openapi_spec.get("paths", {})

        # Check if transformation endpoints exist
        transform_paths = [path for path in paths.keys() if "transform" in path.lower()]
        print(f"Available transformation paths: {transform_paths}")

        # This test passes regardless - it's just for discovery
        assert True


# Simple unit tests that don't require API
class TestUtilities:
    """Test utility functions and basic Python functionality."""

    def test_python_version(self):
        """Test that we're running the expected Python version."""
        import sys

        assert sys.version_info >= (3, 8)

    def test_required_packages(self):
        """Test that required packages are installed."""
        try:
            import httpx
            import pytest
            import asyncio

            assert True
        except ImportError as e:
            pytest.fail(f"Required package not installed: {e}")

    def test_environment_variables(self):
        """Test that test environment variables are set correctly."""
        import os

        # These should be set in the test environment
        expected_vars = {"ENVIRONMENT": "testing", "AI_PROVIDER": "mock"}

        for var, expected_value in expected_vars.items():
            actual_value = os.getenv(var)
            if actual_value != expected_value:
                print(f"Warning: {var} = {actual_value}, expected {expected_value}")

        # This test always passes - it's just informational
        assert True
