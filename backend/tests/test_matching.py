from datetime import date
from typing import Any

import pytest

from app.agents.matcher import EvidenceCatalog, Matcher
from app.agents.scorer import Scorer
from app.agents.skill_normalizer import SkillNormalizer
from app.core.config import Settings
from app.llm.client import LLMClient
from app.schemas.matching import EvidenceJudgements
from app.skills.taxonomy import (
    Taxonomy,
    TaxonomyError,
    TaxonomyFile,
    load_taxonomy,
    skill_key,
)
from tests.builders import cert, edu, job, judged, profile, project, req, reqs, skill
from tests.fakes import FakeModel, InMemoryRepository

pytestmark = pytest.mark.anyio

TAXONOMY = load_taxonomy()
NORMALIZER = SkillNormalizer(TAXONOMY)
AS_OF = date(2026, 9, 1)


# -- taxonomy ----------------------------------------------------------------------------


def test_taxonomy_file_is_valid_and_sizeable() -> None:
    assert len(TAXONOMY.skills) >= 250
    assert TAXONOMY.version


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("React.js", "reactjs"),
        ("Node JS", "nodejs"),
        ("Python 3", "python"),
        ("Angular 2+", "angular"),
        ("C++", "c++"),
        (".NET", ".net"),
        ("CI/CD", "ci/cd"),
        ("Scikit-Learn", "scikitlearn"),
        ("Ｐｙｔｈｏｎ", "python"),
        ("(SQL)", "sql"),
    ],
)
def test_skill_key(name: str, key: str) -> None:
    assert skill_key(name) == key


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ReactJS", "react"),
        ("Postgres", "postgresql"),
        ("K8s", "kubernetes"),
        ("golang", "go"),
        ("R", "r"),
        ("C#", "csharp"),
        ("Amazon Web Services", "aws"),
        ("Communication skills", "communication"),
        ("CI/CD pipelines", "ci-cd"),
        ("Tensorflow2", "tensorflow"),  # fuzzy
        ("Kubernete", "kubernetes"),  # fuzzy
        ("Javascrpt", "javascript"),  # fuzzy
        ("Quantum basket weaving", None),
        ("Rx", None),  # too short for fuzzy
    ],
)
def test_lookup_and_fuzzy(name: str, expected: str | None) -> None:
    assert (TAXONOMY.lookup(name) or TAXONOMY.fuzzy_lookup(name)) == expected


def test_java_and_javascript_are_distinct() -> None:
    assert TAXONOMY.lookup("Java") == "java"
    assert TAXONOMY.lookup("JavaScript") == "javascript"
    assert TAXONOMY.fuzzy_lookup("Javas") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Deployed FastAPI on a k3s cluster with Docker and GitHub Actions CI/CD.",
            {"fastapi", "kubernetes", "docker", "github", "github-actions", "ci-cd"},
        ),
        ("Terraform-managed AWS infra; front-end in React.js", {"terraform", "aws", "react"}),
        (
            "Used scikit-learn, HTML/CSS, C++ and .NET",
            {"scikit-learn", "html", "css", "cpp", "dotnet"},
        ),
        # Everyday words and soft skills are not detected.
        ("I go to meetups, rest, and move work to the cloud; strong communication", set()),
    ],
)
def test_find_in_text(text: str, expected: set[str]) -> None:
    assert TAXONOMY.find_in_text(text) == expected


def test_implied_closure_is_transitive() -> None:
    assert {"sql", "relational-databases", "databases"} <= TAXONOMY.implied_by("postgresql")
    assert "machine-learning" in TAXONOMY.implied_by("pytorch")  # via deep-learning
    assert TAXONOMY.implied_by("unknown") == frozenset()
    assert TAXONOMY.name("cpp") == "C++"
    assert "c" in TAXONOMY.prerequisites("cpp")


def _entry(sid: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": sid,
        "name": sid.title(),
        "category": "concept",
        "aliases": [],
        "prerequisites": [],
        "implies": [],
    }
    return {**base, **kw}


