"""
Enhanced Health Monitoring Service

Provides comprehensive health checks for all system components including
database, Redis, AI providers, and application metrics.
"""

import time
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import psutil

from app.core.config import settings
from app.services.redis_service import redis_service
from app.services.audit_service import audit_service, AuditEventType, AuditLevel


logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class ComponentType(str, Enum):
    """Types of system components"""

    DATABASE = "database"
    REDIS = "redis"
    AI_PROVIDER = "ai_provider"
    CELERY = "celery"
    WEBSOCKET = "websocket"
    FILE_SYSTEM = "file_system"
    SYSTEM_RESOURCES = "system_resources"


@dataclass
class HealthCheck:
    """Individual health check result"""

    component: str
    component_type: ComponentType
    status: HealthStatus
    message: str
    response_time_ms: float
    timestamp: str
    details: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealthReport:
    """Comprehensive system health report"""

    overall_status: HealthStatus
    timestamp: str
    checks: List[HealthCheck]
    summary: Dict[str, Any]
    alerts: List[str]


class HealthMonitoringService:
    """Comprehensive health monitoring service"""

    def __init__(self):
        self.logger = logging.getLogger("health_monitor")
        self.last_health_check = None
        self.health_history = []
        self.alert_thresholds = {
            "response_time_ms": 5000,  # 5 seconds
            "error_rate": 0.1,  # 10%
            "memory_usage": 0.9,  # 90%
            "disk_usage": 0.95,  # 95%
            "cpu_usage": 0.9,  # 90%
        }

    async def perform_comprehensive_health_check(self) -> SystemHealthReport:
        """Perform comprehensive health check of all system components"""
        start_time = time.time()
        checks = []
        alerts = []

        # Database health check
        try:
            db_check = await self._check_database_health()
            checks.append(db_check)
            if db_check.status != HealthStatus.HEALTHY:
                alerts.append(f"Database {db_check.status}: {db_check.message}")
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            checks.append(
                HealthCheck(
                    component="database",
                    component_type=ComponentType.DATABASE,
                    status=HealthStatus.CRITICAL,
                    message=f"Health check failed: {e}",
                    response_time_ms=0,
                    timestamp=datetime.now().isoformat(),
                )
            )
            alerts.append(f"Database health check failed: {e}")

        # Redis health check
        try:
            redis_check = await self._check_redis_health()
            checks.append(redis_check)
            if redis_check.status != HealthStatus.HEALTHY:
                alerts.append(f"Redis {redis_check.status}: {redis_check.message}")
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            checks.append(
                HealthCheck(
                    component="redis",
                    component_type=ComponentType.REDIS,
                    status=HealthStatus.CRITICAL,
                    message=f"Health check failed: {e}",
                    response_time_ms=0,
                    timestamp=datetime.now().isoformat(),
                )
            )
            alerts.append(f"Redis health check failed: {e}")

        # AI Providers health check
        try:
            ai_checks = await self._check_ai_providers_health()
            checks.extend(ai_checks)

            # Check if all AI providers are down
            healthy_providers = [
                c for c in ai_checks if c.status == HealthStatus.HEALTHY
            ]
            if not healthy_providers:
                alerts.append("All AI providers are unhealthy")
        except Exception as e:
            logger.error(f"AI providers health check failed: {e}")
            alerts.append(f"AI providers health check failed: {e}")

        # System resources health check
        try:
            system_check = await self._check_system_resources()
            checks.append(system_check)
            if system_check.status != HealthStatus.HEALTHY:
                alerts.append(
                    f"System resources {system_check.status}: {system_check.message}"
                )
        except Exception as e:
            logger.error(f"System resources health check failed: {e}")
            alerts.append(f"System resources health check failed: {e}")

        # File system health check
        try:
            fs_check = await self._check_file_system_health()
            checks.append(fs_check)
            if fs_check.status != HealthStatus.HEALTHY:
                alerts.append(f"File system {fs_check.status}: {fs_check.message}")
        except Exception as e:
            logger.error(f"File system health check failed: {e}")
            alerts.append(f"File system health check failed: {e}")

        # Celery health check
        try:
            celery_check = await self._check_celery_health()
            checks.append(celery_check)
            if celery_check.status != HealthStatus.HEALTHY:
                alerts.append(f"Celery {celery_check.status}: {celery_check.message}")
        except Exception as e:
            logger.error(f"Celery health check failed: {e}")
            alerts.append(f"Celery health check failed: {e}")

        # Determine overall status
        overall_status = self._determine_overall_status(checks)

        # Create health report
        report = SystemHealthReport(
            overall_status=overall_status,
            timestamp=datetime.now().isoformat(),
            checks=checks,
            summary=self._generate_health_summary(checks),
            alerts=alerts,
        )

        # Store health check result
        await self._store_health_check_result(report)

        # Log health check event
        await audit_service.log_event(
            event_type=AuditEventType.SYSTEM_HEALTH_CHECK,
            level=AuditLevel.ERROR
            if overall_status == HealthStatus.CRITICAL
            else AuditLevel.INFO,
            details={
                "overall_status": overall_status,
                "total_checks": len(checks),
                "failed_checks": len(
                    [c for c in checks if c.status != HealthStatus.HEALTHY]
                ),
                "total_time_ms": (time.time() - start_time) * 1000,
                "alerts_count": len(alerts),
            },
        )

        return report

    async def _check_database_health(self) -> HealthCheck:
        """Check database connectivity and performance"""
        start_time = time.time()

        try:
            # Try to import database dependencies
            from sqlalchemy import create_engine, text

            # Create test connection
            engine = create_engine(settings.get_database_url(async_driver=False))

            # Test basic connectivity
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()

            response_time = (time.time() - start_time) * 1000

            # Additional checks
            details = {"connection_successful": True, "response_time_ms": response_time}

            # Determine status based on response time
            if response_time > self.alert_thresholds["response_time_ms"]:
                status = HealthStatus.DEGRADED
                message = f"Database responding slowly ({response_time:.1f}ms)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Database connection healthy ({response_time:.1f}ms)"

            return HealthCheck(
                component="database",
                component_type=ComponentType.DATABASE,
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details=details,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                component="database",
                component_type=ComponentType.DATABASE,
                status=HealthStatus.CRITICAL,
                message=f"Database connection failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details={"error": str(e)},
            )

    async def _check_redis_health(self) -> HealthCheck:
        """Check Redis connectivity and performance"""
        start_time = time.time()

        try:
            # Test Redis connection
            if not redis_service.is_connected():
                return HealthCheck(
                    component="redis",
                    component_type=ComponentType.REDIS,
                    status=HealthStatus.CRITICAL,
                    message="Redis not connected",
                    response_time_ms=0,
                    timestamp=datetime.now().isoformat(),
                )

            # Test basic operations
            test_key = "health_check_test"
            redis_service.set(test_key, "test_value", expire=10)
            test_value = redis_service.get(test_key)

            response_time = (time.time() - start_time) * 1000

            if test_value == "test_value":
                status = HealthStatus.HEALTHY
                message = f"Redis operations successful ({response_time:.1f}ms)"
            else:
                status = HealthStatus.DEGRADED
                message = "Redis operations partially working"

            # Get Redis info
            try:
                info = (
                    redis_service.redis_client.info()
                    if redis_service.redis_client
                    else {}
                )
                memory_usage = info.get("used_memory", 0)
                connected_clients = info.get("connected_clients", 0)

                details = {
                    "operations_working": test_value == "test_value",
                    "memory_usage_bytes": memory_usage,
                    "connected_clients": connected_clients,
                    "response_time_ms": response_time,
                }
            except Exception:
                details = {"operations_working": test_value == "test_value"}

            return HealthCheck(
                component="redis",
                component_type=ComponentType.REDIS,
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details=details,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                component="redis",
                component_type=ComponentType.REDIS,
                status=HealthStatus.CRITICAL,
                message=f"Redis health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details={"error": str(e)},
            )

    async def _check_ai_providers_health(self) -> List[HealthCheck]:
        """Check all AI providers health"""
        checks = []

        try:
            # Import AI provider manager
            from app.services.ai_providers.manager import AIProviderManager

            # Create manager instance (or use existing one)
            manager = AIProviderManager()

            # Check each provider
            for provider_name, provider in manager.providers.items():
                start_time = time.time()

                try:
                    # Get provider status
                    provider_status = await provider.get_health_status()
                    response_time = (time.time() - start_time) * 1000

                    # Map provider status to health status
                    if provider_status.status == "healthy":
                        status = HealthStatus.HEALTHY
                        message = f"Provider {provider_name} is healthy"
                    elif provider_status.status == "degraded":
                        status = HealthStatus.DEGRADED
                        message = f"Provider {provider_name} is degraded"
                    else:
                        status = HealthStatus.UNHEALTHY
                        message = f"Provider {provider_name} is unhealthy"

                    # Get usage metrics if available
                    usage_tracker = manager.usage_trackers.get(provider_name)
                    metrics = {}
                    if usage_tracker:
                        metrics = {
                            "total_requests": usage_tracker.total_requests,
                            "total_cost": usage_tracker.total_cost,
                            "requests_per_minute": len(
                                usage_tracker.requests_per_minute
                            ),
                            "last_request_time": usage_tracker.last_request_time.isoformat()
                            if usage_tracker.last_request_time
                            else None,
                        }

                    checks.append(
                        HealthCheck(
                            component=f"ai_provider_{provider_name}",
                            component_type=ComponentType.AI_PROVIDER,
                            status=status,
                            message=message,
                            response_time_ms=response_time,
                            timestamp=datetime.now().isoformat(),
                            details=provider_status.details,
                            metrics=metrics,
                        )
                    )

                except Exception as e:
                    response_time = (time.time() - start_time) * 1000
                    checks.append(
                        HealthCheck(
                            component=f"ai_provider_{provider_name}",
                            component_type=ComponentType.AI_PROVIDER,
                            status=HealthStatus.CRITICAL,
                            message=f"Provider {provider_name} health check failed: {e}",
                            response_time_ms=response_time,
                            timestamp=datetime.now().isoformat(),
                            details={"error": str(e)},
                        )
                    )

        except Exception as e:
            logger.error(f"AI providers health check failed: {e}")
            checks.append(
                HealthCheck(
                    component="ai_providers",
                    component_type=ComponentType.AI_PROVIDER,
                    status=HealthStatus.CRITICAL,
                    message=f"AI providers health check failed: {e}",
                    response_time_ms=0,
                    timestamp=datetime.now().isoformat(),
                    details={"error": str(e)},
                )
            )

        return checks

    async def _check_system_resources(self) -> HealthCheck:
        """Check system resource usage"""
        start_time = time.time()

        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            response_time = (time.time() - start_time) * 1000

            # Determine status based on thresholds
            alerts = []
            if cpu_percent / 100 > self.alert_thresholds["cpu_usage"]:
                alerts.append(f"High CPU usage: {cpu_percent:.1f}%")

            if memory.percent / 100 > self.alert_thresholds["memory_usage"]:
                alerts.append(f"High memory usage: {memory.percent:.1f}%")

            if disk.percent / 100 > self.alert_thresholds["disk_usage"]:
                alerts.append(f"High disk usage: {disk.percent:.1f}%")

            # Determine overall status
            if any("High" in alert for alert in alerts):
                if cpu_percent > 95 or memory.percent > 95 or disk.percent > 98:
                    status = HealthStatus.CRITICAL
                else:
                    status = HealthStatus.DEGRADED
                message = "; ".join(alerts)
            else:
                status = HealthStatus.HEALTHY
                message = "System resources within normal limits"

            details = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024**3),
                "alerts": alerts,
            }

            return HealthCheck(
                component="system_resources",
                component_type=ComponentType.SYSTEM_RESOURCES,
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details=details,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                component="system_resources",
                component_type=ComponentType.SYSTEM_RESOURCES,
                status=HealthStatus.CRITICAL,
                message=f"System resources check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details={"error": str(e)},
            )

    async def _check_file_system_health(self) -> HealthCheck:
        """Check file system health and upload directory"""
        start_time = time.time()

        try:
            from pathlib import Path

            # Check upload directory
            upload_dir = Path(settings.UPLOAD_DIR)

            # Ensure upload directory exists and is writable
            upload_dir.mkdir(parents=True, exist_ok=True)

            # Test write permissions
            test_file = upload_dir / "health_check_test.txt"
            test_file.write_text("health check test")
            test_content = test_file.read_text()
            test_file.unlink()  # Clean up

            response_time = (time.time() - start_time) * 1000

            if test_content == "health check test":
                status = HealthStatus.HEALTHY
                message = "File system operations successful"
            else:
                status = HealthStatus.DEGRADED
                message = "File system operations partially working"

            # Get directory info
            try:
                files_count = len(list(upload_dir.iterdir()))
                total_size = sum(
                    f.stat().st_size for f in upload_dir.rglob("*") if f.is_file()
                )
            except Exception:
                files_count = 0
                total_size = 0

            details = {
                "upload_dir_exists": upload_dir.exists(),
                "upload_dir_writable": True,
                "files_count": files_count,
                "total_size_mb": total_size / (1024 * 1024),
                "response_time_ms": response_time,
            }

            return HealthCheck(
                component="file_system",
                component_type=ComponentType.FILE_SYSTEM,
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details=details,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                component="file_system",
                component_type=ComponentType.FILE_SYSTEM,
                status=HealthStatus.CRITICAL,
                message=f"File system check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details={"error": str(e)},
            )

    async def _check_celery_health(self) -> HealthCheck:
        """Check Celery worker health"""
        start_time = time.time()

        try:
            # Import Celery app
            from app.core.celery_app import celery_app

            # Check if workers are active
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            registered_tasks = inspect.registered()

            response_time = (time.time() - start_time) * 1000

            if active_workers:
                worker_count = len(active_workers)
                total_active_tasks = sum(
                    len(tasks) for tasks in active_workers.values()
                )

                status = HealthStatus.HEALTHY
                message = f"Celery healthy: {worker_count} workers, {total_active_tasks} active tasks"

                details = {
                    "workers_count": worker_count,
                    "active_tasks": total_active_tasks,
                    "workers": list(active_workers.keys()),
                    "registered_tasks_count": len(registered_tasks)
                    if registered_tasks
                    else 0,
                }
            else:
                status = HealthStatus.CRITICAL
                message = "No Celery workers available"
                details = {"workers_count": 0, "error": "No active workers"}

            return HealthCheck(
                component="celery",
                component_type=ComponentType.CELERY,
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details=details,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                component="celery",
                component_type=ComponentType.CELERY,
                status=HealthStatus.CRITICAL,
                message=f"Celery health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.now().isoformat(),
                details={"error": str(e)},
            )

    def _determine_overall_status(self, checks: List[HealthCheck]) -> HealthStatus:
        """Determine overall system health status"""
        if not checks:
            return HealthStatus.CRITICAL

        critical_count = len([c for c in checks if c.status == HealthStatus.CRITICAL])
        unhealthy_count = len([c for c in checks if c.status == HealthStatus.UNHEALTHY])
        degraded_count = len([c for c in checks if c.status == HealthStatus.DEGRADED])

        # Critical if any critical components or too many failures
        if critical_count > 0 or (unhealthy_count + critical_count) > len(checks) / 2:
            return HealthStatus.CRITICAL

        # Unhealthy if multiple components are down
        if unhealthy_count > 1:
            return HealthStatus.UNHEALTHY

        # Degraded if any components are degraded or unhealthy
        if degraded_count > 0 or unhealthy_count > 0:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def _generate_health_summary(self, checks: List[HealthCheck]) -> Dict[str, Any]:
        """Generate health summary statistics"""
        if not checks:
            return {}

        status_counts = {}
        for status in HealthStatus:
            status_counts[status] = len([c for c in checks if c.status == status])

        avg_response_time = sum(c.response_time_ms for c in checks) / len(checks)

        return {
            "total_checks": len(checks),
            "status_counts": status_counts,
            "avg_response_time_ms": avg_response_time,
            "slowest_component": max(
                checks, key=lambda c: c.response_time_ms
            ).component,
            "fastest_component": min(
                checks, key=lambda c: c.response_time_ms
            ).component,
        }

    async def _store_health_check_result(self, report: SystemHealthReport):
        """Store health check result in Redis for monitoring"""
        if not redis_service.is_connected():
            return

        try:
            # Store latest health report
            redis_service.setex(
                "health:latest_report",
                3600,  # 1 hour TTL
                json.dumps(asdict(report), default=str),
            )

            # Store in health history (keep last 24 reports)
            redis_service.lpush(
                "health:history", json.dumps(asdict(report), default=str)
            )
            redis_service.ltrim("health:history", 0, 23)

            # Store component-specific metrics
            for check in report.checks:
                key = f"health:component:{check.component}"
                redis_service.setex(key, 3600, json.dumps(asdict(check), default=str))

        except Exception as e:
            logger.error(f"Failed to store health check result: {e}")

    async def get_health_history(self, hours: int = 24) -> List[SystemHealthReport]:
        """Get health check history"""
        if not redis_service.is_connected():
            return []

        try:
            history_data = redis_service.lrange("health:history", 0, hours - 1)
            reports = []

            for data in history_data:
                report_dict = json.loads(data)
                # Convert dict back to SystemHealthReport
                checks = [
                    HealthCheck(**check_dict) for check_dict in report_dict["checks"]
                ]
                report = SystemHealthReport(
                    overall_status=report_dict["overall_status"],
                    timestamp=report_dict["timestamp"],
                    checks=checks,
                    summary=report_dict["summary"],
                    alerts=report_dict["alerts"],
                )
                reports.append(report)

            return reports

        except Exception as e:
            logger.error(f"Failed to get health history: {e}")
            return []

    async def initialize(self):
        """Initialize health monitoring service"""
        logger.info("Health monitoring service initialized")

    async def cleanup(self):
        """Cleanup health monitoring service"""
        logger.info("Health monitoring service cleaned up")

    async def get_real_time_metrics(self):
        """Get real-time system metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get real-time metrics: {e}")
            return {}


# Global health monitoring service instance
health_monitor = HealthMonitoringService()
