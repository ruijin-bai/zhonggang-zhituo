import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, OpportunityRecord, OrganizationRecord, set_tenant_context, utc_now
from app.entity_api import entity_read
from app.intelligence_db import EntityRecord, OpportunityEntityLinkRecord
from app.security import Principal


def test_entity_detail_includes_linked_opportunity_context() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        organization = OrganizationRecord(
            id=str(uuid.uuid4()),
            name="Entity API Org",
            code=f"entity-api-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(organization)
        session.flush()

        opportunity = OpportunityRecord(
            id=f"opp-{uuid.uuid4().hex[:8]}",
            organization_id=organization.id,
            title="Lagos Port Access Upgrade",
            country="Nigeria",
            region="West Africa",
            sector="Transport",
            stage="Procurement",
            owner="Ports Authority",
            estimated_value_usd_m=250,
            summary="Port access project",
            score=78,
            grade="B",
            confidence=80,
            decision="WATCH",
            breakdown={
                "strategic_fit": 16,
                "project_maturity": 11,
                "financing": 11,
                "client_quality": 8,
                "capability_fit": 13,
                "local_position": 7,
                "competition": 8,
                "risk_control": 4,
            },
            pursuit_thesis="Track procurement and financing milestones.",
            next_actions=[],
            is_demo=False,
        )
        entity = EntityRecord(
            id=str(uuid.uuid4()),
            organization_id=organization.id,
            entity_type="organization",
            canonical_name="Nigerian Ports Authority",
            normalized_name="nigerian ports authority",
            country="Nigeria",
            country_key="nigeria",
            identity_key=uuid.uuid4().hex,
            status="active",
            entity_metadata={},
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add_all([opportunity, entity])
        session.flush()
        session.add(
            OpportunityEntityLinkRecord(
                organization_id=organization.id,
                opportunity_id=opportunity.id,
                entity_id=entity.id,
                role="owner",
                confidence=0.96,
                source_count=2,
                first_seen_at=utc_now(),
                last_seen_at=utc_now(),
            )
        )
        session.commit()

        organization_id = organization.id
        opportunity_id = opportunity.id
        entity_id = entity.id
        set_tenant_context(session, organization_id)
        principal = Principal(
            user_id="test-user",
            email="viewer@example.com",
            display_name="Viewer",
            organization_id=organization_id,
            organization_name="Entity API Org",
            role="viewer",
        )

        result = entity_read(entity_id, db=session, principal=principal)
        assert result["canonical_name"] == "Nigerian Ports Authority"
        assert result["opportunities"] == [
            {
                "opportunity_id": opportunity_id,
                "role": "owner",
                "confidence": 0.96,
                "source_count": 2,
                "last_seen_at": result["opportunities"][0]["last_seen_at"],
                "title": "Lagos Port Access Upgrade",
                "country": "Nigeria",
                "sector": "Transport",
                "stage": "Procurement",
            }
        ]
