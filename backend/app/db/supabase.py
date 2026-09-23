"""Repository backed by Supabase's REST APIs (PostgREST + Storage) using the secret key.

The secret key bypasses RLS, so every user-facing query here filters by user_id.
"""

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.llm.client import LLMCallRecord
from app.schemas.ai_settings import AiSettingsRecord
from app.schemas.analyses import AnalysisRecord, LLMUsage
from app.schemas.documents import DocumentKind, DocumentRecord
from app.schemas.interview import BankQuestion
from app.schemas.learning import LearningResource

logger = logging.getLogger(__name__)

UPLOADS_BUCKET = "uploads"


class DatabaseError(RuntimeError):
    pass


def _auth_headers(key: str) -> dict[str, str]:
    headers = {"apikey": key}
    # Legacy service_role keys are JWTs and also go in Authorization. New `sb_secret_...`
    # keys must only be sent as `apikey`; the API gateway handles the rest.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class SupabaseRepository:
    def __init__(self, http: httpx.AsyncClient, supabase_url: str, secret_key: str) -> None:
        if not supabase_url or not secret_key:
            raise DatabaseError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        self._http = http
        self._base = supabase_url.rstrip("/")
        self._headers = _auth_headers(secret_key)

    # -- low-level helpers --------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        response = await self._http.request(
            method,
            f"{self._base}{path}",
            params=params,
            json=json,
            content=content,
            headers={**self._headers, **(headers or {})},
        )
        if response.is_error:
            logger.error(
                "Supabase %s %s -> %s: %s", method, path, response.status_code, response.text[:500]
            )
            raise DatabaseError(f"Supabase request failed ({response.status_code})")
        return response

    async def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = await self._request("GET", f"/rest/v1/{table}", params=params)
        rows: list[dict[str, Any]] = response.json()
        return rows

    async def _insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(
            "POST", f"/rest/v1/{table}", json=row, headers={"Prefer": "return=representation"}
        )
        created: dict[str, Any] = response.json()[0]
        return created

    # -- storage ------------------------------------------------------------------------

    async def upload_file(self, path: str, data: bytes, content_type: str) -> None:
        await self._request(
            "POST",
            f"/storage/v1/object/{UPLOADS_BUCKET}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "false"},
        )

    # -- documents ----------------------------------------------------------------------

    async def insert_document(
        self,
        *,
        user_id: str,
        kind: DocumentKind,
        filename: str | None,
        storage_path: str | None,
        extracted_text: str,
        text_hash: str,
    ) -> DocumentRecord:
        row = await self._insert(
            "documents",
            {
                "user_id": user_id,
                "kind": kind,
                "filename": filename,
                "storage_path": storage_path,
                "extracted_text": extracted_text,
                "text_hash": text_hash,
            },
        )
        return DocumentRecord.model_validate(row)

    async def get_documents(self, user_id: str, ids: list[str]) -> list[DocumentRecord]:
        if not ids:
            return []
        rows = await self._select(
            "documents",
            {"select": "*", "user_id": f"eq.{user_id}", "id": f"in.({','.join(ids)})"},
        )
        return [DocumentRecord.model_validate(r) for r in rows]

    # -- analyses -----------------------------------------------------------------------

    async def count_uploads_since(self, user_id: str, since: datetime) -> int:
        response = await self._request(
            "HEAD",
            "/rest/v1/documents",
            params={
                "select": "id",
                "user_id": f"eq.{user_id}",
                "kind": "in.(resume,supporting)",
                "created_at": f"gte.{since.isoformat()}",
            },
            headers={"Prefer": "count=exact"},
        )
        return int(response.headers.get("content-range", "*/0").rsplit("/", 1)[-1])

    async def list_analyses(self, user_id: str, limit: int) -> list[AnalysisRecord]:
        rows = await self._select(
            "analyses",
            {
                "select": "*",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
        return [AnalysisRecord.model_validate(r) for r in rows]

    async def get_role_titles(
        self, analysis_ids: list[str]
    ) -> dict[str, tuple[str | None, str | None]]:
        if not analysis_ids:
            return {}
        rows = await self._select(
            "analysis_results",
            {
                "select": "analysis_id,role:job_requirements->>role_title,"
                "company:job_requirements->>company",
                "analysis_id": f"in.({','.join(analysis_ids)})",
            },
        )
        return {r["analysis_id"]: (r["role"], r["company"]) for r in rows}

    async def delete_analysis(self, user_id: str, analysis_id: str) -> bool:
        response = await self._request(
            "DELETE",
            "/rest/v1/analyses",
            params={"id": f"eq.{analysis_id}", "user_id": f"eq.{user_id}"},
            headers={"Prefer": "return=representation"},
        )
        return bool(response.json())

    async def insert_analysis(
        self,
        *,
        user_id: str,
        resume_doc_id: str,
        jd_doc_id: str,
        supporting_doc_ids: list[str],
    ) -> AnalysisRecord:
        row = await self._insert(
            "analyses",
            {
                "user_id": user_id,
                "resume_doc_id": resume_doc_id,
                "jd_doc_id": jd_doc_id,
                "supporting_doc_ids": supporting_doc_ids,
            },
        )
        return AnalysisRecord.model_validate(row)

    async def update_analysis(self, analysis_id: str, **fields: Any) -> None:
        await self._request(
            "PATCH", "/rest/v1/analyses", params={"id": f"eq.{analysis_id}"}, json=fields
        )

    async def get_analysis(self, user_id: str, analysis_id: str) -> AnalysisRecord | None:
        rows = await self._select(
            "analyses", {"select": "*", "id": f"eq.{analysis_id}", "user_id": f"eq.{user_id}"}
        )
        return AnalysisRecord.model_validate(rows[0]) if rows else None

    async def save_analysis_results(self, analysis_id: str, **fields: Any) -> None:
        await self._request(
            "POST",
            "/rest/v1/analysis_results",
            params={"on_conflict": "analysis_id"},
            json={"analysis_id": analysis_id, **fields},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    async def get_analysis_results(self, analysis_id: str) -> dict[str, Any] | None:
        rows = await self._select(
            "analysis_results", {"select": "*", "analysis_id": f"eq.{analysis_id}"}
        )
        return rows[0] if rows else None

    # -- LLM cache and accounting (LLMStore) ---------------------------------------------

    async def get_cached(self, key: str) -> dict[str, Any] | None:
        rows = await self._select("llm_cache", {"select": "response", "key": f"eq.{key}"})
        return rows[0]["response"] if rows else None

    async def put_cached(
        self, key: str, *, agent: str, model: str, prompt_version: str, response: dict[str, Any]
    ) -> None:
        await self._request(
            "POST",
            "/rest/v1/llm_cache",
            params={"on_conflict": "key"},
            json={
                "key": key,
                "agent": agent,
                "model": model,
                "prompt_version": prompt_version,
                "response": response,
            },
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
        )

    async def log_call(self, record: LLMCallRecord) -> None:
        await self._request(
            "POST",
            "/rest/v1/llm_calls",
            json=asdict(record),
            headers={"Prefer": "return=minimal"},
        )

    async def get_llm_usage(self, analysis_id: str) -> LLMUsage:
        rows = await self._select(
            "llm_calls",
            {"select": "cached,input_tokens,output_tokens", "analysis_id": f"eq.{analysis_id}"},
        )
        return LLMUsage(
            calls=len(rows),
            cached_calls=sum(1 for r in rows if r["cached"]),
            input_tokens=sum(r["input_tokens"] for r in rows),
            output_tokens=sum(r["output_tokens"] for r in rows),
        )

    # -- learning resources ----------------------------------------------------------------

    async def get_learning_resources(self, skill_ids: list[str]) -> list[LearningResource]:
        if not skill_ids:
            return []
        rows = await self._select(
            "learning_resources",
            {
                "select": "skill_id,title,url,type,level,est_hours,free",
                "skill_id": f"in.({','.join(skill_ids)})",
            },
        )
        return [LearningResource.model_validate(r) for r in rows]

    # -- interview prep ----------------------------------------------------------------------

    async def get_cached_embeddings(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        rows = await self._select(
            "embedding_cache", {"select": "key,embedding", "key": f"in.({','.join(keys)})"}
        )
        # pgvector values come back as "[0.1,0.2,...]" strings.
        return {r["key"]: json.loads(r["embedding"]) for r in rows}

    async def put_cached_embeddings(self, model: str, vectors: dict[str, list[float]]) -> None:
        if not vectors:
            return
        await self._request(
            "POST",
            "/rest/v1/embedding_cache",
            params={"on_conflict": "key"},
            json=[
                {"key": k, "model": model, "embedding": json.dumps(v)} for k, v in vectors.items()
            ],
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
        )

    async def match_interview_questions(
        self,
        embedding: list[float],
        *,
        k: int,
        category: str | None,
        topics: list[str] | None,
        role_tags: list[str] | None,
    ) -> list[BankQuestion]:
        response = await self._request(
            "POST",
            "/rest/v1/rpc/match_interview_questions",
            json={
                "query_embedding": json.dumps(embedding),
                "match_count": k,
                "filter_category": category,
                "filter_topics": topics,
                "filter_roles": role_tags,
            },
        )
        return [BankQuestion.model_validate({**r, "id": str(r["id"])}) for r in response.json()]

    async def list_bank_questions(self, categories: list[str]) -> list[BankQuestion]:
        rows = await self._select(
            "interview_questions",
            {
                "select": "id,text,category,topics,role_tags,difficulty,source_repo,"
                "source_path,source_url,license",
                "category": f"in.({','.join(categories)})",
                "order": "text_hash",
            },
        )
        return [BankQuestion.model_validate(r) for r in rows]

    async def get_interview_set(self, analysis_id: str) -> dict[str, Any] | None:
        rows = await self._select(
            "interview_sets", {"select": "questions", "analysis_id": f"eq.{analysis_id}"}
        )
        return rows[0]["questions"] if rows else None

    async def save_interview_set(
        self, analysis_id: str, questions: dict[str, Any], *, replace: bool = False
    ) -> None:
        # Without replace, the first stored set wins (two racing requests store one set).
        resolution = "merge-duplicates" if replace else "ignore-duplicates"
        await self._request(
            "POST",
            "/rest/v1/interview_sets",
            params={"on_conflict": "analysis_id"},
            json={"analysis_id": analysis_id, "questions": questions},
            headers={"Prefer": f"resolution={resolution},return=minimal"},
        )

    # -- per-user AI settings ------------------------------------------------------------

    async def get_ai_settings(self, user_id: str) -> AiSettingsRecord | None:
        rows = await self._select("user_ai_settings", {"select": "*", "user_id": f"eq.{user_id}"})
        return AiSettingsRecord.model_validate(rows[0]) if rows else None

    async def save_ai_settings(
        self,
        *,
        user_id: str,
        encrypted_api_key: str,
        key_last4: str,
        model_small: str,
        model_large: str | None,
    ) -> None:
        await self._request(
            "POST",
            "/rest/v1/user_ai_settings",
            params={"on_conflict": "user_id"},
            json={
                "user_id": user_id,
                "encrypted_api_key": encrypted_api_key,
                "key_last4": key_last4,
                "model_small": model_small,
                "model_large": model_large,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    async def delete_ai_settings(self, user_id: str) -> None:
        await self._request(
            "DELETE", "/rest/v1/user_ai_settings", params={"user_id": f"eq.{user_id}"}
        )
