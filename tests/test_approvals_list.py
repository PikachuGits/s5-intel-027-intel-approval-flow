"""GET /api/intel/approvals — supervisor worklist filters and pagination."""
from __future__ import annotations

from tests.factories import ORG_B, SITE_A1, SITE_A2, SITE_B1, headers, make_item


def test_pending_lists_only_checked_in_scope(client, session):
    pending = make_item(session, status="checked", title="待审批")
    make_item(session, status="in_check", title="核对中")
    make_item(session, status="approved", title="已通过")
    make_item(session, org_id=ORG_B, site_id=SITE_B1, status="checked", title="他司条目")

    response = client.get("/api/intel/approvals?status=pending", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(pending.id)]


def test_default_status_is_pending(client, session):
    make_item(session, status="checked")
    make_item(session, status="in_check")

    response = client.get("/api/intel/approvals", headers=headers())

    assert response.json()["total"] == 1


def test_rejected_filter_shows_rework_items_only(client, session):
    rejected = make_item(session, status="checked", title="被驳回")
    client.post(
        f"/api/intel/items/{rejected.id}/reject", headers=headers(), json={"comment": "退回"}
    )
    resubmitted = make_item(session, status="checked", title="驳回后重提")
    client.post(
        f"/api/intel/items/{resubmitted.id}/reject", headers=headers(), json={"comment": "退回"}
    )
    from tests.factories import STAFF_USER

    client.post(
        f"/api/intel/items/{resubmitted.id}/submit",
        headers=headers(user=STAFF_USER, role="staff"),
    )
    make_item(session, status="in_check", title="从未提交")

    response = client.get("/api/intel/approvals?status=rejected", headers=headers())

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(rejected.id)
    assert body["items"][0]["review_comment"] == "退回"


def test_approved_and_expired_filters(client, session):
    make_item(session, status="approved")
    make_item(session, status="expired")

    assert client.get(
        "/api/intel/approvals?status=approved", headers=headers()
    ).json()["total"] == 1
    assert client.get(
        "/api/intel/approvals?status=expired", headers=headers()
    ).json()["total"] == 1


def test_invalid_status_422(client, session):
    assert client.get(
        "/api/intel/approvals?status=bogus", headers=headers()
    ).status_code == 422


def test_pagination(client, session):
    for index in range(5):
        make_item(session, status="checked", title=f"条目{index}")

    page = client.get(
        "/api/intel/approvals?status=pending&limit=2&offset=2", headers=headers()
    ).json()

    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 2


def test_site_scope_filters_list(client, session):
    in_scope = make_item(session, site_id=SITE_A2, status="checked")
    make_item(session, site_id=SITE_A1, status="checked")

    body = client.get(
        "/api/intel/approvals?status=pending", headers=headers(sites=[SITE_A2])
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == str(in_scope.id)