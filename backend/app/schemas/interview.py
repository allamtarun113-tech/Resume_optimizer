"""Interview prep: question bank rows, project templates, the stored set, the LLM schema."""

from typing import Literal

from pydantic import BaseModel, Field

BankCategory = Literal["technical", "general", "personal"]
Dimension = Literal[
    "overview",
    "architecture",
    "data",
    "trade-offs",
    "failures",
    "metrics",
    "testing",
    "deployment",
    "scale",
    "security",
    "collaboration",
    "reflection",
]


class BankQuestion(BaseModel):
    """A question from the ingested corpus (interview_questions table)."""

    id: str
    text: str
    category: BankCategory
    topics: list[str]
    role_tags: list[str]
    difficulty: str | None
    source_repo: str
    source_path: str
    source_url: str
    license: str
    similarity: float | None = None


class ProjectTemplate(BaseModel):
    """Hand-curated deep-dive template. Placeholders: {project}, {tech}, {tech2}, {metric}."""

    id: str
    text: str
    dimension: Dimension
    facets: list[str]  # "any", or project facets such as "ml", "backend", "frontend"


class BackgroundTemplate(BaseModel):
    """Background question about one of the student's jobs, degrees or certifications."""

    id: str
    kind: Literal["experience", "education", "certification"]
    text: str


class QuestionSource(BaseModel):
    kind: Literal["github", "template"]
    label: str  # "owner/repo" or "Resume Optimizer project deep-dive bank"
    url: str | None
    license: str | None
    template_id: str | None = None


class InterviewQuestion(BaseModel):
    text: str
    category: Literal["technical", "general", "personal", "project"]
    topic: str | None = None
    dimension: str | None = None
    source: QuestionSource


class ProjectQuestions(BaseModel):
    project: str
    technologies: list[str]
    questions: list[InterviewQuestion]


# Bumped when interview sets get bigger or better; older stored sets are regenerated.
INTERVIEW_SET_VERSION = "2"


class InterviewSet(BaseModel):
    personal: list[InterviewQuestion]
    projects: list[ProjectQuestions]
    technical: list[InterviewQuestion]
    general: list[InterviewQuestion]
    version: str | None = None  # INTERVIEW_SET_VERSION when generated


# -- InterviewPrep LLM output (strict schema: no defaults) ---------------------------------


class FilledTemplate(BaseModel):
    project_id: str = Field(description='Project id as given, e.g. "P1".')
    template_id: str = Field(description='Template id as given, e.g. "T7".')
    question: str = Field(
        description="The template rewritten for this project using only its given details."
    )


class InterviewSelection(BaseModel):
    technical_ids: list[str] = Field(description="Chosen technical question ids (Q...).")
    general_ids: list[str] = Field(description="Chosen behavioral question ids (G...).")
    personal_ids: list[str] = Field(description="Chosen background question ids (G...).")
    project_questions: list[FilledTemplate]
