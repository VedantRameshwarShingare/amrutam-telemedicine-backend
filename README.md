# Amrutam Telemedicine Backend

This repository contains the backend for the Amrutam Telemedicine System, built as a modular monolith with a production-oriented architecture that is designed to scale into service-oriented modules later.

## Overview

The application focuses on secure telemedicine operations with patient, doctor, consultation, prescription, payment, audit, and analytics flows. It uses FastAPI, PostgreSQL, Redis, Celery, Docker, and observability tooling.

## Architecture

- API layer: FastAPI with async endpoints
- Persistence: PostgreSQL with SQLAlchemy 2.0 async
- Caching / rate limiting: Redis
- Background processing: Celery with Redis broker
- Observability: Prometheus, Grafana, OpenTelemetry, structured JSON logs
- Reverse proxy: Nginx

Detailed design documents:

- [Architecture](docs/architecture.md)
- [Components](docs/components.md)
- [API reference](docs/api-reference.md)
- [Database and migrations](docs/database.md)
- [Security and authentication](docs/security-and-authentication.md)
- [Domain flows](docs/domain-flows.md)
- [Outbox, Redis, and observability](docs/outbox-redis-observability.md)
- [Deployment and testing](docs/deployment-and-testing.md)
- [ER diagram](docs/er-diagram.md)
- [Booking sequence](docs/booking-sequence.md)
- [Threat model](docs/threat-model.md)
- [Security checklist](docs/security-checklist.md)
- [Disaster recovery](docs/disaster-recovery.md)

## Tech stack

- Python 3.12
- FastAPI
- SQLAlchemy 2.0 async
- PostgreSQL
- Alembic
- Redis
- Celery
- Pydantic v2
- JWT and MFA support
- Prometheus + Grafana + OpenTelemetry
- Docker and Docker Compose

## Prerequisites

- Docker Desktop or Docker Engine
- Python 3.12
- pip
- Git

## Runtime configuration

Copy `.env.example` to `.env` and adjust the values before running the application.

## Local development

```bash
python -m venv .venv
. .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker compose --env-file .env up --build -d
```

## Database migrations

```bash
alembic upgrade head
```

Never use `Base.metadata.create_all` as a production migration mechanism. Apply reviewed Alembic revisions in deployment order.

## Testing

```bash
pytest --cov=app --cov-report=term-missing
ruff check app tests
mypy app
bandit -r app -ll
pip-audit
```

GitHub Actions runs the quality, test, security, Trivy filesystem, and Docker build jobs on pushes to `main` and pull requests.

## API docs

- Swagger UI: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json
- Health endpoint: http://localhost:8000/health

## Phase status

This repository is currently at the Phase 10 production hardening checkpoint, with documented architecture and recovery procedures, security controls, migration discipline, and automated quality, security, and Docker build workflows.
