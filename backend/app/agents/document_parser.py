"""Agent 1: DocumentParser (no LLM). Bytes or pasted text -> normalized text + sections."""

from app.parsing.extract import ExtractionError, extract_text
from app.parsing.sections import split_sections
from app.parsing.text import normalize_text, text_hash
from app.schemas.documents import ParsedDocument

MIN_PASTED_CHARS = 20


class DocumentParser:
    name = "document_parser"
    uses_llm = False

    def parse_file(self, data: bytes, filename: str) -> ParsedDocument:
        return self._build(extract_text(data, filename))

    def parse_text(self, text: str) -> ParsedDocument:
        normalized = normalize_text(text)
        if len(normalized) < MIN_PASTED_CHARS:
            raise ExtractionError("The pasted text is too short.")
        return self._build(normalized)

    @staticmethod
    def _build(text: str) -> ParsedDocument:
        return ParsedDocument(text=text, text_hash=text_hash(text), sections=split_sections(text))
