import uuid

from fastapi import Request
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.candidate_api import reject_candidate
from app.db import (
    AuditLogRecord,
    Base,
    IdempotencyRecord,
    OpportunityDraftRecord,
    OrganizationRecord,
    UserRecord,
    set_tenant_context,
)
from app.security import Principal


def _request(key: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/candidates/draft/reject",
            "raw_path": b"/api/candidates/draft/reject",
            "query_string": b"",
            "headers": [(b"idempotency-key", key.encode("utf-8"))],
            "client": ("test", 1234),
            "server": ("test", 80),
        }
    )


def test_candidate_reject_replays_same_idempotency_key_without_duplicate_audit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        organization = OrganizationRecord(
            id=str(uuid.uuid4()),
            name="Candidate Reject Org",
            code=f"reject-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=f"manager-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Manager",
            is_active=True,
        )
        draft = OpportunityDraftRecord(
            id=str(uuid.uuid4()),
            organization_id=organization.id,
            status="pending",
            discovery={
                "project_detected": True,
                "title": "Candidate Project",
                "country": "Nigeria",
                "region": "West Africa",
                "sector": "Road",
                "stage": "Procurement",
                "owner": "Public Agency",
                "estimated_value_usd_m": None,
                "summary": "Candidate summary",
                "confidence": 0.9,
                "facts": [],
                "parties": [],
            },
            source_url="https://example.com/project",
            source_title="Project notice",
            publisher="Public Agency",
            published_at="2026-08-24",
            source_rank="A",
            raw_text="",
            duplicate_matches=[],
            is_demo=False,
        )
        session.add_all([organization, user, draft])
        session.commit()
        set_tenant_context(session, organization.id)

        principal = Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            organization_id=organization.id,
            organization_name=organization.name,
            role="manager",
        )

        first = reject_candidate(
            draft.id,
            _request("candidate-reject-stable-key"),
            db=session,
            principal=principal,
        )
        second = reject_candidate(
            draft.id,
            _request("candidate-reject-stable-key"),
            db=session,
            principal=principal,
        )

        assert first == {"id": draft.id, "status": "rejected"}
        assert second == first
        assert session.get(OpportunityDraftRecord, draft.id).status == "rejected"
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AuditLogRecord)
            .where(AuditLogRecord.action == "candidate.reject")
        ) == 1
