import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import OpportunityRecord, OrganizationRecord


settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL RLS integration test requires PostgreSQL",
)


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title=f"RLS {opportunity_id}",
        country="Test",
        region="Test",
        sector="公路工程",
        stage="Test",
        owner="Test",
        estimated_value_usd_m=None,
        summary="RLS integration fixture",
        score=50,
        grade="C",
        confidence=60,
        decision="CAUTION",
        breakdown={
            "strategic_fit": 10,
            "project_maturity": 8,
            "financing": 6,
            "client_quality": 6,
            "capability_fit": 10,
            "local_position": 4,
            "competition": 4,
            "risk_control": 2,
        },
        pursuit_thesis="RLS integration fixture",
        next_actions=[],
        is_demo=False,
    )


def test_postgres_rls_blocks_cross_tenant_reads_for_runtime_role() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"rls-org-a-{suffix}"
    org_b = f"rls-org-b-{suffix}"
    project_a = f"rls-a-{suffix}"
    project_b = f"rls-b-{suffix}"
    role = f"zhituo_rls_{suffix}"
    password = f"RlsTest-{suffix}-Password-123!"

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine) as session:
            session.add_all(
                [
                    OrganizationRecord(id=org_a, name=f"RLS Org A {suffix}", code=f"RLS-A-{suffix}", is_active=True),
                    OrganizationRecord(id=org_b, name=f"RLS Org B {suffix}", code=f"RLS-B-{suffix}", is_active=True),
                ]
            )
            session.flush()
            session.add_all([_opportunity(project_a, org_a), _opportunity(project_b, org_b)])
            session.commit()

        with admin_engine.begin() as connection:
            # role/password are generated locally from a hex suffix, not user input.
            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\'')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(f'GRANT SELECT ON TABLE opportunities TO "{role}"')

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_a},
            )
            ids = connection.execute(
                text("SELECT id FROM opportunities WHERE id IN (:a, :b) ORDER BY id"),
                {"a": project_a, "b": project_b},
            ).scalars().all()
            assert ids == [project_a]

            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_b},
            )
            ids = connection.execute(
                text("SELECT id FROM opportunities WHERE id IN (:a, :b) ORDER BY id"),
                {"a": project_a, "b": project_b},
            ).scalars().all()
            assert ids == [project_b]
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with admin_engine.begin() as connection:
            if role_created:
                connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            connection.execute(
                text("DELETE FROM opportunities WHERE id IN (:a, :b)"),
                {"a": project_a, "b": project_b},
            )
            connection.execute(
                text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
        admin_engine.dispose()
