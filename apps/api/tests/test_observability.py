from fastapi.testclient import TestClient

from app.main import app
from app.observability import _safe_external_id


def test_external_trace_id_validation() -> None:
    assert _safe_external_id("request-12345678") == "request-12345678"
    assert _safe_external_id("bad value with spaces") is None
    assert _safe_external_id("x") is None


def test_liveness_returns_trace_headers() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/health/live",
        headers={
            "X-Request-ID": "request-12345678",
            "X-Correlation-ID": "correlation-12345678",
        },
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-12345678"
    assert response.headers["X-Correlation-ID"] == "correlation-12345678"
