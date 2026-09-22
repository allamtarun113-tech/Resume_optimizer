from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_llm_client, get_repository
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.repository import Repository
from app.llm.client import LLMClient
from app.orchestrator.pipeline import AnalysisPipeline
from app.parsing.text import normalize_text, text_hash
from app.schemas.analyses import AnalysisCreate, AnalysisCreated, AnalysisResponse
from app.schemas.matching import RequirementMatch
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements

router = APIRouter(tags=["analyses"])

User = Annotated[CurrentUser, Depends(get_current_user)]
Repo = Annotated[Repository, Depends(get_repository)]


@router.post("/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    body: AnalysisCreate,
    user: User,
    repo: Repo,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> AnalysisCreated:
    since = datetime.now(UTC) - timedelta(days=1)
    if await repo.count_analyses_since(user.id, since) >= settings.daily_analysis_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've reached the limit of {settings.daily_analysis_limit} analyses per day.",
        )

    resume_id = str(body.resume_doc_id)
    supporting_ids = list(dict.fromkeys(str(i) for i in body.supporting_doc_ids))
    docs = {d.id: d for d in await repo.get_documents(user.id, [resume_id, *supporting_ids])}
    resume = docs.get(resume_id)
    if resume is None or resume.kind != "resume":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found.")
    if any(i not in docs or docs[i].kind != "supporting" for i in supporting_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supporting document not found.")

    jd_text = normalize_text(body.jd_text)
    jd = await repo.insert_document(
        user_id=user.id,
        kind="jd",
        filename=None,
        storage_path=None,
        extracted_text=jd_text,
        text_hash=text_hash(jd_text),
    )
    extra_text = normalize_text(body.extra_text or "")
    if extra_text:
        extra = await repo.insert_document(
            user_id=user.id,
            kind="extra_text",
            filename=None,
            storage_path=None,
            extracted_text=extra_text,
            text_hash=text_hash(extra_text),
        )
        supporting_ids.append(extra.id)

    analysis = await repo.insert_analysis(
        user_id=user.id,
        resume_doc_id=resume_id,
        jd_doc_id=jd.id,
        supporting_doc_ids=supporting_ids,
    )
    background.add_task(AnalysisPipeline(repo, llm).run, analysis.id, user.id)
    return AnalysisCreated(id=analysis.id, status=analysis.status)


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: UUID, user: User, repo: Repo) -> AnalysisResponse:
    analysis = await repo.get_analysis(user.id, str(analysis_id))
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found.")
    results = await repo.get_analysis_results(analysis.id) or {}
    profile = results.get("student_profile")
    requirements = results.get("job_requirements")
    matches = results.get("matches")
    return AnalysisResponse(
        id=analysis.id,
        status=analysis.status,
        error=analysis.error,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        prompt_versions=analysis.prompt_versions,
        fit_score=analysis.fit_score,
        potential_score=analysis.potential_score,
        scoring_version=analysis.scoring_version,
        student_profile=StudentProfile.model_validate(profile) if profile else None,
        job_requirements=JobRequirements.model_validate(requirements) if requirements else None,
        matches=[RequirementMatch.model_validate(m) for m in matches] if matches else None,
        llm_usage=await repo.get_llm_usage(analysis.id),
    )
