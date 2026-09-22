import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyses, documents, health
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Shared connection pool for Supabase REST calls.
    async with httpx.AsyncClient(timeout=30) as http:
        app.state.http = http
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Resume Optimizer API", version=settings.app_version, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(analyses.router)
    return app


app = create_app()
