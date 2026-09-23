"""Explainer (LLM, small): the "Explain" buttons on the results page.

Python picks the facts about the clicked item from the stored analysis (never from the
browser), so the LLM only rephrases what the analysis already knows. Same item → same
prompt → cache hit, so each explanation costs at most one call.
"""

from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.schemas.analyses import AnalysisResponse
from app.schemas.explain import ExplainKind, Explanation
from app.schemas.interview import InterviewQuestion, InterviewSet
from app.schemas.matching import RequirementMatch

MAX_OUTPUT_TOKENS = 700
MAX_SNIPPET_CHARS = 300

BUCKET_TEXT = {
    "strong_in_resume": "Strong match: on the resume and shown in a project or job.",
    "weak_in_resume": "Weak on the resume: mentioned, but not clearly shown in a project or job.",
    "missing_from_resume_but_evidenced": (
        "Not on the resume, but the student's other documents or notes show it."
    ),
    "true_gap": "Skill gap: nothing the student gave shows it yet.",
}

IMPORTANCE_TEXT = {"must": "must-have", "nice": "nice-to-have"}

SCORING_RULES = """\
How the score works (fixed rules, same input always gives the same score):
- Each job requirement has a weight: must-have x3, nice-to-have x1; then by type: skill or
  experience 1.0, domain knowledge 0.9, education 0.6, soft skill 0.4.
- Each requirement gets a strength from the RESUME only: 1.0 = listed and shown in a
  project or job; 0.7 = only listed (or only shown); 0.4 = only hinted at; 0 = not there.
  Years of experience count as your years divided by the years asked for (max 1.0).
- Job fit = weighted average of the strengths, as a percentage.
- "With what you already have" = the same, but also counting the student's other documents
  and notes. The difference is what adding those things to the resume could gain.
- ATS score = how well an applicant tracking system (the software many employers use to
  sort resumes) can read the resume file and find the job's skill keywords in it, word
  for word. Each check earns points; the score is the share of points earned.
- Final score = 70% job fit + 30% ATS score."""


class ExplainNotFound(LookupError):
    pass


def strength_text(strength: float) -> str:
    if strength >= 1:
        return "strong (1.0)"
    if strength >= 0.7:
        return f"listed ({strength:g})"
    if strength > 0:
        return f"partial ({strength:g})"
    return "missing (0)"


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_SNIPPET_CHARS else text[: MAX_SNIPPET_CHARS - 1] + "…"


def _where(source: str) -> str:
    return "resume" if source == "resume" else "other documents or notes"


def _requirement_facts(m: RequirementMatch) -> list[str]:
    lines = [
        f"Requirement: {m.name} ({IMPORTANCE_TEXT[m.importance]}, {m.category.replace('_', ' ')})",
        f"Status: {BUCKET_TEXT[m.bucket]}",
        f"Strength on the resume: {strength_text(m.resume_strength)}",
        f"Strength counting all documents: {strength_text(m.best_strength)}",
        f"Weight in the score: {m.weight:g}",
    ]
    if m.min_years is not None:
        lines.append(f"Years asked for: {m.min_years:g}")
        lines.append(f"Matching years on the resume: {m.resume_years or 0:g}")
    if m.evidence:
        lines.append("Evidence found:")
        for e in m.evidence[:6]:
            relation = "" if e.direct else " (related, not exact)"
            lines.append(
                f"- {e.label} [{e.context.replace('_', ' ')}, {_where(e.source)}]{relation}: "
                f'"{_clip(e.snippet)}"'
            )
    else:
        lines.append("Evidence found: none.")
    return lines


def _ats_facts(a: AnalysisResponse) -> list[str]:
    if a.ats is None:
        return ["ATS check: not available for this analysis."]
    lines = [f"ATS score: {a.ats.score}% (points earned per check):"]
    for c in a.ats.checks:
        lines.append(
            f"- {c.title}: {c.status}, {c.points:g} of {c.max_points:g} points. {c.detail}"
        )
    return lines


def _score_facts(a: AnalysisResponse) -> list[str]:
    lines = [SCORING_RULES, ""]
    if a.final_score is not None:
        lines += [
            f"Final score: {a.final_score}% = 70% x job fit {a.fit_score}% + 30% x ATS "
            f"{a.ats_score}%. With what they already have added: {a.potential_final_score}%.",
            *_ats_facts(a),
            "",
        ]
    lines.append("Requirements (name | importance | weight | resume | all docs):")
    for m in a.matches or []:
        lines.append(
            f"- {m.name} | {IMPORTANCE_TEXT[m.importance]} | {m.weight:g} | "
            f"{strength_text(m.resume_strength)} | {strength_text(m.best_strength)}"
        )
    return lines


def _interview_question(interview: InterviewSet | None, ref: str) -> tuple[str, InterviewQuestion]:
    if interview is None:
        raise ExplainNotFound("No interview questions yet.")
    parts = ref.split(":")
    try:
        if parts[0] == "project" and len(parts) == 3:
            project = interview.projects[int(parts[1])]
            return f"Project: {project.project}", project.questions[int(parts[2])]
        if parts[0] in ("personal", "technical", "general") and len(parts) == 2:
            return "", getattr(interview, parts[0])[int(parts[1])]
    except (ValueError, IndexError):
        pass
    raise ExplainNotFound("Question not found.")