@pytest.mark.parametrize(
    ("skills", "message"),
    [
        ([_entry("a"), _entry("a")], "Duplicate"),
        ([_entry("a", aliases=["x"]), _entry("b", aliases=["X"])], "maps to both"),
        ([_entry("a", implies=["missing"])], "unknown skill"),
        ([_entry("a", prerequisites=["b"]), _entry("b", prerequisites=["a"])], "cycle"),
    ],
)
def test_taxonomy_validation(skills: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(TaxonomyError, match=message):
        Taxonomy(TaxonomyFile.model_validate({"version": "t", "skills": skills}))


# -- SkillNormalizer ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Python (pandas, NumPy)", ["python", "pandas", "numpy"]),
        ("HTML/CSS", ["html", "css"]),
        ("CI/CD", ["ci-cd"]),
        ("Data structures and algorithms", ["dsa", "data-structures", "algorithms"]),
        ("React & Redux", ["react", "redux"]),
        ("Flask", ["flask"]),
        ("Underwater welding", []),
    ],
)
def test_normalizer_resolves_compound_names(name: str, expected: list[str]) -> None:
    assert NORMALIZER.resolve(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Experience with Docker", "docker"),
        ("Strong knowledge of SQL", "sql"),
        ("Hands-on experience with AWS", "aws"),
        ("SQL/NoSQL databases", None),  # not one skill: left for the LLM
        ("AWS, GCP or Azure", None),  # alternatives: left for the LLM
        ("Python or Java", None),
        ("2+ years backend development", None),
    ],
)
def test_normalizer_requirements(name: str, expected: str | None) -> None:
    assert NORMALIZER.resolve_requirement(name) == expected


def test_normalizer_run_covers_mentions_projects_and_jobs() -> None:
    p = profile(
        skills=[skill("Postgres"), skill("Made-up Thing")],
        projects=[project("Shop", ["Next.js", "Tailwind"])],
        experience=[job("Intern", "Acme", "2025-01", "2025-06", ["Go", "gRPC"])],
    )
    out = NORMALIZER.run(p, reqs(req("PostgreSQL"), req("Teamwork", "soft_skill")))
    assert out.mention_ids == [["postgresql"], []]
    assert out.project_ids == [["nextjs", "tailwind"]]
    assert out.experience_ids == [["go", "grpc"]]
    assert out.requirement_ids == ["postgresql", "teamwork"]
    assert out.requirement_alternatives == [[], []]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Java, C++, or R", ["java", "cpp", "r"]),
        ("AWS, GCP or Azure", ["aws", "gcp", "azure"]),
        ("Experience with Python or Go", ["python", "go"]),
        ("Python", []),  # no alternatives
        ("Bachelor's or Master's degree", []),  # not skills
        ("Rust or something else", []),  # only one known alternative
    ],
)
def test_normalizer_alternatives(name: str, expected: list[str]) -> None:
    assert NORMALIZER.resolve_alternatives(name) == expected


async def test_any_alternative_is_direct_evidence() -> None:
    p = profile(skills=[skill("Java")], projects=[project("Bank app", ["Java"])])
    evidence, model = await _match(p, reqs(req("Java, C++, or R", importance="nice")))
    assert evidence[0].method == "taxonomy"
    assert {(r.kind, r.direct) for r in evidence[0].evidence} == {
        ("skill", True),
        ("project", True),
    }
    assert model.requests == []


# -- Matcher ---------------------------------------------------------------------------


def _llm(judgements: EvidenceJudgements | None = None) -> tuple[LLMClient, FakeModel]:
    model = FakeModel({"EvidenceJudgements": judgements or judged()})
    settings = Settings(_env_file=None, openai_model_small="small-model")
    return LLMClient(settings, InMemoryRepository(), model), model


async def _match(p: Any, r: Any, judgements: EvidenceJudgements | None = None) -> Any:
    llm, model = _llm(judgements)
    evidence = await Matcher(llm, TAXONOMY).run(p, r, NORMALIZER.run(p, r))
    return evidence, model


