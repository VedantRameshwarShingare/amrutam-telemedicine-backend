# Outbox, Redis, and Observability

## Outbox lifecycle

Domain services add `AuditEvent` and `OutboxEvent` records in the same SQLAlchemy unit of work as the business mutation. `OutboxEvent` contains:

- `event_type`
- `aggregate_type`
- `aggregate_id`
- `payload`
- `published_at`
- `attempts`
- `last_error`
- timestamps

`process_outbox` calls `publish_pending_events()`. The publisher selects unpublished rows with `FOR UPDATE SKIP LOCKED`, increments attempts, sends a Celery task, records `published_at`, updates the backlog gauge, and commits. Failures increment the outbox failure counter and retain the error text truncated to 500 characters.

Delivery is at-least-once. `deliver_outbox_event` receives the event ID; downstream handling must remain idempotent.

## Redis

`app/core/redis.py` creates `redis_client` from `Settings.redis_url`. Cache helpers:

- `cache_get_json()`
- `cache_set_json()`
- `cache_delete()`

Cache helpers fail open by returning `None`/`False` when Redis is unavailable. Redis is also used for rate-limit counters, booking/payment locks, refresh-token revocation keys, Celery broker traffic, and analytics/report cache entries.

## Celery

`app/workers/celery_app.py` configures JSON serialization, UTC, late acknowledgements, worker-lost rejection, task tracking, broker startup retries, and beat schedules.

Tasks use retry/backoff through `_retryable_task`. Async database work runs through a task-local event loop and disposes the shared async engine before that loop closes.

## Metrics

Prometheus metrics are defined in `app/core/observability.py` and exposed by `GET /metrics`.

HTTP:

- `amrutam_http_requests_total{method,route,status}`
- `amrutam_http_request_duration_seconds{method,route}`
- `amrutam_http_errors_total{method,route,status}`

Infrastructure:

- `amrutam_database_errors_total{operation}`
- `amrutam_celery_tasks_total{task,status}`
- `amrutam_celery_task_failures_total{task}`
- `amrutam_outbox_published_total{event_type}`
- `amrutam_outbox_failures_total{event_type}`
- `amrutam_outbox_backlog`

Labels are bounded to methods, route templates, statuses, task names, operation names, and event types. Sensitive identifiers are not metric labels.

## Tracing and logging

`app/core/telemetry.py` instruments FastAPI, SQLAlchemy, and Redis. The development environment can use the console span exporter; production does not emit spans to the console.

`app/main.py` creates or validates an `X-Correlation-ID`, binds it to structlog context, returns it in the response, and records it in request logs.

Grafana provisioning files:

- `infra/grafana/provisioning/datasources/prometheus.yml`
- `infra/grafana/provisioning/dashboards/dashboard.yml`
- `infra/grafana/dashboards/amrutam-overview.json`
