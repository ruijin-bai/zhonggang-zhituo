import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, MembershipRecord, OrganizationRecord, UserRecord
from app.main import app
from app.security import _select_membership


PROXY_SECRET = "zhituo-production-proxy-secret-32-characters-minimum"


def _production_settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "production",
        "data_backend": "database",
        "database_url": "postgresql+psycopg://user:pass@db.internal:5432/zhituo",
        "database_rls_enabled": True,
        "cors_origins": "https://zhituo.example.com",
        "demo_mode": False,
        "allow_demo_fallback": False,
        "dev_user_email": "admin@zhituo.local",
        "auth_mode": "trusted_proxy",
        "auth_proxy_secret": PROXY_SECRET,
        "job_mode": "queue",
        "redis_url": "redis://redis.internal:6379/0",
        "document_store_backend": "s3",
        "document_store_s3_bucket": "zhituo-production-documents",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_development_header_authentication() -> None:
    with pytest.raises(ValidationError):
        _production_settings(auth_mode="development_header")


def test_production_rejects_short_proxy_secret() -> None:
    with pytest.raises(ValidationError):
        _production_settings(auth_proxy_secret="too-short")


def test_production_accepts_safe_trusted_proxy_baseline() -> None:
    settings = _production_settings()
    assert settings.auth_mode == "trusted_proxy"
    assert settings.job_mode == "queue"
    assert settings.data_backend == "database"
    assert settings.database_rls_enabled is True
    assert settings.document_store_backend == "s3"


def test_production_accepts_oidc_without_proxy_secret() -> None:
    settings = _production_settings(
        auth_mode="oidc",
        auth_proxy_secret=None,
        oidc_issuer="https://id.example.com/",
        oidc_audience="zhituo-api",
        oidc_jwks_url="https://id.example.com/.well-known/jwks.json",
    )
    assert settings.auth_mode == "oidc"


def test_production_oidc_rejects_insecure_jwks_url() -> None:
    with pytest.raises(ValidationError):
        _production_settings(
            auth_mode="oidc",
            auth_proxy_secret=None,
            oidc_issuer="https://id.example.com/",
            oidc_audience="zhituo-api",
            oidc_jwks_url="http://id.example.com/jwks.json",
        )


def test_explicit_organization_selection_uses_membership() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = UserRecord(id=str(uuid.uuid4()), email="multi@example.com", display_name="Multi", is_active=True)
        org_a = OrganizationRecord(id=str(uuid.uuid4()), name="Org A", code="ORG-A", is_active=True)
        org_b = OrganizationRecord(id=str(uuid.uuid4()), name="Org B", code="ORG-B", is_active=True)
        session.add_all([user, org_a, org_b])
        session.flush()
        session.add_all(
            [
                MembershipRecord(organization_id=org_a.id, user_id=user.id, role="viewer", is_active=True),
                MembershipRecord(organization_id=org_b.id, user_id=user.id, role="manager", is_active=True),
            ]
        )
        session.commit()

        membership, organization = _select_membership(session, user.id, "ORG-B")
        assert organization.id == org_b.id
        assert membership.role == "manager"


def test_health_response_has_security_and_trace_headers() -> None:
    client = TestClient(app)
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers.get("x-request-id")
    assert response.headers.get("x-correlation-id")


def test_application_rejects_oversized_declared_body() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/jobs/discovery/scan",
        headers={"Content-Length": "3000000"},
        content=b"{}",
    )
    assert response.status_code == 413
