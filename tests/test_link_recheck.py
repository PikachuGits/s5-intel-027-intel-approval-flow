"""Automatic original-link recheck before approval: failure blocks approval."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import IntelApproval, IntelAuditLog
from tests.factories import headers, make_item


def test_failed_recheck_blocks_approval(client, session, link_stub):
    link_stub.ok = False
    link_stub.http_status = 404
    link_stub.detail = "HTTP 404"
    item = make_item(session, status="checked")

    response = client.post(f"/api/intel/items/{item.id}/approve", headers=headers())

    assert response.status_code == 409
    assert response.json()["code"] == "link_recheck_failed"
    assert link_stub.calls == [item.source_url]
    session.expire_all()
    assert item.status == "checked"
    assert session.scalar(select(func.count()).select_from(IntelApproval)) == 0
    blocked = session.scalar(
        select(IntelAuditLog).where(
            IntelAuditLog.entity_id == item.id, IntelAuditLog.action == "approve_blocked"
        )
    )
    assert blocked is not None
    assert blocked.detail["link_recheck"]["http_status"] == 404


def test_successful_recheck_is_recorded_on_decision(client, session, link_stub):
    item = make_item(session, status="checked")

    response = client.post(f"/api/intel/items/{item.id}/approve", headers=headers())

    assert response.status_code == 200
    assert link_stub.calls == [item.source_url]
    approval = response.json()["approval"]
    assert approval["link_recheck_ok"] is True
    row = session.scalar(select(IntelApproval).where(IntelApproval.item_id == item.id))
    assert row.link_recheck_ok is True
    assert row.link_recheck_detail["ok"] is True


def test_recheck_not_called_for_invalid_state(client, session, link_stub):
    item = make_item(session, status="in_check")

    response = client.post(f"/api/intel/items/{item.id}/approve", headers=headers())

    assert response.status_code == 409
    assert link_stub.calls == []


def test_recheck_failure_then_success_after_fix(client, session, link_stub):
    item = make_item(session, status="checked")
    link_stub.ok = False
    assert client.post(f"/api/intel/items/{item.id}/approve", headers=headers()).status_code == 409

    link_stub.ok = True
    link_stub.http_status = 200
    assert client.post(f"/api/intel/items/{item.id}/approve", headers=headers()).status_code == 200