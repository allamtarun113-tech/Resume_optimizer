from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.api.deps import get_llm_client, get_repository
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.repository import Repository
from app.export.report import build_markdown_report, report_filename
from app.llm.client import LLMClient
from app.orchestrator.pipeline import AnalysisPipeline
from app.parsing.text import normalize_text, text_hash
from app.schemas.advice import Gap, RejectedSuggestion, Suggestion
from app.schemas.analyses import (
    AnalysisCreate,
    AnalysisCreated,
    AnalysisRerun,
    AnalysisResponse,
    AnalysisSummary,
)
from app.schemas.interview import InterviewSet
from app.schemas.learning import LearningPath
from app.schemas.matching import RequirementMatch
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements

router = APIRouter(tags=["analyses"])

HISTORY_LIMIT = 50

User = Annotated[CurrentUser, Depends(get_current_user)]
Repo = Annotated[Repository, Depends(get_repository)]


async def _start_analysis(
    *,
    user: CurrentUser,
    repo: Repository,
    llm: LLMClient,
    settings: Settings,
    background: BackgroundTasks,
    resume_id: str,
    supporting_ids: list[str],
    jd_text: str,
) -> AnalysisCreated:
    jd_text = normalize_text(jd_text)
    jd = await repo.insert_document(
        user_id=user.id,
        kind="jd",
        filename=None,
        storage_path=None,
        extracted_text=jd_text,
        text_hash=text_hash(jd_text),
    )
    analysis = await repo.insert_analysis(
        user_id=user.id,
        resume_doc_id=resume_id,
        jd_doc_id=jd.id,
        supporting_doc_ids=supporting_ids,
    )
    background.add_task(AnalysisPipeline(repo, llm).run, analysis.id, user.id)
    return AnalysisCreated(id=analysis.id, status=analysis.status)


@router.post("/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    body: AnalysisCreate,
    user: User,
    repo: Repo,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> AnalysisCreated:
    resume_id = str(body.resume_doc_id)
    supporting_ids = list(dict.fromkeys(str(i) for i in body.supporting_doc_ids))
    docs = {d.id: d for d in await repo.get_documents(user.id, [resume_id, *supporting_ids])}
    resume = docs.get(resume_id)
    if resume is None or resume.kind != "resume":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found.")
    if any(i not in docs or docs[i].kind != "supporting" for i in supporting_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supporting document not found.")

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
    return await _start_analysis(
        user=user,
        repo=repo,
        llm=llm,
        settings=settings,
        background=background,
        resume_id=resume_id,
        supporting_ids=supporting_ids,
        jd_text=body.jd_text,
    )


@router.post("/analyses/{analysis_id}/rerun", status_code=status.HTTP_202_ACCEPTED)
async def rerun_analysis(
    analysis_id: UUID,
    body: AnalysisRerun,
    user: User,
    repo: Repo,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> AnalysisCreated:
    """Same resume and documents, new job description. Extraction of the profile is
    served from the LLM cache, so only the job side costs anything."""
    previous = await repo.get_analysis(user.id, str(analysis_id))
    if previous is None or previous.resume_doc_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found.")
    ids = [previous.resume_doc_id, *previous.supporting_doc_ids]
    present = {d.id for d in await repo.get_documents(user.id, ids)}
    if previous.resume_doc_id not in present:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The resume for this analysis was deleted.")
    return await _start_analysis(
        user=user,
        repo=repo,
        llm=llm,
        settings=settings,
        background=background,
        resume_id=previous.resume_doc_id,
        supporting_ids=[i for i in previous.supporting_doc_ids if i in present],
        jd_text=body.jd_text,
    )


@router.get("/analyses")
async def list_analyses(user: User, repo: Repo) -> list[AnalysisSummary]:
    analyses = await repo.list_analyses(user.id, HISTORY_LIMIT)
    titles = await repo.get_role_titles([a.id for a in analyses])
    return [
        AnalysisSummary(
            id=a.id,
            status=a.status,
            created_at=a.created_at,
            fit_score=a.fit_score,
            potential_score=a.potential_score,
            role_title=titles.get(a.id, (None, None))[0],
            company=titles.get(a.id, (None, None))[1],
        )
        for a in analyses
    ]


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(analysis_id: UUID, user: User, repo: Repo) -> None:
    if not await repo.delete_analysis(user.id, str(analysis_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found.")


@router.get("/analyses/{analysis_id}/export", response_class=PlainTextResponse)
async def export_analysis(analysis_id: UUID, user: User, repo: Repo) -> PlainTextResponse:
    """The full report as Markdown (download)."""
    analysis = await load_analysis(analysis_id, user, repo)
    if analysis.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "The analysis hasn't finished yet.")
    stored = await repo.get_interview_set(analysis.id)
    interview = InterviewSet.model_validate(stored) if stored else None
    return PlainTextResponse(
        build_markdown_report(analysis, interview),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_filename(analysis)}"'},
    )


async def load_analysis(analysis_id: UUID, user: CurrentUser, repo: Repository) -> AnalysisResponse:
    analysis = await repo.get_analysis(user.id, str(analysis_id))
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found.")
    results = await repo.get_analysis_results(analysis.id) or {}
    profile = results.get("student_profile")
    requirements = results.get("job_requirements")
    matches = results.get("matches")
    advice = results.get("suggestions") or {}
    gaps = results.get("gaps")
    learning_path = results.get("learning_path")
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
        suggestions=[Suggestion.model_validate(x) for x in advice.get("suggestions", [])]
        if gaps is not None
        else None,
        rejected_suggestions=[
            RejectedSuggestion.model_validate(x) for x in advice.get("rejected", [])
        ]
        if gaps is not None
        else None,
        gaps=[Gap.model_validate(g) for g in gaps] if gaps is not None else None,
        learning_path=LearningPath.model_validate(learning_path) if learning_path else None,
        llm_usage=await repo.get_llm_usage(analysis.id),
    )


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: UUID, user: User, repo: Repo) -> AnalysisResponse:
    return await load_analysis(analysis_id, user, repo)
