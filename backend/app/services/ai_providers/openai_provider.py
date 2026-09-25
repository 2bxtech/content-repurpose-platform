"""
OpenAI Provider Implementation

Implements the BaseAIProvider for OpenAI's GPT models.
"""

import openai
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


class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT provider implementation"""

    def get_provider_type(self) -> AIProviderType:
        return AIProviderType.OPENAI

    def _initialize_client(self):
        """Initialize OpenAI client"""
        try:
            self.client = openai.AsyncOpenAI(
                api_key=self.api_key,
                timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
                max_retries=settings.AI_MAX_RETRIES,
            )
        except Exception as e:
            raise AIProviderError(
                f"Failed to initialize OpenAI client: {str(e)}", "openai"
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
        """Generate text using OpenAI API"""
        start_time = time.time()

        # Use default model if not specified
        if not model:
            model = self.get_default_model()

        # Set default parameters
        if max_tokens is None:
            max_tokens = 4000
        if temperature is None:
            temperature = 0.7

        # Prepare messages — system prompt is optional; callers pass it explicitly
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Extract response data
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason

            # Calculate usage metrics
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

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
                    "finish_reason": finish_reason,
                    "response_id": response.id if hasattr(response, "id") else None,
                },
                finish_reason=finish_reason,
            )

        except openai.RateLimitError as e:
            self.set_rate_limited()
            raise RateLimitError(f"OpenAI rate limit exceeded: {str(e)}", "openai")

        except openai.APIError as e:
            if "quota" in str(e).lower():
                raise QuotaExceededError(f"OpenAI quota exceeded: {str(e)}", "openai")
            elif "invalid" in str(e).lower() and "key" in str(e).lower():
                raise InvalidAPIKeyError(f"Invalid OpenAI API key: {str(e)}", "openai")
            else:
                raise AIProviderError(f"OpenAI API error: {str(e)}", "openai")

        except Exception as e:
            raise AIProviderError(f"OpenAI provider error: {str(e)}", "openai")

    def get_available_models(self) -> List[AIModelInfo]:
        """Get available OpenAI models — IDs from platform.openai.com/docs/models (July 2026)"""
        return [
            AIModelInfo(
                name="gpt-5.5",
                display_name="GPT-5.5",
                max_tokens=128000,
                cost_per_1k_input_tokens=0.005,   # $5/MTok
                cost_per_1k_output_tokens=0.030,  # $30/MTok
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
                name="gpt-5.4",
                display_name="GPT-5.4",
                max_tokens=128000,
                cost_per_1k_input_tokens=0.0025,  # $2.50/MTok
                cost_per_1k_output_tokens=0.015,  # $15/MTok
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
                name="gpt-5.4-mini",
                display_name="GPT-5.4 Mini",
                max_tokens=128000,
                cost_per_1k_input_tokens=0.00075,  # $0.75/MTok
                cost_per_1k_output_tokens=0.0045,  # $4.50/MTok
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=400000,
                supports_streaming=True,
                supports_function_calling=True,
            ),
            AIModelInfo(
                name="gpt-4o",
                display_name="GPT-4o (legacy)",
                max_tokens=16384,
                cost_per_1k_input_tokens=0.005,
                cost_per_1k_output_tokens=0.015,
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=128000,
                supports_streaming=True,
                supports_function_calling=True,
            ),
        ]

    def get_default_model(self) -> str:
        """Default: GPT-5.4 Mini — best cost/quality for content tasks"""
        return "gpt-5.4-mini"

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate cost for OpenAI model usage"""
        models = {m.name: m for m in self.get_available_models()}
        model_info = models.get(model)

        if not model_info:
            model_info = models.get("gpt-5.4-mini")

        if model_info:
            input_cost = (input_tokens / 1000) * model_info.cost_per_1k_input_tokens
            output_cost = (output_tokens / 1000) * model_info.cost_per_1k_output_tokens
            return input_cost + output_cost

        return 0.0

    async def validate_api_key(self) -> bool:
        """Validate OpenAI API key by making a test request"""
        try:
            # Make a minimal test request with cheapest/fastest model
            await self.client.chat.completions.create(
                model="gpt-5.4-mini",  # Cheapest current model for validation
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
            )
            return True
        except openai.APIError as e:
            if "invalid" in str(e).lower() and "key" in str(e).lower():
                return False
            # Other API errors might indicate the key is valid but there's another issue
            return True
        except Exception:
            return False
