import pytest

from app.agents.document_parser import DocumentParser
from app.parsing.extract import ExtractionError, FileType, detect_file_type, extract_text
from app.parsing.sections import match_heading, split_sections
from app.parsing.text import normalize_text, text_hash
from tests.samples import RESUME_CLASSIC, RESUME_COLON_HEADINGS, make_docx, make_pdf

PDF_RESUME = make_pdf(RESUME_CLASSIC.replace("•", "-"))


def test_normalize_text_is_canonical() -> None:
    raw = "  Skills\r\n\r\n\r\n\r\n• Python\t\tand  SQL \x00\n  ● Docker  "
    assert normalize_text(raw) == "Skills\n\n- Python and SQL\n- Docker"


def test_normalize_text_is_idempotent() -> None:
    once = normalize_text(RESUME_CLASSIC)
    assert normalize_text(once) == once


def test_normalize_text_folds_compatibility_characters() -> None:
    assert normalize_text("ﬁle ＰＹＴＨＯＮ") == "file PYTHON"


def test_text_hash_is_stable_sha256() -> None:
    assert text_hash("abc") == text_hash("abc")
    assert text_hash("abc") != text_hash("abd")
    assert len(text_hash("abc")) == 64


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("EDUCATION", "education"),
        ("Technical Skills:", "skills"),
        ("Work Experience", "experience"),
        ("Academic Projects", "projects"),
        ("Licenses & Certifications", "certifications"),
        ("Awards and Achievements", "achievements"),
        ("Python, Java, SQL", None),
        ("- Projects", None),
        ("Built a FastAPI backend with PostgreSQL", None),
        ("", None),
    ],
)
def test_match_heading(line: str, expected: str | None) -> None:
    assert match_heading(line) == expected


def test_split_sections_classic_resume() -> None:
    sections = split_sections(normalize_text(RESUME_CLASSIC))
    names = [s.name for s in sections]
    assert names == [
        "header",
        "summary",
        "education",
        "skills",
        "projects",
        "experience",
        "certifications",
    ]
    projects = next(s for s in sections if s.name == "projects")
    assert "Campus Food Ordering App" in projects.text
    assert "LSTM" in projects.text
    assert "Priya Sharma" in sections[0].text


def test_split_sections_colon_headings() -> None:
    names = [s.name for s in split_sections(normalize_text(RESUME_COLON_HEADINGS))]
    assert names == ["header", "summary", "education", "skills", "projects", "achievements"]


def test_split_sections_without_headings_keeps_everything() -> None:
    sections = split_sections("Just some notes about my project\nIt used Rust")
    assert len(sections) == 1
    assert sections[0].name == "header"


def test_detect_file_type_uses_magic_bytes() -> None:
    assert detect_file_type(PDF_RESUME, "resume.docx") is FileType.PDF
    assert detect_file_type(make_docx(["x"]), "cv.docx") is FileType.DOCX
    assert detect_file_type(b"hello", "notes.txt") is FileType.TEXT
    with pytest.raises(ExtractionError):
        detect_file_type(b"PK\x03\x04rest", "archive.zip")
    with pytest.raises(ExtractionError):
        detect_file_type(b"\x89PNG....", "photo.png")


def test_extract_pdf_text() -> None:
    text = extract_text(PDF_RESUME, "resume.pdf")
    assert "Campus Food Ordering App" in text
    assert "B.Tech in Computer Science" in text
    assert [s.name for s in split_sections(text)][1:4] == ["summary", "education", "skills"]


def test_scanned_pdf_is_rejected_with_clear_message() -> None:
    with pytest.raises(ExtractionError, match="scanned"):
        extract_text(make_pdf(""), "scan.pdf")


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"%PDF-1.4\nthis is not really a pdf", "broken.pdf")


def test_extract_docx_includes_tables_once() -> None:
    data = make_docx(
        ["EXPERIENCE", "Data Intern at Foo Labs, built ETL pipelines in Airflow and dbt."],
        table=[["Skills", "Python, Airflow, dbt, Snowflake, Looker dashboards"]],
    )
    text = extract_text(data, "cv.docx")
    assert "Airflow and dbt" in text
    assert text.count("Snowflake") == 1


def test_extract_plain_text_handles_bom_and_latin1() -> None:
    body = "Worked on café recommendation engine using collaborative filtering. " * 3
    assert "café" in extract_text(b"\xef\xbb\xbf" + body.encode(), "notes.txt")
    assert "café" in extract_text(body.encode("latin-1"), "notes.txt")


def test_document_parser_file_and_text() -> None:
    parser = DocumentParser()
    parsed = parser.parse_file(PDF_RESUME, "resume.pdf")
    assert parsed.text_hash == text_hash(parsed.text)
    assert "projects" in [s.name for s in parsed.sections]

    pasted = parser.parse_text("  I also built a Chrome extension in TypeScript.  ")
    assert pasted.text == "I also built a Chrome extension in TypeScript."
    with pytest.raises(ExtractionError):
        parser.parse_text("hi")
