from types import SimpleNamespace
from typing import Any, cast

import httpx2
import openai
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.client import LLMCallRecord, LLMClient, LLMError, OpenAIModel, cache_key
from app.llm.prompts import Prompt, load_prompt, parse_prompt
from tests.fakes import FakeModel, InMemoryRepository

pytestmark = pytest.mark.anyio


class Answer(BaseModel):
    value: str


PROMPT = Prompt(name="test_agent", version="1", text="Say hi.")


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"openai_model_small": "small-model", "openai_model_large": ""}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(
    store: InMemoryRepository | None = None, **settings: Any
) -> tuple[LLMClient, FakeModel, InMemoryRepository]:
    store = store or InMemoryRepository()
    model = FakeModel({"Answer": Answer(value="hi")})
    return LLMClient(_settings(**settings), store, model), model, store


async def _parse(client: LLMClient, input_text: str = "hello", **kwargs: Any) -> Answer:
    return await client.parse(
        agent="test_agent",
        prompt=PROMPT,
        input_text=input_text,
        output_type=Answer,
        max_output_tokens=100,
        analysis_id="a1",
        **kwargs,
    )


# -- prompts -----------------------------------------------------------------------------


def test_parse_prompt_reads_version_and_body() -> None:
    prompt = parse_prompt("x", "---\nversion: 3\n---\nDo the thing.\n")
    assert prompt == Prompt(name="x", version="3", text="Do the thing.")


@pytest.mark.parametrize("raw", ["no front matter", "---\nversion: 1\nbody", "---\n---\nbody"])
def test_parse_prompt_rejects_bad_front_matter(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_prompt("x", raw)


@pytest.mark.parametrize("name", ["profile_extractor", "jd_analyzer"])
def test_agent_prompts_load(name: str) -> None:
    prompt = load_prompt(name)
    assert prompt.version
    assert len(prompt.text) > 200


# -- LLMClient: caching and accounting ---------------------------------------------------


async def test_second_identical_call_is_a_cache_hit() -> None:
    client, model, store = _client()
    assert await _parse(client) == Answer(value="hi")
    assert await _parse(client) == Answer(value="hi")

    assert len(model.requests) == 1
    assert [c.cached for c in store.calls] == [False, True]
    assert store.calls[1].input_tokens == 0
    assert store.calls[0].analysis_id == "a1"


async def test_different_input_misses_cache() -> None:
    client, model, _ = _client()
    await _parse(client, "hello")
    await _parse(client, "hello again")
    assert len(model.requests) == 2


def test_cache_key_depends_on_prompt_version_model_schema_and_input() -> None:
    base = cache_key(PROMPT, "m", Answer, "in")

    class Other(BaseModel):
        value: int

    assert base == cache_key(PROMPT, "m", Answer, "in")
    assert base != cache_key(Prompt("test_agent", "2", PROMPT.text), "m", Answer, "in")
    assert base != cache_key(PROMPT, "m2", Answer, "in")
    assert base != cache_key(PROMPT, "m", Other, "in")
    assert base != cache_key(PROMPT, "m", Answer, "in2")


async def test_stale_cache_entry_that_fails_validation_is_ignored() -> None:
    client, model, store = _client()
    store.cache[cache_key(PROMPT, "small-model", Answer, "hello")] = {"unexpected": 1}
    assert await _parse(client) == Answer(value="hi")
    assert len(model.requests) == 1


async def test_large_tier_falls_back_to_small_model() -> None:
    client, model, _ = _client()
    await _parse(client, tier="large")
    assert model.requests[0]["model"] == "small-model"

    client, model, _ = _client(openai_model_large="big-model")
    await _parse(client, tier="large")
    assert model.requests[0]["model"] == "big-model"


async def test_missing_model_config_raises_llm_error() -> None:
    client, _, _ = _client(openai_model_small="")
    with pytest.raises(LLMError, match="No AI model selected"):
        await _parse(client)


class BrokenStore(InMemoryRepository):
    async def log_call(self, record: LLMCallRecord) -> None:
        raise RuntimeError("db down")

    async def put_cached(self, key: str, **kwargs: Any) -> None:
        raise RuntimeError("db down")


async def test_accounting_and_cache_write_failures_do_not_break_calls() -> None:
    client, _, _ = _client(store=BrokenStore())
    assert await _parse(client) == Answer(value="hi")


# -- OpenAIModel -------------------------------------------------------------------------


def _bad_request(param: str | None, message: str) -> openai.BadRequestError:
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return openai.BadRequestError(
        message,
        response=httpx2.Response(400, request=request),
        body={"param": param, "message": message},
    )


class StubResponses:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(parsed: BaseModel | None, status: str = "completed") -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output_parsed=parsed,
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
    )


def _openai_model(outcomes: list[Any]) -> tuple[OpenAIModel, StubResponses]:
    responses = StubResponses(outcomes)
    stub = cast(openai.AsyncOpenAI, SimpleNamespace(responses=responses))
    return OpenAIModel(_settings(openai_reasoning_effort="low"), client=stub), responses


async def _complete(model: OpenAIModel) -> Any:
    return await model.complete(
        model="m", instructions="i", input_text="x", output_type=Answer, max_output_tokens=50
    )


async def test_openai_model_returns_parsed_output_and_usage() -> None:
    model, responses = _openai_model([_response(Answer(value="ok"))])
    completion = await _complete(model)
    assert completion.parsed == Answer(value="ok")
    assert (completion.input_tokens, completion.output_tokens) == (120, 30)
    call = responses.calls[0]
    assert call["temperature"] == 0
    assert call["reasoning"] == {"effort": "low"}
    assert call["store"] is False
    assert call["text_format"] is Answer


async def test_openai_model_drops_params_the_model_rejects_and_remembers() -> None:
    model, responses = _openai_model(
        [
            _bad_request("temperature", "Unsupported parameter: 'temperature'"),
            _response(Answer(value="ok")),
            _response(Answer(value="again")),
        ]
    )
    assert (await _complete(model)).parsed.value == "ok"
    assert (await _complete(model)).parsed.value == "again"
    assert "temperature" in responses.calls[0]
    assert "temperature" not in responses.calls[1]
    assert "temperature" not in responses.calls[2]  # remembered for this model
    assert responses.calls[1]["reasoning"] == {"effort": "low"}


async def test_openai_model_detects_rejected_param_from_message() -> None:
    model, responses = _openai_model(
        [
            _bad_request(None, "Unsupported parameter: 'reasoning.effort' is not supported"),
            _response(Answer(value="ok")),
        ]
    )
    assert (await _complete(model)).parsed.value == "ok"
    assert "reasoning" not in responses.calls[1]


async def test_openai_model_reraises_unrelated_bad_requests() -> None:
    model, _ = _openai_model([_bad_request("input", "Input too long")])
    with pytest.raises(openai.BadRequestError):
        await _complete(model)


async def test_openai_model_incomplete_and_refusal_raise_llm_error() -> None:
    model, _ = _openai_model([_response(None, status="incomplete")])
    with pytest.raises(LLMError, match="cut off"):
        await _complete(model)

    model, _ = _openai_model([_response(None)])
    with pytest.raises(LLMError, match="declined"):
        await _complete(model)
