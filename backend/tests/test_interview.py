import hashlib
import re
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.interview_prep import InterviewPrep, InterviewPrepInput
from app.api.deps import get_embedder
from app.core.config import Settings
from app.llm.client import LLMClient
from app.mcp_server.server import create_mcp_server, open_tools
from app.rag.embeddings import CachedEmbedder, embedding_key
from app.rag.templates import (
    background_questions,
    is_faithful_fill,
    load_background_templates,
    load_templates,
    project_facets,
)
from app.schemas.interview import (
    INTERVIEW_SET_VERSION,
    BankQuestion,
    FilledTemplate,
    InterviewSelection,
    InterviewSet,
)
from app.schemas.matching import RequirementMatch
from app.schemas.profile import Project
from app.skills.taxonomy import load_taxonomy
from tests.builders import cert, edu, job, profile, project, req, reqs
from tests.fakes import FakeModel, InMemoryRepository

pytestmark = pytest.mark.anyio

TAXONOMY = load_taxonomy()
DIMS = 64


class FakeEmbedder:
    """Bag-of-words hashing embedder: similar wording -> similar vectors."""

    model = "fake-embedding"

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for text in texts:
            v = [0.0] * DIMS
            for word in re.findall(r"[a-z0-9+#]+", text.lower()):
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS] += 1.0
            out.append(v)
        return out


BANK_TEXTS: list[tuple[str, str, list[str]]] = [
    # (category, text, topics)
    *(
        ("technical", f"What is a Docker {w}?", ["docker"])
        for w in ("image", "volume", "network", "layer", "registry", "compose file")
    ),
    *(
        ("technical", f"How does Kubernetes handle {w}?", ["kubernetes"])
        for w in ("scheduling", "service discovery", "rolling updates", "autoscaling")
    ),
    *(
        ("technical", f"Explain {w} in React", ["react"])
        for w in ("hooks", "reconciliation", "context", "suspense", "keys", "portals")
    ),
    *(
        ("technical", f"How do you optimise a slow SQL {w}?", ["sql"])
        for w in ("join", "query", "subquery", "aggregation")
    ),
    *(
        ("technical", f"What is {w} in Python?", ["python"])
        for w in ("a generator", "the GIL", "a decorator", "a context manager")
    ),
    *(
        ("general", f"Tell me about a time you {w}.", [])
        for w in (
            "missed a deadline",
            "disagreed with a teammate",
            "fixed a hard bug",
            "learned something fast",
            "led a project",
            "handled feedback",
            "failed",
            "helped a colleague",
            "changed your mind",
        )
    ),
    *(
        ("personal", w, [])
        for w in (
            "Tell me about yourself",
            "Why do you want to work here?",
            "What are your strengths?",
            "Where do you see yourself in five years?",
            "What are you looking for in your next role?",
        )
    ),
]


async def make_repo(embedder: FakeEmbedder) -> InMemoryRepository:
    repo = InMemoryRepository()
    vectors = await embedder.embed([t for _, t, _ in BANK_TEXTS])
    for i, ((category, text, topics), vector) in enumerate(zip(BANK_TEXTS, vectors, strict=True)):
        q = BankQuestion(
            id=f"q{i}",
            text=text,
            category=category,
            topics=topics,
            role_tags=["backend"],
            difficulty=None,
            source_repo=f"owner/{category}-bank",
            source_path="README.md",
            source_url=f"https://github.com/owner/{category}-bank/blob/main/README.md",
            license="MIT",
        )
        repo.bank.append((q, vector))
    return repo


def match(
    index: int, name: str, skill_id: str | None, importance: str = "must"
) -> RequirementMatch:
    return RequirementMatch.model_validate(
        {
            "requirement_index": index,
            "name": name,
            "category": "skill",
            "importance": importance,
            "min_years": None,
            "skill_id": skill_id,
            "method": "none",
            "weight": 3.0 if importance == "must" else 1.0,
            "resume_strength": 0.0,
            "best_strength": 0.0,
            "resume_years": None,
            "total_years": None,
            "bucket": "true_gap",
            "evidence": [],
        }
    )


FOOD_APP = project(
    "Campus Food App", ["FastAPI", "PostgreSQL", "Docker"], summary="Food ordering backend"
)
FOOD_APP = FOOD_APP.model_copy(update={"metrics": ["2,000 students"], "highlights": ["JWT auth"]})
VISION = project(
    "Plant Disease Detector", ["PyTorch", "OpenCV"], summary="CNN classifier for leaves"
)
BACKEND_JD = [
    match(0, "Docker", "docker"),
    match(1, "Kubernetes", "kubernetes"),
    match(2, "SQL", "sql", "nice"),
]
FRONTEND_JD = [match(0, "React", "react"), match(1, "Python", "python", "nice")]


