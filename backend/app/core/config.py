import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_version: str = "0.1.0"

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    # Only needed for projects still on legacy HS256 JWT signing.
    supabase_jwt_secret: str = ""
    database_url: str = ""

    # OpenAI (used from Phase 1)
    openai_api_key: str = ""
    openai_model_small: str = ""
    openai_model_large: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    mcp_service_token: str = ""
    # Accepts a JSON list or a comma-separated string.
    allowed_origins: Annotated[list[str], NoDecode] = Field(default=["http://localhost:3000"])
    daily_analysis_limit: int = 10

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            value = json.loads(value) if value.startswith("[") else value.split(",")
        if isinstance(value, list):
            # Browsers send origins without a trailing slash.
            return [str(v).strip().rstrip("/") for v in value if str(v).strip()]
        return value

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
