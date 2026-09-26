"""OpenTelemetry tracing for the API and the Celery worker.

Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (the standard OTel variable; the
exporter reads it and OTEL_EXPORTER_OTLP_HEADERS itself), so there's no cost
by default. When on, one trace follows a transformation from the HTTP request
through the queue into the worker and out to the AI provider:

  FastAPI request -> SQLAlchemy/Redis calls -> Celery publish
    -> Celery task -> transformation.execute -> provider HTTP call (httpx)
"""

import logging
import os
from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("content_repurpose")

_configured = False


def tracing_enabled() -> bool:
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_tracing(service_name: str, exporter: Optional[SpanExporter] = None) -> bool:
    """Install the tracer provider and library instrumentations once per process.

    `exporter` is for tests; otherwise OTLP over HTTP is used when enabled.
    """
    global _configured
    if _configured:
        return True
    if exporter is None:
        if not tracing_enabled():
            return False
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter()

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", service_name)})
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    # Covers engines created later too (the worker builds its own).
    SQLAlchemyInstrumentor().instrument(enable_commenter=False)
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()  # the AI provider SDKs use httpx
    CeleryInstrumentor().instrument()  # propagates trace context through task headers
    _configured = True
    logger.info("Tracing enabled for %s", service_name)
    return True


def instrument_app(app) -> None:
    if _configured:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Health checks are frequent and uninteresting.
        FastAPIInstrumentor.instrument_app(app, excluded_urls="api/health")


@contextmanager
def span(name: str, **attributes) -> Iterator[trace.Span]:
    """A child span with attributes; free when tracing is off."""
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current
