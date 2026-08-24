from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import MembershipRecord, UserRecord, utc_now
from .directory_db import (
    DirectoryIdentityLinkRecord,
    DirectoryRoleRuleRecord,
    DirectorySourceRecord,
    DirectorySyncRunRecord,
)
from .security import Principal, ROLE_LEVEL


VALID_ROLES = frozenset(ROLE_LEVEL)


class DirectoryEntry(BaseModel):
    external_subject: str = Field(min_length=1, max_length=240)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=160)
    groups: list[str] = Field(default_factory=list, max_length=100)
    active: bool = True

    @field_validator("external_subject", "display_name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be usable")
        return normalized

    @field_validator("groups")
    @classmethod
    def normalize_groups(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.strip().casefold() for value in values if value.strip()})
        if any(len(value) > 240 for value in normalized):
            raise ValueError("directory group exceeds 240 characters")
        return normalized


class DirectorySnapshot(BaseModel):
    entries: list[DirectoryEntry] = Field(max_length=5000)


@dataclass(frozen=True)
class PlannedIdentity:
    entry: DirectoryEntry
    desired_role: str
    link: DirectoryIdentityLinkRecord | None
    membership: MembershipRecord | None
    user: UserRecord | None
    action: str


def _canonical_snapshot(snapshot: DirectorySnapshot) -> tuple[str, list[DirectoryEntry]]:
    entries = sorted(snapshot.entries, key=lambda item: item.external_subject.casefold())
    seen_subjects: set[str] = set()
    seen_active_emails: set[str] = set()
    for entry in entries:
        subject_key = entry.external_subject.casefold()
        if subject_key in seen_subjects:
            raise ValueError(f"duplicate external_subject in snapshot: {entry.external_subject}")
        seen_subjects.add(subject_key)
        if entry.active:
            if entry.email in seen_active_emails:
                raise ValueError(f"duplicate active email in snapshot: {entry.email}")
            seen_active_emails.add(entry.email)
    payload = [entry.model_dump(mode="json") for entry in entries]
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return digest, entries


def _role_rules(session: Session, source_id: str) -> dict[str, str]:
    rows = session.scalars(
        select(DirectoryRoleRuleRecord).where(DirectoryRoleRuleRecord.source_id == source_id)
    ).all()
    return {row.group_key.casefold(): row.role for row in rows}


def desired_role(source: DirectorySourceRecord, rules: dict[str, str], groups: list[str]) -> str:
    candidates = [source.default_role]
    candidates.extend(rules[group] for group in groups if group in rules)
    return max(candidates, key=lambda role: ROLE_LEVEL[role])


def _membership_links(session: Session, source_id: str) -> dict[str, DirectoryIdentityLinkRecord]:
    rows = session.scalars(
        select(DirectoryIdentityLinkRecord).where(DirectoryIdentityLinkRecord.source_id == source_id)
    ).all()
    return {row.external_subject.casefold(): row for row in rows}


def _other_org_membership_count(session: Session, user_id: str, organization_id: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(MembershipRecord)
            .where(
                MembershipRecord.user_id == user_id,
                MembershipRecord.organization_id != organization_id,
            )
        )
        or 0
    )


def _find_user_and_membership(
    session: Session,
    *,
    organization_id: str,
    email: str,
) -> tuple[UserRecord | None, MembershipRecord | None]:
    user = session.scalar(select(UserRecord).where(UserRecord.email == email))
    if user is None:
        return None, None
    membership = session.scalar(
        select(MembershipRecord).where(
            MembershipRecord.organization_id == organization_id,
            MembershipRecord.user_id == user.id,
        )
    )
    return user, membership


def _linked_membership(
    session: Session,
    link: DirectoryIdentityLinkRecord,
) -> tuple[MembershipRecord, UserRecord]:
    membership = session.get(MembershipRecord, link.membership_id)
    if membership is None:
        raise ValueError(f"directory link {link.id} references missing membership")
    user = session.get(UserRecord, membership.user_id)
    if user is None:
        raise ValueError(f"directory link {link.id} references missing user")
    return membership, user


