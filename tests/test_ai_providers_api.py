"""
Phase 7: AI Provider Management API Integration Tests

Tests for the AI provider management API endpoints including:
- Provider status and configuration
- Cost tracking and usage analytics
- Provider testing and validation
- Selection strategy management

These are INTEGRATION tests that test the API endpoints with a running server.
"""

import pytest
import asyncio
import httpx
import sys
import os

# Add backend to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


class TestAIProviderAPIEndpoints:
    """Test AI provider management API endpoints"""

    @pytest.mark.integration
    async def test_get_provider_status(self, authenticated_client: httpx.AsyncClient):
        """Test getting provider status"""
        response = await authenticated_client.get("/api/ai/providers/status")
        assert response.status_code == 200

        data = response.json()
        assert "providers" in data
        assert "selection_strategy" in data
        assert "total_providers" in data
        assert "available_providers" in data

        # Should have at least the mock provider
        assert data["total_providers"] >= 1
        assert "mock" in data["providers"]

        # Check provider structure
        mock_provider = data["providers"]["mock"]
        assert "provider_info" in mock_provider
        assert "configuration" in mock_provider
        assert "usage" in mock_provider
        assert "performance" in mock_provider

    @pytest.mark.integration
    async def test_get_cost_summary(self, authenticated_client: httpx.AsyncClient):
        """Test getting cost summary"""
        response = await authenticated_client.get("/api/ai/providers/costs")
        assert response.status_code == 200

        data = response.json()
        assert "summary" in data
        assert "period_hours" in data

        summary = data["summary"]
        assert "total" in summary
        assert "cost" in summary["total"]
        assert "requests" in summary["total"]

    @pytest.mark.integration
    async def test_get_cost_summary_custom_period(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test getting cost summary with custom time period"""
        response = await authenticated_client.get("/api/ai/providers/costs?hours=48")
        assert response.status_code == 200

        data = response.json()
        assert data["period_hours"] == 48

    @pytest.mark.integration
    async def test_test_provider(self, authenticated_client: httpx.AsyncClient):
        """Test testing a specific provider"""
        test_data = {
            "provider": "mock",
            "test_prompt": "Test AI provider functionality",
        }

        response = await authenticated_client.post(
            "/api/ai/providers/test", json=test_data
        )
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "provider" in data
        assert "model" in data
        assert "processing_time_ms" in data

        if data["success"]:
            assert "response_content" in data
            assert "usage_metrics" in data
            assert len(data["response_content"]) > 0
        else:
            assert "error_message" in data

    @pytest.mark.integration
    async def test_test_nonexistent_provider(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test testing a non-existent provider"""
        test_data = {"provider": "nonexistent", "test_prompt": "This should fail"}

        response = await authenticated_client.post(
            "/api/ai/providers/test", json=test_data
        )
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    @pytest.mark.integration
    async def test_validate_provider(self, authenticated_client: httpx.AsyncClient):
        """Test validating a specific provider"""
        response = await authenticated_client.post("/api/ai/providers/mock/validate")
        assert response.status_code == 200

        data = response.json()
        assert "provider" in data
        assert "valid" in data
        assert "message" in data
        assert data["provider"] == "mock"
        assert data["valid"] is True  # Mock provider should always validate

    @pytest.mark.integration
    async def test_validate_nonexistent_provider(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test validating a non-existent provider"""
        response = await authenticated_client.post(
            "/api/ai/providers/nonexistent/validate"
        )
        assert response.status_code == 404

    @pytest.mark.integration
    async def test_validate_all_providers(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test validating all providers"""
        response = await authenticated_client.post("/api/ai/providers/validate-all")
        assert response.status_code == 200

        data = response.json()
        assert "validation_results" in data
        assert "valid_providers" in data
        assert "invalid_providers" in data

        # Mock provider should be valid
        assert "mock" in data["validation_results"]
        assert data["validation_results"]["mock"] is True
        assert "mock" in data["valid_providers"]

    @pytest.mark.integration
    async def test_update_provider_config(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test updating provider configuration"""
        config_update = {
            "enabled": True,
            "priority": 2,
            "max_requests_per_minute": 100,
            "max_cost_per_hour": 20.0,
        }

        response = await authenticated_client.put(
            "/api/ai/providers/mock/config", json=config_update
        )
        assert response.status_code == 200

        data = response.json()
        assert "provider" in data
        assert "message" in data
        assert "config" in data
        assert data["provider"] == "mock"

        # Verify the configuration was updated
        config = data["config"]
        assert config["enabled"] == config_update["enabled"]
        assert config["priority"] == config_update["priority"]
        assert (
            config["max_requests_per_minute"]
            == config_update["max_requests_per_minute"]
        )
        assert config["max_cost_per_hour"] == config_update["max_cost_per_hour"]

    @pytest.mark.integration
    async def test_update_nonexistent_provider_config(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test updating configuration for non-existent provider"""
        config_update = {"enabled": False}

        response = await authenticated_client.put(
            "/api/ai/providers/nonexistent/config", json=config_update
        )
        assert response.status_code == 404

    @pytest.mark.integration
    async def test_update_selection_strategy(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test updating provider selection strategy"""
        strategies = ["primary_failover", "round_robin", "fastest", "least_cost"]

        for strategy in strategies:
            strategy_update = {"strategy": strategy}

            response = await authenticated_client.put(
                "/api/ai/providers/strategy", json=strategy_update
            )
            assert response.status_code == 200

            data = response.json()
            assert "message" in data
            assert "strategy" in data
            assert data["strategy"] == strategy

    @pytest.mark.integration
    async def test_update_invalid_selection_strategy(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test updating with invalid selection strategy"""
        strategy_update = {"strategy": "invalid_strategy"}

        response = await authenticated_client.put(
            "/api/ai/providers/strategy", json=strategy_update
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.integration
    async def test_get_available_models(self, authenticated_client: httpx.AsyncClient):
        """Test getting available models from all providers"""
        response = await authenticated_client.get("/api/ai/providers/models")
        assert response.status_code == 200

        data = response.json()
        assert "models_by_provider" in data
        assert "total_models" in data

        models = data["models_by_provider"]
        assert "mock" in models

        # Check mock provider models
        mock_models = models["mock"]
        assert len(mock_models) > 0

        for model in mock_models:
            assert "name" in model
            assert "display_name" in model
            assert "max_tokens" in model
            assert "cost_per_1k_input_tokens" in model
            assert "cost_per_1k_output_tokens" in model
            assert "capabilities" in model
            assert "context_window" in model

    @pytest.mark.integration
    async def test_reset_provider_limits(self, authenticated_client: httpx.AsyncClient):
        """Test resetting provider limits"""
        response = await authenticated_client.post(
            "/api/ai/providers/mock/reset-limits"
        )
        assert response.status_code == 200

        data = response.json()
        assert "provider" in data
        assert "message" in data
        assert data["provider"] == "mock"

    @pytest.mark.integration
    async def test_reset_nonexistent_provider_limits(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test resetting limits for non-existent provider"""
        response = await authenticated_client.post(
            "/api/ai/providers/nonexistent/reset-limits"
        )
        assert response.status_code == 404

    @pytest.mark.integration
    async def test_get_provider_statistics(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test getting detailed provider statistics"""
        response = await authenticated_client.get("/api/ai/providers/statistics")
        assert response.status_code == 200

        data = response.json()
        assert "overview" in data
        assert "usage_summary" in data
        assert "provider_details" in data

        overview = data["overview"]
        assert "total_providers" in overview
        assert "available_providers" in overview
        assert "current_strategy" in overview

        # Check provider details structure
        provider_details = data["provider_details"]
        assert "mock" in provider_details

        mock_details = provider_details["mock"]
        required_fields = [
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
        ]

        for field in required_fields:
            assert field in mock_details


class TestAIProviderAPIAuthentication:
    """Test API authentication for AI provider endpoints"""

    @pytest.mark.integration
    async def test_unauthenticated_access(self, async_client: httpx.AsyncClient):
        """Test that unauthenticated requests are rejected"""
        endpoints = [
            "/api/ai/providers/status",
            "/api/ai/providers/costs",
            "/api/ai/providers/models",
            "/api/ai/providers/statistics",
        ]

        for endpoint in endpoints:
            response = await async_client.get(endpoint)
            assert response.status_code == 401

    @pytest.mark.integration
    async def test_unauthenticated_post_requests(self, async_client: httpx.AsyncClient):
        """Test that unauthenticated POST requests are rejected"""
        endpoints = [
            ("/api/ai/providers/test", {"provider": "mock"}),
            ("/api/ai/providers/mock/validate", {}),
            ("/api/ai/providers/validate-all", {}),
            ("/api/ai/providers/mock/reset-limits", {}),
        ]

        for endpoint, data in endpoints:
            response = await async_client.post(endpoint, json=data)
            assert response.status_code == 401

    @pytest.mark.integration
    async def test_unauthenticated_put_requests(self, async_client: httpx.AsyncClient):
        """Test that unauthenticated PUT requests are rejected"""
        endpoints = [
            ("/api/ai/providers/mock/config", {"enabled": True}),
            ("/api/ai/providers/strategy", {"strategy": "round_robin"}),
        ]

        for endpoint, data in endpoints:
            response = await async_client.put(endpoint, json=data)
            assert response.status_code == 401


class TestAIProviderAPIErrorHandling:
    """Test error handling in AI provider API endpoints"""

    @pytest.mark.integration
    async def test_malformed_json_requests(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test handling of malformed JSON in requests"""
        # Test with invalid JSON for provider test
        response = await authenticated_client.post(
            "/api/ai/providers/test",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    @pytest.mark.integration
    async def test_missing_required_fields(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test handling of missing required fields"""
        # Test provider test without required provider field
        response = await authenticated_client.post(
            "/api/ai/providers/test",
            json={"test_prompt": "test"},  # Missing provider field
        )
        assert response.status_code == 422

    @pytest.mark.integration
    async def test_invalid_field_values(self, authenticated_client: httpx.AsyncClient):
        """Test handling of invalid field values"""
        # Test with invalid priority value
        response = await authenticated_client.put(
            "/api/ai/providers/mock/config",
            json={"priority": "invalid"},  # Should be integer
        )
        assert response.status_code == 422


class TestAIProviderAPIPerformance:
    """Performance tests for AI provider API endpoints"""

    @pytest.mark.integration
    async def test_concurrent_api_requests(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test handling of concurrent API requests"""
        # Create multiple concurrent requests
        tasks = []
        for _ in range(5):
            task = authenticated_client.get("/api/ai/providers/status")
            tasks.append(task)

        # Wait for all to complete
        responses = await asyncio.gather(*tasks)

        # Verify all succeeded
        for response in responses:
            assert response.status_code == 200

    @pytest.mark.integration
    async def test_api_response_times(self, authenticated_client: httpx.AsyncClient):
        """Test API response times are reasonable"""
        import time

        endpoints = [
            "/api/ai/providers/status",
            "/api/ai/providers/costs",
            "/api/ai/providers/models",
            "/api/ai/providers/statistics",
        ]

        for endpoint in endpoints:
            start_time = time.time()
            response = await authenticated_client.get(endpoint)
            end_time = time.time()

            assert response.status_code == 200
            assert (end_time - start_time) < 5.0  # Should respond within 5 seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
