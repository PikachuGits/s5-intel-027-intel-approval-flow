"""Core approval and lifecycle logic.

Every public function owns its transaction and commits before returning.
``approve_item`` additionally dispatches the reminder outbox row *after* the
approval commit, so a reminder-service outage can never roll back an approval.

Guard order for approve/reject: role (403) → data scope (404) → state (409)
→ four-eyes (403) → link recheck (409). State validity is checked before the
four-eyes rule so an out-of-state call always answers 409 (AC-1), and the link
recheck only runs for otherwise-valid approvals.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import ApprovalAction, ItemStatus, Relevance, ReminderStatus, Role
from app.models import IntelApproval, IntelAuditLog, IntelItem, IntelReminderOutbox
from app.principal import Principal
from app.services import briefing
from app.services.errors import (
    ForbiddenRoleError,
    FourEyesViolationError,
    IllegalTransitionHTTPError,
    LinkRecheckFailedError,
    LockedContentError,
    MissingActorError,
    NotFoundError,
    RejectCommentRequiredError,
)
from app.services.link_checker import LinkChecker
from app.services.matcher import MemberMatcher
from app.services.reminder import ReminderDispatchResult, ReminderService
from app.state_machine import IllegalTransitionError, target_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_actor(principal: Principal) -> uuid.UUID:
    if principal.user_id is None:
        raise MissingActorError(
            "X-User-Id is required for this operation (S2-IAM stub; see app/api/deps.py)"
        )
    return principal.user_id


def _require_supervisor(principal: Principal) -> None:
    if principal.role != Role.SUPERVISOR:
        raise ForbiddenRoleError("only supervisors may perform this operation")


def _get_item(
    session: Session, principal: Principal, item_id: uuid.UUID, *, lock: bool = False
) -> IntelItem:
    statement = select(IntelItem).where(
        IntelItem.id == item_id,
        IntelItem.org_id == principal.org_id,
        IntelItem.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    item = session.scalar(statement)
    if item is None or (
        principal.site_ids is not None and item.site_id not in principal.site_ids
    ):
        raise NotFoundError(f"intel item {item_id} not found in the caller's data scope")
    return item


def _transition(item: IntelItem, action: str) -> ItemStatus:
    try:
        return target_status(action, item.status)
    except IllegalTransitionError as exc:
        raise IllegalTransitionHTTPError(
            str(exc), detail={"action": action, "current_status": item.status}
        ) from exc


def _audit(
    session: Session,
    item: IntelItem,
    action: str,
    actor_id: uuid.UUID | None,
    detail: dict[str, Any],
) -> None:
    session.add(
        IntelAuditLog(
            org_id=item.org_id,
            site_id=item.site_id,
            entity_type="intel_item",
            entity_id=item.id,
            action=action,
            actor_id=actor_id,
            detail=detail,
            created_by=actor_id,
        )
    )


def _record_decision(
    session: Session,
    item: IntelItem,
    action: ApprovalAction,
    from_status: str,
    to_status: str,
    actor: uuid.UUID,
    *,
    comment: str | None = None,
    link_recheck_ok: bool | None = None,
    link_recheck_detail: dict | None = None,
) -> IntelApproval:
    approval = IntelApproval(
        org_id=item.org_id,
        site_id=item.site_id,
        item_id=item.id,
        action=action.value,
        from_status=from_status,
        to_status=to_status,
        comment=comment,
        decided_by=actor,
        link_recheck_ok=link_recheck_ok,
        link_recheck_detail=link_recheck_detail,
        created_by=actor,
    )
    session.add(approval)
    session.flush()
    return approval


def _skip_pending_reminders(session: Session, item: IntelItem, reason: str) -> int:
    rows = session.scalars(
        select(IntelReminderOutbox).where(
            IntelReminderOutbox.org_id == item.org_id,
            IntelReminderOutbox.item_id == item.id,
            IntelReminderOutbox.status == ReminderStatus.PENDING,
        )
    ).all()
    for row in rows:
        row.status = ReminderStatus.SKIPPED
        row.last_error = reason
    return len(rows)


# ---------------------------------------------------------------------------
# Read paths
# ---------------------------------------------------------------------------


def get_item(session: Session, principal: Principal, item_id: uuid.UUID) -> IntelItem:
    return _get_item(session, principal, item_id)


def list_approvals(
    session: Session,
    principal: Principal,
    *,
    status_filter: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[IntelItem]]:
    """Supervisor worklist. ``pending`` = items waiting in ``checked``.

    ``rejected`` = items whose latest recorded decision is a reject (they sit
    back in ``in_check`` for rework).
    """
    _require_supervisor(principal)
    base = select(IntelItem).where(
        IntelItem.org_id == principal.org_id, IntelItem.deleted_at.is_(None)
    )
    if principal.site_ids is not None:
        base = base.where(IntelItem.site_id.in_(principal.site_ids))

    if status_filter == "pending":
        base = base.where(IntelItem.status == ItemStatus.CHECKED)
    elif status_filter == "approved":
        base = base.where(IntelItem.status == ItemStatus.APPROVED)
    elif status_filter == "expired":
        base = base.where(IntelItem.status == ItemStatus.EXPIRED)
    elif status_filter == "rejected":
        ranked = (
            select(
                IntelApproval.item_id,
                IntelApproval.action,
                func.row_number()
                .over(
                    partition_by=IntelApproval.item_id,
                    order_by=(IntelApproval.created_at.desc(), IntelApproval.id.desc()),
                )
                .label("rn"),
            )
            .where(IntelApproval.org_id == principal.org_id)
            .subquery()
        )
        base = base.where(
            IntelItem.status == ItemStatus.IN_CHECK,
            IntelItem.id.in_(
                select(ranked.c.item_id).where(ranked.c.rn == 1, ranked.c.action == "reject")
            ),
        )
    else:  # pragma: no cover - guarded by the API layer's Literal
        raise ValueError(f"unknown status filter {status_filter!r}")

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    order = (
        IntelItem.checked_at.asc() if status_filter == "pending" else IntelItem.updated_at.desc()
    )
    rows = list(
        session.scalars(base.order_by(order, IntelItem.id).limit(limit).offset(offset)).all()
    )
    return int(total), rows


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------


def submit_item(session: Session, principal: Principal, item_id: uuid.UUID) -> IntelItem:
    """Employee submits a checked item for supervisor approval."""
    actor = _require_actor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    destination = _transition(item, "submit")
    from_status = item.status
    item.status = destination.value
    item.checked_by = actor
    item.checked_at = _now()
    _audit(
        session, item, "submit", actor,
        {"from_status": from_status, "to_status": destination.value},
    )
    session.commit()
    return item


@dataclass(frozen=True)
class ApproveOutcome:
    item: IntelItem
    approval: IntelApproval
    briefing_week_start: date
    reminder_status: str | None
    reminder_outbox_id: uuid.UUID | None


def approve_item(
    session: Session,
    principal: Principal,
    item_id: uuid.UUID,
    *,
    link_checker: LinkChecker,
    matcher: MemberMatcher,
    reminder: ReminderService,
    comment: str | None = None,
) -> ApproveOutcome:
    actor = _require_actor(principal)
    _require_supervisor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    destination = _transition(item, "approve")  # 409 unless checked (AC-1)

    if item.checked_by is not None and item.checked_by == actor:
        raise FourEyesViolationError(
            "supervisors cannot approve items they checked themselves (four-eyes principle)"
        )

    recheck = link_checker.check(item.source_url)
    if not recheck.ok:
        _audit(
            session, item, "approve_blocked", actor,
            {"reason": "link_recheck_failed", "link_recheck": recheck.as_dict()},
        )
        session.commit()
        raise LinkRecheckFailedError(
            "original link recheck failed; the item cannot be approved",
            detail={"link_recheck": recheck.as_dict()},
        )

    from_status = item.status
    now = _now()
    item.status = destination.value
    item.approved_by = actor
    item.approved_at = now

    approval = _record_decision(
        session, item, ApprovalAction.APPROVE, from_status, destination.value, actor,
        comment=comment, link_recheck_ok=True, link_recheck_detail=recheck.as_dict(),
    )
    _audit(
        session, item, "approve", actor,
        {
            "from_status": from_status,
            "to_status": destination.value,
            "approval_id": str(approval.id),
            "link_recheck": recheck.as_dict(),
        },
    )

    today = briefing.local_today(get_settings().app_timezone)
    candidate = briefing.add_candidate(session, item, today)

    outbox: IntelReminderOutbox | None = None
    if item.relevance == Relevance.HIGH:
        matches = matcher.match(item)
        payload = {
            "item_id": str(item.id),
            "org_id": str(item.org_id),
            "site_id": str(item.site_id),
            "title": item.title,
            "source_url": item.source_url,
            "relevance": item.relevance,
            "matched_company_ids": [str(m) for m in matches],
            "remind_on": today.isoformat(),
        }
        outbox = IntelReminderOutbox(
            org_id=item.org_id,
            site_id=item.site_id,
            item_id=item.id,
            remind_on=today,
            payload=payload,
            status=ReminderStatus.PENDING.value if matches else ReminderStatus.SKIPPED.value,
            last_error=None if matches else "no member company matched",
            created_by=actor,
        )
        session.add(outbox)
        session.flush()

    session.commit()

    if outbox is not None and outbox.status == ReminderStatus.PENDING:
        dispatch_reminder(session, outbox, reminder, actor_id=actor)

    return ApproveOutcome(
        item=item,
        approval=approval,
        briefing_week_start=candidate.week_start,
        reminder_status=outbox.status if outbox is not None else None,
        reminder_outbox_id=outbox.id if outbox is not None else None,
    )


def reject_item(
    session: Session, principal: Principal, item_id: uuid.UUID, comment: str
) -> IntelItem:
    """Supervisor rejects with a mandatory comment; item returns to in_check."""
    actor = _require_actor(principal)
    _require_supervisor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    destination = _transition(item, "reject")

    cleaned = (comment or "").strip()
    if not cleaned:
        raise RejectCommentRequiredError("a reject comment is required")

    from_status = item.status
    item.status = destination.value
    item.review_comment = cleaned
    approval = _record_decision(
        session, item, ApprovalAction.REJECT, from_status, destination.value, actor,
        comment=cleaned,
    )
    _audit(
        session, item, "reject", actor,
        {
            "from_status": from_status,
            "to_status": destination.value,
            "approval_id": str(approval.id),
            "comment": cleaned,
        },
    )
    session.commit()
    return item


def withdraw_item(session: Session, principal: Principal, item_id: uuid.UUID) -> IntelItem:
    """Withdraw an approved/published item to in_check for rework.

    Unlocks summary/conditions, removes the item from active briefing candidate
    pools and skips undispatched reminders.
    """
    actor = _require_actor(principal)
    _require_supervisor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    destination = _transition(item, "withdraw")
    from_status = item.status
    now = _now()
    item.status = destination.value
    item.approved_by = None
    item.approved_at = None
    item.published_at = None
    candidates_removed = briefing.soft_delete_candidates(session, item, now)
    reminders_skipped = _skip_pending_reminders(session, item, "item withdrawn")
    approval = _record_decision(
        session, item, ApprovalAction.WITHDRAW, from_status, destination.value, actor
    )
    _audit(
        session, item, "withdraw", actor,
        {
            "from_status": from_status,
            "to_status": destination.value,
            "approval_id": str(approval.id),
            "candidates_removed": candidates_removed,
            "reminders_skipped": reminders_skipped,
        },
    )
    session.commit()
    return item


def publish_item(session: Session, principal: Principal, item_id: uuid.UUID) -> IntelItem:
    """Mark an approved item as compiled into a briefing and published."""
    actor = _require_actor(principal)
    _require_supervisor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    destination = _transition(item, "publish")
    from_status = item.status
    item.status = destination.value
    item.published_at = _now()
    _audit(
        session, item, "publish", actor,
        {"from_status": from_status, "to_status": destination.value},
    )
    session.commit()
    return item


def expire_item(session: Session, principal: Principal, item_id: uuid.UUID) -> IntelItem:
    """Take an item offline (any non-terminal status → expired)."""
    actor = _require_actor(principal)
    _require_supervisor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    destination = _transition(item, "expire")
    from_status = item.status
    now = _now()
    item.status = destination.value
    item.expired_at = now
    candidates_removed = briefing.soft_delete_candidates(session, item, now)
    reminders_skipped = _skip_pending_reminders(session, item, "item expired")
    _audit(
        session, item, "expire", actor,
        {
            "from_status": from_status,
            "to_status": destination.value,
            "candidates_removed": candidates_removed,
            "reminders_skipped": reminders_skipped,
        },
    )
    session.commit()
    return item


def patch_item(
    session: Session,
    principal: Principal,
    item_id: uuid.UUID,
    changes: dict[str, Any],
) -> IntelItem:
    """Edit content fields.

    approved/published/expired → 409 (work-order lock, AC-4). Editing a
    ``checked`` item demotes it to ``in_check`` so changed content is always
    re-checked before approval (declared design decision, README §4).
    """
    actor = _require_actor(principal)
    item = _get_item(session, principal, item_id, lock=True)
    if item.status in (ItemStatus.APPROVED, ItemStatus.PUBLISHED, ItemStatus.EXPIRED):
        raise LockedContentError(
            "summary and match conditions are locked after approval; "
            "withdraw the item to in_check before editing",
            detail={"current_status": item.status, "fields": sorted(changes)},
        )
    before = {field: getattr(item, field) for field in changes}
    for field, value in changes.items():
        setattr(item, field, value)
    demoted = item.status == ItemStatus.CHECKED
    if demoted:
        item.status = ItemStatus.IN_CHECK.value
    _audit(
        session, item, "update", actor,
        {
            "fields": sorted(changes),
            "before": before,
            "after": changes,
            "status_reset_to_in_check": demoted,
        },
    )
    session.commit()
    return item


# ---------------------------------------------------------------------------
# Reminder outbox dispatch (post-commit)
# ---------------------------------------------------------------------------


def dispatch_reminder(
    session: Session,
    outbox: IntelReminderOutbox,
    reminder: ReminderService,
    *,
    actor_id: uuid.UUID | None = None,
) -> IntelReminderOutbox:
    outbox.attempts += 1
    try:
        result = reminder.send_daily_reminder(outbox.payload)
    except Exception as exc:  # defensive: a broken client must not break approvals
        result = ReminderDispatchResult(False, f"reminder client error: {exc}")
    now = _now()
    if result.ok:
        outbox.status = ReminderStatus.SENT.value
        outbox.dispatched_at = now
        outbox.last_error = None
    else:
        outbox.status = ReminderStatus.FAILED.value
        outbox.last_error = result.detail
    item = session.get(IntelItem, outbox.item_id)
    if item is not None:
        _audit(
            session, item, "reminder_dispatch", actor_id,
            {
                "outbox_id": str(outbox.id),
                "ok": result.ok,
                "detail": result.detail,
                "attempts": outbox.attempts,
            },
        )
    session.commit()
    return outbox