import pytest

from app.reporting.costs import call_cost, cost_report


def row(analysis: str | None, agent: str, cached: bool, tin: int, tout: int) -> dict[str, object]:
    return {
        "analysis_id": analysis,
        "agent": agent,
        "cached": cached,
        "input_tokens": tin,
        "output_tokens": tout,
    }


def test_call_cost() -> None:
    assert call_cost(row("a", "x", False, 1_000_000, 1_000_000), 0.15, 0.60) == pytest.approx(0.75)


def test_cost_report_per_analysis() -> None:
    rows = [
        row("a", "profile_extractor", False, 2_400, 1_500),
        row("a", "jd_analyzer", False, 1_000, 800),
        row("a", "interview_prep", False, 2_800, 600),
        row("b", "profile_extractor", True, 0, 0),
        row("b", "jd_analyzer", True, 0, 0),
        row(None, "ingestion", False, 1_000, 0),  # not tied to an analysis
    ]
    report = cost_report(rows, input_per_m=0.15, output_per_m=0.60, target_usd=0.01)
    a = (6_200 * 0.15 + 2_900 * 0.60) / 1_000_000
    assert report.analyses == 2
    assert report.cached_calls == 2
    assert report.average_usd == pytest.approx(a / 2)
    assert report.max_usd == pytest.approx(a)
    assert report.within_target
    assert next(iter(report.by_agent_usd)) == "profile_extractor"  # most expensive first


def test_empty_report() -> None:
    report = cost_report([], input_per_m=1, output_per_m=1, target_usd=0.01)
    assert report.analyses == 0 and report.average_usd == 0 and report.within_target
