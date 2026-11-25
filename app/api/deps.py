"""HTTP dependencies: DB session, the S2-IAM stub, and injectable services.

STUB NOTICE (integration point)
-------------------------------
Production must replace ``get_principal`` with S2-IAM token introspection. The
header stub below is for this work order's isolated demo/tests only and must
never be used for production authentication or authorization:

1. validate the bearer token and load the user;
2. resolve the user's org memberships, visible site ids and role
   (``supervisor`` / ``staff``);
3. return a :class:`app.principal.Principal`.

Every service path already enforces ``principal.org_id`` / ``principal.site_ids``
and the supervisor-only rule, so only this dependency needs to change.

``get_link_checker`` / ``get_matcher`` / ``get_reminder`` are the three service
integration points (link recheck, member matching, reminder dispatch). Tests
override them via ``app.dependency_overrides``; production swaps the returned
implementations without touching the routers.
"""
from __future__ import annotations

from typing import Annotated, Iterator
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_factory
from app.enums import ROLES, Role
from app.principal import Principal
from app.services.link_checker import HttpLinkChecker, LinkChecker
from app.services.matcher import MemberMatcher, StubMemberMatcher
from app.services.reminder import ReminderService, StubReminderService


def get_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _parse_uuid(raw: str, *, header: str) -> UUID:
    try:
        return UUID(raw.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{header} contains an invalid UUID: {raw!r}",
        ) from exc


def get_principal(
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
    x_site_ids: Annotated[str | None, Header(alias="X-Site-Ids")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> Principal:
    if not x_org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Org-Id is required (S2-IAM stub; see app/api/deps.py)",
        )
    org_id = _parse_uuid(x_org_id, header="X-Org-Id")
    user_id = _parse_uuid(x_user_id, header="X-User-Id") if x_user_id else None

    role = (x_user_role or Role.STAFF.value).strip().lower()
    if role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"X-User-Role must be one of {list(ROLES)}, got {x_user_role!r}",
        )

    site_ids: frozenset[UUID] | None = None
    if x_site_ids:
        parsed = frozenset(
            _parse_uuid(part, header="X-Site-Ids")
            for part in x_site_ids.split(",")
            if part.strip()
        )
        if not parsed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Site-Ids was provided but empty",
            )
        site_ids = parsed

    return Principal(org_id=org_id, site_ids=site_ids, user_id=user_id, role=role)


def get_link_checker() -> LinkChecker:
    return HttpLinkChecker(timeout_seconds=get_settings().link_recheck_timeout_seconds)


def get_matcher() -> MemberMatcher:
    return StubMemberMatcher()


def get_reminder() -> ReminderService:
    return StubReminderService()


SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
LinkCheckerDep = Annotated[LinkChecker, Depends(get_link_checker)]
MatcherDep = Annotated[MemberMatcher, Depends(get_matcher)]
ReminderDep = Annotated[ReminderService, Depends(get_reminder)]