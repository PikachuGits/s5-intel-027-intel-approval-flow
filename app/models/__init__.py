"""Declarative base and model registry."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Base(DeclarativeBase):
    pass


class BusinessTable(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Abstract parent carrying the project's unified columns."""

    __abstract__ = True


from app.models.intel_approval import IntelApproval  # noqa: E402,F401
from app.models.intel_audit_log import IntelAuditLog  # noqa: E402,F401
from app.models.intel_briefing_candidate import IntelBriefingCandidate  # noqa: E402,F401
from app.models.intel_item import IntelItem  # noqa: E402,F401
from app.models.intel_reminder_outbox import IntelReminderOutbox  # noqa: E402,F401

__all__ = [
    "Base",
    "BusinessTable",
    "IntelItem",
    "IntelApproval",
    "IntelAuditLog",
    "IntelBriefingCandidate",
    "IntelReminderOutbox",
]