async def test_taxonomy_matches_direct_and_implied_without_llm() -> None:
    p = profile(
        skills=[skill("Python"), skill("PostgreSQL", "project", within="Shop")],
        projects=[project("Shop", ["FastAPI", "PostgreSQL"])],
    )
    evidence, model = await _match(p, reqs(req("Python"), req("SQL")))
    python, sql = evidence

    assert python.method == "taxonomy"
    direct = {(r.kind, r.direct) for r in python.evidence}
    assert ("skill", True) in direct
    assert ("project", False) in direct  # FastAPI implies Python

    # SQL is only implied by PostgreSQL, so it is also sent to the LLM (which found nothing).
    assert sql.method == "implied"
    assert all(not r.direct for r in sql.evidence)
    assert len(model.requests) == 1
    assert "R2 [skill] SQL" in model.requests[0]["input_text"]
    assert "R1 " not in model.requests[0]["input_text"]


async def test_no_llm_call_when_everything_has_direct_evidence() -> None:
    p = profile(skills=[skill("Python"), skill("Docker")])
    evidence, model = await _match(p, reqs(req("Python"), req("docker")))
    assert [e.method for e in evidence] == ["taxonomy", "taxonomy"]
    assert model.requests == []


async def test_fuzzy_name_match_for_skills_outside_the_taxonomy() -> None:
    p = profile(skills=[skill("Apache Pulsar")])
    evidence, model = await _match(p, reqs(req("Apache Pulsar ")))
    assert evidence[0].method == "fuzzy"
    assert evidence[0].skill_id is None
    assert model.requests == []


async def test_llm_judgements_map_ids_back_to_evidence() -> None:
    p = profile(
        skills=[skill("Python"), skill("Python", "project", within="Bot"), skill("Figma")],
        projects=[project("Bot", ["Python"])],
        experience=[job("TA", "Uni", "2024-01", "2024-12", kind="part_time")],
        education=[edu("B.Tech", "Computer Science")],
        certifications=[cert("AWS Cloud Practitioner", source="supplementary:d1")],
    )
    requirements = reqs(
        req("Python"),
        req("Bachelor's in CS", "education"),
        req("Mentoring students", "soft_skill"),
        req("Cloud fundamentals", "domain", "nice"),
        req("Rust"),
    )
    judgements = judged(
        ("R2", "direct", ["E1"]),
        ("R3", "direct", ["X1", "Z9"]),  # Z9 does not exist and is ignored
        ("R4", "implied", ["C1"]),
        ("R5", "none", []),
        ("R1", "direct", ["P1"]),  # R1 was resolved by the taxonomy: ignored
        ("banana", "direct", ["K1"]),  # malformed id: ignored
    )
    evidence, model = await _match(p, requirements, judgements)

    # Resume evidence and supplementary evidence are judged in separate calls.
    resume_prompt, other_prompt = (r["input_text"] for r in model.requests)
    assert resume_prompt.count("skill: Python") == 1  # repeated skill names are grouped
    assert "P1 project: Bot" in resume_prompt
    assert "X1 job: TA at Uni (2024-01 to 2024-12, part_time)" in resume_prompt
    assert "E1 education: B.Tech, Computer Science, State University" in resume_prompt
    assert "certification" not in resume_prompt
    assert other_prompt.endswith(
        "<evidence>\nC1 certification: AWS Cloud Practitioner\n</evidence>"
    )

    python, degree, mentoring, cloud, rust = evidence
    assert python.method == "taxonomy"
    assert degree.method == "llm" and degree.evidence[0].kind == "education"
    assert mentoring.method == "llm"
    assert [(r.kind, r.direct) for r in mentoring.evidence] == [("experience", True)]
    assert cloud.method == "implied"
    assert cloud.evidence[0].source == "supplementary:d1"
    assert rust.method == "none" and rust.evidence == []


