#!/usr/bin/env python3
"""Seed fictional intel items for local demo / evidence.

All identities, titles, summaries and URLs are fictional (example.invalid).
Deterministic with --seed. Only touches rows created by this script's org id.

Usage:
    DATABASE_URL=... .venv/bin/python scripts/seed_fictional_items.py --seed 42
"""
from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import (  # noqa: E402
    IntelApproval,
    IntelAuditLog,
    IntelBriefingCandidate,
    IntelItem,
    IntelReminderOutbox,
)

ORG = uuid.UUID("a0000000-0000-4000-8000-000000000001")
SITE = uuid.UUID("a0000000-0000-4000-8000-0000000000a1")
STAFF = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
SUPERVISOR = uuid.UUID("00000000-0000-4000-8000-000000000051")

TOPICS = ["产业扶持申报", "展会排期", "园区租金补贴", "技改专项", "人才落户细则"]
STATUSES = ["in_check", "checked", "checked", "approved", "published", "expired"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=12)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        for model in (
            IntelReminderOutbox, IntelBriefingCandidate, IntelAuditLog, IntelApproval, IntelItem
        ):
            session.execute(delete(model).where(model.org_id == ORG))

        created = 0
        for index in range(args.count):
            status = STATUSES[index % len(STATUSES)]
            relevance = rng.choice(["high_relevance", "medium_relevance", "low_relevance"])
            item = IntelItem(
                org_id=ORG,
                site_id=SITE,
                title=f"虚构情报 {index + 1}：{rng.choice(TOPICS)}动态（测试数据）",
                summary="虚构摘要，仅用于本地演示与验收复测，不含任何真实企业信息。",
                source_url=f"https://example.invalid/intel/fictional-{args.seed}-{index}",
                relevance=relevance,
                match_conditions={"keywords": [rng.choice(TOPICS)]} if relevance == "high_relevance" else {},
                status=status,
                created_by=STAFF,
            )
            if status in ("checked", "approved", "published"):
                item.checked_by = STAFF
                item.checked_at = now
            if status in ("approved", "published"):
                item.approved_by = SUPERVISOR
                item.approved_at = now
            if status == "published":
                item.published_at = now
            if status == "expired":
                item.expired_at = now
            session.add(item)
            session.flush()  # assign item.id before referencing it below
            if status in ("approved", "published"):
                session.add(
                    IntelApproval(
                        org_id=ORG, site_id=SITE, item_id=item.id, action="approve",
                        from_status="checked", to_status="approved", decided_by=SUPERVISOR,
                        link_recheck_ok=True,
                        link_recheck_detail={"ok": True, "http_status": 200, "detail": "seed"},
                        created_by=SUPERVISOR,
                    )
                )
            created += 1

    print(f"seeded {created} fictional items into org {ORG} (seed={args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())