"""Regressions from a real analysis: bundled JD requirements and skills the LLM skipped."""

import pytest

from app.agents.jd_analyzer import JDAnalyzer, split_requirement
from app.agents.profile_extractor import SourceDocument, missed_skills
from app.agents.skill_normalizer import SkillNormalizer
from app.core.config import Settings
from app.llm.client import LLMClient
from app.parsing.sections import split_sections
from app.parsing.text import normalize_text, text_hash
from app.schemas.requirements import JobRequirements, Requirement
from app.skills.taxonomy import TECHNICAL_CATEGORIES, load_taxonomy
from tests.builders import profile, skill
from tests.fakes import FakeModel, InMemoryRepository

pytestmark = pytest.mark.anyio
TAXONOMY = load_taxonomy()
NORMALIZER = SkillNormalizer(TAXONOMY)


def requirement(name: str, category: str = "skill", importance: str = "must") -> Requirement:
    return Requirement.model_validate(
        {
            "name": name,
            "category": category,
            "importance": importance,
            "min_years": None,
            "evidence": name,
        }
    )


# -- JD: lists of skills that are all wanted become one requirement each ---------------------


@pytest.mark.parametrize(
    ("name", "category", "expected"),
    [
        (
            "Git, Docker, Kubernetes, and CI/CD pipelines",
            "skill",
            ["Git", "Docker", "Kubernetes", "CI/CD pipelines"],
        ),
        (
            "Solid foundation in applied statistics, probability, linear algebra, and algorithms",
            "domain",
            ["applied statistics", "probability", "linear algebra", "algorithms"],
        ),
        ("Communication and teamwork", "soft_skill", ["Communication", "teamwork"]),
        ("Pandas & NumPy", "skill", ["Pandas", "NumPy"]),
        # Alternatives, single skills and non-skill phrases stay whole.
        ("Java, C++, or R", "skill", ["Java, C++, or R"]),
        ("Data structures and algorithms", "skill", ["Data structures and algorithms"]),
        ("Research and development", "domain", ["Research and development"]),
        ("Design and implement REST APIs", "skill", ["Design and implement REST APIs"]),
        ("CI/CD", "skill", ["CI/CD"]),
        ("Bachelor's in CS and Mathematics", "education", ["Bachelor's in CS and Mathematics"]),
    ],
)
def test_split_requirement(name: str, category: str, expected: list[str]) -> None:
    parts = split_requirement(requirement(name, category), TAXONOMY)
    assert [p.name for p in parts] == expected
    assert {(p.category, p.importance) for p in parts} == {(category, "must")}


async def test_jd_analyzer_splits_bundled_requirements_and_dedupes() -> None:
    bundled = JobRequirements(
        role_title="ML Engineer",
        company=None,
        seniority=None,
        requirements=[
            requirement("Git, Docker, Kubernetes, and CI/CD pipelines"),
            requirement("Docker", importance="nice"),  # repeat: merged, stays a must
        ],
    )
    model = FakeModel({"JobRequirements": bundled})
    llm = LLMClient(Settings(_env_file=None, openai_model_small="m"), InMemoryRepository(), model)
    result = await JDAnalyzer(llm).run("Job description text " * 5)
    assert [(r.name, r.importance) for r in result.requirements] == [
        ("Git", "must"),
        ("Docker", "must"),
        ("Kubernetes", "must"),
        ("CI/CD pipelines", "must"),
    ]


# -- Profile: skills written in a document that the LLM skipped -----------------------------

RESUME = normalize_text(
    """Akhila M
TECHNICAL SKILLS
- Data Structures and Algorithms
- ORACLE Hyperion Planning
PROJECTS
- Bus booking site
ELECTIVE COURSES
- Numerical analysis
- Probability, Stochastic processes and Statistics
EXTRA CURRICULAR ACTIVITIES
- QRIOSITY is a Quiz club at IIT PALAKKAD and I am the member of it.
"""
)


def test_elective_courses_heading_is_recognised() -> None:
    names = [(s.name, s.heading) for s in split_sections(RESUME)]
    assert ("coursework", "ELECTIVE COURSES") in names
    assert ("achievements", "EXTRA CURRICULAR ACTIVITIES") in names


def test_skills_the_llm_skipped_are_added_with_verbatim_evidence() -> None:
    extracted = profile(skills=[skill("Data Structures and Algorithms")])
    doc = SourceDocument(doc_id="r", text=RESUME, text_hash=text_hash(RESUME))
    added = missed_skills(extracted, [("RESUME", "resume", doc)], TAXONOMY, NORMALIZER)

    by_name = {m.name: m for m in added}
    assert set(by_name) == {"Probability", "Statistics"}
    for m in added:
        assert m.source == "resume" and m.context == "education"  # an elective course
        assert m.evidence == "- Probability, Stochastic processes and Statistics"
        assert m.evidence in RESUME
    # Not added: already extracted (DSA and what it names), "ORACLE Hyperion" (not
    # Oracle Database), and "I am" (not IAM).


def test_scanning_prose_does_not_join_words_by_accident() -> None:
    concepts = TECHNICAL_CATEGORIES | {"concept"}
    assert TAXONOMY.find_in_text("and I am the member of it", concepts) == set()
    assert TAXONOMY.find_in_text("HTML,CSS,JAVA SCRIPT") >= {"javascript", "html", "css"}
    assert TAXONOMY.find_in_text("Mongo DB and Node JS") == {"mongodb", "nodejs"}
    # Concepts are only looked for when asked (default: technical skills).
    assert TAXONOMY.find_in_text("Probability and Statistics") == set()
