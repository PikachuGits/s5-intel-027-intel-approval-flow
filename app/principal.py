"""Caller identity value object shared by the API layer and the services.

Constructed from the S2-IAM stub headers in ``app.api.deps``; production builds
the same object from token introspection + org membership lookup.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    org_id: uuid.UUID
    site_ids: frozenset[uuid.UUID] | None  # None = every site inside the org
    user_id: uuid.UUID | None = None
    role: str = "staff"