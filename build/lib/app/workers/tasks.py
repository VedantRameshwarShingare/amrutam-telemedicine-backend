from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.database import AsyncSessionLocal, engine
from app.core.observability import celery_tasks_total
from app.core.redis import cache_set_json
from app.modules.analytics.service import AnalyticsService
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.bookings.outbox import mark_event_delivered, publish_pending_events
from app.modules.doctors.models import AvailabilitySlot
from app.modules.users.models import User
from celery import shared_task  # type: ignore[import-untyped]
from sqlalchemy import select


def _retryable_task(func):
    return shared_task(
        bind=True,
        autoretry_for=(Exception,),
        retry_backoff=True,
        retry_backoff_max=600,
        retry_jitter=True,
        max_retries=5,
    )(func)


async def _run_with_disposed_engine[ResultT](
    coroutine: Coroutine[Any, Any, ResultT],
) -> ResultT:
    try:
        return await coroutine
    finally:
        await engine.dispose()


def _run_async[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(_run_with_disposed_engine(coroutine))


@_retryable_task
def sample_background_task(self, message: str) -> str:
    return f"processed: {message}"


@_retryable_task
def send_notification(self, recipient: str, subject: str, body: str) -> dict[str, str]:
    if not recipient:
        raise ValueError("Notification recipient is required")
    return {"recipient": recipient, "subject": subject, "body": body, "status": "queued"}


async def _find_reminders() -> list[dict[str, str]]:
    now = datetime.now(UTC)
    start = now + timedelta(hours=23)
    end = now + timedelta(hours=25)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Booking, AvailabilitySlot, User)
            .join(AvailabilitySlot, AvailabilitySlot.id == Booking.slot_id)
            .join(User, User.id == Booking.patient_id)
            .where(
                Booking.status == BookingStatus.CONFIRMED,
                AvailabilitySlot.start_time >= start,
                AvailabilitySlot.start_time < end,
            )
        )
        return [
            {
                "recipient": user.email,
                "booking_id": str(booking.id),
                "start_time": slot.start_time.isoformat(),
            }
            for booking, slot, user in result.all()
        ]


@_retryable_task
def send_appointment_reminders(self) -> dict[str, int]:
    reminders = _run_async(_find_reminders())
    for reminder in reminders:
        send_notification.delay(
            reminder["recipient"],
            "Upcoming telemedicine appointment",
            f"Your appointment starts at {reminder['start_time']}.",
        )
    return {"scheduled": len(reminders)}


@_retryable_task
def generate_daily_report(self, report_date: str | None = None) -> dict[str, Any]:
    date_value = report_date or datetime.now(UTC).date().isoformat()

    async def build() -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            report = await AnalyticsService(session).summary(use_cache=False)
        report["report_date"] = date_value
        await cache_set_json(f"reports:daily:{date_value}", report, ttl_seconds=172800)
        return report

    return _run_async(build())


@_retryable_task
def refresh_analytics_cache(self) -> dict[str, Any]:
    async def refresh() -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            return await AnalyticsService(session).summary(use_cache=False)

    return _run_async(refresh())


@_retryable_task
def process_outbox(self) -> dict[str, int]:
    async def publish() -> int:
        async with AsyncSessionLocal() as session:
            return await publish_pending_events(session)

    published = _run_async(publish())
    celery_tasks_total.labels("process_outbox", "success").inc()
    return {"published": published}


@_retryable_task
def deliver_outbox_event(self, event_id: str) -> dict[str, str]:
    async def deliver() -> bool:
        from uuid import UUID

        async with AsyncSessionLocal() as session:
            return await mark_event_delivered(session, UUID(event_id))

    delivered = _run_async(deliver())
    celery_tasks_total.labels("deliver_outbox_event", "success").inc()
    return {"event_id": event_id, "status": "delivered" if delivered else "missing"}
