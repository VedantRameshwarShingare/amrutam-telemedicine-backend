# Booking Sequence

```mermaid
sequenceDiagram
    actor Patient
    participant API as FastAPI
    participant Redis
    participant DB as PostgreSQL
    participant Worker as Celery Worker

    Patient->>API: POST /api/v1/bookings + idempotency key
    API->>Redis: Acquire slot lock
    API->>DB: Begin transaction and lock slot
    DB-->>API: Available slot
    API->>DB: Insert booking, audit event, outbox event
    API->>DB: Commit transaction
    API->>Redis: Release slot lock
    API-->>Patient: 201 booking response
    API->>Worker: Outbox dispatcher enqueues event
    Worker->>DB: Process downstream notification/event

    alt Duplicate request
        Patient->>API: Repeat same idempotency key
        API->>DB: Read existing booking
        API-->>Patient: Original booking response
    else Concurrent slot claim
        API->>DB: Row lock or unique constraint rejects second claim
        API-->>Patient: 409 conflict
    end
```

Payment provider calls follow a separate rule: payment state is committed as `PROCESSING`, the provider is called with no open database transaction, and the final state plus audit/outbox event is committed afterward.