# Disaster Recovery

## Recovery objectives

The service should define deployment-specific targets before production. A practical starting point is an RPO of 15 minutes for PostgreSQL and an RTO of 60 minutes for API recovery. Redis is treated as recoverable cache/broker state; durable business state remains in PostgreSQL and the outbox.

## Backup policy

- Take encrypted PostgreSQL backups daily plus continuous/WAL-based recovery where supported.
- Retain daily backups for 30 days and test restore access separately from production credentials.
- Do not treat Redis snapshots as the source of truth for bookings, payments, audit, or outbox events.
- Store backup metadata, checksums, and restore logs in a separate protected location.

## Recovery runbook

1. Declare the incident and freeze deployments.
2. Establish the last known-good PostgreSQL backup and restore it into an isolated environment.
3. Validate migration compatibility with `alembic current` and `alembic upgrade head`.
4. Start PostgreSQL, Redis, API, workers, and beat in dependency order.
5. Verify `/health`, `/metrics`, authentication, booking idempotency, and payment state recovery.
6. Replay unpublished outbox rows; consumers must deduplicate by event ID.
7. Compare audit/outbox counts and critical business counters with the incident timeline.
8. Switch traffic back only after smoke tests and data-owner approval.

## Exercises

- Perform a quarterly restore test.
- Perform a quarterly Redis-loss exercise and confirm API degradation is fail-open where intended.
- Test worker restart during outbox dispatch and verify retries do not create duplicate business effects.
- Record RPO/RTO results and update this runbook after every exercise.