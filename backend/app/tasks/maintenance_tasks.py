"""
Maintenance tasks for system cleanup and monitoring.
"""

from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, and_
import asyncio

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.models.transformation import Transformation as TransformationDB


# Create async database session for maintenance tasks
async_engine = create_async_engine(settings.get_database_url(), echo=settings.DEBUG)

AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


@celery_app.task(name="app.tasks.maintenance_tasks.cleanup_expired_tasks")
def cleanup_expired_tasks():
    """
    Clean up expired task results and failed transformations
    """
    return asyncio.run(_cleanup_expired_tasks_async())


async def _cleanup_expired_tasks_async():
    """
    Async implementation of cleanup
    """
    async with AsyncSessionLocal() as db:
        try:
            # Clean up old failed transformations (older than 7 days)
            cutoff_date = datetime.utcnow() - timedelta(days=7)

            # Delete failed transformations older than cutoff
            stmt = delete(TransformationDB).where(
                and_(
                    TransformationDB.status == "failed",
                    TransformationDB.updated_at < cutoff_date,
                )
            )

            result = await db.execute(stmt)
            deleted_count = result.rowcount

            await db.commit()

            # Clean up Celery result backend (Redis)
            # This removes old task results from Redis
            celery_app.backend.cleanup()

            return {
                "deleted_failed_transformations": deleted_count,
                "cleanup_date": datetime.utcnow().isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
            }

        except Exception as e:
            await db.rollback()
            raise e


@celery_app.task(name="app.tasks.maintenance_tasks.health_check")
def health_check():
    """
    Periodic health check for the task system
    """
    return asyncio.run(_health_check_async())


async def _health_check_async():
    """
    Async health check implementation
    """
    health_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "checks": {},
    }

    try:
        # Check database connection
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
            health_status["checks"]["database"] = "ok"

        # Check Redis connection (Celery broker)
        try:
            broker_info = celery_app.control.inspect().stats()
            if broker_info:
                health_status["checks"]["redis_broker"] = "ok"
            else:
                health_status["checks"]["redis_broker"] = "no_workers"
        except Exception:
            health_status["checks"]["redis_broker"] = "error"

        # Check active workers
        try:
            active_workers = celery_app.control.inspect().active()
            worker_count = len(active_workers) if active_workers else 0
            health_status["checks"]["active_workers"] = worker_count
        except Exception:
            health_status["checks"]["active_workers"] = 0

        # Check pending tasks
        try:
            reserved_tasks = celery_app.control.inspect().reserved()
            if reserved_tasks:
                pending_count = sum(len(tasks) for tasks in reserved_tasks.values())
                health_status["checks"]["pending_tasks"] = pending_count
            else:
                health_status["checks"]["pending_tasks"] = 0
        except Exception:
            health_status["checks"]["pending_tasks"] = "unknown"

        return health_status

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
        return health_status


@celery_app.task(name="app.tasks.maintenance_tasks.monitor_long_running_tasks")
def monitor_long_running_tasks():
    """
    Monitor and potentially terminate long-running tasks
    """
    return asyncio.run(_monitor_long_running_tasks_async())


async def _monitor_long_running_tasks_async():
    """
    Async implementation of long-running task monitoring
    """
    try:
        # Get active tasks
        active_tasks = celery_app.control.inspect().active()

        if not active_tasks:
            return {
                "message": "No active tasks",
                "timestamp": datetime.utcnow().isoformat(),
            }

        long_running_tasks = []
        current_time = datetime.utcnow()

        for worker, tasks in active_tasks.items():
            for task in tasks:
                # Check if task has been running for more than 30 minutes
                task_start_time = datetime.fromtimestamp(task.get("time_start", 0))
                runtime = current_time - task_start_time

                if runtime > timedelta(minutes=30):
                    long_running_tasks.append(
                        {
                            "worker": worker,
                            "task_id": task.get("id"),
                            "task_name": task.get("name"),
                            "runtime_minutes": runtime.total_seconds() / 60,
                            "args": task.get("args", []),
                        }
                    )

        # Log long-running tasks (could also send alerts)
        if long_running_tasks:
            # In production, you might want to send alerts or terminate these tasks
            return {
                "long_running_tasks": long_running_tasks,
                "count": len(long_running_tasks),
                "timestamp": current_time.isoformat(),
            }

        return {
            "message": "No long-running tasks detected",
            "timestamp": current_time.isoformat(),
        }

    except Exception as e:
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}
