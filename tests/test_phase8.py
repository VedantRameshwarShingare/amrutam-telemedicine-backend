from __future__ import annotations

from uuid import uuid4

import pytest
from app.core.logging import redact_sensitive
from app.core.observability import outbox_published_total
from app.modules.bookings import outbox as outbox_module
from app.modules.bookings.models import OutboxEvent
from app.workers.celery_app import celery_app


def test_sensitive_log_fields_are_removed():
    event = {
        "event": "request",
        "correlation_id": "corr-1",
        "email": "patient@example.com",
        "clinical_notes": "private",
        "authorization": "Bearer secret",
        "status_code": 200,
    }

    redacted = redact_sensitive(None, "", event)

    assert redacted == {
        "event": "request",
        "correlation_id": "corr-1",
        "status_code": 200,
    }


@pytest.mark.asyncio
async def test_outbox_publisher_enqueues_and_marks_event(monkeypatch):
    event = OutboxEvent(
        id=uuid4(),
        event_type="booking.created",
        aggregate_type="booking",
        aggregate_id=uuid4(),
        payload="sensitive payload is never logged",
        attempts=0,
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [event]

    class Session:
        async def execute(self, statement):
            return Result()

        async def flush(self):
            return None

        async def scalar(self, statement):
            return 0

        async def commit(self):
            return None

    sent: list[tuple[str, list[str]]] = []

    def send_task(name: str, *, args: list[str], headers: dict[str, str]):
        sent.append((name, args))

    monkeypatch.setattr(outbox_module.celery_app, "send_task", send_task)
    before = outbox_published_total.labels("booking.created")._value.get()

    published = await outbox_module.publish_pending_events(Session())

    assert published == 1
    assert event.published_at is not None
    assert event.attempts == 1
    assert sent == [("app.workers.tasks.deliver_outbox_event", [str(event.id)])]
    assert outbox_published_total.labels("booking.created")._value.get() == before + 1


def test_celery_has_outbox_schedule_and_late_acknowledgement():
    assert "process-outbox-every-minute" in celery_app.conf.beat_schedule
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True