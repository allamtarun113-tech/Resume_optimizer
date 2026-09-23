from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.parsing.sections import Section

DocumentKind = Literal["resume", "supporting", "jd", "extra_text"]
UploadKind = Literal["resume", "supporting"]


class ParsedDocument(BaseModel):
    """DocumentParser output."""

    text: str
    text_hash: str
    sections: list[Section]


class DocumentRecord(BaseModel):
    id: str
    user_id: str
    kind: DocumentKind
    filename: str | None
    storage_path: str | None
    extracted_text: str | None
    text_hash: str | None
    created_at: datetime


class DocumentResponse(BaseModel):
    id: str
    kind: DocumentKind
    filename: str | None
    char_count: int
    sections: list[str]


class ExtractedText(BaseModel):
    """Text pulled out of an uploaded file without storing it (e.g. a job description)."""

    text: str
    char_count: int
