from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "amrutam_http_requests_total",
    "Total HTTP requests handled by the API",
    ("method", "route", "status"),
)
http_request_duration_seconds = Histogram(
    "amrutam_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
)
outbox_published_total = Counter(
    "amrutam_outbox_published_total",
    "Outbox events handed to the broker",
    ("event_type",),
)
outbox_failures_total = Counter(
    "amrutam_outbox_failures_total",
    "Outbox processing failures",
    ("event_type",),
)
celery_tasks_total = Counter(
    "amrutam_celery_tasks_total",
    "Celery task executions",
    ("task", "status"),
)
http_errors_total = Counter(
    "amrutam_http_errors_total",
    "Total HTTP responses with client or server errors",
    ("method", "route", "status"),
)
database_errors_total = Counter(
    "amrutam_database_errors_total",
    "Total database operation errors",
    ("operation",),
)
celery_task_failures_total = Counter(
    "amrutam_celery_task_failures_total",
    "Total Celery task failures",
    ("task",),
)
outbox_backlog = Gauge(
    "amrutam_outbox_backlog",
    "Number of unpublished outbox events",
)