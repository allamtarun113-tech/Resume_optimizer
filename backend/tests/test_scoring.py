"""app.scoring must stay at 100% coverage (enforced in CI)."""

from datetime import date
from fractions import Fraction as F

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.scoring.engine import (
    classify,
    evidence_strength,
    experience_strength,
    experience_years,
    fit_score,
    parse_month,
    requirement_weight,
    round_half_up,
    uplift,
)
from app.scoring.weights import IMPLIED, LISTED_OR_DEMONSTRATED, NONE, SCORING_VERSION
from tests.builders import ref

AS_OF = date(2026, 9, 1)


def test_scoring_version_is_set() -> None:
    assert SCORING_VERSION


@pytest.mark.parametrize(
    ("importance", "category", "expected"),
    [
        ("must", "skill", F(3)),
        ("nice", "skill", F(1)),
        ("must", "domain", F("2.7")),
        ("must", "experience", F(3)),
        ("nice", "education", F("0.6")),
        ("must", "soft_skill", F("1.2")),
    ],
)
def test_requirement_weight(importance: str, category: str, expected: F) -> None:
    assert requirement_weight(importance, category) == expected


def test_round_half_up() -> None:
    assert round_half_up(F(1, 2)) == 1
    assert round_half_up(F(3, 2)) == 2  # not banker's rounding
    assert round_half_up(F(149, 100)) == 1
    assert round_half_up(F(2, 3), 3) == F(667, 1000)


# -- evidence strength ------------------------------------------------------------------


def test_listed_and_demonstrated_is_full() -> None:
    refs = [ref("skills_section"), ref("project", kind="project")]
    assert evidence_strength("skill", refs) == 1


@pytest.mark.parametrize("context", ["skills_section", "summary", "certification", "project"])
def test_listed_or_demonstrated_only_is_point_seven(context: str) -> None:
    assert evidence_strength("skill", [ref(context)]) == LISTED_OR_DEMONSTRATED


def test_only_implied_evidence_is_point_four() -> None:
    assert evidence_strength("skill", [ref("project", direct=False)]) == IMPLIED


def test_no_evidence_is_zero() -> None:
    assert evidence_strength("skill", []) == NONE


def test_implied_refs_do_not_count_towards_listed_and_demonstrated() -> None:
    refs = [ref("skills_section"), ref("project", direct=False)]
    assert evidence_strength("skill", refs) == LISTED_OR_DEMONSTRATED


def test_education_any_direct_evidence_is_full() -> None:
    assert evidence_strength("education", [ref("education", kind="education")]) == 1
    assert evidence_strength("education", [ref("education", direct=False)]) == IMPLIED


def test_soft_skill_needs_demonstration_for_full() -> None:
    assert evidence_strength("soft_skill", [ref("experience", kind="experience")]) == 1
    assert evidence_strength("soft_skill", [ref("skills_section")]) == LISTED_OR_DEMONSTRATED


# -- experience years -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-03", 2024 * 12 + 2),
        ("2024", 2024 * 12),
        ("Present", 2026 * 12 + 8),
        ("current", 2026 * 12 + 8),
        (None, None),
        ("", None),
        ("2024-13", None),
        ("March 2024", None),
    ],
)
def test_parse_month(value: str | None, expected: int | None) -> None:
    assert parse_month(value, AS_OF) == expected


def test_experience_years_merges_overlaps_and_counts_inclusive_months() -> None:
    ranges = [("2024-01", "2024-06"), ("2024-04", "2024-12"), ("2025-06", "2025-08")]
    assert experience_years(ranges, AS_OF) == F(12 + 3, 12)


def test_experience_years_adjacent_ranges_join() -> None:
    assert experience_years([("2024-01", "2024-06"), ("2024-07", "2024-12")], AS_OF) == 1


def test_experience_years_present_and_missing_or_bad_ends() -> None:
    assert experience_years([("2026-01", "present")], AS_OF) == F(9, 12)
    assert experience_years([("2025-05", None)], AS_OF) == F(1, 12)
    assert experience_years([("2025-05", "sometime")], AS_OF) == F(1, 12)
    assert experience_years([("2025-05", "2025-01")], AS_OF) == F(1, 12)  # reversed


def test_experience_years_none_without_usable_start() -> None:
    assert experience_years([(None, "2024-01"), ("soon", None)], AS_OF) is None
    assert experience_years([], AS_OF) is None


