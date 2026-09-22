"""JobRequirements: JDAnalyzer output. Strict-schema rules as in schemas/profile.py."""

from typing import Literal

from pydantic import BaseModel, Field

RequirementCategory = Literal["skill", "domain", "experience", "education", "soft_skill"]
Importance = Literal["must", "nice"]
Seniority = Literal["intern", "entry", "mid", "senior", "lead"]


class Requirement(BaseModel):
    name: str = Field(
        description="One atomic requirement, e.g. 'Python', 'REST APIs', "
        "'2+ years backend experience', 'B.Tech in Computer Science'."
    )
    category: RequirementCategory
    importance: Importance = Field(
        description="must = required/essential; nice = preferred/bonus/plus."
    )
    min_years: float | None = Field(description="Minimum years if stated, else null.")
    evidence: str = Field(description="Short verbatim quote from the job description.")


class JobRequirements(BaseModel):
    role_title: str | None
    company: str | None
    seniority: Seniority | None
    requirements: list[Requirement]
