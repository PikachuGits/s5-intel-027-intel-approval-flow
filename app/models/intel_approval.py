"""``intel_approvals`` — one row per supervisor decision (approve/reject/withdraw)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import BusinessTable


class IntelApproval(BusinessTable):
    __tablename__ = "intel_approvals"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intel_items.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    link_recheck_ok: Mapped[bool | None] = mapped_column(nullable=True)
    link_recheck_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action IN ('approve', 'reject', 'withdraw')",
            name="ck_intel_approvals_action",
        ),
        CheckConstraint(
            "action <> 'reject' OR (comment IS NOT NULL AND length(btrim(comment)) > 0)",
            name="ck_intel_approvals_reject_requires_comment",
        ),
        Index("ix_intel_approvals_org_item_created", "org_id", "item_id", "created_at"),
    )