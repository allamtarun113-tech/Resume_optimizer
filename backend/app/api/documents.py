import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.agents.document_parser import DocumentParser
from app.api.deps import get_repository
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.repository import Repository
from app.parsing.extract import ExtractionError, FileType, detect_file_type
from app.schemas.analyses import MAX_JD_CHARS
from app.schemas.documents import DocumentResponse, ExtractedText, ParsedDocument, UploadKind

router = APIRouter(tags=["documents"])

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PASTED_CHARS = 20_000
_CONTENT_TYPES = {
    FileType.PDF: ("application/pdf", ".pdf"),
    FileType.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    FileType.TEXT: ("text/plain", ".txt"),
}

_parser = DocumentParser()


def _safe_filename(name: str | None) -> str:
    """Display name only (never used as a storage path): base name, printable, bounded."""
    base = (name or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(c for c in base if c.isprintable()).strip()
    return (cleaned or "upload")[:200]


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repo: Annotated[Repository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    kind: Annotated[UploadKind, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form(max_length=MAX_PASTED_CHARS)] = None,
) -> DocumentResponse:
    """Upload a resume/supporting file, or paste supporting text. Text is extracted now."""
    if (file is None) == (not text):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send either a file or text.")
    if kind == "resume" and file is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload the resume as a file.")

    since = datetime.now(UTC) - timedelta(days=1)
    if await repo.count_uploads_since(user.id, since) >= settings.daily_upload_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've reached the limit of {settings.daily_upload_limit} uploads per day.",
        )

    storage_path: str | None = None
    filename: str | None = None
    try:
        if file is not None:
            data = await file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, "Files must be 5 MB or smaller."
                )
            filename = _safe_filename(file.filename)
            content_type, ext = _CONTENT_TYPES[detect_file_type(data, filename)]
            # pdfminer is CPU-bound; keep the event loop free.
            parsed: ParsedDocument = await asyncio.to_thread(_parser.parse_file, data, filename)
            storage_path = f"{user.id}/{uuid.uuid4()}{ext}"
            await repo.upload_file(storage_path, data, content_type)
        else:
            parsed = _parser.parse_text(text or "")
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    doc = await repo.insert_document(
        user_id=user.id,
        kind=kind,
        filename=filename,
        storage_path=storage_path,
        extracted_text=parsed.text,
        text_hash=parsed.text_hash,
    )
    return DocumentResponse(
        id=doc.id,
        kind=doc.kind,
        filename=doc.filename,
        char_count=len(parsed.text),
        sections=[s.name for s in parsed.sections],
    )


@router.post("/documents/extract-text")
async def extract_document_text(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> ExtractedText:
    """Read the text of a job description file (PDF/DOCX/TXT) so the user can review and
    edit it before analyzing. Nothing is stored."""
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Files must be 5 MB or smaller.")
    try:
        parsed = await asyncio.to_thread(_parser.parse_file, data, _safe_filename(file.filename))
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if len(parsed.text) > MAX_JD_CHARS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"This file has {len(parsed.text):,} characters; job descriptions can be up to "
            f"{MAX_JD_CHARS:,}. Paste just the job description part instead.",
        )
    return ExtractedText(text=parsed.text, char_count=len(parsed.text))
