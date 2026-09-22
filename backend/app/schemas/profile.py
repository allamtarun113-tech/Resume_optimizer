"""StudentProfile: ProfileExtractor output.

These models are sent to OpenAI as a strict JSON schema, so every field is required
(optional values are `X | None`) and there are no defaults. Field descriptions are
part of the schema the model sees.
"""

from typing import Literal

from pydantic import BaseModel, Field

SourceField = Field(
    description='Id of the document this came from, exactly as given, e.g. "RESUME" or "S1".'
)
EvidenceField = Field(
    description="Short verbatim quote (under 200 characters) copied exactly from that document."
)
DateField = Field(description='"YYYY-MM", "YYYY", "present", or null if not stated.')

SkillContext = Literal[
    "skills_section", "project", "experience", "education", "certification", "summary", "other"
]
EmploymentType = Literal[
    "full_time", "part_time", "internship", "freelance", "research", "volunteer", "other"
]


class SkillMention(BaseModel):
    name: str = Field(description="Skill, tool, language or concept, as written.")
    context: SkillContext = Field(description="Where in the document the skill appears.")
    context_name: str | None = Field(
        description="Project or job name when context is project or experience, else null."
    )
    source: str = SourceField
    evidence: str = EvidenceField


class Project(BaseModel):
    name: str
    summary: str = Field(description="One or two sentences on what the project is.")
    role: str | None = Field(description="The student's role, if stated.")
    technologies: list[str]
    highlights: list[str] = Field(
        description="Concrete technical details: what was built, how, design decisions."
    )
    metrics: list[str] = Field(description="Quantified results as stated (numbers, scale).")
    challenges: list[str] = Field(description="Problems faced or solved, if stated.")
    start: str | None = DateField
    end: str | None = DateField
    url: str | None
    source: str = SourceField
    evidence: str = EvidenceField


class Experience(BaseModel):
    title: str
    organization: str
    employment_type: EmploymentType
    start: str | None = DateField
    end: str | None = DateField
    technologies: list[str]
    highlights: list[str] = Field(description="Responsibilities and achievements as stated.")
    source: str = SourceField
    evidence: str = EvidenceField


class Education(BaseModel):
    institution: str
    degree: str | None
    field_of_study: str | None
    start: str | None = DateField
    end: str | None = DateField
    grade: str | None = Field(description="GPA/CGPA/percentage as written, if stated.")
    source: str = SourceField
    evidence: str = EvidenceField


class Certification(BaseModel):
    name: str
    issuer: str | None
    date: str | None = DateField
    source: str = SourceField
    evidence: str = EvidenceField


class StudentProfile(BaseModel):
    headline: str | None = Field(description="The student's own summary line, if any.")
    skills: list[SkillMention] = Field(
        description="One entry per place a skill appears; the same skill may repeat."
    )
    projects: list[Project]
    experience: list[Experience]
    education: list[Education]
    certifications: list[Certification]
