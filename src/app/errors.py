"""Application errors.

Every error that can reach the browser carries a stable ``code``, an HTTP
status, a human message, and (optionally) a ``hint`` telling the user what to do
next. The API layer renders them uniformly, so the UI never has to guess.
"""

from __future__ import annotations


class AppError(Exception):
    status = 500
    code = "internal_error"

    def __init__(self, message: str, *, hint: str | None = None, **extra):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.extra = extra

    def to_payload(self) -> dict:
        payload = {"error": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        payload.update(self.extra)
        return payload


class BadRequest(AppError):
    status = 422
    code = "invalid_parameters"


class NotFound(AppError):
    status = 404
    code = "not_found"


class DataUnavailable(AppError):
    """Nothing cached and the upstream cannot be reached (or is disabled)."""

    status = 503
    code = "data_unavailable"


class UpstreamError(AppError):
    """Understat (or another provider) answered with an error."""

    status = 502
    code = "upstream_error"

    def __init__(self, message: str, *, upstream_status: int | None = None, **kwargs):
        super().__init__(message, upstream_status=upstream_status, **kwargs)
        self.upstream_status = upstream_status


class UpstreamTimeout(UpstreamError):
    code = "upstream_timeout"