def _plan(
    session: Session,
    *,
    source: DirectorySourceRecord,
    entries: list[DirectoryEntry],
) -> tuple[list[PlannedIdentity], list[DirectoryIdentityLinkRecord], dict]:
    if not source.is_active:
        raise ValueError("directory source is inactive")
    rules = _role_rules(session, source.id)
    links = _membership_links(session, source.id)
    planned: list[PlannedIdentity] = []
    seen_subject_keys: set[str] = set()
    existing_membership_claims = {
        row.membership_id: row
        for row in session.scalars(select(DirectoryIdentityLinkRecord)).all()
    }

    counts = {
        "create_user": 0,
        "create_membership": 0,
        "link_existing": 0,
        "reactivate": 0,
        "deactivate": 0,
        "role_change": 0,
        "profile_update": 0,
        "unchanged": 0,
    }

    for entry in entries:
        subject_key = entry.external_subject.casefold()
        seen_subject_keys.add(subject_key)
        link = links.get(subject_key)
        role = desired_role(source, rules, entry.groups)

        if link is not None:
            membership, user = _linked_membership(session, link)
            if user.email != entry.email:
                conflicting = session.scalar(
                    select(UserRecord).where(
                        UserRecord.email == entry.email,
                        UserRecord.id != user.id,
                    )
                )
                if conflicting is not None:
                    raise ValueError(
                        f"email {entry.email} already belongs to another user"
                    )
                if _other_org_membership_count(session, user.id, source.organization_id):
                    raise ValueError(
                        f"cannot change global email for cross-organization user {user.email}"
                    )
            if not entry.active:
                action = "deactivate" if membership.is_active else "unchanged"
                counts[action] += 1
            else:
                changes = []
                if not membership.is_active or link.status != "active" or not user.is_active:
                    changes.append("reactivate")
                if membership.role != role:
                    changes.append("role_change")
                if user.email != entry.email or user.display_name != entry.display_name:
                    changes.append("profile_update")
                action = "+".join(changes) if changes else "unchanged"
                if changes:
                    for change in changes:
                        counts[change] += 1
                else:
                    counts["unchanged"] += 1
            planned.append(
                PlannedIdentity(
                    entry=entry,
                    desired_role=role,
                    link=link,
                    membership=membership,
                    user=user,
                    action=action,
                )
            )
            continue

        if not entry.active:
            counts["unchanged"] += 1
            planned.append(
                PlannedIdentity(entry, role, None, None, None, "inactive_unmanaged")
            )
            continue

        user, membership = _find_user_and_membership(
            session,
            organization_id=source.organization_id,
            email=entry.email,
        )
        if membership is not None:
            claimed = existing_membership_claims.get(membership.id)
            if claimed is not None and claimed.source_id != source.id:
                raise ValueError(
                    f"membership for {entry.email} is already managed by another directory source"
                )
            counts["link_existing"] += 1
            if not membership.is_active:
                counts["reactivate"] += 1
            if membership.role != role:
                counts["role_change"] += 1
            if user is not None and user.display_name != entry.display_name:
                counts["profile_update"] += 1
            action = "link_existing"
        elif user is not None:
            counts["create_membership"] += 1
            if user.display_name != entry.display_name:
                counts["profile_update"] += 1
            action = "create_membership"
        else:
            counts["create_user"] += 1
            counts["create_membership"] += 1
            action = "create_user_membership"
        planned.append(
            PlannedIdentity(entry, role, None, membership, user, action)
        )

    missing_links: list[DirectoryIdentityLinkRecord] = []
    if source.authoritative:
        for subject_key, link in links.items():
            if subject_key in seen_subject_keys:
                continue
            membership, _ = _linked_membership(session, link)
            if membership.is_active or link.status != "inactive":
                counts["deactivate"] += 1
                missing_links.append(link)

    _protect_last_admin(
        session,
        organization_id=source.organization_id,
        planned=planned,
        missing_links=missing_links,
    )
    return planned, missing_links, counts


def _protect_last_admin(
    session: Session,
    *,
    organization_id: str,
    planned: list[PlannedIdentity],
    missing_links: list[DirectoryIdentityLinkRecord],
) -> None:
    memberships = session.scalars(
        select(MembershipRecord).where(MembershipRecord.organization_id == organization_id)
    ).all()
    state = {membership.id: (membership.is_active, membership.role) for membership in memberships}
    synthetic_admins = 0

    for item in planned:
        if not item.entry.active:
            if item.membership is not None:
                state[item.membership.id] = (False, item.membership.role)
            continue
        if item.membership is not None:
            state[item.membership.id] = (True, item.desired_role)
        elif item.desired_role == "admin":
            synthetic_admins += 1

    for link in missing_links:
        if link.membership_id in state:
            state[link.membership_id] = (False, state[link.membership_id][1])

    resulting_admins = synthetic_admins + sum(
        1 for active, role in state.values() if active and role == "admin"
    )
    if resulting_admins < 1:
        raise ValueError("directory sync would remove the organization's last active admin")


