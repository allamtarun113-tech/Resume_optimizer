"""ATS check models: facts read from the resume file and text (Python only), and the
report the scoring engine builds from them."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.matching import Bucket
from app.schemas.requirements import Importance

AtsStatus = Literal["pass", "warn", "fail"]
AtsGroup = Literal["readable", "sections", "keywords"]


class ResumeLayout(BaseModel):
    """How the resume file is built (PDF or DOCX). None for fields a format can't tell."""

    file_type: Literal["pdf", "docx"]
    pages: int | None
    tables: int
    multi_column: bool
    images: int
    photo: bool  # a picture that looks like a portrait near the top of page 1
    text_boxes: int
    header_footer_contact: bool | None  # DOCX: email/phone only in the page header/footer


class TextFacts(BaseModel):
    """What an ATS would see in the resume's extracted text."""

    chars: int
    unreadable_chars: int
    words: int
    sections: list[str]
    has_email: bool
    has_phone: bool
    link_urls: list[str]  # linkedin.com/... or github.com/... written out in the text
    link_mentions: list[str]  # "LinkedIn"/"GitHub" written without a URL
    date_styles: dict[str, str]  # style -> first example, e.g. {"Mon YYYY": "May 2023"}
    personal_details: list[str]  # e.g. ["gender", "age"]


class KeywordFact(BaseModel):
    requirement_index: int
    name: str
    importance: Importance
    found: bool  # written in the resume, word for word (or a known alias)
    bucket: Bucket | None


class AtsCheck(BaseModel):
    id: str
    group: AtsGroup
    title: str
    status: AtsStatus
    points: float
    max_points: float
    detail: str
    fix: str | None
    items: list[str]


class AtsReport(BaseModel):
    version: str
    score: int
    potential_score: int  # if the suggested resume lines are added
    checks: list[AtsCheck]
    keywords: list[KeywordFact]
