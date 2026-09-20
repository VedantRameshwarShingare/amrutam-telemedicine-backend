from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4


@dataclass(frozen=True)
class ProviderChargeResult:
    provider_payment_id: str
    succeeded: bool
    failure_code: str | None = None
    failure_message: str | None = None


class PaymentProvider:
    async def charge(
        self,
        *,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> ProviderChargeResult:
        raise NotImplementedError


class MockPaymentProvider(PaymentProvider):
    async def charge(
        self,
        *,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> ProviderChargeResult:
        if amount <= 0:
            return ProviderChargeResult(
                provider_payment_id=f"mock_{uuid4().hex}",
                succeeded=False,
                failure_code="INVALID_AMOUNT",
                failure_message="Payment amount must be positive",
            )
        if idempotency_key.lower().startswith("fail-"):
            return ProviderChargeResult(
                provider_payment_id=f"mock_{uuid4().hex}",
                succeeded=False,
                failure_code="MOCK_DECLINED",
                failure_message="Mock provider declined the payment",
            )
        return ProviderChargeResult(
            provider_payment_id=f"mock_{uuid4().hex}",
            succeeded=True,
        )
