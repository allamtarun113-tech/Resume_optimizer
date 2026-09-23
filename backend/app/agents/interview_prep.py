"""Agent 10: InterviewPrep (on demand). Questions come from real sources via MCP tools:
the ingested GitHub corpus (technical, behavioral, background) and the curated project
deep-dive templates. The LLM only selects, dedupes and fills templates; Python validates
every choice, pads short groups deterministically, and attaches each question's source.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from pydantic import BaseModel

from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.mcp_server.server import McpTools
from app.rag.templates import (
    background_questions,
    fill_template,
    is_faithful_fill,
    project_facets,
)
from app.schemas.interview import (
    INTERVIEW_SET_VERSION,
    BankQuestion,
    InterviewQuestion,
    InterviewSelection,
    InterviewSet,
    ProjectQuestions,
    ProjectTemplate,
    QuestionSource,
)
from app.schemas.matching import RequirementMatch
from app.schemas.profile import Project, StudentProfile
from app.schemas.requirements import JobRequirements
from app.skills.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 12_000
MAX_TOPICS = 12  # requirements used to retrieve technical questions
PER_TOPIC = 8
MIN_SIMILARITY_UNFILTERED = 0.35
MAX_PROJECTS = 5
GENERAL_SAMPLE = 30
TEMPLATE_LABEL = "Resume Optimizer project deep-dive bank"
BACKGROUND_LABEL = "Resume Optimizer background question bank"
# (min, max) per group; the LLM picks within, Python pads up to the min.
TECHNICAL = (20, 30)
GENERAL = (10, 15)
PERSONAL = (6, 10)  # from the question bank; background drill-downs come on top
PROJECT = (12, 15)
LEARNABLE = ("skill", "domain", "experience")


class InterviewPrepInput(BaseModel):
    analysis_id: str
    profile: StudentProfile
    requirements: JobRequirements
    matches: list[RequirementMatch]


def _bank_source(q: BankQuestion) -> QuestionSource:
    return QuestionSource(kind="github", label=q.source_repo, url=q.source_url, license=q.license)


def _template_source(t: ProjectTemplate) -> QuestionSource:
    return QuestionSource(
        kind="template", label=TEMPLATE_LABEL, url=None, license=None, template_id=t.id
    )


def ranked_requirements(inp: InterviewPrepInput) -> list[RequirementMatch]:
    """Most important first: must-haves, then heavier weights, then JD order."""
    relevant = [m for m in inp.matches if m.category in LEARNABLE]
    return sorted(
        relevant,
        key=lambda m: (m.importance != "must", -m.weight, m.requirement_index),
    )[:MAX_TOPICS]


def interview_projects(profile: StudentProfile) -> list[Project]:
    resume = [p for p in profile.projects if p.source == "resume"]
    others = [p for p in profile.projects if p.source != "resume"]
    return (resume + others)[:MAX_PROJECTS]


class InterviewPrep:
    name = "interview_prep"
    uses_llm = True

    def __init__(
        self,
        llm: LLMClient,
        taxonomy: Taxonomy,
        tools: Callable[[], AbstractAsyncContextManager[McpTools]],
    ) -> None:
        self._llm = llm
        self._taxonomy = taxonomy
        self._tools = tools
        self.prompt = load_prompt(self.name)

    def _topics(self, match: RequirementMatch) -> list[str]:
        if match.skill_id:
            return [match.skill_id]
        return sorted(self._taxonomy.find_in_text(match.name))

    async def _technical(
        self, tools: McpTools, inp: InterviewPrepInput
    ) -> list[tuple[str, BankQuestion]]:
        """(requirement name, question) candidates, deduplicated, in requirement order."""
        seen: set[str] = set()
        out: list[tuple[str, BankQuestion]] = []
        for match in ranked_requirements(inp):
            topics = self._topics(match)
            hits = (
                await tools.search_questions(
                    match.name, category="technical", topics=topics, k=PER_TOPIC
                )
                if topics
                else []
            )
            if len(hits) < 3:
                broad = await tools.search_questions(match.name, category="technical", k=PER_TOPIC)
                hits += [h for h in broad if (h.similarity or 0) >= MIN_SIMILARITY_UNFILTERED]
            for hit in hits:
                if hit.id not in seen:
                    seen.add(hit.id)
                    out.append((match.name, hit))
        return out

    async def run(self, inp: InterviewPrepInput, *, user_id: str | None = None) -> InterviewSet:
        projects = interview_projects(inp.profile)
        async with self._tools() as tools:
            technical = await self._technical(tools, inp)
            general = await tools.general_questions(GENERAL_SAMPLE, inp.analysis_id)
            templates_by_project = [
                await tools.project_templates(project_facets(p, self._taxonomy)) for p in projects
            ]
            background = background_questions(inp.profile, await tools.background_templates())

        tech_ids = {f"Q{i + 1}": pair for i, pair in enumerate(technical)}
        general_ids = {f"G{i + 1}": q for i, q in enumerate(general)}
        all_templates = {t.id: t for ts in templates_by_project for t in ts}

        selection = await self._select(inp, tech_ids, general_ids, projects, templates_by_project)
        return InterviewSet(
            personal=self._pick_bank(
                selection.personal_ids if selection else [], general_ids, "personal", PERSONAL
            )
            + [
                InterviewQuestion(
                    text=text,
                    category="personal",
                    dimension=template.kind,
                    source=QuestionSource(
                        kind="template",
                        label=BACKGROUND_LABEL,
                        url=None,
                        license=None,
                        template_id=template.id,
                    ),
                )
                for template, text in background
            ],
            projects=[
                self._project_questions(i, p, templates_by_project[i], all_templates, selection)
                for i, p in enumerate(projects)
            ],
            technical=self._pick_technical(selection, tech_ids),
            general=self._pick_bank(
                selection.general_ids if selection else [], general_ids, "general", GENERAL
            ),
            version=INTERVIEW_SET_VERSION,
        )

    # -- LLM selection -------------------------------------------------------------------

    async def _select(
        self,
        inp: InterviewPrepInput,
        tech_ids: dict[str, tuple[str, BankQuestion]],
        general_ids: dict[str, BankQuestion],
        projects: list[Project],
        templates_by_project: list[list[ProjectTemplate]],
    ) -> InterviewSelection | None:
        if not tech_ids and not general_ids and not projects:
            return None
        top = ", ".join(f"{m.name} ({m.importance})" for m in ranked_requirements(inp))
        lines = [
            "<job>",
            f"Role: {inp.requirements.role_title or 'not stated'}",
            f"Top requirements: {top or 'not stated'}",
            "</job>",
            "",
            "<technical_candidates>",
            *(f"{qid} [{req}] {q.text}" for qid, (req, q) in tech_ids.items()),
            "</technical_candidates>",
            "",
            "<general_candidates>",
            *(f"{gid} [{q.category}] {q.text}" for gid, q in general_ids.items()),
            "</general_candidates>",
            "",
            "<projects>",
        ]
        for i, p in enumerate(projects):
            lines.append(
                f"P{i + 1} {p.name} — {p.summary} Tech: {', '.join(p.technologies) or 'n/a'}. "
                f"Highlights: {'; '.join(p.highlights) or 'n/a'}. "
                f"Metrics: {'; '.join(p.metrics) or 'none'}. "
                f"Challenges: {'; '.join(p.challenges) or 'n/a'}."
            )
        lines += ["</projects>", "", "<templates>"]
        seen: set[str] = set()
        for ts in templates_by_project:
            for t in ts:
                if t.id not in seen:
                    seen.add(t.id)
                    lines.append(f"{t.id} [{t.dimension}] {t.text}")
        for i, ts in enumerate(templates_by_project):
            lines.append(f"Templates for P{i + 1}: {', '.join(t.id for t in ts)}")
        lines.append("</templates>")
        try:
            return await self._llm.parse(
                agent=self.name,
                prompt=self.prompt,
                input_text="\n".join(lines),
                output_type=InterviewSelection,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                tier="large",
                analysis_id=inp.analysis_id,
                user_id=None,
            )
        except Exception:
            logger.exception("Interview selection failed; using deterministic selection")
            return None

    # -- validation and padding -------------------------------------------------------------

    def _pick_technical(
        self,
        selection: InterviewSelection | None,
        tech_ids: dict[str, tuple[str, BankQuestion]],
    ) -> list[InterviewQuestion]:
        chosen = [i.strip().upper() for i in (selection.technical_ids if selection else [])]
        picked = list(dict.fromkeys(i for i in chosen if i in tech_ids))[: TECHNICAL[1]]
        if len(picked) < TECHNICAL[0]:
            # Round-robin over requirements so padding stays spread across the job.
            by_req: dict[str, list[str]] = {}
            for qid, (req, _) in tech_ids.items():
                by_req.setdefault(req, []).append(qid)
            while len(picked) < TECHNICAL[0] and any(by_req.values()):
                for ids in by_req.values():
                    while ids and ids[0] in picked:
                        ids.pop(0)
                    if ids and len(picked) < TECHNICAL[0]:
                        picked.append(ids.pop(0))
        return [
            InterviewQuestion(
                text=tech_ids[qid][1].text,
                category="technical",
                topic=tech_ids[qid][0],
                source=_bank_source(tech_ids[qid][1]),
            )
            for qid in picked
        ]

    def _pick_bank(
        self,
        chosen: list[str],
        general_ids: dict[str, BankQuestion],
        category: str,
        limits: tuple[int, int],
    ) -> list[InterviewQuestion]:
        valid = [
            gid
            for gid in dict.fromkeys(c.strip().upper() for c in chosen)
            if gid in general_ids and general_ids[gid].category == category
        ][: limits[1]]
        for gid, q in general_ids.items():
            if len(valid) >= limits[0]:
                break
            if q.category == category and gid not in valid:
                valid.append(gid)
        return [
            InterviewQuestion(
                text=general_ids[gid].text,
                category="personal" if category == "personal" else "general",
                source=_bank_source(general_ids[gid]),
            )
            for gid in valid
        ]

    def _project_questions(
        self,
        index: int,
        project: Project,
        allowed: list[ProjectTemplate],
        all_templates: dict[str, ProjectTemplate],
        selection: InterviewSelection | None,
    ) -> ProjectQuestions:
        allowed_ids = {t.id for t in allowed}
        pid = f"P{index + 1}"
        questions: list[InterviewQuestion] = []
        used: set[str] = set()
        for filled in selection.project_questions if selection else []:
            tid = filled.template_id.strip().upper()
            if filled.project_id.strip().upper() != pid or tid not in allowed_ids or tid in used:
                continue
            template = all_templates[tid]
            if not is_faithful_fill(filled.question, template, project):
                logger.info("Rejected filled template %s for %s", tid, project.name)
                continue
            used.add(tid)
            questions.append(self._project_question(filled.question.strip(), template))
            if len(questions) >= PROJECT[1]:
                break

        # Pad with deterministic fills, rotating through dimensions for variety
        # (dimensions not yet covered first).
        covered = {q.dimension for q in questions}
        queues: dict[str, list[ProjectTemplate]] = {}
        for t in allowed:
            if t.id not in used:
                queues.setdefault(t.dimension, []).append(t)
        order = sorted(queues, key=lambda d: d in covered)  # stable: keeps bank order
        while len(questions) < PROJECT[0] and any(queues.values()):
            for dimension in order:
                queue = queues[dimension]
                while queue and len(questions) < PROJECT[0]:
                    template = queue.pop(0)
                    text = fill_template(template, project)
                    if text:
                        used.add(template.id)
                        questions.append(self._project_question(text, template))
                        break
        return ProjectQuestions(
            project=project.name, technologies=project.technologies, questions=questions
        )

    @staticmethod
    def _project_question(text: str, template: ProjectTemplate) -> InterviewQuestion:
        return InterviewQuestion(
            text=text,
            category="project",
            dimension=template.dimension,
            source=_template_source(template),
        )
