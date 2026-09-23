"""Explainer models: "Explain" buttons on the results page."""

from typing import Literal

from pydantic import BaseModel, Field

# What the student clicked. `ref` identifies the item inside the stored analysis:
#   score: ""                  requirement: requirement_index      suggestion: suggestion id
#   learning_step: step number interview_question: "technical:3", "project:0:5", ...
#   ats: "" (the ATS score)    ats_check: check id, e.g. "no_tables"
ExplainKind = Literal[
    "score",
    "requirement",
    "suggestion",
    "learning_step",
    "interview_question",
    "ats",
    "ats_check",
]


class ExplainRequest(BaseModel):
    kind: ExplainKind
    ref: str = Field(default="", max_length=64)


# -- LLM output (strict schema: no defaults) ------------------------------------------------


class Explanation(BaseModel):
    summary: str = Field(
        description="Two or three short, plain-English sentences that answer the question."
    )
    details: list[str] = Field(
        description="Two to four short bullet points with the key facts behind the summary."
    )
    next_steps: list[str] = Field(
        description="One to three concrete things the student can do next. Empty if none."
    )
