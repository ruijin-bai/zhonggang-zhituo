import uuid
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import OrganizationRecord, utc_now
from app.intelligence_db import EntityRecord


settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL RLS integration test requires PostgreSQL",
)


INTELLIGENCE_TABLES = (
    "source_document_insights",
    "candidate_source_documents",
    "entities",
    "entity_aliases",
    "source_entity_mentions",
    "opportunity_entity_links",
    "opportunity_source_documents",
)


def _entity(*, entity_id: str, organization_id: str, name: str, country: str) -> EntityRecord:
    normalized = " ".join(name.casefold().split())
    country_key = country.casefold()
    return EntityRecord(
        id=entity_id,
        organization_id=organization_id,
        entity_type="organization",
        canonical_name=name,
        normalized_name=normalized,
        country=country,
        country_key=country_key,
        identity_key=sha256(f"organization|{normalized}|{country_key}".encode()).hexdigest(),
        status="active",
        entity_metadata={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def test_postgres_intelligence_tables_enable_rls_and_block_cross_tenant_entity_access() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"intel-rls-org-a-{suffix}"
    org_b = f"intel-rls-org-b-{suffix}"
    entity_a_id = f"entity-a-{suffix}"
    entity_b_id = f"entity-b-{suffix}"
    role = f"zhituo_intel_rls_{suffix}"
    password = f"IntelligenceRls-{suffix}-Password-123!"

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine) as session:
            session.add_all(
                [
                    OrganizationRecord(
                        id=org_a,
                        name=f"Intelligence RLS A {suffix}",
                        code=f"INT-A-{suffix}",
                        is_active=True,
                    ),
                    OrganizationRecord(
                        id=org_b,
                        name=f"Intelligence RLS B {suffix}",
                        code=f"INT-B-{suffix}",
                        is_active=True,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    _entity(
                        entity_id=entity_a_id,
                        organization_id=org_a,
                        name="Entity A",
                        country="Nigeria",
                    ),
                    _entity(
                        entity_id=entity_b_id,
                        organization_id=org_b,
                        name="Entity B",
                        country="Ghana",
                    ),
                ]
            )
            session.commit()

        with admin_engine.begin() as connection:
            rls_rows = connection.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity
                    FROM pg_class c
                    WHERE c.relname = ANY(:tables)
                    """
                ),
                {"tables": list(INTELLIGENCE_TABLES)},
            ).all()
            assert {row[0] for row in rls_rows} == set(INTELLIGENCE_TABLES)
            assert all(row[1] is True for row in rls_rows)
            policy_rows = connection.execute(
                text(
                    """
                    SELECT tablename, policyname
                    FROM pg_policies
                    WHERE tablename = ANY(:tables)
                    """
                ),
                {"tables": list(INTELLIGENCE_TABLES)},
            ).all()
            assert {row[0] for row in policy_rows} == set(INTELLIGENCE_TABLES)
            assert all(row[1] == "zhituo_tenant_isolation" for row in policy_rows)

            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\'')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(f'GRANT SELECT, INSERT ON TABLE entities TO "{role}"')

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_a},
            )
            visible = connection.execute(
                text("SELECT id FROM entities WHERE id IN (:a, :b) ORDER BY id"),
                {"a": entity_a_id, "b": entity_b_id},
            ).scalars().all()
            assert visible == [entity_a_id]

            with pytest.raises(DBAPIError, match="row-level security"):
                connection.execute(
                    text(
                        """
                        INSERT INTO entities (
                            id, organization_id, entity_type, canonical_name, normalized_name,
                            country, country_key, identity_key, status, entity_metadata,
                            created_at, updated_at
                        ) VALUES (
                            :id, :org, 'organization', 'Forbidden', 'forbidden',
                            'Ghana', 'ghana', :identity_key, 'active', CAST('{}' AS JSON),
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": f"forbidden-{suffix}",
                        "org": org_b,
                        "identity_key": sha256(f"forbidden-{suffix}".encode()).hexdigest(),
                    },
                )
            connection.rollback()
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with admin_engine.begin() as connection:
            if role_created:
                connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            connection.execute(
                text("DELETE FROM entities WHERE id IN (:a, :b)"),
                {"a": entity_a_id, "b": entity_b_id},
            )
            connection.execute(
                text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
        admin_engine.dispose()
