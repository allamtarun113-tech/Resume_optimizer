"""Scoring constants (CLAUDE.md §5). Changing anything here means bumping SCORING_VERSION.

Evidence strength of a requirement, from the evidence in one set of documents:
  1.0  listed (skills section, summary, education, certification) AND demonstrated in a
       project or job
  0.7  listed OR demonstrated, but not both
  0.4  only implied (related evidence, e.g. PostgreSQL for "SQL", or an LLM "implied" match)
  0.0  no evidence
Category overrides:
  education   any direct evidence counts as 1.0 (a degree is either there or not)
  soft_skill  demonstrated in a project/job = 1.0, only listed = 0.7
  experience with min_years: min(1, candidate_years / min_years), counting only dated jobs
       that are direct evidence; other relevant evidence counts as implied (0.4)
Buckets (GapClassifier): resume strength 1.0 = strong_in_resume; >0 = weak_in_resume;
0 in the resume but >0 elsewhere = missing_from_resume_but_evidenced; else true_gap.
"""

from fractions import Fraction

# 2: requirements with alternatives ("Java, C++ or R") match any known alternative.
SCORING_VERSION = "2"

IMPORTANCE_WEIGHTS: dict[str, Fraction] = {"must": Fraction(3), "nice": Fraction(1)}

CATEGORY_WEIGHTS: dict[str, Fraction] = {
    "skill": Fraction("1.0"),
    "domain": Fraction("0.9"),
    "experience": Fraction("1.0"),
    "education": Fraction("0.6"),
    "soft_skill": Fraction("0.4"),
}

FULL = Fraction(1)
LISTED_OR_DEMONSTRATED = Fraction("0.7")
IMPLIED = Fraction("0.4")
NONE = Fraction(0)

LISTED_CONTEXTS = frozenset({"skills_section", "summary", "education", "certification", "other"})
DEMONSTRATED_CONTEXTS = frozenset({"project", "experience"})

# Strengths are rounded to this many decimals so stored values recompute exactly.
STRENGTH_DECIMALS = 3
