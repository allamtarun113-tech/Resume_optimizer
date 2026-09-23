from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.jd_analyzer import NOT_A_JD_MESSAGE
from app.api.deps import get_llm_client, get_repository
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.llm.client import LLMClient
from app.main import create_app
from app.schemas.advice import ResumeAdvice
from app.schemas.learning import PathPlan
from app.schemas.requirements import JDAnalysis
from app.scoring.weights import SCORING_VERSION
from tests.builders import judged
from tests.fakes import FakeModel, InMemoryRepository
from tests.samples import (
    JOB_DESCRIPTION,
    PROFILE_FIXTURE,
    REQUIREMENTS_FIXTURE,
    RESUME_CLASSIC,
    SUPPORTING_PROJECT,
    make_pdf,
)

USER = CurrentUser(id="11111111-1111-4111-8111-111111111111", email="a@example.com")
OTHER = CurrentUser(id="22222222-2222-4222-8222-222222222222", email="b@example.com")
RESUME_PDF = make_pdf(RESUME_CLASSIC.replace("•", "-"))


class Harness:
    def __init__(self, settings: Settings) -> None:
        self.repo = InMemoryRepository()
        self.model = FakeModel(
            {
                "StudentProfile": PROFILE_FIXTURE,
                "JobRequirements": REQUIREMENTS_FIXTURE,
                "EvidenceJudgements": judged(("R4", "direct", ["C1"])),
                # Advice and study-plan steps answer "nothing to add" unless a test says so.
                "ResumeAdvice": ResumeAdvice(suggestions=[]),
                "PathPlan": PathPlan(order=[], notes=[]),
            }
        )
        self.user = USER
        self.settings = settings.model_copy(update={"openai_model_small": "small-model"})
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: self.settings
        app.dependency_overrides[get_repository] = lambda: self.repo
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_llm_client] = lambda: LLMClient(
            self.settings, self.repo, self.model
        )
        self.client = TestClient(app)

    def upload_resume(self, data: bytes = RESUME_PDF, name: str = "resume.pdf") -> Any:
        return self.client.post(
            "/documents",
            data={"kind": "resume"},
            files={"file": (name, data, "application/pdf")},
        )

    def paste_supporting(self, text: str = SUPPORTING_PROJECT) -> Any:
        return self.client.post("/documents", data={"kind": "supporting", "text": text})

    def analyze(self, resume_id: str, supporting: list[str] | None = None, **extra: Any) -> Any:
        body = {
            "resume_doc_id": resume_id,
            "jd_text": JOB_DESCRIPTION,
            "supporting_doc_ids": supporting or [],
            **extra,
        }
        return self.client.post("/analyses", json=body)


@pytest.fixture
def h(settings: Settings) -> Iterator[Harness]:
    harness = Harness(settings)
    with harness.client:
        yield harness


# -- documents ---------------------------------------------------------------------------


def test_upload_resume_pdf_extracts_text_and_stores_file(h: Harness) -> None:
    res = h.upload_resume()
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "resume"
    assert body["filename"] == "resume.pdf"
    assert "projects" in body["sections"]

    doc = h.repo.documents[body["id"]]
    assert doc.user_id == USER.id
    assert doc.storage_path and doc.storage_path.startswith(f"{USER.id}/")
    assert doc.storage_path.endswith(".pdf")
    assert h.repo.files[doc.storage_path] == RESUME_PDF
    assert "Campus Food Ordering App" in (doc.extracted_text or "")


def test_upload_rejects_scanned_pdf(h: Harness) -> None:
    res = h.upload_resume(make_pdf(""), "scan.pdf")
    assert res.status_code == 422
    assert "scanned" in res.json()["detail"]
    assert not h.repo.documents


def test_upload_rejects_large_files(h: Harness) -> None:
    res = h.upload_resume(b"%PDF-" + b"0" * (5 * 1024 * 1024), "big.pdf")
    assert res.status_code == 413


def test_upload_rejects_unsupported_type(h: Harness) -> None:
    res = h.client.post(
        "/documents",
        data={"kind": "supporting"},
        files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
    )
    assert res.status_code == 422


def test_resume_must_be_a_file_and_input_must_be_one_of_file_or_text(h: Harness) -> None:
    pasted_resume = h.client.post("/documents", data={"kind": "resume", "text": RESUME_CLASSIC})
    assert pasted_resume.status_code == 422
    assert h.client.post("/documents", data={"kind": "supporting"}).status_code == 422


def test_paste_supporting_text(h: Harness) -> None:
    res = h.paste_supporting()
    assert res.status_code == 201
    doc = h.repo.documents[res.json()["id"]]
    assert doc.kind == "supporting"
    assert doc.storage_path is None


def test_documents_require_auth(settings: Settings) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        assert client.post("/documents", data={"kind": "supporting"}).status_code == 401
        assert client.get("/analyses/11111111-1111-4111-8111-111111111111").status_code == 401


# -- analyses ----------------------------------------------------------------------------