def prep_input(
    matches: list[RequirementMatch], projects: list[Project] | None = None
) -> InterviewPrepInput:
    return InterviewPrepInput(
        analysis_id="analysis-1",
        profile=profile(projects=projects if projects is not None else [FOOD_APP, VISION]),
        requirements=reqs(req("x"), title="Backend Engineer"),
        matches=matches,
    )


async def make_prep(select: Any = None) -> tuple[InterviewPrep, FakeModel, InMemoryRepository]:
    embedder = FakeEmbedder()
    repo = await make_repo(embedder)
    model = FakeModel(
        {
            "InterviewSelection": select
            or (
                lambda m, t: InterviewSelection(
                    technical_ids=[], general_ids=[], personal_ids=[], project_questions=[]
                )
            )
        }
    )
    llm = LLMClient(Settings(_env_file=None, openai_model_small="small-model"), repo, model)
    server = create_mcp_server(lambda: repo, TAXONOMY, lambda: CachedEmbedder(embedder, repo))
    return InterviewPrep(llm, TAXONOMY, lambda: open_tools(server)), model, repo


def all_questions(s: InterviewSet) -> list[Any]:
    return [*s.personal, *s.technical, *s.general, *(q for p in s.projects for q in p.questions)]


# -- MCP tools ---------------------------------------------------------------------------


async def test_search_tool_filters_by_topic_and_ranks_by_similarity() -> None:
    embedder = FakeEmbedder()
    repo = await make_repo(embedder)
    server = create_mcp_server(lambda: repo, TAXONOMY, lambda: CachedEmbedder(embedder, repo))
    async with open_tools(server) as tools:
        hits = await tools.search_questions(
            "Docker volume", category="technical", topics=["docker"], k=3
        )
        again = await tools.search_questions(
            "Docker volume", category="technical", topics=["docker"], k=3
        )
    assert all("docker" in h.topics for h in hits)
    assert hits[0].text == "What is a Docker volume?"
    assert [h.id for h in hits] == [h.id for h in again]
    # The query embedding was cached, so the second search didn't embed again.
    assert embedding_key("fake-embedding", "Docker volume") in repo.embedding_cache


async def test_general_questions_are_seeded_and_deterministic() -> None:
    embedder = FakeEmbedder()
    repo = await make_repo(embedder)
    server = create_mcp_server(lambda: repo, TAXONOMY, lambda: embedder)
    async with open_tools(server) as tools:
        a = await tools.general_questions(3, "seed-a")
        a2 = await tools.general_questions(3, "seed-a")
        b = await tools.general_questions(3, "seed-b")
    assert [q.id for q in a] == [q.id for q in a2]
    assert [q.id for q in a] != [q.id for q in b]
    assert sorted(q.category for q in a) == ["general"] * 3 + ["personal"] * 3


async def test_templates_tool_by_facets() -> None:
    server = create_mcp_server(InMemoryRepository, TAXONOMY)
    async with open_tools(server) as tools:
        ml = await tools.project_templates(["ml"])
        plain = await tools.project_templates([])
    assert {"any"} == {f for t in plain for f in t.facets}
    assert any("ml" in t.facets for t in ml) and len(ml) > len(plain)


def test_project_facets_from_technologies() -> None:
    assert project_facets(FOOD_APP, TAXONOMY) == ["backend", "database", "deployment"]
    assert "ml" in project_facets(VISION, TAXONOMY)


def test_faithful_fill_check() -> None:
    template = next(t for t in load_templates() if t.id == "T5")
    good = (
        "Why did you choose FastAPI for Campus Food App, and which alternatives did you consider?"
    )
    assert is_faithful_fill(good, template, FOOD_APP)
    assert not is_faithful_fill("Tell me about Campus Food App.", template, FOOD_APP)  # reworded
    unrelated = (
        "Why did you choose Rails for Some Other App, and which alternatives did you consider?"
    )
    assert not is_faithful_fill(unrelated, template, FOOD_APP)  # not about this project


# -- InterviewPrep -----------------------------------------------------------------------


