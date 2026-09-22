import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core import auth
from tests.conftest import JWT_SECRET, SUPABASE_URL

USER_ID = "8d0f3c1e-1111-4222-8333-944455556666"


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims = {
        "sub": USER_ID,
        "email": "student@example.com",
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def _hs256(**overrides: Any) -> str:
    return jwt.encode(_claims(**overrides), JWT_SECRET, algorithm="HS256")


def test_health_is_public(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_me_requires_token(client: TestClient) -> None:
    assert client.get("/health/me").status_code == 401


def test_me_with_valid_hs256_token(client: TestClient) -> None:
    res = client.get("/health/me", headers={"Authorization": f"Bearer {_hs256()}"})
    assert res.status_code == 200
    assert res.json() == {"user_id": USER_ID, "email": "student@example.com"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 10},
        {"aud": "anon"},
        {"iss": "https://other.supabase.co/auth/v1"},
    ],
    ids=["expired", "wrong-audience", "wrong-issuer"],
)
def test_me_rejects_invalid_claims(client: TestClient, overrides: dict[str, Any]) -> None:
    token = _hs256(**overrides)
    res = client.get("/health/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_me_rejects_wrong_secret(client: TestClient) -> None:
    token = jwt.encode(_claims(), "another-secret-at-least-32-bytes-long", algorithm="HS256")
    res = client.get("/health/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_me_rejects_garbage_token(client: TestClient) -> None:
    res = client.get("/health/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_me_with_asymmetric_es256_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), private_key, algorithm="ES256", headers={"kid": "k1"})

    class FakeJWKClient:
        def get_signing_key_from_jwt(self, _token: str) -> Any:
            return private_key.public_key()

    monkeypatch.setattr(auth, "_jwks_client", lambda _url: FakeJWKClient())
    res = client.get("/health/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user_id"] == USER_ID
