"""Which OpenAI models users may pick, and the per-request AI configuration."""

import re
from dataclasses import dataclass
from typing import Protocol

import openai

# Cheap, structured-output-capable models first; gpt-4o-mini is the tested default.
RECOMMENDED = [
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "gpt-5-mini",
    "gpt-5.4-mini",
    "gpt-4.1-nano",
    "gpt-5-nano",
]
DEFAULT_MODEL = "gpt-4o-mini"

_CHAT_FAMILY = re.compile(r"^(gpt-4o|gpt-4\.1|gpt-5|gpt-6|o3|o4)")
_EXCLUDE = re.compile(
    r"(audio|realtime|tts|transcribe|image|search|instruct|codex|live|whisper|-pro\b|"
    r"chat-latest|translate|-\d{4}-\d{2}-\d{2}$)"
)


def usable_models(model_ids: list[str]) -> list[str]:
    """Chat models this app supports, recommended ones first, then alphabetical."""
    usable = {m for m in model_ids if _CHAT_FAMILY.match(m) and not _EXCLUDE.search(m)}
    first = [m for m in RECOMMENDED if m in usable]
    return first + sorted(usable - set(first))


def default_model(models: list[str]) -> str | None:
    return DEFAULT_MODEL if DEFAULT_MODEL in models else (models[0] if models else None)


class InvalidApiKey(ValueError):
    pass


class ModelCatalog(Protocol):
    async def list_models(self, api_key: str) -> list[str]: ...


class OpenAIModelCatalog:
    """Validates a key by listing the models it can use."""

    async def list_models(self, api_key: str) -> list[str]:
        client = openai.AsyncOpenAI(api_key=api_key, max_retries=1, timeout=20)
        try:
            return [m.id async for m in client.models.list()]
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise InvalidApiKey("OpenAI rejected this API key.") from exc
        finally:
            await client.close()


@dataclass(frozen=True)
class UserAI:
    """The signed-in user's OpenAI configuration for this request."""

    api_key: str
    model_small: str
    model_large: str | None
