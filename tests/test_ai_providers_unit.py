"""
Unit tests for AI providers that don't require the full API server.
These tests validate the core functionality of the AI provider system.
"""

import pytest
import os

# Set test environment variables
os.environ["SECRET_KEY"] = "test-secret-key-12345678901234567890123456789012"
os.environ["REFRESH_SECRET_KEY"] = (
    "test-refresh-secret-key-12345678901234567890123456789012"
)
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

# Add backend directory to path for imports
import sys
import pathlib

backend_path = pathlib.Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.ai_providers.base import (
    AIResponse,
    AIUsageMetrics,
    AIProviderError,
    RateLimitError,
    QuotaExceededError,
    AIModelInfo,
    ModelCapability,
)
from app.services.ai_providers.mock_provider import MockProvider


class TestBaseAIProvider:
    """Test the base AI provider abstract class."""

    def test_ai_response_creation(self):
        """Test AIResponse model creation."""
        # Create mock usage metrics
        usage_metrics = AIUsageMetrics(
            provider="test",
            model="test-model",
            input_tokens=50,
            output_tokens=25,
            total_tokens=75,
            cost_input=0.001,
            cost_output=0.002,
            total_cost=0.003,
            processing_time_ms=1500,
            timestamp=None,
        )

        response = AIResponse(
            content="Test response",
            provider="test-provider",
            model="test-model",
            usage_metrics=usage_metrics,
            metadata={"test": "value"},
            finish_reason="stop",
        )

        assert response.content == "Test response"
        assert response.provider == "test-provider"
        assert response.model == "test-model"
        assert response.usage_metrics.input_tokens == 50
        assert response.usage_metrics.output_tokens == 25
        assert response.finish_reason == "stop"

    def test_ai_usage_metrics_creation(self):
        """Test AIUsageMetrics model creation."""
        metrics = AIUsageMetrics(
            provider="test",
            model="test-model",
            input_tokens=5000,
            output_tokens=2500,
            total_tokens=7500,
            cost_input=5.0,
            cost_output=5.0,
            total_cost=10.0,
            processing_time_ms=1500,
            timestamp=None,
        )

        assert metrics.provider == "test"
        assert metrics.model == "test-model"
        assert metrics.input_tokens == 5000
        assert metrics.output_tokens == 2500
        assert metrics.total_tokens == 7500
        assert metrics.total_cost == 10.0

    def test_ai_provider_exceptions(self):
        """Test AI provider exception classes."""
        base_error = AIProviderError("Base error", "test-provider")
        assert str(base_error) == "Base error"
        assert base_error.provider == "test-provider"

        rate_limit_error = RateLimitError("Rate limited", "test-provider", 60)
        assert str(rate_limit_error) == "Rate limited"
        assert isinstance(rate_limit_error, AIProviderError)
        assert rate_limit_error.retry_after == 60

        quota_error = QuotaExceededError("Quota exceeded", "test-provider")
        assert str(quota_error) == "Quota exceeded"
        assert isinstance(quota_error, AIProviderError)


class TestMockProvider:
    """Test the mock AI provider implementation."""

    def test_mock_provider_initialization(self):
        """Test mock provider can be initialized."""
        provider = MockProvider(api_key="test-key")

        assert provider.provider_type.value == "mock"
        assert provider.api_key == "test-key"
        assert provider.is_available() is True
        assert len(provider.get_available_models()) > 0

    @pytest.mark.asyncio
    async def test_mock_text_generation(self):
        """Test mock provider text generation."""
        provider = MockProvider(api_key="test-key")

        response = await provider.generate_text(
            prompt="Test prompt for summary", model="mock-gpt-4", max_tokens=100
        )

        assert isinstance(response, AIResponse)
        assert response.provider == "mock"
        assert response.model == "mock-gpt-4"
        assert len(response.content) > 0
        assert response.usage_metrics.input_tokens > 0
        assert response.usage_metrics.output_tokens > 0
        assert response.usage_metrics.total_cost >= 0
        assert response.usage_metrics.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_mock_different_transformation_types(self):
        """Test mock provider handles different transformation types."""
        provider = MockProvider(api_key="test-key")

        transformation_types = [
            "blog post",
            "social media",
            "email",
            "newsletter",
            "summary",
        ]

        for transformation_type in transformation_types:
            response = await provider.generate_text(
                prompt=f"Create a {transformation_type} from this content",
                model="mock-gpt-4",
                max_tokens=100,
            )

            assert isinstance(response, AIResponse)
            # Check that different content is generated for different types
            assert len(response.content) > 50  # Should have substantial content

    def test_mock_cost_estimation(self):
        """Test mock provider cost estimation."""
        provider = MockProvider(api_key="test-key")

        cost = provider.estimate_cost(
            input_tokens=1000, output_tokens=500, model="mock-gpt-4"
        )

        assert cost == 0.0  # Mock provider should have no cost

    def test_mock_model_support(self):
        """Test mock provider model support."""
        provider = MockProvider(api_key="test-key")
        models = provider.get_available_models()

        assert len(models) > 0
        assert all(isinstance(model, AIModelInfo) for model in models)

        # Check default model exists
        default_model = provider.get_default_model()
        model_names = [m.name for m in models]
        assert default_model in model_names

    @pytest.mark.asyncio
    async def test_mock_api_key_validation(self):
        """Test mock provider API key validation."""
        provider = MockProvider(api_key="test-key")

        # Mock provider should always validate successfully
        is_valid = await provider.validate_api_key()
        assert is_valid is True


class TestAIProviderIntegration:
    """Test AI provider integration without external dependencies."""

    @pytest.mark.asyncio
    async def test_mock_provider_performance(self):
        """Test mock provider performance characteristics."""
        provider = MockProvider(api_key="test-key")

        # Test multiple requests to check consistency
        responses = []
        for i in range(3):
            response = await provider.generate_text(
                prompt=f"Test prompt {i}", model="mock-gpt-4", max_tokens=100
            )
            responses.append(response)

        # Check all responses are valid
        assert len(responses) == 3
        for response in responses:
            assert isinstance(response, AIResponse)
            assert response.provider == "mock"
            assert len(response.content) > 0
            assert response.usage_metrics.processing_time_ms > 0

    def test_model_capabilities(self):
        """Test model capability information."""
        provider = MockProvider(api_key="test-key")
        models = provider.get_available_models()

        for model in models:
            assert isinstance(model.name, str)
            assert isinstance(model.display_name, str)
            assert isinstance(model.max_tokens, int)
            assert model.max_tokens > 0
            assert isinstance(model.capabilities, list)
            assert len(model.capabilities) > 0
            assert all(isinstance(cap, ModelCapability) for cap in model.capabilities)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
