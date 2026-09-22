"""EvidenceValidator (no LLM): enforces "never fabricate qualifications" (CLAUDE.md §1).

A drafted suggestion is kept only if:
1. it addresses at least one requirement that is eligible for advice,
2. it cites known evidence that belongs to one of those requirements,
3. its quote appears verbatim (ignoring case, spacing and quote/dash styles) in the
   document of one of the cited evidence items, and
4. every technical skill named in its suggested text is shown somewhere in the student's
   own documents (directly, or implied via the taxonomy).
"""

import re
import unicodedata
from dataclasses import dataclass

from app.schemas.advice import SuggestionDraft
from app.schemas.matching import EvidenceRef
from app.skills.taxonomy import Taxonomy

MIN_QUOTE_CHARS = 8
_ELLIPSIS_RE = re.compile(r"\.\.\.|…")
_CHAR_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "•": " "})


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP).casefold()
    return " ".join(text.split())


class RejectedDraft(ValueError):
    """The draft failed validation. The message is shown to users."""


@dataclass(frozen=True)
class ValidatedDraft:
    requirement_indexes: list[int]
    evidence: list[EvidenceRef]
    quote_source: str


class EvidenceValidator:
    name = "evidence_validator"
    uses_llm = False

    def __init__(self, taxonomy: Taxonomy, source_texts: dict[str, str]) -> None:
        """source_texts: {"resume" | "supplementary:<id>": full extracted text}.

        Allowed skills come from the raw documents, not the LLM-extracted profile, so an
        extraction mistake can't make a skill "allowed".
        """
        self._taxonomy = taxonomy
        self._sources = {k: normalize_for_match(v) for k, v in source_texts.items()}
        shown: set[str] = set()
        for text in source_texts.values():
            shown |= taxonomy.find_in_text(text)
        self._allowed_skills = shown | {i for s in shown for i in taxonomy.implied_by(s)}

    def validate(
        self,
        draft: SuggestionDraft,
        eligible: dict[str, int],
        evidence: dict[str, EvidenceRef],
        evidence_by_requirement: dict[int, set[str]],
    ) -> ValidatedDraft:
        """eligible: {"R3": requirement index}; evidence: {"Q1": ref};
        evidence_by_requirement: {requirement index: {"Q1", ...}}."""
        indexes = list(
            dict.fromkeys(
                eligible[r] for r in map(_clean_id, draft.requirement_ids) if r in eligible
            )
        )
        if not indexes:
            raise RejectedDraft("It doesn't address a requirement you can improve.")

        cited = [c for c in dict.fromkeys(map(_clean_id, draft.evidence_ids)) if c in evidence]
        if not cited:
            raise RejectedDraft("It doesn't cite any of your evidence.")
        related = set().union(*(evidence_by_requirement.get(i, set()) for i in indexes))
        if not any(c in related for c in cited):
            raise RejectedDraft("Its evidence is unrelated to the requirement.")

        quote_source = self._find_quote(draft.quote, [evidence[c].source for c in cited])
        if quote_source is None:
            raise RejectedDraft("Its quote isn't in your documents.")

        unsupported = self._taxonomy.find_in_text(draft.suggested_text) - self._allowed_skills
        if unsupported:
            names = ", ".join(sorted(self._taxonomy.name(s) for s in unsupported))
            raise RejectedDraft(f"It mentions {names}, which your documents don't show.")

        return ValidatedDraft(
            requirement_indexes=indexes,
            evidence=[evidence[c] for c in cited],
            quote_source=quote_source,
        )

    def _find_quote(self, quote: str, sources: list[str]) -> str | None:
        fragments = [normalize_for_match(f) for f in _ELLIPSIS_RE.split(quote)]
        fragments = [f for f in fragments if f]
        if not fragments or any(len(f) < MIN_QUOTE_CHARS for f in fragments):
            return None
        for source in dict.fromkeys(sources):
            text = self._sources.get(source, "")
            if _contains_in_order(text, fragments):
                return source
        return None


def _contains_in_order(text: str, fragments: list[str]) -> bool:
    position = 0
    for fragment in fragments:
        found = text.find(fragment, position)
        if found == -1:
            return False
        position = found + len(fragment)
    return True


def _clean_id(value: str) -> str:
    return value.strip().upper()
