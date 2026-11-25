"""Weekly briefing candidate pool helpers."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntelBriefingCandidate, IntelItem


def week_start(day: date) -> date:
    """Monday of ``day``'s ISO week."""
    return date.fromordinal(day.toordinal() - day.weekday())


def local_today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def add_candidate(session: Session, item: IntelItem, today: date) -> IntelBriefingCandidate:
    """Idempotently add the item to this week's candidate pool.

    The item row is locked by the caller, so check-then-insert is safe against
    concurrent approvals of the same item; the partial unique index is the
    final guard.
    """
    start = week_start(today)
    existing = session.scalar(
        select(IntelBriefingCandidate).where(
            IntelBriefingCandidate.org_id == item.org_id,
            IntelBriefingCandidate.item_id == item.id,
            IntelBriefingCandidate.week_start == start,
            IntelBriefingCandidate.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    candidate = IntelBriefingCandidate(
        org_id=item.org_id,
        site_id=item.site_id,
        item_id=item.id,
        week_start=start,
        created_by=item.approved_by,
    )
    session.add(candidate)
    session.flush()
    return candidate


def soft_delete_candidates(session: Session, item: IntelItem, now: datetime) -> int:
    """Withdraw/expire removes the item from every active candidate pool."""
    rows = session.scalars(
        select(IntelBriefingCandidate).where(
            IntelBriefingCandidate.org_id == item.org_id,
            IntelBriefingCandidate.item_id == item.id,
            IntelBriefingCandidate.deleted_at.is_(None),
        )
    ).all()
    for row in rows:
        row.deleted_at = now
    return len(rows)