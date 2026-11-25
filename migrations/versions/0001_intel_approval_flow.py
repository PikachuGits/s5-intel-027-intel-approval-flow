"""intel approval flow tables

Revision ID: 0001_intel_approval_flow
Revises:
Create Date: 2026-11-25 21:00:00

Tables: intel_items, intel_approvals, intel_audit_logs,
intel_briefing_candidates, intel_reminder_outbox.

Enum literal sets are repeated here on purpose: migrations must not import
application modules. tests/test_constraints.py guards the sets at the DB layer.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_intel_approval_flow"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "intel_items",
        *_common_columns(),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "relevance",
            sa.String(length=20),
            server_default=sa.text("'medium_relevance'"),
            nullable=False,
        ),
        sa.Column(
            "match_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'in_check'"),
            nullable=False,
        ),
        sa.Column("checked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_intel_items"),
        sa.CheckConstraint(
            "status IN ('in_check', 'checked', 'approved', 'published', 'expired')",
            name="ck_intel_items_status",
        ),
        sa.CheckConstraint(
            "relevance IN ('high_relevance', 'medium_relevance', 'low_relevance')",
            name="ck_intel_items_relevance",
        ),
        sa.CheckConstraint(
            "status <> 'checked' OR checked_by IS NOT NULL",
            name="ck_intel_items_checked_requires_checker",
        ),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'published') OR approved_at IS NOT NULL",
            name="ck_intel_items_approved_requires_timestamp",
        ),
    )
    op.create_index("ix_intel_items_org_status", "intel_items", ["org_id", "status"])
    op.create_index(
        "ix_intel_items_org_site_status", "intel_items", ["org_id", "site_id", "status"]
    )

    op.create_table(
        "intel_approvals",
        *_common_columns(),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_recheck_ok", sa.Boolean(), nullable=True),
        sa.Column(
            "link_recheck_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.PrimaryKeyConstraint("id", name="pk_intel_approvals"),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["intel_items.id"],
            name="fk_intel_approvals_item_id_intel_items",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action IN ('approve', 'reject', 'withdraw')",
            name="ck_intel_approvals_action",
        ),
        sa.CheckConstraint(
            "action <> 'reject' OR (comment IS NOT NULL AND length(btrim(comment)) > 0)",
            name="ck_intel_approvals_reject_requires_comment",
        ),
    )
    op.create_index(
        "ix_intel_approvals_org_item_created",
        "intel_approvals",
        ["org_id", "item_id", "created_at"],
    )

    op.create_table(
        "intel_audit_logs",
        *_common_columns(),
        sa.Column(
            "entity_type",
            sa.String(length=32),
            server_default=sa.text("'intel_item'"),
            nullable=False,
        ),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_intel_audit_logs"),
    )
    op.create_index(
        "ix_intel_audit_logs_org_entity_created",
        "intel_audit_logs",
        ["org_id", "entity_id", "created_at"],
    )

    op.create_table(
        "intel_briefing_candidates",
        *_common_columns(),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_intel_briefing_candidates"),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["intel_items.id"],
            name="fk_intel_briefing_candidates_item_id_intel_items",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_intel_briefing_candidates_org_item_week",
        "intel_briefing_candidates",
        ["org_id", "item_id", "week_start"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_intel_briefing_candidates_org_week",
        "intel_briefing_candidates",
        ["org_id", "week_start"],
    )

    op.create_table(
        "intel_reminder_outbox",
        *_common_columns(),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remind_on", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_intel_reminder_outbox"),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["intel_items.id"],
            name="fk_intel_reminder_outbox_item_id_intel_items",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_intel_reminder_outbox_status",
        ),
    )
    op.create_index(
        "ix_intel_reminder_outbox_org_status", "intel_reminder_outbox", ["org_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_intel_reminder_outbox_org_status", table_name="intel_reminder_outbox")
    op.drop_table("intel_reminder_outbox")
    op.drop_index(
        "ix_intel_briefing_candidates_org_week", table_name="intel_briefing_candidates"
    )
    op.drop_index(
        "uq_intel_briefing_candidates_org_item_week", table_name="intel_briefing_candidates"
    )
    op.drop_table("intel_briefing_candidates")
    op.drop_index("ix_intel_audit_logs_org_entity_created", table_name="intel_audit_logs")
    op.drop_table("intel_audit_logs")
    op.drop_index("ix_intel_approvals_org_item_created", table_name="intel_approvals")
    op.drop_table("intel_approvals")
    op.drop_index("ix_intel_items_org_site_status", table_name="intel_items")
    op.drop_index("ix_intel_items_org_status", table_name="intel_items")
    op.drop_table("intel_items")