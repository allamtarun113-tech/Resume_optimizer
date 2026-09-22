import asyncio
import random
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.learning_path_planner import LearningPathPlanner, PlannerInput
from app.agents.skill_normalizer import NormalizedSkills
from app.core.config import Settings
from app.llm.client import LLMClient
from app.main import create_app
from app.mcp_server.server import create_mcp_server, open_tools
from app.schemas.learning import LearningResource, PathPlan, StepNote
from app.schemas.matching import RequirementMatch, ScoreResult
from app.skills.taxonomy import load_taxonomy
from tests.fakes import FakeModel, InMemoryRepository

pytestmark = pytest.mark.anyio

TAXONOMY = load_taxonomy()
SEED_FILE = Path(__file__).resolve().parents[2] / "ingestion" / "resources_seed.yaml"


def resource(skill_id: str, title: str, **kw: Any) -> LearningResource:
    base: dict[str, Any] = {
        "skill_id": skill_id,
        "title": title,
        "url": f"https://example.org/{skill_id}/{title.replace(' ', '-').lower()}",
        "type": "docs",
        "level": "beginner",
        "est_hours": 5.0,
        "free": True,
    }
    return LearningResource.model_validate({**base, **kw})


def repo_with_resources() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.resources = [
        resource("docker", "Docker get started", est_hours=6),
        resource("docker", "Docker deep dive", level="advanced", est_hours=20),
        resource("docker", "Paid docker course", free=False),
        resource("docker", "Docker book", est_hours=12),
        resource("kubernetes", "Kubernetes basics", level="intermediate", est_hours=6),
        resource("linux", "Linux command line", est_hours=20),
        resource("terraform", "Terraform tutorials", est_hours=10),
    ]
    return repo


def gap(index: int, name: str, skill_id: str | None, **kw: Any) -> RequirementMatch:
    base: dict[str, Any] = {
        "requirement_index": index,
        "name": name,
        "category": "skill",
        "importance": "must",
        "min_years": None,
        "skill_id": skill_id,
        "method": "none",
        "weight": 3.0,
        "resume_strength": 0.0,
        "best_strength": 0.0,
        "resume_years": None,
        "total_years": None,
        "bucket": "true_gap",
        "evidence": [],
    }
    return RequirementMatch.model_validate({**base, **kw})


def planner_input(
    matches: list[RequirementMatch],
    known: list[str] | None = None,
    alternatives: dict[int, list[str]] | None = None,
) -> PlannerInput:
    size = max((m.requirement_index for m in matches), default=-1) + 1
    alts = alternatives or {}
    return PlannerInput(
        score=ScoreResult(scoring_version="t", fit_score=0, potential_score=0, matches=matches),
        normalized=NormalizedSkills(
            mention_ids=[[k] for k in known or []],
            project_ids=[],
            experience_ids=[],
            requirement_ids=[m.skill_id for m in matches],
            requirement_alternatives=[alts.get(i, []) for i in range(size)],
        ),
    )


def make_planner(
    repo: InMemoryRepository | None = None, plan: Any = None
) -> tuple[LearningPathPlanner, FakeModel, InMemoryRepository]:
    repo = repo or repo_with_resources()
    model = FakeModel({"PathPlan": plan or (lambda m, text: PathPlan(order=[], notes=[]))})
    llm = LLMClient(Settings(_env_file=None, openai_model_small="small-model"), repo, model)
    server = create_mcp_server(lambda: repo, TAXONOMY)
    return LearningPathPlanner(llm, TAXONOMY, lambda: open_tools(server)), model, repo


# -- MCP server ---------------------------------------------------------------------------


async def test_mcp_learning_resources_are_ranked_and_capped() -> None:
    server = create_mcp_server(repo_with_resources, TAXONOMY)
    async with open_tools(server) as tools:
        found = await tools.learning_resources(["docker", "kubernetes", "unknown"])
    docker = [r.title for r in found if r.skill_id == "docker"]
    # free first, then easier, then shorter; at most 3
    assert docker == ["Docker get started", "Docker book", "Docker deep dive"]
    assert [r.skill_id for r in found].count("kubernetes") == 1


