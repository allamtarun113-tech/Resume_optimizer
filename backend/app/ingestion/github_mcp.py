"""Fetch question files through the official GitHub MCP server (remote, read-only mode).

Needs GITHUB_PERSONAL_ACCESS_TOKEN (a fine-grained token with public-repo read access).
"""

import os
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

GITHUB_MCP_URL = os.environ.get("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/readonly")


class GitHubMcpError(RuntimeError):
    pass


def _texts(result: Any) -> list[str]:
    """All text payloads in a tool result (plain text or embedded resources)."""
    texts: list[str] = []
    for item in getattr(result, "content", None) or []:
        if text := getattr(item, "text", None):
            texts.append(text)
        resource = getattr(item, "resource", None)
        if resource is not None and (text := getattr(resource, "text", None)):
            texts.append(text)
    return texts


class GitHubFiles:
    """`async with GitHubFiles(token) as gh: text = await gh.read(owner, repo, path, ref)`."""

    def __init__(self, token: str, url: str = GITHUB_MCP_URL) -> None:
        if not token:
            raise GitHubMcpError("Set GITHUB_PERSONAL_ACCESS_TOKEN in backend/.env")
        transport = StreamableHttpTransport(url, headers={"Authorization": f"Bearer {token}"})
        self._client: Client[Any] = Client(transport)
        self._entered = False

    async def __aenter__(self) -> "GitHubFiles":
        await self._client.__aenter__()  # type: ignore[no-untyped-call]
        tools = {t.name for t in await self._client.list_tools()}
        if "get_file_contents" not in tools:
            raise GitHubMcpError(f"GitHub MCP server has no get_file_contents tool: {tools}")
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)  # type: ignore[no-untyped-call]

    async def read(self, owner: str, repo: str, path: str, ref: str) -> str:
        result = await self._client.call_tool(
            "get_file_contents",
            {"owner": owner, "repo": repo, "path": path, "ref": f"refs/heads/{ref}"},
            raise_on_error=False,
        )
        if result.is_error:
            raise GitHubMcpError(f"{owner}/{repo}/{path}: {' '.join(_texts(result))[:300]}")
        texts = _texts(result)
        if not texts:
            raise GitHubMcpError(f"{owner}/{repo}/{path}: empty response")
        # The file body is the largest payload; the rest are status messages.
        return max(texts, key=len)
