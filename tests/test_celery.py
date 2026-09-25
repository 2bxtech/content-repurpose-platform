"""
Background processing: POST /api/transformations queues a Celery task, the worker
runs it and records COMPLETED/FAILED on the transformation row.
"""

import asyncio
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.transformation import TransformationStatus
from app.services.ai_providers.base import AIProviderError
from app.services.transformation_runner import execute_transformation


@pytest.mark.integration
@pytest.mark.celery
class TestCeleryIntegration:
    """Transformations run on the worker of the running stack"""

    async def test_transformation_task_creation(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
    ):
        response = await authenticated_client.post(
            "/api/transformations", json={**sample_transformation_data, "document_id": test_document["id"]}
        )
        assert response.status_code == 201

        transformation = response.json()
        assert transformation["id"]
        assert transformation["task_id"]
        # The worker can finish before the create response is built.
        assert transformation["status"] in ("PENDING", "PROCESSING", "COMPLETED")

    async def test_transformation_status_tracking(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
        wait_for_transformation,
    ):
        response = await authenticated_client.post(
            "/api/transformations", json={**sample_transformation_data, "document_id": test_document["id"]}
        )
        assert response.status_code == 201
        transformation_id = response.json()["id"]

        final = await wait_for_transformation(authenticated_client, transformation_id)

        assert final["status"] == "COMPLETED"
        assert final["result"]
        assert final["error_message"] is None


@pytest.mark.integration
@pytest.mark.celery
class TestCeleryErrorHandling:
    """Bad requests are refused up front; failures on the worker are recorded, not lost"""

    async def test_invalid_type_rejected_before_queueing(
        self, authenticated_client: httpx.AsyncClient, test_document: dict
    ):
        response = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": test_document["id"], "transformation_type": "invalid_type", "parameters": {}},
        )
        assert response.status_code == 422
        listed = (await authenticated_client.get("/api/transformations")).json()
        assert listed["count"] == 0

    async def test_task_failure_handling(
        self, authenticated_client: httpx.AsyncClient, wait_for_transformation
    ):
        """A document with no extractable text makes the worker mark the job FAILED"""
        upload = await authenticated_client.post(
            "/api/documents/upload",
            data={"title": "Blank"},
            files={"file": ("blank.txt", b"   \n\n   ", "text/plain")},
        )
        assert upload.status_code == 201, upload.text

        response = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": upload.json()["id"], "transformation_type": "SUMMARY", "parameters": {}},
        )
        assert response.status_code == 201

        final = await wait_for_transformation(authenticated_client, response.json()["id"])
        assert final["status"] == "FAILED"
        assert "no extractable text" in final["error_message"]
        assert final["result"] is None


@pytest.mark.unit
@pytest.mark.celery
class _FakeSession:
    """Just enough AsyncSession for the executor: records the terminal UPDATE and
    applies it on refresh, the way reloading the row would."""

    def __init__(self, rowcount: int = 1):
        self.commits = 0
        self.updates = []
        self.rowcount = rowcount

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def execute(self, stmt):
        params = stmt.compile().params
        self.updates.append({k: v for k, v in params.items() if not k.endswith("_1")})
        return SimpleNamespace(rowcount=self.rowcount)

    async def refresh(self, obj):
        if self.rowcount and self.updates:
            for key, value in self.updates[-1].items():
                setattr(obj, key, value)


class TestTransformationRunner:
    """The code the worker runs, with the AI provider manager replaced"""

    @staticmethod
    def _transformation():
        return SimpleNamespace(
            id=uuid.uuid4(),
            transformation_type="SUMMARY",
            parameters={},
            status=TransformationStatus.PENDING,
            result=None,
            error_message=None,
        )

    async def test_ai_service_failure_handling(self):
        db = _FakeSession()
        manager = MagicMock()
        manager.generate_text = AsyncMock(side_effect=AIProviderError("all providers down", "openai"))
        transformation = self._transformation()

        with patch("app.services.transformation_runner.get_ai_provider_manager", return_value=manager):
            result = await execute_transformation(db, transformation, "Some document text")

        assert result.status == TransformationStatus.FAILED
        assert "AI provider error" in result.error_message
        assert "all providers down" in result.error_message
        assert result.result is None
        # PROCESSING is committed before the call, the terminal state after it
        assert db.commits == 2

    async def test_success_records_result_and_usage(self):
        db = _FakeSession()
        usage = SimpleNamespace(total_tokens=30, input_tokens=10, output_tokens=20, total_cost=0.01)
        manager = MagicMock()
        manager.generate_text = AsyncMock(
            return_value=SimpleNamespace(content="summary text", provider="mock", usage_metrics=usage)
        )
        transformation = self._transformation()

        with patch("app.services.transformation_runner.get_ai_provider_manager", return_value=manager):
            result = await execute_transformation(db, transformation, "Some document text")

        assert result.status == TransformationStatus.COMPLETED
        assert result.result == "summary text"
        assert result.ai_provider == "mock"
        assert result.tokens_used == 30
        assert result.ai_cost == 0.01
        assert result.error_message is None

    async def test_empty_content_fails_without_calling_provider(self):
        db = _FakeSession()
        manager = MagicMock()
        manager.generate_text = AsyncMock()
        transformation = self._transformation()

        with patch("app.services.transformation_runner.get_ai_provider_manager", return_value=manager):
            result = await execute_transformation(db, transformation, "   ")

        assert result.status == TransformationStatus.FAILED
        manager.generate_text.assert_not_awaited()

    async def test_late_result_does_not_overwrite_a_timed_out_row(self):
        # The sweeper already failed the row, so the conditional UPDATE matches nothing.
        db = _FakeSession(rowcount=0)
        usage = SimpleNamespace(total_tokens=1, input_tokens=1, output_tokens=0, total_cost=0.0)
        manager = MagicMock()
        manager.generate_text = AsyncMock(
            return_value=SimpleNamespace(content="late", provider="mock", usage_metrics=usage)
        )
        transformation = self._transformation()

        with patch("app.services.transformation_runner.get_ai_provider_manager", return_value=manager):
            result = await execute_transformation(db, transformation, "Some document text")

        assert result.result is None
        assert result.status != TransformationStatus.COMPLETED


@pytest.mark.integration
@pytest.mark.celery
class TestCeleryPerformance:
    """Performance tests for Celery integration"""

    @pytest.mark.slow
    async def test_concurrent_task_processing(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: dict,
        sample_transformation_data: dict,
        wait_for_transformation,
    ):
        num_tasks = 5
        started = time.perf_counter()
        responses = await asyncio.gather(
            *[
                authenticated_client.post(
                    "/api/transformations",
                    json={
                        **sample_transformation_data,
                        "document_id": test_document["id"],
                        "parameters": {"task_number": i},
                    },
                )
                for i in range(num_tasks)
            ]
        )
        assert [r.status_code for r in responses] == [201] * num_tasks
        assert time.perf_counter() - started < 10.0  # queueing is fast; work happens on the worker

        ids = [r.json()["id"] for r in responses]
        assert len(set(ids)) == num_tasks

        finals = await asyncio.gather(
            *[wait_for_transformation(authenticated_client, tid, timeout=90) for tid in ids]
        )
        assert [f["status"] for f in finals] == ["COMPLETED"] * num_tasks
