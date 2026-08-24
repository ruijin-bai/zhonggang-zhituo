from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, OpportunityDraftRecord, OrganizationRecord, set_tenant_context
from app.models import ProjectDiscovery
from app.project_matching import pending_draft_duplicate


def _project(
    *,
    title: str,
    country: str,
    sector: str = "公路工程",
    owner: str = "Ministry of Works",
) -> ProjectDiscovery:
    return ProjectDiscovery(
        project_detected=True,
        title=title,
        country=country,
        region="West Africa",
        sector=sector,
        stage="Procurement",
        owner=owner,
        estimated_value_usd_m=None,
        summary="Project opportunity",
        confidence=0.85,
        facts=[],
    )


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    organization = OrganizationRecord(name="Matching Test", code="MATCH", is_active=True)
    session.add(organization)
    session.commit()
    set_tenant_context(session, organization.id)
    return engine, session


def _add_pending(session: Session, discovery: ProjectDiscovery) -> OpportunityDraftRecord:
    row = OpportunityDraftRecord(
        id="draft-existing",
        status="pending",
        discovery=discovery.model_dump(mode="json"),
        source_url="https://example.com/a",
        source_title=discovery.title,
        publisher="Authority",
        published_at="待核实",
        source_rank="B",
        raw_text="source text",
        duplicate_matches=[],
        is_demo=False,
    )
    session.add(row)
    session.commit()
    return row


def test_pending_candidate_exact_title_different_country_is_not_auto_duplicate() -> None:
    engine, session = _session()
    _add_pending(
        session,
        _project(title="National Highway Project", country="Nigeria"),
    )
    incoming = _project(title="National Highway Project", country="Ghana")
    assert pending_draft_duplicate(incoming, session, threshold=0.88) is None
    session.close()
    engine.dispose()


def test_pending_candidate_exact_title_different_sector_is_not_auto_duplicate() -> None:
    engine, session = _session()
    _add_pending(
        session,
        _project(
            title="Lagos Infrastructure Project",
            country="Nigeria",
            sector="公路工程",
        ),
    )
    incoming = _project(
        title="Lagos Infrastructure Project",
        country="Nigeria",
        sector="港口工程",
    )
    assert pending_draft_duplicate(incoming, session, threshold=0.88) is None
    session.close()
    engine.dispose()


def test_pending_candidate_same_identity_is_auto_duplicate() -> None:
    engine, session = _session()
    existing = _add_pending(
        session,
        _project(title="Lagos Port Access Road", country="Nigeria"),
    )
    incoming = _project(title="Lagos Port Access Road", country="Nigeria")
    match = pending_draft_duplicate(incoming, session, threshold=0.88)
    assert match is not None
    assert match[0] == existing.id
    assert match[1] >= 0.88
    session.close()
    engine.dispose()
