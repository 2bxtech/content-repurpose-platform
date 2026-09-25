import pytest

from app.core.config import settings
from app.services.ai_providers.base import AIProviderError
from app.services.ai_providers.manager import AIProviderManager


def test_mock_provider_is_not_registered_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")

    manager = AIProviderManager()

    assert manager.providers == {}


@pytest.mark.asyncio
async def test_production_without_real_provider_fails_explicitly(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")
    manager = AIProviderManager()

    with pytest.raises(AIProviderError, match="No available AI providers"):
        await manager.generate_text("This must never return canned content")


def test_mock_provider_remains_available_for_local_development(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")

    manager = AIProviderManager()

    assert list(manager.providers) == ["mock"]


def test_mock_is_not_a_silent_failover_behind_a_real_provider(monkeypatch):
    # A failing real provider must produce FAILED, not canned mock text marked COMPLETED.
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-ant-test-not-a-real-key")

    manager = AIProviderManager()

    assert "mock" not in manager.providers
    assert "anthropic" in manager.providers
