"""FastAPI entry point.  Run:  uvicorn app.main:app --reload --port 8000"""
import logging
from contextlib import asynccontextmanager

# pyrefly: ignore[missing-import]
from fastapi import FastAPI
# pyrefly: ignore[missing-import]
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.deps import Container, build_container
from app.routes import chats, documents, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container or build_container(settings)
        yield

    app = FastAPI(title="NEXUS AI API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    for r in (health.router, chats.router, documents.router):
        app.include_router(r)
    return app


app = create_app()
