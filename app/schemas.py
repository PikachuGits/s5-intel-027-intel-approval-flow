"""Pydantic request/response schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

RelevanceLiteral = Literal["high_relevance", "medium_relevance", "low_relevance"]
ListStatusLiteral = Literal["pending", "approved", "rejected", "expired"]

#: Trimmed, non-empty opinion text (whitespace-only rejects fail with 422).
CommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
OptionalCommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000)
]


class RejectRequest(BaseModel):
    """Reject body. Missing / empty / whitespace-only comment → 422 (AC-3)."""

    comment: CommentText


class ApproveRequest(BaseModel):
    """Optional approve body; an opinion may be recorded but is not required."""

    comment: OptionalCommentText | None = None


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, min_length=1)
    match_conditions: dict[str, Any] | None = None
    relevance: RelevanceLiteral | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "ItemPatch":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("at least one field must be provided")
        return self


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    site_id: uuid.UUID
    title: str
    summary: str
    source_url: str
    relevance: str
    match_conditions: dict[str, Any]
    status: str
    checked_by: uuid.UUID | None
    checked_at: datetime | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    published_at: datetime | None
    expired_at: datetime | None
    review_comment: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    action: str
    from_status: str
    to_status: str
    comment: str | None
    decided_by: uuid.UUID
    link_recheck_ok: bool | None
    created_at: datetime


class ReminderOut(BaseModel):
    outbox_id: uuid.UUID
    status: str


class ApproveResponse(BaseModel):
    item: ItemOut
    approval: ApprovalOut
    briefing_week_start: date
    reminder: ReminderOut | None


class ApprovalListResponse(BaseModel):
    status: str
    total: int
    limit: int
    offset: int
    items: list[ItemOut]