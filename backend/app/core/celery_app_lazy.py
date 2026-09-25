"""
Lazy-loading Celery application configuration for background task processing.
This version defers Redis connection until first task execution.
"""

import os
from typing import Optional
from celery import Celery
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Global variable to store the Celery instance
_celery_app: Optional[Celery] = None
_celery_initialized = False


def get_celery_app() -> Celery:
    """
    Get or create the Celery application instance with lazy initialization.
    This defers Redis connection until the first time Celery is actually needed.
    """
    global _celery_app, _celery_initialized
    
    if _celery_app is None or not _celery_initialized:
        # Check if we should disable Celery for debugging
        if os.getenv("DISABLE_CELERY", "false").lower() == "true":
            logger.info("Celery disabled via DISABLE_CELERY environment variable")
            return _create_mock_celery()
        
        try:
            _celery_app = _create_celery_app()
            _celery_initialized = True
            logger.info("Celery app initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Celery app: {e}")
            # Return mock Celery for development/testing
            return _create_mock_celery()
    
    return _celery_app


def _create_celery_app() -> Celery:
    """Create and configure the actual Celery application"""
    
    # Create Celery instance
    celery_app = Celery(
        "content_repurpose",
        include=["app.tasks.transformation_tasks", "app.tasks.maintenance_tasks"],
    )

    # Configure broker and backend URLs
    celery_app.conf.broker_url = settings.get_celery_broker_url()
    celery_app.conf.result_backend = settings.get_celery_result_backend()

    # Celery configuration
    celery_app.conf.update(
        # Task settings
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        # Task execution settings
        task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,  # Use from settings
        task_eager_propagates=True,
        task_ignore_result=False,
        task_store_eager_result=True,
        # Result backend settings
        result_expires=3600,  # Results expire after 1 hour
        result_backend_transport_options={
            "master_name": "mymaster",
            "visibility_timeout": 3600,
        },
        # Worker settings
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        worker_disable_rate_limits=False,
        # Retry settings
        task_default_retry_delay=60,  # Retry after 60 seconds
        task_max_retries=3,
        # Beat scheduler settings (for periodic tasks)
        beat_schedule={
            "cleanup-expired-tasks": {
                "task": "app.tasks.maintenance_tasks.cleanup_expired_tasks",
                "schedule": 3600.0,  # Run every hour
            },
            "health-check": {
                "task": "app.tasks.maintenance_tasks.health_check",
                "schedule": 300.0,  # Run every 5 minutes
            },
            "monitor-long-running-tasks": {
                "task": "app.tasks.maintenance_tasks.monitor_long_running_tasks",
                "schedule": 600.0,  # Run every 10 minutes
            },
        },
        # Monitoring
        worker_send_task_events=True,
        task_send_sent_event=True,
        # Security
        worker_hijack_root_logger=False,
        worker_log_color=False,
    )

    # Additional Redis configuration if password is set
    if settings.REDIS_PASSWORD:
        broker_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        result_backend = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        celery_app.conf.broker_url = broker_url
        celery_app.conf.result_backend = result_backend

    return celery_app


def _create_mock_celery():
    """Create a mock Celery app for development/testing when Redis is not available"""
    from unittest.mock import MagicMock
    
    logger.info("Creating mock Celery app (Redis not available)")
    
    # Create a minimal mock that satisfies basic Celery interface
    mock_celery = MagicMock()
    
    # Mock task decorator
    def mock_task(*args, **kwargs):
        def decorator(func):
            # Create a mock task that returns a mock result
            mock_task_instance = MagicMock()
            mock_task_instance.delay = MagicMock()
            mock_task_instance.apply_async = MagicMock()
            
            # Mock result
            mock_result = MagicMock()
            mock_result.id = "mock-task-id"
            mock_result.state = "SUCCESS"
            mock_result.result = "Mock task completed"
            
            mock_task_instance.delay.return_value = mock_result
            mock_task_instance.apply_async.return_value = mock_result
            
            return mock_task_instance
        return decorator
    
    mock_celery.task = mock_task
    
    # Mock control interface
    mock_inspect = MagicMock()
    mock_inspect.stats.return_value = None
    mock_inspect.active.return_value = None
    mock_inspect.reserved.return_value = None
    
    mock_control = MagicMock()
    mock_control.inspect.return_value = mock_inspect
    
    mock_celery.control = mock_control
    
    # Mock conf
    mock_celery.conf = MagicMock()
    mock_celery.conf.broker_url = "memory://"
    mock_celery.conf.result_backend = "cache+memory://"
    
    return mock_celery


def is_celery_available() -> bool:
    """Check if Celery is available and properly configured"""
    try:
        celery_app = get_celery_app()
        # Try to inspect - this will fail if Redis is not available
        celery_app.control.inspect().stats()
        return True
    except Exception:
        return False


def reset_celery_app():
    """Reset the Celery app instance - useful for testing"""
    global _celery_app, _celery_initialized
    _celery_app = None
    _celery_initialized = False


# For backward compatibility, provide the app instance
# But now it's lazy-loaded
celery_app = get_celery_app()