"""``intel_briefing_candidates`` — items approved into a given week's briefing pool.

Briefing compilation/publishing itself is a sibling work order; this table is
the hand-off contract. ``week_start`` is the Monday of the approval week in
``APP_TIMEZONE``.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import BusinessTable


class IntelBriefingCandidate(BusinessTable):
    __tablename__ = "intel_briefing_candidates"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intel_items.id", ondelete="RESTRICT"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index(
            "uq_intel_briefing_candidates_org_item_week",
            "org_id",
            "item_id",
            "week_start",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_intel_briefing_candidates_org_week", "org_id", "week_start"),
    )