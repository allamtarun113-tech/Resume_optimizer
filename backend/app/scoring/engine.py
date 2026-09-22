"""Deterministic Job Fit Score. Pure functions, exact rational arithmetic, no I/O."""

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from fractions import Fraction

from app.schemas.matching import Bucket, EvidenceRef
from app.scoring.weights import (
    CATEGORY_WEIGHTS,
    DEMONSTRATED_CONTEXTS,
    FULL,
    IMPLIED,
    IMPORTANCE_WEIGHTS,
    LISTED_CONTEXTS,
    LISTED_OR_DEMONSTRATED,
    NONE,
    STRENGTH_DECIMALS,
)

_YEAR_MONTH_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")


def round_half_up(value: Fraction, decimals: int = 0) -> Fraction:
    scale = 10**decimals
    return Fraction(math.floor(value * scale + Fraction(1, 2)), scale)


def requirement_weight(importance: str, category: str) -> Fraction:
    return IMPORTANCE_WEIGHTS[importance] * CATEGORY_WEIGHTS[category]


def evidence_strength(category: str, refs: Iterable[EvidenceRef]) -> Fraction:
    refs = list(refs)
    direct = [r for r in refs if r.direct]
    if direct:
        listed = any(r.context in LISTED_CONTEXTS for r in direct)
        demonstrated = any(r.context in DEMONSTRATED_CONTEXTS for r in direct)
        if category == "education":
            return FULL
        if category == "soft_skill":
            return FULL if demonstrated else LISTED_OR_DEMONSTRATED
        return FULL if listed and demonstrated else LISTED_OR_DEMONSTRATED
    return IMPLIED if refs else NONE


def experience_strength(
    years: Fraction | None, min_years: Fraction, refs: Sequence[EvidenceRef]
) -> Fraction:
    """Strength for an experience requirement with a stated minimum number of years."""
    if years is None or min_years <= 0:
        return IMPLIED if refs else NONE
    return round_half_up(min(FULL, years / min_years), STRENGTH_DECIMALS)


def parse_month(value: str | None, as_of: date) -> int | None:
    """ "YYYY-MM" | "YYYY" | "present" -> months since year 0. Year-only means January."""
    if not value:
        return None
    text = value.strip().lower()
    if text in {"present", "current", "now", "ongoing"}:
        return as_of.year * 12 + as_of.month - 1
    match = _YEAR_MONTH_RE.match(text)
    if not match:
        return None
    month = int(match.group(2) or 1)
    if not 1 <= month <= 12:
        return None
    return int(match.group(1)) * 12 + month - 1


def experience_years(
    ranges: Iterable[tuple[str | None, str | None]], as_of: date
) -> Fraction | None:
    """Total years covered by (start, end) ranges, overlaps merged. None if no usable range.

    Months are inclusive (2024-01 to 2024-03 is 3 months); a missing end means one month.
    """
    intervals = []
    for start, end in ranges:
        first = parse_month(start, as_of)
        if first is None:
            continue
        last = parse_month(end, as_of) if end else first
        if last is None:
            last = first
        intervals.append((first, max(first, last)))
    if not intervals:
        return None

    intervals.sort()
    months = 0
    current_start, current_end = intervals[0]
    for first, last in intervals[1:]:
        if first <= current_end + 1:
            current_end = max(current_end, last)
        else:
            months += current_end - current_start + 1
            current_start, current_end = first, last
    months += current_end - current_start + 1
    return Fraction(months, 12)


def fit_score(weighted: Iterable[tuple[Fraction, Fraction]]) -> int:
    """round_half_up(100 × Σ w·s / Σ w) over (weight, strength) pairs; 0 if there are none."""
    total = Fraction(0)
    achieved = Fraction(0)
    for weight, strength in weighted:
        total += weight
        achieved += weight * strength
    if total == 0:
        return 0
    return int(round_half_up(100 * achieved / total))


def uplift(weighted: Sequence[tuple[Fraction, Fraction]], improved: Mapping[int, Fraction]) -> int:
    """Score change if requirement i's strength became improved[i] (never lowered)."""
    new = [(w, max(s, improved.get(i, s))) for i, (w, s) in enumerate(weighted)]
    return fit_score(new) - fit_score(weighted)


def classify(resume_strength: Fraction, best_strength: Fraction) -> Bucket:
    if resume_strength >= FULL:
        return "strong_in_resume"
    if resume_strength > 0:
        return "weak_in_resume"
    if best_strength > 0:
        return "missing_from_resume_but_evidenced"
    return "true_gap"
