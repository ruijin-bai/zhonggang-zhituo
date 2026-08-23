from collections import Counter, defaultdict
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import EvidenceRecord, OpportunityDraftRecord, OpportunityEventRecord, SourceRecord
from .discovery import discover
from .models import DiscoverRequest, DiscoverResult, Opportunity, SourceRank
from .repository import list_opportunities


class CountryRadar(BaseModel):
    country: str
    region: str
    opportunity_count: int
    pending_draft_count: int
    source_count: int
    evidence_count: int
    high_grade_count: int
    average_score: float | None = None
    average_confidence: float | None = None
    total_value_usd_m: float | None = None
    activity_index: int = Field(ge=0, le=100)
    attractiveness_index: int | None = Field(default=None, ge=0, le=100)
    top_sectors: list[str] = Field(default_factory=list)


class SectorRadar(BaseModel):
    sector: str
    opportunity_count: int
    high_grade_count: int
    average_score: float | None = None
    total_value_usd_m: float | None = None


class RadarOverview(BaseModel):
    opportunity_count: int
    pending_draft_count: int
    source_count: int
    evidence_count: int
    recent_event_count: int
    country_count: int
    countries: list[CountryRadar]
    sectors: list[SectorRadar]
    note: str


class BatchScanItem(BaseModel):
    url: str | None = None
    text: str | None = Field(default=None, max_length=100_000)
    source_title: str | None = None
    publisher: str = "公开来源"
    published_at: str = "待核实"
    source_rank: SourceRank = "B"
    use_ai: bool = True
    is_demo: bool = False

    @model_validator(mode="after")
    def require_url_or_text(self):
        if not self.url and not (self.text and self.text.strip()):
            raise ValueError("url 和 text 至少提供一个")
        return self


class BatchScanRequest(BaseModel):
    items: list[BatchScanItem] = Field(min_length=1, max_length=8)


class BatchScanEntry(BaseModel):
    index: int
    ok: bool
    result: DiscoverResult | None = None
    error: str | None = None


class BatchScanResult(BaseModel):
    scanned: int
    discovered: int
    pending_drafts: int
    errors: int
    entries: list[BatchScanEntry]


def _country_for_draft(discovery: dict[str, Any]) -> tuple[str, str, str]:
    country = str(discovery.get("country") or "待识别")
    region = str(discovery.get("region") or "待识别")
    sector = str(discovery.get("sector") or "待识别")
    return country, region, sector


def _database_counts(session: Session) -> tuple[list[Any], dict[str, int], dict[str, int], int, int, int]:
    drafts: list[Any] = []
    sources_by_country: dict[str, int] = defaultdict(int)
    evidence_by_country: dict[str, int] = defaultdict(int)
    source_count = evidence_count = recent_event_count = 0
    try:
        drafts = list(
            session.scalars(
                select(OpportunityDraftRecord).where(OpportunityDraftRecord.status == "pending")
            ).all()
        )
        source_count = session.scalar(select(func.count()).select_from(SourceRecord)) or 0
        evidence_count = session.scalar(select(func.count()).select_from(EvidenceRecord)) or 0
        recent_event_count = session.scalar(select(func.count()).select_from(OpportunityEventRecord)) or 0

        source_rows = session.execute(
            select(SourceRecord.opportunity_id, func.count(SourceRecord.id))
            .where(SourceRecord.opportunity_id.is_not(None))
            .group_by(SourceRecord.opportunity_id)
        ).all()
        evidence_rows = session.execute(
            select(EvidenceRecord.opportunity_id, func.count(EvidenceRecord.id))
            .group_by(EvidenceRecord.opportunity_id)
        ).all()
        opportunity_lookup = {item.id: item for item in list_opportunities(session)}
        for opportunity_id, count in source_rows:
            item = opportunity_lookup.get(opportunity_id)
            if item:
                sources_by_country[item.country] += int(count)
        for opportunity_id, count in evidence_rows:
            item = opportunity_lookup.get(opportunity_id)
            if item:
                evidence_by_country[item.country] += int(count)
    except SQLAlchemyError:
        session.rollback()
    return drafts, dict(sources_by_country), dict(evidence_by_country), int(source_count), int(evidence_count), int(recent_event_count)


