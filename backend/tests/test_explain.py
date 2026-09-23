from collections.abc import Iterator
from typing import Any

import pytest

from app.agents.explainer import ExplainNotFound, build_request, strength_text
from app.core.config import Settings
from app.schemas.analyses import AnalysisResponse
from app.schemas.explain import Explanation
from app.schemas.interview import InterviewQuestion, InterviewSet, ProjectQuestions, QuestionSource
from tests.test_api_analyses import OTHER, Harness

ANSWER = Explanation(
    summary="Your resume shows most of what the job asks for.",
    details=["Python is listed and used in a project."],
    next_steps=["Add your Docker project to the resume."],
)


@pytest.fixture
def h(settings: Settings) -> Iterator[Harness]:
    harness = Harness(settings)
    harness.model.responses["Explanation"] = ANSWER
    with harness.client:
        yield harness


def finished(h: Harness) -> dict[str, Any]:
    created = h.analyze(h.upload_resume().json()["id"], [h.paste_supporting().json()["id"]])
    body: dict[str, Any] = h.client.get(f"/analyses/{created.json()['id']}").json()
    assert body["status"] == "done", body["error"]
    return body


def explain(h: Harness, analysis_id: str, kind: str, ref: str = "") -> Any:
    return h.client.post(f"/analyses/{analysis_id}/explain", json={"kind": kind, "ref": ref})


def explainer_inputs(h: Harness) -> list[str]:
    return [r["input_text"] for r in h.model.requests if r["output_type"] == "Explanation"]


def test_explain_score_uses_the_scoring_rules_and_is_cached(h: Harness) -> None:
    body = finished(h)
    res = explain(h, body["id"], "score")
    assert res.status_code == 200
    assert res.json() == ANSWER.model_dump()
    (prompt,) = explainer_inputs(h)
    assert f"Job fit (resume): {body['fit_score']}%" in prompt
    assert "How the score works" in prompt
    for m in body["matches"]:
        assert m["name"] in prompt

    # Clicking again is a cache hit: no second model call.
    assert explain(h, body["id"], "score").status_code == 200
    assert len(explainer_inputs(h)) == 1


def test_explain_requirement_includes_its_evidence(h: Harness) -> None:
    body = finished(h)
    match = next(m for m in body["matches"] if m["evidence"])
    res = explain(h, body["id"], "requirement", str(match["requirement_index"]))
    assert res.status_code == 200
    (prompt,) = explainer_inputs(h)
    assert f'"{match["name"]}"' in prompt
    assert match["evidence"][0]["label"] in prompt


def test_explain_unknown_items_and_other_users(h: Harness) -> None:
    body = finished(h)
    assert explain(h, body["id"], "requirement", "999").status_code == 404
    assert explain(h, body["id"], "suggestion", "nope").status_code == 404
    assert explain(h, body["id"], "learning_step", "999").status_code == 404
    assert explain(h, body["id"], "interview_question", "technical:0").status_code == 404
    assert h.client.post(f"/analyses/{body['id']}/explain", json={"kind": "bad"}).status_code == 422
    h.user = OTHER
    assert explain(h, body["id"], "score").status_code == 404
    assert explainer_inputs(h) == []


def test_explain_llm_failure_is_a_clear_error(h: Harness) -> None:
    from app.llm.client import LLMError

    body = finished(h)

    def fail(model: str, prompt: str) -> Explanation:
        raise LLMError("The AI returned an unusable answer.")

    h.model.responses["Explanation"] = fail
    res = explain(h, body["id"], "score")
    assert res.status_code == 502
    assert "unusable" in res.json()["detail"]


# -- build_request, for kinds that need extra data ------------------------------------------


def _analysis(h: Harness) -> AnalysisResponse:
    return AnalysisResponse.model_validate(finished(h))


def _question(text: str, category: str = "technical") -> InterviewQuestion:
    return InterviewQuestion(
        text=text,
        category=category,  # type: ignore[arg-type]
        topic="Python" if category == "technical" else None,
        dimension="trade-offs" if category == "project" else None,
        source=QuestionSource(kind="template", label="bank", url=None, license=None),
    )


def test_build_request_for_interview_questions(h: Harness) -> None:
    analysis = _analysis(h)
    interview = InterviewSet(
        personal=[_question("Tell me about yourself.", "personal")],
        projects=[
            ProjectQuestions(
                project="Campus Food Ordering App",
                technologies=["FastAPI"],
                questions=[_question("Why FastAPI for this app?", "project")],
            )
        ],
        technical=[_question("What is a Python generator?")],
        general=[],
    )
    question, facts = build_request(analysis, "interview_question", "project:0:0", interview)
    assert "interviewer" in question
    assert "Question: Why FastAPI for this app?" in facts
    assert "Project: Campus Food Ordering App" in facts
    _, facts = build_request(analysis, "interview_question", "technical:0", interview)
    assert "Job topic: Python" in facts
    for ref in ("general:0", "project:1:0", "project:x:0", "technical", "other:0"):
        with pytest.raises(ExplainNotFound):
            build_request(analysis, "interview_question", ref, interview)


def test_build_request_for_learning_steps_and_suggestions(h: Harness) -> None:
    from app.schemas.advice import Suggestion
    from app.schemas.learning import LearningPath, LearningStep

    analysis = _analysis(h)
    match = analysis.matches[0]  # type: ignore[index]
    suggestion = Suggestion(
        id="s1",
        requirement_indexes=[match.requirement_index],
        requirement_names=[match.name],
        section="projects",
        action="expand_project",
        target="Campus Food Ordering App",
        suggested_text="Deployed the app with Docker.",
        rationale="The job asks for Docker.",
        quote="I containerized the app",
        quote_source="supplementary:x",
        quote_source_label="your notes",
        evidence=[],
        uplift=9,
    )
    step = LearningStep(
        step=1,
        skill_id="aws",
        name="AWS",
        kind="gap",
        for_requirements=[match.name],
        unlocks=[],
        why="The job lists it.",
        resources=[],
        est_hours=None,
    )
    analysis = analysis.model_copy(
        update={
            "suggestions": [suggestion],
            "learning_path": LearningPath(steps=[step], total_hours=0),
        }
    )

    _, facts = build_request(analysis, "suggestion", "s1")
    assert 'Suggested text: "Deployed the app with Docker."' in facts
    assert "Where to add it: projects → Campus Food Ordering App" in facts
    question, facts = build_request(analysis, "learning_step", "1")
    assert "AWS" in question and "Step 1 of 1: AWS" in facts
    assert "Resources: none curated yet" in facts

    # A requirement links to its suggestion and learning step.
    _, facts = build_request(analysis, "requirement", str(match.requirement_index))
    assert 'Suggested resume change: "Deployed the app with Docker." (+9 points)' in facts
    assert "In the learning path as step 1: AWS" in facts


def test_explain_interview_question_through_the_api(h: Harness) -> None:
    body = finished(h)
    interview = InterviewSet(
        personal=[], projects=[], technical=[_question("What is a Python generator?")], general=[]
    )
    h.repo.interview_sets[body["id"]] = interview.model_dump(mode="json")
    assert explain(h, body["id"], "interview_question", "technical:0").status_code == 200
    (prompt,) = explainer_inputs(h)
    assert "What is a Python generator?" in prompt


def test_strength_text() -> None:
    assert strength_text(1.0) == "strong (1.0)"
    assert strength_text(0.7) == "listed (0.7)"
    assert strength_text(0.4) == "partial (0.4)"
    assert strength_text(0.0) == "missing (0)"
