"""
AI provider management API (/api/providers/*).

Most endpoints are operator-only (require_platform_admin) and act on the in-process
provider manager, so their behaviour is tested in-process with the admin dependency
overridden. The live stack is used to check who may call them.
"""

import asyncio
import copy
import time

import httpx
import pytest

from app.api.routes.auth import require_platform_admin
from app.services.ai_providers import get_ai_provider_manager

ADMIN_GET_ENDPOINTS = [
    "/api/providers/status",
    "/api/providers/costs",
    "/api/providers/statistics",
]
ADMIN_POST_ENDPOINTS = [
    ("/api/providers/test", {"provider": "mock"}),
    ("/api/providers/mock/validate", {}),
    ("/api/providers/validate-all", {}),
    ("/api/providers/mock/reset-limits", {}),
]
ADMIN_PUT_ENDPOINTS = [
    ("/api/providers/mock/config", {"enabled": True}),
    ("/api/providers/strategy", {"strategy": "round_robin"}),
]


@pytest.fixture
def admin_client(unit_client, fake_user):
    """In-process client whose user passes the platform-admin gate.

    Restores the shared provider manager's config and strategy afterwards.
    """
    from main import app

    manager = get_ai_provider_manager()
    saved_configs = copy.deepcopy(manager.provider_configs)
    saved_strategy = manager.selection_strategy

    app.dependency_overrides[require_platform_admin] = lambda: fake_user
    try:
        yield unit_client
    finally:
        manager.provider_configs.clear()
        manager.provider_configs.update(saved_configs)
        manager.set_selection_strategy(saved_strategy)


