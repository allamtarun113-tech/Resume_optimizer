"""Heuristic resume section splitting (Education, Experience, Projects, Skills...)."""

import re

from pydantic import BaseModel

# Canonical section -> headings that introduce it (compared lowercase, punctuation stripped).
SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "profile",
        "professional summary",
        "objective",
        "career objective",
        "about me",
        "about",
    ),
    "education": (
        "education",
        "academic background",
        "academics",
        "education and training",
        "academic qualifications",
        "qualifications",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "internships",
        "internship",
        "internship experience",
        "relevant experience",
    ),
    "projects": (
        "projects",
        "project",
        "academic projects",
        "personal projects",
        "key projects",
        "technical projects",
        "project experience",
        "selected projects",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "skills and tools",
        "technologies",
        "tech stack",
        "tools and technologies",
        "core competencies",
        "competencies",
        "skills summary",
    ),
    "coursework": (
        "coursework",
        "relevant coursework",
        "relevant courses",
        "elective courses",
        "electives",
        "core courses",
        "academic courses",
        "key courses",
        "courses taken",
        "courses undertaken",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses and certifications",
        "courses",
        "certifications and courses",
        "online courses",
        "training",
        "training and workshop",
        "training and workshops",
        "workshops",
    ),
    "achievements": (
        "achievements",
        "awards",
        "honors",
        "honours",
        "awards and achievements",
        "accomplishments",
        "extracurricular activities",
        "extra curricular activities",
        "co curricular activities",
        "extracurriculars",
        "activities",
        "leadership",
        "positions of responsibility",
    ),
    "publications": ("publications", "research", "research experience", "papers"),
}

_HEADING_LOOKUP = {h: name for name, headings in SECTION_HEADINGS.items() for h in headings}
_STRIP_RE = re.compile(r"[^a-z& ]+")
MAX_HEADING_WORDS = 5


class Section(BaseModel):
    name: str  # canonical name, or "header" for text before the first heading
    heading: str  # the heading as written
    text: str


def _heading_key(line: str) -> str:
    key = _STRIP_RE.sub(" ", line.lower().replace("&", " and "))
    return " ".join(key.split())


def match_heading(line: str) -> str | None:
    """Return the canonical section name if `line` looks like a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped.split()) > MAX_HEADING_WORDS or stripped.startswith("-"):
        return None
    return _HEADING_LOOKUP.get(_heading_key(stripped))


def split_sections(text: str) -> list[Section]:
    """Split normalized text into sections. Unrecognized text stays in the current section."""
    sections: list[Section] = []
    name, heading = "header", ""
    lines: list[str] = []

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            sections.append(Section(name=name, heading=heading, text=body))

    for line in text.split("\n"):
        matched = match_heading(line)
        if matched:
            flush()
            name, heading, lines = matched, line.strip(), []
        else:
            lines.append(line)
    flush()
    return sections
