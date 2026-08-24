from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import OpportunityDraftRecord
from .models import DuplicateMatch, ProjectDiscovery
from .repository import list_opportunities


def _project_similarity(
    left_title: str,
    left_country: str,
    right_title: str,
    right_country: str,
) -> float:
    title_similarity = SequenceMatcher(None, left_title.lower(), right_title.lower()).ratio()
    country_bonus = (
        0.12
        if left_country != "待识别"
        and right_country != "待识别"
        and left_country == right_country
        else 0.0
    )
    return min(1.0, title_similarity + country_bonus)


def opportunity_duplicate_matches(
    discovery: ProjectDiscovery,
    session: Session,
) -> list[DuplicateMatch]:
    matches: list[DuplicateMatch] = []
    for item in list_opportunities(session):
        score = _project_similarity(
            discovery.title,
            discovery.country,
            item.title,
            item.country,
        )
        if score >= 0.58:
            matches.append(
                DuplicateMatch(
                    opportunity_id=item.id,
                    title=item.title,
                    country=item.country,
                    similarity=round(score, 3),
                )
            )
    return sorted(matches, key=lambda item: item.similarity, reverse=True)[:5]


def pending_draft_duplicate(
    discovery: ProjectDiscovery,
    session: Session,
    *,
    threshold: float,
) -> tuple[str, float] | None:
    """Return a high-confidence existing candidate match.

    Formal opportunities are never auto-suppressed because a new package/phase may legitimately
    resemble an existing project; those matches stay visible to the human reviewer. Pending
    candidates use a deliberately higher threshold so repeated publication of the same project
    does not flood the candidate inbox.
    """

    best: tuple[str, float] | None = None
    rows = session.scalars(
        select(OpportunityDraftRecord).where(OpportunityDraftRecord.status == "pending")
    ).all()
    for row in rows:
        try:
            candidate = ProjectDiscovery.model_validate(row.discovery)
        except (TypeError, ValueError):
            continue
        if not candidate.project_detected:
            continue
        score = _project_similarity(
            discovery.title,
            discovery.country,
            candidate.title,
            candidate.country,
        )
        if score < threshold:
            continue
        if best is None or score > best[1]:
            best = (row.id, round(score, 3))
    return best
