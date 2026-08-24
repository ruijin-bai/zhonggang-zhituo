from __future__ import annotations

import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formataddr
from hashlib import sha256
from html import escape
from typing import Protocol
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import MembershipRecord, OpportunityRecord, UserRecord, utc_now
from .pursuit_delivery_db import PursuitReminderDeliveryRecord
from .pursuit_reminder_db import PursuitReminderRecord

ACTIVE_DELIVERY_STATUSES = ("pending", "retry", "processing")


class ReminderEmailTransport(Protocol):
    def send(self, message: EmailMessage) -> str:
        ...


class SMTPReminderEmailTransport:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def send(self, message: EmailMessage) -> str:
        settings = self.settings
        context = ssl.create_default_context()
        if settings.smtp_use_ssl:
            client = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=context,
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )
        try:
            if settings.smtp_starttls and not settings.smtp_use_ssl:
                client.starttls(context=context)
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            refused = client.send_message(message)
            if refused:
                raise RuntimeError(f"SMTP refused recipients: {sorted(refused)}")
        finally:
            try:
                client.quit()
            except Exception:
                client.close()
        return str(message["Message-ID"])


def _address_fingerprint(address: str) -> str:
    return sha256(address.strip().casefold().encode("utf-8")).hexdigest()[:16]


def _target_membership_id(reminder: PursuitReminderRecord) -> int:
    if reminder.escalation_level > 0 and reminder.escalated_to_membership_id is not None:
        return reminder.escalated_to_membership_id
    return reminder.recipient_membership_id


def _delivery_key(
    reminder: PursuitReminderRecord,
    membership_id: int,
    address: str,
) -> str:
    return (
        f"email:{reminder.id}:occ:{reminder.occurrence_count}:esc:{reminder.escalation_level}:"
        f"member:{membership_id}:addr:{_address_fingerprint(address)}"
    )[:220]


