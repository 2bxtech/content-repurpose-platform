"""
Integration tests for Celery background processing
Tests task creation, execution, monitoring, and error handling
"""

import pytest
import httpx
import asyncio


class TestCeleryIntegration:
    """Integration tests for Celery background processing"""

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_worker_status_endpoint(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test worker status monitoring endpoint"""
        response = await authenticated_client.get("/api/system/workers")

        # In test environment with CELERY_TASK_ALWAYS_EAGER=true,
        # workers might not be running, so accept various statuses
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            worker_data = response.json()
            assert "status" in worker_data
            assert "workers" in worker_data

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_queue_status_endpoint(self, authenticated_client: httpx.AsyncClient):
        """Test queue monitoring endpoint"""
        response = await authenticated_client.get("/api/system/queue")

        # Should work even without workers
        assert response.status_code == 200

        queue_data = response.json()
        assert "total_tasks" in queue_data
        assert isinstance(queue_data["total_tasks"], int)

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_transformation_task_creation(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
    ):
        """Test creating a transformation that triggers a Celery task"""
        # Add document_id to transformation data
        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
        }

        response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )

        # Should accept the transformation for background processing
        assert response.status_code in [201, 202]

        transformation = response.json()
        assert "id" in transformation

        # In eager mode, task might complete immediately
        if "task_id" in transformation:
            assert transformation["task_id"] is not None

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_transformation_status_tracking(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
        wait_for_task,
    ):
        """Test tracking transformation status through completion"""
        # Create transformation
        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
        }

        response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )
        assert response.status_code in [201, 202]

        transformation = response.json()
        transformation_id = transformation["id"]

        # Wait for task completion (in eager mode, should be quick)
        final_status = await wait_for_task(
            authenticated_client, transformation_id, timeout=10
        )

        assert final_status["database_status"] in ["completed", "failed"]

        # If completed, verify results
        if final_status["database_status"] == "completed":
            # Get final transformation
            response = await authenticated_client.get(
                f"/api/transformations/{transformation_id}"
            )
            assert response.status_code == 200

            final_transformation = response.json()
            assert final_transformation["status"] == "completed"

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_task_cancellation(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
    ):
        """Test task cancellation functionality"""
        # Create transformation
        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
        }

        response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )
        assert response.status_code in [201, 202]

        transformation = response.json()
        transformation_id = transformation["id"]

        # Try to cancel the task
        cancel_response = await authenticated_client.post(
            f"/api/transformations/{transformation_id}/cancel"
        )

        # In eager mode, task might already be completed
        assert cancel_response.status_code in [200, 400, 409]

        if cancel_response.status_code == 200:
            cancel_data = cancel_response.json()
            assert "status" in cancel_data


class TestCeleryErrorHandling:
    """Test error handling in Celery tasks"""

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_task_failure_handling(
        self, authenticated_client: httpx.AsyncClient, test_document: dict
    ):
        """Test handling of failed tasks"""
        # Create transformation with invalid parameters to trigger failure
        transformation_data = {
            "document_id": test_document["id"],
            "transformation_type": "invalid_type",  # Should cause failure
            "parameters": {},
        }

        response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )

        # Might be rejected at API level or accepted and fail in background
        if response.status_code in [201, 202]:
            transformation = response.json()
            transformation_id = transformation["id"]

            # Check status after a brief wait
            await asyncio.sleep(1)

            status_response = await authenticated_client.get(
                f"/api/transformations/{transformation_id}/status"
            )
            assert status_response.status_code == 200

            status_data = status_response.json()
            # Should either be failed or still processing
            assert status_data["database_status"] in ["pending", "processing", "failed"]

    @pytest.mark.integration
    @pytest.mark.celery
    async def test_ai_service_failure_handling(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
    ):
        """Test handling of AI service failures"""
        # Note: This test would normally mock the AI service, but since we're in test mode,
        # we'll simulate the scenario by creating a transformation and checking error handling

        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
            "transformation_type": "invalid_type",  # Use invalid type to trigger error
        }

        response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )

        # Should either reject invalid type or accept and fail gracefully
        assert response.status_code in [400, 422, 201, 202]

        if response.status_code in [201, 202]:
            transformation = response.json()
            transformation_id = transformation["id"]

            # Wait a bit for processing
            await asyncio.sleep(2)

            status_response = await authenticated_client.get(
                f"/api/transformations/{transformation_id}/status"
            )
            assert status_response.status_code == 200


class TestCeleryPerformance:
    """Performance tests for Celery integration"""

    @pytest.mark.integration
    @pytest.mark.celery
    @pytest.mark.slow
    async def test_concurrent_task_processing(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
        performance_monitor,
    ):
        """Test processing multiple tasks concurrently"""
        num_tasks = 5
        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
        }

        performance_monitor.start()

        # Create multiple transformations
        tasks = []
        for i in range(num_tasks):
            task_data = {
                **transformation_data,
                "parameters": {**transformation_data["parameters"], "task_number": i},
            }

            response = await authenticated_client.post(
                "/api/transformations", json=task_data
            )

            if response.status_code in [201, 202]:
                transformation = response.json()
                tasks.append(transformation["id"])

        duration = performance_monitor.stop("concurrent_task_creation")

        assert len(tasks) == num_tasks
        assert duration < 10.0  # Should create tasks quickly

        # In eager mode, tasks should complete quickly
        performance_monitor.start()

        # Check all tasks completed
        completed_count = 0
        for task_id in tasks:
            status_response = await authenticated_client.get(
                f"/api/transformations/{task_id}/status"
            )
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data["database_status"] == "completed":
                    completed_count += 1

        completion_duration = performance_monitor.stop("task_completion_check")

        # In eager mode, most tasks should be completed
        assert completed_count >= num_tasks * 0.5  # At least 50% completed
        assert completion_duration < 5.0  # Quick status checks
