import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyses, documents, health
from app.core.config import Settings, get_settings
from app.db.supabase import SupabaseRepository
from app.mcp_server.server import BearerTokenGuard, create_mcp_server
from app.skills.taxonomy import load_taxonomy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _mcp_http_app(app: FastAPI, settings: Settings) -> BearerTokenGuard:
    """Our MCP server over streamable HTTP, for MCP clients outside the app."""

    def store() -> SupabaseRepository:
        return SupabaseRepository(
            app.state.http, settings.supabase_url, settings.supabase_service_role_key
        )

    mcp_app = create_mcp_server(store, load_taxonomy()).http_app(
        path="/", stateless_http=True, json_response=True
    )
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
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(analyses.router)
    # Only exposed when a service token is configured.
    if settings.mcp_service_token:
        app.mount("/mcp", _mcp_http_app(app, settings))
    return app


app = create_app()
