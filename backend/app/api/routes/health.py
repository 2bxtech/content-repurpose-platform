from fastapi import APIRouter, HTTPException, status
from datetime import datetime
from app.services.redis_service import redis_service
from app.services.health_monitoring import health_monitor
from app.services.metrics_service import performance_monitor
from app.services.audit_service import audit_service, AuditEventType, AuditLevel
from app.core.config import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "version": "2.0.0",
    }


@router.get("/health/comprehensive")
async def comprehensive_health_check():
    """Comprehensive health check of all system components"""
    try:
        # Perform comprehensive health check
        health_report = await health_monitor.perform_comprehensive_health_check()

        # Log health check
        await audit_service.log_event(
            event_type=AuditEventType.SYSTEM_HEALTH_CHECK,
            level=AuditLevel.INFO,
            details={
                "overall_status": health_report.overall_status,
                "total_checks": len(health_report.checks),
                "alerts_count": len(health_report.alerts),
            },
        )

        return {
            "overall_status": health_report.overall_status,
            "timestamp": health_report.timestamp,
            "checks": [
                {
                    "component": check.component,
                    "component_type": check.component_type,
                    "status": check.status,
                    "message": check.message,
                    "response_time_ms": check.response_time_ms,
                    "details": check.details,
                    "metrics": check.metrics,
                }
                for check in health_report.checks
            ],
            "summary": health_report.summary,
            "alerts": health_report.alerts,
        }

    except Exception as e:
        logger.error(f"Comprehensive health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "message": "Health check failed",
                "error": str(e),
            },
        )


@router.get("/health/metrics")
async def health_metrics():
    """Get application performance metrics"""
    try:
        # Get performance dashboard
        dashboard = await performance_monitor.get_performance_dashboard()

        return {"status": "success", "data": dashboard}

    except Exception as e:
        logger.error(f"Failed to get health metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to retrieve metrics",
                "error": str(e),
            },
        )


@router.get("/health/alerts")
async def get_active_alerts():
    """Get active system alerts"""
    try:
        alerts = await performance_monitor.metrics_collector.get_active_alerts()

        return {
            "status": "success",
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "metric_name": alert.metric_name,
                    "severity": alert.severity,
                    "message": alert.message,
                    "threshold": alert.threshold,
                    "current_value": alert.current_value,
                    "timestamp": alert.timestamp,
                    "resolved": alert.resolved,
                }
                for alert in alerts
            ],
            "count": len(alerts),
            "critical_count": len([a for a in alerts if a.severity == "critical"]),
            "warning_count": len([a for a in alerts if a.severity == "warning"]),
        }

    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to retrieve alerts",
                "error": str(e),
            },
        )


@router.post("/health/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve an active alert"""
    try:
        success = await performance_monitor.metrics_collector.resolve_alert(alert_id)

        if success:
            return {"status": "success", "message": f"Alert {alert_id} resolved"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "error", "message": f"Alert {alert_id} not found"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to resolve alert",
                "error": str(e),
            },
        )


@router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check including service dependencies"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "services": {},
    }

    # Check Redis connection
    try:
        redis_connected = redis_service.is_connected()
        health_status["services"]["redis"] = {
            "status": "healthy" if redis_connected else "unhealthy",
            "connected": redis_connected,
        }
    except Exception as e:
        health_status["services"]["redis"] = {"status": "error", "error": str(e)}
        health_status["status"] = "degraded"

    # Check authentication service
    try:
        from app.services.auth_service import auth_service

        # Test password hashing (basic functionality test)
        test_hash = auth_service.get_password_hash("test_password_123")
        auth_working = len(test_hash) > 0

        health_status["services"]["auth"] = {
            "status": "healthy" if auth_working else "unhealthy",
            "password_hashing": auth_working,
        }
    except Exception as e:
        health_status["services"]["auth"] = {"status": "error", "error": str(e)}
        health_status["status"] = "degraded"

    # Report which AI providers were registered without exposing credentials or
    # provider error payloads through this public health endpoint.
    try:
        from app.services.ai_providers.manager import get_ai_provider_manager

        provider_manager = get_ai_provider_manager()
        providers = {
            name: {
                "enabled": provider_manager.provider_configs[name].enabled,
                "available": provider.is_available(),
            }
            for name, provider in provider_manager.providers.items()
        }
        real_provider_available = any(
            info["enabled"] and info["available"]
            for name, info in providers.items()
            if name != "mock"
        )
        health_status["services"]["ai"] = {
            "status": "healthy" if real_provider_available else "unhealthy",
            "providers": providers,
            "real_provider_available": real_provider_available,
        }
        if settings.ENVIRONMENT.lower() == "production" and not real_provider_available:
            health_status["status"] = "degraded"
    except Exception as e:
        logger.error("AI provider health check failed: %s", e)
        health_status["services"]["ai"] = {"status": "error"}
        health_status["status"] = "degraded"

    # Overall status
    if health_status["status"] == "degraded":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_status
        )

    return health_status


@router.get("/health/redis")
async def redis_health():
    """Redis-specific health check"""
    try:
        connected = redis_service.is_connected()
        if connected:
            # Test basic operations
            test_key = "health_check_test"
            redis_service.set(test_key, "test_value", expire=10)
            test_value = redis_service.get(test_key)

            return {
                "status": "healthy",
                "connected": True,
                "operations_working": test_value == "test_value",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "status": "unhealthy",
                    "connected": False,
                    "error": "Redis connection failed",
                },
            )
    except Exception as e:
        logger.error(f"Redis health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "error": str(e)},
        )
