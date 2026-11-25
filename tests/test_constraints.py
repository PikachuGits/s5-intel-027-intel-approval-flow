"""Database-layer guards: enum CHECKs, reject-comment CHECK, unique candidate
pool, FK RESTRICT. These are the last line of defence behind the API."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    IntelApproval,
    IntelBriefingCandidate,
    IntelItem,
    IntelReminderOutbox,
)
from tests.factories import ORG_A, SITE_A1, STAFF_USER, make_item


def _expect_integrity_error(session, fn):
    with pytest.raises(IntegrityError):
        fn()
        session.flush()
    session.rollback()


def test_item_status_enum_guard(session):
    def insert():
        session.add(
            IntelItem(
                org_id=ORG_A, site_id=SITE_A1, title="t", summary="s",
                source_url="https://example.invalid/x", status="bogus",
            )
        )
    _expect_integrity_error(session, insert)


def test_item_relevance_enum_guard(session):
    def insert():
        session.add(
            IntelItem(
                org_id=ORG_A, site_id=SITE_A1, title="t", summary="s",
                source_url="https://example.invalid/x", relevance="bogus",
            )
        )
    _expect_integrity_error(session, insert)


def test_checked_requires_checker(session):
    def insert():
        session.add(
            IntelItem(
                org_id=ORG_A, site_id=SITE_A1, title="t", summary="s",
                source_url="https://example.invalid/x", status="checked", checked_by=None,
            )
        )
    _expect_integrity_error(session, insert)


def test_approved_requires_timestamp(session):
    def insert():
        session.add(
            IntelItem(
                org_id=ORG_A, site_id=SITE_A1, title="t", summary="s",
                source_url="https://example.invalid/x", status="approved",
                checked_by=STAFF_USER, approved_by=STAFF_USER, approved_at=None,
            )
        )
    _expect_integrity_error(session, insert)


def test_approval_action_enum_guard(session):
    item = make_item(session)

    def insert():
        session.add(
            IntelApproval(
                org_id=ORG_A, site_id=SITE_A1, item_id=item.id, action="publish",
                from_status="approved", to_status="published", decided_by=STAFF_USER,
            )
        )
    _expect_integrity_error(session, insert)


@pytest.mark.parametrize("comment", [None, "", "   "])
def test_reject_requires_comment_at_db_layer(session, comment):
    item = make_item(session)

    def insert():
        session.add(
            IntelApproval(
                org_id=ORG_A, site_id=SITE_A1, item_id=item.id, action="reject",
                from_status="checked", to_status="in_check", decided_by=STAFF_USER,
                comment=comment,
            )
        )
    _expect_integrity_error(session, insert)


def test_outbox_status_enum_guard(session):
    item = make_item(session)

    def insert():
        session.add(
            IntelReminderOutbox(
                org_id=ORG_A, site_id=SITE_A1, item_id=item.id,
                remind_on=date.today(), payload={}, status="bogus",
            )
        )
    _expect_integrity_error(session, insert)


def test_unique_active_candidate_per_week(session):
    item = make_item(session)
    week = date(2026, 11, 23)

    session.add(
        IntelBriefingCandidate(org_id=ORG_A, site_id=SITE_A1, item_id=item.id, week_start=week)
    )
    session.commit()

    def duplicate():
        session.add(
            IntelBriefingCandidate(
                org_id=ORG_A, site_id=SITE_A1, item_id=item.id, week_start=week
            )
        )
    _expect_integrity_error(session, duplicate)


def test_soft_deleted_candidate_frees_the_slot(session):
    item = make_item(session)
    week = date(2026, 11, 23)
    first = IntelBriefingCandidate(
        org_id=ORG_A, site_id=SITE_A1, item_id=item.id, week_start=week,
        deleted_at=datetime.now(timezone.utc),
    )
    session.add(first)
    session.commit()

    session.add(
        IntelBriefingCandidate(org_id=ORG_A, site_id=SITE_A1, item_id=item.id, week_start=week)
    )
    session.commit()  # must not raise


def test_item_hard_delete_restricted_while_referenced(session):
    item = make_item(session)
    session.add(
        IntelApproval(
            org_id=ORG_A, site_id=SITE_A1, item_id=item.id, action="approve",
            from_status="checked", to_status="approved", decided_by=STAFF_USER,
        )
    )
    session.commit()

    with pytest.raises(IntegrityError):
        session.delete(item)
        session.flush()
    session.rollback()