# Production Security Checklist

## Before deployment

- [ ] Set `APP_ENV=production` and `APP_DEBUG=false`.
- [ ] Use PostgreSQL; do not use the SQLite fallback.
- [ ] Replace database, Grafana, Redis, and JWT secrets with secret-manager values.
- [ ] Restrict `CORS_ORIGINS` to known HTTPS origins; never use `*`.
- [ ] Keep PostgreSQL, Redis, Celery, Prometheus, and Grafana on private networks.
- [ ] Terminate TLS at the ingress/load balancer and forward the correlation ID.
- [ ] Apply `alembic upgrade head` during a controlled deployment.

## Application review

- [ ] Every new resource endpoint has ownership or role authorization.
- [ ] Every mutating request has validation and an idempotency strategy where retries are possible.
- [ ] Healthcare/auth/payment data is absent from logs, metrics labels, and traces.
- [ ] External calls never run inside a database transaction.
- [ ] Outbox consumers are idempotent and have retry/dead-letter monitoring.
- [ ] Pagination limits are bounded and list queries are reviewed for N+1 behavior.

## Release gates

- [ ] `pytest --cov=app --cov-report=term-missing`
- [ ] `ruff check app tests`
- [ ] `mypy app`
- [ ] `bandit -r app -ll`
- [ ] `pip-audit`
- [ ] `trivy fs --severity HIGH,CRITICAL .`
- [ ] Docker image build and vulnerability scan pass.
- [ ] Restore test completed for the current backup set.