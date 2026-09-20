from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") == "1",
        reason="synchronous TestClient checks use the isolated test database",
    ),
]

def test_health_and_metrics_include_correlation_id(client):
    correlation_id = "integration-correlation-id"

    health = client.get("/health", headers={"X-Correlation-ID": correlation_id})
    metrics = client.get("/metrics", headers={"X-Correlation-ID": correlation_id})

    assert health.status_code == 200
    assert health.headers["X-Correlation-ID"] == correlation_id
    assert metrics.status_code == 200
    assert metrics.headers["X-Correlation-ID"] == correlation_id
    assert b"amrutam_http_requests_total" in metrics.content