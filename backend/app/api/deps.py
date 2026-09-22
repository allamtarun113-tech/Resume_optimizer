from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.db.repository import Repository
from app.db.supabase import DatabaseError, SupabaseRepository
from app.llm.client import LLMClient, OpenAIModel


def get_repository(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Repository:
    try:
        return SupabaseRepository(
            request.app.state.http, settings.supabase_url, settings.supabase_service_role_key
        )
    except DatabaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured") from exc


def get_llm_client(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[Repository, Depends(get_repository)],
) -> LLMClient:
    if not settings.openai_api_key or not settings.openai_model_small:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI model not configured")
    # One OpenAI client per process: keeps the connection pool and learned model quirks.
    model = getattr(request.app.state, "openai_model", None)
    if model is None:
        model = request.app.state.openai_model = OpenAIModel(settings)
    return LLMClient(settings, repo, model)
