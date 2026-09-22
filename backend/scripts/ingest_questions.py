"""Build the interview question corpus (offline; never runs during user requests).

Run from backend/:
    uv run python -m scripts.ingest_questions            # fetch, parse, embed, load
    uv run python -m scripts.ingest_questions --dry-run  # fetch + parse + stats only

1. fetch: files listed in ingestion/sources.yaml via the GitHub MCP server (read-only),
   cached under ingestion/.cache/raw (use --refresh to refetch).
2. parse: markdown -> question records (app/ingestion/questions.py).
3. dedupe: exact (normalized-text hash), then near-duplicates (embedding cosine > 0.95);
   earlier sources win.
4. embed: text-embedding-3-small, cached in ingestion/.cache/embeddings.json.
5. load: upsert into interview_questions and delete rows no longer produced.

Needs GITHUB_PERSONAL_ACCESS_TOKEN, OPENAI_API_KEY, SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY in backend/.env.
"""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import httpx
import numpy as np
import yaml

from app.core.config import get_settings
from app.db.supabase import _auth_headers
from app.ingestion.github_mcp import GitHubFiles
from app.ingestion.questions import QuestionRecord, Source, parse_file
from app.rag.embeddings import OpenAIEmbedder
from app.skills.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[2] / "ingestion"
SOURCES_FILE = ROOT / "sources.yaml"
CACHE = ROOT / ".cache"
NEAR_DUPLICATE = 0.95
LOAD_BATCH = 200
PAGE = 1000  # PostgREST returns at most 1000 rows per request
RETRIES = 3


def load_sources() -> list[Source]:
    return [Source.model_validate(s) for s in yaml.safe_load(SOURCES_FILE.read_text())["sources"]]


def raw_path(source: Source, path: str) -> Path:
    return CACHE / "raw" / source.repo.replace("/", "__") / path


async def fetch(sources: list[Source], token: str, refresh: bool) -> None:
    todo = [
        (s, f.path) for s in sources for f in s.files if refresh or not raw_path(s, f.path).exists()
    ]
    if not todo:
        print("fetch: all files cached")
        return
    async with GitHubFiles(token) as gh:
        for source, path in todo:
            owner, repo = source.repo.split("/")
            text = await gh.read(owner, repo, path, source.ref)
            target = raw_path(source, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(f"fetch: {source.repo}/{path} ({len(text):,} chars)")


def parse(sources: list[Source]) -> list[QuestionRecord]:
    taxonomy = load_taxonomy()
    records: dict[str, QuestionRecord] = {}
    for source in sources:
        before = len(records)
        for file in source.files:
            markdown = raw_path(source, file.path).read_text(encoding="utf-8")
            for record in parse_file(markdown, source, file, taxonomy):
                records.setdefault(record.text_hash, record)
        print(f"parse: {source.repo:58} +{len(records) - before}")
    return list(records.values())


async def embed(records: list[QuestionRecord], api_key: str, model: str) -> dict[str, list[float]]:
    cache_file = CACHE / "embeddings.json"
    cache: dict[str, list[float]] = (
        json.loads(cache_file.read_text()) if cache_file.exists() else {}
    )
    missing = [r for r in records if r.text_hash not in cache]
    if missing:
        print(f"embed: {len(missing)} new texts with {model}")
        vectors = await OpenAIEmbedder(api_key, model).embed([r.text for r in missing])
        cache.update({r.text_hash: v for r, v in zip(missing, vectors, strict=True)})
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache))
    return {r.text_hash: cache[r.text_hash] for r in records}


def drop_near_duplicates(
    records: list[QuestionRecord], vectors: dict[str, list[float]]
) -> list[QuestionRecord]:
    matrix = np.array([vectors[r.text_hash] for r in records], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    keep: list[int] = []
    kept_matrix = np.empty((0, matrix.shape[1]), dtype=np.float32)
    for i, row in enumerate(matrix):
        if kept_matrix.shape[0] and float((kept_matrix @ row).max()) > NEAR_DUPLICATE:
            continue
        keep.append(i)
        kept_matrix = np.vstack([kept_matrix, row])
    return [records[i] for i in keep]


async def load(records: list[QuestionRecord], vectors: dict[str, list[float]]) -> None:
    settings = get_settings()
    base = f"{settings.supabase_url.rstrip('/')}/rest/v1/interview_questions"
    headers = _auth_headers(settings.supabase_service_role_key)
    async with httpx.AsyncClient(timeout=120, headers=headers) as http:
        for start in range(0, len(records), LOAD_BATCH):
            batch = records[start : start + LOAD_BATCH]
            rows = [
                {**r.model_dump(), "embedding": json.dumps(vectors[r.text_hash])} for r in batch
            ]
            for attempt in range(RETRIES):
                try:
                    response = await http.post(
                        base,
                        params={"on_conflict": "text_hash"},
                        json=rows,
                        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                    )
                    response.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    if attempt == RETRIES - 1:
                        raise
                    print(f"load: batch at {start} failed ({exc}); retrying")
                    await asyncio.sleep(2 * (attempt + 1))
        wanted = {r.text_hash for r in records}
        existing: list[dict[str, str]] = []
        while True:
            page = (
                await http.get(
                    base,
                    params={
                        "select": "id,text_hash",
                        "order": "id",
                        "limit": str(PAGE),
                        "offset": str(len(existing)),
                    },
                )
            ).json()
            existing += page
            if len(page) < PAGE:
                break
        stale = [row["id"] for row in existing if row["text_hash"] not in wanted]
        for start in range(0, len(stale), LOAD_BATCH):
            ids = ",".join(stale[start : start + LOAD_BATCH])
            (await http.delete(base, params={"id": f"in.({ids})"})).raise_for_status()
    print(f"load: upserted {len(records)}, removed {len(stale)} stale")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="fetch + parse + stats only")
    parser.add_argument("--refresh", action="store_true", help="refetch cached files")
    args = parser.parse_args()

    settings = get_settings()
    sources = load_sources()
    await fetch(sources, settings.github_personal_access_token, args.refresh)
    records = parse(sources)
    print(f"parse: {len(records)} unique questions", dict(Counter(r.category for r in records)))
    if args.dry_run:
        return

    vectors = await embed(records, settings.openai_api_key, settings.openai_embedding_model)
    records = drop_near_duplicates(records, vectors)
    print(f"dedupe: {len(records)} after removing near-duplicates")
    by_repo = Counter(r.source_repo for r in records)
    for repo, count in by_repo.most_common():
        print(f"  {repo:58} {count}")
    await load(records, vectors)


if __name__ == "__main__":
    asyncio.run(main())
