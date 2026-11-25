"""Approval side effects: intel_approvals + audit log + weekly briefing
candidate + same-day reminder for high_relevance matches (stub-first)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models import (
    IntelApproval,
    IntelAuditLog,
    IntelBriefingCandidate,
    IntelReminderOutbox,
)
from app.services.briefing import week_start
from tests.factories import headers, make_item


def _approve(client, item):
    return client.post(f"/api/intel/items/{item.id}/approve", headers=headers())


def test_approval_writes_decision_and_audit(client, session):
    item = make_item(session, status="checked")

    response = _approve(client, item)

    assert response.status_code == 200
    approvals = session.scalars(
        select(IntelApproval).where(IntelApproval.item_id == item.id)
    ).all()
    assert len(approvals) == 1
    assert approvals[0].action == "approve"
    audits = session.scalars(
        select(IntelAuditLog).where(
            IntelAuditLog.entity_id == item.id, IntelAuditLog.action == "approve"
        )
    ).all()
    assert len(audits) == 1
    assert audits[0].detail["approval_id"] == str(approvals[0].id)


def test_approval_adds_current_week_briefing_candidate(client, session):
    item = make_item(session, status="checked")

    response = _approve(client, item)

    assert response.status_code == 200
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    expected_week = week_start(today)
    assert response.json()["briefing_week_start"] == expected_week.isoformat()
    candidate = session.scalar(
        select(IntelBriefingCandidate).where(IntelBriefingCandidate.item_id == item.id)
    )
    assert candidate is not None
    assert candidate.week_start == expected_week
    assert candidate.deleted_at is None


def test_high_relevance_match_generates_same_day_reminder(client, session, reminder_stub):
    item = make_item(
        session,
        status="checked",
        relevance="high_relevance",
        match_conditions={"keywords": ["智能制造"], "regions": ["华北"]},
    )

    response = _approve(client, item)

    assert response.status_code == 200
    reminder = response.json()["reminder"]
    assert reminder is not None
    assert reminder["status"] == "sent"
    outbox = session.get(IntelReminderOutbox, reminder["outbox_id"])
    assert outbox.status == "sent"
    assert outbox.attempts == 1
    assert outbox.remind_on == datetime.now(ZoneInfo("Asia/Shanghai")).date()
    assert outbox.payload["matched_company_ids"], "stub matcher must produce fictional matches"
    assert len(reminder_stub.calls) == 1
    assert reminder_stub.calls[0]["item_id"] == str(item.id)


def test_medium_and_low_relevance_do_not_remind(client, session, reminder_stub):
    for relevance in ("medium_relevance", "low_relevance"):
        item = make_item(session, status="checked", relevance=relevance,
                         match_conditions={"keywords": ["测试"]})
        response = _approve(client, item)
        assert response.status_code == 200
        assert response.json()["reminder"] is None
    assert reminder_stub.calls == []
    assert session.scalar(select(func.count()).select_from(IntelReminderOutbox)) == 0


def test_high_relevance_without_matches_is_skipped(client, session, reminder_stub):
    item = make_item(session, status="checked", relevance="high_relevance", match_conditions={})

    response = _approve(client, item)

    assert response.status_code == 200
    reminder = response.json()["reminder"]
    assert reminder["status"] == "skipped"
    assert reminder_stub.calls == []
    outbox = session.get(IntelReminderOutbox, reminder["outbox_id"])
    assert outbox.last_error == "no member company matched"


def test_reminder_outage_does_not_roll_back_approval(client, session, reminder_stub):
    reminder_stub.fail = True
    item = make_item(
        session, status="checked", relevance="high_relevance",
        match_conditions={"keywords": ["测试"]},
    )

    response = _approve(client, item)

    assert response.status_code == 200
    assert response.json()["item"]["status"] == "approved"
    outbox = session.scalar(
        select(IntelReminderOutbox).where(IntelReminderOutbox.item_id == item.id)
    )
    assert outbox.status == "failed"
    assert outbox.attempts == 1
    assert outbox.last_error
    assert session.scalar(
        select(func.count()).select_from(IntelBriefingCandidate).where(
            IntelBriefingCandidate.item_id == item.id
        )
    ) == 1


def test_failed_reminder_can_be_retried(client, session, reminder_stub, monkeypatch):
    reminder_stub.fail = True
    item = make_item(
        session, status="checked", relevance="high_relevance",
        match_conditions={"keywords": ["测试"]},
    )
    assert _approve(client, item).status_code == 200

    from app.jobs import retry_reminders
    from app.services.reminder import StubReminderService

    working = StubReminderService(fail=False)
    monkeypatch.setattr(retry_reminders, "get_reminder", lambda: working)
    assert retry_reminders.main([]) == 0

    outbox = session.scalar(
        select(IntelReminderOutbox).where(IntelReminderOutbox.item_id == item.id)
    )
    session.expire_all()
    assert outbox.status == "sent"
    assert outbox.attempts == 2
    assert len(working.calls) == 1


def test_candidate_pool_idempotent_within_week(client, session):
    item = make_item(session, status="checked")
    assert _approve(client, item).status_code == 200
    assert client.post(f"/api/intel/items/{item.id}/withdraw", headers=headers()).status_code == 200
    from tests.factories import STAFF_USER

    assert client.post(
        f"/api/intel/items/{item.id}/submit", headers=headers(user=STAFF_USER, role="staff")
    ).status_code == 200
    assert _approve(client, item).status_code == 200

    active = session.scalars(
        select(IntelBriefingCandidate).where(
            IntelBriefingCandidate.item_id == item.id,
            IntelBriefingCandidate.deleted_at.is_(None),
        )
    ).all()
    assert len(active) == 1