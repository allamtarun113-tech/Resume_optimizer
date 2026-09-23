import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyses, documents, explain, health, interview
from app.api import settings as ai_settings
from app.core.config import Settings, get_settings
from app.db.supabase import SupabaseRepository
from app.mcp_server.server import BearerTokenGuard, create_mcp_server
from app.rag.embeddings import CachedEmbedder, OpenAIEmbedder
from app.skills.taxonomy import load_taxonomy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _mcp_http_app(app: FastAPI, settings: Settings) -> BearerTokenGuard:
    """Our MCP server over streamable HTTP, for MCP clients outside the app."""

    def store() -> SupabaseRepository:
        return SupabaseRepository(
            app.state.http, settings.supabase_url, settings.supabase_service_role_key
        )

    inner = (
        OpenAIEmbedder(settings.openai_api_key, settings.openai_embedding_model)
        if settings.openai_api_key
        else None
    )

    def embedder() -> CachedEmbedder:
        assert inner is not None
        return CachedEmbedder(inner, store())

    mcp_app = create_mcp_server(
        store, load_taxonomy(), embedder if inner is not None else None
    ).http_app(path="/", stateless_http=True, json_response=True)
    app.state.mcp_lifespan = mcp_app.lifespan
    return BearerTokenGuard(mcp_app, settings.mcp_service_token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        # Shared connection pool for Supabase REST calls.
        app.state.http = await stack.enter_async_context(httpx.AsyncClient(timeout=30))
        mcp_lifespan = getattr(app.state, "mcp_lifespan", None)
        if mcp_lifespan is not None:
            await stack.enter_async_context(mcp_lifespan(app))
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
        # Lets the browser read the report's file name on download.
        expose_headers=["Content-Disposition"],
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(analyses.router)
    app.include_router(interview.router)
    app.include_router(explain.router)
    app.include_router(ai_settings.router)
    # Only exposed when a service token is configured.
    if settings.mcp_service_token:
        app.mount("/mcp", _mcp_http_app(app, settings))
    return app


app = create_app()
