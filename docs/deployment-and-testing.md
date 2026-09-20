# Deployment and Testing

## Environment variables

`app/core/config.py` reads `.env` through Pydantic Settings. The tracked template is `.env.example`; replace every placeholder before deployment.

Application variables include:

```text
APP_NAME
APP_ENV
APP_DEBUG
APP_VERSION
DATABASE_URL
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT
REDIS_URL
REDIS_HOST
REDIS_PORT
REDIS_DB
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
JWT_SECRET_KEY
JWT_ALGORITHM
JWT_ACCESS_TOKEN_EXPIRE_MINUTES
JWT_REFRESH_TOKEN_EXPIRE_DAYS
MFA_ISSUER
CORS_ORIGINS
LOG_LEVEL
RATE_LIMIT_PER_MINUTE
LOGIN_RATE_LIMIT
REGISTRATION_RATE_LIMIT
REFRESH_RATE_LIMIT
MFA_RATE_LIMIT
LOGIN_RATE_LIMIT_SECONDS
REGISTRATION_RATE_LIMIT_SECONDS
REFRESH_RATE_LIMIT_SECONDS
MFA_RATE_LIMIT_SECONDS
```

Compose also uses `GRAFANA_ADMIN_PASSWORD`.

## Local Python setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Run the API locally:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker Compose

Validate configuration without starting services:

```powershell
docker compose --env-file .env.example config
```

Build and start the stack:

```powershell
docker compose --env-file .env up --build -d
docker compose --env-file .env ps -a
```

The services are `api`, `postgres`, `redis`, `celery-worker`, `celery-beat`, `prometheus`, `grafana`, and `nginx`. The API container runs `alembic upgrade head` before Uvicorn. Worker and beat wait for the healthy API, PostgreSQL, and Redis dependencies.

Expected published ports:

```text
80     Nginx
8000   API
5432   PostgreSQL
6379   Redis
9090   Prometheus
3000   Grafana
```

Stop the stack:

```powershell
docker compose --env-file .env down
```

## Database migrations

```powershell
alembic upgrade head
alembic current
alembic heads
```

The current revision is `20260920_000007`.

## Test commands

Ordinary tests use the isolated test configuration from `tests/conftest.py`:

```powershell
$env:RUN_LIVE_INTEGRATION=$null
.\.venv\Scripts\python.exe -m pytest tests -q --cov=app --cov-report=term-missing
```

Live PostgreSQL, Redis, and Celery tests require the services to be reachable and:

```powershell
$env:RUN_LIVE_INTEGRATION="1"
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

Quality and security checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m bandit -r app -ll
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m compileall -q app migrations tests
```

## CI

The workflow `.github/workflows/ci.yml` runs on Python 3.12 and includes:

- Ruff and mypy.
- Pytest with coverage.
- PostgreSQL and Redis service containers.
- Alembic migration execution.
- Celery worker ping and registered-task checks.
- Bandit, pip-audit, and Trivy.
- Docker Compose config validation and Docker image build.

## Runtime checks

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest http://127.0.0.1/api/v1/health
Invoke-WebRequest http://127.0.0.1/metrics

docker compose exec postgres pg_isready -U amrutam -d amrutam_telemedicine
docker compose exec redis redis-cli ping
docker compose exec api alembic current
docker compose exec celery-worker celery -A app.workers.celery_app inspect ping
docker compose exec celery-worker celery -A app.workers.celery_app inspect registered
```

## Load testing

The local load runner is `loadtest/load_test.py`. It uses the existing `httpx` dependency and exercises health, login, doctor discovery, availability, and booking.

```powershell
$env:LOADTEST_EMAIL = "existing-patient@example.com"
$env:LOADTEST_PASSWORD = "local-test-password"
$env:LOADTEST_DOCTOR_ID = "doctor-uuid"
$env:LOADTEST_SLOT_IDS = "slot-uuid-1,slot-uuid-2"
.\.venv\Scripts\python.exe .\loadtest\load_test.py --base-url http://127.0.0.1:8000 --concurrency 2 --duration 30
```

Booking `409` responses are reported as expected contention. Unexpected responses, transport failures, missing doctor data, and missing available slots cause a non-zero exit.
