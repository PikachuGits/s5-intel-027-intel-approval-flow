"""Member-company matching for approved intel items.

STUB NOTICE (integration point)
-------------------------------
Production matching against the member CRM (~100 member companies) is a sibling
work order. ``StubMemberMatcher`` derives deterministic *fictional* company UUIDs
from the item's ``match_conditions`` so the reminder path is fully testable
without real enterprise data. Replace ``app.api.deps.get_matcher`` to integrate.

Stub semantics: empty conditions → no matches; otherwise 1–3 deterministic
UUIDv5 values derived from the conditions JSON and the org id.
"""
from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models import IntelItem

_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


class MemberMatcher(Protocol):
    def match(self, item: "IntelItem") -> list[uuid.UUID]: ...


class StubMemberMatcher:
    def match(self, item: "IntelItem") -> list[uuid.UUID]:
        conditions = item.match_conditions or {}
        if not conditions:
            return []
        digest = uuid.uuid5(
            _NAMESPACE, json.dumps(conditions, sort_keys=True, ensure_ascii=False) + str(item.org_id)
        ).bytes
        count = 1 + digest[0] % 3
        return [
            uuid.uuid5(_NAMESPACE, f"{digest.hex()}:{index}")
            for index in range(count)
        ]