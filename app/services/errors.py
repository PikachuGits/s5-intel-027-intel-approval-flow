"""Domain errors mapped to HTTP status codes by ``app.main``."""
from __future__ import annotations


class DomainError(Exception):
    http_status: int = 400
    code: str = "domain_error"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(DomainError):
    http_status = 404
    code = "not_found"


class ForbiddenRoleError(DomainError):
    http_status = 403
    code = "forbidden_role"


class FourEyesViolationError(DomainError):
    http_status = 403
    code = "four_eyes_violation"


class IllegalTransitionHTTPError(DomainError):
    http_status = 409
    code = "illegal_transition"


class LinkRecheckFailedError(DomainError):
    http_status = 409
    code = "link_recheck_failed"


class LockedContentError(DomainError):
    http_status = 409
    code = "content_locked"


class MissingActorError(DomainError):
    http_status = 401
    code = "missing_actor"


class RejectCommentRequiredError(DomainError):
    http_status = 422
    code = "reject_comment_required"