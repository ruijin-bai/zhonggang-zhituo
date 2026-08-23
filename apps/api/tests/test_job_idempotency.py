from app import job_registry
from app.security import Principal


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def eval(self, script, count, key, expected):
        if self.values.get(key) == expected:
            del self.values[key]
            return 1
        return 0


def _principal(org: str) -> Principal:
    return Principal(
        user_id=f"user-{org}",
        email=f"{org}@example.com",
        display_name=org,
        organization_id=org,
        organization_name=org,
        role="analyst",
    )


def test_same_idempotency_key_replays_same_job_within_org(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(job_registry, "redis_client", fake)
    principal = _principal("org-a")

    first, replayed_first = job_registry.reserve_job_id(
        principal=principal,
        job_type="source.ingest",
        idempotency_key="request-00000001",
    )
    second, replayed_second = job_registry.reserve_job_id(
        principal=principal,
        job_type="source.ingest",
        idempotency_key="request-00000001",
    )

    assert replayed_first is False
    assert replayed_second is True
    assert first == second


def test_idempotency_key_is_scoped_by_organization(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(job_registry, "redis_client", fake)

    job_a, _ = job_registry.reserve_job_id(
        principal=_principal("org-a"),
        job_type="source.ingest",
        idempotency_key="request-00000001",
    )
    job_b, _ = job_registry.reserve_job_id(
        principal=_principal("org-b"),
        job_type="source.ingest",
        idempotency_key="request-00000001",
    )

    assert job_a != job_b


def test_invalid_idempotency_key_is_rejected() -> None:
    try:
        job_registry.validate_idempotency_key("short")
    except ValueError as exc:
        assert "8 to 200" in str(exc)
    else:
        raise AssertionError("short idempotency key must be rejected")
