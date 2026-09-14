"""A handful of defensive response headers (Phase 21) - cheap, well
established, and appropriate for every response this API sends. Exempts
the interactive API docs (`/docs`, `/redoc`, `/openapi.json`): Swagger
UI/ReDoc load their own JS/CSS from a CDN and render real HTML, and a
CSP tuned for a pure JSON API would break them - dev/debug tooling, not
the surface this hardens.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}

_HEADERS: dict[str, str] = {
    # Force HTTPS on every future visit once served over it even once -
    # a no-op, harmless header when served over plain HTTP (as in local
    # dev), so safe to always send rather than branch on `environment`.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # A pure JSON API needs nothing else loaded or embedded - `apps/web`
    # is a separate origin entirely, never an iframe of this one.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _DOCS_PATHS:
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in _HEADERS.items():
                    headers.append((name.encode("latin-1"), value.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
