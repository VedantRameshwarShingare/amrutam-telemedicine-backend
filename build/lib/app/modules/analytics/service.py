from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.redis import cache_get_json, cache_set_json
from app.modules.bookings.models import Booking
from app.modules.consultations.models import Consultation
from app.modules.payments.models import Payment, PaymentStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsService:
    cache_key = "analytics:summary"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self, *, use_cache: bool = True) -> dict[str, Any]:
        if use_cache:
            cached = await cache_get_json(self.cache_key)
            if isinstance(cached, dict):
                return cached

        since = datetime.now(UTC) - timedelta(days=30)
        bookings = await self._count(Booking, Booking.created_at >= since)
        consultations = await self._count(Consultation, Consultation.created_at >= since)
        successful_payments = await self._count(
            Payment,
            Payment.created_at >= since,
            Payment.status == PaymentStatus.SUCCEEDED,
        )
        result = {
            "window_days": 30,
            "bookings": bookings,
            "consultations": consultations,
            "successful_payments": successful_payments,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        await cache_set_json(self.cache_key, result, ttl_seconds=900)
        return result

    async def _count(self, model: type[Any], *conditions: Any) -> int:
        value = await self.session.scalar(
            select(func.count()).select_from(model).where(*conditions)
        )
        return int(value or 0)