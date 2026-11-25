"""AC-1: approving an item that is still in_check returns 409."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import IntelApproval
from tests.factories import headers, make_item


def test_approve_in_check_returns_409(client, session):
    item = make_item(session, status="in_check")

    response = client.post(f"/api/intel/items/{item.id}/approve", headers=headers())

    assert response.status_code == 409
    assert response.json()["code"] == "illegal_transition"
    session.expire_all()
    assert item.status == "in_check"
    assert session.scalar(select(func.count()).select_from(IntelApproval)) == 0


def test_approve_in_check_with_body_also_409(client, session):
    item = make_item(session, status="in_check")

    response = client.post(
        f"/api/intel/items/{item.id}/approve",
        headers=headers(),
        json={"comment": "同意"},
    )

    assert response.status_code == 409


def test_double_approve_second_call_409(client, session):
    """Row lock + status re-check make a repeated approve fail cleanly."""
    item = make_item(session, status="checked")

    first = client.post(f"/api/intel/items/{item.id}/approve", headers=headers())
    second = client.post(f"/api/intel/items/{item.id}/approve", headers=headers())

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "illegal_transition"