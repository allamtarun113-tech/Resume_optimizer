import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.agents.document_parser import DocumentParser
from app.api.deps import get_repository
from app.core.auth import CurrentUser, get_current_user
from app.db.repository import Repository
from app.parsing.extract import ExtractionError, FileType, detect_file_type
from app.schemas.documents import DocumentResponse, ParsedDocument, UploadKind

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


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repo: Annotated[Repository, Depends(get_repository)],
    kind: Annotated[UploadKind, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form(max_length=MAX_PASTED_CHARS)] = None,
) -> DocumentResponse:
    """Upload a resume/supporting file, or paste supporting text. Text is extracted now."""
    if (file is None) == (not text):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send either a file or text.")
    if kind == "resume" and file is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload the resume as a file.")

    storage_path: str | None = None
    filename: str | None = None
    try:
        if file is not None:
            data = await file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, "Files must be 5 MB or smaller."
                )
            filename = (file.filename or "upload")[:200]
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
