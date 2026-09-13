import os

_DEFAULT_MODEL = "claude-sonnet-5"


def get_anthropic_api_key() -> str:
    """Reads ANTHROPIC_API_KEY lazily (not at import time) so tests can
    set it via monkeypatch/env before a task actually needs it - and so
    a worker process with no AI tasks configured never fails to start
    just because the key is unset."""
    return os.environ["ANTHROPIC_API_KEY"]


def get_anthropic_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
