"""
AI Provider Management API Endpoints

Provides API endpoints for managing AI providers, viewing usage statistics,
and configuring provider settings.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.api.routes.auth import get_current_active_user
from app.services.ai_providers import (
    get_ai_provider_manager,
    ProviderSelectionStrategy,
    AIProviderStatus,
)

router = APIRouter()


class ProviderStatusResponse(BaseModel):
    """Response model for provider status"""

    providers: Dict[str, Any]
    selection_strategy: str
    total_providers: int
    available_providers: int


class CostSummaryResponse(BaseModel):
    """Response model for cost summary"""

    summary: Dict[str, Any]
    period_hours: int


class ProviderTestRequest(BaseModel):
    """Request model for testing a provider"""

    provider: str
    test_prompt: str = "Hello, world!"


class ProviderTestResponse(BaseModel):
    """Response model for provider test"""

    success: bool
    provider: str
    model: str
    response_content: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: int
    usage_metrics: Optional[Dict[str, Any]] = None


class ProviderConfigUpdate(BaseModel):
    """Request model for updating provider configuration"""

    enabled: Optional[bool] = None
    priority: Optional[int] = None
    max_requests_per_minute: Optional[int] = None
    max_cost_per_hour: Optional[float] = None


class StrategyUpdateRequest(BaseModel):
    """Request model for updating provider selection strategy"""

    strategy: ProviderSelectionStrategy


@router.get("/providers/status", response_model=ProviderStatusResponse)
async def get_provider_status(current_user: dict = Depends(get_current_active_user)):
    """Get status of all AI providers"""
    manager = get_ai_provider_manager()
    provider_status = manager.get_provider_status()

    available_count = sum(
        1
        for status in provider_status.values()
        if status["provider_info"]["is_available"]
    )

    return ProviderStatusResponse(
        providers=provider_status,
        selection_strategy=manager.selection_strategy.value,
        total_providers=len(provider_status),
        available_providers=available_count,
    )


@router.get("/providers/costs", response_model=CostSummaryResponse)
async def get_cost_summary(
    hours: int = 24, current_user: dict = Depends(get_current_active_user)
):
    """Get cost summary for AI provider usage"""
    manager = get_ai_provider_manager()
    cost_summary = manager.get_cost_summary(hours=hours)

    return CostSummaryResponse(summary=cost_summary, period_hours=hours)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_provider(
    request: ProviderTestRequest, current_user: dict = Depends(get_current_active_user)
):
    """Test a specific AI provider"""
    manager = get_ai_provider_manager()

    # Check if provider exists
    if request.provider not in manager.providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{request.provider}' not found",
        )

    try:
        import time

        start_time = time.time()

        response = await manager.generate_text(
            prompt=request.test_prompt, preferred_provider=request.provider
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        return ProviderTestResponse(
            success=True,
            provider=response.provider,
            model=response.model,
            response_content=response.content[:200] + "..."
            if len(response.content) > 200
            else response.content,
            processing_time_ms=processing_time_ms,
            usage_metrics={
                "input_tokens": response.usage_metrics.input_tokens,
                "output_tokens": response.usage_metrics.output_tokens,
                "total_cost": response.usage_metrics.total_cost,
            },
        )

    except Exception as e:
        return ProviderTestResponse(
            success=False,
            provider=request.provider,
            model="unknown",
            error_message=str(e),
            processing_time_ms=0,
        )


@router.post("/providers/{provider_name}/validate")
async def validate_provider(
    provider_name: str, current_user: dict = Depends(get_current_active_user)
):
    """Validate API key for a specific provider"""
    manager = get_ai_provider_manager()

    if provider_name not in manager.providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )

    try:
        provider = manager.providers[provider_name]
        is_valid = await provider.validate_api_key()

        return {
            "provider": provider_name,
            "valid": is_valid,
            "message": "API key is valid" if is_valid else "API key is invalid",
        }

    except Exception as e:
        return {
            "provider": provider_name,
            "valid": False,
            "message": f"Validation error: {str(e)}",
        }


@router.post("/providers/validate-all")
async def validate_all_providers(current_user: dict = Depends(get_current_active_user)):
    """Validate API keys for all providers"""
    manager = get_ai_provider_manager()
    results = await manager.validate_all_providers()

    return {
        "validation_results": results,
        "valid_providers": [name for name, valid in results.items() if valid],
        "invalid_providers": [name for name, valid in results.items() if not valid],
    }


@router.put("/providers/{provider_name}/config")
async def update_provider_config(
    provider_name: str,
    config_update: ProviderConfigUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    """Update configuration for a specific provider"""
    manager = get_ai_provider_manager()

    if provider_name not in manager.provider_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )

    config = manager.provider_configs[provider_name]

    # Update configuration
    if config_update.enabled is not None:
        config.enabled = config_update.enabled
    if config_update.priority is not None:
        config.priority = config_update.priority
    if config_update.max_requests_per_minute is not None:
        config.max_requests_per_minute = config_update.max_requests_per_minute
    if config_update.max_cost_per_hour is not None:
        config.max_cost_per_hour = config_update.max_cost_per_hour

    return {
        "provider": provider_name,
        "message": "Configuration updated successfully",
        "config": {
            "enabled": config.enabled,
            "priority": config.priority,
            "max_requests_per_minute": config.max_requests_per_minute,
            "max_cost_per_hour": config.max_cost_per_hour,
        },
    }


@router.put("/providers/strategy")
async def update_selection_strategy(
    strategy_update: StrategyUpdateRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """Update provider selection strategy"""
    manager = get_ai_provider_manager()
    manager.set_selection_strategy(strategy_update.strategy)

    return {
        "message": "Selection strategy updated successfully",
        "strategy": strategy_update.strategy.value,
    }


@router.get("/providers/models")
async def get_available_models(current_user: dict = Depends(get_current_active_user)):
    """Get all available models from all providers"""
    manager = get_ai_provider_manager()
    models_by_provider = {}

    for provider_name, provider in manager.providers.items():
        models = provider.get_available_models()
        models_by_provider[provider_name] = [
            {
                "name": model.name,
                "display_name": model.display_name,
                "max_tokens": model.max_tokens,
                "cost_per_1k_input_tokens": model.cost_per_1k_input_tokens,
                "cost_per_1k_output_tokens": model.cost_per_1k_output_tokens,
                "capabilities": [cap.value for cap in model.capabilities],
                "context_window": model.context_window,
                "supports_streaming": model.supports_streaming,
                "supports_function_calling": model.supports_function_calling,
            }
            for model in models
        ]

    return {
        "models_by_provider": models_by_provider,
        "total_models": sum(len(models) for models in models_by_provider.values()),
    }


@router.post("/providers/{provider_name}/reset-limits")
async def reset_provider_limits(
    provider_name: str, current_user: dict = Depends(get_current_active_user)
):
    """Reset rate limits and usage tracking for a provider"""
    manager = get_ai_provider_manager()

    if provider_name not in manager.providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )

    # Reset usage tracker
    if provider_name in manager.usage_trackers:
        tracker = manager.usage_trackers[provider_name]
        tracker.requests_per_minute.clear()
        tracker.costs_per_hour.clear()

    # Reset provider status if rate limited
    provider = manager.providers[provider_name]
    if provider.status == AIProviderStatus.RATE_LIMITED:
        provider.set_status(AIProviderStatus.AVAILABLE)

    return {"provider": provider_name, "message": "Limits reset successfully"}


@router.get("/providers/statistics")
async def get_provider_statistics(
    current_user: dict = Depends(get_current_active_user),
):
    """Get detailed statistics for all providers"""
    manager = get_ai_provider_manager()

    statistics = {
        "overview": {
            "total_providers": len(manager.providers),
            "available_providers": sum(
                1 for p in manager.providers.values() if p.is_available()
            ),
            "current_strategy": manager.selection_strategy.value,
        },
        "usage_summary": manager.get_cost_summary(hours=24),
        "provider_details": {},
    }

    for provider_name, provider in manager.providers.items():
        config = manager.provider_configs[provider_name]
        tracker = manager.usage_trackers[provider_name]
        performance = manager.provider_performance[provider_name]

        statistics["provider_details"][provider_name] = {
            "type": provider.provider_type.value,
            "status": provider.status.value,
            "is_available": provider.is_available(),
            "enabled": config.enabled,
            "priority": config.priority,
            "total_requests": tracker.total_requests,
            "total_cost": tracker.total_cost,
            "average_response_time": performance["avg_response_time"],
            "success_rate": performance["success_rate"],
            "last_request": tracker.last_request_time.isoformat()
            if tracker.last_request_time
            else None,
            "available_models": len(provider.get_available_models()),
            "default_model": provider.get_default_model(),
        }

    return statistics
