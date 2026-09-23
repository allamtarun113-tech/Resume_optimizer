"""AtsChecker (no LLM): how well an applicant tracking system can read the resume.

Reads facts from the resume's extracted text (contact details, headings, dates,
personal details, the job's keywords written word for word) and combines them with the
file's layout (app.parsing.layout) into an AtsReport via app.scoring.ats.
"""

import re
from collections.abc import Collection, Sequence

from app.agents.skill_normalizer import NormalizedSkills
from app.parsing.sections import split_sections
from app.schemas.ats import AtsReport, KeywordFact, ResumeLayout, TextFacts
from app.schemas.matching import RequirementMatch
from app.schemas.requirements import JobRequirements
from app.scoring.ats import ats_report
from app.skills.taxonomy import Taxonomy

# Requirement categories an ATS searches for as keywords.
KEYWORD_CATEGORIES = ("skill", "domain")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{8,}\d(?![\w/])")
MIN_PHONE_DIGITS = 10
LINK_URL_RE = re.compile(r"\b(?:linkedin\.com|github\.com)/\S+", re.IGNORECASE)
LINK_MENTION_RE = re.compile(r"\b(linked\s?in|github)\b", re.IGNORECASE)

_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
DATE_STYLES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Month YYYY", re.compile(rf"\b(?:{_MONTHS})[.,]?\s+(?:19|20)\d{{2}}\b", re.IGNORECASE)),
    ("MM/YYYY", re.compile(r"\b(?:0?[1-9]|1[0-2])/(?:19|20)\d{2}\b")),
    ("YYYY-MM", re.compile(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])\b")),
    ("MM-YYYY", re.compile(r"\b(?:0[1-9]|1[0-2])-(?:19|20)\d{2}\b")),
)
PERSONAL_DETAILS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gender", re.compile(r"\b(?:gender|male|female)\b", re.IGNORECASE)),
    (
        "age",
        re.compile(
            r"\bage\s*[:\-]\s*\d{2}\b|\b\d{2}\s*(?:years|yrs)\s+old\b"
            r"|\b(?:male|female)\s*[,|/]\s*\d{2}\b",
            re.IGNORECASE,
        ),
    ),
    ("date of birth", re.compile(r"\bdate of birth\b|\bd\.?o\.?b\b|\bborn on\b", re.IGNORECASE)),
    ("marital status", re.compile(r"\bmarital status\b|\b(?:un)?married\b", re.IGNORECASE)),
    ("religion", re.compile(r"\breligion\b", re.IGNORECASE)),
    ("nationality", re.compile(r"\bnationality\b", re.IGNORECASE)),
    ("father's name", re.compile(r"\bfather'?s name\b", re.IGNORECASE)),
)


def _unreadable(c: str) -> bool:
    return c == "\ufffd" or "\ue000" <= c <= "\uf8ff"


def text_facts(text: str) -> TextFacts:
    phones = [
        m for m in PHONE_RE.findall(text) if sum(ch.isdigit() for ch in m) >= MIN_PHONE_DIGITS
    ]
    urls = [m.group(0).rstrip(".,;)") for m in LINK_URL_RE.finditer(text)]
    linked = {u.split(".com")[0].lower() for u in urls}
    mentions: list[str] = []
    for m in LINK_MENTION_RE.finditer(text):
        name = "LinkedIn" if m.group(1).lower().startswith("linked") else "GitHub"
        site = "linkedin" if name == "LinkedIn" else "github"
        if not any(site in u for u in linked) and name not in mentions:
            mentions.append(name)
    styles: dict[str, str] = {}
    for style, pattern in DATE_STYLES:
        match = pattern.search(text)
        if match:
            styles[style] = match.group(0)
    return TextFacts(
        chars=sum(1 for c in text if not c.isspace()),
        unreadable_chars=sum(1 for c in text if _unreadable(c)) + 5 * text.count("(cid:"),
        words=len(text.split()),
        sections=sorted({s.name for s in split_sections(text)} - {"header"}),
        has_email=bool(EMAIL_RE.search(text)),
        has_phone=bool(phones),
        link_urls=urls,
        link_mentions=mentions,
        date_styles=styles,
        personal_details=[name for name, pattern in PERSONAL_DETAILS if pattern.search(text)],
    )


def _literal(name: str, text: str) -> bool:
    words = name.split()
    if not words:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def keyword_facts(
    requirements: JobRequirements,
    normalized: NormalizedSkills,
    matches: Sequence[RequirementMatch],
    text: str,
    taxonomy: Taxonomy,
) -> list[KeywordFact]:
    """The job's skill and domain requirements, and whether the resume names each one
    word for word (or by a known alias). Related skills don't count: an ATS matches words."""
    all_categories = frozenset(s.category for s in taxonomy.skills.values())
    named = taxonomy.find_in_text(text, all_categories)
    buckets = {m.requirement_index: m.bucket for m in matches}
    facts: list[KeywordFact] = []
    for i, req in enumerate(requirements.requirements):
        if req.category not in KEYWORD_CATEGORIES:
            continue
        ids = {normalized.requirement_ids[i], *normalized.requirement_alternatives[i]} - {None}
        found = bool(ids & named) or _literal(req.name, text)
        facts.append(
            KeywordFact(
                requirement_index=i,
                name=req.name,
                importance=req.importance,
                found=found,
                bucket=buckets.get(i),
            )
        )
    return facts


class AtsChecker:
    name = "ats_checker"
    uses_llm = False

    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def run(
        self,
        *,
        layout: ResumeLayout | None,
        resume_text: str,
        requirements: JobRequirements,
        normalized: NormalizedSkills,
        matches: Sequence[RequirementMatch],
        addressed: Collection[int] = (),
    ) -> AtsReport:
        keywords = keyword_facts(requirements, normalized, matches, resume_text, self._taxonomy)
        return ats_report(layout, text_facts(resume_text), keywords, addressed)
