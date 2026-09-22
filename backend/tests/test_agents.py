import pytest

from app.agents.jd_analyzer import JDAnalyzer, dedupe_requirements
from app.agents.profile_extractor import (
    MAX_SUPPLEMENTARY_CHARS,
    ProfileExtractor,
    ProfileExtractorInput,
    SourceDocument,
    build_input,
    label_documents,
)
from app.core.config import Settings
from app.llm.client import LLMClient
from app.parsing.text import normalize_text, text_hash
from tests.fakes import FakeModel, InMemoryRepository
from tests.samples import (
    JOB_DESCRIPTION,
    PROFILE_FIXTURE,
    REQUIREMENTS_FIXTURE,
    RESUME_CLASSIC,
    SUPPORTING_PROJECT,
)

pytestmark = pytest.mark.anyio


def _doc(doc_id: str, text: str) -> SourceDocument:
    normalized = normalize_text(text)
    return SourceDocument(doc_id=doc_id, text=normalized, text_hash=text_hash(normalized))


def _llm() -> tuple[LLMClient, FakeModel, InMemoryRepository]:
    store = InMemoryRepository()
    model = FakeModel({"StudentProfile": PROFILE_FIXTURE, "JobRequirements": REQUIREMENTS_FIXTURE})
    settings = Settings(_env_file=None, openai_model_small="small-model")
    return LLMClient(settings, store, model), model, store


def test_labels_are_positional_by_content_not_document_id() -> None:
    a, b = _doc("id-a", "Notes about project A " * 3), _doc("id-b", "Notes about project B " * 3)
    resume = _doc("id-r", RESUME_CLASSIC)
    first = label_documents(ProfileExtractorInput(resume=resume, supplementary=[a, b]))
    second = label_documents(
        ProfileExtractorInput(
            resume=_doc("id-r2", RESUME_CLASSIC),
            supplementary=[_doc("id-b2", b.text), _doc("id-a2", a.text)],
        )
    )
    assert build_input(first) == build_input(second)
    assert [label for label, _, _ in first] == ["RESUME", "S1", "S2"]
    assert first[0][1] == "resume"
    assert {source for _, source, _ in first[1:]} == {"supplementary:id-a", "supplementary:id-b"}


def test_duplicate_supplementary_documents_are_sent_once() -> None:
    resume = _doc("r", RESUME_CLASSIC)
    note = "Same notes uploaded twice " * 3
    labeled = label_documents(
        ProfileExtractorInput(
            resume=resume,
            supplementary=[_doc("x", note), _doc("y", note), _doc("z", RESUME_CLASSIC)],
        )
    )
    assert len(labeled) == 2


def test_build_input_wraps_and_truncates_documents() -> None:
    long_doc = _doc("s", "x" * (MAX_SUPPLEMENTARY_CHARS + 500))
    text = build_input(
        label_documents(ProfileExtractorInput(resume=_doc("r", "resume"), supplementary=[long_doc]))
    )
    assert text.startswith('<document id="RESUME">\nresume\n</document>')
    assert '<document id="S1">' in text
    assert text.count("x") == MAX_SUPPLEMENTARY_CHARS


async def test_profile_extractor_resolves_sources_and_drops_unknown() -> None:
    llm, model, _ = _llm()
    profile = await ProfileExtractor(llm).run(
        ProfileExtractorInput(
            resume=_doc("resume-id", RESUME_CLASSIC),
            supplementary=[_doc("doc-1", SUPPORTING_PROJECT)],
        )
    )
    sources = {s.name: s.source for s in profile.skills}
    assert sources == {
        "Python": "resume",
        "FastAPI": "resume",
        "Kubernetes": "supplementary:doc-1",
    }  # "Made-up skill" cited S9, which doesn't exist
    assert profile.projects[0].source == "resume"
    assert profile.education[0].grade == "8.7/10"
    sent = model.requests[0]["input_text"]
    assert "Campus Food Ordering App" in sent
    assert "k3s cluster" in sent


async def test_jd_analyzer_wraps_input_and_dedupes() -> None:
    llm, model, _ = _llm()
    result = await JDAnalyzer(llm).run(normalize_text(JOB_DESCRIPTION))
    assert model.requests[0]["input_text"].startswith("<job_description>\n")
    names = [r.name for r in result.requirements]
    assert names == ["Python", "FastAPI", "Docker", "AWS", "Communication"]
    docker = next(r for r in result.requirements if r.name == "Docker")
    assert docker.importance == "must"


def test_dedupe_requirements_keeps_largest_min_years() -> None:
    reqs = REQUIREMENTS_FIXTURE.requirements[:1]
    python_3y = reqs[0].model_copy(update={"min_years": 3.0})
    python_1y = reqs[0].model_copy(update={"min_years": 1.0, "name": "python "})
    merged = dedupe_requirements([python_1y, python_3y])
    assert len(merged) == 1
    assert merged[0].min_years == 3.0


def test_dedupe_keeps_same_name_in_different_categories() -> None:
    skill = REQUIREMENTS_FIXTURE.requirements[0]
    domain = skill.model_copy(update={"category": "domain"})
    assert len(dedupe_requirements([skill, domain])) == 2
