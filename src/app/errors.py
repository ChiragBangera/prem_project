class AnalyticsError(Exception):
    """Base exception for errors that can be shown through the public API."""


class UnderstatRequestError(AnalyticsError):
    """Raised when Understat cannot be reached or returns an invalid response."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class UnderstatTimeoutError(UnderstatRequestError):
    """Raised when an Understat request exceeds the configured timeout."""
