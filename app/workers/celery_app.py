from __future__ import annotations

from app.core.config import settings
from app.core.observability import celery_task_failures_total
from celery import Celery  # type: ignore[import-untyped]
from celery.signals import task_failure  # type: ignore[import-untyped]

# mypy: disable-error-code=import-untyped

celery_app = Celery(
    "amrutam_telemedicine",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "process-outbox-every-minute": {
            "task": "app.workers.tasks.process_outbox",
            "schedule": 60.0,
        },
        "send-appointment-reminders-hourly": {
            "task": "app.workers.tasks.send_appointment_reminders",
            "schedule": 3600.0,
        },
        "generate-daily-report": {
            "task": "app.workers.tasks.generate_daily_report",
            "schedule": 86400.0,
        },
        "refresh-analytics-cache": {
            "task": "app.workers.tasks.refresh_analytics_cache",
            "schedule": 900.0,
        },
    },
)


@task_failure.connect(weak=False)
def record_task_failure(sender=None, **_: object) -> None:
    task_name = getattr(sender, "name", None) or str(sender or "unknown")
    celery_task_failures_total.labels(task_name).inc()
