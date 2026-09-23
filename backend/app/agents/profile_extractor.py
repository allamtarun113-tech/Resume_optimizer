"""Agent 2: ProfileExtractor (LLM, small). Resume + supplementary text -> StudentProfile.

The resume and the supplementary material are extracted in two separate (parallel) calls,
each cached on its own text. So the resume's extraction — and with it the job fit score —
depends only on the resume: editing notes or adding a document never changes it.

Safety net (no LLM): the LLM sometimes skips a skill that is plainly written (e.g. an
elective course "Probability, Stochastic processes and Statistics"). Python scans each
document for skills the taxonomy knows and adds the ones the LLM missed, quoting the line
verbatim as evidence.
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from app.agents.skill_normalizer import SkillNormalizer
from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.parsing.sections import split_sections
from app.schemas.profile import SkillContext, SkillMention, StudentProfile
from app.skills.taxonomy import TECHNICAL_CATEGORIES, Taxonomy, load_taxonomy

logger = logging.getLogger(__name__)

MAX_RESUME_CHARS = 20_000
# Supplementary documents (projects, notes, files; up to 20 per analysis):
# - up to UNTRIMMED_DOCS of them are sent whole (only a safety ceiling per document, so a
#   huge file can't overflow the model's context);
# - with more, they share SUPPLEMENTARY_BUDGET, split fairly: short documents stay whole
#   and only the long ones are trimmed. This keeps a 20-document analysis around a cent.
MAX_SUPPLEMENTARY_CHARS = 40_000  # safety ceiling per document
UNTRIMMED_DOCS = 5
SUPPLEMENTARY_BUDGET = 120_000
MAX_OUTPUT_TOKENS = 16_000
RESUME_LABEL = "RESUME"
_SOURCED_FIELDS = ("skills", "projects", "experience", "education", "certifications")
# Safety net: short, list-like lines are scanned for concepts too ("Statistics",
# "Linear algebra"); longer prose lines only for technical skills (tools, languages...).
LIST_LINE_MAX_WORDS = 12
MAX_EVIDENCE_CHARS = 200
SECTION_CONTEXT: dict[str, SkillContext] = {
    "skills": "skills_section",
    "coursework": "education",
    "education": "education",
    "certifications": "certification",
    "summary": "summary",
}


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


def supplementary_limits(lengths: list[int]) -> list[int]:
    if len(lengths) <= UNTRIMMED_DOCS:
        return [min(n, MAX_SUPPLEMENTARY_CHARS) for n in lengths]
    return fair_limits(lengths, SUPPLEMENTARY_BUDGET, MAX_SUPPLEMENTARY_CHARS)


def build_input(labeled: list[tuple[str, str, SourceDocument]]) -> str:
    supplementary = [doc for label, _, doc in labeled if label != RESUME_LABEL]
    limits = iter(supplementary_limits([len(d.text) for d in supplementary]))
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


def merge_profiles(resume: StudentProfile, others: list[StudentProfile]) -> StudentProfile:
    """Resume items first, then supplementary ones; the headline comes from the resume."""
    updates: dict[str, list[Any]] = {
        field: [item for p in (resume, *others) for item in getattr(p, field)]
        for field in _SOURCED_FIELDS
    }
    return resume.model_copy(update=updates)


def missed_skills(
    profile: StudentProfile,
    labeled: list[tuple[str, str, SourceDocument]],
    taxonomy: Taxonomy,
    normalizer: SkillNormalizer,
) -> list[SkillMention]:
    """Skills written in a document that the extracted profile doesn't list for it."""
    added: list[SkillMention] = []
    for _, source, doc in labeled:
        known: set[str] = set()
        for m in profile.skills:
            if m.source == source:
                known.update(normalizer.resolve(m.name))
        techs = [t for p in profile.projects if p.source == source for t in p.technologies]
        techs += [t for x in profile.experience if x.source == source for t in x.technologies]
        for tech in techs:
            known.update(normalizer.resolve(tech))
        for section in split_sections(doc.text):
            context = SECTION_CONTEXT.get(section.name, "other")
            for line in section.text.split("\n"):
                text = line.strip()
                if not text:
                    continue
                categories = (
                    TECHNICAL_CATEGORIES | {"concept"}
                    if len(text.split()) <= LIST_LINE_MAX_WORDS
                    else TECHNICAL_CATEGORIES
                )
                for skill_id in sorted(taxonomy.find_in_text(text, categories) - known):
                    known.add(skill_id)
                    added.append(
                        SkillMention(
                            name=taxonomy.name(skill_id),
                            context=context,
                            context_name=None,
                            source=source,
                            evidence=text[:MAX_EVIDENCE_CHARS],
                        )
                    )
    return added


class ProfileExtractor:
    name = "profile_extractor"
    uses_llm = True

    def __init__(self, llm: LLMClient, taxonomy: Taxonomy | None = None) -> None:
        self._llm = llm
        self._taxonomy = taxonomy or load_taxonomy()
        self._normalizer = SkillNormalizer(self._taxonomy)
        self.prompt = load_prompt(self.name)

    async def _extract(
        self,
        labeled: list[tuple[str, str, SourceDocument]],
        analysis_id: str | None,
        user_id: str | None,
    ) -> StudentProfile:
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

    async def run(
        self,
        inp: ProfileExtractorInput,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> StudentProfile:
        labeled = label_documents(inp)
        parts = [
            [x for x in labeled if x[0] == RESUME_LABEL],
            [x for x in labeled if x[0] != RESUME_LABEL],
        ]
        resume, *others = await asyncio.gather(
            *(self._extract(part, analysis_id, user_id) for part in parts if part)
        )
        profile = merge_profiles(resume, others)
        extra = missed_skills(profile, labeled, self._taxonomy, self._normalizer)
        if extra:
            logger.info("Added %d skills the extraction missed", len(extra))
        return profile.model_copy(update={"skills": [*profile.skills, *extra]})
