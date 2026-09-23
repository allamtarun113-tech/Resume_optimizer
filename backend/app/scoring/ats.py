"""Deterministic ATS score and final score. Pure functions over facts, no I/O.

Each check looks at facts Python read from the resume (app.parsing.layout,
app.agents.ats_checker) and earns up to ATS_POINTS[check]. Messages are plain English
because they are shown to students as they are."""

from collections.abc import Collection, Sequence
from fractions import Fraction

from app.schemas.ats import (
    AtsCheck,
    AtsGroup,
    AtsReport,
    AtsStatus,
    KeywordFact,
    ResumeLayout,
    TextFacts,
)
from app.scoring.engine import round_half_up
from app.scoring.weights import (
    ATS_GRAPHICS_SHARE,
    ATS_HIDDEN_LINK_SHARE,
    ATS_KEYWORDS_PASS,
    ATS_KEYWORDS_WARN,
    ATS_LONG_RESUME_SHARE,
    ATS_MAX_PAGES,
    ATS_MAX_WORDS,
    ATS_MIN_WORDS,
    ATS_PARTIAL_SHARE,
    ATS_POINTS,
    ATS_REQUIRED_SECTIONS,
    ATS_TABLE_SHARE,
    ATS_UNREADABLE_OK,
    ATS_UNREADABLE_WARN,
    ATS_VERSION,
    FINAL_ATS_WEIGHT,
    FINAL_FIT_WEIGHT,
    IMPORTANCE_WEIGHTS,
)

SECTION_NAMES = {"education": "Education", "skills": "Skills", "experience": "Experience"}


def _check(
    check_id: str,
    group: AtsGroup,
    title: str,
    share: Fraction,
    detail: str,
    fix: str | None = None,
    items: Sequence[str] = (),
    status: AtsStatus | None = None,
) -> AtsCheck:
    if status is None:
        status = "pass" if share == 1 else "fail" if share == 0 else "warn"
    points = ATS_POINTS[check_id]
    return AtsCheck(
        id=check_id,
        group=group,
        title=title,
        status=status,
        points=float(round_half_up(points * share, 2)),
        max_points=points,
        detail=detail,
        fix=None if status == "pass" else fix,
        items=list(items),
    )


# -- Can an ATS read it? -----------------------------------------------------------------


def readable_text(facts: TextFacts) -> AtsCheck:
    bad = Fraction(facts.unreadable_chars, max(facts.chars, 1))
    title = "Text can be read"
    fix = (
        "Export the PDF again from Word or Google Docs with standard fonts (Arial, Calibri, "
        "Times New Roman), or upload the resume as a DOCX."
    )
    if bad <= ATS_UNREADABLE_OK:
        return _check(
            "readable_text",
            "readable",
            title,
            Fraction(1),
            "All the text in your resume can be read as plain text.",
        )
    detail = (
        f"{facts.unreadable_chars} characters in your resume come out as unreadable symbols, "
        "so an ATS may miss words (often caused by special fonts or icons)."
    )
    share = ATS_PARTIAL_SHARE if bad <= ATS_UNREADABLE_WARN else Fraction(0)
    return _check("readable_text", "readable", title, share, detail, fix)


