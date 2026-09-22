"""Terse constructors for profiles, requirements and evidence in tests."""

from typing import Any

from app.schemas.matching import EvidenceJudgements, EvidenceRef, RequirementJudgement
from app.schemas.profile import (
    Certification,
    Education,
    Experience,
    Project,
    SkillMention,
    StudentProfile,
)
from app.schemas.requirements import JobRequirements, Requirement


def skill(
    name: str, context: Any = "skills_section", source: str = "resume", within: str | None = None
) -> SkillMention:
    return SkillMention(
        name=name, context=context, context_name=within, source=source, evidence=name
    )


def project(name: str, tech: list[str], source: str = "resume", summary: str = "") -> Project:
    return Project(
        name=name,
        summary=summary or name,
        role=None,
        technologies=tech,
        highlights=[],
        metrics=[],
        challenges=[],
        start=None,
        end=None,
        url=None,
        source=source,
        evidence=name,
    )


def job(
    title: str,
    org: str,
    start: str | None,
    end: str | None,
    tech: list[str] | None = None,
    kind: Any = "internship",
    source: str = "resume",
) -> Experience:
    return Experience(
        title=title,
        organization=org,
        employment_type=kind,
        start=start,
        end=end,
        technologies=tech or [],
        highlights=[],
        source=source,
        evidence=f"{title}, {org}",
    )


def edu(degree: str, field: str, school: str = "State University") -> Education:
    return Education(
        institution=school,
        degree=degree,
        field_of_study=field,
        start=None,
        end=None,
        grade=None,
        source="resume",
        evidence=f"{degree} {field}",
    )


def cert(name: str, source: str = "resume") -> Certification:
    return Certification(name=name, issuer=None, date=None, source=source, evidence=name)


def profile(
    skills: list[SkillMention] | None = None,
    projects: list[Project] | None = None,
    experience: list[Experience] | None = None,
    education: list[Education] | None = None,
    certifications: list[Certification] | None = None,
) -> StudentProfile:
    return StudentProfile(
        headline=None,
        skills=skills or [],
        projects=projects or [],
        experience=experience or [],
        education=education or [],
        certifications=certifications or [],
    )


def req(
    name: str, category: Any = "skill", importance: Any = "must", min_years: float | None = None
) -> Requirement:
    return Requirement(
        name=name, category=category, importance=importance, min_years=min_years, evidence=name
    )


def reqs(*items: Requirement, title: str = "Engineer") -> JobRequirements:
    return JobRequirements(role_title=title, company=None, seniority=None, requirements=list(items))


def judged(*items: tuple[str, str, list[str]]) -> EvidenceJudgements:
    """judged(("R3", "direct", ["C1"]), ...)"""
    return EvidenceJudgements(
        judgements=[
            RequirementJudgement.model_validate(
                {"requirement_id": rid, "relation": rel, "evidence_ids": ids}
            )
            for rid, rel, ids in items
        ]
    )


def ref(
    context: str = "skills_section",
    source: str = "resume",
    direct: bool = True,
    kind: Any = "skill",
    index: int = 0,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        index=index,
        context=context,
        source=source,
        label="x",
        snippet="x",
        direct=direct,
    )
