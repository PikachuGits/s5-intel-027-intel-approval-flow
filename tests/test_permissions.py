"""S2-IAM stub: supervisor-only approval, actor identity, org/site isolation."""
from __future__ import annotations

import uuid

import pytest
from tests.factories import (
    ORG_B,
    SITE_A1,
    SITE_A2,
    SITE_B1,
    STAFF_USER,
    headers,
    make_item,
)


def test_missing_org_header_401(client, session):
    item = make_item(session)
    response = client.get(f"/api/intel/items/{item.id}")
    assert response.status_code == 401


def test_invalid_org_uuid_400(client, session):
    response = client.get("/api/intel/approvals", headers={"X-Org-Id": "not-a-uuid"})
    assert response.status_code == 400


def test_invalid_role_400(client, session):
    item = make_item(session, status="checked")
    response = client.post(
        f"/api/intel/items/{item.id}/approve", headers=headers(role="admin")
    )
    assert response.status_code == 400


@pytest.mark.parametrize("action", ["approve", "reject", "withdraw", "publish", "expire"])
def test_staff_cannot_perform_supervisor_actions(client, session, action):
    status = {"approve": "checked", "reject": "checked", "withdraw": "approved",
              "publish": "approved", "expire": "checked"}[action]
    item = make_item(session, status=status)
    kwargs = {"headers": headers(user=STAFF_USER, role="staff")}
    if action == "reject":
        kwargs["json"] = {"comment": "员工尝试驳回"}
    response = client.post(f"/api/intel/items/{item.id}/{action}", **kwargs)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_role"


def test_staff_cannot_list_approvals(client, session):
    response = client.get("/api/intel/approvals", headers=headers(user=STAFF_USER, role="staff"))
    assert response.status_code == 403


def test_staff_can_submit_and_patch(client, session):
    item = make_item(session, status="in_check")
    assert client.post(
        f"/api/intel/items/{item.id}/submit", headers=headers(user=STAFF_USER, role="staff")
    ).status_code == 200
    assert client.patch(
        f"/api/intel/items/{item.id}",
        headers=headers(user=STAFF_USER, role="staff"),
        json={"summary": "员工修改"},
    ).status_code == 200


@pytest.mark.parametrize("action", ["submit", "approve"])
def test_mutations_require_actor_identity(client, session, action):
    item = make_item(session, status="in_check" if action == "submit" else "checked")
    response = client.post(
        f"/api/intel/items/{item.id}/{action}", headers=headers(user=None)
    )
    assert response.status_code == 401
    assert response.json()["code"] == "missing_actor"


def test_cross_org_item_is_404(client, session):
    item = make_item(session, org_id=ORG_B, site_id=SITE_B1, status="checked")
    assert client.get(f"/api/intel/items/{item.id}", headers=headers()).status_code == 404
    assert client.post(
        f"/api/intel/items/{item.id}/approve", headers=headers()
    ).status_code == 404


def test_out_of_scope_site_is_404(client, session):
    item = make_item(session, site_id=SITE_A1, status="checked")
    response = client.post(
        f"/api/intel/items/{item.id}/approve", headers=headers(sites=[SITE_A2])
    )
    assert response.status_code == 404


def test_soft_deleted_item_is_404(client, session):
    from datetime import datetime, timezone

    item = make_item(session)
    item.deleted_at = datetime.now(timezone.utc)
    session.commit()
    assert client.get(f"/api/intel/items/{item.id}", headers=headers()).status_code == 404


def test_unknown_item_404(client, session):
    assert client.get(
        f"/api/intel/items/{uuid.uuid4()}", headers=headers()
    ).status_code == 404