def layout_checks(layout: ResumeLayout) -> list[AtsCheck]:
    checks = [
        _check(
            "single_column",
            "readable",
            "One column",
            Fraction(0) if layout.multi_column else Fraction(1),
            "Your resume uses two or more columns side by side. Many ATSs read straight "
            "across the page and mix lines from both columns together."
            if layout.multi_column
            else "Your resume uses a single column, which every ATS reads in the right order.",
            "Move everything into one column: headings on the left, content below them.",
        ),
        _check(
            "no_tables",
            "readable",
            "No tables",
            ATS_TABLE_SHARE if layout.tables else Fraction(1),
            f"Found {_plural(layout.tables, 'table')}. Many ATSs read tables cell by cell or "
            "row by row, which jumbles the text (for example, an education table)."
            if layout.tables
            else "No tables: your text flows in plain lines.",
            'Write each row as one plain line, e.g. "B.Tech, Computer Science, '
            'ABC University, 2020 to 2024, CGPA 8.1".',
        ),
    ]
    graphics: list[str] = []
    if layout.photo:
        graphics.append("a photo")
    others = layout.images - (1 if layout.photo else 0)
    if others > 0:
        graphics.append(_plural(others, "picture or icon", "pictures or icons"))
    if layout.text_boxes:
        graphics.append(_plural(layout.text_boxes, "text box", "text boxes"))
    if layout.photo:
        share = Fraction(0)
    elif graphics:
        share = ATS_GRAPHICS_SHARE
    else:
        share = Fraction(1)
    checks.append(
        _check(
            "no_graphics",
            "readable",
            "No photo, icons or text boxes",
            share,
            f"Found {', '.join(graphics)}. An ATS can't read pictures, and text inside "
            "text boxes is often skipped. A photo can also lead to bias, so most "
            "employers ask you not to include one."
            if graphics
            else "No pictures, icons or text boxes.",
            "Remove the photo and icons; write contact details and headings as plain text.",
            items=graphics,
        )
    )
    if layout.header_footer_contact is not None:
        checks.append(
            _check(
                "contact_in_body",
                "readable",
                "Contact details in the main text",
                Fraction(0) if layout.header_footer_contact else Fraction(1),
                "Your email or phone number is only in the page header or footer, which "
                "many ATSs ignore."
                if layout.header_footer_contact
                else "Your contact details are in the main text.",
                "Move your email and phone number into the top lines of the page itself.",
            )
        )
    if layout.pages is not None:
        long = layout.pages > ATS_MAX_PAGES
        checks.append(
            _check(
                "page_count",
                "readable",
                "Length in pages",
                ATS_LONG_RESUME_SHARE if long else Fraction(1),
                f"Your resume is {layout.pages} pages. For students and new graduates, "
                "1 page (2 at most) is expected."
                if long
                else f"Your resume is {_plural(layout.pages, 'page')}.",
                "Cut it to 1 to 2 pages: keep what matters for this job.",
            )
        )
    return checks


# -- Sections and contact details ---------------------------------------------------------


def section_checks(facts: TextFacts) -> list[AtsCheck]:
    found = set(facts.sections)
    missing = [
        " or ".join(SECTION_NAMES.get(s, s.title()) for s in names)
        for names in ATS_REQUIRED_SECTIONS
        if not found.intersection(names)
    ]
    share = Fraction(len(ATS_REQUIRED_SECTIONS) - len(missing), len(ATS_REQUIRED_SECTIONS))
    checks = [
        _check(
            "standard_headings",
            "sections",
            "Standard section headings",
            share,
            f"We couldn't find these sections: {', '.join(missing)}. ATSs sort your resume "
            "by standard headings."
            if missing
            else "Your resume has the standard sections (Education, Skills, Experience or "
            "Projects) that ATSs look for.",
            'Use standard headings on their own line, e.g. "Education", "Skills", '
            '"Experience", "Projects".',
            items=missing,
        )
    ]

    contact_missing = [
        name
        for name, present in (("email", facts.has_email), ("phone number", facts.has_phone))
        if not present
    ]
    checks.append(
        _check(
            "contact_details",
            "sections",
            "Email and phone number",
            Fraction(2 - len(contact_missing), 2),
            f"We couldn't find your {' or '.join(contact_missing)} as text."
            if contact_missing
            else "Your email and phone number are written as text.",
            "Write your email and phone number as plain text at the top.",
            items=contact_missing,
        )
    )

    if facts.link_urls:
        share, detail = Fraction(1), "Your profile links are written out in full."
    elif facts.link_mentions:
        share = ATS_HIDDEN_LINK_SHARE
        detail = (
            f"{' and '.join(facts.link_mentions)} is written as a word only; an ATS "
            "reads text, not the link behind it."
        )
    else:
        share = ATS_PARTIAL_SHARE
        detail = "There's no LinkedIn or GitHub link. Recruiters usually look for one."
    checks.append(
        _check(
            "profile_links",
            "sections",
            "LinkedIn / GitHub links",
            share,
            detail,
            "Write the full link as text, e.g. linkedin.com/in/your-name and github.com/your-name.",
            items=facts.link_mentions,
        )
    )

    styles = list(facts.date_styles.items())
    checks.append(
        _check(
            "date_format",
            "sections",
            "Consistent dates",
            ATS_PARTIAL_SHARE if len(styles) > 1 else Fraction(1),
            "Dates are written in different styles ("
            + ", ".join(f'"{example}"' for _, example in styles)
            + "), which can confuse how an ATS works out your experience."
            if len(styles) > 1
            else "Dates are written in one consistent style.",
            'Use one style everywhere, e.g. "May 2023 to Jul 2023".',
            items=[example for _, example in styles] if len(styles) > 1 else [],
        )
    )

    checks.append(
        _check(
            "personal_details",
            "sections",
            "No unnecessary personal details",
            Fraction(0) if facts.personal_details else Fraction(1),
            f"Your resume includes {', '.join(facts.personal_details)}. These aren't needed "
            "and many employers remove them to avoid bias."
            if facts.personal_details
            else "No unnecessary personal details (such as age or gender).",
            "Remove details like gender, age, date of birth and marital status.",
            items=facts.personal_details,
            status="warn" if facts.personal_details else "pass",
        )
    )

    if facts.words < ATS_MIN_WORDS:
        share, detail = (
            ATS_PARTIAL_SHARE,
            (
                f"Your resume has about {facts.words} words, which is short: there's little "
                "for an ATS to match against the job."
            ),
        )
        fix = (
            "Describe your projects and experience in more detail: what you built, with "
            "what, and the result."
        )
    elif facts.words > ATS_MAX_WORDS:
        share, detail = (
            ATS_PARTIAL_SHARE,
            (f"Your resume has about {facts.words} words, which is long for a student resume."),
        )
        fix = "Shorten it: keep the points that matter for this job."
    else:
        share, detail, fix = Fraction(1), f"About {facts.words} words: a good length.", None
    checks.append(_check("length", "sections", "Amount of text", share, detail, fix))
    return checks


