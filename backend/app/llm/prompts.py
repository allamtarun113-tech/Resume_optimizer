"""Versioned prompt files in app/agents/prompts/*.md.

Each file starts with a front-matter block holding its version:

    ---
    version: 1
    ---
    <instructions>

Changing a prompt means bumping its version, which also invalidates cached LLM results.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "agents" / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str


def parse_prompt(name: str, raw: str) -> Prompt:
    lines = raw.strip().split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Prompt {name!r} is missing its front-matter block")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"Prompt {name!r} front matter is not closed") from exc

    meta = dict(line.split(":", 1) for line in lines[1:end] if ":" in line)
    version = meta.get("version", "").strip()
    if not version:
        raise ValueError(f"Prompt {name!r} has no version")
    return Prompt(name=name, version=version, text="\n".join(lines[end + 1 :]).strip())


@cache
def load_prompt(name: str) -> Prompt:
    return parse_prompt(name, (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"))
