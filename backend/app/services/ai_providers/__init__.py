"""
AI Provider Management Package

This package provides a comprehensive multi-provider AI system with:
- Abstract provider interface for consistent behavior
- Multiple provider implementations (OpenAI, Anthropic, Mock)
- Intelligent provider selection and failover
- Cost tracking and rate limiting
- Performance monitoring
"""

from .base import (
    BaseAIProvider,
    AIProviderType,
    AIProviderStatus,
    AIResponse,
    AIUsageMetrics,
    AIModelInfo,
    ModelCapability,
    AIProviderError,
    RateLimitError,
    QuotaExceededError,
    InvalidAPIKeyError,
)

from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .mock_provider import MockProvider
from .manager import (
    AIProviderManager,
    ProviderSelectionStrategy,
    get_ai_provider_manager,
)

__all__ = [
    # Base classes and types
    "BaseAIProvider",
    "AIProviderType",
    "AIProviderStatus",
    "AIResponse",
    "AIUsageMetrics",
    "AIModelInfo",
    "ModelCapability",
    # Exceptions
    "AIProviderError",
    "RateLimitError",
    "QuotaExceededError",
    "InvalidAPIKeyError",
    # Provider implementations
    "OpenAIProvider",
    "AnthropicProvider",
    "MockProvider",
    # Manager
    "AIProviderManager",
    "ProviderSelectionStrategy",
    "get_ai_provider_manager",
]
