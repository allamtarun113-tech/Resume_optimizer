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
# 3: combined skills count as each part ("Data structures and algorithms" = algorithms);
#    the LLM matcher can't link a known skill to an unrelated known requirement.
# 4: JD lists of skills that are all wanted are split into one requirement each; skills
#    written in a document but skipped by the LLM are added from the taxonomy.
# 5: a language/tool/database/cloud requirement ("GitHub", "MySQL") only counts a project
#    or job the LLM cites if its text names that skill (or one implying it).
# 6: adds the ATS score (ATS_VERSION) and the final score (job fit and ATS combined).
SCORING_VERSION = "6"

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

# -- ATS check and final score -------------------------------------------------------------
# The ATS score (0-100) says how well an applicant tracking system can read the resume and
# find the job's keywords in it. Each check earns up to its points; the score is the share
# of points earned over the checks that apply (layout checks need the PDF/DOCX file).
ATS_VERSION = "1"
ATS_POINTS: dict[str, int] = {
    # Can an ATS read it?
    "readable_text": 12,
    "single_column": 10,
    "no_tables": 8,
    "no_graphics": 5,
    "contact_in_body": 5,  # DOCX only: contact details in the page header/footer
    "page_count": 3,
    # Sections and contact details
    "standard_headings": 10,
    "contact_details": 8,
    "profile_links": 4,
    "date_format": 4,
    "personal_details": 5,
    "length": 3,
    # Job keywords, word for word
    "keywords": 25,
}
# Share of a check's points earned for a warning (the rest of the rules are in scoring/ats.py).
ATS_TABLE_SHARE = Fraction(1, 4)
ATS_GRAPHICS_SHARE = Fraction(1, 2)
ATS_PARTIAL_SHARE = Fraction(1, 2)
ATS_HIDDEN_LINK_SHARE = Fraction(1, 4)
ATS_LONG_RESUME_SHARE = Fraction(1, 3)
ATS_UNREADABLE_OK = Fraction(2, 1000)  # share of characters an ATS can't read
ATS_UNREADABLE_WARN = Fraction(2, 100)
ATS_MIN_WORDS = 200
ATS_MAX_WORDS = 1000
ATS_MAX_PAGES = 2
ATS_KEYWORDS_PASS = Fraction(8, 10)
ATS_KEYWORDS_WARN = Fraction(4, 10)
ATS_REQUIRED_SECTIONS = (("education",), ("skills",), ("experience", "projects"))

# Final score = the one number shown first: mostly job fit, partly ATS readability.
FINAL_FIT_WEIGHT = Fraction(7, 10)
FINAL_ATS_WEIGHT = Fraction(3, 10)