async def test_deterministic_fallback_is_complete_and_fully_sourced() -> None:
    prep, model, _ = await make_prep()  # LLM picks nothing -> Python pads everything
    result = await prep.run(prep_input(BACKEND_JD))

    assert len(model.requests) == 1
    # The test bank is small: every candidate for the job is used (14 < the minimum of 20).
    assert len(result.technical) == 14
    assert len(result.personal) == 5 and len(result.general) == 9  # whole test bank
    assert result.version == INTERVIEW_SET_VERSION
    assert {q.category for q in result.personal} == {"personal"}
    assert [p.project for p in result.projects] == ["Campus Food App", "Plant Disease Detector"]
    for p in result.projects:
        assert len(p.questions) >= 12
        assert len({q.dimension for q in p.questions}) >= 7
        assert all(p.project in q.text for q in p.questions)
    # Exit criterion: 100% of questions have a source.
    for q in all_questions(result):
        assert q.source.label
        if q.source.kind == "github":
            assert q.source.url and q.source.license
        else:
            assert q.source.template_id


async def test_technical_questions_follow_the_job_description() -> None:
    prep, _, _ = await make_prep()
    backend = await prep.run(prep_input(BACKEND_JD))
    frontend = await prep.run(prep_input(FRONTEND_JD))

    backend_topics = {q.topic for q in backend.technical}
    assert backend_topics <= {"Docker", "Kubernetes", "SQL"}
    assert {"Docker", "Kubernetes"} <= backend_topics  # must-haves covered first
    assert {q.topic for q in frontend.technical} <= {"React", "Python"}
    assert not {q.text for q in backend.technical} & {q.text for q in frontend.technical}


async def test_llm_selection_is_validated() -> None:
    def select(model: str, text: str) -> InterviewSelection:
        ids = re.findall(r"^(Q\d+) \[Docker\]", text, re.M)
        personal = re.findall(r"^(G\d+) \[personal\]", text, re.M)
        general = re.findall(r"^(G\d+) \[general\]", text, re.M)
        return InterviewSelection(
            technical_ids=[ids[0], ids[0], "Q999"],  # duplicate and unknown ids are dropped
            general_ids=[general[0], personal[0]],  # a personal id in the general list is dropped
            personal_ids=[personal[1]],
            project_questions=[
                FilledTemplate(
                    project_id="P1",
                    template_id="T5",
                    question="Why did you choose PostgreSQL for Campus Food App, and which "
                    "alternatives did you consider?",
                ),
                FilledTemplate(  # invented project details: rejected
                    project_id="P1", template_id="T21", question="Tell me about your Kafka cluster."
                ),
                FilledTemplate(  # template not allowed for this project's facets
                    project_id="P1",
                    template_id="T9",
                    question="Describe the model architecture "
                    "you used in Campus Food App. Why that model and not a simpler baseline?",
                ),
                FilledTemplate(project_id="P9", template_id="T1", question="Walk me through X"),
            ],
        )

    prep, _, _ = await make_prep(select)
    result = await prep.run(prep_input(BACKEND_JD))

    assert result.technical[0].topic == "Docker"
    assert len({q.text for q in result.technical}) == len(result.technical)
    assert result.general[0].category == "general"
    assert result.personal[0].text == "Why do you want to work here?" or result.personal
    food = result.projects[0]
    assert food.questions[0].text.startswith("Why did you choose PostgreSQL")
    assert food.questions[0].source.template_id == "T5"
    assert not any("Kafka" in q.text for q in food.questions)
    assert not any(q.source.template_id == "T9" for q in food.questions)
    assert len(food.questions) >= 12


async def test_llm_failure_still_returns_a_full_set() -> None:
    def boom(model: str, text: str) -> InterviewSelection:
        raise RuntimeError("model down")

    prep, _, _ = await make_prep(boom)
    result = await prep.run(prep_input(BACKEND_JD))
    assert len(result.technical) == 14 and len(result.projects) == 2


async def test_templates_needing_missing_details_are_skipped() -> None:
    bare = project("Bare Project", [])  # no technologies, no metrics
    prep, _, _ = await make_prep()
    result = await prep.run(prep_input(BACKEND_JD, [bare]))
    texts = [q.text for q in result.projects[0].questions]
    assert texts and all("{" not in t for t in texts)


