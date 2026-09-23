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


# Categories whose names are specific enough to detect in free text.
TECHNICAL_CATEGORIES = frozenset(
    {
        "language",
        "frontend",
        "backend",
        "database",
        "cloud",
        "devops",
        "data",
        "ml",
        "mobile",
        "testing",
        "tool",
        "security",
    }
)
# Keys that are also everyday words or too short to detect reliably in prose.
_AMBIGUOUS_KEYS = frozenset(
    {
        "go",
        "r",
        "c",
        "rest",
        "express",
        "spring",
        "shell",
        "sh",
        "swift",
        "rust",
        "dart",
        "lambda",
        "node",
        "next",
        "cloud",
        "security",
        "api",
        "apis",
        "oracle",  # also the company and its many products (e.g. Oracle Hyperion)
        "iam",
        "excel",
        "gin",
        "tf",
        "ts",
        "js",
        "py",
        "ml",
        "dl",
        "rn",
        "cv",
        "os",
        "ds",
        "rl",
        "sql queries",
        "hosting",
    }
)
# Hyphens split tokens ("Terraform-managed"); keys ignore them, so "scikit-learn" and
# "front-end" still match as two-word spans.
_TOKEN_RE = re.compile(r"\.?[A-Za-z0-9][A-Za-z0-9+#./]*")
MAX_NGRAM = 4


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
        self._multiword_keys: set[str] = set()  # keys of names written as several words
        for skill in data.skills:
            for name in (skill.id, skill.name, *skill.aliases):
                key = skill_key(name)
                if len(_SEPARATORS_RE.split(name.strip())) > 1:
                    self._multiword_keys.add(key)
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

    def find_in_text(
        self, text: str, categories: frozenset[str] = TECHNICAL_CATEGORIES
    ) -> set[str]:
        """Skills of these categories named in free text (exact alias matches on 1-4 word
        spans). Defaults to technical skills (tools, languages...)."""
        tokens = _TOKEN_RE.findall(text)
        found: set[str] = set()
        for size in range(1, MAX_NGRAM + 1):
            for start in range(len(tokens) - size + 1):
                span = " ".join(tokens[start : start + size])
                candidates = [span]
                if size == 1 and "/" in span:
                    candidates += span.split("/")
                # Joining several words only matches a one-word name when it clearly spells
                # it ("JAVA SCRIPT"), not by accident ("I am" -> "iam").
                words = tokens[start : start + size]
                accidental = size > 1 and (min(len(w) for w in words) < 2 or len(span) < 6)
                for candidate in candidates:
                    key = skill_key(candidate)
                    if accidental and key not in self._multiword_keys:
                        continue
                    skill_id = self._keys.get(key)
                    if (
                        skill_id
                        and key not in _AMBIGUOUS_KEYS
                        and self.skills[skill_id].category in categories
                    ):
                        found.add(skill_id)
        return found

    def implied_by(self, skill_id: str) -> frozenset[str]:
        """Skills that evidence of `skill_id` implies (transitively), excluding itself."""
        return self._implied.get(skill_id, frozenset())

    def prerequisite_closure(self, skill_id: str) -> frozenset[str]:
        """All direct and indirect prerequisites of `skill_id`."""
        return self._closure(skill_id, "prerequisites") if skill_id in self.skills else frozenset()

    def name(self, skill_id: str) -> str:
        return self.skills[skill_id].name

    def prerequisites(self, skill_id: str) -> list[str]:
        return list(self.skills[skill_id].prerequisites)


@cache
def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    return Taxonomy(TaxonomyFile.model_validate(json.loads(path.read_text(encoding="utf-8"))))
