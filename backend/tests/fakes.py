"""In-memory stand-ins for Supabase and OpenAI. Tests never touch the network."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.llm.client import Completion, LLMCallRecord
from app.rag.embeddings import cosine
from app.schemas.analyses import AnalysisRecord, LLMUsage
from app.schemas.documents import DocumentKind, DocumentRecord
from app.schemas.interview import BankQuestion
from app.schemas.learning import LearningResource


class InMemoryRepository:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.documents: dict[str, DocumentRecord] = {}
        self.analyses: dict[str, AnalysisRecord] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.cache: dict[str, dict[str, Any]] = {}
        self.calls: list[LLMCallRecord] = []
        self.status_history: dict[str, list[str]] = {}
        self.resources: list[LearningResource] = []
        self.embedding_cache: dict[str, list[float]] = {}
        self.bank: list[tuple[BankQuestion, list[float]]] = []  # (question, embedding)
        self.interview_sets: dict[str, dict[str, Any]] = {}

    async def upload_file(self, path: str, data: bytes, content_type: str) -> None:
        self.files[path] = data

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
        doc = DocumentRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            kind=kind,
            filename=filename,
            storage_path=storage_path,
            extracted_text=extracted_text,
            text_hash=text_hash,
            created_at=datetime.now(UTC),
        )
        self.documents[doc.id] = doc
        return doc

    async def get_documents(self, user_id: str, ids: list[str]) -> list[DocumentRecord]:
        return [d for i in ids if (d := self.documents.get(i)) is not None and d.user_id == user_id]

    async def count_analyses_since(self, user_id: str, since: datetime) -> int:
        return sum(
            1 for a in self.analyses.values() if a.user_id == user_id and a.created_at >= since
        )

    async def count_uploads_since(self, user_id: str, since: datetime) -> int:
        return sum(
            1
            for d in self.documents.values()
            if d.user_id == user_id and d.kind in ("resume", "supporting") and d.created_at >= since
        )

    async def list_analyses(self, user_id: str, limit: int) -> list[AnalysisRecord]:
        mine = [a for a in self.analyses.values() if a.user_id == user_id]
        return sorted(mine, key=lambda a: a.created_at, reverse=True)[:limit]

    async def get_role_titles(
        self, analysis_ids: list[str]
    ) -> dict[str, tuple[str | None, str | None]]:
        out: dict[str, tuple[str | None, str | None]] = {}
        for aid in analysis_ids:
            reqs = (self.results.get(aid) or {}).get("job_requirements")
            if reqs:
                out[aid] = (reqs.get("role_title"), reqs.get("company"))
        return out

    async def delete_analysis(self, user_id: str, analysis_id: str) -> bool:
        analysis = self.analyses.get(analysis_id)
        if analysis is None or analysis.user_id != user_id:
            return False
        del self.analyses[analysis_id]
        self.results.pop(analysis_id, None)
        self.interview_sets.pop(analysis_id, None)
        return True

    async def insert_analysis(
        self,
        *,
        user_id: str,
        resume_doc_id: str,
        jd_doc_id: str,
        supporting_doc_ids: list[str],
    ) -> AnalysisRecord:
        now = datetime.now(UTC)
        analysis = AnalysisRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            resume_doc_id=resume_doc_id,
            jd_doc_id=jd_doc_id,
            supporting_doc_ids=supporting_doc_ids,
            status="queued",
            error=None,
            prompt_versions={},
            created_at=now,
            updated_at=now,
        )
        self.analyses[analysis.id] = analysis
        self.status_history[analysis.id] = ["queued"]
        return analysis

    async def update_analysis(self, analysis_id: str, **fields: Any) -> None:
        current = self.analyses[analysis_id]
        self.analyses[analysis_id] = current.model_copy(
            update={**fields, "updated_at": datetime.now(UTC)}
        )
        if "status" in fields:
            self.status_history[analysis_id].append(fields["status"])

    async def get_analysis(self, user_id: str, analysis_id: str) -> AnalysisRecord | None:
        analysis = self.analyses.get(analysis_id)
        return analysis if analysis and analysis.user_id == user_id else None

    async def save_analysis_results(self, analysis_id: str, **fields: Any) -> None:
        self.results.setdefault(analysis_id, {}).update(fields)

    async def get_analysis_results(self, analysis_id: str) -> dict[str, Any] | None:
        return self.results.get(analysis_id)

    async def get_cached(self, key: str) -> dict[str, Any] | None:
        return self.cache.get(key)

    async def put_cached(
        self, key: str, *, agent: str, model: str, prompt_version: str, response: dict[str, Any]
    ) -> None:
        self.cache.setdefault(key, response)

    async def log_call(self, record: LLMCallRecord) -> None:
        self.calls.append(record)

    async def get_llm_usage(self, analysis_id: str) -> LLMUsage:
        calls = [c for c in self.calls if c.analysis_id == analysis_id]
        return LLMUsage(
            calls=len(calls),
            cached_calls=sum(c.cached for c in calls),
            input_tokens=sum(c.input_tokens for c in calls),
            output_tokens=sum(c.output_tokens for c in calls),
        )

    async def get_learning_resources(self, skill_ids: list[str]) -> list[LearningResource]:
        return [r for r in self.resources if r.skill_id in skill_ids]

    async def get_cached_embeddings(self, keys: list[str]) -> dict[str, list[float]]:
        return {k: self.embedding_cache[k] for k in keys if k in self.embedding_cache}

    async def put_cached_embeddings(self, model: str, vectors: dict[str, list[float]]) -> None:
        self.embedding_cache.update(vectors)

    async def match_interview_questions(
        self,
        embedding: list[float],
        *,
        k: int,
        category: str | None,
        topics: list[str] | None,
        role_tags: list[str] | None,
    ) -> list[BankQuestion]:
        hits = [
            q.model_copy(update={"similarity": cosine(embedding, vector)})
            for q, vector in self.bank
            if (category is None or q.category == category)
            and (topics is None or set(topics) & set(q.topics))
            and (role_tags is None or set(role_tags) & set(q.role_tags))
        ]
        hits.sort(key=lambda q: -(q.similarity or 0))
        return hits[:k]

    async def list_bank_questions(self, categories: list[str]) -> list[BankQuestion]:
        return [q for q, _ in self.bank if q.category in categories]

    async def get_interview_set(self, analysis_id: str) -> dict[str, Any] | None:
        return self.interview_sets.get(analysis_id)

    async def save_interview_set(self, analysis_id: str, questions: dict[str, Any]) -> None:
        self.interview_sets.setdefault(analysis_id, questions)


Responder = Callable[[str, str], BaseModel]


class FakeModel:
    """StructuredModel that answers from recorded fixtures, keyed by output type name."""

    def __init__(self, responses: dict[str, BaseModel | Responder]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def complete[T: BaseModel](
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        output_type: type[T],
        max_output_tokens: int,
    ) -> Completion[T]:
        self.requests.append(
            {"model": model, "output_type": output_type.__name__, "input_text": input_text}
        )
        answer = self.responses[output_type.__name__]
        if callable(answer):
            answer = answer(model, input_text)
        return Completion(
            parsed=output_type.model_validate(answer.model_dump()),
            input_tokens=len(input_text) // 4,
            output_tokens=100,
        )
