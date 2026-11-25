"""``intel_reminder_outbox`` — durable same-day reminder dispatch queue.

The row is written in the same transaction as the approval, then dispatched
after commit. A reminder-service failure never rolls back an approval; the row
stays ``failed`` and can be retried via ``python -m app.jobs.retry_reminders``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import BusinessTable


class IntelReminderOutbox(BusinessTable):
    __tablename__ = "intel_reminder_outbox"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intel_items.id", ondelete="RESTRICT"), nullable=False
    )
    remind_on: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_intel_reminder_outbox_status",
        ),
        Index("ix_intel_reminder_outbox_org_status", "org_id", "status"),
    )