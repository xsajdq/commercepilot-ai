import time

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.types import ASGIApp, Receive, Scope, Send

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["method", "path"]
)

_METRICS_PATH = "/metrics"


class PrometheusMiddleware:
    """Plain ASGI middleware (not `BaseHTTPMiddleware`) so a streaming
    response is measured correctly and the request is never buffered in
    memory just to time it.

    Reads `scope["route"]` *after* the inner app has run - Starlette's
    router sets it on the (mutable, shared-by-reference) scope dict
    before dispatching to the matched endpoint, so it's the real route
    template (`/products/{product_id}`) rather than the raw path,
    keeping the cardinality of the `path` label bounded regardless of
    how many distinct product ids get requested.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == _METRICS_PATH:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = _route_template(scope)
            REQUEST_COUNT.labels(method=scope["method"], path=path, status=status_code).inc()
            REQUEST_DURATION.labels(method=scope["method"], path=path).observe(
                time.perf_counter() - start
            )


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    if route is not None:
        return route.path
    return scope.get("path", "unknown")


router = APIRouter()


@router.get(_METRICS_PATH, include_in_schema=False)
async def metrics() -> Response:
    """Unauthenticated by design (Prometheus scrapes it directly) - the
    values here are aggregate request counts/latencies, never tenant
    data, so this doesn't need the tenant-scoped auth every other route
    requires. Restrict network access to it at the proxy/firewall layer
    in production (see docs/architecture/deployment.md), the same way
    Prometheus's own `/metrics` convention expects.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
