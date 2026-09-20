# Database and Migrations

## Connection and sessions

`app/core/database.py` creates:

- `engine`: async SQLAlchemy engine from `Settings.database_url`.
- `AsyncSessionLocal`: async session factory with `expire_on_commit=False`.
- `get_db()`: FastAPI dependency yielding an `AsyncSession`.

Production containers run `alembic upgrade head` before starting Uvicorn. Local test fixtures may use SQLite; production is validated to require PostgreSQL.

## Declarative base

`app/core/base.py` defines `Base`, the SQLAlchemy `DeclarativeBase` used by all models.

## Tables

| Model | Table | Main purpose |
| --- | --- | --- |
| `User` | `users` | Identity, role, password hash, MFA state |
| `RefreshToken` | `refresh_tokens` | Persisted refresh-token JTIs and rotation state |
| `Doctor` | `doctors` | Doctor profile and consultation fee |
| `AvailabilitySlot` | `availability_slots` | Doctor time slots and slot status |
| `Booking` | `bookings` | Patient reservation of a slot |
| `Consultation` | `consultations` | Consultation lifecycle and clinical notes |
| `Prescription` | `prescriptions` | Serialized medication list and instructions |
| `Payment` | `payments` | Payment amount, provider, status, and idempotency |
| `AuditEvent` | `audit_events` | Actor/entity audit records |
| `OutboxEvent` | `outbox_events` | Transactionally-created background events |

## Integrity controls

Important uniqueness constraints include:

- `users.email`, `users.phone`
- `doctors.user_id`, `doctors.license_number`
- `bookings.slot_id`
- `bookings(patient_id, idempotency_key)`
- `consultations.booking_id`
- `consultations(patient_id, idempotency_key)`
- `prescriptions(consultation_id, idempotency_key)`
- `payments.booking_id`
- `payments(patient_id, idempotency_key)`
- `payments.provider_payment_id`
- `refresh_tokens.token_jti`

Availability slots have the check constraint `start_time < end_time`. Query indexes cover common patient/doctor/status/date access patterns.

## Migration chain

Configuration:

```text
alembic.ini
migrations/env.py
migrations/script.py.mako
```

Revisions:

```text
20260919_000001_create_users_table.py
20260919_000002_create_doctors_and_availability.py
20260920_000003_create_bookings_events.py
20260920_000004_create_consultations_prescriptions.py
20260920_000005_create_payments.py
20260920_000006_create_audit_outbox.py
20260920_000007_add_outbox_attempts.py
```

Current head:

```text
20260920_000007
```

Revision `20260920_000006_create_audit_outbox.py` is a compatibility/no-op revision because the audit and outbox tables were already created in revision `20260920_000003_create_bookings_events.py`.

## Commands

```powershell
alembic upgrade head
alembic current
alembic heads
```

Do not use `Base.metadata.create_all()` for production schema management. The application only uses it for non-production startup/test behavior.
