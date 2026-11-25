"""Retry failed reminder dispatches: ``python -m app.jobs.retry_reminders``.

Uses the same injectable reminder service as the approval path; with the stub
client a retry always succeeds, in production it calls the reminder work order.
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.api.deps import get_reminder
from app.db import session_scope
from app.enums import ReminderStatus
from app.models import IntelReminderOutbox
from app.services.approvals import dispatch_reminder

MAX_ATTEMPTS = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    args = parser.parse_args(argv)

    reminder = get_reminder()
    retried = sent = failed = 0
    with session_scope() as session:
        rows = session.scalars(
            select(IntelReminderOutbox).where(
                IntelReminderOutbox.status == ReminderStatus.FAILED,
                IntelReminderOutbox.attempts < args.max_attempts,
                IntelReminderOutbox.deleted_at.is_(None),
            )
        ).all()
        for row in rows:
            retried += 1
            dispatch_reminder(session, row, reminder)
            if row.status == ReminderStatus.SENT:
                sent += 1
            else:
                failed += 1
    print(f"retried={retried} sent={sent} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())