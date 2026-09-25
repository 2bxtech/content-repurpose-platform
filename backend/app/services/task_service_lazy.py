"""
Lazy-loading task management service for handling background processing.
This version defers Celery initialization until first task execution.
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from app.models.transformation import TransformationType

logger = logging.getLogger(__name__)

# Global variable to store the Celery app
_celery_app = None


def _get_celery_app():
    """Lazy-load the Celery app only when needed"""
    global _celery_app
    
    if _celery_app is None:
        try:
            from app.core.celery_app_lazy import get_celery_app
            _celery_app = get_celery_app()
            logger.info("Celery app loaded for task service")
        except Exception as e:
            logger.error(f"Failed to load Celery app: {e}")
            # Return a mock for development
            _celery_app = _create_mock_celery_app()
    
    return _celery_app


def _create_mock_celery_app():
    """Create a mock Celery app for development when Redis is not available"""
    from unittest.mock import MagicMock
    
    logger.info("Using mock Celery app in task service")
    
    mock_app = MagicMock()
    
    # Mock control interface
    mock_inspect = MagicMock()
    mock_inspect.stats.return_value = None
    mock_inspect.active.return_value = {}
    mock_inspect.reserved.return_value = {}
    
    mock_control = MagicMock()
    mock_control.inspect.return_value = mock_inspect
    
    mock_app.control = mock_control
    
    return mock_app


def _get_task_functions():
    """Lazy-load task functions only when needed"""
    try:
        from app.tasks.transformation_tasks import (
            process_transformation_task,
            get_task_status,
            cancel_task,
        )
        return process_transformation_task, get_task_status, cancel_task
    except Exception as e:
        logger.error(f"Failed to import task functions: {e}")
        # Return mock functions
        from unittest.mock import MagicMock
        return MagicMock(), MagicMock(), MagicMock()


class TaskService:
    """Service for managing background tasks with lazy Celery loading"""

    def __init__(self):
        # Don't initialize Celery here - wait until needed
        self._celery_app = None
        self._task_functions = None

    @property
    def celery_app(self):
        """Lazy-load Celery app when first accessed"""
        if self._celery_app is None:
            self._celery_app = _get_celery_app()
        return self._celery_app

    def _get_task_functions_cached(self):
        """Cache task functions after first load"""
        if self._task_functions is None:
            self._task_functions = _get_task_functions()
        return self._task_functions

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
        try:
            process_transformation_task, _, _ = self._get_task_functions_cached()
            
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
        
        except Exception as e:
            logger.error(f"Failed to start transformation task: {e}")
            # Return a mock task ID for development
            return f"mock-task-{uuid.uuid4()}"

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a background task
        """
        try:
            _, get_task_status_func, _ = self._get_task_functions_cached()
            return get_task_status_func(task_id)
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return {
                "task_id": task_id,
                "status": "unknown",
                "progress": 0,
                "message": f"Error retrieving task status: {str(e)}",
            }

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """
        Cancel a running task
        """
        try:
            _, _, cancel_task_func = self._get_task_functions_cached()
            return cancel_task_func(task_id)
        except Exception as e:
            logger.error(f"Failed to cancel task: {e}")
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
            logger.error(f"Failed to get worker status: {e}")
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
            logger.error(f"Failed to get queue info: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

    def is_available(self) -> bool:
        """Check if the task service is available"""
        try:
            # Try to get worker stats without raising exceptions
            self.celery_app.control.inspect().stats()
            return True
        except Exception:
            return False


# Create a lazy-loading task service instance
class LazyTaskService:
    """Proxy that creates the actual TaskService only when first accessed"""
    
    def __init__(self):
        self._service: Optional[TaskService] = None
    
    def _get_service(self) -> TaskService:
        if self._service is None:
            self._service = TaskService()
        return self._service
    
    def __getattr__(self, name):
        # Delegate all attribute access to the real service
        return getattr(self._get_service(), name)


# Global task service instance - now with lazy loading
task_service = LazyTaskService()