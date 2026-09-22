"""ResumeAdvisor + EvidenceValidator, including adversarial LLM output."""

import re
from datetime import date
from fractions import Fraction
from typing import Any

import pytest

from app.agents.evidence_validator import normalize_for_match
from app.agents.matcher import Matcher
from app.agents.resume_advisor import (
    AdvisorInput,
    ResumeAdvisor,
    SourceDoc,
    eligible_matches,
    suggestion_uplift,
)
from app.agents.scorer import Scorer
from app.agents.skill_normalizer import SkillNormalizer
from app.core.config import Settings
from app.llm.client import LLMClient
from app.schemas.advice import ResumeAdvice, SuggestionDraft
from app.schemas.matching import ScoreResult
from app.schemas.profile import SkillMention
from app.scoring.engine import fit_score
from app.skills.taxonomy import load_taxonomy
from tests.builders import judged, profile, project, req, reqs
from tests.fakes import FakeModel, InMemoryRepository

pytestmark = pytest.mark.anyio

TAXONOMY = load_taxonomy()
SUPP = "supplementary:doc-1"
RESUME_TEXT = """SKILLS
Python, Docker
PROJECTS
Campus Food App - Built a FastAPI backend with PostgreSQL."""
SUPP_TEXT = """Deployment notes. I containerized the FastAPI service with Docker and
deployed it on a 3-node k3s cluster. Set up GitHub Actions CI for every push."""
JD_TEXT_QUOTE = "Familiarity with Terraform"  # appears only in the job description


def _mention(name: str, context: Any, source: str, evidence: str) -> SkillMention:
    return SkillMention(
        name=name, context=context, context_name=None, source=source, evidence=evidence
    )


PROFILE = profile(
    skills=[
        _mention("Python", "skills_section", "resume", "Python, Docker"),
        _mention("Docker", "skills_section", "resume", "Python, Docker"),
        _mention("FastAPI", "project", "resume", "Built a FastAPI backend with PostgreSQL"),
        _mention("Kubernetes", "project", SUPP, "deployed it on a 3-node k3s cluster"),
        _mention("Docker", "project", SUPP, "containerized the FastAPI service with Docker"),
        _mention("GitHub Actions", "project", SUPP, "Set up GitHub Actions CI for every push"),
    ],
    projects=[
        project("Campus Food App", ["FastAPI", "PostgreSQL"]),
        project("Campus Food App deployment", ["Docker", "Kubernetes"], source=SUPP),
    ],
)
REQUIREMENTS = reqs(
    req("Python"),  # R1: listed; only implied by the FastAPI project anywhere -> not eligible
    req("Docker"),  # R2: listed on resume, demonstrated in notes -> eligible
    req("Kubernetes"),  # R3: notes only -> eligible
    req("CI/CD", importance="nice"),  # R4: implied by GitHub Actions in notes -> eligible
    req("Terraform", importance="nice"),  # R5: nowhere -> gap
    req("Communication", "soft_skill"),  # R6: nowhere -> gap
)
SOURCES = {
    "resume": SourceDoc(label="your resume", text=RESUME_TEXT),
    SUPP: SourceDoc(label="deploy-notes.pdf", text=SUPP_TEXT),
}


def _llm(responses: dict[str, Any]) -> tuple[LLMClient, FakeModel]:
    model = FakeModel(responses)
    settings = Settings(_env_file=None, openai_model_small="small-model")
    return LLMClient(settings, InMemoryRepository(), model), model


async def _score() -> ScoreResult:
    llm, _ = _llm({"EvidenceJudgements": judged()})
    normalized = SkillNormalizer(TAXONOMY).run(PROFILE, REQUIREMENTS)
    evidence = await Matcher(llm, TAXONOMY).run(PROFILE, REQUIREMENTS, normalized)
    return Scorer().run(REQUIREMENTS, evidence, PROFILE, as_of=date(2026, 9, 1))


def qid(prompt: str, fragment: str) -> str:
    """Evidence id of the line in the advisor prompt containing `fragment`."""
    for line in prompt.splitlines():
        if fragment in line and (m := re.match(r"(Q\d+) ", line)):
            return m.group(1)
    raise AssertionError(f"no evidence line with {fragment!r}")


def draft(**overrides: Any) -> SuggestionDraft:
    base: dict[str, Any] = {
        "requirement_ids": ["R3"],
        "evidence_ids": [],
        "section": "projects",
        "action": "expand_project",
        "target": "Campus Food App",
        "suggested_text": "Deployed the service on a 3-node Kubernetes (k3s) cluster.",
        "quote": "deployed it on a 3-node k3s cluster",
        "rationale": "The job asks for Kubernetes.",
    }
    return SuggestionDraft.model_validate({**base, **overrides})