@pytest.mark.unit
class TestAIProviderAPIEndpoints:
    """Endpoint behaviour for a platform admin"""

    def test_get_provider_status(self, admin_client):
        response = admin_client.get("/api/providers/status")
        assert response.status_code == 200

        data = response.json()
        assert data["total_providers"] >= 1
        assert data["available_providers"] >= 1
        assert data["selection_strategy"]
        mock_provider = data["providers"]["mock"]
        for section in ("provider_info", "configuration", "usage", "performance"):
            assert section in mock_provider

    def test_get_cost_summary(self, admin_client):
        response = admin_client.get("/api/providers/costs")
        assert response.status_code == 200

        data = response.json()
        assert data["period_hours"] == 24
        assert "cost" in data["summary"]["total"]
        assert "requests" in data["summary"]["total"]

    def test_get_cost_summary_custom_period(self, admin_client):
        response = admin_client.get("/api/providers/costs?hours=48")
        assert response.status_code == 200
        assert response.json()["period_hours"] == 48

    def test_test_provider(self, admin_client):
        response = admin_client.post(
            "/api/providers/test", json={"provider": "mock", "test_prompt": "Test AI provider functionality"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "mock"
        assert data["model"]
        assert data["processing_time_ms"] >= 0
        assert data["response_content"]
        assert {"input_tokens", "output_tokens", "total_cost"} <= set(data["usage_metrics"])

    def test_test_nonexistent_provider(self, admin_client):
        response = admin_client.post("/api/providers/test", json={"provider": "nonexistent"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_validate_provider(self, admin_client):
        response = admin_client.post("/api/providers/mock/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "mock"
        assert data["valid"] is True
        assert data["message"]

    def test_validate_nonexistent_provider(self, admin_client):
        assert admin_client.post("/api/providers/nonexistent/validate").status_code == 404

    def test_validate_all_providers(self, admin_client, monkeypatch):
        # Keep real providers from making network calls with whatever keys are configured
        manager = get_ai_provider_manager()

        async def only_mock():
            return {name: name == "mock" for name in manager.providers}

        monkeypatch.setattr(manager, "validate_all_providers", only_mock)

        response = admin_client.post("/api/providers/validate-all")
        assert response.status_code == 200

        data = response.json()
        assert data["validation_results"]["mock"] is True
        assert "mock" in data["valid_providers"]
        assert "mock" not in data["invalid_providers"]

    def test_update_provider_config(self, admin_client):
        config_update = {
            "enabled": True,
            "priority": 2,
            "max_requests_per_minute": 100,
            "max_cost_per_hour": 20.0,
        }
        response = admin_client.put("/api/providers/mock/config", json=config_update)
        assert response.status_code == 200

        data = response.json()
        assert data["provider"] == "mock"
        assert data["config"] == config_update
        assert get_ai_provider_manager().provider_configs["mock"].priority == 2

    def test_update_nonexistent_provider_config(self, admin_client):
        response = admin_client.put("/api/providers/nonexistent/config", json={"enabled": False})
        assert response.status_code == 404

    def test_update_selection_strategy(self, admin_client):
        for strategy in ["primary_failover", "round_robin", "fastest", "least_cost"]:
            response = admin_client.put("/api/providers/strategy", json={"strategy": strategy})
            assert response.status_code == 200
            assert response.json()["strategy"] == strategy
            assert get_ai_provider_manager().selection_strategy.value == strategy

    def test_update_invalid_selection_strategy(self, admin_client):
        response = admin_client.put("/api/providers/strategy", json={"strategy": "invalid_strategy"})
        assert response.status_code == 422

    def test_get_available_models(self, admin_client):
        response = admin_client.get("/api/providers/models")
        assert response.status_code == 200

        data = response.json()
        models = data["models_by_provider"]
        assert data["total_models"] == sum(len(m) for m in models.values())
        assert models["mock"]
        for model in models["mock"]:
            for field in (
                "name",
                "display_name",
                "max_tokens",
                "cost_per_1k_input_tokens",
                "cost_per_1k_output_tokens",
                "capabilities",
                "context_window",
            ):
                assert field in model

    def test_reset_provider_limits(self, admin_client):
        manager = get_ai_provider_manager()
        manager.usage_trackers["mock"].requests_per_minute.append(time.time())

        response = admin_client.post("/api/providers/mock/reset-limits")
        assert response.status_code == 200
        assert response.json()["provider"] == "mock"
        assert len(manager.usage_trackers["mock"].requests_per_minute) == 0

    def test_reset_nonexistent_provider_limits(self, admin_client):
        assert admin_client.post("/api/providers/nonexistent/reset-limits").status_code == 404

    def test_get_provider_statistics(self, admin_client):
        response = admin_client.get("/api/providers/statistics")
        assert response.status_code == 200

        data = response.json()
        overview = data["overview"]
        assert overview["total_providers"] >= 1
        assert "available_providers" in overview
        assert "current_strategy" in overview
        assert "usage_summary" in data

        mock_details = data["provider_details"]["mock"]
        for field in [
            "type",
            "status",
            "is_available",
            "enabled",
            "priority",
            "total_requests",
            "total_cost",
            "average_response_time",
            "success_rate",
            "available_models",
            "default_model",
        ]:
            assert field in mock_details


@pytest.mark.unit
class TestAIProviderAPIErrorHandling:
    """Request validation"""

    def test_malformed_json_requests(self, admin_client):
        response = admin_client.post(
            "/api/providers/test", content="invalid json", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_missing_required_fields(self, admin_client):
        response = admin_client.post("/api/providers/test", json={"test_prompt": "test"})
        assert response.status_code == 422

    def test_invalid_field_values(self, admin_client):
        response = admin_client.put("/api/providers/mock/config", json={"priority": "invalid"})
        assert response.status_code == 422


@pytest.mark.unit
class TestAIProviderAPIAuthorization:
    """Members are refused operator endpoints; the model catalogue is open to them"""

    def test_member_gets_403_on_operator_endpoints(self, unit_client):
        for endpoint in ADMIN_GET_ENDPOINTS:
            assert unit_client.get(endpoint).status_code == 403, endpoint
        for endpoint, body in ADMIN_POST_ENDPOINTS:
            assert unit_client.post(endpoint, json=body).status_code == 403, endpoint
        for endpoint, body in ADMIN_PUT_ENDPOINTS:
            assert unit_client.put(endpoint, json=body).status_code == 403, endpoint

    def test_member_can_list_models(self, unit_client):
        assert unit_client.get("/api/providers/models").status_code == 200


@pytest.mark.integration
class TestAIProviderAPIAuthentication:
    """Access control on the running stack"""

    async def test_unauthenticated_access(self, api_client: httpx.AsyncClient):
        for endpoint in ADMIN_GET_ENDPOINTS + ["/api/providers/models"]:
            response = await api_client.get(endpoint)
            assert response.status_code == 401, endpoint

    async def test_unauthenticated_post_requests(self, api_client: httpx.AsyncClient):
        for endpoint, data in ADMIN_POST_ENDPOINTS:
            response = await api_client.post(endpoint, json=data)
            assert response.status_code == 401, endpoint

    async def test_unauthenticated_put_requests(self, api_client: httpx.AsyncClient):
        for endpoint, data in ADMIN_PUT_ENDPOINTS:
            response = await api_client.put(endpoint, json=data)
            assert response.status_code == 401, endpoint

    async def test_regular_user_is_not_platform_admin(self, authenticated_client: httpx.AsyncClient):
        for endpoint in ADMIN_GET_ENDPOINTS:
            assert (await authenticated_client.get(endpoint)).status_code == 403, endpoint
        for endpoint, data in ADMIN_POST_ENDPOINTS:
            assert (await authenticated_client.post(endpoint, json=data)).status_code == 403, endpoint
        for endpoint, data in ADMIN_PUT_ENDPOINTS:
            assert (await authenticated_client.put(endpoint, json=data)).status_code == 403, endpoint

    async def test_models_available_to_members(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.get("/api/providers/models")
        assert response.status_code == 200
        assert response.json()["models_by_provider"]["mock"]

    async def test_concurrent_api_requests(self, authenticated_client: httpx.AsyncClient):
        responses = await asyncio.gather(
            *[authenticated_client.get("/api/providers/models") for _ in range(5)]
        )
        assert [r.status_code for r in responses] == [200] * 5

    async def test_api_response_times(self, authenticated_client: httpx.AsyncClient):
        start_time = time.time()
        response = await authenticated_client.get("/api/providers/models")
        assert response.status_code == 200
        assert time.time() - start_time < 5.0
