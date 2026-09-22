"""Text extraction from uploaded files. No LLM, no I/O besides the given bytes."""

import io
import logging
import zipfile
from enum import StrEnum

import pdfplumber
import pypdf
from docx import Document as load_docx

from app.parsing.text import normalize_text

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 30
# Below this many non-space characters we assume the PDF is scanned (no text layer).
MIN_TEXT_CHARS = 80


class FileType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"


class ExtractionError(ValueError):
    """The file can't be turned into text. The message is safe to show to users."""


def detect_file_type(data: bytes, filename: str) -> FileType:
    """Decide the type from the file's bytes; the extension only disambiguates zips."""
    name = filename.lower()
    if data.startswith(b"%PDF-"):
        return FileType.PDF
    if data.startswith(b"PK\x03\x04"):
        if name.endswith(".docx"):
            return FileType.DOCX
        raise ExtractionError("Only .docx Word files are supported.")
    if name.endswith((".txt", ".md")):
        return FileType.TEXT
    raise ExtractionError("Unsupported file type. Upload a PDF, DOCX or .txt file.")


def extract_text(data: bytes, filename: str) -> str:
    """Return normalized text, or raise ExtractionError with a user-facing message."""
    file_type = detect_file_type(data, filename)
    if file_type is FileType.PDF:
        text = _extract_pdf(data)
    elif file_type is FileType.DOCX:
        text = _extract_docx(data)
    else:
        text = _decode_text(data)

    text = normalize_text(text)
    if _meaningful_chars(text) < MIN_TEXT_CHARS:
        if file_type is FileType.PDF:
            raise ExtractionError(
                "This PDF has no selectable text (it looks scanned). "
                "Export it again from Word/Google Docs, or upload a DOCX instead."
            )
        raise ExtractionError("The file contains too little text to analyze.")
    return text


def _meaningful_chars(text: str) -> int:
    return sum(1 for c in text if not c.isspace())


def _extract_pdf(data: bytes) -> str:
    primary = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages[:MAX_PDF_PAGES]
            primary = "\n\n".join(page.extract_text() or "" for page in pages)
    except Exception:  # pdfminer raises many exception types on odd PDFs
        logger.warning("pdfplumber failed, falling back to pypdf", exc_info=True)

    if _meaningful_chars(primary) >= MIN_TEXT_CHARS:
        return primary

    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        fallback = "\n\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES])
    except Exception as exc:
        if primary:
            return primary
        raise ExtractionError(
            "Could not read this PDF. It may be damaged or password-protected."
        ) from exc
    return max(primary, fallback, key=_meaningful_chars)


def _extract_docx(data: bytes) -> str:
    try:
        doc = load_docx(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ExtractionError("Could not read this Word file.") from exc

    parts = [p.text for p in doc.paragraphs]
    # Resumes built from Word templates often put content in tables.
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            # Merged cells repeat the same text; keep the first occurrence only.
            parts.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(parts)


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")
