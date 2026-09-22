"""Agent 9: LearningPathPlanner (LLM, small). Orders true skill gaps into a study plan.

Taxonomy first: the prerequisite graph (via the MCP tool get_skill_prerequisites) fixes
what must come before what, and Python computes a deterministic topological order. The
LLM only reorders independent steps and writes "why this next" notes; an order that breaks
a prerequisite is discarded. Resources come only from the database via the MCP tool
get_learning_resources — the LLM never writes URLs.
"""

import heapq
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.agents.skill_normalizer import NormalizedSkills
from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.mcp_server.server import McpTools
from app.schemas.learning import LearningPath, LearningResource, LearningStep, PathPlan
from app.schemas.matching import ScoreResult
from app.skills.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 3_000
MAX_PREREQUISITE_DEPTH = 2  # levels of prerequisites pulled in below each gap
LEARNABLE_CATEGORIES = ("skill", "domain")


class PlannerInput(BaseModel):
    score: ScoreResult
    normalized: NormalizedSkills


@dataclass
class _Step:
    id: str
    name: str
    skill_id: str | None
    kind: str  # "gap" | "prerequisite"
    priority: float  # heaviest requirement weight this step serves
    requirements: list[str] = field(default_factory=list)
    needs: set[str] = field(default_factory=set)  # direct prerequisites (for display)
    unlocks: set[str] = field(default_factory=set)  # direct dependents (for display)
    after: set[str] = field(default_factory=set)  # every included prerequisite (ordering)


def respects_prerequisites(order: list[str], steps: dict[str, "_Step"]) -> bool:
    if sorted(order) != sorted(steps):
        return False
    position = {sid: i for i, sid in enumerate(order)}
    return all(position[p] < position[s.id] for s in steps.values() for p in s.after)


def topological_order(steps: dict[str, _Step]) -> list[str]:
    """Prerequisites first; among available steps, heavier requirements, then name."""
    dependents: dict[str, set[str]] = {sid: set() for sid in steps}
    for s in steps.values():
        for p in s.after:
            dependents[p].add(s.id)
    remaining = {sid: len(s.after) for sid, s in steps.items()}
    ready = [(-s.priority, s.name.casefold(), sid) for sid, s in steps.items() if not s.after]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, _, sid = heapq.heappop(ready)
        order.append(sid)
        for nxt in sorted(dependents[sid]):
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                s = steps[nxt]
                heapq.heappush(ready, (-s.priority, s.name.casefold(), nxt))
    return order


