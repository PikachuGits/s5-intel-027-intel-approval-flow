"""AC-2: a supervisor cannot approve an item they checked themselves (four-eyes)."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import IntelApproval
from tests.factories import SUPERVISOR_USER, headers, make_item


def test_supervisor_approving_own_checked_item_403(client, session):
    item = make_item(session, status="checked", checked_by=SUPERVISOR_USER)

    response = client.post(
        f"/api/intel/items/{item.id}/approve",
        headers=headers(user=SUPERVISOR_USER, role="supervisor"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "four_eyes_violation"
    session.expire_all()
    assert item.status == "checked"
    assert session.scalar(select(func.count()).select_from(IntelApproval)) == 0


def test_second_supervisor_approves_successfully(client, session):
    from tests.factories import OTHER_SUPERVISOR

    item = make_item(session, status="checked", checked_by=SUPERVISOR_USER)

    response = client.post(
        f"/api/intel/items/{item.id}/approve",
        headers=headers(user=OTHER_SUPERVISOR, role="supervisor"),
    )

    assert response.status_code == 200
    assert response.json()["item"]["status"] == "approved"


def test_four_eyes_checked_before_link_recheck(client, session, link_stub):
    """A four-eyes rejection must not burn a link recheck call."""
    item = make_item(session, status="checked", checked_by=SUPERVISOR_USER)

    response = client.post(
        f"/api/intel/items/{item.id}/approve",
        headers=headers(user=SUPERVISOR_USER, role="supervisor"),
    )

    assert response.status_code == 403
    assert link_stub.calls == []


def test_rejecting_own_item_is_allowed(client, session):
    """Four-eyes applies to approvals; sending one's own item back is harmless.

    Declared interpretation of "主管不能审批自己核对提交的条目" (README §4).
    """
    item = make_item(session, status="checked", checked_by=SUPERVISOR_USER)

    response = client.post(
        f"/api/intel/items/{item.id}/reject",
        headers=headers(user=SUPERVISOR_USER, role="supervisor"),
        json={"comment": "自查后退回补充材料"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_check"