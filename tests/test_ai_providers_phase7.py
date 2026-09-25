"""
Phase 7: AI Provider Management Tests

Tests for multi-provider AI support with intelligent failover, cost tracking,
and provider selection strategies. These tests cover:

1. Provider Interface Implementation
2. Provider Manager Functionality
3. Failover Logic
4. Cost Tracking
5. Rate Limiting
6. API Endpoints

These are UNIT and INTEGRATION tests that test the AI provider system.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
import sys
import os

# Add backend to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.ai_providers import (
    AIProviderType,
    AIProviderStatus,
    AIResponse,
    AIUsageMetrics,
    AIModelInfo,
    AIProviderError,
    OpenAIProvider,
    AnthropicProvider,
    MockProvider,
    AIProviderManager,
    ProviderSelectionStrategy,
    get_ai_provider_manager,
)


class TestAIProviderBase:
    """Test the base AI provider interface"""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider for testing"""
        return MockProvider(api_key="test-key")

    def test_provider_initialization(self, mock_provider):
        """Test provider initialization"""
        assert mock_provider.api_key == "test-key"
        assert mock_provider.provider_type == AIProviderType.MOCK
        assert mock_provider.status == AIProviderStatus.AVAILABLE
        assert mock_provider.is_available() is True

    def test_provider_status_management(self, mock_provider):
        """Test provider status management"""
        # Test rate limiting
        mock_provider.set_rate_limited(retry_after=60)
        assert mock_provider.status == AIProviderStatus.RATE_LIMITED
        assert mock_provider.is_available() is False

        # Test error status
        mock_provider.set_status(AIProviderStatus.ERROR, "Test error")
        assert mock_provider.status == AIProviderStatus.ERROR
        assert mock_provider.last_error == "Test error"
        assert mock_provider.is_available() is False

        # Test recovery
        mock_provider.set_status(AIProviderStatus.AVAILABLE)
        assert mock_provider.is_available() is True

    def test_provider_models(self, mock_provider):
        """Test provider model information"""
        models = mock_provider.get_available_models()
        assert len(models) > 0

        default_model = mock_provider.get_default_model()
        assert isinstance(default_model, str)
        assert len(default_model) > 0

        # Test model capabilities
        for model in models:
            assert isinstance(model, AIModelInfo)
            assert len(model.capabilities) > 0
            assert model.max_tokens > 0

    def test_cost_estimation(self, mock_provider):
        """Test cost estimation"""
        cost = mock_provider.estimate_cost(1000, 500, "mock-gpt-4")
        assert isinstance(cost, float)
        assert cost >= 0.0  # Mock provider should return 0 cost


class TestMockProvider:
    """Test the mock provider implementation"""

    @pytest.fixture
    def mock_provider(self):
        return MockProvider(api_key="test-key")

    @pytest.mark.asyncio
    async def test_text_generation(self, mock_provider):
        """Test mock text generation"""
        prompt = "Transform this content into a blog post"

        response = await mock_provider.generate_text(prompt)

        assert isinstance(response, AIResponse)
        assert len(response.content) > 0
        assert response.provider == "mock"
        assert response.model in ["mock-gpt-4", "mock-claude"]
        assert response.usage_metrics.total_tokens > 0
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_different_transformation_types(self, mock_provider):
        """Test mock responses for different transformation types"""
        test_cases = [
            ("blog post", "blog"),
            ("social media", "social"),
            ("email sequence", "email"),
            ("newsletter", "newsletter"),
            ("summary", "summary"),
        ]

        for prompt_type, expected_content_type in test_cases:
            prompt = f"Transform this into a {prompt_type}"
            response = await mock_provider.generate_text(prompt)

            assert len(response.content) > 100  # Substantial content
            assert expected_content_type.lower() in response.content.lower()

    @pytest.mark.asyncio
    async def test_mock_processing_time(self, mock_provider):
        """Test that mock provider simulates realistic processing time"""
        start_time = time.time()

        await mock_provider.generate_text("test prompt")

        elapsed = time.time() - start_time
        assert elapsed >= 0.5  # Should take at least 0.5 seconds
        assert elapsed <= 3.0  # But not more than 3 seconds

    @pytest.mark.asyncio
    async def test_api_key_validation(self, mock_provider):
        """Test API key validation for mock provider"""
        is_valid = await mock_provider.validate_api_key()
        assert is_valid is True  # Mock provider always validates


