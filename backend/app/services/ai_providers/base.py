"""
Base AI Provider Interface

This module defines the abstract base class that all AI providers must implement,
ensuring consistent behavior across different AI services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import time
from datetime import datetime


class AIProviderType(str, Enum):
    """Supported AI provider types"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure"
    LOCAL = "local"
    MOCK = "mock"


class AIProviderStatus(str, Enum):
    """AI provider status"""

    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"


class ModelCapability(str, Enum):
    """AI model capabilities"""

    TEXT_GENERATION = "text_generation"
    CONVERSATION = "conversation"
    CONTENT_CREATION = "content_creation"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"


class AIModelInfo(BaseModel):
    """Information about an AI model"""

    name: str
    display_name: str
    max_tokens: int
    cost_per_1k_input_tokens: float
    cost_per_1k_output_tokens: float
    capabilities: List[ModelCapability]
    context_window: int
    supports_streaming: bool = False
    supports_function_calling: bool = False


class AIUsageMetrics(BaseModel):
    """AI usage metrics for cost tracking"""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_input: float
    cost_output: float
    total_cost: float
    processing_time_ms: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("timestamp", mode="before")
    @classmethod
    def default_missing_timestamp(cls, value):
        return value or datetime.utcnow()


class AIResponse(BaseModel):
    """Standardized AI response format"""

    content: str
    provider: str
    model: str
    usage_metrics: AIUsageMetrics
    metadata: Dict[str, Any] = Field(default_factory=dict)
    finish_reason: Optional[str] = None


class AIProviderError(Exception):
    """Base exception for AI provider errors"""

    def __init__(self, message: str, provider: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.provider = provider
        self.error_code = error_code


class RateLimitError(AIProviderError):
    """Rate limit exceeded error"""

    def __init__(self, message: str, provider: str, retry_after: Optional[int] = None):
        super().__init__(message, provider, "rate_limit")
        self.retry_after = retry_after


class QuotaExceededError(AIProviderError):
    """Quota exceeded error"""

    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, "quota_exceeded")


class InvalidAPIKeyError(AIProviderError):
    """Invalid API key error"""

    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, "invalid_api_key")


class BaseAIProvider(ABC):
    """
    Abstract base class for all AI providers.

    This class defines the interface that all AI providers must implement,
    ensuring consistent behavior and easy switching between providers.
    """

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.provider_type = self.get_provider_type()
        self.status = AIProviderStatus.AVAILABLE
        self.last_error = None
        self.rate_limit_reset_time = None
        self.config = kwargs

        # Initialize provider-specific client
        self._initialize_client()

    @abstractmethod
    def get_provider_type(self) -> AIProviderType:
        """Return the provider type"""
        pass

    @abstractmethod
    def _initialize_client(self):
        """Initialize the provider-specific client"""
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> AIResponse:
        """
        Generate text using the AI provider

        Args:
            prompt: The input prompt
            model: Model to use (provider-specific)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Returns:
            AIResponse with generated text and metadata

        Raises:
            AIProviderError: If generation fails
            RateLimitError: If rate limited
            QuotaExceededError: If quota exceeded
        """
        pass

    @abstractmethod
    def get_available_models(self) -> List[AIModelInfo]:
        """Get list of available models for this provider"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model for this provider"""
        pass

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate cost for given token usage"""
        pass

    def is_available(self) -> bool:
        """Check if the provider is currently available"""
        if self.status == AIProviderStatus.RATE_LIMITED:
            if self.rate_limit_reset_time and time.time() >= self.rate_limit_reset_time:
                self.status = AIProviderStatus.AVAILABLE
                self.rate_limit_reset_time = None

        return self.status == AIProviderStatus.AVAILABLE

    def set_status(self, status: AIProviderStatus, error_message: Optional[str] = None):
        """Set provider status"""
        self.status = status
        if error_message:
            self.last_error = error_message

    def set_rate_limited(self, retry_after: Optional[int] = None):
        """Mark provider as rate limited"""
        self.status = AIProviderStatus.RATE_LIMITED
        if retry_after:
            self.rate_limit_reset_time = time.time() + retry_after

    def get_status_info(self) -> Dict[str, Any]:
        """Get current provider status information"""
        return {
            "provider": self.provider_type.value,
            "status": self.status.value,
            "is_available": self.is_available(),
            "last_error": self.last_error,
            "rate_limit_reset_time": self.rate_limit_reset_time,
            "supported_models": [model.name for model in self.get_available_models()],
        }

    def validate_api_key(self) -> bool:
        """Validate the API key (implement in subclasses)"""
        return bool(self.api_key)

    def _calculate_usage_metrics(
        self, model: str, input_tokens: int, output_tokens: int, processing_time_ms: int
    ) -> AIUsageMetrics:
        """Calculate usage metrics for cost tracking"""
        total_tokens = input_tokens + output_tokens

        # Get model info for cost calculation
        models = {m.name: m for m in self.get_available_models()}
        model_info = models.get(model)

        if model_info:
            cost_input = (input_tokens / 1000) * model_info.cost_per_1k_input_tokens
            cost_output = (output_tokens / 1000) * model_info.cost_per_1k_output_tokens
        else:
            # Fallback to default rates if model not found
            cost_input = (input_tokens / 1000) * 0.001  # $0.001 per 1K tokens
            cost_output = (output_tokens / 1000) * 0.002  # $0.002 per 1K tokens

        total_cost = cost_input + cost_output

        return AIUsageMetrics(
            provider=self.provider_type.value,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_input=cost_input,
            cost_output=cost_output,
            total_cost=total_cost,
            processing_time_ms=processing_time_ms,
            timestamp=datetime.utcnow(),
        )
