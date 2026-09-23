"""Markdown export of an analysis (and its interview set, if generated). Pure function."""

import re

from app.schemas.analyses import AnalysisResponse
from app.schemas.interview import InterviewQuestion, InterviewSet

_BUCKET_TITLES = {
    "strong_in_resume": "Strong matches",
    "weak_in_resume": "Weak on your resume",
    "missing_from_resume_but_evidenced": "You have it, but it's not on your resume",
    "true_gap": "Skill gaps",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "analysis"


def report_filename(analysis: AnalysisResponse) -> str:
    title = analysis.job_requirements.role_title if analysis.job_requirements else None
    return f"resume-optimizer-{_slug(title or 'analysis')}-{analysis.created_at:%Y-%m-%d}.md"


def _questions(lines: list[str], questions: list[InterviewQuestion]) -> None:
    for i, q in enumerate(questions, start=1):
        src = q.source.url or q.source.label
        lines.append(f"{i}. {q.text}  \n   _Source: {src}_")
    lines.append("")


def build_markdown_report(analysis: AnalysisResponse, interview: InterviewSet | None) -> str:
    reqs = analysis.job_requirements
    title = (reqs.role_title if reqs else None) or "Job analysis"
    company = f" at {reqs.company}" if reqs and reqs.company else ""
    lines = [
        f"# {title}{company}",
        "",
        f"_Resume Optimizer report, {analysis.created_at:%d %b %Y}. "
        f"Scoring version {analysis.scoring_version or 'n/a'}._",
        "",
        "## Job fit",
        "",
        *(
            [
                f"- **Final score:** {analysis.final_score}% (70% job fit + 30% ATS)",
                f"- **ATS score:** {analysis.ats_score}%",
            ]
            if analysis.final_score is not None
            else []
        ),
        f"- **Job Fit Score:** {analysis.fit_score}%",
        f"- **With what you already have:** {analysis.potential_score}%",
        "",
    ]
    if analysis.ats:
        lines += [f"## ATS check ({analysis.ats.score}%)", ""]
        mark = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
        for c in analysis.ats.checks:
            lines.append(f"- {mark[c.status]} **{c.title}:** {c.detail}")
            if c.fix:
                lines.append(f"  - Fix: {c.fix}")
        lines.append("")

    suggestions = analysis.suggestions or []
    if suggestions:
        lines += ["## Add to your resume", ""]
        for s in suggestions:
            target = f" → {s.target}" if s.target else ""
            lines += [
                f"### {', '.join(s.requirement_names)} (+{s.uplift} points)",
                "",
                f"**Where:** {s.section.capitalize()}{target}",
                "",
                f"> {s.suggested_text}",
                "",
                f'{s.rationale} _Based on {s.quote_source_label}: "{s.quote}"_',
                "",
            ]

    if analysis.matches:
        lines += ["## Requirement by requirement", ""]
        for bucket, heading in _BUCKET_TITLES.items():
            items = [m for m in analysis.matches if m.bucket == bucket]
            if not items:
                continue
            lines += [f"### {heading}", ""]
            for m in items:
                lines.append(
                    f"- {m.name} ({'must have' if m.importance == 'must' else 'nice to have'})"
                )
            lines.append("")

    path = analysis.learning_path
    if path and path.steps:
        lines += [f"## Learning path (about {round(path.total_hours)} hours)", ""]
        for step in path.steps:
            lines.append(f"{step.step}. **{step.name}**: {step.why}")
            for r in step.resources:
                lines.append(f"   - [{r.title}]({r.url}) ({r.type}, {r.level})")
        lines.append("")

    if interview:
        lines += ["## Interview preparation", ""]
        if interview.personal:
            lines += ["### About you", ""]
            _questions(lines, interview.personal)
        for project in interview.projects:
            lines += [f"### Project: {project.project}", ""]
            _questions(lines, project.questions)
        if interview.technical:
            lines += ["### Technical", ""]
            _questions(lines, interview.technical)
        if interview.general:
            lines += ["### Behavioral", ""]
            _questions(lines, interview.general)

    return "\n".join(lines).rstrip() + "\n"
