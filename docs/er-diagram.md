# Entity Relationship Diagram

The following diagram shows the core ownership and audit relationships. Audit and outbox aggregates are polymorphic by `entity_type`/`aggregate_type`, so they do not use database foreign keys to every domain table.

```mermaid
erDiagram
    USERS ||--o| DOCTORS : owns
    USERS ||--o{ BOOKINGS : creates
    DOCTORS ||--o{ AVAILABILITY_SLOTS : publishes
    AVAILABILITY_SLOTS ||--o| BOOKINGS : reserves
    BOOKINGS ||--o| PAYMENTS : has
    BOOKINGS ||--o| CONSULTATIONS : starts
    CONSULTATIONS ||--o{ PRESCRIPTIONS : produces
    USERS ||--o{ REFRESH_TOKENS : receives
    USERS ||--o{ AUDIT_EVENTS : acts

    USERS {
        uuid id PK
        string email UK
        string phone UK
        enum role
        boolean is_active
    }
    DOCTORS {
        uuid id PK
        uuid user_id FK
        string license_number UK
        decimal consultation_fee
    }
    AVAILABILITY_SLOTS {
        uuid id PK
        uuid doctor_id FK
        datetime start_time
        datetime end_time
        enum status
    }
    BOOKINGS {
        uuid id PK
        uuid slot_id FK
        uuid patient_id FK
        enum status
        string idempotency_key
    }
    PAYMENTS {
        uuid id PK
        uuid booking_id FK
        decimal amount
        enum status
        string idempotency_key
    }
    CONSULTATIONS {
        uuid id PK
        uuid booking_id FK
        enum status
    }
    PRESCRIPTIONS {
        uuid id PK
        uuid consultation_id FK
        text medications
    }
    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_jti UK
        datetime revoked_at
    }
    AUDIT_EVENTS {
        uuid id PK
        uuid actor_user_id FK
        string event_type
        uuid entity_id
    }
    OUTBOX_EVENTS {
        uuid id PK
        string event_type
        uuid aggregate_id
        datetime published_at
        integer attempts
    }
```