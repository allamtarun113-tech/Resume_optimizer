"""Job-description file extraction, 20 supporting documents, and the shared text budget."""

from collections.abc import Iterator

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.profile_extractor import (
    MAX_SUPPLEMENTARY_CHARS,
    SUPPLEMENTARY_BUDGET,
    ProfileExtractorInput,
    SourceDocument,
    build_input,
    fair_limits,
    label_documents,
)
from app.core.config import Settings
from app.parsing.text import text_hash
from tests.samples import JOB_DESCRIPTION, make_docx, make_pdf
from tests.test_api_analyses import Harness


@pytest.fixture
def h(settings: Settings) -> Iterator[Harness]:
    harness = Harness(settings)
    with harness.client:
        yield harness


# -- fair text budget ---------------------------------------------------------------------


def test_short_documents_keep_everything_and_long_ones_share_the_rest() -> None:
    limits = fair_limits([1_000, 2_000, 50_000, 50_000], budget=20_000, cap=15_000)
    assert limits == [1_000, 2_000, 8_500, 8_500]


def test_under_budget_nothing_is_cut_except_by_the_per_document_cap() -> None:
    assert fair_limits([100, 20_000], budget=60_000, cap=15_000) == [100, 15_000]
    assert fair_limits([], budget=60_000, cap=15_000) == []


@given(st.lists(st.integers(0, 40_000), max_size=20))
def test_limits_always_fit_the_budget(lengths: list[int]) -> None:
    limits = fair_limits(lengths, SUPPLEMENTARY_BUDGET, MAX_SUPPLEMENTARY_CHARS)
    assert sum(limits) <= SUPPLEMENTARY_BUDGET
    assert all(
        0 <= lim <= min(n, MAX_SUPPLEMENTARY_CHARS) for lim, n in zip(limits, lengths, strict=True)
    )


def test_twenty_long_documents_fit_the_prompt_budget() -> None:
    def doc(i: int) -> SourceDocument:
        text = f"Project {i}. " + "detail " * 3_000
        return SourceDocument(doc_id=f"d{i}", text=text, text_hash=text_hash(text))

    resume = SourceDocument(doc_id="r", text="resume", text_hash=text_hash("resume"))
    prompt = build_input(
        label_documents(
            ProfileExtractorInput(resume=resume, supplementary=[doc(i) for i in range(20)])
        )
    )
    assert prompt.count("<document id=") == 21
    assert len(prompt) < SUPPLEMENTARY_BUDGET + 2_000


# -- 20 supporting documents ----------------------------------------------------------------


def test_analysis_accepts_twenty_supporting_documents(h: Harness) -> None:
    resume_id = h.upload_resume().json()["id"]
    ids = [
        h.paste_supporting(f"Project {i}: built a thing with Python and Docker.").json()["id"]
        for i in range(20)
    ]
    assert h.analyze(resume_id, ids).status_code == 202
    assert h.analyze(resume_id, [*ids, ids[0]]).status_code == 422  # 21 is over the limit


# -- job description files --------------------------------------------------------------


def test_extract_text_from_a_jd_pdf_without_storing_it(h: Harness) -> None:
    before = len(h.repo.documents)
    res = h.client.post(
        "/documents/extract-text",
        files={"file": ("job.pdf", make_pdf(JOB_DESCRIPTION), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "Strong Python and FastAPI" in body["text"]
    assert body["char_count"] == len(body["text"])
    assert len(h.repo.documents) == before and not h.repo.files  # nothing stored


def test_extract_text_from_docx(h: Harness) -> None:
    data = make_docx(
        [
            "Data Analyst at Example Retail",
            "Requirements: SQL, Excel, Tableau and statistics.",
            "You will build dashboards and present insights to stakeholders every week.",
        ]
    )
    res = h.client.post(
        "/documents/extract-text", files={"file": ("jd.docx", data, "application/octet-stream")}
    )
    assert res.status_code == 200
    assert "Tableau" in res.json()["text"]


@pytest.mark.parametrize(
    ("name", "data", "status", "detail"),
    [
        ("scan.pdf", make_pdf(""), 422, "scanned"),
        ("photo.png", b"\x89PNG....", 422, "Unsupported"),
        ("huge.txt", ("word " * 4_000).encode(), 422, "up to 15,000"),
        ("big.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024), 413, "5 MB"),
    ],
)
def test_extract_text_rejects_bad_files(
    h: Harness, name: str, data: bytes, status: int, detail: str
) -> None:
    res = h.client.post("/documents/extract-text", files={"file": (name, data, "application/pdf")})
    assert res.status_code == status
    assert detail in res.json()["detail"]