async def test_mcp_prerequisites() -> None:
    server = create_mcp_server(repo_with_resources, TAXONOMY)
    async with open_tools(server) as tools:
        k8s = await tools.prerequisites("kubernetes")
        unknown = await tools.prerequisites("not-a-skill")
    assert k8s.name == "Kubernetes"
    assert [p.skill_id for p in k8s.prerequisites] == ["docker"]
    assert unknown.name is None and unknown.prerequisites == []


@pytest.fixture
def mcp_client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    configured = settings.model_copy(update={"mcp_service_token": "secret-token"})
    monkeypatch.setattr("app.main.get_settings", lambda: configured)
    with TestClient(create_app()) as client:
        yield client


def test_mcp_http_requires_service_token(mcp_client: TestClient) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}
    assert mcp_client.post("/mcp/", json=body, headers=headers).status_code == 401
    wrong = {**headers, "Authorization": "Bearer nope"}
    assert mcp_client.post("/mcp/", json=body, headers=wrong).status_code == 401

    ok = mcp_client.post(
        "/mcp/", json=body, headers={**headers, "Authorization": "Bearer secret-token"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["result"]["serverInfo"]["name"] == "resume-optimizer"


def test_mcp_not_mounted_without_token(client: TestClient) -> None:
    assert client.post("/mcp/", json={}).status_code == 404


# -- planner ---------------------------------------------------------------------------


async def test_prerequisites_come_first_and_resources_come_from_the_store() -> None:
    planner, model, repo = make_planner()
    path = await planner.run(planner_input([gap(0, "Kubernetes", "kubernetes")]))

    assert [s.skill_id for s in path.steps] == ["linux", "docker", "kubernetes"]
    assert [s.kind for s in path.steps] == ["prerequisite", "prerequisite", "gap"]
    assert path.steps[1].unlocks == ["Kubernetes"]
    assert path.steps[0].for_requirements == ["Kubernetes"]  # inherited
    # Exit criterion: every URL shown exists in the resource table.
    stored = {r.url for r in repo.resources}
    assert all(r.url in stored for s in path.steps for r in s.resources)
    assert path.steps[1].est_hours == 6  # first (best) docker resource
    assert path.total_hours == 20 + 6 + 6
    assert len(model.requests) == 1


async def test_known_skills_and_their_prerequisites_are_skipped() -> None:
    planner, _, _ = make_planner()
    # Knowing Docker implies knowing its prerequisite Linux.
    path = await planner.run(planner_input([gap(0, "Kubernetes", "kubernetes")], known=["docker"]))
    assert [s.skill_id for s in path.steps] == ["kubernetes"]


async def test_prerequisite_depth_is_limited() -> None:
    planner, _, _ = make_planner()
    # kubernetes -> docker -> linux -> operating-systems -> computer-architecture
    path = await planner.run(planner_input([gap(0, "Kubernetes", "kubernetes")]))
    assert "operating-systems" not in [s.skill_id for s in path.steps]


async def test_non_learnable_and_unknown_gaps() -> None:
    planner, _, _ = make_planner()
    matches = [
        gap(0, "Bachelor's degree", None, category="education"),
        gap(1, "3+ years experience", None, category="experience"),
        gap(2, "Communication", "communication", category="soft_skill"),
        gap(3, "Quantum widgets", None, importance="nice", weight=1.0),
        gap(4, "Terraform", "terraform"),
        gap(5, "Covered", "python", bucket="weak_in_resume"),
    ]
    path = await planner.run(planner_input(matches, known=["linux", "cloud-computing"]))
    assert [s.name for s in path.steps] == ["Terraform", "Quantum widgets"]
    custom = path.steps[1]
    assert custom.skill_id is None and custom.resources == [] and custom.est_hours is None


async def test_alternatives_use_the_first_known_alternative() -> None:
    planner, _, _ = make_planner()
    matches = [gap(0, "Docker or Podman", None)]
    path = await planner.run(planner_input(matches, known=["linux"], alternatives={0: ["docker"]}))
    assert [s.skill_id for s in path.steps] == ["docker"]


async def test_no_gaps_means_no_llm_call() -> None:
    planner, model, _ = make_planner()
    path = await planner.run(planner_input([gap(0, "Python", "python", bucket="strong_in_resume")]))
    assert path.steps == [] and path.total_hours == 0
    assert model.requests == []


async def test_llm_may_reorder_independent_steps_and_writes_notes() -> None:
    def plan(model: str, text: str) -> PathPlan:
        return PathPlan(
            order=["terraform", "linux", "docker", "kubernetes"],
            notes=[StepNote(step_id="docker", why="Kubernetes runs containers.")],
        )

    planner, _, _ = make_planner(plan=plan)
    matches = [
        gap(0, "Kubernetes", "kubernetes"),
        gap(1, "Terraform", "terraform", importance="nice", weight=1.0),
    ]
    path = await planner.run(planner_input(matches, known=["cloud-computing"]))
    assert [s.skill_id for s in path.steps] == ["terraform", "linux", "docker", "kubernetes"]
    assert path.steps[2].why == "Kubernetes runs containers."
    assert path.steps[0].why == "The job asks for Terraform."  # default note


async def test_llm_order_breaking_prerequisites_is_ignored() -> None:
    def plan(model: str, text: str) -> PathPlan:
        return PathPlan(order=["kubernetes", "docker", "linux"], notes=[])

    planner, _, _ = make_planner(plan=plan)
    path = await planner.run(planner_input([gap(0, "Kubernetes", "kubernetes")]))
    assert [s.skill_id for s in path.steps] == ["linux", "docker", "kubernetes"]
    assert path.steps[0].why == "Comes first because Docker builds on it."


async def test_llm_failure_still_returns_the_path() -> None:
    def plan(model: str, text: str) -> PathPlan:
        raise RuntimeError("model down")

    planner, _, _ = make_planner(plan=plan)
    path = await planner.run(planner_input([gap(0, "Kubernetes", "kubernetes")]))
    assert len(path.steps) == 3


SKILL_IDS = sorted(TAXONOMY.skills)


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.sampled_from(SKILL_IDS), min_size=1, max_size=6, unique=True),
    st.lists(st.sampled_from(SKILL_IDS), max_size=4, unique=True),
    st.randoms(use_true_random=False),
)
def test_order_always_respects_the_taxonomy(
    gaps_ids: list[str], known: list[str], rnd: random.Random
) -> None:
    def plan(model: str, text: str) -> PathPlan:
        ids = [line.split(" ", 1)[0] for line in text.splitlines()[1:-1]]
        rnd.shuffle(ids)  # adversarial: an arbitrary order
        return PathPlan(order=ids, notes=[])

    planner, _, _ = make_planner(plan=plan)
    matches = [gap(i, sid, sid) for i, sid in enumerate(gaps_ids)]
    path = asyncio.run(planner.run(planner_input(matches, known=known)))

    position = {s.skill_id: s.step for s in path.steps}
    for s in path.steps:
        assert s.skill_id is not None
        for pre in TAXONOMY.prerequisite_closure(s.skill_id):  # direct and indirect
            if pre in position:
                assert position[pre] < s.step, f"{pre} must come before {s.skill_id}"


# -- seed file -------------------------------------------------------------------------


def test_seed_file_is_valid() -> None:
    rows = yaml.safe_load(SEED_FILE.read_text())["resources"]
    parsed = [LearningResource.model_validate(r) for r in rows]
    assert len(parsed) >= 150
    assert all(r.skill_id in TAXONOMY.skills for r in parsed)
    assert all(r.url.startswith("https://") for r in parsed)
    keys = [(r.skill_id, r.url) for r in parsed]
    assert len(keys) == len(set(keys))
    covered = {r.skill_id for r in parsed}
    for common in ("python", "sql", "docker", "kubernetes", "aws", "react", "machine-learning"):
        assert common in covered