def test_experience_strength() -> None:
    job = [ref("experience", kind="experience")]
    assert experience_strength(F(1), F(2), job) == F(1, 2)
    assert experience_strength(F(3), F(2), job) == 1
    assert experience_strength(F(1, 12), F(3), job) == F(28, 1000)  # 0.0277… -> 0.028
    assert experience_strength(None, F(2), job) == IMPLIED
    assert experience_strength(None, F(2), []) == NONE
    assert experience_strength(F(1), F(0), job) == IMPLIED


# -- score ------------------------------------------------------------------------------


def test_fit_score_worked_example() -> None:
    # must skill 1.0, must skill 0.7, nice skill 0, must soft skill 0.4
    weighted = [(F(3), F(1)), (F(3), F("0.7")), (F(1), F(0)), (F("1.2"), F("0.4"))]
    # 100 × (3 + 2.1 + 0 + 0.48) / 8.2 = 68.048… -> 68
    assert fit_score(weighted) == 68


def test_fit_score_bounds_and_empty() -> None:
    assert fit_score([]) == 0
    assert fit_score([(F(3), F(0))]) == 0
    assert fit_score([(F(3), F(1)), (F(1), F(1))]) == 100


def test_fit_score_rounds_half_up() -> None:
    # 100 × 1/8 = 12.5 -> 13
    assert fit_score([(F(1), F(1, 8))]) == 13


def test_uplift() -> None:
    weighted = [(F(3), F(1)), (F(3), F(0))]
    assert uplift(weighted, {1: F(1)}) == 50
    assert uplift(weighted, {1: F("0.7")}) == 35
    assert uplift(weighted, {0: F(0)}) == 0  # never lowers a strength
    assert uplift(weighted, {}) == 0


@pytest.mark.parametrize(
    ("resume", "best", "bucket"),
    [
        (F(1), F(1), "strong_in_resume"),
        (F("0.7"), F(1), "weak_in_resume"),
        (F("0.4"), F("0.4"), "weak_in_resume"),
        (F(0), F("0.7"), "missing_from_resume_but_evidenced"),
        (F(0), F(0), "true_gap"),
    ],
)
def test_classify(resume: F, best: F, bucket: str) -> None:
    assert classify(resume, best) == bucket


# -- properties -------------------------------------------------------------------------

weights = st.sampled_from([F(3), F("2.7"), F(1), F("0.9"), F("1.8"), F("0.6"), F("1.2")])
strengths = st.sampled_from([F(0), F("0.4"), F("0.7"), F(1), F(1, 3), F("0.5")])
pairs = st.lists(st.tuples(weights, strengths), min_size=1, max_size=30)


@given(pairs)
def test_score_is_between_0_and_100(weighted: list[tuple[F, F]]) -> None:
    assert 0 <= fit_score(weighted) <= 100


@given(pairs, st.data())
def test_adding_evidence_never_lowers_the_score(
    weighted: list[tuple[F, F]], data: st.DataObject
) -> None:
    i = data.draw(st.integers(0, len(weighted) - 1))
    stronger = data.draw(strengths.filter(lambda s: s >= weighted[i][1]))
    improved = list(weighted)
    improved[i] = (weighted[i][0], stronger)
    assert fit_score(improved) >= fit_score(weighted)
    assert uplift(weighted, {i: stronger}) >= 0


@given(pairs, st.randoms())
def test_score_ignores_requirement_order(weighted: list[tuple[F, F]], rnd: object) -> None:
    shuffled = list(weighted)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert fit_score(shuffled) == fit_score(weighted)


@given(pairs)
def test_score_is_deterministic(weighted: list[tuple[F, F]]) -> None:
    assert len({fit_score(list(weighted)) for _ in range(5)}) == 1


@given(pairs, weights)
def test_adding_an_unmet_requirement_never_raises_the_score(
    weighted: list[tuple[F, F]], weight: F
) -> None:
    assert fit_score([*weighted, (weight, F(0))]) <= fit_score(weighted)


@given(
    st.lists(st.sampled_from(["skills_section", "project", "experience", "summary"]), max_size=5),
    st.lists(st.booleans(), max_size=5),
)
def test_more_refs_never_lower_strength(contexts: list[str], directs: list[bool]) -> None:
    refs = [ref(c, direct=d) for c, d in zip(contexts, directs, strict=False)]
    for category in ("skill", "domain", "education", "soft_skill"):
        for extra in (ref("project"), ref("skills_section"), ref("project", direct=False)):
            assert evidence_strength(category, [*refs, extra]) >= evidence_strength(category, refs)