async def test_combined_skill_is_direct_evidence_for_each_part() -> None:
    p = profile(skills=[skill("Data Structures and Algorithms"), skill("Linear Algebra")])
    evidence, model = await _match(p, reqs(req("algorithms"), req("linear algebra")))
    algorithms, algebra = evidence
    assert algorithms.method == "taxonomy"
    assert [(r.label, r.direct) for r in algorithms.evidence] == [
        ("Data Structures and Algorithms", True)
    ]
    assert [r.label for r in algebra.evidence] == ["Linear Algebra"]
    assert model.requests == []


async def test_llm_cannot_link_unrelated_known_skills() -> None:
    # Algorithms and linear algebra are both in the taxonomy and unrelated, so the LLM
    # calling "Linear Algebra" direct evidence for "Algorithms" is ignored. A skill the
    # taxonomy doesn't know is still up to the LLM.
    p = profile(skills=[skill("Linear Algebra"), skill("Underwater welding")])
    evidence, _ = await _match(
        p,
        reqs(req("Algorithms"), req("Diving safety", "domain")),
        judged(("R1", "direct", ["K1", "K2"]), ("R2", "direct", ["K1", "K2"])),
    )
    algorithms, diving = evidence
    assert [r.label for r in algorithms.evidence] == ["Underwater welding"]
    assert [r.label for r in diving.evidence] == ["Linear Algebra", "Underwater welding"]


async def test_experience_requirements_always_go_to_the_llm() -> None:
    p = profile(
        skills=[skill("Python")],
        experience=[job("Backend Intern", "Acme", "2025-01", "2025-06", ["Python"])],
    )
    requirements = reqs(req("Python", "experience", min_years=1))
    evidence, model = await _match(p, requirements, judged(("R1", "direct", ["X1"])))
    assert len(model.requests) == 1
    assert {r.kind for r in evidence[0].evidence} == {"skill", "experience"}


def test_catalog_handles_empty_profile_and_long_text() -> None:
    catalog = EvidenceCatalog(profile())
    assert catalog.lines == []
    assert catalog.refs("K1", direct=True) == []

    long = project("Big", ["Python"], summary="word " * 200)
    line = EvidenceCatalog(profile(projects=[long])).lines[0]
    assert line.endswith("…")
    assert len(line) < 400


# -- Scorer ------------------------------------------------------------------------------


async def test_scorer_end_to_end_small_case() -> None:
    p = profile(
        skills=[
            skill("Python"),
            skill("Python", "project", within="Bot"),
            skill("Docker"),
            skill("Kubernetes", "project", source="supplementary:d1", within="Deploy"),
        ],
        projects=[project("Bot", ["Python"])],
        experience=[job("Backend Intern", "Acme", "2025-01", "2025-06", ["Python"])],
    )
    requirements = reqs(
        req("Python"),  # listed + demonstrated -> 1.0
        req("Docker"),  # listed only -> 0.7
        req("Kubernetes", importance="nice"),  # supplementary only -> 0 resume, 0.7 best
        req("Terraform", importance="nice"),  # nothing -> 0
        req("1+ year backend experience", "experience", min_years=1),  # 6 months -> 0.5
    )
    evidence, _ = await _match(p, requirements, judged(("R5", "direct", ["X1"])))
    result = Scorer().run(requirements, evidence, p, as_of=AS_OF)

    # weights 3, 3, 1, 1, 3; resume = 3 + 2.1 + 0 + 0 + 1.5 = 6.6 / 11 = 60%
    assert result.fit_score == 60
    # potential adds Kubernetes 0.7 -> 7.3 / 11 = 66.36% -> 66
    assert result.potential_score == 66
    buckets = {m.name: m.bucket for m in result.matches}
    assert buckets == {
        "Python": "strong_in_resume",
        "Docker": "weak_in_resume",
        "Kubernetes": "missing_from_resume_but_evidenced",
        "Terraform": "true_gap",
        "1+ year backend experience": "weak_in_resume",
    }
    exp = result.matches[4]
    assert exp.resume_years == 0.5 and exp.resume_strength == 0.5
