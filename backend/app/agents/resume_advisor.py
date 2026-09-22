"""Agent 8: ResumeAdvisor (LLM) + EvidenceValidator. Suggests resume changes backed by
evidence the student already has, each with its projected score uplift.

Only requirements whose best strength (all documents) beats their resume strength are
eligible: those are exactly the ones where adding existing evidence raises the score.
"""

import logging
from fractions import Fraction

from pydantic import BaseModel

from app.agents.evidence_validator import EvidenceValidator, RejectedDraft
from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.schemas.advice import (
    AdviceResult,
    Gap,
    RejectedSuggestion,
    ResumeAdvice,
    Suggestion,
)
from app.schemas.matching import EvidenceRef, RequirementMatch, ScoreResult
from app.schemas.profile import StudentProfile
from app.scoring.engine import uplift
from app.skills.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 6_000
MAX_EVIDENCE_ITEMS = 60
_STRENGTH_TEXT = {0.0: "missing", 0.4: "only implied", 0.7: "listed or shown, not both"}


class SourceDoc(BaseModel):
    label: str  # "your resume", "your notes", file name...
    text: str


class AdvisorInput(BaseModel):
    profile: StudentProfile
    score: ScoreResult
    sources: dict[str, SourceDoc]  # "resume" | "supplementary:<doc_id>" -> document


def eligible_matches(score: ScoreResult) -> list[RequirementMatch]:
    return [
        m
        for m in score.matches
        if m.bucket in ("weak_in_resume", "missing_from_resume_but_evidenced")
        and m.best_strength > m.resume_strength
    ]


def gaps(score: ScoreResult) -> list[Gap]:
    return [
        Gap(
            requirement_index=m.requirement_index,
            name=m.name,
            category=m.category,
            importance=m.importance,
            skill_id=m.skill_id,
        )
        for m in score.matches
        if m.bucket == "true_gap"
    ]


def suggestion_uplift(score: ScoreResult, requirement_indexes: list[int]) -> int:
    """Score gain if these requirements reached the strength the evidence supports."""
    position = {m.requirement_index: i for i, m in enumerate(score.matches)}
    weighted = [(Fraction(str(m.weight)), Fraction(str(m.resume_strength))) for m in score.matches]
    improved = {
        position[i]: Fraction(str(score.matches[position[i]].best_strength))
        for i in requirement_indexes
    }
    return uplift(weighted, improved)


def _describe(ref: EvidenceRef, profile: StudentProfile) -> str:
    if ref.kind == "project":
        p = profile.projects[ref.index]
        return f'project "{p.name}" (tech: {", ".join(p.technologies) or "n/a"})'
    if ref.kind == "experience":
        x = profile.experience[ref.index]
        return f'job "{x.title} at {x.organization}" (tech: {", ".join(x.technologies) or "n/a"})'
    return f'{ref.kind} "{ref.label}"'


class ResumeAdvisor:
    name = "resume_advisor"
    uses_llm = True

    def __init__(self, llm: LLMClient, taxonomy: Taxonomy) -> None:
        self._llm = llm
        self._taxonomy = taxonomy
        self.prompt = load_prompt(self.name)

    async def run(
        self,
        inp: AdvisorInput,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> AdviceResult:
        eligible = eligible_matches(inp.score)
        if not eligible:
            return AdviceResult(suggestions=[], rejected=[], gaps=gaps(inp.score))

        # Number the evidence (non-resume first: that's what the resume is missing).
        evidence: dict[str, EvidenceRef] = {}
        ids_by_item: dict[tuple[str, int], str] = {}
        by_requirement: dict[int, set[str]] = {}
        ordered = sorted(
            ((m, r) for m in eligible for r in m.evidence),
            key=lambda pair: pair[1].source == "resume",
        )
        for match, ref in ordered:
            key = (ref.kind, ref.index)
            if key not in ids_by_item:
                if len(evidence) >= MAX_EVIDENCE_ITEMS:
                    continue
                ids_by_item[key] = f"Q{len(evidence) + 1}"
                evidence[ids_by_item[key]] = ref
            by_requirement.setdefault(match.requirement_index, set()).add(ids_by_item[key])

        req_ids = {f"R{m.requirement_index + 1}": m.requirement_index for m in eligible}
        req_lines = []
        for m in eligible:
            now = _STRENGTH_TEXT.get(m.resume_strength, "partly shown")
            refs = ", ".join(sorted(by_requirement.get(m.requirement_index, set())))
            req_lines.append(
                f"R{m.requirement_index + 1} [{m.importance}, {m.category}] {m.name} — "
                f"resume: {now}; evidence: {refs or 'none'}"
            )
        evidence_lines = [
            f"Q{i + 1} [{inp.sources[r.source].label if r.source in inp.sources else r.source}]"
            f' {_describe(r, inp.profile)} quote: "{r.snippet}"'
            for i, r in enumerate(evidence.values())
        ]
        entries = [f"project: {p.name}" for p in inp.profile.projects if p.source == "resume"]
        entries += [
            f"job: {x.title} at {x.organization}"
            for x in inp.profile.experience
            if x.source == "resume"
        ]
        input_text = (
            "<requirements>\n" + "\n".join(req_lines) + "\n</requirements>\n\n"
            "<evidence>\n" + "\n".join(evidence_lines) + "\n</evidence>\n\n"
            "<resume_entries>\n" + ("\n".join(entries) or "(none)") + "\n</resume_entries>"
        )
        advice = await self._llm.parse(
            agent=self.name,
            prompt=self.prompt,
            input_text=input_text,
            output_type=ResumeAdvice,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tier="large",
            analysis_id=analysis_id,
            user_id=user_id,
        )

        validator = EvidenceValidator(self._taxonomy, {k: v.text for k, v in inp.sources.items()})
        names = {m.requirement_index: m.name for m in inp.score.matches}
        suggestions: list[Suggestion] = []
        rejected: list[RejectedSuggestion] = []
        for draft in advice.suggestions:
            try:
                ok = validator.validate(draft, req_ids, evidence, by_requirement)
            except RejectedDraft as exc:
                logger.info("Rejected suggestion %r: %s", draft.suggested_text[:80], exc)
                rejected.append(
                    RejectedSuggestion(suggested_text=draft.suggested_text, reason=str(exc))
                )
                continue
            source = inp.sources.get(ok.quote_source)
            suggestions.append(
                Suggestion(
                    id=f"s{len(suggestions) + 1}",
                    requirement_indexes=ok.requirement_indexes,
                    requirement_names=[names[i] for i in ok.requirement_indexes],
                    section=draft.section,
                    action=draft.action,
                    target=draft.target,
                    suggested_text=draft.suggested_text.strip(),
                    rationale=draft.rationale.strip(),
                    quote=draft.quote.strip(),
                    quote_source=ok.quote_source,
                    quote_source_label=source.label if source else ok.quote_source,
                    evidence=ok.evidence,
                    uplift=suggestion_uplift(inp.score, ok.requirement_indexes),
                )
            )
        # Biggest gains first; ties keep the model's order (stable sort).
        suggestions.sort(key=lambda s: -s.uplift)
        return AdviceResult(suggestions=suggestions, rejected=rejected, gaps=gaps(inp.score))
