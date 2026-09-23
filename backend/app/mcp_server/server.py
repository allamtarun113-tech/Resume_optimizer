"""Our MCP server (FastMCP): learning resources, the skill prerequisite graph, and the
interview question bank (vector search over the ingested corpus + project templates).

Agents call it in-process through `McpTools` (an MCP client over the in-memory transport),
so data sources stay swappable. The same server is mounted at /mcp over HTTP, behind a
service token, for debugging from Claude Desktop or other MCP clients.
"""

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol
from urllib.parse import urlparse

from fastmcp import Client, FastMCP
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from app.rag.embeddings import Embedder
from app.rag.templates import load_background_templates, load_templates, matching_templates
from app.schemas.interview import BackgroundTemplate, BankQuestion, ProjectTemplate
from app.schemas.learning import LearningResource
from app.skills.taxonomy import Taxonomy

MAX_RESOURCES_PER_SKILL = 3
MAX_YOUTUBE_PER_SKILL = 2
_LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


class ToolStore(Protocol):
    async def get_learning_resources(self, skill_ids: list[str]) -> list[LearningResource]: ...

    async def match_interview_questions(
        self,
        embedding: list[float],
        *,
        k: int,
        category: str | None,
        topics: list[str] | None,
        role_tags: list[str] | None,
    ) -> list[BankQuestion]: ...

    async def list_bank_questions(self, categories: list[str]) -> list[BankQuestion]: ...


class QuestionsResult(BaseModel):
    questions: list[BankQuestion]


class TemplatesResult(BaseModel):
    templates: list[ProjectTemplate]


class BackgroundTemplatesResult(BaseModel):
    templates: list[BackgroundTemplate]


class ResourcesResult(BaseModel):
    resources: list[LearningResource]


class SkillRef(BaseModel):
    skill_id: str
    name: str


class PrerequisitesResult(BaseModel):
    skill_id: str
    name: str | None  # None when the skill isn't in the taxonomy
    prerequisites: list[SkillRef]


