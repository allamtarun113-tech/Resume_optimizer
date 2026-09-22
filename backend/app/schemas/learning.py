"""Learning resources (DB rows), the learning path we store, and the planner's LLM schema."""

from typing import Literal

from pydantic import BaseModel, Field

ResourceType = Literal["docs", "course", "video", "book", "practice"]
ResourceLevel = Literal["beginner", "intermediate", "advanced"]


class LearningResource(BaseModel):
    skill_id: str
    title: str
    url: str
    type: ResourceType
    level: ResourceLevel
    est_hours: float | None
    free: bool


class LearningStep(BaseModel):
    step: int  # 1-based position
    skill_id: str | None  # None for gaps the taxonomy doesn't know
    name: str
    kind: Literal["gap", "prerequisite"]
    for_requirements: list[str]  # JD requirements this step works towards
    unlocks: list[str]  # later steps that build on it
    why: str
    resources: list[LearningResource]
    est_hours: float | None


class LearningPath(BaseModel):
    steps: list[LearningStep]
    total_hours: float


# -- LearningPathPlanner LLM output (strict schema: no defaults) ---------------------------


class StepNote(BaseModel):
    step_id: str = Field(description='Step id as given, e.g. "docker".')
    why: str = Field(description="One or two sentences: why learn this now, for this job.")


class PathPlan(BaseModel):
    order: list[str] = Field(
        description="All step ids in the recommended order. Keep every prerequisite "
        "before the steps that need it."
    )
    notes: list[StepNote]
