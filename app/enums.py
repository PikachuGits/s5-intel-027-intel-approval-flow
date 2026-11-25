"""Enum values fixed by the work order.

The same literal sets are repeated in the Alembic migration because migrations
must not import application modules; ``tests/test_constraints.py`` asserts that
the database rejects values outside these sets.
"""

from __future__ import annotations

from enum import StrEnum


class ItemStatus(StrEnum):
    """Lifecycle of an intel item (work-order state machine)."""

    IN_CHECK = "in_check"
    CHECKED = "checked"
    APPROVED = "approved"
    PUBLISHED = "published"
    EXPIRED = "expired"


class Relevance(StrEnum):
    """Relevance grade assigned during checking.

    Only ``high_relevance`` items generate same-day member reminders on approval.
    """

    HIGH = "high_relevance"
    MEDIUM = "medium_relevance"
    LOW = "low_relevance"


class ApprovalAction(StrEnum):
    """Decisions recorded in ``intel_approvals``.

    ``submit`` / ``publish`` / ``expire`` are lifecycle events, not approval
    decisions; they are written to ``intel_audit_logs`` only.
    """

    APPROVE = "approve"
    REJECT = "reject"
    WITHDRAW = "withdraw"


class ReminderStatus(StrEnum):
    """Dispatch state of a same-day reminder outbox row."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class Role(StrEnum):
    """S2-IAM roles relevant to this work order (stub values)."""

    SUPERVISOR = "supervisor"
    STAFF = "staff"


ITEM_STATUSES = tuple(item.value for item in ItemStatus)
RELEVANCES = tuple(item.value for item in Relevance)
APPROVAL_ACTIONS = tuple(item.value for item in ApprovalAction)
REMINDER_STATUSES = tuple(item.value for item in ReminderStatus)
ROLES = tuple(item.value for item in Role)

#: Content fields locked once an item reaches ``approved`` (work-order rule:
#: "approved 后摘要与条件锁定"). ``title`` and ``relevance`` are locked together
#: with them so approved/published content cannot be changed through a side door;
#: this conservative extension is declared in the README.
LOCKED_PATCH_FIELDS = ("title", "summary", "match_conditions", "relevance")