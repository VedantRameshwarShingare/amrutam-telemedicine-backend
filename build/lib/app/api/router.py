from __future__ import annotations

from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.bookings.router import router as bookings_router
from app.modules.consultations.router import router as consultations_router
from app.modules.doctors.router import router as doctors_router
from app.modules.payments.router import router as payments_router
from app.modules.prescriptions.router import router as prescriptions_router
from app.modules.users.router import router as users_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(analytics_router)
api_router.include_router(bookings_router)
api_router.include_router(consultations_router)
api_router.include_router(doctors_router)
api_router.include_router(prescriptions_router)
api_router.include_router(payments_router)
api_router.include_router(users_router)


@api_router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "telemedicine-api"}
