"""AC-4: after approval the summary (and match conditions) are locked; editing
requires a withdraw back to in_check."""
from __future__ import annotations

import pytest
from tests.factories import headers, make_item


@pytest.mark.parametrize("status", ["approved", "published", "expired"])
def test_patch_summary_locked_409(client, session, status):
    item = make_item(session, status=status)

    response = client.patch(
        f"/api/intel/items/{item.id}", headers=headers(), json={"summary": "改后的摘要"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "content_locked"
    session.expire_all()
    assert item.summary != "改后的摘要"


def test_patch_match_conditions_locked_409(client, session):
    item = make_item(session, status="approved", match_conditions={"keywords": ["原条件"]})

    response = client.patch(
        f"/api/intel/items/{item.id}",
        headers=headers(),
        json={"match_conditions": {"keywords": ["新条件"]}},
    )

    assert response.status_code == 409
    session.expire_all()
    assert item.match_conditions == {"keywords": ["原条件"]}


@pytest.mark.parametrize("field,value", [("title", "新标题"), ("relevance", "high_relevance")])
def test_other_content_fields_locked_too(client, session, field, value):
    """Declared conservative extension: title/relevance locked with the batch."""
    item = make_item(session, status="approved")

    response = client.patch(
        f"/api/intel/items/{item.id}", headers=headers(), json={field: value}
    )

    assert response.status_code == 409


def test_withdraw_unlocks_editing(client, session):
    item = make_item(session, status="approved")

    withdraw = client.post(f"/api/intel/items/{item.id}/withdraw", headers=headers())
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "in_check"

    patch = client.patch(
        f"/api/intel/items/{item.id}", headers=headers(), json={"summary": "撤回后重新核对的摘要"}
    )
    assert patch.status_code == 200
    assert patch.json()["summary"] == "撤回后重新核对的摘要"


def test_patch_in_check_allowed(client, session):
    item = make_item(session, status="in_check")

    response = client.patch(
        f"/api/intel/items/{item.id}", headers=headers(), json={"summary": "核对中的修改"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_check"


def test_patch_checked_demotes_to_in_check(client, session):
    """Design decision: changed content must be re-checked before approval."""
    item = make_item(session, status="checked")

    response = client.patch(
        f"/api/intel/items/{item.id}", headers=headers(), json={"summary": "提交后又改了内容"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_check"


def test_empty_patch_422(client, session):
    item = make_item(session, status="in_check")

    response = client.patch(f"/api/intel/items/{item.id}", headers=headers(), json={})

    assert response.status_code == 422