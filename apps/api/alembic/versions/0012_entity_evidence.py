"""add entity resolution and multi-source evidence aggregation

Revision ID: 0012_entity_evidence
Revises: 0011_candidate_processing
Create Date: 2026-08-24
"""

from __future__ import annotations

from hashlib import sha256
import re
import unicodedata
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0012_entity_evidence"
down_revision = "0011_candidate_processing"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"
_UNKNOWN = {"", "待识别", "待核实", "unknown", "n/a", "na", "none"}


def _enable_rls(table_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "{POLICY_NAME}" ON "{table_name}"
            USING (
                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
            )
            WITH CHECK (
                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
            )'''
    )


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _known(value: str | None) -> bool:
    return bool(value and value.strip().casefold() not in _UNKNOWN)


def _identity_key(name: str, country: str) -> str:
    return sha256(f"organization|{name}|{country}".encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_sources_source_document_id",
        "sources",
        "source_documents",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sources_source_document_id", "sources", ["source_document_id"])

    op.create_table(
        "source_document_insights",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("project_detected", sa.Boolean(), nullable=False),
        sa.Column("extraction_mode", sa.String(length=40), nullable=False),
        sa.Column("discovery", sa.JSON(), nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_source_document_insights_organization_id",
        "source_document_insights",
        ["organization_id"],
    )
    op.create_index(
        "ix_source_document_insights_project_detected",
        "source_document_insights",
        ["project_detected"],
    )
    op.create_index(
        "ix_source_document_insights_identity_fingerprint",
        "source_document_insights",
        ["identity_fingerprint"],
    )
    _enable_rls("source_document_insights")

    op.create_table(
        "candidate_source_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "draft_id",
            sa.String(length=36),
            sa.ForeignKey("opportunity_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "draft_id",
            "source_document_id",
            name="uq_candidate_source_org_draft_document",
        ),
    )
    op.create_index(
        "ix_candidate_source_documents_organization_id",
        "candidate_source_documents",
        ["organization_id"],
    )
    op.create_index("ix_candidate_source_documents_draft_id", "candidate_source_documents", ["draft_id"])
    op.create_index(
        "ix_candidate_source_documents_source_document_id",
        "candidate_source_documents",
        ["source_document_id"],
    )
    _enable_rls("candidate_source_documents")

    op.create_table(
        "entities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_name", sa.String(length=320), nullable=False),
        sa.Column("normalized_name", sa.String(length=320), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("country_key", sa.String(length=120), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("entity_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "identity_key",
            name="uq_entity_org_type_identity",
        ),
    )
    op.create_index("ix_entities_organization_id", "entities", ["organization_id"])
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])
    op.create_index("ix_entities_normalized_name", "entities", ["normalized_name"])
    op.create_index("ix_entities_country_key", "entities", ["country_key"])
    op.create_index("ix_entities_status", "entities", ["status"])
    _enable_rls("entities")

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=320), nullable=False),
        sa.Column("normalized_alias", sa.String(length=320), nullable=False),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("source_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "entity_id",
            "normalized_alias",
            name="uq_entity_alias_org_entity_normalized",
        ),
    )
    op.create_index("ix_entity_aliases_organization_id", "entity_aliases", ["organization_id"])
    op.create_index("ix_entity_aliases_entity_id", "entity_aliases", ["entity_id"])
    op.create_index("ix_entity_aliases_normalized_alias", "entity_aliases", ["normalized_alias"])
    _enable_rls("entity_aliases")

    op.create_table(
        "source_entity_mentions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("name_text", sa.String(length=320), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("resolver", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "source_document_id",
            "entity_id",
            "role",
            name="uq_entity_mention_org_document_entity_role",
        ),
    )
    op.create_index("ix_source_entity_mentions_organization_id", "source_entity_mentions", ["organization_id"])
    op.create_index("ix_source_entity_mentions_source_document_id", "source_entity_mentions", ["source_document_id"])
    op.create_index("ix_source_entity_mentions_entity_id", "source_entity_mentions", ["entity_id"])
    op.create_index("ix_source_entity_mentions_role", "source_entity_mentions", ["role"])
    _enable_rls("source_entity_mentions")

    op.create_table(
        "opportunity_entity_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            sa.String(length=120),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "opportunity_id",
            "entity_id",
            "role",
            name="uq_opportunity_entity_org_opportunity_entity_role",
        ),
    )
    op.create_index("ix_opportunity_entity_links_organization_id", "opportunity_entity_links", ["organization_id"])
    op.create_index("ix_opportunity_entity_links_opportunity_id", "opportunity_entity_links", ["opportunity_id"])
    op.create_index("ix_opportunity_entity_links_entity_id", "opportunity_entity_links", ["entity_id"])
    op.create_index("ix_opportunity_entity_links_role", "opportunity_entity_links", ["role"])
    _enable_rls("opportunity_entity_links")

    bind = op.get_bind()
    now_sql = "CURRENT_TIMESTAMP"
    # Preserve every source already suppressed as a duplicate in the previous stage by attaching
    # it to the candidate it supported. This turns old duplicate-processing history into useful
    # multi-source evidence immediately after migration.
    bind.execute(
        sa.text(
            f"""
            INSERT INTO candidate_source_documents (
                organization_id, draft_id, source_document_id, is_primary, added_at
            )
            SELECT
                organization_id,
                COALESCE(draft_id, duplicate_draft_id),
                source_document_id,
                CASE WHEN draft_id IS NOT NULL THEN TRUE ELSE FALSE END,
                {now_sql}
            FROM candidate_processing
            WHERE COALESCE(draft_id, duplicate_draft_id) IS NOT NULL
            ON CONFLICT (organization_id, draft_id, source_document_id) DO NOTHING
            """
        )
    )

    # Existing created candidates already contain a structured ProjectDiscovery JSON payload.
    bind.execute(
        sa.text(
            f"""
            INSERT INTO source_document_insights (
                id, organization_id, source_document_id, project_detected, extraction_mode,
                discovery, identity_fingerprint, created_at, updated_at
            )
            SELECT
                cp.source_document_id,
                cp.organization_id,
                cp.source_document_id,
                TRUE,
                COALESCE(cp.extraction_mode, 'legacy'),
                d.discovery,
                NULL,
                {now_sql},
                {now_sql}
            FROM candidate_processing cp
            JOIN opportunity_drafts d ON d.id = cp.draft_id
            WHERE cp.draft_id IS NOT NULL
            ON CONFLICT (source_document_id) DO NOTHING
            """
        )
    )

    # Seed a conservative entity baseline from already-confirmed opportunities. Only known owner
    # names are migrated; no fuzzy historical guesses are made.
    rows = bind.execute(
        sa.text(
            "SELECT id, organization_id, owner, country FROM opportunities WHERE owner IS NOT NULL"
        )
    ).mappings().all()
    for row in rows:
        if not _known(row["owner"]):
            continue
        normalized = _normalize_name(row["owner"])
        country = row["country"] if _known(row["country"]) else ""
        country_key = _normalize_name(country)
        identity_key = _identity_key(normalized, country_key)
        existing = bind.execute(
            sa.text(
                """
                SELECT id FROM entities
                WHERE organization_id=:org AND entity_type='organization' AND identity_key=:key
                """
            ),
            {"org": row["organization_id"], "key": identity_key},
        ).scalar_one_or_none()
        entity_id = existing or str(uuid4())
        if existing is None:
            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO entities (
                        id, organization_id, entity_type, canonical_name, normalized_name,
                        country, country_key, identity_key, status, entity_metadata,
                        created_at, updated_at
                    ) VALUES (
                        :id, :org, 'organization', :name, :normalized,
                        :country, :country_key, :identity_key, 'active', :metadata,
                        {now_sql}, {now_sql}
                    )
                    """
                ),
                {
                    "id": entity_id,
                    "org": row["organization_id"],
                    "name": row["owner"],
                    "normalized": normalized,
                    "country": country or None,
                    "country_key": country_key,
                    "identity_key": identity_key,
                    "metadata": "{}",
                },
            )
            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO entity_aliases (
                        organization_id, entity_id, alias, normalized_alias,
                        source_document_id, confidence, created_at
                    ) VALUES (:org, :entity_id, :alias, :normalized, NULL, 1.0, {now_sql})
                    """
                ),
                {
                    "org": row["organization_id"],
                    "entity_id": entity_id,
                    "alias": row["owner"],
                    "normalized": normalized,
                },
            )
        bind.execute(
            sa.text(
                f"""
                INSERT INTO opportunity_entity_links (
                    organization_id, opportunity_id, entity_id, role, confidence,
                    source_count, first_seen_at, last_seen_at
                ) VALUES (:org, :opportunity, :entity, 'owner', 1.0, 1, {now_sql}, {now_sql})
                ON CONFLICT (organization_id, opportunity_id, entity_id, role) DO NOTHING
                """
            ),
            {
                "org": row["organization_id"],
                "opportunity": row["id"],
                "entity": entity_id,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in (
            "opportunity_entity_links",
            "source_entity_mentions",
            "entity_aliases",
            "entities",
            "candidate_source_documents",
            "source_document_insights",
        ):
            op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table_name}"')
    op.drop_table("opportunity_entity_links")
    op.drop_table("source_entity_mentions")
    op.drop_table("entity_aliases")
    op.drop_table("entities")
    op.drop_table("candidate_source_documents")
    op.drop_table("source_document_insights")
    op.drop_index("ix_sources_source_document_id", table_name="sources")
    op.drop_constraint("fk_sources_source_document_id", "sources", type_="foreignkey")
    op.drop_column("sources", "source_document_id")
