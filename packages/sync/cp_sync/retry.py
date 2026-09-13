import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)

T = TypeVar("T")

_JITTER_RATIO = 0.25


def _is_retryable(exc: BaseException) -> bool:
    """ConnectorAuthError/ConnectorNotFoundError are permanent for a
    given call - retrying wrong credentials or a missing resource just
    burns rate-limit budget. Everything else that looks like a transient
    platform or network hiccup is worth retrying."""
    if isinstance(exc, ConnectorAuthError | ConnectorNotFoundError):
        return False
    return isinstance(exc, ConnectorRateLimitError | ConnectorError | httpx.TransportError)


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> T:
    """Calls `fn()`, retrying on transient connector/network failures
    with exponential backoff + jitter. Honors
    ConnectorRateLimitError.retry_after_seconds when the platform told us
    exactly how long to wait, rather than guessing. Never retries
    ConnectorAuthError or ConnectorNotFoundError (see `_is_retryable`).
    Re-raises the last exception once `max_attempts` is exhausted, or any
    non-retryable exception immediately.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await fn()
        except Exception as exc:
            if not _is_retryable(exc) or attempt >= max_attempts:
                raise

            if isinstance(exc, ConnectorRateLimitError) and exc.retry_after_seconds:
                delay = exc.retry_after_seconds
            else:
                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                delay *= 1 + random.random() * _JITTER_RATIO

            await asyncio.sleep(delay)
