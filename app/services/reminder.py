"""Same-day reminder dispatch (reminder service is a sibling work order).

STUB NOTICE (integration point)
-------------------------------
``StubReminderService`` performs no network call; it records payloads so tests
and the demo can assert what would be sent. Production replaces
``app.api.deps.get_reminder`` with an HTTP client for the reminder work order
(base URL from ``REMINDER_SERVICE_URL``); the outbox contract stays unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ReminderDispatchResult:
    ok: bool
    detail: str = ""


class ReminderService(Protocol):
    def send_daily_reminder(self, payload: dict[str, Any]) -> ReminderDispatchResult: ...


@dataclass
class StubReminderService:
    """Deterministic test double; set ``fail=True`` to simulate an outage."""

    fail: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)

    def send_daily_reminder(self, payload: dict[str, Any]) -> ReminderDispatchResult:
        self.calls.append(payload)
        if self.fail:
            return ReminderDispatchResult(False, "stub: reminder service unavailable")
        return ReminderDispatchResult(True, "stub: accepted")