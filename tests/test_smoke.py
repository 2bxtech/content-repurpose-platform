"""
Smoke tests: the test environment itself, plus basic reachability of the API.

Consolidates the former test_simple.py, test_basic.py and test_smoke.py.
"""

import os
import sys

import httpx
import pytest


class TestFrameworkSetup:
    """The test environment is wired up the way conftest.py promises."""

    @pytest.mark.unit
    def test_python_version(self):
        assert sys.version_info >= (3, 11), "Python 3.11+ is required"

    @pytest.mark.unit
    def test_project_structure(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        for file_path in [
            "backend/main.py",
            "backend/requirements.txt",
            "docker-compose.yml",
            "Makefile",
        ]:
            assert os.path.exists(os.path.join(project_root, file_path)), file_path

    @pytest.mark.unit
    async def test_async_support(self):
        import asyncio

        assert await asyncio.sleep(0.01, result="async_works") == "async_works"

    @pytest.mark.unit
    def test_environment_variables(self):
        """Set by conftest.py before the app is imported."""
        assert os.environ.get("ENVIRONMENT") == "testing"
        assert os.environ.get("DEBUG") == "true"
        assert os.environ.get("SECRET_KEY")
        assert os.environ.get("REFRESH_SECRET_KEY")

    @pytest.mark.unit
    def test_app_imports(self):
        from main import app

        paths = app.openapi()["paths"]
        assert "/api/health" in paths
        assert "/api/auth/token" in paths


@pytest.mark.integration
class TestAPIReachability:
    """The running API answers on its public, unauthenticated endpoints."""

    async def test_root(self, api_client: httpx.AsyncClient):
        response = await api_client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "content-repurpose-api"
        assert data["version"]

    async def test_health(self, api_client: httpx.AsyncClient):
        """/api/health reports dependency status (replaces /api/health/detailed)."""
        response = await api_client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        checks = data["checks"]
        assert checks["database"]["status"] == "healthy"
        assert checks["redis"]["status"] == "healthy"
        assert "mock" in checks["ai_provider"]["providers"]

    async def test_openapi_schema(self, api_client: httpx.AsyncClient):
        response = await api_client.get("/openapi.json")
        assert response.status_code == 200

        spec = response.json()
        assert "openapi" in spec
        assert "info" in spec
        assert "/api/transformations" in spec["paths"]

    async def test_docs_ui(self, api_client: httpx.AsyncClient):
        """Swagger UI is served while DEBUG is on (the dev/test stack)."""
        response = await api_client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()
