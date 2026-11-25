"""AC-3: reject without a comment → 422; a valid reject returns the item to
in_check and keeps the comment."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import IntelApproval
from tests.factories import headers, make_item


@pytest.mark.parametrize("body", [None, {}, {"comment": ""}, {"comment": "   "}, {"comment": None}])
def test_reject_without_comment_422(client, session, body):
    item = make_item(session, status="checked")

    kwargs = {"headers": headers()}
    if body is not None:
        kwargs["json"] = body
    response = client.post(f"/api/intel/items/{item.id}/reject", **kwargs)

    assert response.status_code == 422
    session.expire_all()
    assert item.status == "checked"


def test_reject_with_comment_returns_to_in_check_and_keeps_it(client, session):
    item = make_item(session, status="checked")
    comment = "来源可信度不足，请补充原文佐证后重新提交。"

    response = client.post(
        f"/api/intel/items/{item.id}/reject", headers=headers(), json={"comment": comment}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "in_check"
    assert payload["review_comment"] == comment

    approval = session.scalar(select(IntelApproval).where(IntelApproval.item_id == item.id))
    assert approval is not None
    assert approval.action == "reject"
    assert approval.from_status == "checked"
    assert approval.to_status == "in_check"
    assert approval.comment == comment


def test_comment_survives_resubmission(client, session):
    item = make_item(session, status="checked")
    comment = "请核对申报截止日期。"
    client.post(f"/api/intel/items/{item.id}/reject", headers=headers(), json={"comment": comment})

    from tests.factories import STAFF_USER

    resubmit = client.post(
        f"/api/intel/items/{item.id}/submit", headers=headers(user=STAFF_USER, role="staff")
    )

    assert resubmit.status_code == 200
    assert resubmit.json()["status"] == "checked"
    assert resubmit.json()["review_comment"] == comment


def test_reject_comment_is_trimmed(client, session):
    item = make_item(session, status="checked")

    response = client.post(
        f"/api/intel/items/{item.id}/reject",
        headers=headers(),
        json={"comment": "  意见两侧空白应被去除  "},
    )

    assert response.status_code == 200
    assert response.json()["review_comment"] == "意见两侧空白应被去除"