from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai.models import InvalidApiKey, default_model, usable_models
from app.api.deps import get_llm_client, get_model_catalog, get_repository, get_user_ai
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.crypto import CryptoError, decrypt, encrypt
from app.main import create_app
from tests.conftest import ENCRYPTION_KEY
from tests.fakes import InMemoryRepository

pytestmark = pytest.mark.anyio

USER = CurrentUser(id="11111111-1111-4111-8111-111111111111", email="a@example.com")
GOOD_KEY = "sk-proj-" + "a" * 40 + "WXYZ"
MODEL_IDS = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini", "gpt-4o-mini-tts", "o3", "dall-e-3"]


class FakeCatalog:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def list_models(self, api_key: str) -> list[str]:
        self.keys.append(api_key)
        if api_key != GOOD_KEY:
            raise InvalidApiKey("OpenAI rejected this API key.")
        return MODEL_IDS


# -- crypto -------------------------------------------------------------------------------


def test_encrypt_round_trip_and_ciphertext_hides_the_key() -> None:
    token = encrypt(GOOD_KEY, ENCRYPTION_KEY)
    assert GOOD_KEY not in token
    assert decrypt(token, ENCRYPTION_KEY) == GOOD_KEY


@pytest.mark.parametrize("bad", ["", "not-a-fernet-key"])
def test_bad_encryption_key(bad: str) -> None:
    with pytest.raises(CryptoError):
        encrypt("x", bad)


def test_decrypt_with_another_key_fails() -> None:
    other = "T3RoZXJGYWtlRmVybmV0S2V5Rm9yVGVzdHMwMDAwMDA="
    with pytest.raises(CryptoError):
        decrypt(encrypt("secret", ENCRYPTION_KEY), other)


# -- model list -----------------------------------------------------------------------------


def test_usable_models_filters_and_orders() -> None:
    ids = [
        "gpt-5.4-mini",
        "gpt-4o-mini",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-mini-tts",
        "gpt-realtime",
        "gpt-image-1",
        "gpt-5-pro",
        "gpt-5-chat-latest",
        "gpt-5.1-codex",
        "o3",
        "o4-mini",
        "gpt-3.5-turbo",
        "gpt-4",
        "text-embedding-3-small",
        "gpt-4o-search-preview",
        "gpt-6-sol",
    ]
    assert usable_models(ids) == ["gpt-4o-mini", "gpt-5.4-mini", "gpt-6-sol", "o3", "o4-mini"]
    assert default_model(["gpt-5-mini", "gpt-4o-mini"]) == "gpt-4o-mini"
    assert default_model(["o3"]) == "o3"
    assert default_model([]) is None


# -- settings API -------------------------------------------------------------------------


@pytest.fixture
def api(settings: Settings) -> Iterator[tuple[TestClient, InMemoryRepository, FakeCatalog]]:
    repo, catalog = InMemoryRepository(), FakeCatalog()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_model_catalog] = lambda: catalog
    with TestClient(app) as client:
        yield client, repo, catalog


