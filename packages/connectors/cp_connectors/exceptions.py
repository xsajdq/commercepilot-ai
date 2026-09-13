class ConnectorError(Exception):
    """Base for every connector failure."""


class ConnectorNotFoundError(ConnectorError):
    """The requested resource doesn't exist on the platform."""


class ConnectorAuthError(ConnectorError):
    """Credentials are invalid, expired, or revoked."""


class ConnectorRateLimitError(ConnectorError):
    """The platform is rate-limiting requests; the caller should back off
    and retry rather than treat this as a permanent failure."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
