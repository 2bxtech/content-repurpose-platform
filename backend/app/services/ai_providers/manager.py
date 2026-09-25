"""
AI Provider Manager

Centralized management for multiple AI providers with intelligent routing,
failover handling, cost tracking, and rate limiting.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json
import redis
from enum import Enum

from app.core.config import settings
from .base import (
    BaseAIProvider,
    AIProviderType,
    AIResponse,
    AIUsageMetrics,
    AIProviderError,
    RateLimitError,
    QuotaExceededError,
)
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .mock_provider import MockProvider


logger = logging.getLogger(__name__)


class ProviderSelectionStrategy(str, Enum):
    """Provider selection strategies"""

    ROUND_ROBIN = "round_robin"
    LEAST_COST = "least_cost"
    FASTEST = "fastest"
    PRIMARY_FAILOVER = "primary_failover"
    LOAD_BALANCED = "load_balanced"


@dataclass
class ProviderConfig:
    """Configuration for a single AI provider"""

    provider_type: AIProviderType
    api_key: str
    enabled: bool = True
    priority: int = 1  # Lower number = higher priority
    max_requests_per_minute: int = 60
    max_cost_per_hour: float = 10.0
    preferred_models: List[str] = field(default_factory=list)
    fallback_models: List[str] = field(default_factory=list)


@dataclass
class UsageTracker:
    """Track usage for rate limiting and cost management"""

    requests_per_minute: deque = field(default_factory=deque)
    costs_per_hour: deque = field(
        default_factory=lambda: deque(maxlen=3600)
    )  # Store more cost entries
    total_requests: int = 0
    total_cost: float = 0.0
    last_request_time: Optional[datetime] = None


class AIProviderManager:
    """
    Manages multiple AI providers with intelligent routing and failover
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.providers: Dict[str, BaseAIProvider] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        self.usage_trackers: Dict[str, UsageTracker] = defaultdict(UsageTracker)
        self.redis_client = redis_client
        self.selection_strategy = ProviderSelectionStrategy.PRIMARY_FAILOVER
        self.provider_rotation_index = 0

        # Performance tracking
        self.provider_performance: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"avg_response_time": 0.0, "success_rate": 1.0, "total_requests": 0}
        )

        # Initialize providers based on configuration
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize AI providers based on configuration"""
        # OpenAI provider
        if settings.OPENAI_API_KEY:
            self.provider_configs["openai"] = ProviderConfig(
                provider_type=AIProviderType.OPENAI,
                api_key=settings.OPENAI_API_KEY,
                enabled=True,
                priority=1 if settings.AI_PROVIDER == "openai" else 2,
                max_requests_per_minute=60,
                max_cost_per_hour=50.0,
                preferred_models=["gpt-5.4-mini", "gpt-5.4"],
                fallback_models=["gpt-5.5", "gpt-4o"],
            )
            self.providers["openai"] = OpenAIProvider(api_key=settings.OPENAI_API_KEY)

        # Anthropic provider
        if settings.CLAUDE_API_KEY:
            self.provider_configs["anthropic"] = ProviderConfig(
                provider_type=AIProviderType.ANTHROPIC,
                api_key=settings.CLAUDE_API_KEY,
                enabled=True,
                priority=1 if settings.AI_PROVIDER == "anthropic" else 2,
                max_requests_per_minute=50,
                max_cost_per_hour=100.0,
                preferred_models=[
                    "claude-sonnet-5",     # Default: best speed/intelligence balance
                    "claude-haiku-4-5",   # Fast/cheap alternative
                ],
                fallback_models=["claude-opus-4-8"],  # Premium for complex tasks
            )
            self.providers["anthropic"] = AnthropicProvider(
                api_key=settings.CLAUDE_API_KEY
            )

        # Mock responses let the stack run locally and in CI without keys, but only
        # as a stand-in: never in production, and never as a failover behind a real
        # provider (a failed real call must surface as FAILED, not as canned text).
        if settings.ENVIRONMENT.lower() != "production" and not self.providers:
            self.provider_configs["mock"] = ProviderConfig(
                provider_type=AIProviderType.MOCK,
                api_key="mock-key",
                enabled=True,
                priority=3,
                max_requests_per_minute=1000,
                max_cost_per_hour=1000.0,
                preferred_models=["mock-gpt-4"],
                fallback_models=["mock-claude"],
            )
            self.providers["mock"] = MockProvider(api_key="mock-key")

        provider_names = list(self.providers.keys())
        if settings.ENVIRONMENT.lower() == "production" and not provider_names:
            logger.error(
                "No real AI providers are configured in production; transformations will fail explicitly"
            )
        else:
            logger.info("AI providers initialized: %s", provider_names)

        # Set selection strategy based on configuration
        if len([p for p in self.provider_configs.values() if p.enabled]) > 1:
            self.selection_strategy = ProviderSelectionStrategy.PRIMARY_FAILOVER
        else:
            self.selection_strategy = ProviderSelectionStrategy.PRIMARY_FAILOVER

    async def generate_text(
        self,
        prompt: str,
        preferred_provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> AIResponse:
        """
        Generate text using the best available provider

        Args:
            prompt: The input prompt
            preferred_provider: Preferred provider name (optional)
            model: Specific model to use (optional)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            AIResponse with generated text and metadata

        Raises:
            AIProviderError: If all providers fail
        """
        if preferred_provider and preferred_provider not in self.providers:
            raise AIProviderError(
                f"Unknown AI provider: {preferred_provider}",
                preferred_provider,
                "unknown_provider",
            )

        # Get ordered list of providers to try
        providers_to_try = self._get_provider_order(preferred_provider)

        last_error = None

        for provider_name in providers_to_try:
            try:
                # Check if provider is available and within limits
                if not self._can_use_provider(provider_name):
                    continue

                provider = self.providers[provider_name]
                self.provider_configs[provider_name]

                # Select model for this provider
                selected_model = self._select_model(provider_name, model)

                # Make the request
                start_time = time.time()
                response = await provider.generate_text(
                    prompt=prompt,
                    model=selected_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )

                # Track usage and performance
                await self._track_usage(
                    provider_name, response, time.time() - start_time
                )

                return response

            except RateLimitError as e:
                logger.warning("AI provider %s rate limited: %s", provider_name, e)
                self._mark_rate_limited(provider_name, e.retry_after)
                last_error = e
                continue

            except QuotaExceededError as e:
                logger.error("AI provider %s quota exceeded: %s", provider_name, e)
                self._disable_provider(provider_name, str(e))
                last_error = e
                continue

            except AIProviderError as e:
                logger.error("AI provider %s failed: %s", provider_name, e)
                last_error = e
                continue

        # If we get here, all providers failed
        if last_error:
            raise last_error
        else:
            raise AIProviderError("No available AI providers", "all")

    def _get_provider_order(
        self, preferred_provider: Optional[str] = None
    ) -> List[str]:
        """Get ordered list of providers to try based on strategy"""
        available_providers = [
            name
            for name, config in self.provider_configs.items()
            if config.enabled and self.providers[name].is_available()
        ]

        if not available_providers:
            # If no providers are available, try all providers anyway (in case status is stale)
            available_providers = list(self.provider_configs.keys())

        # If preferred provider is specified and available, try it first
        if preferred_provider and preferred_provider in available_providers:
            available_providers.remove(preferred_provider)
            available_providers.insert(0, preferred_provider)
            return available_providers

        # Apply selection strategy
        if self.selection_strategy == ProviderSelectionStrategy.PRIMARY_FAILOVER:
            # Sort by priority (lower number = higher priority)
            return sorted(
                available_providers, key=lambda x: self.provider_configs[x].priority
            )

        elif self.selection_strategy == ProviderSelectionStrategy.ROUND_ROBIN:
            # Round-robin through available providers
            if available_providers:
                self.provider_rotation_index = (self.provider_rotation_index + 1) % len(
                    available_providers
                )
                ordered = (
                    available_providers[self.provider_rotation_index :]
                    + available_providers[: self.provider_rotation_index]
                )
                return ordered

        elif self.selection_strategy == ProviderSelectionStrategy.FASTEST:
            # Sort by average response time
            return sorted(
                available_providers,
                key=lambda x: self.provider_performance[x]["avg_response_time"],
            )

        elif self.selection_strategy == ProviderSelectionStrategy.LEAST_COST:
            # Sort by cost efficiency (would need cost estimation)
            return sorted(
                available_providers, key=lambda x: self.provider_configs[x].priority
            )

        # Default to priority-based ordering
        return sorted(
            available_providers, key=lambda x: self.provider_configs[x].priority
        )

    def _can_use_provider(self, provider_name: str) -> bool:
        """Check if provider can be used (rate limits, cost limits, etc.)"""
        config = self.provider_configs.get(provider_name)
        if not config or not config.enabled:
            return False

        provider = self.providers.get(provider_name)
        if not provider or not provider.is_available():
            return False

        tracker = self.usage_trackers[provider_name]
        current_time = time.time()

        # Check rate limits (requests per minute)
        minute_ago = current_time - 60
        while (
            tracker.requests_per_minute
            and tracker.requests_per_minute[0] <= minute_ago
        ):
            tracker.requests_per_minute.popleft()
        if len(tracker.requests_per_minute) >= config.max_requests_per_minute:
            return False

        # Check cost limits (per hour)
        hour_ago = current_time - 3600
        recent_costs = [c for c in tracker.costs_per_hour if c[0] > hour_ago]
        total_hour_cost = sum(c[1] for c in recent_costs)
        if total_hour_cost >= config.max_cost_per_hour:
            return False

        return True

    def _select_model(
        self, provider_name: str, requested_model: Optional[str] = None
    ) -> str:
        """Select the best model for a provider"""
        provider = self.providers[provider_name]
        config = self.provider_configs[provider_name]
        available_models = [m.name for m in provider.get_available_models()]

        # If specific model requested and available, use it
        if requested_model and requested_model in available_models:
            return requested_model

        # Try preferred models first
        for model in config.preferred_models:
            if model in available_models:
                return model

        # Fall back to provider's default
        default_model = provider.get_default_model()
        if default_model in available_models:
            return default_model

        # Use any available model
        if available_models:
            return available_models[0]

        # This shouldn't happen, but return something
        return provider.get_default_model()

    async def _track_usage(
        self, provider_name: str, response: AIResponse, processing_time: float
    ):
        """Track usage for rate limiting and cost management"""
        tracker = self.usage_trackers[provider_name]
        current_time = time.time()

        # Track request timing
        tracker.requests_per_minute.append(current_time)
        tracker.total_requests += 1
        tracker.last_request_time = datetime.fromtimestamp(current_time)

        # Track costs
        cost = response.usage_metrics.total_cost
        tracker.costs_per_hour.append((current_time, cost))
        tracker.total_cost += cost

        # Update performance metrics
        perf = self.provider_performance[provider_name]
        perf["total_requests"] += 1

        # Update average response time
        if perf["avg_response_time"] == 0:
            perf["avg_response_time"] = processing_time
        else:
            # Exponential moving average
            perf["avg_response_time"] = (perf["avg_response_time"] * 0.9) + (
                processing_time * 0.1
            )

        # Store usage metrics to Redis if available
        if self.redis_client:
            await self._store_usage_metrics(response.usage_metrics)

    async def _store_usage_metrics(self, metrics: AIUsageMetrics):
        """Store usage metrics to Redis for persistence"""
        try:
            key = f"ai_usage:{metrics.provider}:{metrics.timestamp.strftime('%Y-%m-%d-%H')}"
            data = {
                "provider": metrics.provider,
                "model": metrics.model,
                "input_tokens": metrics.input_tokens,
                "output_tokens": metrics.output_tokens,
                "total_cost": metrics.total_cost,
                "processing_time_ms": metrics.processing_time_ms,
            }

            # Store as JSON with expiry (7 days)
            self.redis_client.setex(key, 7 * 24 * 3600, json.dumps(data, default=str))

        except Exception as e:
            logger.warning("Failed to store AI usage metrics: %s", e)

    def _mark_rate_limited(self, provider_name: str, retry_after: Optional[int] = None):
        """Mark provider as rate limited"""
        if provider_name in self.providers:
            self.providers[provider_name].set_rate_limited(retry_after)

    def _disable_provider(self, provider_name: str, reason: str):
        """Temporarily disable a provider"""
        if provider_name in self.provider_configs:
            self.provider_configs[provider_name].enabled = False
            logger.warning("Disabled AI provider %s: %s", provider_name, reason)

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers"""
        status = {}
        for name, provider in self.providers.items():
            config = self.provider_configs[name]
            tracker = self.usage_trackers[name]
            perf = self.provider_performance[name]

            status[name] = {
                "provider_info": provider.get_status_info(),
                "configuration": {
                    "enabled": config.enabled,
                    "priority": config.priority,
                    "max_requests_per_minute": config.max_requests_per_minute,
                    "max_cost_per_hour": config.max_cost_per_hour,
                },
                "usage": {
                    "total_requests": tracker.total_requests,
                    "total_cost": tracker.total_cost,
                    "last_request": tracker.last_request_time.isoformat()
                    if tracker.last_request_time
                    else None,
                    "recent_requests_count": len(tracker.requests_per_minute),
                    "hourly_cost": sum(
                        c[1]
                        for c in tracker.costs_per_hour
                        if c[0] > time.time() - 3600
                    ),
                },
                "performance": perf,
            }

        return status

    def get_cost_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get cost summary for the specified time period"""
        cutoff_time = time.time() - (hours * 3600)
        summary = {}
        total_cost = 0.0

        for provider_name, tracker in self.usage_trackers.items():
            provider_cost = sum(
                c[1] for c in tracker.costs_per_hour if c[0] > cutoff_time
            )
            provider_requests = len(
                [t for t in tracker.requests_per_minute if t > cutoff_time]
            )

            summary[provider_name] = {
                "cost": provider_cost,
                "requests": provider_requests,
                "avg_cost_per_request": provider_cost / provider_requests
                if provider_requests > 0
                else 0.0,
            }
            total_cost += provider_cost

        summary["total"] = {
            "cost": total_cost,
            "requests": sum(
                p["requests"]
                for p in summary.values()
                if isinstance(p, dict) and "requests" in p
            ),
            "period_hours": hours,
        }

        return summary

    def set_selection_strategy(self, strategy: ProviderSelectionStrategy):
        """Set the provider selection strategy"""
        self.selection_strategy = strategy

    async def validate_all_providers(self) -> Dict[str, bool]:
        """Validate API keys for all configured providers"""
        results = {}

        for name, provider in self.providers.items():
            try:
                is_valid = await provider.validate_api_key()
                results[name] = is_valid

                if not is_valid:
                    self._disable_provider(name, "Invalid API key")
            except Exception as e:
                results[name] = False
                logger.error("Error validating AI provider %s: %s", name, e)

        return results


# Global instance
ai_provider_manager: Optional[AIProviderManager] = None


def get_ai_provider_manager() -> AIProviderManager:
    """Get the global AI provider manager instance"""
    global ai_provider_manager
    if ai_provider_manager is None:
        # Share the process-wide client (honours REDIS_URL); None means Redis is down
        # and usage tracking degrades to in-memory only.
        from app.services.redis_service import redis_service

        if redis_service.redis_client is None:
            logger.warning("Redis not available for AI usage tracking")
        ai_provider_manager = AIProviderManager(redis_client=redis_service.redis_client)

    return ai_provider_manager
