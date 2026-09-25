"""
Celery application configuration for background task processing.
"""

from celery import Celery
from app.core.config import settings

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
    task_always_eager=False,  # Set to True for testing without Redis
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
