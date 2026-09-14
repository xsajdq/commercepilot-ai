"""Sentry event scrubbing shared by apps/api and apps/worker (Phase 21).

Sentry's own `send_default_pii=False` default (never overridden here)
already strips a lot, but an event can still carry request headers,
local variables from a stack frame, or `extra`/`tags` a caller attached
- any of which could echo a secret cp_shared.logging would also redact.
`scrub_event` reuses the exact same known-field-name list and
real-secret-shape patterns as the logging redactor, so both layers stay
in sync with a single source of truth rather than two hand-maintained
lists drifting apart.
"""

from typing import Any

from cp_shared.logging import SENSITIVE_KEYS, redact_text

_REDACTED = "[REDACTED]"


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS
                else _scrub(val)
            )
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """A Sentry `before_send` hook: recursively scrubs known sensitive
    field names and real secret shapes from the entire event body
    (request headers/data, `extra`, `tags`, stack-frame local variables,
    exception messages) before it ever leaves the process."""
    return _scrub(event)
