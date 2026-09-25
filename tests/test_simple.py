"""
Simple connectivity tests to verify test environment
"""

import pytest
import httpx


@pytest.mark.unit
def test_basic_math():
    """Basic unit test to verify pytest works"""
    assert 2 + 2 == 4


@pytest.mark.integration
async def test_api_connectivity(api_client: httpx.AsyncClient):
    """Test basic API connectivity"""
    response = await api_client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "name" in data
    assert data["status"] == "ok"


@pytest.mark.integration
async def test_health_endpoint(api_client: httpx.AsyncClient):
    """Test health endpoint"""
    response = await api_client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.integration
async def test_detailed_health_endpoint(api_client: httpx.AsyncClient):
    """Test detailed health endpoint"""
    response = await api_client.get("/api/health/detailed")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "services" in data
