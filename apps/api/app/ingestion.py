from uuid import uuid4

from sqlalchemy.orm import Session

from .ai import AIService
from .db import EvidenceRecord, OpportunityEventRecord, ScoreSnapshotRecord, SourceRecord
from .models import IngestResult, SourceIngestRequest
from .repository import database_record, get_opportunity
from .scoring import apply_score_updates, calculate_score

AUTO_APPLY_RANKS = {"S", "A"}
MIN_AUTO_APPLY_CONFIDENCE = 0.80


async def ingest_source(
    request: SourceIngestRequest,
    session: Session,
    ai_service: AIService | None = None,
) -> IngestResult:
    ai_service = ai_service or AIService()
    extraction, extraction_mode = await ai_service.extract_source(request.text, use_ai=request.use_ai)

    if request.opportunity_id is None:
        return IngestResult(
            opportunity_id=None,
            persisted=False,
            extraction_mode=extraction_mode,
            extraction=extraction,
            applied_fields=[],
            note="已完成情报抽取预览；选择目标机会后才会绑定证据并触发重评。",
        )

    current = get_opportunity(request.opportunity_id, session)
    if current is None:
        return IngestResult(
            opportunity_id=request.opportunity_id,
            persisted=False,
            extraction_mode=extraction_mode,
            extraction=extraction,
            applied_fields=[],
            note="未找到目标机会，未执行写入。",
        )

    record = database_record(request.opportunity_id, session)
    if record is None:
        preview_updates = {
            fact.field_name: fact.score_hint
            for fact in extraction.facts
            if fact.score_hint is not None
            and request.source_rank in AUTO_APPLY_RANKS
            and fact.confidence >= MIN_AUTO_APPLY_CONFIDENCE
        }
        updated_breakdown, applied = apply_score_updates(current.breakdown, preview_updates)
        score_result = calculate_score(updated_breakdown, current.confidence)
        return IngestResult(
            opportunity_id=current.id,
            persisted=False,
            extraction_mode=extraction_mode,
            extraction=extraction,
            score_before=current.score,
            score_after=score_result.total,
            grade_before=current.grade,
            grade_after=score_result.grade,
            decision_after=score_result.decision,
            applied_fields=applied,
            note="当前使用 JSON/降级数据源，因此仅完成重评预览；初始化数据库后可持久化证据和评分快照。",
        )

    source_id = str(uuid4())
    source = SourceRecord(
        id=source_id,
        opportunity_id=record.id,
        title=request.title,
        publisher=request.publisher,
        published_at=request.published_at,
        source_rank=request.source_rank,
        url=request.url,
        raw_text=request.text,
        is_demo=request.is_demo,
    )
    session.add(source)

    updates: dict[str, int] = {}
    for fact in extraction.facts:
        session.add(
            EvidenceRecord(
                id=str(uuid4()),
                opportunity_id=record.id,
                source_id=source_id,
                rank=request.source_rank,
                title=request.title,
                publisher=request.publisher,
                published_at=request.published_at,
                fact=fact.evidence_quote,
                field_name=fact.field_name,
                confidence=fact.confidence,
                source_url=request.url,
            )
        )
        if (
            fact.score_hint is not None
            and request.source_rank in AUTO_APPLY_RANKS
            and fact.confidence >= MIN_AUTO_APPLY_CONFIDENCE
        ):
            updates[fact.field_name] = fact.score_hint

    old_score = record.score
    old_grade = record.grade
    updated_breakdown, applied_fields = apply_score_updates(current.breakdown, updates)
    result = calculate_score(updated_breakdown, current.confidence)

    if applied_fields:
        record.breakdown = updated_breakdown.model_dump()
        record.score = result.total
        record.grade = result.grade
        record.decision = result.decision
        maturity_fact = next(
            (fact for fact in extraction.facts if fact.field_name == "project_maturity"),
            None,
        )
        if maturity_fact and "project_maturity" in applied_fields:
            record.stage = maturity_fact.value
        note = f"新情报触发自动重评：{old_score}/{old_grade} → {result.total}/{result.grade}。"
        session.add(
            ScoreSnapshotRecord(
                opportunity_id=record.id,
                total=result.total,
                grade=result.grade,
                breakdown=updated_breakdown.model_dump(),
                note=note,
            )
        )
        session.add(
            OpportunityEventRecord(
                opportunity_id=record.id,
                event_type="score_changed",
                payload={
                    "source_id": source_id,
                    "score_before": old_score,
                    "score_after": result.total,
                    "grade_before": old_grade,
                    "grade_after": result.grade,
                    "applied_fields": applied_fields,
                },
            )
        )
    else:
        note = "情报与证据已保存，但来源等级/置信度未达到自动修改评分的阈值。"
        session.add(
            OpportunityEventRecord(
                opportunity_id=record.id,
                event_type="evidence_added",
                payload={"source_id": source_id, "applied_fields": []},
            )
        )

    session.commit()
    return IngestResult(
        opportunity_id=record.id,
        persisted=True,
        extraction_mode=extraction_mode,
        extraction=extraction,
        score_before=old_score,
        score_after=record.score,
        grade_before=old_grade,
        grade_after=record.grade,
        decision_after=record.decision,
        applied_fields=applied_fields,
        note=note,
    )
