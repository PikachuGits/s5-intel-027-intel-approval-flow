"""Full action × status matrix: every legal transition succeeds, everything
else answers 409, and the API behaviour matches app.state_machine exactly."""
from __future__ import annotations

import pytest

from app.enums import ITEM_STATUSES
from app.state_machine import TRANSITIONS, legal_pairs
from tests.factories import STAFF_USER, headers, make_item

ACTIONS = ("submit", "approve", "reject", "withdraw", "publish", "expire")

_EXPECTED = {
    (t.action, src.value): t.to_status.value for t in TRANSITIONS for src in t.from_statuses
}


def _call(client, action, item_id):
    hdrs = headers(user=STAFF_USER, role="staff") if action == "submit" else headers()
    kwargs = {"headers": hdrs}
    if action == "reject":
        kwargs["json"] = {"comment": "矩阵测试驳回意见"}
    return client.post(f"/api/intel/items/{item_id}/{action}", **kwargs)


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("status", ITEM_STATUSES)
def test_transition_matrix(client, session, action, status):
    item = make_item(session, status=status)

    response = _call(client, action, item.id)

    expected = _EXPECTED.get((action, status))
    if expected is None:
        assert response.status_code == 409, (action, status, response.text)
        assert response.json()["code"] == "illegal_transition"
        session.expire_all()
        assert item.status == status
    else:
        assert response.status_code == 200, (action, status, response.text)
        body = response.json()
        new_status = body["item"]["status"] if action == "approve" else body["status"]
        assert new_status == expected


def test_expired_is_terminal(client, session):
    item = make_item(session, status="expired")
    for action in ACTIONS:
        response = _call(client, action, item.id)
        assert response.status_code == 409, action


def test_api_matrix_matches_state_machine_table(client, session):
    observed: set[tuple[str, str]] = set()
    for action in ACTIONS:
        for status in ITEM_STATUSES:
            item = make_item(session, status=status, title=f"{action}-{status}")
            response = _call(client, action, item.id)
            if response.status_code == 200:
                body = response.json()
                new_status = body["item"]["status"] if action == "approve" else body["status"]
                observed.add((status, new_status))
    assert observed == set(legal_pairs())


def test_full_happy_path(client, session):
    """in_check → checked → approved → published, then expire is refused."""
    item = make_item(session, status="in_check")

    assert client.post(
        f"/api/intel/items/{item.id}/submit", headers=headers(user=STAFF_USER, role="staff")
    ).status_code == 200
    assert client.post(f"/api/intel/items/{item.id}/approve", headers=headers()).status_code == 200
    assert client.post(f"/api/intel/items/{item.id}/publish", headers=headers()).status_code == 200

    session.expire_all()
    assert item.status == "published"
    assert item.published_at is not None


def test_any_non_terminal_status_can_expire(client, session):
    for status in ("in_check", "checked", "approved", "published"):
        item = make_item(session, status=status)
        response = client.post(f"/api/intel/items/{item.id}/expire", headers=headers())
        assert response.status_code == 200, status
        assert response.json()["status"] == "expired"