def test_background_questions_drill_into_jobs_degree_and_certification() -> None:
    templates = list(load_background_templates())
    student = profile(
        experience=[
            job("Backend Intern", "Acme", "2025-01", "2025-06", ["Go"]),
            job("Research Assistant", "State University", "2024-01", "2024-12"),
            job("TA", "Uni", None, None),
            job("Fourth job", "Ignored", None, None),  # at most three jobs
        ],
        education=[edu("B.Tech", "Computer Science")],
        certifications=[cert("AWS Cloud Practitioner")],
    )
    questions = background_questions(student, templates)
    texts = [text for _, text in questions]
    ids = [t.id for t, _ in questions]

    assert ids[:3] == ["B1", "B2", "B3"]  # first job, with its technology
    assert "How did you use Go at Acme?" in texts[2]
    assert ids[3:6] == ["B4", "B5", "B6"]  # second job starts elsewhere: varied questions
    assert len([t for t, _ in questions if t.kind == "experience"]) == 9
    assert not any("Ignored" in t for t in texts)
    assert "Why did you choose Computer Science at State University?" in texts
    assert any("AWS Cloud Practitioner" in t for t in texts)
    assert all("{" not in t for t in texts)
    assert background_questions(profile(), templates) == []


def test_background_templates_skip_missing_details() -> None:
    templates = list(load_background_templates())
    no_tech = profile(experience=[job("Intern", "Acme", None, None)])
    assert all(t.id != "B3" for t, _ in background_questions(no_tech, templates))


async def test_personal_questions_include_background_drill_downs() -> None:
    prep, _, _ = await make_prep()
    inp = prep_input(BACKEND_JD)
    inp = inp.model_copy(
        update={
            "profile": inp.profile.model_copy(
                update={"experience": [job("Backend Intern", "Acme", "2025-01", None, ["Go"])]}
            )
        }
    )
    result = await prep.run(inp)
    drill = [q for q in result.personal if q.source.kind == "template"]
    assert len(drill) == 3 and all("Acme" in q.text for q in drill)
    assert {q.dimension for q in drill} == {"experience"}
    assert drill[0].source.label == "Resume Optimizer background question bank"


# -- API -------------------------------------------------------------------------------


@pytest.fixture
def api(settings: Settings) -> Iterator[tuple[TestClient, Any]]:
    from tests.test_api_analyses import Harness

    harness = Harness(settings)
    embedder = FakeEmbedder()
    harness.client.app.dependency_overrides[get_embedder] = lambda: CachedEmbedder(  # type: ignore[attr-defined]
        embedder, harness.repo
    )
    harness.model.responses["InterviewSelection"] = lambda m, t: InterviewSelection(
        technical_ids=[], general_ids=[], personal_ids=[], project_questions=[]
    )
    with harness.client:
        yield harness.client, harness


async def test_interview_endpoint_is_idempotent_and_scoped(api: tuple[TestClient, Any]) -> None:
    client, h = api
    for q, vector in (await make_repo(FakeEmbedder())).bank:
        h.repo.bank.append((q, vector))
    analysis_id = h.analyze(h.upload_resume().json()["id"]).json()["id"]

    assert client.get(f"/analyses/{analysis_id}/interview").status_code == 404
    first = client.post(f"/analyses/{analysis_id}/interview")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["projects"] and body["technical"] and body["general"]
    calls = len(h.model.requests)

    second = client.post(f"/analyses/{analysis_id}/interview")
    assert second.json() == body
    assert len(h.model.requests) == calls  # stored set reused, no new LLM call
    assert client.get(f"/analyses/{analysis_id}/interview").json() == body

    from tests.test_api_analyses import OTHER

    h.user = OTHER
    assert client.post(f"/analyses/{analysis_id}/interview").status_code == 404


async def test_interview_requires_a_finished_analysis(api: tuple[TestClient, Any]) -> None:
    client, h = api
    analysis_id = h.analyze(h.upload_resume().json()["id"]).json()["id"]
    await h.repo.update_analysis(analysis_id, status="extracting")
    assert client.post(f"/analyses/{analysis_id}/interview").status_code == 409


async def test_outdated_interview_sets_are_regenerated(api: tuple[TestClient, Any]) -> None:
    client, h = api
    for q, vector in (await make_repo(FakeEmbedder())).bank:
        h.repo.bank.append((q, vector))
    analysis_id = h.analyze(h.upload_resume().json()["id"]).json()["id"]
    # A set stored by an older version (smaller, no version field).
    old = {"personal": [], "projects": [], "technical": [], "general": []}
    h.repo.interview_sets[analysis_id] = old

    assert client.get(f"/analyses/{analysis_id}/interview").status_code == 404
    fresh = client.post(f"/analyses/{analysis_id}/interview").json()
    assert fresh["version"] == INTERVIEW_SET_VERSION and fresh["technical"]
    assert h.repo.interview_sets[analysis_id]["version"] == INTERVIEW_SET_VERSION
    assert client.get(f"/analyses/{analysis_id}/interview").json() == fresh