class TestOpenAIProvider:
    """Test OpenAI provider implementation"""

    @pytest.fixture
    def openai_provider(self):
        return OpenAIProvider(api_key="test-openai-key")

    def test_openai_initialization(self, openai_provider):
        """Test OpenAI provider initialization"""
        assert openai_provider.provider_type == AIProviderType.OPENAI
        assert openai_provider.api_key == "test-openai-key"

    def test_openai_models(self, openai_provider):
        """Test OpenAI model information"""
        models = openai_provider.get_available_models()
        model_names = [m.name for m in models]

        assert "gpt-4o" in model_names
        assert "gpt-4o-mini" in model_names
        assert "gpt-3.5-turbo" in model_names

        default_model = openai_provider.get_default_model()
        assert default_model == "gpt-4o-mini"

    def test_openai_cost_estimation(self, openai_provider):
        """Test OpenAI cost estimation"""
        # Test with gpt-4o-mini (should be cheapest)
        cost_mini = openai_provider.estimate_cost(1000, 500, "gpt-4o-mini")

        # Test with gpt-4o (should be more expensive)
        cost_regular = openai_provider.estimate_cost(1000, 500, "gpt-4o")

        assert cost_mini > 0
        assert cost_regular > cost_mini

    @pytest.mark.asyncio
    async def test_openai_error_handling(self, openai_provider):
        """Test OpenAI error handling"""
        with patch.object(openai_provider, "client") as mock_client:
            # Test rate limit error
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("Rate limit exceeded")
            )

            with pytest.raises(AIProviderError):
                await openai_provider.generate_text("test prompt")


class TestAnthropicProvider:
    """Test Anthropic provider implementation"""

    @pytest.fixture
    def anthropic_provider(self):
        return AnthropicProvider(api_key="test-claude-key")

    def test_anthropic_initialization(self, anthropic_provider):
        """Test Anthropic provider initialization"""
        assert anthropic_provider.provider_type == AIProviderType.ANTHROPIC
        assert anthropic_provider.api_key == "test-claude-key"

    def test_anthropic_models(self, anthropic_provider):
        """Test Anthropic model information"""
        models = anthropic_provider.get_available_models()
        model_names = [m.name for m in models]

        assert "claude-3-5-sonnet-20241022" in model_names
        assert "claude-3-haiku-20240307" in model_names
        assert "claude-3-opus-20240229" in model_names

        default_model = anthropic_provider.get_default_model()
        assert default_model == "claude-3-5-sonnet-20241022"

    def test_anthropic_cost_estimation(self, anthropic_provider):
        """Test Anthropic cost estimation"""
        # Test with Haiku (should be cheapest)
        cost_haiku = anthropic_provider.estimate_cost(
            1000, 500, "claude-3-haiku-20240307"
        )

        # Test with Opus (should be most expensive)
        cost_opus = anthropic_provider.estimate_cost(
            1000, 500, "claude-3-opus-20240229"
        )

        assert cost_haiku > 0
        assert cost_opus > cost_haiku


