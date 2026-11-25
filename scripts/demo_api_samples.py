#!/usr/bin/env python3
"""Capture live API samples (including AC error bodies) into evidence/api-samples.json.

Prereqs: migrations applied, fictional seed loaded, and the API running at
--base-url (default http://127.0.0.1:8027). The success-path demo item points
its source_url at the API's own /openapi.json so the *production* link recheck
(HttpLinkChecker) succeeds without any external network target.

Usage:
    DATABASE_URL=... .venv/bin/python scripts/demo_api_samples.py
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import session_scope  # noqa: E402
from app.models import IntelItem  # noqa: E402

ORG = uuid.UUID("a0000000-0000-4000-8000-000000000001")
SITE = uuid.UUID("a0000000-0000-4000-8000-0000000000a1")
STAFF = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
SUPERVISOR = uuid.UUID("00000000-0000-4000-8000-000000000051")
SECOND_SUPERVISOR = uuid.UUID("00000000-0000-4000-8000-000000000052")


def call(base: str, method: str, path: str, *, user=None, role="supervisor", body=None):
    headers = {"X-Org-Id": str(ORG), "X-User-Role": role}
    if user is not None:
        headers["X-User-Id"] = str(user)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8027")
    args = parser.parse_args()
    base = args.base_url
    samples: list[dict] = []

    def record(label, method, path, result, **kw):
        status, payload = result
        samples.append(
            {"label": label, "request": {"method": method, "path": path, **kw},
             "response_status": status, "response": payload}
        )
        print(f"{status}  {label}")

    # Demo item whose original link is the API's own openapi.json (local recheck target).
    with session_scope() as session:
        demo = IntelItem(
            org_id=ORG, site_id=SITE,
            title="虚构演示条目：本地复检目标",
            summary="虚构摘要（演示用，测试数据）。",
            source_url=f"{base}/openapi.json",
            relevance="high_relevance",
            match_conditions={"keywords": ["虚构产业"]},
            status="in_check", created_by=STAFF,
        )
        session.add(demo)
        session.flush()
        demo_id = demo.id

    record("待审批列表", "GET", "/api/intel/approvals?status=pending",
           call(base, "GET", "/api/intel/approvals?status=pending", user=SUPERVISOR))

    record("AC-1：in_check 直接 approve → 409", "POST", f"/api/intel/items/{demo_id}/approve",
           call(base, "POST", f"/api/intel/items/{demo_id}/approve", user=SUPERVISOR))

    record("员工提交核对（submit）", "POST", f"/api/intel/items/{demo_id}/submit",
           call(base, "POST", f"/api/intel/items/{demo_id}/submit", user=STAFF, role="staff"))

    record("主管通过（复检本地链接成功 + 提醒 outbox）", "POST", f"/api/intel/items/{demo_id}/approve",
           call(base, "POST", f"/api/intel/items/{demo_id}/approve", user=SECOND_SUPERVISOR))

    record("AC-4：approved 后改摘要 → 409", "PATCH", f"/api/intel/items/{demo_id}",
           call(base, "PATCH", f"/api/intel/items/{demo_id}", user=SUPERVISOR,
                body={"summary": "尝试修改已审批摘要"}), body={"summary": "尝试修改已审批摘要"})

    record("撤回到 in_check（withdraw）", "POST", f"/api/intel/items/{demo_id}/withdraw",
           call(base, "POST", f"/api/intel/items/{demo_id}/withdraw", user=SUPERVISOR))

    record("撤回后修改摘要成功", "PATCH", f"/api/intel/items/{demo_id}",
           call(base, "PATCH", f"/api/intel/items/{demo_id}", user=SUPERVISOR,
                body={"summary": "撤回后重新核对的虚构摘要"}), body={"summary": "撤回后重新核对的虚构摘要"})

    # AC-2: supervisor submits (checks) an item, then tries to approve it themselves.
    with session_scope() as session:
        own = IntelItem(
            org_id=ORG, site_id=SITE, title="虚构演示条目：四眼原则",
            summary="虚构摘要（演示用）。", source_url=f"{base}/openapi.json",
            status="in_check", created_by=SUPERVISOR,
        )
        session.add(own)
        session.flush()
        own_id = own.id
    call(base, "POST", f"/api/intel/items/{own_id}/submit", user=SUPERVISOR)
    record("AC-2：主管审批自己核对的条目 → 403", "POST", f"/api/intel/items/{own_id}/approve",
           call(base, "POST", f"/api/intel/items/{own_id}/approve", user=SUPERVISOR))

    # AC-3: reject without / with comment.
    record("AC-3：驳回未填意见 → 422", "POST", f"/api/intel/items/{own_id}/reject",
           call(base, "POST", f"/api/intel/items/{own_id}/reject", user=SUPERVISOR, body={}), body={})
    record("AC-3：带意见驳回 → 回到 in_check 并保留意见", "POST", f"/api/intel/items/{own_id}/reject",
           call(base, "POST", f"/api/intel/items/{own_id}/reject", user=SUPERVISOR,
                body={"comment": "请补充虚构原文佐证"}), body={"comment": "请补充虚构原文佐证"})

    # Production link recheck failure: a seeded item points at example.invalid.
    with session_scope() as session:
        from sqlalchemy import select

        unreachable = session.scalar(
            select(IntelItem).where(
                IntelItem.org_id == ORG, IntelItem.status == "checked",
                IntelItem.source_url.like("https://example.invalid%"),
            )
        )
        unreachable_id = unreachable.id if unreachable else None
    if unreachable_id is not None:
        record("生产复检失败：原文链接不可达 → 409", "POST", f"/api/intel/items/{unreachable_id}/approve",
               call(base, "POST", f"/api/intel/items/{unreachable_id}/approve", user=SECOND_SUPERVISOR))

    out = Path(__file__).resolve().parents[1] / "evidence" / "api-samples.json"
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(samples)} samples -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())