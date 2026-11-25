"""Fictional identities and item factories. No real personal or enterprise data."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import IntelItem, IntelReminderOutbox

ORG_A = uuid.UUID("a0000000-0000-4000-8000-000000000001")
ORG_B = uuid.UUID("b0000000-0000-4000-8000-000000000002")
SITE_A1 = uuid.UUID("a0000000-0000-4000-8000-0000000000a1")
SITE_A2 = uuid.UUID("a0000000-0000-4000-8000-0000000000a2")
SITE_B1 = uuid.UUID("b0000000-0000-4000-8000-0000000000b1")

STAFF_USER = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
SUPERVISOR_USER = uuid.UUID("00000000-0000-4000-8000-000000000051")
OTHER_SUPERVISOR = uuid.UUID("00000000-0000-4000-8000-000000000052")


def headers(
    *,
    org: uuid.UUID = ORG_A,
    user: uuid.UUID | None = SUPERVISOR_USER,
    role: str = "supervisor",
    sites: list[uuid.UUID] | None = None,
) -> dict[str, str]:
    result = {"X-Org-Id": str(org), "X-User-Role": role}
    if user is not None:
        result["X-User-Id"] = str(user)
    if sites is not None:
        result["X-Site-Ids"] = ",".join(str(s) for s in sites)
    return result


def make_item(
    session: Session,
    *,
    org_id: uuid.UUID = ORG_A,
    site_id: uuid.UUID = SITE_A1,
    status: str = "in_check",
    relevance: str = "medium_relevance",
    title: str = "虚构政策情报条目",
    summary: str = "虚构摘要：某地发布产业扶持申报通知（测试数据）。",
    source_url: str = "https://example.invalid/intel/fictional-notice",
    match_conditions: dict | None = None,
    checked_by: uuid.UUID | None = None,
    review_comment: str | None = None,
) -> IntelItem:
    now = datetime.now(timezone.utc)
    item = IntelItem(
        org_id=org_id,
        site_id=site_id,
        title=title,
        summary=summary,
        source_url=source_url,
        relevance=relevance,
        match_conditions=match_conditions if match_conditions is not None else {},
        status=status,
        review_comment=review_comment,
        created_by=STAFF_USER,
    )
    if status in ("checked", "approved", "published"):
        item.checked_by = checked_by if checked_by is not None else STAFF_USER
        item.checked_at = now
    if status in ("approved", "published"):
        item.approved_by = OTHER_SUPERVISOR
        item.approved_at = now
    if status == "published":
        item.published_at = now
    if status == "expired":
        item.expired_at = now
    session.add(item)
    session.commit()
    return item


def make_pending_reminder(
    session: Session, item: IntelItem, *, remind_on=None
) -> IntelReminderOutbox:
    from datetime import date

    row = IntelReminderOutbox(
        org_id=item.org_id,
        site_id=item.site_id,
        item_id=item.id,
        remind_on=remind_on or date.today(),
        payload={"item_id": str(item.id), "matched_company_ids": []},
        status="pending",
        created_by=SUPERVISOR_USER,
    )
    session.add(row)
    session.commit()
    return row