def _membership_email(
    session: Session,
    organization_id: str,
    membership_id: int,
) -> tuple[str, str] | None:
    row = session.execute(
        select(MembershipRecord, UserRecord)
        .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
        .where(
            MembershipRecord.id == membership_id,
            MembershipRecord.organization_id == organization_id,
            MembershipRecord.is_active.is_(True),
            UserRecord.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    membership, user = row
    address = user.email.strip()
    if not address or "@" not in address:
        return None
    return address, user.display_name


def stage_reminder_email_deliveries(
    session: Session,
    *,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    if not settings.pursuit_email_delivery_enabled:
        return {"enabled": False, "eligible": 0, "created": 0, "skipped": 0}

    now = utc_now()
    reminders = session.scalars(
        select(PursuitReminderRecord).where(PursuitReminderRecord.status == "open")
    ).all()
    created = 0
    skipped = 0
    for reminder in reminders:
        membership_id = _target_membership_id(reminder)
        recipient = _membership_email(session, reminder.organization_id, membership_id)
        if recipient is None:
            skipped += 1
            continue
        address, _ = recipient
        key = _delivery_key(reminder, membership_id, address)
        existing = session.scalar(
            select(PursuitReminderDeliveryRecord).where(
                PursuitReminderDeliveryRecord.delivery_key == key
            )
        )
        if existing is not None:
            continue
        delivery = PursuitReminderDeliveryRecord(
            id=str(uuid4()),
            reminder_id=reminder.id,
            channel="email",
            recipient_membership_id=membership_id,
            recipient_address=address,
            delivery_key=key,
            status="pending",
            attempt_count=0,
            next_attempt_at=now,
            lease_until=None,
            lease_token=None,
            error_detail=None,
            message_id=None,
            created_at=now,
            updated_at=now,
            sent_at=None,
        )
        try:
            with session.begin_nested():
                session.add(delivery)
                session.flush()
            created += 1
        except IntegrityError:
            # Concurrent staging is harmless: the delivery key is deterministic and tenant scoped.
            pass
    session.commit()
    return {
        "enabled": True,
        "eligible": len(reminders),
        "created": created,
        "skipped": skipped,
    }


def _lease_expired_clause(now):
    return or_(
        PursuitReminderDeliveryRecord.lease_until.is_(None),
        PursuitReminderDeliveryRecord.lease_until < now,
    )


def claim_reminder_email_deliveries(
    session: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    settings = settings or get_settings()
    if not settings.pursuit_email_delivery_enabled:
        return []
    now = utc_now()
    rows = session.scalars(
        select(PursuitReminderDeliveryRecord)
        .where(
            PursuitReminderDeliveryRecord.channel == "email",
            PursuitReminderDeliveryRecord.status.in_(ACTIVE_DELIVERY_STATUSES),
            PursuitReminderDeliveryRecord.next_attempt_at <= now,
            _lease_expired_clause(now),
        )
        .order_by(PursuitReminderDeliveryRecord.next_attempt_at.asc())
        .limit(limit or settings.pursuit_email_dispatch_batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    lease_until = now + timedelta(seconds=settings.pursuit_email_lease_seconds)
    claims: list[tuple[str, str]] = []
    for row in rows:
        token = str(uuid4())
        row.status = "processing"
        row.lease_until = lease_until
        row.lease_token = token
        row.updated_at = now
        claims.append((row.id, token))
    session.commit()
    return claims


def _lock_delivery(session: Session, delivery_id: str) -> PursuitReminderDeliveryRecord | None:
    return session.scalar(
        select(PursuitReminderDeliveryRecord)
        .where(PursuitReminderDeliveryRecord.id == delivery_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _retry_delay(attempt_count: int, settings: Settings) -> int:
    delay = settings.pursuit_email_dispatch_interval_seconds * (
        2 ** min(max(attempt_count - 1, 0), 10)
    )
    return min(delay, settings.pursuit_email_max_backoff_seconds)


def release_reminder_email_dispatch_claim(
    session: Session,
    delivery_id: str,
    error: str,
    *,
    lease_token: str,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    row = _lock_delivery(session, delivery_id)
    if row is None or row.lease_token != lease_token:
        session.rollback()
        return
    now = utc_now()
    row.status = "retry"
    row.lease_until = None
    row.lease_token = None
    row.error_detail = f"dispatch failed: {error}"[:4000]
    row.next_attempt_at = now + timedelta(seconds=settings.pursuit_email_dispatch_interval_seconds)
    row.updated_at = now
    session.commit()


def _cancel_delivery(session: Session, row: PursuitReminderDeliveryRecord, reason: str) -> dict:
    now = utc_now()
    row.status = "cancelled"
    row.lease_until = None
    row.lease_token = None
    row.error_detail = reason[:4000]
    row.updated_at = now
    session.commit()
    return {"delivery_id": row.id, "status": "cancelled", "reason": reason}


def _message_id(delivery_id: str, from_email: str) -> str:
    domain = from_email.rsplit("@", 1)[-1].strip().lower() if "@" in from_email else "zhituo.local"
    return f"<zhituo-{delivery_id}@{domain}>"


def _build_message(
    *,
    delivery: PursuitReminderDeliveryRecord,
    reminder: PursuitReminderRecord,
    opportunity_title: str,
    recipient_name: str,
    settings: Settings,
) -> EmailMessage:
    is_escalation = (
        reminder.escalation_level > 0
        and reminder.escalated_to_membership_id == delivery.recipient_membership_id
    )
    subject_prefix = "执行升级" if is_escalation else "执行提醒"
    subject = f"[中港智拓][{subject_prefix}] {reminder.title}"[:998]
    link = ""
    if settings.notification_public_base_url:
        link = (
            settings.notification_public_base_url.rstrip("/")
            + "/pursuit/opportunities/"
            + quote(reminder.opportunity_id, safe="")
        )

    plain_lines = [
        f"{recipient_name}：",
        "",
        f"{subject_prefix}：{reminder.title}",
        f"项目：{opportunity_title}",
        f"级别：{reminder.severity}",
        f"说明：{reminder.message}",
    ]
    if reminder.source_due_at:
        plain_lines.append(f"业务时间：{reminder.source_due_at.isoformat()}")
    if is_escalation:
        plain_lines.append("该事项已达到升级阈值，当前由 Pursuit Lead 共同关注。")
    if link:
        plain_lines.extend(["", f"进入智拓处理：{link}"])
    plain_lines.extend(
        [
            "",
            "说明：本邮件来自智拓的持久化 Reminder 事实。邮件送达不代表原事项已完成；只有业务条件解除后 Reminder 才会自动关闭。",
        ]
    )

    html_link = (
        f'<p><a href="{escape(link, quote=True)}">进入智拓处理原事项</a></p>' if link else ""
    )
    html_body = f"""
    <p>{escape(recipient_name)}：</p>
    <p><strong>{escape(subject_prefix)}：{escape(reminder.title)}</strong></p>
    <p>项目：{escape(opportunity_title)}<br>
    级别：{escape(reminder.severity)}<br>
    说明：{escape(reminder.message)}</p>
    {html_link}
    <p style="color:#666;font-size:12px">本邮件来自智拓的持久化 Reminder 事实。邮件送达不代表原事项已完成；只有业务条件解除后 Reminder 才会自动关闭。</p>
    """.strip()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = delivery.recipient_address
    message["Message-ID"] = _message_id(delivery.id, settings.smtp_from_email)
    message["X-Zhituo-Reminder-ID"] = reminder.id
    message["X-Zhituo-Delivery-ID"] = delivery.id
    message.set_content("\n".join(plain_lines))
    message.add_alternative(html_body, subtype="html")
    return message


def deliver_reminder_email(
    session: Session,
    delivery_id: str,
    *,
    lease_token: str,
    settings: Settings | None = None,
    transport: ReminderEmailTransport | None = None,
) -> dict:
    settings = settings or get_settings()
    row = _lock_delivery(session, delivery_id)
    if row is None:
        session.rollback()
        return {"delivery_id": delivery_id, "status": "missing"}
    if row.status != "processing" or row.lease_token != lease_token:
        session.rollback()
        return {"delivery_id": delivery_id, "status": "stale_claim"}

    reminder = session.get(PursuitReminderRecord, row.reminder_id)
    if reminder is None:
        return _cancel_delivery(session, row, "reminder no longer exists")
    if reminder.status != "open":
        return _cancel_delivery(session, row, f"reminder is {reminder.status}")
    expected_membership_id = _target_membership_id(reminder)
    if expected_membership_id != row.recipient_membership_id:
        return _cancel_delivery(session, row, "reminder delivery target changed")
    recipient = _membership_email(session, reminder.organization_id, row.recipient_membership_id)
    if recipient is None:
        return _cancel_delivery(session, row, "recipient membership or email is inactive")
    current_address, recipient_name = recipient
    if current_address.casefold() != row.recipient_address.casefold():
        return _cancel_delivery(session, row, "recipient email changed after staging")
    if _delivery_key(reminder, row.recipient_membership_id, current_address) != row.delivery_key:
        return _cancel_delivery(session, row, "reminder occurrence or escalation changed")

    opportunity = session.get(OpportunityRecord, reminder.opportunity_id)
    opportunity_title = opportunity.title if opportunity is not None else reminder.opportunity_id
    message = _build_message(
        delivery=row,
        reminder=reminder,
        opportunity_title=opportunity_title,
        recipient_name=recipient_name,
        settings=settings,
    )
    # Do not hold a PostgreSQL transaction while waiting for SMTP network I/O. The durable lease
    # remains committed from the claim step; the fencing token is re-checked during finalization.
    session.rollback()

    resolved_transport = transport or SMTPReminderEmailTransport(settings)
    try:
        message_id = resolved_transport.send(message)
    except Exception as exc:
        failed = _lock_delivery(session, delivery_id)
        if failed is None or failed.lease_token != lease_token:
            session.rollback()
            raise
        now = utc_now()
        failed.attempt_count += 1
        failed.lease_until = None
        failed.lease_token = None
        failed.error_detail = str(exc)[:4000]
        failed.updated_at = now
        if failed.attempt_count >= settings.pursuit_email_max_attempts:
            failed.status = "failed"
        else:
            failed.status = "retry"
            failed.next_attempt_at = now + timedelta(
                seconds=_retry_delay(failed.attempt_count, settings)
            )
        session.commit()
        return {
            "delivery_id": delivery_id,
            "status": failed.status,
            "attempt_count": failed.attempt_count,
            "error": failed.error_detail,
        }

    sent = _lock_delivery(session, delivery_id)
    if sent is None or sent.lease_token != lease_token or sent.status != "processing":
        session.rollback()
        # SMTP cannot provide end-to-end exactly-once semantics. The deterministic Message-ID and
        # fencing lease reduce duplicate risk, while this explicit outcome exposes a lost claim.
        return {"delivery_id": delivery_id, "status": "sent_but_claim_lost", "message_id": message_id}
    now = utc_now()
    sent.status = "sent"
    sent.attempt_count += 1
    sent.message_id = message_id
    sent.sent_at = now
    sent.lease_until = None
    sent.lease_token = None
    sent.error_detail = None
    sent.updated_at = now
    session.commit()
    return {
        "delivery_id": delivery_id,
        "status": "sent",
        "attempt_count": sent.attempt_count,
        "message_id": message_id,
    }


def reminder_delivery_health(session: Session, *, limit: int = 50) -> dict:
    status_rows = session.execute(
        select(PursuitReminderDeliveryRecord.status, func.count())
        .group_by(PursuitReminderDeliveryRecord.status)
    ).all()
    rows = session.scalars(
        select(PursuitReminderDeliveryRecord)
        .order_by(PursuitReminderDeliveryRecord.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "enabled": get_settings().pursuit_email_delivery_enabled,
        "counts": {status: count for status, count in status_rows},
        "recent": [
            {
                "id": row.id,
                "reminder_id": row.reminder_id,
                "channel": row.channel,
                "recipient_membership_id": row.recipient_membership_id,
                "recipient_address": row.recipient_address,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "next_attempt_at": row.next_attempt_at.isoformat(),
                "error_detail": row.error_detail,
                "message_id": row.message_id,
                "created_at": row.created_at.isoformat(),
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            }
            for row in rows
        ],
    }