# -- Job keywords -------------------------------------------------------------------------


def keyword_share(keywords: Sequence[KeywordFact], found_extra: Collection[int] = ()) -> Fraction:
    total = sum((IMPORTANCE_WEIGHTS[k.importance] for k in keywords), Fraction(0))
    if total == 0:
        return Fraction(1)
    found = sum(
        (
            IMPORTANCE_WEIGHTS[k.importance]
            for k in keywords
            if k.found or k.requirement_index in found_extra
        ),
        Fraction(0),
    )
    return found / total


def keyword_check(keywords: Sequence[KeywordFact], found_extra: Collection[int] = ()) -> AtsCheck:
    share = keyword_share(keywords, found_extra)
    found = [k for k in keywords if k.found or k.requirement_index in found_extra]
    missing = [k.name for k in keywords if not (k.found or k.requirement_index in found_extra)]
    if not keywords:
        detail = "This job lists no specific skills to look for."
    else:
        detail = (
            f"Your resume uses {len(found)} of the job's {len(keywords)} skill keywords "
            "word for word (must-haves count 3 times). ATSs rank resumes by these words."
        )
    status: AtsStatus = (
        "pass" if share >= ATS_KEYWORDS_PASS else "warn" if share >= ATS_KEYWORDS_WARN else "fail"
    )
    return _check(
        "keywords",
        "keywords",
        "Job keywords",
        share,
        detail,
        "Use the job's exact words for skills you really have (see Improve resume); "
        "learn the rest (see Learn).",
        items=missing,
        status=status,
    )


# -- Totals -------------------------------------------------------------------------------


def ats_score(checks: Sequence[AtsCheck]) -> int:
    earned = sum((Fraction(str(c.points)) for c in checks), Fraction(0))
    total = sum((Fraction(c.max_points) for c in checks), Fraction(0))
    return int(round_half_up(100 * earned / total))


def ats_report(
    layout: ResumeLayout | None,
    facts: TextFacts,
    keywords: Sequence[KeywordFact],
    addressed: Collection[int] = (),
) -> AtsReport:
    """`addressed`: requirement indexes that the suggested resume lines would add."""
    base = [
        readable_text(facts),
        *(layout_checks(layout) if layout else []),
        *section_checks(facts),
    ]
    checks = [*base, keyword_check(keywords)]
    potential = [*base, keyword_check(keywords, addressed)]
    return AtsReport(
        version=ATS_VERSION,
        score=ats_score(checks),
        potential_score=ats_score(potential),
        checks=checks,
        keywords=list(keywords),
    )


def final_score(fit: int, ats: int) -> int:
    return int(round_half_up(FINAL_FIT_WEIGHT * fit + FINAL_ATS_WEIGHT * ats))


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"
