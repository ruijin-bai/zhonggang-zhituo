from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base, OrganizationRecord, set_tenant_context
from app.entity_management import add_manual_alias
from app.intelligence import resolve_discovery_entities
from app.intelligence_db import EntityAliasRecord, EntityRecord
from app.models import ProjectDiscovery, ProjectParty


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = OrganizationRecord(name="Entity Test", code="ENTITY", is_active=True)
    session.add(org)
    session.commit()
    set_tenant_context(session, org.id)
    return engine, session


def _discovery(*, country: str, owner: str) -> ProjectDiscovery:
    return ProjectDiscovery(
        project_detected=True,
        title=f"{country} Port Project",
        country=country,
        region="Africa",
        sector="港口工程",
        stage="Procurement",
        owner=owner,
        estimated_value_usd_m=None,
        summary="Project",
        confidence=0.85,
        facts=[],
        parties=[
            ProjectParty(
                role="owner",
                name=owner,
                country=country,
                evidence_quote=f"Owner: {owner}",
                confidence=0.95,
            )
        ],
    )


def test_exact_normalized_entity_is_reused_within_country() -> None:
    engine, session = _session()
    first = resolve_discovery_entities(
        session,
        discovery=_discovery(country="Nigeria", owner="Nigerian Ports Authority"),
        source_document_id=None,
    )
    second = resolve_discovery_entities(
        session,
        discovery=_discovery(country="Nigeria", owner="  NIGERIAN   PORTS AUTHORITY "),
        source_document_id=None,
    )
    assert first[0]["entity_id"] == second[0]["entity_id"]
    assert session.scalar(select(func.count()).select_from(EntityRecord)) == 1
    session.close()
    engine.dispose()


def test_same_entity_name_in_different_country_is_not_auto_merged() -> None:
    engine, session = _session()
    first = resolve_discovery_entities(
        session,
        discovery=_discovery(country="Nigeria", owner="Ministry of Works"),
        source_document_id=None,
    )
    second = resolve_discovery_entities(
        session,
        discovery=_discovery(country="Ghana", owner="Ministry of Works"),
        source_document_id=None,
    )
    assert first[0]["entity_id"] != second[0]["entity_id"]
    assert session.scalar(select(func.count()).select_from(EntityRecord)) == 2
    session.close()
    engine.dispose()


def test_manual_alias_cannot_make_same_country_identity_ambiguous() -> None:
    engine, session = _session()
    first = resolve_discovery_entities(
        session,
        discovery=_discovery(country="Nigeria", owner="Nigerian Ports Authority"),
        source_document_id=None,
    )[0]
    second = resolve_discovery_entities(
        session,
        discovery=_discovery(country="Nigeria", owner="Federal Ports Agency"),
        source_document_id=None,
    )[0]

    alias = add_manual_alias(
        session,
        entity_id=first["entity_id"],
        alias="NPA",
    )
    assert alias.normalized_alias == "npa"

    try:
        add_manual_alias(
            session,
            entity_id=second["entity_id"],
            alias="NPA",
        )
        assert False, "ambiguous alias should be rejected"
    except ValueError as exc:
        assert "another entity" in str(exc)

    assert session.scalar(
        select(func.count()).select_from(EntityAliasRecord).where(
            EntityAliasRecord.normalized_alias == "npa"
        )
    ) == 1
    session.close()
    engine.dispose()
