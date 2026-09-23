"""Agent 4: SkillNormalizer (no LLM). Maps skill names to canonical taxonomy ids."""

import re

from pydantic import BaseModel

from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements
from app.skills.taxonomy import Taxonomy

_ALTERNATIVES_RE = re.compile(r"\bor\b", re.IGNORECASE)
_ALTERNATIVE_SPLIT_RE = re.compile(r"\s*(?:,|/|\bor\b)\s*", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*(?:[/,;|()]|\band\b|&)\s*")
# Requirement phrasing the JD analyzer sometimes keeps ("Experience with Docker").
_PREFIX_RE = re.compile(
    r"^(?:(?:strong|solid|good|basic|advanced|deep|working|hands-on|proven|excellent)\s+)*"
    r"(?:(?:experience|knowledge|understanding|proficiency|familiarity|expertise|skills?)"
    r"\s+(?:with|of|in)\s+)?",
    re.IGNORECASE,
)


class NormalizedSkills(BaseModel):
    mention_ids: list[list[str]]  # per StudentProfile.skills entry
    project_ids: list[list[str]]  # per project, from its technologies
    experience_ids: list[list[str]]  # per job, from its technologies
    requirement_ids: list[str | None]  # per requirement; None if not (uniquely) known
    # Per requirement: known ids of its alternatives ("Java, C++ or R"), else empty.
    requirement_alternatives: list[list[str]]


class SkillNormalizer:
    name = "skill_normalizer"
    uses_llm = False

    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def _single(self, name: str) -> str | None:
        return self._taxonomy.lookup(name) or self._taxonomy.fuzzy_lookup(name)

    def resolve(self, name: str) -> list[str]:
        """All canonical ids in a name like "Python (pandas, NumPy)" or "HTML/CSS".

        A combined skill also counts as each named part: "Data structures and algorithms"
        is dsa, data-structures and algorithms."""
        whole = self._taxonomy.lookup(name)
        parts = [p for p in _SPLIT_RE.split(name) if p.strip()]
        if whole:
            named = (self._taxonomy.lookup(p) for p in parts) if len(parts) > 1 else ()
            return list(dict.fromkeys([whole, *(i for i in named if i)]))
        if len(parts) > 1:
            found = (self._single(p) for p in parts)
            return list(dict.fromkeys(i for i in found if i))
        fuzzy = self._taxonomy.fuzzy_lookup(name)
        return [fuzzy] if fuzzy else []

    def resolve_requirement(self, name: str) -> str | None:
        # "Python or Java" is satisfied by either one; the LLM matcher judges those.
        if _ALTERNATIVES_RE.search(name):
            return None
        for candidate in (name, _PREFIX_RE.sub("", name)):
            ids = self.resolve(candidate) if candidate.strip() else []
            if len(ids) == 1:
                return ids[0]
        return None

    def resolve_alternatives(self, name: str) -> list[str]:
        """Ids for "X, Y or Z" when at least two alternatives are known skills."""
        if not _ALTERNATIVES_RE.search(name):
            return []
        parts = [_PREFIX_RE.sub("", p) for p in _ALTERNATIVE_SPLIT_RE.split(name) if p.strip()]
        ids = list(dict.fromkeys(i for p in parts if (i := self._single(p))))
        return ids if len(ids) >= 2 else []

    def _resolve_all(self, names: list[str]) -> list[str]:
        return list(dict.fromkeys(i for n in names for i in self.resolve(n)))

    def run(self, profile: StudentProfile, requirements: JobRequirements) -> NormalizedSkills:
        return NormalizedSkills(
            mention_ids=[self.resolve(m.name) for m in profile.skills],
            project_ids=[self._resolve_all(p.technologies) for p in profile.projects],
            experience_ids=[self._resolve_all(x.technologies) for x in profile.experience],
            requirement_ids=[self.resolve_requirement(r.name) for r in requirements.requirements],
            requirement_alternatives=[
                self.resolve_alternatives(r.name) for r in requirements.requirements
            ],
        )
