from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

# Supabase signs user access tokens with this audience.
_AUDIENCE = "authenticated"
_ASYMMETRIC_ALGS = ["ES256", "RS256", "EdDSA"]


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # Caches signing keys in-process; refetches on unknown key IDs.
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600)


def decode_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Verify a Supabase access token.

    Supports both the current asymmetric signing keys (verified via JWKS) and
    the legacy HS256 shared secret.
    """
    alg = jwt.get_unverified_header(token).get("alg")
    common: dict[str, Any] = {"audience": _AUDIENCE, "issuer": settings.supabase_issuer}

    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not set")
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **common)

    if alg not in _ASYMMETRIC_ALGS:
        raise jwt.InvalidTokenError(f"Unsupported JWT algorithm: {alg}")
    key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(token, key, algorithms=_ASYMMETRIC_ALGS, **common)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_supabase_jwt(credentials.credentials, settings)
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        raise unauthorized from exc

    return CurrentUser(id=claims["sub"], email=claims.get("email"))