def is_youtube(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def rank_resources(resources: list[LearningResource]) -> list[LearningResource]:
    """Deterministic order per skill: free first, easier first, shorter first, then title."""
    return sorted(
        resources,
        key=lambda r: (
            r.skill_id,
            not r.free,
            _LEVEL_ORDER[r.level],
            r.est_hours if r.est_hours is not None else float("inf"),
            r.title,
            r.url,
        ),
    )


def seeded_order(items: list[BankQuestion], seed: str) -> list[BankQuestion]:
    """Deterministic shuffle: the same seed always gives the same order."""
    return sorted(items, key=lambda q: hashlib.sha256(f"{seed}:{q.id}".encode()).hexdigest())


def create_mcp_server(
    store: Callable[[], ToolStore],
    taxonomy: Taxonomy,
    embedder: Callable[[], Embedder] | None = None,
) -> FastMCP:
    """`store`/`embedder` are called per tool call, so the server can outlive any connection."""
    mcp = FastMCP(
        "resume-optimizer",
        instructions="Curated learning resources, the skill prerequisite graph and an "
        "interview question bank used by Resume Optimizer. Skill ids come from its skills "
        "taxonomy (e.g. 'docker'). Every question carries its source repo and license.",
    )

    @mcp.tool
    async def get_learning_resources(skill_ids: list[str]) -> ResourcesResult:
        """Curated, mostly free learning resources for the given taxonomy skill ids: at
        most 3 per skill (best first), then at most 2 YouTube videos per skill."""
        wanted = sorted(set(skill_ids))
        ranked = rank_resources(await store().get_learning_resources(wanted))
        kept: list[LearningResource] = []
        per_skill: dict[tuple[str, bool], int] = {}
        for youtube in (False, True):
            limit = MAX_YOUTUBE_PER_SKILL if youtube else MAX_RESOURCES_PER_SKILL
            for r in ranked:
                key = (r.skill_id, youtube)
                if is_youtube(r.url) == youtube and per_skill.get(key, 0) < limit:
                    per_skill[key] = per_skill.get(key, 0) + 1
                    kept.append(r)
        return ResourcesResult(resources=kept)

    @mcp.tool
    def get_skill_prerequisites(skill_id: str) -> PrerequisitesResult:
        """Direct prerequisites of a taxonomy skill id."""
        if skill_id not in taxonomy.skills:
            return PrerequisitesResult(skill_id=skill_id, name=None, prerequisites=[])
        return PrerequisitesResult(
            skill_id=skill_id,
            name=taxonomy.name(skill_id),
            prerequisites=[
                SkillRef(skill_id=p, name=taxonomy.name(p))
                for p in taxonomy.prerequisites(skill_id)
            ],
        )

    @mcp.tool
    async def search_interview_questions(
        query: str,
        category: str | None = None,
        topics: list[str] | None = None,
        role_tags: list[str] | None = None,
        k: int = 10,
    ) -> QuestionsResult:
        """Semantic search over the interview question bank with optional filters.
        category: technical | general | personal. topics: taxonomy skill ids."""
        if embedder is None:
            raise ValueError("Question search is not configured on this server")
        [vector] = await embedder().embed([query])
        hits = await store().match_interview_questions(
            vector,
            k=max(1, min(k, 50)),
            category=category,
            topics=topics or None,
            role_tags=role_tags or None,
        )
        return QuestionsResult(questions=hits)

    @mcp.tool
    def get_project_question_templates(project_facets: list[str]) -> TemplatesResult:
        """Deep-dive question templates for a project with these facets (e.g. ["ml",
        "backend"]). Placeholders: {project}, {tech}, {tech2}, {metric}."""
        return TemplatesResult(templates=matching_templates(project_facets, load_templates()))

    @mcp.tool
    def get_background_question_templates() -> BackgroundTemplatesResult:
        """Templates for background questions about the student's own jobs ({role},
        {org}, {tech}), education ({degree}, {field}, {institution}) and certifications
        ({cert})."""
        return BackgroundTemplatesResult(templates=list(load_background_templates()))

    @mcp.tool
    async def get_general_questions(k: int, seed: str) -> QuestionsResult:
        """Behavioral (general) and background (personal) questions, k of each at most,
        sampled deterministically by seed."""
        k = max(1, min(k, 50))
        bank = await store().list_bank_questions(["general", "personal"])
        chosen: list[BankQuestion] = []
        for category in ("general", "personal"):
            items = [q for q in bank if q.category == category]
            chosen += seeded_order(items, seed)[:k]
        return QuestionsResult(questions=chosen)

    return mcp


class McpTools:
    """Typed wrapper over an MCP client session. Open one with `open_tools(server)`."""

    def __init__(self, client: Client[Any]) -> None:
        self._client = client

    async def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await self._client.call_tool(name, args)
        content: dict[str, Any] = result.structured_content or {}
        return content

    async def learning_resources(self, skill_ids: list[str]) -> list[LearningResource]:
        data = await self._call("get_learning_resources", {"skill_ids": skill_ids})
        return ResourcesResult.model_validate(data).resources

    async def prerequisites(self, skill_id: str) -> PrerequisitesResult:
        data = await self._call("get_skill_prerequisites", {"skill_id": skill_id})
        return PrerequisitesResult.model_validate(data)

    async def search_questions(
        self,
        query: str,
        *,
        category: str | None = None,
        topics: list[str] | None = None,
        k: int = 10,
    ) -> list[BankQuestion]:
        data = await self._call(
            "search_interview_questions",
            {"query": query, "category": category, "topics": topics, "k": k},
        )
        return QuestionsResult.model_validate(data).questions

    async def project_templates(self, facets: list[str]) -> list[ProjectTemplate]:
        data = await self._call("get_project_question_templates", {"project_facets": facets})
        return TemplatesResult.model_validate(data).templates

    async def background_templates(self) -> list[BackgroundTemplate]:
        data = await self._call("get_background_question_templates", {})
        return BackgroundTemplatesResult.model_validate(data).templates

    async def general_questions(self, k: int, seed: str) -> list[BankQuestion]:
        data = await self._call("get_general_questions", {"k": k, "seed": seed})
        return QuestionsResult.model_validate(data).questions


@asynccontextmanager
async def open_tools(server: FastMCP) -> AsyncIterator[McpTools]:
    """In-process MCP client session (in-memory transport, no network)."""
    async with Client(server) as client:
        yield McpTools(client)


class BearerTokenGuard:
    """ASGI wrapper: HTTP requests need `Authorization: Bearer <token>`."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            if not hmac.compare_digest(headers.get(b"authorization", b""), self._expected):
                body = json.dumps({"detail": "Invalid or missing service token"}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self._app(scope, receive, send)
