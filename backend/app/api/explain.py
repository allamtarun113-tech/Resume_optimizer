from typing import Annotated
from uuid import UUID

import openai
from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.explainer import Explainer, ExplainNotFound
from app.api.analyses import load_analysis
from app.api.deps import get_llm_client, get_repository
from app.core.auth import CurrentUser, get_current_user
from app.db.repository import Repository
from app.llm.client import LLMClient, LLMError
from app.orchestrator.pipeline import user_message
from app.schemas.explain import ExplainRequest, Explanation
from app.schemas.interview import InterviewSet

router = APIRouter(tags=["explain"])


@router.post("/analyses/{analysis_id}/explain")
async def explain(
    analysis_id: UUID,
    body: ExplainRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repo: Annotated[Repository, Depends(get_repository)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> Explanation:
    """Plain-English explanation of one item on the results page (cached per item)."""
    analysis = await load_analysis(analysis_id, user, repo)
    if analysis.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "The analysis hasn't finished yet.")
    interview = None
    if body.kind == "interview_question":
        stored = await repo.get_interview_set(analysis.id)
        interview = InterviewSet.model_validate(stored) if stored else None
    try:
        return await Explainer(llm).run(
            analysis, body.kind, body.ref, interview=interview, user_id=user.id
        )
    except ExplainNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except (LLMError, openai.OpenAIError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, user_message(e)) from e