def build_request(
    analysis: AnalysisResponse,
    kind: ExplainKind,
    ref: str,
    interview: InterviewSet | None = None,
) -> tuple[str, list[str]]:
    """Returns (question, facts) for the clicked item, or raises ExplainNotFound."""
    if kind == "score":
        question = (
            f"Why is my job fit {analysis.fit_score}%, and why could it be "
            f"{analysis.potential_score}% with what I already have?"
        )
        return question, _score_facts(analysis)

    if kind == "ats":
        question = f"What does my ATS score of {analysis.ats_score}% mean, and how do I improve it?"
        return question, [SCORING_RULES, "", *_ats_facts(analysis)]

    if kind == "ats_check":
        check = (
            next((c for c in analysis.ats.checks if c.id == ref), None) if analysis.ats else None
        )
        if check is None:
            raise ExplainNotFound("ATS check not found.")
        facts = [
            f"ATS check: {check.title}",
            f"Result: {check.status}, {check.points:g} of {check.max_points:g} points",
            f"What we found: {check.detail}",
        ]
        if check.items:
            facts.append("Items: " + ", ".join(check.items))
        if check.fix:
            facts.append(f"Suggested fix: {check.fix}")
        if check.id == "keywords" and analysis.ats:
            for k in analysis.ats.keywords:
                if not k.found:
                    where = BUCKET_TEXT[k.bucket] if k.bucket else "unknown"
                    facts.append(
                        f"Missing keyword {k.name} ({IMPORTANCE_TEXT[k.importance]}): {where}"
                    )
        return f'What does the ATS check "{check.title}" mean for my resume?', facts

    if kind == "requirement":
        match = next((m for m in analysis.matches or [] if str(m.requirement_index) == ref), None)
        if match is None:
            raise ExplainNotFound("Requirement not found.")
        facts = _requirement_facts(match)
        for sug in analysis.suggestions or []:
            if match.requirement_index in sug.requirement_indexes:
                facts.append(
                    f'Suggested resume change: "{sug.suggested_text}" (+{sug.uplift} points)'
                )
        for st in analysis.learning_path.steps if analysis.learning_path else []:
            if match.name in st.for_requirements:
                facts.append(f"In the learning path as step {st.step}: {st.name}")
        return f'What does "{match.name}" mean for me and this job?', facts

    if kind == "suggestion":
        s = next((x for x in analysis.suggestions or [] if x.id == ref), None)
        if s is None:
            raise ExplainNotFound("Suggestion not found.")
        facts = [
            f"Addresses: {', '.join(s.requirement_names)}",
            f"Where to add it: {s.section}" + (f" → {s.target}" if s.target else ""),
            f'Suggested text: "{s.suggested_text}"',
            f"Reason given: {s.rationale}",
            f'Based on the student\'s own words in {s.quote_source_label}: "{_clip(s.quote)}"',
            f"Score gain if applied: +{s.uplift} points",
        ]
        return "Why should I make this change to my resume, and how?", facts

    if kind == "learning_step":
        steps = analysis.learning_path.steps if analysis.learning_path else []
        step = next((x for x in steps if str(x.step) == ref), None)
        if step is None:
            raise ExplainNotFound("Learning step not found.")
        facts = [
            f"Step {step.step} of {len(steps)}: {step.name}",
            "Type: "
            + ("foundation for a later step" if step.kind == "prerequisite" else "job requirement"),
            f"Helps with: {', '.join(step.for_requirements) or 'the job'}",
            f"Later steps that build on it: {', '.join(step.unlocks) or 'none'}",
            f"Why at this point: {step.why}",
            "Resources: " + (", ".join(r.title for r in step.resources) or "none curated yet"),
        ]
        return f"What is {step.name}, and why should I learn it now?", facts

    context, q = _interview_question(interview, ref)
    facts = [f"Question: {q.text}", f"Group: {q.category}"]
    if context:
        facts.append(context)
    if q.topic:
        facts.append(f"Job topic: {q.topic}")
    if q.dimension:
        facts.append(f"Angle: {q.dimension}")
    return "What is the interviewer looking for with this question, and how do I prepare?", facts


def render_input(analysis: AnalysisResponse, question: str, facts: list[str]) -> str:
    job = analysis.job_requirements
    role = job.role_title if job and job.role_title else "the job"
    company = f" at {job.company}" if job and job.company else ""
    return "\n".join(
        [
            "<job>",
            f"Role: {role}{company}",
            *(
                [f"Final score: {analysis.final_score}%", f"ATS score: {analysis.ats_score}%"]
                if analysis.final_score is not None
                else []
            ),
            f"Job fit (resume): {analysis.fit_score}%",
            f"With what they already have: {analysis.potential_score}%",
            "</job>",
            "<question>",
            question,
            "</question>",
            "<facts>",
            *facts,
            "</facts>",
        ]
    )


class Explainer:
    name = "explainer"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.prompt = load_prompt(self.name)

    async def run(
        self,
        analysis: AnalysisResponse,
        kind: ExplainKind,
        ref: str,
        *,
        interview: InterviewSet | None = None,
        user_id: str | None = None,
    ) -> Explanation:
        question, facts = build_request(analysis, kind, ref, interview)
        return await self._llm.parse(
            agent=self.name,
            prompt=self.prompt,
            input_text=render_input(analysis, question, facts),
            output_type=Explanation,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            analysis_id=analysis.id,
            user_id=user_id,
        )
