import asyncio

import pytest
from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)

from cp_sync.retry import retry_with_backoff


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return sleeps


async def test_succeeds_on_first_try() -> None:
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert await retry_with_backoff(fn) == "ok"
    assert calls == 1


async def test_retries_transient_error_then_succeeds(no_real_sleep: list[float]) -> None:
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectorError("transient")
        return "ok"

    result = await retry_with_backoff(fn, max_attempts=5, base_delay=0.01)
    assert result == "ok"
    assert calls == 3
    assert len(no_real_sleep) == 2


async def test_does_not_retry_auth_error() -> None:
    calls = 0

    async def fn() -> None:
        nonlocal calls
        calls += 1
        raise ConnectorAuthError("bad creds")

    with pytest.raises(ConnectorAuthError):
        await retry_with_backoff(fn, max_attempts=5)
    assert calls == 1


async def test_does_not_retry_not_found_error() -> None:
    calls = 0

    async def fn() -> None:
        nonlocal calls
        calls += 1
        raise ConnectorNotFoundError("gone")

    with pytest.raises(ConnectorNotFoundError):
        await retry_with_backoff(fn, max_attempts=5)
    assert calls == 1


async def test_gives_up_after_max_attempts(no_real_sleep: list[float]) -> None:
    calls = 0

    async def fn() -> None:
        nonlocal calls
        calls += 1
        raise ConnectorError("still broken")

    with pytest.raises(ConnectorError):
        await retry_with_backoff(fn, max_attempts=3, base_delay=0.01)
    assert calls == 3


async def test_honors_retry_after_seconds(no_real_sleep: list[float]) -> None:
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectorRateLimitError("slow down", retry_after_seconds=7.5)
        return "ok"

    result = await retry_with_backoff(fn, max_attempts=3, base_delay=0.01)
    assert result == "ok"
    assert no_real_sleep == [7.5]


async def test_non_connector_exception_is_not_retried() -> None:
    calls = 0

    async def fn() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("bug in caller code")

    with pytest.raises(ValueError):
        await retry_with_backoff(fn)
    assert calls == 1
