from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.matching import RequirementMatch
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements

AnalysisStatus = Literal["queued", "parsing", "extracting", "scoring", "advising", "done", "failed"]

MAX_JD_CHARS = 15_000
MAX_EXTRA_TEXT_CHARS = 5_000
MAX_SUPPORTING_DOCS = 5


class AnalysisCreate(BaseModel):
    resume_doc_id: UUID
    jd_text: str = Field(min_length=50, max_length=MAX_JD_CHARS)
    extra_text: str | None = Field(default=None, max_length=MAX_EXTRA_TEXT_CHARS)
    supporting_doc_ids: list[UUID] = Field(default_factory=list, max_length=MAX_SUPPORTING_DOCS)


class AnalysisCreated(BaseModel):
    id: str
    status: AnalysisStatus


class AnalysisRecord(BaseModel):
    id: str
    user_id: str
    resume_doc_id: str | None
    jd_doc_id: str | None
    supporting_doc_ids: list[str]
    status: AnalysisStatus
    error: str | None
    fit_score: int | None = None
    potential_score: int | None = None
    scoring_version: str | None = None
    prompt_versions: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class LLMUsage(BaseModel):
    calls: int
    cached_calls: int
    input_tokens: int
    output_tokens: int


class AnalysisResponse(BaseModel):
    id: str
    status: AnalysisStatus
    error: str | None
    created_at: datetime
    updated_at: datetime
    prompt_versions: dict[str, Any]
    fit_score: int | None
    potential_score: int | None
    scoring_version: str | None
    student_profile: StudentProfile | None
    job_requirements: JobRequirements | None
    matches: list[RequirementMatch] | None
    llm_usage: LLMUsage
