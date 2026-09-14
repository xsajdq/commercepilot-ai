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


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="CommercePilot API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