def plan_directory_snapshot(
    session: Session,
    *,
    source_id: str,
    snapshot: DirectorySnapshot,
) -> dict:
    source = session.get(DirectorySourceRecord, source_id)
    if source is None:
        raise ValueError("directory source not found")
    digest, entries = _canonical_snapshot(snapshot)
    planned, missing_links, counts = _plan(session, source=source, entries=entries)
    return {
        "source_id": source.id,
        "source_code": source.code,
        "authoritative": source.authoritative,
        "snapshot_sha256": digest,
        "received_count": len(entries),
        "summary": counts,
        "changes": [
            {
                "external_subject": item.entry.external_subject,
                "email": item.entry.email,
                "active": item.entry.active,
                "desired_role": item.desired_role,
                "action": item.action,
            }
            for item in planned
            if item.action not in {"unchanged", "inactive_unmanaged"}
        ]
        + [
            {
                "external_subject": link.external_subject,
                "email": None,
                "active": False,
                "desired_role": None,
                "action": "deactivate_missing_authoritative",
            }
            for link in missing_links
        ],
    }


def _refresh_user_active(session: Session, user_ids: set[str]) -> None:
    for user_id in user_ids:
        user = session.get(UserRecord, user_id)
        if user is None:
            continue
        active_count = session.scalar(
            select(func.count())
            .select_from(MembershipRecord)
            .where(
                MembershipRecord.user_id == user_id,
                MembershipRecord.is_active.is_(True),
            )
        ) or 0
        user.is_active = bool(active_count)


def apply_directory_snapshot(
    session: Session,
    *,
    source_id: str,
    snapshot: DirectorySnapshot,
    principal: Principal,
) -> dict:
    source = session.get(DirectorySourceRecord, source_id)
    if source is None:
        raise ValueError("directory source not found")
    digest, entries = _canonical_snapshot(snapshot)
    planned, missing_links, counts = _plan(session, source=source, entries=entries)
    now = utc_now()
    run = DirectorySyncRunRecord(
        id=str(uuid4()),
        source_id=source.id,
        snapshot_sha256=digest,
        received_count=len(entries),
        summary={},
        actor_user_id=principal.user_id,
        status="applying",
        created_at=now,
        completed_at=None,
    )
    session.add(run)
    session.flush()
    affected_user_ids: set[str] = set()

    for item in planned:
        entry = item.entry
        if item.link is not None:
            membership = item.membership
            user = item.user
            assert membership is not None and user is not None
            affected_user_ids.add(user.id)
            item.link.last_seen_run_id = run.id
            item.link.last_seen_at = now
            item.link.updated_at = now
            if not entry.active:
                membership.is_active = False
                item.link.status = "inactive"
                continue
            membership.is_active = True
            membership.role = item.desired_role
            user.is_active = True
            user.email = entry.email
            user.display_name = entry.display_name
            item.link.status = "active"
            continue

        if not entry.active:
            continue

        user = item.user
        membership = item.membership
        if user is None:
            user = UserRecord(
                id=str(uuid4()),
                email=entry.email,
                display_name=entry.display_name,
                is_active=True,
            )
            session.add(user)
            session.flush()
        else:
            user.is_active = True
            user.display_name = entry.display_name
        affected_user_ids.add(user.id)

        if membership is None:
            membership = MembershipRecord(
                organization_id=source.organization_id,
                user_id=user.id,
                role=item.desired_role,
                is_active=True,
            )
            session.add(membership)
            session.flush()
        else:
            membership.is_active = True
            membership.role = item.desired_role

        link = DirectoryIdentityLinkRecord(
            id=str(uuid4()),
            source_id=source.id,
            external_subject=entry.external_subject,
            membership_id=membership.id,
            status="active",
            last_seen_run_id=run.id,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(link)

    for link in missing_links:
        membership, user = _linked_membership(session, link)
        affected_user_ids.add(user.id)
        membership.is_active = False
        link.status = "inactive"
        link.updated_at = now

    session.flush()
    _refresh_user_active(session, affected_user_ids)
    run.status = "applied"
    run.summary = counts
    run.completed_at = now
    session.commit()
    return {
        "run_id": run.id,
        "source_id": source.id,
        "snapshot_sha256": digest,
        "received_count": len(entries),
        "summary": counts,
        "completed_at": run.completed_at.isoformat(),
    }