async def _advise(make_drafts: Any) -> tuple[Any, FakeModel, ScoreResult]:
    """make_drafts(prompt) -> list[SuggestionDraft]; runs the advisor with that LLM output."""
    score = await _score()

    def respond(model: str, input_text: str) -> ResumeAdvice:
        return ResumeAdvice(suggestions=make_drafts(input_text))

    llm, model = _llm({"ResumeAdvice": respond})
    advisor = ResumeAdvisor(llm, TAXONOMY)
    result = await advisor.run(AdvisorInput(profile=PROFILE, score=score, sources=SOURCES))
    return result, model, score


# -- setup sanity ------------------------------------------------------------------------


async def test_scenario_buckets_and_eligibility() -> None:
    score = await _score()
    buckets = [m.bucket for m in score.matches]
    assert buckets == [
        "weak_in_resume",
        "weak_in_resume",
        "missing_from_resume_but_evidenced",
        "missing_from_resume_but_evidenced",
        "true_gap",
        "true_gap",
    ]
    assert [m.name for m in eligible_matches(score)] == ["Docker", "Kubernetes", "CI/CD"]
    # 100 × (3·0.7 + 3·0.7) / 12.2 = 34.4
    assert score.fit_score == 34


async def test_no_llm_call_without_eligible_requirements() -> None:
    score = await _score()
    only_gaps = score.model_copy(
        update={"matches": [m for m in score.matches if m.bucket == "true_gap"]}
    )
    llm, model = _llm({})
    result = await ResumeAdvisor(llm, TAXONOMY).run(
        AdvisorInput(profile=PROFILE, score=only_gaps, sources=SOURCES)
    )
    assert result.suggestions == [] and model.requests == []
    assert [g.name for g in result.gaps] == ["Terraform", "Communication"]


# -- prompt ------------------------------------------------------------------------------


async def test_prompt_lists_eligible_requirements_and_supplementary_evidence_first() -> None:
    _, model, _ = await _advise(lambda prompt: [])
    prompt = model.requests[0]["input_text"]
    assert "R2 [must, skill] Docker — resume: listed or shown, not both" in prompt
    assert "R3 [must, skill] Kubernetes — resume: missing" in prompt
    assert "R1 " not in prompt and "R5 " not in prompt  # not eligible
    assert "Terraform" not in prompt
    assert prompt.index("[deploy-notes.pdf]") < prompt.index("[your resume]")
    assert "<resume_entries>\nproject: Campus Food App\n</resume_entries>" in prompt


# -- validation ------------------------------------------------------------------------


async def test_valid_suggestion_is_kept_with_uplift_and_source() -> None:
    def drafts(prompt: str) -> list[SuggestionDraft]:
        k8s, docker = qid(prompt, "3-node k3s"), qid(prompt, "containerized the FastAPI")
        return [
            draft(
                requirement_ids=["R2", "R3"],
                evidence_ids=[k8s, docker],
                suggested_text="Containerized the FastAPI service with Docker and deployed it "
                "on a 3-node Kubernetes (k3s) cluster.",
            )
        ]

    result, _, score = await _advise(drafts)
    assert result.rejected == []
    (s,) = result.suggestions
    assert s.requirement_names == ["Docker", "Kubernetes"]
    assert s.quote_source == SUPP
    assert s.quote_source_label == "deploy-notes.pdf"
    # Docker 0.7 -> 1.0 and Kubernetes 0 -> 0.7: (4.2 + 0.9 + 2.1) / 12.2 = 59.0 -> +25
    assert s.uplift == 25


ADVERSARIAL: list[tuple[str, dict[str, Any], str]] = [
    ("fabricated quote", {"quote": "Led a team of 10 engineers at Google"}, "quote isn't"),
    ("quote from the job description", {"quote": JD_TEXT_QUOTE}, "quote isn't"),
    ("too-short quote", {"quote": "k3s"}, "quote isn't"),
    ("quote from the wrong document", {"quote": "Built a FastAPI backend"}, "quote isn't"),
    ("gap requirement", {"requirement_ids": ["R5"]}, "doesn't address"),
    ("requirement with nothing to add", {"requirement_ids": ["R1"]}, "doesn't address"),
    ("unknown requirement", {"requirement_ids": ["R99"]}, "doesn't address"),
    ("unknown evidence", {"evidence_ids": ["Q99"]}, "doesn't cite"),
    (
        "invented skill in text",
        {"suggested_text": "Deployed on Kubernetes with Terraform-managed AWS infrastructure."},
        "Terraform",
    ),
]


