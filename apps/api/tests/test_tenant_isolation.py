from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base, OpportunityRecord, OrganizationRecord


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title=f"Project {opportunity_id}",
        country="Nigeria",
        region="West Africa",
        sector="公路工程",
        stage="规划",
        owner="Owner",
        estimated_value_usd_m=None,
        summary="test",
        score=50,
        grade="C",
        confidence=60,
        decision="CAUTION",
        breakdown={
            "strategic_fit": 10,
            "project_maturity": 5,
            "financing": 5,
            "client_quality": 5,
            "capability_fit": 10,
            "local_position": 5,
            "competition": 5,
            "risk_control": 5,
        },
        pursuit_thesis="test",
        next_actions=[],
        is_demo=False,
    )


def test_selects_are_scoped_to_session_organization() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org_a = OrganizationRecord(id="org-a", name="Org A", code="A", is_active=True)
        org_b = OrganizationRecord(id="org-b", name="Org B", code="B", is_active=True)
        session.add_all([org_a, org_b])
        session.flush()
        session.add_all([_opportunity("a-project", "org-a"), _opportunity("b-project", "org-b")])
        session.commit()

        session.info["organization_id"] = "org-a"
        rows = session.scalars(select(OpportunityRecord).order_by(OpportunityRecord.id)).all()
        assert [row.id for row in rows] == ["a-project"]
        assert session.get(OpportunityRecord, "b-project") is None


def test_cross_tenant_insert_is_blocked_when_tenant_context_exists() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            OrganizationRecord(id="org-a", name="Org A", code="A", is_active=True),
            OrganizationRecord(id="org-b", name="Org B", code="B", is_active=True),
        ])
        session.commit()
        session.info["organization_id"] = "org-a"
        session.add(_opportunity("wrong-tenant", "org-b"))
        try:
            session.flush()
        except PermissionError:
            session.rollback()
        else:
            raise AssertionError("cross-tenant insert must be rejected")
