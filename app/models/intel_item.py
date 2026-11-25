"""``intel_items`` — the minimal item contract this work order operates on.

Integration note (README §7): item ingestion / normalisation / dedup belongs to
sibling intel work orders. This table defines only the columns the approval
flow needs; the core team merges it with the sibling schema at integration.
``source_id`` / ``raw_page_id`` are loose UUID references (no cross-deliverable
foreign keys) pointing at S5-INTEL-001's ``intel_sources`` / ``intel_raw_pages``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import BusinessTable


class IntelItem(BusinessTable):
    __tablename__ = "intel_items"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    raw_page_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    relevance: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'medium_relevance'")
    )
    match_conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'in_check'")
    )

    checked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Latest reject comment, kept on the item so the rework loop always shows
    #: the supervisor's opinion. Full decision history lives in intel_approvals.
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_check', 'checked', 'approved', 'published', 'expired')",
            name="ck_intel_items_status",
        ),
        CheckConstraint(
            "relevance IN ('high_relevance', 'medium_relevance', 'low_relevance')",
            name="ck_intel_items_relevance",
        ),
        CheckConstraint(
            "status <> 'checked' OR checked_by IS NOT NULL",
            name="ck_intel_items_checked_requires_checker",
        ),
        CheckConstraint(
            "status NOT IN ('approved', 'published') OR approved_at IS NOT NULL",
            name="ck_intel_items_approved_requires_timestamp",
        ),
        Index("ix_intel_items_org_status", "org_id", "status"),
        Index("ix_intel_items_org_site_status", "org_id", "site_id", "status"),
    )