"""OpenAI wrapper: structured outputs, result caching, token accounting.

Agents call `LLMClient.parse`. Results are cached by
sha256(prompt name + prompt version + model + output schema + input), so identical
inputs never hit OpenAI twice and extraction (hence scoring) stays reproducible.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import openai
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm.prompts import Prompt

logger = logging.getLogger(__name__)

ModelTier = Literal["small", "large"]


class LLMError(RuntimeError):
    """An LLM call failed in a way retrying won't fix. The message is safe to show users."""


@dataclass(frozen=True)
class Completion[T: BaseModel]:
    parsed: T
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMCallRecord:
    agent: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cached: bool
    latency_ms: int
    analysis_id: str | None
    user_id: str | None


class StructuredModel(Protocol):
    async def complete[T: BaseModel](
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        output_type: type[T],
        max_output_tokens: int,
    ) -> Completion[T]: ...


class LLMStore(Protocol):
    async def get_cached(self, key: str) -> dict[str, Any] | None: ...

    async def put_cached(
        self, key: str, *, agent: str, model: str, prompt_version: str, response: dict[str, Any]
    ) -> None: ...

    async def log_call(self, record: LLMCallRecord) -> None: ...


def cache_key(prompt: Prompt, model: str, output_type: type[BaseModel], input_text: str) -> str:
    payload = {
        "prompt": prompt.name,
        "version": prompt.version,
        "model": model,
        "schema": output_type.model_json_schema(),
        "input": input_text,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class LLMClient:
    def __init__(self, settings: Settings, store: LLMStore, model: StructuredModel) -> None:
        self._settings = settings
        self._store = store
        self._model = model

    def model_for(self, tier: ModelTier) -> str:
        name = (
            self._settings.openai_model_small
            if tier == "small"
            else self._settings.openai_model_large or self._settings.openai_model_small
        )
        if not name:
            raise LLMError("The AI model is not configured on the server (OPENAI_MODEL_SMALL).")
        return name

    async def parse[T: BaseModel](
        self,
        *,
        agent: str,
        prompt: Prompt,
        input_text: str,
        output_type: type[T],
        max_output_tokens: int,
        tier: ModelTier = "small",
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> T:
        model = self.model_for(tier)
        key = cache_key(prompt, model, output_type, input_text)
        started = time.perf_counter()

        def record(cached: bool, input_tokens: int = 0, output_tokens: int = 0) -> LLMCallRecord:
            return LLMCallRecord(
                agent=agent,
                model=model,
                prompt_version=prompt.version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached=cached,
                latency_ms=round((time.perf_counter() - started) * 1000),
                analysis_id=analysis_id,
                user_id=user_id,
            )

        cached = await self._store.get_cached(key)
        if cached is not None:
            try:
                result = output_type.model_validate(cached)
            except ValidationError:
                logger.warning("Ignoring cached %s result that no longer validates", agent)
            else:
                await self._log(record(cached=True))
                return result

        completion = await self._model.complete(
            model=model,
            instructions=prompt.text,
            input_text=input_text,
            output_type=output_type,
            max_output_tokens=max_output_tokens,
        )
        await self._log(record(False, completion.input_tokens, completion.output_tokens))
        try:
            await self._store.put_cached(
                key,
                agent=agent,
                model=model,
                prompt_version=prompt.version,
                response=completion.parsed.model_dump(mode="json"),
            )
        except Exception:
            logger.exception("Failed to cache %s result", agent)
        return completion.parsed

    async def _log(self, record: LLMCallRecord) -> None:
        # Accounting must never break an analysis.
        try:
            await self._store.log_call(record)
        except Exception:
            logger.exception("Failed to log LLM call for %s", record.agent)


class OpenAIModel:
    """StructuredModel backed by the OpenAI Responses API.

    Models differ in which sampling parameters they accept (reasoning models reject
    `temperature`, older models reject `reasoning`). We send both and drop whichever one a
    model rejects, remembering it for the rest of the process. Transient errors (429, 5xx,
    timeouts) are retried by the SDK.
    """

    def __init__(self, settings: Settings, client: openai.AsyncOpenAI | None = None) -> None:
        self._client = client or openai.AsyncOpenAI(
            api_key=settings.openai_api_key or None,
            timeout=settings.openai_timeout_seconds,
            max_retries=3,
        )
        self._reasoning_effort = settings.openai_reasoning_effort or None
        self._rejected: dict[str, set[str]] = {}

    def _optional_params(self, model: str) -> dict[str, Any]:
        params: dict[str, Any] = {"temperature": 0}
        if self._reasoning_effort:
            params["reasoning"] = {"effort": self._reasoning_effort}
        rejected = self._rejected.get(model, set())
        return {k: v for k, v in params.items() if k not in rejected}

    async def complete[T: BaseModel](
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        output_type: type[T],
        max_output_tokens: int,
    ) -> Completion[T]:
        while True:
            params = self._optional_params(model)
            try:
                response = await self._client.responses.parse(
                    model=model,
                    instructions=instructions,
                    input=input_text,
                    text_format=output_type,
                    max_output_tokens=max_output_tokens,
                    store=False,
                    **params,
                )
                break
            except openai.BadRequestError as exc:
                rejected = _rejected_param(exc, params)
                if rejected is None:
                    raise
                logger.info("Model %s rejected %r; retrying without it", model, rejected)
                self._rejected.setdefault(model, set()).add(rejected)
            except openai.AuthenticationError as exc:
                raise LLMError("The server's OpenAI API key was rejected.") from exc

        if response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else None
            raise LLMError(f"The AI response was cut off ({reason or 'incomplete'}).")
        parsed = response.output_parsed
        if parsed is None:
            raise LLMError("The AI model declined to process this document.")
        usage = response.usage
        return Completion(
            parsed=parsed,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )


def _rejected_param(exc: openai.BadRequestError, sent: dict[str, Any]) -> str | None:
    """Which of the optional params `sent` the API complained about, if any."""
    if exc.param:
        top = exc.param.split(".")[0]
        if top in sent:
            return top
    message = str(exc.message)
    if "nsupported" in message or "not supported" in message:
        return next((name for name in sent if f"'{name}" in message), None)
    return None
