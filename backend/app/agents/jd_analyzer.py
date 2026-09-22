"""Agent 3: JDAnalyzer (LLM, small). Job description text -> JobRequirements."""

from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.schemas.requirements import JobRequirements, Requirement

MAX_OUTPUT_TOKENS = 6_000


def dedupe_requirements(requirements: list[Requirement]) -> list[Requirement]:
    """Merge repeats of the same requirement, keeping the stricter one, in first-seen order."""
    merged: dict[tuple[str, str], Requirement] = {}
    for req in requirements:
        key = (" ".join(req.name.casefold().split()), req.category)
        current = merged.get(key)
        if current is None:
            merged[key] = req
        elif req.importance == "must" and current.importance == "nice":
            merged[key] = current.model_copy(update={"importance": "must"})
        if current and req.min_years is not None:
            best = merged[key]
            if best.min_years is None or req.min_years > best.min_years:
                merged[key] = best.model_copy(update={"min_years": req.min_years})
    return list(merged.values())


class JDAnalyzer:
    name = "jd_analyzer"
    uses_llm = True

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.prompt = load_prompt(self.name)

    async def run(
        self,
        jd_text: str,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> JobRequirements:
        result = await self._llm.parse(
            agent=self.name,
            prompt=self.prompt,
            input_text=f"<job_description>\n{jd_text}\n</job_description>",
            output_type=JobRequirements,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            analysis_id=analysis_id,
            user_id=user_id,
        )
        return result.model_copy(update={"requirements": dedupe_requirements(result.requirements)})
