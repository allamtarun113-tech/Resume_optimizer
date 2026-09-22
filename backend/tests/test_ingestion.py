import re
from pathlib import Path

import pytest
import yaml

from app.ingestion.questions import QuestionRecord as Record
from app.ingestion.questions import (
    Source,
    SourceFile,
    clean,
    looks_like_question,
    normalize_question,
    parse_file,
    question_hash,
)
from app.rag.templates import PLACEHOLDER_RE, load_templates
from app.skills.taxonomy import load_taxonomy
from scripts.ingest_questions import drop_near_duplicates

TAXONOMY = load_taxonomy()
SOURCES_FILE = Path(__file__).resolve().parents[2] / "ingestion" / "sources.yaml"
PERMISSIVE = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC0-1.0",
    "CC-BY-4.0",
    "Unlicense",
}


def source(**kw: object) -> Source:
    base: dict[str, object] = {
        "repo": "owner/repo",
        "ref": "main",
        "license": "MIT",
        "category": "technical",
        "role_tags": ["backend"],
        "files": [{"path": "README.md", "topics": ["python"]}],
    }
    return Source.model_validate({**base, **kw})


def parse(markdown: str, **kw: object) -> list[Record]:
    s = source(**kw)
    return parse_file(markdown, s, s.files[0], TAXONOMY)


# -- cleaning and detection -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[What is a closure?](#what-is-a-closure)", "What is a closure?"),
        ("<b>What is your favorite shell and why?</b>", "What is your favorite shell and why?"),
        ("**What is regression? 👶**", "What is regression?"),
        ("Q12: What is Docker?", "What is Docker?"),
        ("12. What is `useEffect`?", "What is useEffect?"),
        ("What is OSGI? (Specification describes a modular system...)", "What is OSGI?"),
        ("### What are microservices?", "What are microservices?"),
        ("What does &lt;code&gt; mean?", "What does <code> mean?"),
    ],
)
def test_clean(raw: str, expected: str) -> None:
    assert clean(raw) == expected


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("What is a closure?", True),
        ("Describe how processes are created", True),
        ("Design a URL shortener service", True),
        ("where folks came from", False),  # lowercase statement
        ("Why?", False),  # too short
        ("Table of Contents", False),
        ("See https://example.com for answers?", False),
        ("Python is a programming language", False),
    ],
)
def test_looks_like_question(text: str, ok: bool) -> None:
    assert looks_like_question(text) is ok


def test_normalize_and_hash_ignore_case_and_punctuation() -> None:
    assert normalize_question("What is  Docker?") == normalize_question("what is docker")
    assert question_hash("What is Docker?") == question_hash("what is docker ?")
    assert question_hash("What is C++?") != question_hash("What is C?")


# -- parsing ---------------------------------------------------------------------------

MARKDOWN = """# Java questions

## Concurrency
* How to correctly stop a thread? (Thread.interrupt())
* [What is a deadlock?](#what-is-a-deadlock)

```python
# What is inside code blocks is ignored?
print("How is this a question?")
```

| # | Question |
|---|----------|
| 1 | [What is a race condition?](#race) |

<details><summary><b>What does the fields in ls -al output mean?</b></summary>
answer text
</details>

**Can you explain how cross-validation works? 👶**

[How do I UPDATE from a SELECT in SQL Server?](#update)

## Docker
- What is the difference between an image and a container?
- This is an answer bullet, not a question.
"""


def test_parse_file_extracts_questions_from_every_structure() -> None:
    texts = [r.text for r in parse(MARKDOWN)]
    assert texts == [
        "How to correctly stop a thread?",
        "What is a deadlock?",
        "What is a race condition?",
        "What does the fields in ls -al output mean?",
        "Can you explain how cross-validation works?",
        "How do I UPDATE from a SELECT in SQL Server?",
        "What is the difference between an image and a container?",
    ]


def test_markers_restrict_structures() -> None:
    texts = [r.text for r in parse(MARKDOWN, markers=["summary"])]
    assert texts == ["What does the fields in ls -al output mean?"]


def test_records_carry_source_topics_and_license() -> None:
    records = {r.text: r for r in parse(MARKDOWN)}
    docker = records["What is the difference between an image and a container?"]
    assert docker.topics[0] == "python"  # file default first
    assert "docker" in docker.topics  # from the section heading
    sql = records["How do I UPDATE from a SELECT in SQL Server?"]
    assert "sql-server" in sql.topics  # from the question text
    assert docker.source_repo == "owner/repo" and docker.license == "MIT"
    assert docker.source_url == "https://github.com/owner/repo/blob/main/README.md"


def test_difficulty_markers() -> None:
    md = "**Easy one? 👶**\n\n**What is a medium question? ⭐️**\n\n**What is a hard question? 🚀**"
    by_text = {r.text: r.difficulty for r in parse(md, difficulty_markers=True)}
    assert by_text == {
        "What is a medium question?": "medium",
        "What is a hard question?": "hard",
    }  # "Easy one?" is too short


def test_behavioral_questions_about_the_candidate_are_personal() -> None:
    md = "1. Tell me about yourself.\n1. Tell me about a time you missed a deadline.\n"
    by_text = {r.text: r.category for r in parse(md, category="general")}
    assert by_text == {
        "Tell me about yourself": "personal",
        "Tell me about a time you missed a deadline": "general",
    }


def test_duplicates_within_a_file_are_dropped() -> None:
    md = "- What is Docker?\n## What is Docker?\n- what is docker ?"
    assert len(parse(md)) == 1


# -- near-duplicate removal ------------------------------------------------------------


def test_drop_near_duplicates_keeps_the_first() -> None:
    records = parse("- What is Docker?\n- What is a Docker container?\n- What is Kubernetes?")
    a, b, c = (r.text_hash for r in records)
    vectors = {a: [1.0, 0.0, 0.0], b: [0.99, 0.05, 0.0], c: [0.0, 1.0, 0.0]}
    kept = drop_near_duplicates(records, vectors)
    assert [r.text for r in kept] == ["What is Docker?", "What is Kubernetes?"]


# -- data files ------------------------------------------------------------------------


def test_sources_file_is_valid_and_permissive() -> None:
    raw = yaml.safe_load(SOURCES_FILE.read_text())["sources"]
    sources = [Source.model_validate(s) for s in raw]
    assert len(sources) >= 15
    for s in sources:
        assert s.license in PERMISSIVE, s.repo
        assert re.fullmatch(r"[\w.-]+/[\w.-]+", s.repo)
        for f in s.files:
            assert all(t in TAXONOMY.skills for t in f.topics), (s.repo, f.path)
    assert {"general", "technical"} <= {s.category for s in sources}
    roles = {r for s in sources for r in s.role_tags}
    assert {"frontend", "backend", "devops", "data", "ml"} <= roles


def test_template_bank_is_valid() -> None:
    templates = load_templates()
    assert len(templates) >= 40
    assert len({t.id for t in templates}) == len(templates)
    for t in templates:
        stripped = PLACEHOLDER_RE.sub("", t.text)
        assert "{" not in stripped, t.id  # only known placeholders
        assert "{project}" in t.text, t.id
    generic = [t for t in templates if t.facets == ["any"]]
    assert len({t.dimension for t in generic}) >= 8
    assert len(generic) >= 15


def test_source_file_defaults() -> None:
    assert SourceFile(path="x.md").topics == []
