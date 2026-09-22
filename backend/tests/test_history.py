from collections.abc import Iterator
from typing import Any

import pytest

from app.api.documents import _safe_filename
from app.core.config import Settings
from app.export.report import build_markdown_report, report_filename
from app.schemas.analyses import AnalysisResponse
from app.schemas.interview import InterviewSet
from tests.samples import JOB_DESCRIPTION
from tests.test_api_analyses import OTHER, Harness

pytestmark = pytest.mark.anyio

OTHER_JD = "Data Analyst. Requirements: SQL, Excel, Tableau, statistics, and communication."


@pytest.fixture
def h(settings: Settings) -> Iterator[Harness]:
    harness = Harness(settings)
    with harness.client:
        yield harness


def run(h: Harness, **kw: Any) -> str:
    resume_id = h.upload_resume().json()["id"]
    supporting_id = h.paste_supporting().json()["id"]
    res = h.analyze(resume_id, [supporting_id], extra_text="I also know Terraform.", **kw)
    assert res.status_code == 202, res.text
    analysis_id: str = res.json()["id"]
    return analysis_id


def test_history_lists_own_analyses_newest_first(h: Harness) -> None:
    first, second = run(h), run(h)
    res = h.client.get("/analyses")
    assert res.status_code == 200
    items = res.json()
    assert [i["id"] for i in items] == [second, first]
    assert items[0]["role_title"] == "Backend Engineer"
    assert items[0]["company"] == "Example Corp"
    assert items[0]["fit_score"] == 44 and items[0]["status"] == "done"

    h.user = OTHER
    assert h.client.get("/analyses").json() == []


def test_rerun_reuses_documents_with_a_new_jd(h: Harness) -> None:
    original = run(h)
    before = len(h.model.requests)
    res = h.client.post(f"/analyses/{original}/rerun", json={"jd_text": OTHER_JD})
    assert res.status_code == 202, res.text
    new_id = res.json()["id"]

    old, new = h.repo.analyses[original], h.repo.analyses[new_id]
    assert new.resume_doc_id == old.resume_doc_id
    assert new.supporting_doc_ids == old.supporting_doc_ids  # incl. the extra-text notes
    assert new.jd_doc_id != old.jd_doc_id
    assert h.repo.documents[new.jd_doc_id or ""].extracted_text == OTHER_JD
    assert h.repo.analyses[new_id].status == "done"
    # The profile extraction came from the cache: only the JD side hit the model.
    new_calls = [r["output_type"] for r in h.model.requests[before:]]
    assert "StudentProfile" not in new_calls
    assert "JobRequirements" in new_calls


def test_rerun_validation(h: Harness) -> None:
    original = run(h)
    assert (
        h.client.post(f"/analyses/{original}/rerun", json={"jd_text": "short"}).status_code == 422
    )
    missing = "33333333-3333-4333-8333-333333333333"
    assert (
        h.client.post(f"/analyses/{missing}/rerun", json={"jd_text": OTHER_JD}).status_code == 404
    )
    h.user = OTHER
    assert (
        h.client.post(f"/analyses/{original}/rerun", json={"jd_text": OTHER_JD}).status_code == 404
    )


def test_rerun_counts_towards_the_daily_limit(h: Harness) -> None:
    original = run(h)
    for _ in range(2):
        assert (
            h.client.post(f"/analyses/{original}/rerun", json={"jd_text": OTHER_JD}).status_code
            == 202
        )
    assert (
        h.client.post(f"/analyses/{original}/rerun", json={"jd_text": OTHER_JD}).status_code == 429
    )


def test_delete_analysis(h: Harness) -> None:
    analysis_id = run(h)
    h.user = OTHER
    assert h.client.delete(f"/analyses/{analysis_id}").status_code == 404
    from tests.test_api_analyses import USER

    h.user = USER
    assert h.client.delete(f"/analyses/{analysis_id}").status_code == 204
    assert h.client.get(f"/analyses/{analysis_id}").status_code == 404
    assert h.client.delete(f"/analyses/{analysis_id}").status_code == 404


def test_export_markdown(h: Harness) -> None:
    analysis_id = run(h)
    res = h.client.get(f"/analyses/{analysis_id}/export")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    assert 'filename="resume-optimizer-backend-engineer-' in res.headers["content-disposition"]
    text = res.text
    assert text.startswith("# Backend Engineer at Example Corp")
    assert "**Job Fit Score:** 44%" in text
    assert "### Skill gaps" in text and "- Docker (must have)" in text


def test_export_includes_interview_questions_with_sources() -> None:
    analysis = AnalysisResponse.model_validate(
        {
            "id": "a",
            "status": "done",
            "error": None,
            "created_at": "2026-09-23T10:00:00Z",
            "updated_at": "2026-09-23T10:00:00Z",
            "prompt_versions": {},
            "fit_score": 50,
            "potential_score": 60,
            "scoring_version": "2",
            "student_profile": None,
            "job_requirements": None,
            "matches": None,
            "suggestions": None,
            "rejected_suggestions": None,
            "gaps": None,
            "learning_path": None,
            "llm_usage": {"calls": 0, "cached_calls": 0, "input_tokens": 0, "output_tokens": 0},
        }
    )
    question = {
        "text": "What is Docker?",
        "category": "technical",
        "topic": "Docker",
        "source": {
            "kind": "github",
            "label": "o/r",
            "url": "https://github.com/o/r",
            "license": "MIT",
        },
    }
    interview = InterviewSet.model_validate(
        {"personal": [], "projects": [], "technical": [question], "general": []}
    )
    text = build_markdown_report(analysis, interview)
    assert "# Job analysis" in text
    assert "1. What is Docker?  \n   _Source: https://github.com/o/r_" in text
    assert report_filename(analysis) == "resume-optimizer-analysis-2026-09-23.md"


def test_export_requires_a_finished_analysis(h: Harness) -> None:
    analysis_id = run(h)
    h.repo.analyses[analysis_id] = h.repo.analyses[analysis_id].model_copy(
        update={"status": "scoring"}
    )
    assert h.client.get(f"/analyses/{analysis_id}/export").status_code == 409


def test_daily_upload_limit(h: Harness) -> None:
    h.settings = h.settings.model_copy(update={"daily_upload_limit": 2})
    assert h.paste_supporting().status_code == 201
    assert h.paste_supporting().status_code == 201
    res = h.paste_supporting()
    assert res.status_code == 429
    assert "2 uploads per day" in res.json()["detail"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("resume.pdf", "resume.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\cv.docx", "cv.docx"),
        ("bad\x00name\n.pdf", "badname.pdf"),
        (None, "upload"),
        ("", "upload"),
        ("x" * 300 + ".pdf", "x" * 200),
    ],
)
def test_safe_filename(name: str | None, expected: str) -> None:
    assert _safe_filename(name) == expected


def test_jd_fixture_is_long_enough() -> None:
    assert len(JOB_DESCRIPTION) >= 50 and len(OTHER_JD) >= 50
