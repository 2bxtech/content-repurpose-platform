"""
Task management service for handling background processing.
"""

import uuid
from typing import Dict, Any
from datetime import datetime

from app.core.celery_app import celery_app
from app.tasks.transformation_tasks import (
    process_transformation_task,
    get_task_status,
    cancel_task,
)
from app.models.transformation import TransformationType


class TaskService:
    """Service for managing background tasks"""

    def __init__(self):
        self.celery_app = celery_app

    def start_transformation_task(
        self,
        transformation_id: uuid.UUID,
        document_path: str,
        transformation_type: TransformationType,
        parameters: Dict[str, Any],
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> str:
        """
        Start a background transformation task

        Returns:
            task_id: Celery task ID for tracking
        """
        # Start the Celery task
        task = process_transformation_task.delay(
            str(transformation_id),
            document_path,
            transformation_type.value,
            parameters,
            str(workspace_id),
            str(user_id),
        )

        return task.id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a background task
        """
        try:
            return get_task_status(task_id)
        except Exception as e:
            return {
                "task_id": task_id,
                "status": "error",
                "progress": 0,
                "message": f"Error retrieving task status: {str(e)}",
            }

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """
        Cancel a running task
        """
        try:
            return cancel_task(task_id)
        except Exception as e:
            return {
                "task_id": task_id,
                "status": "error",
                "message": f"Error cancelling task: {str(e)}",
            }

    def get_worker_status(self) -> Dict[str, Any]:
        """
        Get status of Celery workers
        """
        try:
            # Get worker stats
            stats = self.celery_app.control.inspect().stats()
            active = self.celery_app.control.inspect().active()
            reserved = self.celery_app.control.inspect().reserved()

            return {
                "workers": {
                    "stats": stats,
                    "active_tasks": active,
                    "reserved_tasks": reserved,
                },
                "status": "healthy" if stats else "no_workers",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def get_queue_info(self) -> Dict[str, Any]:
        """
        Get information about task queues
        """
        try:
            # Get active and reserved tasks
            active_tasks = self.celery_app.control.inspect().active()
            reserved_tasks = self.celery_app.control.inspect().reserved()

            # Count tasks
            active_count = 0
            reserved_count = 0

            if active_tasks:
                active_count = sum(len(tasks) for tasks in active_tasks.values())

            if reserved_tasks:
                reserved_count = sum(len(tasks) for tasks in reserved_tasks.values())

            return {
                "active_tasks": active_count,
                "reserved_tasks": reserved_count,
                "total_pending": active_count + reserved_count,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}


# Global task service instance
task_service = TaskService()
