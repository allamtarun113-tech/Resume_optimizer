"""Agent 2: ProfileExtractor (LLM, small). Resume + supplementary text -> StudentProfile."""

import logging
from typing import Any

from pydantic import BaseModel

from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.schemas.profile import StudentProfile

logger = logging.getLogger(__name__)

MAX_RESUME_CHARS = 20_000
MAX_SUPPLEMENTARY_CHARS = 15_000  # per document
# All supplementary documents together (up to 20 per analysis) share this budget, which
# keeps a 20-document analysis around a cent on a small model.
SUPPLEMENTARY_BUDGET = 60_000
MAX_OUTPUT_TOKENS = 16_000
RESUME_LABEL = "RESUME"
_SOURCED_FIELDS = ("skills", "projects", "experience", "education", "certifications")


class SourceDocument(BaseModel):
    doc_id: str
    text: str
    text_hash: str


class ProfileExtractorInput(BaseModel):
    resume: SourceDocument
    supplementary: list[SourceDocument]


def label_documents(inp: ProfileExtractorInput) -> list[tuple[str, str, SourceDocument]]:
    """(prompt label, stored source, document) for each input document.

    Supplementary docs get positional labels ordered by content hash, so re-uploading the
    same files yields the same prompt (and a cache hit) even though document ids differ.
    """
    labeled = [(RESUME_LABEL, "resume", inp.resume)]
    seen = {inp.resume.text_hash}
    for doc in sorted(inp.supplementary, key=lambda d: d.text_hash):
        if doc.text_hash in seen:
            continue
        seen.add(doc.text_hash)
        labeled.append((f"S{len(labeled)}", f"supplementary:{doc.doc_id}", doc))
    return labeled


def fair_limits(lengths: list[int], budget: int, cap: int) -> list[int]:
    """Per-document character limits that fit `budget`: short documents keep all their
    text, and what they don't use is shared equally among the longer ones."""
    limits = [0] * len(lengths)
    remaining = budget
    pending = sorted(range(len(lengths)), key=lambda i: lengths[i])
    while pending:
        share = remaining // len(pending)
        i = pending.pop(0)
        limits[i] = min(lengths[i], cap, share)
        remaining -= limits[i]
    return limits


def build_input(labeled: list[tuple[str, str, SourceDocument]]) -> str:
    supplementary = [doc for label, _, doc in labeled if label != RESUME_LABEL]
    limits = iter(
        fair_limits(
            [len(d.text) for d in supplementary], SUPPLEMENTARY_BUDGET, MAX_SUPPLEMENTARY_CHARS
        )
    )
    blocks = []
    for label, _, doc in labeled:
        limit = MAX_RESUME_CHARS if label == RESUME_LABEL else next(limits)
        blocks.append(f'<document id="{label}">\n{doc.text[:limit]}\n</document>')
    return "\n\n".join(blocks)


def resolve_sources(profile: StudentProfile, sources: dict[str, str]) -> StudentProfile:
    """Replace prompt labels with stored sources; drop items citing an unknown document."""
    updates: dict[str, list[Any]] = {}
    for field in _SOURCED_FIELDS:
        kept = []
        for item in getattr(profile, field):
            source = sources.get(item.source.strip().upper())
            if source is None:
                logger.warning("Dropping %s item with unknown source %r", field, item.source)
                continue
            kept.append(item.model_copy(update={"source": source}))
        updates[field] = kept
    return profile.model_copy(update=updates)


class ProfileExtractor:
    name = "profile_extractor"
    uses_llm = True

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.prompt = load_prompt(self.name)

    async def run(
        self,
        inp: ProfileExtractorInput,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> StudentProfile:
        labeled = label_documents(inp)
        profile = await self._llm.parse(
            agent=self.name,
            prompt=self.prompt,
            input_text=build_input(labeled),
            output_type=StudentProfile,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            analysis_id=analysis_id,
            user_id=user_id,
        )
        return resolve_sources(profile, {label: source for label, source, _ in labeled})