def test_analysis_runs_extraction_and_returns_results(h: Harness) -> None:
    resume_id = h.upload_resume().json()["id"]
    supporting_id = h.paste_supporting().json()["id"]

    created = h.analyze(resume_id, [supporting_id], extra_text="I also know Terraform.")
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]

    # TestClient runs background tasks before returning.
    res = h.client.get(f"/analyses/{analysis_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "done", body["error"]
    assert h.repo.status_history[analysis_id] == [
        "queued",
        "parsing",
        "extracting",
        "scoring",
        "advising",
        "done",
    ]
    assert body["prompt_versions"] == {
        "profile_extractor": "2",
        "jd_analyzer": "3",
        "evidence_matcher": "1",
        "resume_advisor": "1",
        "learning_path_planner": "1",
    }
    assert body["job_requirements"]["role_title"] == "Backend Engineer"

    skills = {s["name"]: s["source"] for s in body["student_profile"]["skills"]}
    assert skills["Python"] == "resume"
    assert skills["Kubernetes"].startswith("supplementary:")
    # Profile (resume, supporting), JD, matcher (resume evidence, supporting evidence),
    # advisor (FastAPI is stronger in the supporting doc than on the resume).
    assert body["llm_usage"]["calls"] == 6
    assert body["llm_usage"]["cached_calls"] == 0

    # Requirements (deduped): Python, FastAPI, Docker (must), AWS (nice), Communication.
    # Python listed only 0.7; FastAPI shown in a project 0.7; AWS via certification 0.7.
    # Docker: the fixture extraction missed it, but the resume lists it ("Tools: Git,
    # Docker, PostgreSQL"), so the safety net adds it: listed only, 0.7.
    # 100 × (2.1 + 2.1 + 2.1 + 0.7 + 0) / (3 + 3 + 3 + 1 + 1.2) = 62.5 -> 63
    assert body["fit_score"] == 63
    docker = next(s for s in body["student_profile"]["skills"] if s["name"] == "Docker")
    assert (docker["source"], docker["context"]) == ("resume", "skills_section")
    assert docker["evidence"] == "Tools: Git, Docker, PostgreSQL"
    assert body["scoring_version"] == SCORING_VERSION
    buckets = {m["name"]: m["bucket"] for m in body["matches"]}
    assert buckets == {
        "Python": "weak_in_resume",
        "FastAPI": "weak_in_resume",
        "Docker": "weak_in_resume",
        "AWS": "weak_in_resume",
        "Communication": "true_gap",
    }
    # The (fake) advisor suggests nothing; Communication is the only gap.
    assert body["suggestions"] == []
    assert [g["name"] for g in body["gaps"]] == ["Communication"]
    # Communication is a soft skill, not a study step: nothing to plan, no planner call.
    assert body["learning_path"] == {"steps": [], "total_hours": 0.0}

    # Two profile prompts: the resume alone, then the supporting doc and the extra text.
    profile_prompts = [
        r["input_text"] for r in h.model.requests if r["output_type"] == "StudentProfile"
    ]
    assert sorted(p.count("<document id=") for p in profile_prompts) == [1, 2]
    assert any("Terraform" in p and "RESUME" not in p for p in profile_prompts)

    analysis = h.repo.analyses[analysis_id]
    extra_docs = [h.repo.documents[i] for i in analysis.supporting_doc_ids]
    assert [d.kind for d in extra_docs] == ["supporting", "extra_text"]
    assert h.repo.documents[analysis.jd_doc_id or ""].kind == "jd"


def test_identical_second_run_is_fully_cached(h: Harness) -> None:
    # Re-upload the same files: new document ids, same content.
    first = h.analyze(h.upload_resume().json()["id"], [h.paste_supporting().json()["id"]])
    second = h.analyze(h.upload_resume().json()["id"], [h.paste_supporting().json()["id"]])

    first_body = h.client.get(f"/analyses/{first.json()['id']}").json()
    second_body = h.client.get(f"/analyses/{second.json()['id']}").json()
    assert len(h.model.requests) == 6  # only the first run reached the model
    assert second_body["fit_score"] == first_body["fit_score"]
    assert second_body["matches"] is not None
    assert second_body["llm_usage"] == {
        "calls": 6,
        "cached_calls": 6,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    assert second_body["job_requirements"] == first_body["job_requirements"]
    # Same content, but sources point at each run's own documents.
    first_kube = next(
        s for s in first_body["student_profile"]["skills"] if s["name"] == "Kubernetes"
    )
    second_kube = next(
        s for s in second_body["student_profile"]["skills"] if s["name"] == "Kubernetes"
    )
    assert first_kube["source"] != second_kube["source"]


def test_failed_extraction_marks_analysis_failed_with_safe_message(h: Harness) -> None:
    def explode(model: str, input_text: str) -> Any:
        raise RuntimeError("secret internal detail")

    h.model.responses["JobRequirements"] = explode
    created = h.analyze(h.upload_resume().json()["id"])
    body = h.client.get(f"/analyses/{created.json()['id']}").json()
    assert body["status"] == "failed"
    assert body["error"] == "Something went wrong while analyzing. Please try again."
    assert "secret" not in body["error"]


def test_text_that_is_not_a_job_description_fails_with_a_clear_message(h: Harness) -> None:
    def chat_message(model: str, input_text: str) -> Any:
        return JDAnalysis(
            role_title=None,
            company=None,
            seniority=None,
            requirements=[],
            is_job_description=False,
        )

    h.model.responses["JDAnalysis"] = chat_message
    created = h.analyze(h.upload_resume().json()["id"])
    body = h.client.get(f"/analyses/{created.json()['id']}").json()
    assert body["status"] == "failed"
    assert body["error"] == NOT_A_JD_MESSAGE
    assert body["fit_score"] is None


def test_analysis_validates_documents(h: Harness) -> None:
    resume_id = h.upload_resume().json()["id"]
    supporting_id = h.paste_supporting().json()["id"]

    # A supporting doc can't be used as the resume, and vice versa.
    assert h.analyze(supporting_id).status_code == 404
    assert h.analyze(resume_id, [resume_id]).status_code == 404
    assert h.analyze("not-a-uuid").status_code == 422
    assert h.analyze(resume_id, jd_text="too short").status_code == 422
    assert h.analyze(resume_id, [supporting_id] * 21).status_code == 422

    # Another user's documents and analyses are invisible.
    analysis_id = h.analyze(resume_id).json()["id"]
    h.user = OTHER
    assert h.analyze(resume_id).status_code == 404
    assert h.client.get(f"/analyses/{analysis_id}").status_code == 404


def test_no_daily_analysis_limit(h: Harness) -> None:
    resume_id = h.upload_resume().json()["id"]
    for _ in range(15):
        assert h.analyze(resume_id).status_code == 202


def test_unknown_analysis_is_404(h: Harness) -> None:
    assert h.client.get("/analyses/33333333-3333-4333-8333-333333333333").status_code == 404


def test_openai_quota_error_gets_a_specific_message() -> None:
    import httpx2
    import openai

    from app.orchestrator.pipeline import user_message

    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")

    def rate_limit(code: str) -> openai.RateLimitError:
        return openai.RateLimitError(
            "429", response=httpx2.Response(429, request=request), body={"code": code}
        )

    assert "run out of credit" in user_message(rate_limit("insufficient_quota"))
    assert "busy" in user_message(rate_limit("rate_limit_exceeded"))


def test_suggestions_flow_through_the_pipeline(h: Harness) -> None:
    from app.schemas.advice import ResumeAdvice, SuggestionDraft
    from tests.builders import req, reqs
    from tests.test_advice import qid

    h.model.responses["JobRequirements"] = reqs(req("Kubernetes"))

    def advise(model: str, prompt: str) -> ResumeAdvice:
        return ResumeAdvice(
            suggestions=[
                SuggestionDraft(
                    requirement_ids=["R1"],
                    evidence_ids=[qid(prompt, "3-node k3s")],
                    section="projects",
                    action="expand_project",
                    target="Campus Food Ordering App",
                    suggested_text="Deployed the backend on a 3-node Kubernetes (k3s) cluster.",
                    quote="deployed it on a 3-node k3s cluster",
                    rationale="The job requires Kubernetes.",
                ),
                SuggestionDraft(
                    requirement_ids=["R1"],
                    evidence_ids=[qid(prompt, "3-node k3s")],
                    section="skills",
                    action="add_skill",
                    target=None,
                    suggested_text="Kubernetes",
                    quote="managed a 50-node production cluster",  # not in any document
                    rationale="Invented.",
                ),
            ]
        )

    h.model.responses["ResumeAdvice"] = advise
    created = h.analyze(h.upload_resume().json()["id"], [h.paste_supporting().json()["id"]])
    body = h.client.get(f"/analyses/{created.json()['id']}").json()

    assert body["status"] == "done", body["error"]
    assert body["fit_score"] == 0 and body["potential_score"] == 70
    (suggestion,) = body["suggestions"]
    assert suggestion["quote_source_label"] == "your pasted text"
    assert suggestion["uplift"] == 70
    assert suggestion["requirement_names"] == ["Kubernetes"]
    assert [r["reason"] for r in body["rejected_suggestions"]] == [
        "Its quote isn't in your documents."
    ]
    assert body["gaps"] == []


def test_changing_notes_never_changes_the_resume_score(h: Harness) -> None:
    # Same resume and job; the notes differ only in letter case.
    first = h.analyze(h.upload_resume().json()["id"], extra_text="Additional skills: Kubernetes.")
    calls_before = len(h.model.requests)
    second = h.analyze(h.upload_resume().json()["id"], extra_text="Additional skills: kubernetes.")
    first_body = h.client.get(f"/analyses/{first.json()['id']}").json()
    second_body = h.client.get(f"/analyses/{second.json()['id']}").json()

    assert second_body["fit_score"] == first_body["fit_score"]
    # Only the notes were read again; everything about the resume came from the cache.
    (new_prompt,) = [r["input_text"] for r in h.model.requests[calls_before:]]
    assert new_prompt.startswith('<document id="S1">') and "kubernetes" in new_prompt
