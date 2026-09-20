# Threat Model

## Assets

- Patient identity, contact details, clinical notes, prescriptions, and appointment history.
- Payment state and provider identifiers.
- JWT signing key, database credentials, Redis/Celery credentials, and operational dashboards.

## Trust boundaries

1. Untrusted internet client to Nginx/API.
2. API process to PostgreSQL and Redis.
3. Celery broker to workers.
4. Operators to Grafana, Prometheus, and logs.
5. Payment provider boundary outside the database transaction.

## Main threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| Credential theft | Argon2 password hashing, JWT expiry, MFA, secret environment variables | Key rotation and external secret manager remain operational responsibilities |
| Broken object authorization | Role dependencies and ownership checks in services | New endpoints require an authorization test before release |
| Replay/double booking/payment | Idempotency constraints, row locks, Redis locks, provider idempotency keys | Redis outage reduces coordination; database constraints remain authoritative |
| PHI leakage in logs | Structured logging redaction and no payload logging | Third-party infrastructure logs must be governed separately |
| SQL injection | SQLAlchemy expressions and bound parameters | Raw SQL additions require review |
| Outbox duplication | At-least-once delivery and consumer idempotency by event ID | Delivery is not exactly once |
| DoS | Redis rate limits, request body limit at Nginx, bounded pagination | Global WAF/rate limiting is still recommended |
| Supply-chain compromise | pip-audit, Bandit, Trivy, pinned CI checks | Dependency updates require regular review |

## Out of scope

Network segmentation, cloud IAM, managed secret storage, provider-specific webhook signature verification, and formal HIPAA/SOC 2 controls require deployment-specific design.