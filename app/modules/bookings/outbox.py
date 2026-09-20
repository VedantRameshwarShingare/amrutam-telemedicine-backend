from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.logging import logger
from app.core.observability import outbox_backlog, outbox_failures_total, outbox_published_total
from app.modules.bookings.models import OutboxEvent
from app.workers.celery_app import celery_app
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def publish_pending_events(session: AsyncSession, *, limit: int = 100) -> int:
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())
    published = 0
    for event in events:
        event.attempts += 1
        try:
            celery_app.send_task(
                "app.workers.tasks.deliver_outbox_event",
                args=[str(event.id)],
                headers={"event_type": event.event_type},
            )
            event.published_at = datetime.now(UTC)
            event.last_error = None
            outbox_published_total.labels(event.event_type).inc()
            published += 1
            logger.info(
                "outbox_published", event_type=event.event_type, event_id=str(event.id)
            )
        except Exception as exc:
            event.last_error = str(exc)[:500]
            outbox_failures_total.labels(event.event_type).inc()
            logger.error(
                "outbox_publish_failed", event_type=event.event_type, event_id=str(event.id)
            )
            raise
    await session.flush()
    backlog = await session.scalar(
        select(func.count()).select_from(OutboxEvent).where(OutboxEvent.published_at.is_(None))
    )
    outbox_backlog.set(int(backlog or 0))
    await session.commit()
    return published


async def mark_event_delivered(session: AsyncSession, event_id: UUID) -> bool:
    event = await session.get(OutboxEvent, event_id)
    if event is None:
        return False
    logger.info("outbox_delivered", event_type=event.event_type, event_id=str(event.id))
    return True