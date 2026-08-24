from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import OpportunityDraftRecord
from .models import DuplicateMatch, ProjectDiscovery
from .repository import list_opportunities

_UNKNOWN_VALUES = {"", "待识别", "待核实", "unknown", "n/a", "na", "none"}


def _known(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in _UNKNOWN_VALUES)


def _same_known(left: str | None, right: str | None) -> bool:
    return bool(
        _known(left)
        and _known(right)
        and left is not None
        and right is not None
        and left.strip().lower() == right.strip().lower()
    )


def _project_similarity(
    left_title: str,
    left_country: str,
    right_title: str,
    right_country: str,
    *,
    left_sector: str | None = None,
    right_sector: str | None = None,
    left_owner: str | None = None,
    right_owner: str | None = None,
) -> float:
    title_similarity = SequenceMatcher(None, left_title.lower(), right_title.lower()).ratio()

    # Known country disagreement is a strong identity conflict. Without this guard, two generic
    # projects named e.g. "National Highway Project" in different countries can score 1.0 from
    # title equality and be incorrectly auto-suppressed.
    if _known(left_country) and _known(right_country) and not _same_known(left_country, right_country):
        return min(0.55, title_similarity)

    score = title_similarity
    if _same_known(left_country, right_country):
        score += 0.12
    if _same_known(left_sector, right_sector):
        score += 0.05
    if _same_known(left_owner, right_owner):
        score += 0.05

    # A known sector conflict should never trigger high-confidence candidate auto-dedupe, while
    # still allowing the formal-opportunity UI to show a weak human-review hint when titles match.
    if _known(left_sector) and _known(right_sector) and not _same_known(left_sector, right_sector):
        return min(0.70, score)
    return min(1.0, score)


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
            left_sector=discovery.sector,
            right_sector=item.sector,
            left_owner=discovery.owner,
            right_owner=item.owner,
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
            left_sector=discovery.sector,
            right_sector=candidate.sector,
            left_owner=discovery.owner,
            right_owner=candidate.owner,
        )
        if score < threshold:
            continue
        if best is None or score > best[1]:
            best = (row.id, round(score, 3))
    return best
