"""Our MCP server (FastMCP): curated learning resources and the skill prerequisite graph.

Agents call it in-process through `McpTools` (an MCP client over the in-memory transport),
so data sources stay swappable. The same server is mounted at /mcp over HTTP, behind a
service token, for debugging from Claude Desktop or other MCP clients. Phase 5 adds the
interview-question tools here.
"""

import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastmcp import Client, FastMCP
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from app.schemas.learning import LearningResource
from app.skills.taxonomy import Taxonomy

MAX_RESOURCES_PER_SKILL = 3
_LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


class ResourceStore(Protocol):
    async def get_learning_resources(self, skill_ids: list[str]) -> list[LearningResource]: ...


class ResourcesResult(BaseModel):
    resources: list[LearningResource]


class SkillRef(BaseModel):
    skill_id: str
    name: str


class PrerequisitesResult(BaseModel):
    skill_id: str
    name: str | None  # None when the skill isn't in the taxonomy
    prerequisites: list[SkillRef]


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


def create_mcp_server(store: Callable[[], ResourceStore], taxonomy: Taxonomy) -> FastMCP:
    """`store` is called per tool call, so the server can outlive any one connection."""
    mcp = FastMCP(
        "resume-optimizer",
        instructions="Curated learning resources and the skill prerequisite graph used by "
        "Resume Optimizer. Skill ids come from its skills taxonomy (e.g. 'docker').",
    )

    @mcp.tool
    async def get_learning_resources(skill_ids: list[str]) -> ResourcesResult:
        """Curated, mostly free learning resources for the given taxonomy skill ids
        (at most 3 per skill, best first)."""
        wanted = sorted(set(skill_ids))
        ranked = rank_resources(await store().get_learning_resources(wanted))
        kept: list[LearningResource] = []
        per_skill: dict[str, int] = {}
        for r in ranked:
            if per_skill.get(r.skill_id, 0) < MAX_RESOURCES_PER_SKILL:
                per_skill[r.skill_id] = per_skill.get(r.skill_id, 0) + 1
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
