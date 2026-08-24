from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import utc_now
from .intelligence import normalize_entity_name, resolve_discovery_entities
from .intelligence_db import EntityAliasRecord, EntityRecord, OpportunityEntityLinkRecord
from .models import ProjectDiscovery


def enforce_reviewed_owner(
    session: Session,
    *,
    opportunity_id: str,
    discovery: ProjectDiscovery,
    source_count: int,
) -> OpportunityEntityLinkRecord | None:
    """Make the human-reviewed Opportunity.owner authoritative in the entity layer.

    Source mentions remain immutable evidence. The opportunity-level owner relation, however,
    reflects the manager's reviewed headline field, so a corrected owner does not leave the
    formal opportunity linked to a stale machine-extracted owner.
    """

    owner_only = discovery.model_copy(update={"parties": []})
    resolved = resolve_discovery_entities(
        session,
        discovery=owner_only,
        source_document_id=None,
    )
    owner = next((item for item in resolved if item["role"] == "owner"), None)
    if owner is None:
        return None

    session.execute(
        delete(OpportunityEntityLinkRecord).where(
            OpportunityEntityLinkRecord.opportunity_id == opportunity_id,
            OpportunityEntityLinkRecord.role == "owner",
            OpportunityEntityLinkRecord.entity_id != owner["entity_id"],
        )
    )
    row = session.scalar(
        select(OpportunityEntityLinkRecord).where(
            OpportunityEntityLinkRecord.opportunity_id == opportunity_id,
            OpportunityEntityLinkRecord.entity_id == owner["entity_id"],
            OpportunityEntityLinkRecord.role == "owner",
        )
    )
    now = utc_now()
    if row is None:
        row = OpportunityEntityLinkRecord(
            opportunity_id=opportunity_id,
            entity_id=owner["entity_id"],
            role="owner",
            confidence=1.0,
            source_count=max(1, source_count),
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(row)
    else:
        row.confidence = 1.0
        row.source_count = max(row.source_count, source_count)
        row.last_seen_at = now
    session.flush()
    return row


def add_manual_alias(
    session: Session,
    *,
    entity_id: str,
    alias: str,
) -> EntityAliasRecord:
    entity = session.get(EntityRecord, entity_id)
    if entity is None or entity.status != "active":
        raise ValueError("entity not found")
    normalized = normalize_entity_name(alias)
    if len(normalized) < 2:
        raise ValueError("entity alias is too short")

    # Do not allow a manager to make identity resolution ambiguous within the same country.
    collisions = session.scalars(
        select(EntityAliasRecord).where(EntityAliasRecord.normalized_alias == normalized)
    ).all()
    for collision in collisions:
        other = session.get(EntityRecord, collision.entity_id)
        if other is None:
            continue
        if other.id != entity.id and other.country_key == entity.country_key:
            raise ValueError("alias already belongs to another entity in the same country")
        if other.id == entity.id:
            return collision

    row = EntityAliasRecord(
        entity_id=entity.id,
        alias=alias.strip(),
        normalized_alias=normalized,
        source_document_id=None,
        confidence=1.0,
        created_at=utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
        return row
    except IntegrityError:
        existing = session.scalar(
            select(EntityAliasRecord).where(
                EntityAliasRecord.entity_id == entity.id,
                EntityAliasRecord.normalized_alias == normalized,
            )
        )
        if existing is None:
            raise
        return existing
