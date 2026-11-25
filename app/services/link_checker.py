"""Original-link recheck executed automatically before every approval.

STUB NOTICE (integration point)
-------------------------------
``HttpLinkChecker`` is the production implementation: it only ever requests the
item's own ``source_url`` using the Python standard library (no third-party SDK,
no data sent to any other party). Tests inject ``StubLinkChecker`` through the
FastAPI dependency ``app.api.deps.get_link_checker`` so the suite never touches
the network.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LinkCheckResult:
    ok: bool
    http_status: int | None = None
    detail: str = ""

    def as_dict(self) -> dict:
        return {"ok": self.ok, "http_status": self.http_status, "detail": self.detail}


class LinkChecker(Protocol):
    def check(self, url: str) -> LinkCheckResult: ...


class HttpLinkChecker:
    """HEAD the source URL (GET fallback when HEAD is rejected); 2xx/3xx = ok."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def _request(self, url: str, method: str) -> LinkCheckResult:
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": "intel-link-recheck/1.0"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            status = response.status
            return LinkCheckResult(ok=200 <= status < 400, http_status=status, detail="reachable")

    def check(self, url: str) -> LinkCheckResult:
        try:
            return self._request(url, "HEAD")
        except urllib.error.HTTPError as exc:
            if exc.code in (405, 501):
                try:
                    return self._request(url, "GET")
                except urllib.error.HTTPError as get_exc:
                    return LinkCheckResult(False, get_exc.code, f"HTTP {get_exc.code}")
                except (urllib.error.URLError, TimeoutError, OSError) as get_exc:
                    return LinkCheckResult(False, None, f"unreachable: {get_exc}")
            return LinkCheckResult(False, exc.code, f"HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return LinkCheckResult(False, None, f"unreachable: {exc}")


@dataclass
class StubLinkChecker:
    """Deterministic test double; records every call."""

    ok: bool = True
    http_status: int | None = 200
    detail: str = "stub"
    calls: list[str] = field(default_factory=list)

    def check(self, url: str) -> LinkCheckResult:
        self.calls.append(url)
        return LinkCheckResult(self.ok, self.http_status, self.detail)