from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.interview_prep import InterviewPrep, InterviewPrepInput
from app.api.deps import get_embedder, get_llm_client, get_repository
from app.core.auth import CurrentUser, get_current_user
from app.db.repository import Repository
from app.llm.client import LLMClient
from app.mcp_server.server import create_mcp_server, open_tools
from app.rag.embeddings import Embedder
from app.schemas.interview import INTERVIEW_SET_VERSION, InterviewSet
from app.schemas.matching import RequirementMatch
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements
from app.skills.taxonomy import load_taxonomy

router = APIRouter(tags=["interview"])

User = Annotated[CurrentUser, Depends(get_current_user)]
Repo = Annotated[Repository, Depends(get_repository)]


async def _current_set(repo: Repository, analysis_id: str) -> InterviewSet | None:
    """The stored set, unless it was made by an older (smaller) version."""
    stored = await repo.get_interview_set(analysis_id)
    if stored is None:
        return None
    interview = InterviewSet.model_validate(stored)
    return interview if interview.version == INTERVIEW_SET_VERSION else None


async def _own_analysis_id(repo: Repository, user: CurrentUser, analysis_id: UUID) -> str:
    analysis = await repo.get_analysis(user.id, str(analysis_id))
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found.")
    if analysis.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "The analysis hasn't finished yet.")
    return analysis.id


@router.get("/analyses/{analysis_id}/interview")
async def get_interview(analysis_id: UUID, user: User, repo: Repo) -> InterviewSet:
    aid = await _own_analysis_id(repo, user, analysis_id)
    current = await _current_set(repo, aid)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No interview set yet.")
    return current


@router.post("/analyses/{analysis_id}/interview")
async def prepare_interview(
    analysis_id: UUID,
    user: User,
    repo: Repo,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> InterviewSet:
    """ "Prepare Me for Interview". Idempotent: returns the stored set if there is one
    (a set from an older version is regenerated and replaced)."""
    aid = await _own_analysis_id(repo, user, analysis_id)
    outdated = await repo.get_interview_set(aid) is not None
    current = await _current_set(repo, aid)
    if current is not None:
        return current

    results = await repo.get_analysis_results(aid) or {}
    if not results.get("student_profile") or not results.get("job_requirements"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This analysis has no extracted data.")

    taxonomy = load_taxonomy()
    server = create_mcp_server(lambda: repo, taxonomy, lambda: embedder)
    prep = InterviewPrep(llm, taxonomy, lambda: open_tools(server))
    interview = await prep.run(
        InterviewPrepInput(
            analysis_id=aid,
            profile=StudentProfile.model_validate(results["student_profile"]),
            requirements=JobRequirements.model_validate(results["job_requirements"]),
            matches=[RequirementMatch.model_validate(m) for m in results.get("matches") or []],
        ),
        user_id=user.id,
    )
    await repo.save_interview_set(aid, interview.model_dump(mode="json"), replace=outdated)
    # If two requests raced, both return whichever set was stored first.
    return InterviewSet.model_validate(await repo.get_interview_set(aid) or interview.model_dump())
