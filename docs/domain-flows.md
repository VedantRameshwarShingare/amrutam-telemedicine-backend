# Domain Flows

## Consultation flow

1. A confirmed booking is required.
2. A patient or the assigned doctor creates the consultation with an idempotency key.
3. The booking row is selected for update.
4. A `Consultation` is created with status `SCHEDULED`.
5. A `consultation.created` audit and outbox event is added in the same database unit of work.
6. The assigned doctor or admin may transition status.
7. Valid transitions are:
   - `SCHEDULED -> IN_PROGRESS`
   - `SCHEDULED -> CANCELLED`
   - `IN_PROGRESS -> COMPLETED`
   - `IN_PROGRESS -> CANCELLED`

The patient and assigned doctor can read a consultation; admin can also read it.

## Prescription flow

1. A consultation must exist.
2. The assigned doctor or admin creates the prescription.
3. The consultation must be `IN_PROGRESS` or `COMPLETED`.
4. Medication items are validated by `MedicationItem` and serialized into the `medications` text column.
5. A `prescription.created` audit and outbox event is added.
6. The patient, assigned doctor, or admin can read the prescription.

## Payment flow

1. The patient submits a confirmed booking and idempotency key.
2. The booking is selected for update and only one payment is allowed by `uq_payments_booking_id`.
3. A `Payment` is persisted as `PROCESSING` and the database transaction is committed.
4. `PaymentProvider.charge()` is called after the database transaction has ended.
5. The payment is finalized as `SUCCEEDED` or `FAILED`.
6. The final state creates a payment audit/outbox event.
7. The provider idempotency key is the request idempotency key.

`MockPaymentProvider` supports positive successful charges, invalid-amount failures, and deterministic mock declines for keys starting with `fail-`.

## Idempotency

Supported request keys are stored in database uniqueness constraints and checked before creation:

- Booking: `(patient_id, idempotency_key)` bound to the original `slot_id`.
- Consultation: `(patient_id, idempotency_key)` bound to the original `booking_id`.
- Prescription: `(consultation_id, idempotency_key)`.
- Payment: `(patient_id, idempotency_key)` bound to the original `booking_id`.

A replay for the same resource returns the existing resource. Reusing a key for a different resource is rejected with a conflict.

## Booking concurrency

`BookingService.create_booking()` combines:

- Redis slot lock with a random token and compare-and-delete release.
- PostgreSQL `SELECT ... FOR UPDATE` on the availability slot.
- Slot status transition from `AVAILABLE` to `BOOKED`.
- Unique `bookings.slot_id` constraint.
- A transaction containing the booking, audit event, and outbox event.

The database constraint is authoritative if Redis is unavailable.