def build_radar(
    opportunities: list[Opportunity],
    *,
    drafts: list[Any] | None = None,
    sources_by_country: dict[str, int] | None = None,
    evidence_by_country: dict[str, int] | None = None,
    source_count: int = 0,
    evidence_count: int = 0,
    recent_event_count: int = 0,
) -> RadarOverview:
    drafts = drafts or []
    sources_by_country = sources_by_country or {}
    evidence_by_country = evidence_by_country or {}

    grouped: dict[str, list[Opportunity]] = defaultdict(list)
    region_by_country: dict[str, str] = {}
    sectors_by_country: dict[str, Counter[str]] = defaultdict(Counter)
    draft_counts: Counter[str] = Counter()
    draft_sectors: dict[str, Counter[str]] = defaultdict(Counter)

    for item in opportunities:
        grouped[item.country].append(item)
        region_by_country[item.country] = item.region
        sectors_by_country[item.country][item.sector] += 1

    for draft in drafts:
        discovery = draft.discovery if hasattr(draft, "discovery") else draft
        country, region, sector = _country_for_draft(discovery)
        if country == "待识别":
            continue
        draft_counts[country] += 1
        region_by_country.setdefault(country, region)
        draft_sectors[country][sector] += 1

    countries = sorted(set(grouped) | set(draft_counts))
    radar_countries: list[CountryRadar] = []
    for country in countries:
        items = grouped.get(country, [])
        rated = [item for item in items if item.confidence >= 45]
        high_grade = [item for item in rated if item.grade == "A"]
        average_score = round(sum(item.score for item in rated) / len(rated), 1) if rated else None
        average_confidence = round(sum(item.confidence for item in items) / len(items), 1) if items else None
        values = [item.estimated_value_usd_m for item in items if item.estimated_value_usd_m is not None]
        total_value = round(sum(values), 1) if values else None

        activity_raw = (
            len(items) * 18
            + draft_counts[country] * 12
            + sources_by_country.get(country, 0) * 4
            + evidence_by_country.get(country, 0) * 3
        )
        activity_index = min(100, activity_raw)
        attractiveness = None
        if rated and average_score is not None:
            high_share = len(high_grade) / len(rated)
            confidence_factor = sum(item.confidence for item in rated) / len(rated) / 100
            attractiveness = round(min(100, average_score * 0.72 + high_share * 18 + confidence_factor * 10))

        sector_counter = sectors_by_country[country] + draft_sectors[country]
        top_sectors = [name for name, _ in sector_counter.most_common(3) if name != "待识别"]
        radar_countries.append(
            CountryRadar(
                country=country,
                region=region_by_country.get(country, "待识别"),
                opportunity_count=len(items),
                pending_draft_count=draft_counts[country],
                source_count=sources_by_country.get(country, 0),
                evidence_count=evidence_by_country.get(country, 0),
                high_grade_count=len(high_grade),
                average_score=average_score,
                average_confidence=average_confidence,
                total_value_usd_m=total_value,
                activity_index=activity_index,
                attractiveness_index=attractiveness,
                top_sectors=top_sectors,
            )
        )

    radar_countries.sort(
        key=lambda item: (
            item.attractiveness_index is not None,
            item.attractiveness_index or 0,
            item.activity_index,
        ),
        reverse=True,
    )

    sector_groups: dict[str, list[Opportunity]] = defaultdict(list)
    for item in opportunities:
        sector_groups[item.sector].append(item)
    radar_sectors: list[SectorRadar] = []
    for sector, items in sector_groups.items():
        rated = [item for item in items if item.confidence >= 45]
        values = [item.estimated_value_usd_m for item in items if item.estimated_value_usd_m is not None]
        radar_sectors.append(
            SectorRadar(
                sector=sector,
                opportunity_count=len(items),
                high_grade_count=sum(1 for item in rated if item.grade == "A"),
                average_score=(round(sum(item.score for item in rated) / len(rated), 1) if rated else None),
                total_value_usd_m=(round(sum(values), 1) if values else None),
            )
        )
    radar_sectors.sort(key=lambda item: (item.opportunity_count, item.average_score or 0), reverse=True)

    return RadarOverview(
        opportunity_count=len(opportunities),
        pending_draft_count=len(drafts),
        source_count=source_count,
        evidence_count=evidence_count,
        recent_event_count=recent_event_count,
        country_count=len(radar_countries),
        countries=radar_countries,
        sectors=radar_sectors,
        note=(
            "市场活跃度反映机会、草稿与证据沉淀；经营吸引力仅对证据置信度达到阈值的正式机会计算。"
            "当前指标用于横向筛选和资源聚焦，不替代国别战略决策。"
        ),
    )


def get_radar(session: Session) -> RadarOverview:
    opportunities = list_opportunities(session)
    drafts, sources_by_country, evidence_by_country, source_count, evidence_count, recent_event_count = _database_counts(session)
    return build_radar(
        opportunities,
        drafts=drafts,
        sources_by_country=sources_by_country,
        evidence_by_country=evidence_by_country,
        source_count=source_count,
        evidence_count=evidence_count,
        recent_event_count=recent_event_count,
    )


async def batch_scan(request: BatchScanRequest, session: Session) -> BatchScanResult:
    entries: list[BatchScanEntry] = []
    discovered_count = 0
    draft_count = 0
    error_count = 0
    for index, item in enumerate(request.items):
        try:
            result = await discover(DiscoverRequest.model_validate(item.model_dump()), session)
            detected = result.draft.discovery.project_detected
            discovered_count += int(detected)
            draft_count += int(result.draft.persisted)
            entries.append(BatchScanEntry(index=index, ok=True, result=result))
        except Exception as exc:  # batch mode isolates one failing source from the rest
            error_count += 1
            entries.append(BatchScanEntry(index=index, ok=False, error=str(exc)))
    return BatchScanResult(
        scanned=len(request.items),
        discovered=discovered_count,
        pending_drafts=draft_count,
        errors=error_count,
        entries=entries,
    )
