"""ResumeAdvisor models: the LLM draft schema and the validated suggestions we store."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.matching import EvidenceRef
from app.schemas.requirements import Importance, RequirementCategory

ResumeSection = Literal[
    "skills", "projects", "experience", "education", "certifications", "summary"
]
SuggestionAction = Literal[
    "add_skill",
    "add_project",
    "expand_project",
    "add_experience",
    "expand_experience",
    "add_certification",
    "add_education_detail",
]

# -- LLM output (strict schema: no defaults) ------------------------------------------------


class SuggestionDraft(BaseModel):
    requirement_ids: list[str] = Field(description='Requirement ids it addresses, e.g. ["R2"].')
    evidence_ids: list[str] = Field(description='Evidence ids it relies on, e.g. ["Q3"].')
    section: ResumeSection = Field(description="Resume section to change.")
    action: SuggestionAction
    target: str | None = Field(
        description="Existing resume entry to edit (project or job name), or null."
    )
    suggested_text: str = Field(
        description="The line or bullet to add to the resume, written for the resume."
    )
    quote: str = Field(
        description="Exact quote copied from the evidence snippet it relies on (no edits)."
    )
    rationale: str = Field(description="One sentence: why this helps for this job.")


class ResumeAdvice(BaseModel):
    suggestions: list[SuggestionDraft]


# -- stored results ------------------------------------------------------------------------


class Suggestion(BaseModel):
    id: str
    requirement_indexes: list[int]
    requirement_names: list[str]
    section: ResumeSection
    action: SuggestionAction
    target: str | None
    suggested_text: str
    rationale: str
    quote: str
    quote_source: str  # "resume" | "supplementary:<doc_id>"
    quote_source_label: str  # "your resume", "your notes", or the uploaded file name
    evidence: list[EvidenceRef]
    uplift: int  # score points gained if applied on its own


class RejectedSuggestion(BaseModel):
    suggested_text: str
    reason: str


class Gap(BaseModel):
    requirement_index: int
    name: str
    category: RequirementCategory
    importance: Importance
    skill_id: str | None


class AdviceResult(BaseModel):
    suggestions: list[Suggestion]
    rejected: list[RejectedSuggestion]
    gaps: list[Gap]
