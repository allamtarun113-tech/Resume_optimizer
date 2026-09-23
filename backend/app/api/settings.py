from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.models import InvalidApiKey, ModelCatalog, default_model, usable_models
from app.api.deps import get_model_catalog, get_repository
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.crypto import CryptoError, decrypt, encrypt
from app.db.repository import Repository
from app.schemas.ai_settings import (
    AiSettingsResponse,
    AiSettingsUpdate,
    ModelListRequest,
    ModelListResponse,
)

router = APIRouter(prefix="/settings/ai", tags=["settings"])

User = Annotated[CurrentUser, Depends(get_current_user)]
Repo = Annotated[Repository, Depends(get_repository)]
Catalog = Annotated[ModelCatalog, Depends(get_model_catalog)]
Config = Annotated[Settings, Depends(get_settings)]


async def _saved_key(repo: Repository, user: CurrentUser, settings: Settings) -> str | None:
    saved = await repo.get_ai_settings(user.id)
    if saved is None:
        return None
    try:
        return decrypt(saved.encrypted_api_key, settings.app_encryption_key)
    except CryptoError:
        return None


async def _models_for(catalog: ModelCatalog, api_key: str) -> list[str]:
    try:
        models = usable_models(await catalog.list_models(api_key.strip()))
    except InvalidApiKey as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if not models:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This key has no access to a supported chat model (e.g. gpt-4o-mini).",
        )
    return models


@router.get("")
async def get_ai_settings(user: User, repo: Repo) -> AiSettingsResponse:
    saved = await repo.get_ai_settings(user.id)
    if saved is None:
        return AiSettingsResponse(
            has_key=False, key_last4=None, model_small=None, model_large=None, updated_at=None
        )
    return AiSettingsResponse(
        has_key=True,
        key_last4=saved.key_last4,
        model_small=saved.model_small,
        model_large=saved.model_large,
        updated_at=saved.updated_at,
    )


@router.post("/models")
async def list_models(
    body: ModelListRequest, user: User, repo: Repo, catalog: Catalog, settings: Config
) -> ModelListResponse:
    """Check a key (or the saved one) and list the models it can use in this app."""
    api_key = body.api_key or await _saved_key(repo, user, settings)
    if not api_key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Paste your OpenAI API key.")
    models = await _models_for(catalog, api_key)
    return ModelListResponse(models=models, default=default_model(models))


@router.put("")
async def save_ai_settings(
    body: AiSettingsUpdate, user: User, repo: Repo, catalog: Catalog, settings: Config
) -> AiSettingsResponse:
    api_key = body.api_key.strip() if body.api_key else await _saved_key(repo, user, settings)
    if not api_key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Paste your OpenAI API key.")
    models = await _models_for(catalog, api_key)
    for chosen in (body.model_small, body.model_large):
        if chosen and chosen not in models:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{chosen} isn't available for this key.",
            )
    try:
        encrypted = encrypt(api_key, settings.app_encryption_key)
    except CryptoError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Key storage isn't configured on the server."
        ) from exc
    await repo.save_ai_settings(
        user_id=user.id,
        encrypted_api_key=encrypted,
        key_last4=api_key[-4:],
        model_small=body.model_small,
        model_large=body.model_large if body.model_large != body.model_small else None,
    )
    return await get_ai_settings(user, repo)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_settings(user: User, repo: Repo) -> None:
    await repo.delete_ai_settings(user.id)
