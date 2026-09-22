"""Write the FastAPI OpenAPI spec to frontend/lib/openapi.json (source for TS types).

Run from backend/:  uv run python -m scripts.export_openapi
Then in frontend/:  pnpm gen:api
"""

import json
from pathlib import Path

from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "openapi.json"


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render())
    print(f"Wrote {OUTPUT}")