def test_settings_lifecycle(api: tuple[TestClient, InMemoryRepository, FakeCatalog]) -> None:
    client, repo, _ = api
    assert client.get("/settings/ai").json()["has_key"] is False

    models = client.post("/settings/ai/models", json={"api_key": GOOD_KEY}).json()
    assert models == {
        "models": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini", "o3"],
        "default": "gpt-4o-mini",
    }

    saved = client.put(
        "/settings/ai",
        json={"api_key": GOOD_KEY, "model_small": "gpt-4o-mini", "model_large": "o3"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["has_key"] and body["key_last4"] == "WXYZ"
    assert body["model_small"] == "gpt-4o-mini" and body["model_large"] == "o3"
    stored = repo.ai_settings[USER.id]
    assert GOOD_KEY not in stored.encrypted_api_key  # encrypted at rest
    assert decrypt(stored.encrypted_api_key, ENCRYPTION_KEY) == GOOD_KEY
    assert GOOD_KEY not in client.get("/settings/ai").text  # never returned

    # Change models only: the saved key is reused (and re-validated).
    changed = client.put(
        "/settings/ai", json={"model_small": "gpt-5-mini", "model_large": "gpt-5-mini"}
    )
    assert changed.json()["model_small"] == "gpt-5-mini"
    assert changed.json()["model_large"] is None  # same as small -> stored as "not set"
    assert client.post("/settings/ai/models", json={}).status_code == 200

    assert client.delete("/settings/ai").status_code == 204
    assert client.get("/settings/ai").json()["has_key"] is False


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"api_key": "sk-wrong-" + "x" * 30, "model_small": "gpt-4o-mini"}, "rejected"),
        ({"api_key": GOOD_KEY, "model_small": "gpt-4o-mini-tts"}, "isn't available"),
        (
            {"api_key": GOOD_KEY, "model_small": "gpt-4o-mini", "model_large": "dall-e-3"},
            "isn't available",
        ),
        ({"model_small": "gpt-4o-mini"}, "Paste your OpenAI API key"),  # nothing saved yet
    ],
)
def test_settings_validation(
    api: tuple[TestClient, InMemoryRepository, FakeCatalog], payload: dict[str, Any], detail: str
) -> None:
    client, repo, _ = api
    res = client.put("/settings/ai", json=payload)
    assert res.status_code == 422
    assert detail in res.json()["detail"]
    assert USER.id not in repo.ai_settings


def test_models_endpoint_rejects_bad_keys(
    api: tuple[TestClient, InMemoryRepository, FakeCatalog],
) -> None:
    client, _, _ = api
    assert (
        client.post("/settings/ai/models", json={"api_key": "sk-nope-" + "x" * 30}).status_code
        == 422
    )
    assert client.post("/settings/ai/models", json={}).status_code == 422


# -- every AI request uses the user's own key ------------------------------------------------


def test_ai_endpoints_require_a_key(
    api: tuple[TestClient, InMemoryRepository, FakeCatalog],
) -> None:
    client, _, _ = api
    body = {"resume_doc_id": "11111111-1111-4111-8111-111111111111", "jd_text": "x" * 60}
    res = client.post("/analyses", json=body)
    assert res.status_code == 428
    assert res.json()["detail"] == "Add your OpenAI API key in Settings to run analyses."


async def test_user_ai_and_llm_client_use_the_saved_key(settings: Settings) -> None:
    repo = InMemoryRepository()
    with pytest.raises(HTTPException) as missing:
        await get_user_ai(USER, repo, settings)
    assert missing.value.status_code == 428

    await repo.save_ai_settings(
        user_id=USER.id,
        encrypted_api_key=encrypt(GOOD_KEY, ENCRYPTION_KEY),
        key_last4="WXYZ",
        model_small="gpt-5-mini",
        model_large=None,
    )
    ai = await get_user_ai(USER, repo, settings)
    assert (ai.api_key, ai.model_small, ai.model_large) == (GOOD_KEY, "gpt-5-mini", None)

    request: Any = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    llm = get_llm_client(request, settings, repo, ai)
    assert llm.model_for("small") == "gpt-5-mini"
    assert llm.model_for("large") == "gpt-5-mini"
    # One OpenAI client per key, reused across requests.
    again = get_llm_client(request, settings, repo, ai)
    assert again._model is llm._model  # noqa: SLF001


async def test_undecryptable_key_asks_to_re_add(settings: Settings) -> None:
    repo = InMemoryRepository()
    await repo.save_ai_settings(
        user_id=USER.id,
        encrypted_api_key="garbage",
        key_last4="WXYZ",
        model_small="gpt-4o-mini",
        model_large=None,
    )
    with pytest.raises(HTTPException) as exc:
        await get_user_ai(USER, repo, settings)
    assert exc.value.status_code == 428
    assert "add it again" in str(exc.value.detail)
