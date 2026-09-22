"""Analysis pipeline. Runs as a background task and records progress in analyses.status.

Parser (at upload) -> ProfileExtractor || JDAnalyzer -> SkillNormalizer -> Matcher ->
Scorer (+ GapClassifier) -> store results and scores.
"""

import asyncio
import logging

import openai

from app.agents.jd_analyzer import JDAnalyzer
from app.agents.matcher import Matcher
from app.agents.profile_extractor import ProfileExtractor, ProfileExtractorInput, SourceDocument
from app.agents.scorer import Scorer
from app.agents.skill_normalizer import SkillNormalizer
from app.db.repository import Repository
from app.llm.client import LLMClient, LLMError
from app.parsing.extract import ExtractionError
from app.schemas.documents import DocumentRecord
from app.skills.taxonomy import load_taxonomy

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Expected failure with a message that is safe to show users."""


def user_message(exc: Exception) -> str:
    if isinstance(exc, PipelineError | LLMError | ExtractionError):
        return str(exc)
    if isinstance(exc, openai.RateLimitError) and exc.code == "insufficient_quota":
        return "The server's OpenAI account has run out of credit. Please try again later."
    if isinstance(exc, openai.RateLimitError):
        return "The AI service is busy right now. Please try again in a minute."
    if isinstance(exc, openai.APIError):
        return "The AI service returned an error. Please try again."
    return "Something went wrong while analyzing. Please try again."


def _source(doc: DocumentRecord) -> SourceDocument:
    return SourceDocument(
        doc_id=doc.id, text=doc.extracted_text or "", text_hash=doc.text_hash or ""
    )


class AnalysisPipeline:
    def __init__(self, repo: Repository, llm: LLMClient) -> None:
        self._repo = repo
        self._profile_extractor = ProfileExtractor(llm)
        self._jd_analyzer = JDAnalyzer(llm)
        taxonomy = load_taxonomy()
        self._normalizer = SkillNormalizer(taxonomy)
        self._matcher = Matcher(llm, taxonomy)
        self._scorer = Scorer()

    @property
    def prompt_versions(self) -> dict[str, str]:
        return {
            self._profile_extractor.name: self._profile_extractor.prompt.version,
            self._jd_analyzer.name: self._jd_analyzer.prompt.version,
            self._matcher.name: self._matcher.prompt.version,
        }

    async def run(self, analysis_id: str, user_id: str) -> None:
        try:
            await self._run(analysis_id, user_id)
        except Exception as exc:
            logger.exception("Analysis %s failed", analysis_id)
            try:
                await self._repo.update_analysis(
                    analysis_id, status="failed", error=user_message(exc)
                )
            except Exception:
                logger.exception("Could not mark analysis %s as failed", analysis_id)

    async def _run(self, analysis_id: str, user_id: str) -> None:
        await self._repo.update_analysis(analysis_id, status="parsing")
        analysis = await self._repo.get_analysis(user_id, analysis_id)
        if analysis is None or analysis.resume_doc_id is None or analysis.jd_doc_id is None:
            raise PipelineError("This analysis is missing its resume or job description.")

        ids = [analysis.resume_doc_id, analysis.jd_doc_id, *analysis.supporting_doc_ids]
        docs = {d.id: d for d in await self._repo.get_documents(user_id, ids)}
        resume, jd = docs.get(analysis.resume_doc_id), docs.get(analysis.jd_doc_id)
        if resume is None or jd is None:
            raise PipelineError("The resume or job description was deleted.")
        supplementary = [_source(docs[i]) for i in analysis.supporting_doc_ids if i in docs]

        await self._repo.update_analysis(
            analysis_id, status="extracting", prompt_versions=self.prompt_versions
        )
        profile, requirements = await asyncio.gather(
            self._profile_extractor.run(
                ProfileExtractorInput(resume=_source(resume), supplementary=supplementary),
                analysis_id=analysis_id,
                user_id=user_id,
            ),
            self._jd_analyzer.run(
                jd.extracted_text or "", analysis_id=analysis_id, user_id=user_id
            ),
        )
        await self._repo.save_analysis_results(
            analysis_id,
            student_profile=profile.model_dump(mode="json"),
            job_requirements=requirements.model_dump(mode="json"),
        )

        await self._repo.update_analysis(analysis_id, status="scoring")
        normalized = self._normalizer.run(profile, requirements)
        evidence = await self._matcher.run(
            profile, requirements, normalized, analysis_id=analysis_id, user_id=user_id
        )
        score = self._scorer.run(requirements, evidence, profile, as_of=analysis.created_at.date())
        await self._repo.save_analysis_results(
            analysis_id, matches=[m.model_dump(mode="json") for m in score.matches]
        )
        await self._repo.update_analysis(
            analysis_id,
            status="done",
            error=None,
            fit_score=score.fit_score,
            potential_score=score.potential_score,
            scoring_version=score.scoring_version,
        )
