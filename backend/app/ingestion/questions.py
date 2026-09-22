"""Markdown -> interview question records (offline ingestion, no LLM).

Question banks use many layouts: headings, bullet lists, tables of contents, bold lines,
`<summary>` tags. The parser looks at the markdown structures a source allows
(`markers`), cleans the text, and keeps lines that read like interview questions.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from app.skills.taxonomy import Taxonomy

Marker = Literal["heading", "list", "table", "bold", "summary", "link"]
ALL_MARKERS: tuple[Marker, ...] = ("heading", "list", "table", "bold", "summary", "link")
Category = Literal["technical", "general", "personal"]

MIN_CHARS = 12
MAX_CHARS = 300

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
_BOLD_LINE_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*(.*)$")
_LINK_LINE_RE = re.compile(r"^\s*\[([^\]]+)\]\([^)]*\)\s*$")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_TAG_RE = re.compile(r"<[^>]+>")
_NUMBERING_RE = re.compile(r"^(?:q(?:uestion)?\s*\d*\s*[:.)-]|\d+\s*[.):-]|#\d+[.:]?)\s*", re.I)
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")
_TRAILING_ANSWER_RE = re.compile(r"^(.*?\?)\s*[(\[].*$")
_EMOJI_RE = re.compile("[\U0001f300-\U0001faff☀-➿⭐‍️]")
_SPACE_RE = re.compile(r"\s+")

_PROMPT_START = re.compile(
    r"^(what|why|how|when|where|which|who|whom|whose|explain|describe|compare|define|"
    r"difference|differentiate|tell me|give (?:an|me|some)|can you|could you|would you|"
    r"is|are|do|does|did|should|name|list|write|design|implement|walk me|discuss|"
    r"have you|if you|imagine|suppose|in what|talk about)\b",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"(table of contents|back to top|contributing|license|translations?|credits|"
    r"^answers?$|^solution|click here|star this repo)",
    re.IGNORECASE,
)
# Behavioral questions about the candidate themselves.
_PERSONAL = re.compile(
    r"(tell me about yourself|your (?:background|strengths?|weakness(?:es)?|career|goals?)|"
    r"why do you want|what are you looking for|where do you see yourself|describe yourself|"
    r"colleagues (?:use to )?describe you|what are you excited about|what frustrates you|"
    r"why (?:should we|will you be a good fit)|leave your (?:current|last))",
    re.IGNORECASE,
)


class QuestionRecord(BaseModel):
    text: str
    text_hash: str
    category: Category
    topics: list[str]
    role_tags: list[str]
    difficulty: Literal["easy", "medium", "hard"] | None
    source_repo: str
    source_path: str
    source_url: str
    license: str


class SourceFile(BaseModel):
    path: str
    topics: list[str] = Field(default_factory=list)


class Source(BaseModel):
    repo: str
    ref: str
    license: str
    category: Literal["technical", "general"]
    role_tags: list[str]
    files: list[SourceFile]
    markers: list[Marker] = Field(default_factory=lambda: list(ALL_MARKERS))
    difficulty_markers: bool = False


def normalize_question(text: str) -> str:
    """Comparison form: case/spacing/punctuation-insensitive."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s?+#]", " ", text)
    return _SPACE_RE.sub(" ", text).strip(" ?")


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode()).hexdigest()


def clean(text: str) -> str:
    text = _SUMMARY_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    text = text.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    text = _EMOJI_RE.sub("", text)
    text = _EMPHASIS_RE.sub("", text)
    text = text.replace("\\", "")
    text = _SPACE_RE.sub(" ", text).strip(" |:-#")
    text = _NUMBERING_RE.sub("", text).strip()
    # "What is OSGI? (Specification describes ...)" -> keep the question only.
    if (m := _TRAILING_ANSWER_RE.match(text)) and len(m.group(1)) >= MIN_CHARS:
        text = m.group(1)
    return text.rstrip(" .*").strip()


def looks_like_question(text: str) -> bool:
    if not MIN_CHARS <= len(text) <= MAX_CHARS or _NOISE.search(text):
        return False
    if "http" in text or text.count("|") > 0:
        return False
    if text.endswith("?"):
        return len(text.split()) >= 3
    # Without a question mark: a capitalized prompt ("Describe how processes are created").
    return text[0].isupper() and bool(_PROMPT_START.match(text)) and len(text.split()) >= 4


def difficulty_from(raw: str) -> Literal["easy", "medium", "hard"] | None:
    """alexeygrigorev/data-science-interviews marks 👶 easy, ⭐️ medium, 🚀 hard."""
    if "🚀" in raw:
        return "hard"
    if "⭐" in raw:
        return "medium"
    if "👶" in raw:
        return "easy"
    return None


def candidate_lines(markdown: str, markers: Iterable[Marker]) -> Iterable[tuple[str, str]]:
    """(raw line, current heading text) for lines in the allowed structures."""
    allowed = set(markers)
    in_code = False
    heading = ""
    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        if m := _HEADING_RE.match(line):
            heading = clean(m.group(2))
            if "heading" in allowed:
                yield m.group(2), heading
            continue
        if "summary" in allowed and "<summary" in line.lower():
            for s in _SUMMARY_RE.findall(line):
                yield s, heading
            continue
        if "table" in allowed and line.lstrip().startswith("|"):
            for cell in line.strip().strip("|").split("|"):
                yield cell, heading
            continue
        if "bold" in allowed and (m := _BOLD_LINE_RE.match(line)):
            yield m.group(1) + " " + m.group(2), heading
            continue
        if "link" in allowed and (m := _LINK_LINE_RE.match(line)):
            yield m.group(1), heading
            continue
        if "list" in allowed and (m := _LIST_RE.match(line)):
            yield m.group(1), heading


def parse_file(
    markdown: str, source: Source, file: SourceFile, taxonomy: Taxonomy
) -> list[QuestionRecord]:
    records: dict[str, QuestionRecord] = {}
    url = f"https://github.com/{source.repo}/blob/{source.ref}/{file.path}".replace(" ", "%20")
    for raw, heading in candidate_lines(markdown, source.markers):
        text = clean(raw)
        if not looks_like_question(text):
            continue
        key = question_hash(text)
        if key in records:
            continue
        topics = list(
            dict.fromkeys(
                [
                    *file.topics,
                    *sorted(taxonomy.find_in_text(heading)),
                    *([t] if (t := taxonomy.lookup(heading)) else []),
                    *sorted(taxonomy.find_in_text(text)),
                ]
            )
        )
        category: Category = source.category
        if category == "general" and _PERSONAL.search(text):
            category = "personal"
        records[key] = QuestionRecord(
            text=text,
            text_hash=key,
            category=category,
            topics=topics,
            role_tags=source.role_tags,
            difficulty=difficulty_from(raw) if source.difficulty_markers else None,
            source_repo=source.repo,
            source_path=file.path,
            source_url=url,
            license=source.license,
        )
    return list(records.values())
