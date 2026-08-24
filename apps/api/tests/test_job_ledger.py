import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, OrganizationRecord, UserRecord, clear_tenant_context, set_tenant_context
from app.job_ledger import create_job_record, get_job_record, transition_job_record
from app.security import Principal


def _principal(session: Session, *, org_code: str, email: str) -> Principal:
    org = OrganizationRecord(
        id=str(uuid.uuid4()),
        name=f"Job Org {org_code} {uuid.uuid4().hex[:6]}",
        code=f"JOB-{org_code}-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=email,
        display_name=email.split("@")[0],
        is_active=True,
    )
    session.add_all([org, user])
    session.commit()
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=org.id,
        organization_name=org.name,
        role="manager",
    )


def test_job_ledger_tracks_lifecycle_and_retry_lineage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        principal = _principal(session, org_code="A", email="manager-a@example.com")
        set_tenant_context(session, principal.organization_id)

        original_id = str(uuid.uuid4())
        original = create_job_record(
            session,
            job_id=original_id,
            principal=principal,
            job_type="strategy.generate",
            task_name="zhituo.strategy.generate",
            task_args=["opp-1", principal.organization_id],
            resource_id="opp-1",
            request_id="req-12345678",
            correlation_id="corr-12345678",
        )
        assert original.status == "queued"
        assert original.attempts == 0

        running = transition_job_record(session, original_id, status="running", increment_attempt=True)
        assert running is not None
        assert running.status == "running"
        assert running.attempts == 1
        assert running.started_at is not None

        failed = transition_job_record(session, original_id, status="failed", error_detail="provider timeout")
        assert failed is not None
        assert failed.status == "failed"
        assert failed.finished_at is not None
        assert failed.error_detail == "provider timeout"

        retry_id = str(uuid.uuid4())
        retry = create_job_record(
            session,
            job_id=retry_id,
            principal=principal,
            job_type=failed.job_type,
            task_name=failed.task_name,
            task_args=failed.task_args,
            resource_id=failed.resource_id,
            retry_of_job_id=failed.id,
        )
        assert retry.retry_of_job_id == original_id
        assert get_job_record(session, original_id).status == "failed"
        assert get_job_record(session, retry_id).status == "queued"


def test_job_ledger_is_hidden_from_other_organization() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        principal_a = _principal(session, org_code="A", email="a@example.com")
        principal_b = _principal(session, org_code="B", email="b@example.com")

        set_tenant_context(session, principal_a.organization_id)
        job_id = str(uuid.uuid4())
        create_job_record(
            session,
            job_id=job_id,
            principal=principal_a,
            job_type="opportunity.analyze",
            task_name="zhituo.opportunity.analyze",
            task_args=["opp-a", principal_a.organization_id],
        )
        assert get_job_record(session, job_id) is not None

        clear_tenant_context(session)
        set_tenant_context(session, principal_b.organization_id)
        assert get_job_record(session, job_id) is None
