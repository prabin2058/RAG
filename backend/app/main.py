"""FastAPI app factory."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.v1.router import api_router
from app.core.config import settings

log = logging.getLogger(__name__)


def _preload_models():
    """Preload ML models in the background so the first query isn't slow."""
    def _load():
        try:
            from app.services.embedding_service import _get_model as load_embed
            log.info("Preloading embedding model...")
            load_embed()
            log.info("Embedding model ready.")
        except Exception as e:
            log.warning("Failed to preload embedding model: %s", e)

    threading.Thread(target=_load, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _preload_models()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="RAG PDF Q&A", version="1.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Configure OpenAPI schema for Swagger auto-authorize
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
        # Apply security globally to all endpoints
        openapi_schema["security"] = [{"BearerAuth": []}]
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app


app = create_app()
