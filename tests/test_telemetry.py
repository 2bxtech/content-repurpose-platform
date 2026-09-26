"""Tracing is off by default and, when on, records API and executor spans.

The tracer provider is process-global, so each scenario runs in a subprocess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"

ENABLED = """
import asyncio, json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from app.core import telemetry

exporter = InMemorySpanExporter()
assert telemetry.setup_tracing("test-api", exporter=exporter)

from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
client.get("/")
try:
    with client.websocket_connect("/api/ws?token=SECRET-TOKEN-VALUE&workspace_id=w-1"):
        pass
except Exception:
    pass  # rejected: the token is fake; only what gets exported matters here

from app.models.transformation import TransformationStatus
from app.services import transformation_runner as runner

async def fake_finish(db, transformation, error=None, **fields):
    transformation.status = TransformationStatus.FAILED if error else TransformationStatus.COMPLETED
    transformation.error_message = error
    for key, value in fields.items():
        setattr(transformation, key, value)
    return transformation

usage = SimpleNamespace(total_tokens=42, input_tokens=20, output_tokens=22, total_cost=0.0021)
manager = MagicMock()
manager.generate_text = AsyncMock(
    return_value=SimpleNamespace(content="done", provider="mock", usage_metrics=usage)
)
row = SimpleNamespace(
    id="t-1", workspace_id="w-1", transformation_type=SimpleNamespace(value="SUMMARY"),
    parameters={}, status=TransformationStatus.PROCESSING, error_message=None,
)
with patch.object(runner, "get_ai_provider_manager", return_value=manager), \\
        patch.object(runner, "finish", fake_finish):
    asyncio.run(runner.execute_transformation(MagicMock(), row, "some text"))

trace.get_tracer_provider().force_flush()
spans = exporter.get_finished_spans()
print(json.dumps({
    "names": [s.name for s in spans],
    "executor": next(dict(s.attributes) for s in spans if s.name == "transformation.execute"),
    "service": spans[0].resource.attributes["service.name"],
    "leaks_token": any(
        "SECRET-TOKEN-VALUE" in str(value) for s in spans for value in (s.attributes or {}).values()
    ),
}))
"""

DISABLED = """
from app.core import telemetry
print(telemetry.setup_tracing("test-api"))
"""


def _run(script: str) -> str:
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "SECRET_KEY": "test-only-access-signing-key-0123456789abcdef",
        "REFRESH_SECRET_KEY": "test-only-refresh-signing-key-0123456789abcdef",
        "DATABASE_URL": "postgresql+asyncpg://unit:unit@127.0.0.1:9/unit_tests",
        "REDIS_URL": "redis://127.0.0.1:9/0",
    }
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout.strip().splitlines()[-1]


def test_tracing_is_a_no_op_without_an_endpoint():
    assert _run(DISABLED) == "False"


def test_api_requests_and_transformations_are_traced():
    out = json.loads(_run(ENABLED))

    assert out["service"] == "test-api"
    assert out["leaks_token"] is False
    assert any(name.startswith("GET") for name in out["names"]), out["names"]
    attrs = out["executor"]
    assert attrs["transformation.status"] == "COMPLETED"
    assert attrs["ai.provider"] == "mock"
    assert attrs["ai.tokens"] == 42
    assert attrs["workspace.id"] == "w-1"
