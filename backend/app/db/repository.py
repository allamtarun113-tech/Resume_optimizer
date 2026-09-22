"""Data access interface. The app uses SupabaseRepository; tests use an in-memory fake."""

from datetime import datetime
from typing import Any, Protocol

from app.llm.client import LLMStore
from app.schemas.analyses import AnalysisRecord, LLMUsage
from app.schemas.documents import DocumentKind, DocumentRecord
from app.schemas.learning import LearningResource


class Repository(LLMStore, Protocol):
    async def upload_file(self, path: str, data: bytes, content_type: str) -> None: ...

    async def insert_document(
        self,
        *,
        user_id: str,
        kind: DocumentKind,
        filename: str | None,
        storage_path: str | None,
        extracted_text: str,
        text_hash: str,
    ) -> DocumentRecord: ...

    async def get_documents(self, user_id: str, ids: list[str]) -> list[DocumentRecord]: ...

    async def count_analyses_since(self, user_id: str, since: datetime) -> int: ...

    async def insert_analysis(
        self,
        *,
        user_id: str,
        resume_doc_id: str,
        jd_doc_id: str,
        supporting_doc_ids: list[str],
    ) -> AnalysisRecord: ...

    async def update_analysis(self, analysis_id: str, **fields: Any) -> None: ...

    async def get_analysis(self, user_id: str, analysis_id: str) -> AnalysisRecord | None: ...

    async def save_analysis_results(self, analysis_id: str, **fields: Any) -> None: ...

    async def get_analysis_results(self, analysis_id: str) -> dict[str, Any] | None: ...

    async def get_llm_usage(self, analysis_id: str) -> LLMUsage: ...

    async def get_learning_resources(self, skill_ids: list[str]) -> list[LearningResource]: ...
