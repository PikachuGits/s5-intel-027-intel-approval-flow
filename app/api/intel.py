"""Intel approval routes (work-order scope)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import (
    LinkCheckerDep,
    MatcherDep,
    PrincipalDep,
    ReminderDep,
    SessionDep,
)
from app.schemas import (
    ApprovalListResponse,
    ApproveRequest,
    ApproveResponse,
    ApprovalOut,
    ItemOut,
    ItemPatch,
    ListStatusLiteral,
    RejectRequest,
    ReminderOut,
)
from app.services import approvals

router = APIRouter(prefix="/api/intel", tags=["intel-approvals"])


@router.get("/approvals", response_model=ApprovalListResponse)
def list_approvals(
    session: SessionDep,
    principal: PrincipalDep,
    status: ListStatusLiteral = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApprovalListResponse:
    total, rows = approvals.list_approvals(
        session, principal, status_filter=status, limit=limit, offset=offset
    )
    return ApprovalListResponse(
        status=status,
        total=total,
        limit=limit,
        offset=offset,
        items=[ItemOut.model_validate(row) for row in rows],
    )


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> ItemOut:
    return ItemOut.model_validate(approvals.get_item(session, principal, item_id))


@router.patch("/items/{item_id}", response_model=ItemOut)
def patch_item(
    item_id: uuid.UUID,
    body: ItemPatch,
    session: SessionDep,
    principal: PrincipalDep,
) -> ItemOut:
    changes = body.model_dump(exclude_unset=True)
    return ItemOut.model_validate(approvals.patch_item(session, principal, item_id, changes))


@router.post("/items/{item_id}/submit", response_model=ItemOut)
def submit_item(item_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> ItemOut:
    return ItemOut.model_validate(approvals.submit_item(session, principal, item_id))


@router.post("/items/{item_id}/approve", response_model=ApproveResponse)
def approve_item(
    item_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
    link_checker: LinkCheckerDep,
    matcher: MatcherDep,
    reminder: ReminderDep,
    body: ApproveRequest | None = None,
) -> ApproveResponse:
    outcome = approvals.approve_item(
        session,
        principal,
        item_id,
        link_checker=link_checker,
        matcher=matcher,
        reminder=reminder,
        comment=body.comment if body else None,
    )
    return ApproveResponse(
        item=ItemOut.model_validate(outcome.item),
        approval=ApprovalOut.model_validate(outcome.approval),
        briefing_week_start=outcome.briefing_week_start,
        reminder=(
            ReminderOut(outbox_id=outcome.reminder_outbox_id, status=outcome.reminder_status)
            if outcome.reminder_outbox_id is not None and outcome.reminder_status is not None
            else None
        ),
    )


@router.post("/items/{item_id}/reject", response_model=ItemOut)
def reject_item(
    item_id: uuid.UUID,
    body: RejectRequest,
    session: SessionDep,
    principal: PrincipalDep,
) -> ItemOut:
    return ItemOut.model_validate(approvals.reject_item(session, principal, item_id, body.comment))


@router.post("/items/{item_id}/withdraw", response_model=ItemOut)
def withdraw_item(item_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> ItemOut:
    return ItemOut.model_validate(approvals.withdraw_item(session, principal, item_id))


@router.post("/items/{item_id}/publish", response_model=ItemOut)
def publish_item(item_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> ItemOut:
    return ItemOut.model_validate(approvals.publish_item(session, principal, item_id))


@router.post("/items/{item_id}/expire", response_model=ItemOut)
def expire_item(item_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> ItemOut:
    return ItemOut.model_validate(approvals.expire_item(session, principal, item_id))