@pytest.mark.parametrize(
    ("label", "changes", "reason"), ADVERSARIAL, ids=[a[0] for a in ADVERSARIAL]
)
async def test_adversarial_drafts_are_rejected(
    label: str, changes: dict[str, Any], reason: str
) -> None:
    def drafts(prompt: str) -> list[SuggestionDraft]:
        return [draft(**{"evidence_ids": [qid(prompt, "3-node k3s")], **changes})]

    result, _, _ = await _advise(drafts)
    assert result.suggestions == []
    assert len(result.rejected) == 1
    assert reason in result.rejected[0].reason


async def test_evidence_unrelated_to_the_requirement_is_rejected() -> None:
    # Cites the CI evidence for the Kubernetes requirement.
    result, _, _ = await _advise(
        lambda prompt: [draft(evidence_ids=[qid(prompt, "GitHub Actions CI")])]
    )
    assert "unrelated" in result.rejected[0].reason


@pytest.mark.parametrize(
    "quote",
    [
        "DEPLOYED IT ON A 3-NODE   K3S CLUSTER",  # case and spacing
        "containerized the FastAPI service with Docker and deployed it",  # spans a line break
        "containerized the FastAPI service … 3-node k3s cluster",  # ellipsis, in order
    ],
)
async def test_quote_matching_tolerates_formatting(quote: str) -> None:
    def drafts(prompt: str) -> list[SuggestionDraft]:
        return [draft(evidence_ids=[qid(prompt, "3-node k3s")], quote=quote)]

    result, _, _ = await _advise(drafts)
    assert result.rejected == [] and len(result.suggestions) == 1


async def test_ellipsis_fragments_must_be_in_order() -> None:
    quote = "3-node k3s cluster … containerized the FastAPI service"
    result, _, _ = await _advise(
        lambda prompt: [draft(evidence_ids=[qid(prompt, "3-node k3s")], quote=quote)]
    )
    assert result.suggestions == []


def test_normalize_for_match() -> None:
    assert normalize_for_match("It’s  a “test” – ok") == 'it\'s a "test" - ok'


async def test_skills_implied_by_evidence_are_allowed_in_text() -> None:
    # "CI/CD" isn't written anywhere, but GitHub Actions (in the notes) implies it.
    def drafts(prompt: str) -> list[SuggestionDraft]:
        return [
            draft(
                requirement_ids=["R4"],
                evidence_ids=[qid(prompt, "GitHub Actions CI")],
                section="projects",
                suggested_text="Set up a CI/CD pipeline with GitHub Actions on every push.",
                quote="Set up GitHub Actions CI for every push",
            )
        ]

    result, _, _ = await _advise(drafts)
    assert result.rejected == []
    # CI/CD nice 0 -> 0.4: 34.4% -> 37.7%, which round to 34 and 38
    assert result.suggestions[0].uplift == 4


# -- uplift ----------------------------------------------------------------------------


async def test_uplift_matches_a_recomputed_score_for_every_combination() -> None:
    score = await _score()
    eligible = [m.requirement_index for m in eligible_matches(score)]
    subsets = [[i] for i in eligible] + [eligible[:2], eligible]
    for subset in subsets:
        recomputed = fit_score(
            (
                Fraction(str(m.weight)),
                Fraction(
                    str(m.best_strength if m.requirement_index in subset else m.resume_strength)
                ),
            )
            for m in score.matches
        )
        assert suggestion_uplift(score, subset) == recomputed - score.fit_score
    # Applying everything reaches the potential score.
    assert score.fit_score + suggestion_uplift(score, eligible) == score.potential_score


async def test_suggestions_sorted_by_uplift_and_stored_in_order() -> None:
    def drafts(prompt: str) -> list[SuggestionDraft]:
        ci = draft(
            requirement_ids=["R4"],
            evidence_ids=[qid(prompt, "GitHub Actions CI")],
            suggested_text="Set up GitHub Actions CI.",
            quote="Set up GitHub Actions CI for every push",
        )
        k8s = draft(evidence_ids=[qid(prompt, "3-node k3s")])
        return [ci, k8s]

    result, _, _ = await _advise(drafts)
    assert [s.requirement_names for s in result.suggestions] == [["Kubernetes"], ["CI/CD"]]
    assert result.suggestions[0].uplift > result.suggestions[1].uplift
