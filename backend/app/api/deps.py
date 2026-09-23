import hashlib
from collections import OrderedDict
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.ai.models import ModelCatalog, OpenAIModelCatalog, UserAI
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.crypto import CryptoError, decrypt
from app.db.repository import Repository
from app.db.supabase import DatabaseError, SupabaseRepository
from app.llm.client import LLMClient, OpenAIModel
from app.rag.embeddings import CachedEmbedder, Embedder, OpenAIEmbedder

NO_KEY_MESSAGE = "Add your OpenAI API key in Settings to run analyses."
_MAX_CLIENTS = 128


def get_repository(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Repository:
    try:
        return SupabaseRepository(
            request.app.state.http, settings.supabase_url, settings.supabase_service_role_key
        )
    except DatabaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured") from exc


def get_model_catalog() -> ModelCatalog:
    return OpenAIModelCatalog()


async def get_user_ai(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repo: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserAI:
    """The signed-in user's own OpenAI key and models. Every user brings their own key."""
    saved = await repo.get_ai_settings(user.id)
    if saved is None:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, NO_KEY_MESSAGE)
    try:
        api_key = decrypt(saved.encrypted_api_key, settings.app_encryption_key)
    except CryptoError as exc:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "Your saved OpenAI key can't be read. Please add it again in Settings.",
        ) from exc
    return UserAI(api_key=api_key, model_small=saved.model_small, model_large=saved.model_large)


def _per_key(request: Request, name: str) -> "OrderedDict[str, object]":
    """Small per-process LRU of OpenAI clients, keyed by a hash of the API key."""
    cache: OrderedDict[str, object] | None = getattr(request.app.state, name, None)
    if cache is None:
        cache = OrderedDict()
        setattr(request.app.state, name, cache)
    return cache


def _key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_llm_client(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[Repository, Depends(get_repository)],
    ai: Annotated[UserAI, Depends(get_user_ai)],
) -> LLMClient:
    cache = _per_key(request, "openai_models")
    key_id = _key_id(ai.api_key)
    model = cache.get(key_id)
    if not isinstance(model, OpenAIModel):
        model = OpenAIModel(settings.model_copy(update={"openai_api_key": ai.api_key}))
        cache[key_id] = model
        if len(cache) > _MAX_CLIENTS:
            cache.popitem(last=False)
    cache.move_to_end(key_id)
    user_settings = settings.model_copy(
        update={"openai_model_small": ai.model_small, "openai_model_large": ai.model_large or ""}
    )
    return LLMClient(user_settings, repo, model)


def get_embedder(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[Repository, Depends(get_repository)],
    ai: Annotated[UserAI, Depends(get_user_ai)],
) -> Embedder:
    cache = _per_key(request, "openai_embedders")
    key_id = _key_id(ai.api_key)
    inner = cache.get(key_id)
    if not isinstance(inner, OpenAIEmbedder):
        inner = OpenAIEmbedder(ai.api_key, settings.openai_embedding_model)
        cache[key_id] = inner
        if len(cache) > _MAX_CLIENTS:
            cache.popitem(last=False)
    cache.move_to_end(key_id)
    return CachedEmbedder(inner, repo)
