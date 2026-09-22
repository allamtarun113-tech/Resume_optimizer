"""Matching and scoring models: Matcher, Scorer and GapClassifier outputs, plus the
EvidenceMatcher LLM schema."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.requirements import Importance, RequirementCategory

EvidenceKind = Literal["skill", "project", "experience", "education", "certification"]
MatchMethod = Literal["taxonomy", "implied", "fuzzy", "llm", "none"]
Bucket = Literal[
    "strong_in_resume", "weak_in_resume", "missing_from_resume_but_evidenced", "true_gap"
]


class EvidenceRef(BaseModel):
    """One piece of the student's evidence for a requirement."""

    kind: EvidenceKind
    index: int  # position in the StudentProfile list of that kind
    context: str  # skill context, or the kind for projects/experience/education/certs
    source: str  # "resume" | "supplementary:<doc_id>"
    label: str  # skill name, project name, job title...
    snippet: str  # verbatim evidence quote
    direct: bool  # False when it only implies the requirement


class RequirementEvidence(BaseModel):
    """Matcher output for one requirement."""

    requirement_index: int
    skill_id: str | None
    method: MatchMethod
    evidence: list[EvidenceRef]


class RequirementMatch(BaseModel):
    """Scorer + GapClassifier output for one requirement."""

    requirement_index: int
    name: str
    category: RequirementCategory
    importance: Importance
    min_years: float | None
    skill_id: str | None
    method: MatchMethod
    weight: float
    resume_strength: float
    best_strength: float  # using the resume and all supplementary material
    resume_years: float | None
    total_years: float | None
    bucket: Bucket
    evidence: list[EvidenceRef]


class ScoreResult(BaseModel):
    scoring_version: str
    fit_score: int
    potential_score: int
    matches: list[RequirementMatch]


# -- EvidenceMatcher LLM output (strict schema: no defaults) --------------------------------


class RequirementJudgement(BaseModel):
    requirement_id: str = Field(description='Requirement id as given, e.g. "R3".')
    relation: Literal["direct", "implied", "none"] = Field(
        description="direct: the evidence shows this exact requirement (or a synonym or a "
        "more specific instance of it). implied: related evidence suggests it but it is not "
        "stated. none: no evidence."
    )
    evidence_ids: list[str] = Field(
        description='Ids of the evidence items that support it, e.g. ["K4", "P1"]. Empty for none.'
    )


class EvidenceJudgements(BaseModel):
    judgements: list[RequirementJudgement]
