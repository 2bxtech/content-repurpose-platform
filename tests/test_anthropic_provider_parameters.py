from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai_providers.anthropic_provider import AnthropicProvider


def _message():
    return SimpleNamespace(
        id="msg_test",
        content=[SimpleNamespace(type="text", text="Generated response")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        stop_reason="end_turn",
    )


@pytest.mark.asyncio
async def test_generate_text_omits_default_temperature():
    provider = AnthropicProvider(api_key="test-key")
    provider.client.messages.create = AsyncMock(return_value=_message())

    await provider.generate_text("Test prompt")

    kwargs = provider.client.messages.create.await_args.kwargs
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_generate_text_preserves_explicit_temperature():
    provider = AnthropicProvider(api_key="test-key")
    provider.client.messages.create = AsyncMock(return_value=_message())

    await provider.generate_text("Test prompt", temperature=0.2)

    kwargs = provider.client.messages.create.await_args.kwargs
    assert kwargs["temperature"] == 0.2


@pytest.mark.asyncio
async def test_generate_text_skips_thinking_blocks():
    provider = AnthropicProvider(api_key="test-key")
    message = _message()
    message.content = [
        SimpleNamespace(type="thinking", thinking="Internal reasoning"),
        SimpleNamespace(type="text", text="Generated response"),
    ]
    provider.client.messages.create = AsyncMock(return_value=message)

    response = await provider.generate_text("Test prompt")

    assert response.content == "Generated response"


@pytest.mark.asyncio
async def test_generate_text_combines_multiple_text_blocks():
    provider = AnthropicProvider(api_key="test-key")
    message = _message()
    message.content = [
        SimpleNamespace(type="text", text="First paragraph.\n"),
        SimpleNamespace(type="tool_use", name="example"),
        SimpleNamespace(type="text", text="Second paragraph."),
    ]
    provider.client.messages.create = AsyncMock(return_value=message)

    response = await provider.generate_text("Test prompt")

    assert response.content == "First paragraph.\nSecond paragraph."
