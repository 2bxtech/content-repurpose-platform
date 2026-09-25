"""Celery application: Redis broker/backend, JSON only, one task at a time per process."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "content_repurpose",
    broker=settings.get_celery_broker_url(),
    backend=settings.get_celery_result_backend(),
    include=["app.tasks.transformation_tasks", "app.tasks.maintenance_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
    # AI calls are slow and billed: don't let one worker hoard queued work.
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    # A transformation is one provider call with bounded retries and failover; anything
    # past these limits is hung. Hard limit < STUCK_AFTER (maintenance_tasks.py).
    task_soft_time_limit=600,
    task_time_limit=720,
    # Fail fast in the API if the broker is down instead of blocking the request.
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5},
    worker_hijack_root_logger=False,
    beat_schedule={
        "fail-stuck-transformations": {
            "task": "app.tasks.maintenance_tasks.fail_stuck_transformations",
            "schedule": 300.0,
        },
    },
)
