"""Agents 6 and 7: Scorer and GapClassifier (no LLM). Thin wrappers over app.scoring."""

from datetime import date
from fractions import Fraction

from app.schemas.matching import (
    Bucket,
    EvidenceRef,
    RequirementEvidence,
    RequirementMatch,
    ScoreResult,
)
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements, Requirement
from app.scoring.engine import (
    classify,
    evidence_strength,
    experience_strength,
    experience_years,
    fit_score,
    requirement_weight,
)
from app.scoring.weights import SCORING_VERSION


class GapClassifier:
    name = "gap_classifier"
    uses_llm = False

    def classify(self, resume_strength: Fraction, best_strength: Fraction) -> Bucket:
        return classify(resume_strength, best_strength)


def _years(refs: list[EvidenceRef], profile: StudentProfile, as_of: date) -> Fraction | None:
    # Only jobs judged directly relevant count towards years; merely related jobs don't.
    jobs = sorted({r.index for r in refs if r.kind == "experience" and r.direct})
    return experience_years(
        ((profile.experience[i].start, profile.experience[i].end) for i in jobs), as_of
    )


class Scorer:
    name = "scorer"
    uses_llm = False

    def __init__(self, gap_classifier: GapClassifier | None = None) -> None:
        self._gaps = gap_classifier or GapClassifier()

    def _strength(
        self, req: Requirement, refs: list[EvidenceRef], profile: StudentProfile, as_of: date
    ) -> tuple[Fraction, Fraction | None]:
        if req.category == "experience" and req.min_years:
            years = _years(refs, profile, as_of)
            return experience_strength(years, Fraction(str(req.min_years)), refs), years
        return evidence_strength(req.category, refs), None

    def run(
        self,
        requirements: JobRequirements,
        evidence: list[RequirementEvidence],
        profile: StudentProfile,
        *,
        as_of: date,
    ) -> ScoreResult:
        """`as_of` resolves "present" end dates; the pipeline passes the analysis date."""
        matches: list[RequirementMatch] = []
        weighted_resume: list[tuple[Fraction, Fraction]] = []
        weighted_best: list[tuple[Fraction, Fraction]] = []
        for req, ev in zip(requirements.requirements, evidence, strict=True):
            weight = requirement_weight(req.importance, req.category)
            resume_refs = [r for r in ev.evidence if r.source == "resume"]
            resume_strength, resume_years = self._strength(req, resume_refs, profile, as_of)
            best_strength, total_years = self._strength(req, ev.evidence, profile, as_of)
            best_strength = max(best_strength, resume_strength)
            weighted_resume.append((weight, resume_strength))
            weighted_best.append((weight, best_strength))
            matches.append(
                RequirementMatch(
                    requirement_index=ev.requirement_index,
                    name=req.name,
                    category=req.category,
                    importance=req.importance,
                    min_years=req.min_years,
                    skill_id=ev.skill_id,
                    method=ev.method,
                    weight=float(weight),
                    resume_strength=float(resume_strength),
                    best_strength=float(best_strength),
                    resume_years=float(resume_years) if resume_years is not None else None,
                    total_years=float(total_years) if total_years is not None else None,
                    bucket=self._gaps.classify(resume_strength, best_strength),
                    evidence=ev.evidence,
                )
            )
        return ScoreResult(
            scoring_version=SCORING_VERSION,
            fit_score=fit_score(weighted_resume),
            potential_score=fit_score(weighted_best),
            matches=matches,
        )
