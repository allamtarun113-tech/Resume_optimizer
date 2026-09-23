from datetime import datetime

from pydantic import BaseModel, Field


class AiSettingsRecord(BaseModel):
    user_id: str
    encrypted_api_key: str
    key_last4: str
    model_small: str
    model_large: str | None
    updated_at: datetime


class AiSettingsResponse(BaseModel):
    has_key: bool
    key_last4: str | None
    model_small: str | None
    model_large: str | None
    updated_at: datetime | None


class AiSettingsUpdate(BaseModel):
    # Omit api_key to keep the saved key and only change models.
    api_key: str | None = Field(default=None, min_length=20, max_length=300)
    model_small: str = Field(min_length=1, max_length=100)
    model_large: str | None = Field(default=None, max_length=100)


class ModelListRequest(BaseModel):
    # Omit to list models for the saved key.
    api_key: str | None = Field(default=None, min_length=20, max_length=300)


class ModelListResponse(BaseModel):
    models: list[str]
    default: str | None
