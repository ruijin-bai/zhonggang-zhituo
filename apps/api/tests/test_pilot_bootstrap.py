from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base, MembershipRecord, OpportunityRecord
from app.pilot_bootstrap import ensure_pilot_identity


def test_pilot_bootstrap_is_idempotent_and_does_not_seed_demo_data() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    values = {
        "email": "pilot.owner@example.com",
        "display_name": "Pilot Owner",
        "organization_name": "Zhituo Pilot",
        "organization_code": "zhituo-pilot",
    }
    with Session(engine) as session:
        first_org, first_user, first_membership = ensure_pilot_identity(session, **values)
        second_org, second_user, second_membership = ensure_pilot_identity(session, **values)

        assert first_org.id == second_org.id
        assert first_user.id == second_user.id
        assert first_membership.id == second_membership.id
        assert first_membership.role == "admin"
        assert session.scalar(select(func.count()).select_from(MembershipRecord)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityRecord)) == 0


def test_pilot_bootstrap_rejects_demo_identity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        try:
            ensure_pilot_identity(
                session,
                email="admin@zhituo.local",
                display_name="Demo",
                organization_name="Pilot",
                organization_code="PILOT",
            )
        except ValueError as exc:
            assert "non-demo email" in str(exc)
        else:
            raise AssertionError("demo identity must be rejected")
