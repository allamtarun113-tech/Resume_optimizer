"""Sync the learning_resources table with ingestion/resources_seed.yaml.

Run from backend/ (needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env):
    uv run python -m scripts.seed_resources

Rows are upserted on (skill_id, url); rows no longer in the file are deleted, so the
YAML file is the single source of truth.
"""

import asyncio
from pathlib import Path

import httpx
import yaml

from app.core.config import get_settings
from app.db.supabase import _auth_headers
from app.schemas.learning import LearningResource
from app.skills.taxonomy import load_taxonomy

SEED_FILE = Path(__file__).resolve().parents[2] / "ingestion" / "resources_seed.yaml"


def load_seed(path: Path = SEED_FILE) -> list[LearningResource]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))["resources"]
    resources = [LearningResource.model_validate(r) for r in rows]
    taxonomy = load_taxonomy()
    unknown = sorted({r.skill_id for r in resources} - set(taxonomy.skills))
    if unknown:
        raise SystemExit(f"Unknown skill ids in {path.name}: {', '.join(unknown)}")
    keys = [(r.skill_id, r.url) for r in resources]
    if len(keys) != len(set(keys)):
        raise SystemExit("Duplicate (skill_id, url) pairs in the seed file")
    return resources


async def main() -> None:
    settings = get_settings()
    resources = load_seed()
    base = f"{settings.supabase_url.rstrip('/')}/rest/v1/learning_resources"
    headers = _auth_headers(settings.supabase_service_role_key)
    async with httpx.AsyncClient(timeout=60, headers=headers) as http:
        response = await http.post(
            base,
            params={"on_conflict": "skill_id,url"},
            json=[r.model_dump() for r in resources],
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        response.raise_for_status()

        existing = (await http.get(base, params={"select": "id,skill_id,url"})).json()
        wanted = {(r.skill_id, r.url) for r in resources}
        stale = [row["id"] for row in existing if (row["skill_id"], row["url"]) not in wanted]
        if stale:
            (await http.delete(base, params={"id": f"in.({','.join(stale)})"})).raise_for_status()
    print(f"Synced {len(resources)} resources; removed {len(stale)} stale rows.")


if __name__ == "__main__":
    asyncio.run(main())
