from cp_shared.logging import configure_logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    analytics,
    billing,
    catalog,
    connections,
    health,
    products,
    recommendations,
)
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.metrics import PrometheusMiddleware
from app.core.metrics import router as metrics_router
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.sentry import configure_sentry


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(service_name="api")
    configure_sentry(settings)

    app = FastAPI(title="CommercePilot API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Middleware wraps in reverse order of registration - each of these
    # ends up wrapping the ones before it, so SecurityHeaders is
    # outermost (added last): every response gets the headers, even a
    # 429 the rate limiter rejects or a CORS preflight.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(metrics_router)
    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(connections.router)
    app.include_router(products.router)
    app.include_router(products.offers_router)
    app.include_router(recommendations.router)
    app.include_router(catalog.router)
    app.include_router(analytics.router)
    app.include_router(billing.router)

    return app


app = create_app()
