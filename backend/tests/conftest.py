from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

SUPABASE_URL = "https://test-project.supabase.co"
JWT_SECRET = "test-secret-at-least-32-bytes-long!!"
ENCRYPTION_KEY = "Sm9ZcW5rRmFrZUZlcm5ldEtleUZvclRlc3RzMDAwMDA="  # test-only Fernet key


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        supabase_url=SUPABASE_URL,
        supabase_jwt_secret=JWT_SECRET,
        app_encryption_key=ENCRYPTION_KEY,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
