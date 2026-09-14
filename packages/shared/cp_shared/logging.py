"""Structured JSON logging shared by apps/api and apps/worker (Phase 21).

CLAUDE.md forbids ever logging access tokens, refresh tokens, API keys,
customer personal data, or payment information. Discipline at each call
site (never pass a secret to a logger) is the primary guarantee; this
module is the defense-in-depth backstop, not a substitute for it - a
`RedactingFilter` scrubs every record before it reaches a handler.

The filter's coverage is deliberately honest about its limits rather
than pretending to catch everything (CLAUDE.md #9's "don't guess/invent"
spirit applies here too):

- Known sensitive field names (passed via `extra={...}` or already
  attached to the record) are always replaced outright.
- A small set of *real, recognized* secret shapes this codebase actually
  produces are pattern-redacted wherever they appear in a message or a
  string argument: JWT access tokens (`eyJ...`), Fernet-encrypted
  credential blobs (`gAAAAA...`), `Authorization: Bearer ...` headers,
  and Stripe secret/webhook keys (`sk_live_`/`sk_test_`/`whsec_`).
- An opaque high-entropy value with no recognizable prefix (e.g. this
  app's own refresh tokens) is NOT pattern-matched - a generic
  "looks random" heuristic would false-positive on ordinary ids and
  still not be a real guarantee. Those must never be logged in the
  first place; this module cannot make that safe after the fact.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

_REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "secret_key",
    "password",
    "credentials",
    "encrypted_credentials",
    "authorization",
    "client_secret",
    "stripe_secret_key",
    "stripe_webhook_secret",
    "encryption_key",
    "token",
}

# Real, recognized secret shapes - see module docstring for why this list
# stops here rather than trying to catch anything "random-looking".
_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT
    re.compile(r"gAAAAA[A-Za-z0-9_=-]{20,}"),  # Fernet token (cp_shared.crypto)
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._-]+"),  # Authorization header
    re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{10,}"),  # Stripe secret key
    re.compile(r"whsec_[A-Za-z0-9]{10,}"),  # Stripe webhook secret
]


def redact_text(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    """Scrubs known secret-shaped data from every log record before it
    reaches a handler. See module docstring for exactly what this does
    and does not catch."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: _REDACTED if key.lower() in SENSITIVE_KEYS else _redact_arg(value)
                    for key, value in record.args.items()
                }
            else:
                record.args = tuple(_redact_arg(arg) for arg in record.args)

        for key in list(record.__dict__.keys()):
            if key.lower() in SENSITIVE_KEYS:
                setattr(record, key, _REDACTED)

        return True


def _redact_arg(value: Any) -> Any:
    return redact_text(value) if isinstance(value, str) else value


# Standard attributes every LogRecord carries - anything else on the
# record came from a caller's `extra={...}` and is worth shipping too
# (that's the actual point of structured logging - a tenant_id or
# connection_id in `extra` should be filterable, not thrown away).
_RESERVED_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line - easy to ship to any log aggregator
    without a parser tuned to a particular text layout. Any `extra={...}`
    field a caller attached is included (after `RedactingFilter` has had
    a chance to scrub it by name)."""

    def __init__(self, *, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self._service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


_configured_services: set[str] = set()


def configure_logging(*, service_name: str, level: str = "INFO") -> None:
    """Installs the JSON formatter + `RedactingFilter` on the root
    logger. Idempotent per `service_name` (safe to call more than once,
    e.g. once per Celery worker process) so it never accumulates
    duplicate handlers on repeated calls within the same process.
    """
    if service_name in _configured_services:
        return
    _configured_services.add(service_name)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service_name=service_name))
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
