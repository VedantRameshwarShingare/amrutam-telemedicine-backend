from __future__ import annotations

from app.core.config import settings
from app.core.observability import database_errors_total
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from sqlalchemy import event

resource = Resource.create({"service.name": "amrutam-telemedicine-api"})
provider = TracerProvider(resource=resource)
if settings.app_env.lower() not in {"prod", "production"}:
	provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("amrutam.telemedicine")


def instrument_application(app: object, engine: object) -> None:
	FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
	sync_engine = engine.sync_engine  # type: ignore[attr-defined]
	SQLAlchemyInstrumentor().instrument(engine=sync_engine)
	if not event.contains(sync_engine, "handle_error", _record_database_error):
		event.listen(sync_engine, "handle_error", _record_database_error)
	RedisInstrumentor().instrument()


def _record_database_error(exception_context: object) -> None:
	database_errors_total.labels("sql").inc()
