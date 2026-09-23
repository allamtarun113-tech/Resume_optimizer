"""Agent 3: JDAnalyzer (LLM, small). Job description text -> JobRequirements.

The LLM is told to split lists of skills that are all wanted, but doesn't always do it.
Python splits them afterwards ("Git, Docker and Kubernetes" -> three requirements), so a
student can't get credit for a whole list from evidence of one item. Alternatives ("Java
or C++") stay together.
"""

import re

from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.schemas.requirements import JobRequirements, Requirement
from app.skills.taxonomy import Taxonomy, load_taxonomy

MAX_OUTPUT_TOKENS = 6_000
SPLITTABLE = ("skill", "domain", "soft_skill")
MAX_PART_WORDS = 5
_ALTERNATIVE_RE = re.compile(r"\bor\b|\beither\b", re.IGNORECASE)
_LIST_SPLIT_RE = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*|\s*;\s*", re.IGNORECASE)
_LEADING_RE = re.compile(
    r"^(?:(?:strong|solid|good|basic|deep|working|hands-on|proven|excellent)\s+)*"
    r"(?:(?:experience|knowledge|understanding|proficiency|familiarity|foundation)"
    r"\s+(?:with|of|in)\s+)?",
    re.IGNORECASE,
)


def _known(taxonomy: Taxonomy, name: str) -> bool:
    return bool(taxonomy.lookup(name) or taxonomy.fuzzy_lookup(name))


def split_requirement(req: Requirement, taxonomy: Taxonomy) -> list[Requirement]:
    """Split a list of skills that are all wanted into one requirement each.

    Only when it's clearly a list: not alternatives ("or"), not a single known skill
    ("Data structures and algorithms"), short parts, and at least two parts are skills the
    taxonomy knows (so "Research and development" stays whole)."""
    name = req.name.strip()
    if req.category not in SPLITTABLE or _ALTERNATIVE_RE.search(name) or _known(taxonomy, name):
        return [req]
    parts = [p.strip(" .") for p in _LIST_SPLIT_RE.split(_LEADING_RE.sub("", name))]
    parts = [p for p in parts if p]
    if len(parts) < 2 or any(len(p.split()) > MAX_PART_WORDS for p in parts):
        return [req]
    if sum(_known(taxonomy, p) for p in parts) < 2:
        return [req]
    return [req.model_copy(update={"name": p}) for p in parts]


def split_requirements(requirements: list[Requirement], taxonomy: Taxonomy) -> list[Requirement]:
    return [part for req in requirements for part in split_requirement(req, taxonomy)]


def dedupe_requirements(requirements: list[Requirement]) -> list[Requirement]:
    """Merge repeats of the same requirement, keeping the stricter one, in first-seen order."""
    merged: dict[tuple[str, str], Requirement] = {}
    for req in requirements:
        key = (" ".join(req.name.casefold().split()), req.category)
        current = merged.get(key)
        if current is None:
            merged[key] = req
        elif req.importance == "must" and current.importance == "nice":
            merged[key] = current.model_copy(update={"importance": "must"})
        if current and req.min_years is not None:
            best = merged[key]
            if best.min_years is None or req.min_years > best.min_years:
                merged[key] = best.model_copy(update={"min_years": req.min_years})
    return list(merged.values())


class JDAnalyzer:
    name = "jd_analyzer"
    uses_llm = True

    def __init__(self, llm: LLMClient, taxonomy: Taxonomy | None = None) -> None:
        self._llm = llm
        self._taxonomy = taxonomy or load_taxonomy()
        self.prompt = load_prompt(self.name)

    async def run(
        self,
        jd_text: str,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> JobRequirements:
        result = await self._llm.parse(
            agent=self.name,
            prompt=self.prompt,
            input_text=f"<job_description>\n{jd_text}\n</job_description>",
            output_type=JobRequirements,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            analysis_id=analysis_id,
            user_id=user_id,
        )
        requirements = split_requirements(result.requirements, self._taxonomy)
        return result.model_copy(update={"requirements": dedupe_requirements(requirements)})
