import pytest

from app.core.config import Settings

VERCEL = "https://resume-optimizer.vercel.app"


@pytest.mark.parametrize(
    "raw",
    [
        f'["{VERCEL}", "http://localhost:3000"]',
        f'["{VERCEL}/", "http://localhost:3000/"]',
        f"{VERCEL}, http://localhost:3000",
        f"{VERCEL}/,http://localhost:3000",
    ],
    ids=["json", "json-trailing-slash", "comma", "comma-trailing-slash"],
)
def test_allowed_origins_formats(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", raw)
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == [VERCEL, "http://localhost:3000"]
