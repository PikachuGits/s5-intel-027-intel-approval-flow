"""``intel_audit_logs`` — append-only audit trail for every lifecycle event."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import BusinessTable


class IntelAuditLog(BusinessTable):
    __tablename__ = "intel_audit_logs"

    entity_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'intel_item'")
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        Index("ix_intel_audit_logs_org_entity_created", "org_id", "entity_id", "created_at"),
    )