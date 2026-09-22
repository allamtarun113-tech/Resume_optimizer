"""Canonical skill taxonomy: ids, aliases, prerequisites and "implies" edges.

Data lives in app/skills/data/skills_taxonomy.json. `implies` means evidence of the
skill is also (weaker) evidence of the implied skill, e.g. PostgreSQL implies SQL.
`prerequisites` orders learning paths (Phase 4).
"""

import json
import re
import unicodedata
from functools import cache
from pathlib import Path

from pydantic import BaseModel
from rapidfuzz import fuzz, process

TAXONOMY_PATH = Path(__file__).resolve().parent / "data" / "skills_taxonomy.json"

# Fuzzy matching only for keys this long; short names ("r", "go", "c#") must match exactly.
FUZZY_MIN_LENGTH = 5
FUZZY_CUTOFF = 92

_VERSION_SUFFIX_RE = re.compile(r"\s+v?\d+(\.\d+)*\+?$")
_SEPARATORS_RE = re.compile(r"[\s\-_]+")


def skill_key(name: str) -> str:
    """Comparison key: case/spacing/version-insensitive, keeps meaningful symbols (c++, .net)."""
    key = unicodedata.normalize("NFKC", name).casefold().strip()
    key = key.replace("&", " and ")
    key = _VERSION_SUFFIX_RE.sub("", key)
    key = _SEPARATORS_RE.sub("", key)
    key = key.rstrip(".,;:!?'\")]}").lstrip("'\"([{")
    if key.endswith(".js"):
        key = key[:-3] + "js"
    return key


class SkillEntry(BaseModel):
    id: str
    name: str
    category: str
    aliases: list[str]
    prerequisites: list[str]
    implies: list[str]


class TaxonomyFile(BaseModel):
    version: str
    skills: list[SkillEntry]


class TaxonomyError(ValueError):
    pass


class Taxonomy:
    def __init__(self, data: TaxonomyFile) -> None:
        self.version = data.version
        self.skills = {s.id: s for s in data.skills}
        if len(self.skills) != len(data.skills):
            raise TaxonomyError("Duplicate skill ids")

        self._keys: dict[str, str] = {}
        for skill in data.skills:
            for name in (skill.id, skill.name, *skill.aliases):
                key = skill_key(name)
                owner = self._keys.setdefault(key, skill.id)
                if owner != skill.id:
                    raise TaxonomyError(f"{name!r} maps to both {owner} and {skill.id}")
            for ref in (*skill.prerequisites, *skill.implies):
                if ref not in self.skills:
                    raise TaxonomyError(f"{skill.id} references unknown skill {ref!r}")

        self._fuzzy_keys = sorted(k for k in self._keys if len(k) >= FUZZY_MIN_LENGTH)
        self._implied = {sid: self._closure(sid, "implies") for sid in self.skills}
        for sid in self.skills:
            if sid in self._closure(sid, "prerequisites"):
                raise TaxonomyError(f"Prerequisite cycle through {sid}")

    def _closure(self, skill_id: str, edge: str) -> frozenset[str]:
        seen: set[str] = set()
        stack = list(getattr(self.skills[skill_id], edge))
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(getattr(self.skills[current], edge))
        return frozenset(seen)

    def lookup(self, name: str) -> str | None:
        """Exact match on id, name or alias (after skill_key normalization)."""
        return self._keys.get(skill_key(name))

    def fuzzy_lookup(self, name: str) -> str | None:
        key = skill_key(name)
        if len(key) < FUZZY_MIN_LENGTH:
            return None
        best = process.extractOne(
            key, self._fuzzy_keys, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF
        )
        return self._keys[best[0]] if best else None

    def implied_by(self, skill_id: str) -> frozenset[str]:
        """Skills that evidence of `skill_id` implies (transitively), excluding itself."""
        return self._implied.get(skill_id, frozenset())

    def name(self, skill_id: str) -> str:
        return self.skills[skill_id].name

    def prerequisites(self, skill_id: str) -> list[str]:
        return list(self.skills[skill_id].prerequisites)


@cache
def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    return Taxonomy(TaxonomyFile.model_validate(json.loads(path.read_text(encoding="utf-8"))))