class LearningPathPlanner:
    name = "learning_path_planner"
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

    def known_skills(self, normalized: NormalizedSkills) -> set[str]:
        """Skills the student shows, plus what they imply and what they build on."""
        shown = {
            i
            for ids in (
                *normalized.mention_ids,
                *normalized.project_ids,
                *normalized.experience_ids,
            )
            for i in ids
        }
        known = set(shown)
        for sid in shown:
            known |= self._taxonomy.implied_by(sid)
        stack = list(known)
        while stack:
            for p in self._taxonomy.prerequisites(stack.pop()):
                if p not in known:
                    known.add(p)
                    stack.append(p)
        return known

    def _targets(self, inp: PlannerInput, known: set[str]) -> dict[str, _Step]:
        steps: dict[str, _Step] = {}
        for m in inp.score.matches:
            if m.bucket != "true_gap" or m.category not in LEARNABLE_CATEGORIES:
                continue
            alternatives = inp.normalized.requirement_alternatives[m.requirement_index]
            skill_id = m.skill_id or (alternatives[0] if alternatives else None)
            if skill_id and skill_id in known:
                continue
            sid = skill_id or f"req-{m.requirement_index}"
            name = self._taxonomy.name(skill_id) if skill_id else m.name
            step = steps.setdefault(sid, _Step(sid, name, skill_id, "gap", m.weight))
            step.priority = max(step.priority, m.weight)
            step.requirements.append(m.name)
        return steps

    async def _add_prerequisites(
        self, tools: McpTools, steps: dict[str, _Step], known: set[str]
    ) -> None:
        frontier = [s.id for s in steps.values() if s.skill_id]
        for _ in range(MAX_PREREQUISITE_DEPTH):
            next_frontier: list[str] = []
            for sid in sorted(frontier):
                result = await tools.prerequisites(sid)
                for pre in result.prerequisites:
                    if pre.skill_id in known:
                        continue
                    if pre.skill_id not in steps:
                        steps[pre.skill_id] = _Step(
                            pre.skill_id, pre.name, pre.skill_id, "prerequisite", 0.0
                        )
                        next_frontier.append(pre.skill_id)
                    steps[sid].needs.add(pre.skill_id)
                    steps[pre.skill_id].unlocks.add(sid)
            frontier = next_frontier
        # Order by the full prerequisite graph among included steps, including links that
        # run through steps beyond the depth limit or through skills the student knows.
        for step in steps.values():
            if step.skill_id:
                closure = self._taxonomy.prerequisite_closure(step.skill_id)
                step.after = {p for p in closure if p in steps} | step.needs
        # Prerequisites inherit the importance and requirements of what builds on them.
        for sid in reversed(topological_order(steps)):
            step = steps[sid]
            for nxt in (d.id for d in steps.values() if sid in d.after):
                step.priority = max(step.priority, steps[nxt].priority)
                step.requirements.extend(
                    r for r in steps[nxt].requirements if r not in step.requirements
                )

    async def run(
        self,
        inp: PlannerInput,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> LearningPath:
        known = self.known_skills(inp.normalized)
        steps = self._targets(inp, known)
        if not steps:
            return LearningPath(steps=[], total_hours=0)

        async with self._tools() as tools:
            await self._add_prerequisites(tools, steps, known)
            skill_ids = sorted(s.skill_id for s in steps.values() if s.skill_id)
            resources = await tools.learning_resources(skill_ids)

        order = topological_order(steps)
        notes: dict[str, str] = {}
        plan = await self._plan(steps, order, analysis_id, user_id)
        if plan is not None:
            notes = {n.step_id: n.why.strip() for n in plan.notes if n.why.strip()}
            if respects_prerequisites(plan.order, steps):
                order = plan.order
            else:
                logger.info("Ignoring LLM step order that breaks prerequisites")

        by_skill: dict[str, list[LearningResource]] = {}
        for r in resources:
            by_skill.setdefault(r.skill_id, []).append(r)
        result: list[LearningStep] = []
        for position, sid in enumerate(order, start=1):
            s = steps[sid]
            step_resources = by_skill.get(s.skill_id or "", [])
            result.append(
                LearningStep(
                    step=position,
                    skill_id=s.skill_id,
                    name=s.name,
                    kind="gap" if s.kind == "gap" else "prerequisite",
                    for_requirements=s.requirements,
                    unlocks=sorted(steps[u].name for u in s.unlocks),
                    why=notes.get(sid) or _default_note(s, steps),
                    resources=step_resources,
                    est_hours=step_resources[0].est_hours if step_resources else None,
                )
            )
        total = sum(s.est_hours or 0 for s in result)
        return LearningPath(steps=result, total_hours=round(total, 1))

    async def _plan(
        self,
        steps: dict[str, _Step],
        order: list[str],
        analysis_id: str | None,
        user_id: str | None,
    ) -> PathPlan | None:
        lines = []
        for sid in order:
            s = steps[sid]
            before = ", ".join(sorted(steps[n].id for n in s.needs)) or "nothing"
            lines.append(
                f"{sid} [{s.kind}] {s.name} — needs first: {before}; "
                f"for job requirements: {', '.join(s.requirements) or 'none'}"
            )
        try:
            return await self._llm.parse(
                agent=self.name,
                prompt=self.prompt,
                input_text="<steps>\n" + "\n".join(lines) + "\n</steps>",
                output_type=PathPlan,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                analysis_id=analysis_id,
                user_id=user_id,
            )
        except Exception:
            # Notes are nice-to-have; the ordered path with resources still stands.
            logger.exception("Learning path notes failed; using default notes")
            return None


def _default_note(step: _Step, steps: dict[str, _Step]) -> str:
    if step.kind == "prerequisite":
        unlocks = ", ".join(sorted(steps[u].name for u in step.unlocks))
        return f"Comes first because {unlocks} builds on it."
    return f"The job asks for {', '.join(step.requirements)}."
