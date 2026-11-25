"""Withdraw: approved/published → in_check, unlock content, clean up pools."""
from __future__ import annotations

from sqlalchemy import select

from app.models import IntelApproval, IntelAuditLog, IntelBriefingCandidate, IntelReminderOutbox
from tests.factories import STAFF_USER, headers, make_item, make_pending_reminder


def test_withdraw_approved_resets_and_cleans(client, session):
    item = make_item(session, status="checked", relevance="high_relevance",
                     match_conditions={"keywords": ["测试"]})
    assert client.post(f"/api/intel/items/{item.id}/approve", headers=headers()).status_code == 200
    pending = make_pending_reminder(session, item)

    response = client.post(f"/api/intel/items/{item.id}/withdraw", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_check"
    assert body["approved_by"] is None
    assert body["approved_at"] is None

    candidate = session.scalar(
        select(IntelBriefingCandidate).where(IntelBriefingCandidate.item_id == item.id)
    )
    assert candidate.deleted_at is not None
    session.expire_all()
    assert pending.status == "skipped"

    actions = [
        row.action
        for row in session.scalars(
            select(IntelApproval).where(IntelApproval.item_id == item.id)
        ).all()
    ]
    assert actions == ["approve", "withdraw"]
    audit = session.scalar(
        select(IntelAuditLog).where(
            IntelAuditLog.entity_id == item.id, IntelAuditLog.action == "withdraw"
        )
    )
    assert audit.detail["candidates_removed"] == 1
    assert audit.detail["reminders_skipped"] == 1


def test_withdraw_published_clears_published_at(client, session):
    item = make_item(session, status="published")

    response = client.post(f"/api/intel/items/{item.id}/withdraw", headers=headers())

    assert response.status_code == 200
    assert response.json()["status"] == "in_check"
    assert response.json()["published_at"] is None


def test_withdrawn_item_can_be_reworked_and_reapproved(client, session):
    item = make_item(session, status="approved")
    assert client.post(f"/api/intel/items/{item.id}/withdraw", headers=headers()).status_code == 200
    assert client.patch(
        f"/api/intel/items/{item.id}", headers=headers(), json={"summary": "重新核对后的摘要"}
    ).status_code == 200
    assert client.post(
        f"/api/intel/items/{item.id}/submit", headers=headers(user=STAFF_USER, role="staff")
    ).status_code == 200
    assert client.post(f"/api/intel/items/{item.id}/approve", headers=headers()).status_code == 200


def test_expire_cleans_pools_too(client, session):
    item = make_item(session, status="checked", relevance="high_relevance",
                     match_conditions={"keywords": ["测试"]})
    assert client.post(f"/api/intel/items/{item.id}/approve", headers=headers()).status_code == 200
    pending = make_pending_reminder(session, item)

    response = client.post(f"/api/intel/items/{item.id}/expire", headers=headers())

    assert response.status_code == 200
    session.expire_all()
    assert pending.status == "skipped"
    candidate = session.scalar(
        select(IntelBriefingCandidate).where(IntelBriefingCandidate.item_id == item.id)
    )
    assert candidate.deleted_at is not None