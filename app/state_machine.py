"""The work-order state machine, as data.

Legal transitions (everything else is an illegal transition → HTTP 409):

    in_check  --submit(staff)---------->  checked
    checked   --approve(supervisor)---->  approved     [four-eyes + link recheck]
    checked   --reject(supervisor)----->  in_check     [comment required]
    approved  --publish(supervisor)---->  published
    approved  --withdraw(supervisor)--->  in_check
    published --withdraw(supervisor)--->  in_check
    {in_check, checked, approved, published} --expire(supervisor)--> expired

``expired`` is terminal. Editing locked content on a ``checked`` item demotes
it back to ``in_check`` (see ``services/approvals.patch_item``); that demotion
is an edit side effect, not a lifecycle action.

The transition table is the single source of truth shared by the service
layer, the tests and ``docs/state-machine.md``.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.enums import ItemStatus


@dataclass(frozen=True)
class Transition:
    action: str
    from_statuses: frozenset[ItemStatus]
    to_status: ItemStatus
    actor: str  # "staff" (any authenticated member) or "supervisor"


TRANSITIONS: tuple[Transition, ...] = (
    Transition("submit", frozenset({ItemStatus.IN_CHECK}), ItemStatus.CHECKED, "staff"),
    Transition("approve", frozenset({ItemStatus.CHECKED}), ItemStatus.APPROVED, "supervisor"),
    Transition("reject", frozenset({ItemStatus.CHECKED}), ItemStatus.IN_CHECK, "supervisor"),
    Transition("publish", frozenset({ItemStatus.APPROVED}), ItemStatus.PUBLISHED, "supervisor"),
    Transition(
        "withdraw",
        frozenset({ItemStatus.APPROVED, ItemStatus.PUBLISHED}),
        ItemStatus.IN_CHECK,
        "supervisor",
    ),
    Transition(
        "expire",
        frozenset(
            {ItemStatus.IN_CHECK, ItemStatus.CHECKED, ItemStatus.APPROVED, ItemStatus.PUBLISHED}
        ),
        ItemStatus.EXPIRED,
        "supervisor",
    ),
)

_BY_ACTION = {t.action: t for t in TRANSITIONS}


class IllegalTransitionError(Exception):
    """Raised when an action is applied to a status it cannot leave."""

    def __init__(self, action: str, current: str) -> None:
        self.action = action
        self.current = current
        super().__init__(
            f"action {action!r} is not allowed from status {current!r} (illegal transition)"
        )


def target_status(action: str, current: ItemStatus | str) -> ItemStatus:
    """Return the destination status, or raise :class:`IllegalTransitionError`."""
    transition = _BY_ACTION[action]
    if ItemStatus(current) not in transition.from_statuses:
        raise IllegalTransitionError(action, str(current))
    return transition.to_status


def legal_pairs() -> frozenset[tuple[str, str]]:
    """All legal (from_status, to_status) pairs; used by tests and docs."""
    return frozenset(
        (src.value, t.to_status.value) for t in TRANSITIONS for src in t.from_statuses
    )