class TestAIProviderManager:
    """Test the AI provider manager"""

    @pytest.fixture
    def manager(self):
        """Create a test manager with mock providers"""
        manager = AIProviderManager(redis_client=None)
        return manager

    def test_manager_initialization(self, manager):
        """Test manager initialization"""
        assert len(manager.providers) > 0
        assert "mock" in manager.providers
        assert manager.selection_strategy in ProviderSelectionStrategy

    def test_provider_discovery(self, manager):
        """Test provider discovery and configuration"""
        status = manager.get_provider_status()

        assert isinstance(status, dict)
        assert len(status) > 0

        # Mock provider should always be available
        assert "mock" in status
        assert status["mock"]["provider_info"]["is_available"] is True

    @pytest.mark.asyncio
    async def test_text_generation_with_fallback(self, manager):
        """Test text generation with provider fallback"""
        # Test with mock provider (should always work)
        response = await manager.generate_text(
            prompt="Test prompt", preferred_provider="mock"
        )

        assert isinstance(response, AIResponse)
        assert len(response.content) > 0
        assert response.provider == "mock"

    @pytest.mark.asyncio
    async def test_provider_selection_strategies(self, manager):
        """Test different provider selection strategies"""
        strategies = [
            ProviderSelectionStrategy.PRIMARY_FAILOVER,
            ProviderSelectionStrategy.ROUND_ROBIN,
            ProviderSelectionStrategy.FASTEST,
        ]

        for strategy in strategies:
            manager.set_selection_strategy(strategy)
            assert manager.selection_strategy == strategy

            # Test that generation still works
            response = await manager.generate_text("test prompt")
            assert isinstance(response, AIResponse)

    def test_usage_tracking(self, manager):
        """Test usage tracking and cost management"""
        # Create a mock response
        usage_metrics = AIUsageMetrics(
            provider="mock",
            model="mock-gpt-4",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_input=0.01,
            cost_output=0.02,
            total_cost=0.03,
            processing_time_ms=1000,
            timestamp=datetime.utcnow(),
        )

        # Track usage
        asyncio.run(
            manager._track_usage("mock", MagicMock(usage_metrics=usage_metrics), 1.0)
        )

        # Check usage was recorded
        tracker = manager.usage_trackers["mock"]
        assert tracker.total_requests > 0
        assert tracker.total_cost > 0

    def test_cost_summary(self, manager):
        """Test cost summary generation"""
        summary = manager.get_cost_summary(hours=24)

        assert isinstance(summary, dict)
        assert "total" in summary
        assert "cost" in summary["total"]
        assert "requests" in summary["total"]

    def test_rate_limiting(self, manager):
        """Test rate limiting functionality"""
        provider_name = "mock"
        config = manager.provider_configs[provider_name]

        # Simulate reaching rate limit
        tracker = manager.usage_trackers[provider_name]
        current_time = time.time()

        # Fill up the rate limit
        for _ in range(config.max_requests_per_minute):
            tracker.requests_per_minute.append(current_time)

        # Should now be rate limited
        assert not manager._can_use_provider(provider_name)

    @pytest.mark.asyncio
    async def test_api_key_validation(self, manager):
        """Test API key validation for all providers"""
        results = await manager.validate_all_providers()

        assert isinstance(results, dict)
        assert len(results) > 0

        # Mock provider should always validate
        assert "mock" in results
        assert results["mock"] is True


class TestAIProviderIntegration:
    """Integration tests for AI provider system"""

    @pytest.mark.asyncio
    async def test_provider_manager_singleton(self):
        """Test that get_ai_provider_manager returns singleton"""
        manager1 = get_ai_provider_manager()
        manager2 = get_ai_provider_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_end_to_end_transformation(self):
        """Test complete transformation flow using provider manager"""
        manager = get_ai_provider_manager()

        test_prompts = [
            "Transform this text into a blog post: 'AI is transforming content creation'",
            "Create social media posts from: 'New product launch announcement'",
            "Summarize this content: 'Long technical documentation about APIs'",
        ]

        for prompt in test_prompts:
            response = await manager.generate_text(prompt)

            assert isinstance(response, AIResponse)
            assert len(response.content) > 50  # Substantial response
            assert response.usage_metrics.total_tokens > 0
            assert response.usage_metrics.total_cost >= 0

    def test_provider_configuration_updates(self):
        """Test dynamic provider configuration updates"""
        manager = get_ai_provider_manager()

        # Get original config
        original_config = manager.provider_configs["mock"]
        original_enabled = original_config.enabled

        # Update configuration
        original_config.enabled = not original_enabled

        # Verify update
        assert manager.provider_configs["mock"].enabled == (not original_enabled)

        # Restore original
        original_config.enabled = original_enabled

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self):
        """Test error handling and provider recovery"""
        manager = get_ai_provider_manager()

        # Test with invalid provider
        with pytest.raises(AIProviderError):
            await manager.generate_text("test", preferred_provider="nonexistent")

        # Test normal operation after error
        response = await manager.generate_text("test prompt")
        assert isinstance(response, AIResponse)


class TestAIProviderPerformance:
    """Performance tests for AI provider system"""

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        manager = get_ai_provider_manager()

        # Create multiple concurrent requests
        tasks = []
        for i in range(5):
            task = manager.generate_text(f"Test prompt {i}")
            tasks.append(task)

        # Wait for all to complete
        responses = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert len(responses) == 5
        for response in responses:
            assert isinstance(response, AIResponse)
            assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_response_time_tracking(self):
        """Test response time tracking"""
        manager = get_ai_provider_manager()

        start_time = time.time()
        response = await manager.generate_text("Quick test prompt")
        end_time = time.time()

        processing_time = end_time - start_time

        # Verify response time is reasonable
        assert processing_time < 10.0  # Should complete within 10 seconds
        assert response.usage_metrics.processing_time_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
