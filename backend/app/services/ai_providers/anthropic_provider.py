"""
Anthropic Claude Provider Implementation

Implements the BaseAIProvider for Anthropic's Claude models.
"""

import anthropic
import time
from typing import Optional, List
from app.core.config import settings
from .base import (
    BaseAIProvider,
    AIProviderType,
    AIResponse,
    AIModelInfo,
    ModelCapability,
    AIProviderError,
    RateLimitError,
    QuotaExceededError,
    InvalidAPIKeyError,
)


class AnthropicProvider(BaseAIProvider):
    """Anthropic Claude provider implementation"""

    def get_provider_type(self) -> AIProviderType:
        return AIProviderType.ANTHROPIC

    def _initialize_client(self):
        """Initialize Anthropic async client"""
        try:
            self.client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
                max_retries=settings.AI_MAX_RETRIES,
            )
        except Exception as e:
            raise AIProviderError(
                f"Failed to initialize Anthropic client: {str(e)}", "anthropic"
            )

    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate text using Anthropic API"""
        start_time = time.time()

        # Use default model if not specified
        if not model:
            model = self.get_default_model()

        # Set default parameters
        if max_tokens is None:
            max_tokens = 4000

        try:
            # Build kwargs; only pass system/temperature if the caller provided them —
            # newer Claude models reject a "temperature" field outright (400 invalid_request_error).
            create_kwargs = dict(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            if system_prompt:
                create_kwargs["system"] = system_prompt
            if temperature is not None:
                create_kwargs["temperature"] = temperature

            message = await self.client.messages.create(**create_kwargs)

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Claude responses may include thinking or tool-use blocks before or
            # between text blocks. Only text blocks are user-visible output.
            content = "".join(
                block.text
                for block in message.content
                if getattr(block, "type", None) == "text"
            )

            # Calculate usage metrics
            input_tokens = (
                message.usage.input_tokens
                if hasattr(message, "usage") and message.usage
                else 0
            )
            output_tokens = (
                message.usage.output_tokens
                if hasattr(message, "usage") and message.usage
                else 0
            )

            usage_metrics = self._calculate_usage_metrics(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                processing_time_ms=processing_time_ms,
            )

            return AIResponse(
                content=content,
                provider=self.provider_type.value,
                model=model,
                usage_metrics=usage_metrics,
                metadata={
                    "message_id": message.id if hasattr(message, "id") else None,
                    "stop_reason": message.stop_reason
                    if hasattr(message, "stop_reason")
                    else None,
                },
                finish_reason=message.stop_reason
                if hasattr(message, "stop_reason")
                else None,
            )

        except anthropic.RateLimitError as e:
            self.set_rate_limited()
            raise RateLimitError(
                f"Anthropic rate limit exceeded: {str(e)}", "anthropic"
            )

        except anthropic.APIError as e:
            error_msg = str(e)
            if "rate_limit" in error_msg.lower():
                self.set_rate_limited()
                raise RateLimitError(f"Anthropic rate limit: {error_msg}", "anthropic")
            elif "quota" in error_msg.lower() or "credit" in error_msg.lower():
                raise QuotaExceededError(
                    f"Anthropic quota exceeded: {error_msg}", "anthropic"
                )
            elif "invalid" in error_msg.lower() and "key" in error_msg.lower():
                raise InvalidAPIKeyError(
                    f"Invalid Anthropic API key: {error_msg}", "anthropic"
                )
            else:
                raise AIProviderError(f"Anthropic API error: {error_msg}", "anthropic")

        except Exception as e:
            raise AIProviderError(f"Anthropic provider error: {str(e)}", "anthropic")

    def get_available_models(self) -> List[AIModelInfo]:
        """Get available Anthropic models — IDs from docs.anthropic.com/models (July 2026)"""
        return [
            AIModelInfo(
                name="claude-opus-4-8",
                display_name="Claude Opus 4.8",
                max_tokens=128000,
                cost_per_1k_input_tokens=0.005,   # $5/MTok
                cost_per_1k_output_tokens=0.025,  # $25/MTok
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=1000000,
                supports_streaming=True,
                supports_function_calling=True,
            ),
            AIModelInfo(
                name="claude-sonnet-5",
                display_name="Claude Sonnet 5",
                max_tokens=128000,
                cost_per_1k_input_tokens=0.002,   # $2/MTok intro (until Aug 31, 2026)
                cost_per_1k_output_tokens=0.010,  # $10/MTok intro
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=1000000,
                supports_streaming=True,
                supports_function_calling=True,
            ),
            AIModelInfo(
                name="claude-haiku-4-5",
                display_name="Claude Haiku 4.5",
                max_tokens=64000,
                cost_per_1k_input_tokens=0.001,   # $1/MTok
                cost_per_1k_output_tokens=0.005,  # $5/MTok
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=200000,
                supports_streaming=True,
                supports_function_calling=True,
            ),
        ]

    def get_default_model(self) -> str:
        """Default: Claude Sonnet 5 — best speed/intelligence balance (intro pricing until Aug 2026)"""
        return "claude-sonnet-5"

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate cost for Anthropic model usage"""
        models = {m.name: m for m in self.get_available_models()}
        model_info = models.get(model)

        if not model_info:
            model_info = models.get("claude-sonnet-5")

        if model_info:
            input_cost = (input_tokens / 1000) * model_info.cost_per_1k_input_tokens
            output_cost = (output_tokens / 1000) * model_info.cost_per_1k_output_tokens
            return input_cost + output_cost

        return 0.0

    async def validate_api_key(self) -> bool:
        """Validate Anthropic API key by making a test request"""
        try:
            # Make a minimal test request with fastest model
            await self.client.messages.create(
                model="claude-haiku-4-5",  # Fastest model for validation
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except anthropic.APIError as e:
            error_msg = str(e)
            if "invalid" in error_msg.lower() and "key" in error_msg.lower():
                return False
            # Other API errors might indicate the key is valid but there's another issue
            return True
        except Exception:
            return False
