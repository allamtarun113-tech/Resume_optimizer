"""Project deep-dive templates: loading, facet detection and deterministic filling."""

import re
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.schemas.interview import ProjectTemplate
from app.schemas.profile import Project
from app.skills.taxonomy import Taxonomy

TEMPLATES_PATH = Path(__file__).resolve().parent / "data" / "project_templates.yaml"
PLACEHOLDER_RE = re.compile(r"\{(project|tech|tech2|metric)\}")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Taxonomy category -> project facet.
CATEGORY_FACETS = {
    "ml": "ml",
    "data": "data",
    "database": "database",
    "backend": "backend",
    "frontend": "frontend",
    "devops": "deployment",
    "cloud": "deployment",
    "mobile": "mobile",
    "testing": "testing",
    "security": "security",
}


class TemplateFile(BaseModel):
    templates: list[ProjectTemplate]


@cache
def load_templates(path: Path = TEMPLATES_PATH) -> list[ProjectTemplate]:
    data = TemplateFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    ids = [t.id for t in data.templates]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate template ids")
    return data.templates


def project_facets(project: Project, taxonomy: Taxonomy) -> list[str]:
    facets: set[str] = set()
    names = [*project.technologies, project.summary, *project.highlights]
    for name in names:
        ids = taxonomy.find_in_text(name) | ({t} if (t := taxonomy.lookup(name)) else set())
        for skill_id in ids:
            facet = CATEGORY_FACETS.get(taxonomy.skills[skill_id].category)
            if facet:
                facets.add(facet)
    return sorted(facets)


def matching_templates(
    facets: list[str], templates: list[ProjectTemplate]
) -> list[ProjectTemplate]:
    wanted = set(facets) | {"any"}
    return [t for t in templates if wanted & set(t.facets)]


def fill_template(template: ProjectTemplate, project: Project) -> str | None:
    """Deterministic fill; None if the template needs a detail the project doesn't have."""
    values = {
        "project": project.name,
        "tech": project.technologies[0] if project.technologies else None,
        "tech2": project.technologies[1] if len(project.technologies) > 1 else None,
        "metric": project.metrics[0] if project.metrics else None,
    }
    needed = set(PLACEHOLDER_RE.findall(template.text))
    if any(values[n] is None for n in needed):
        return None
    return PLACEHOLDER_RE.sub(lambda m: values[m.group(1)] or "", template.text)


def template_words(template: ProjectTemplate) -> set[str]:
    return set(_WORD_RE.findall(PLACEHOLDER_RE.sub(" ", template.text).lower()))


def is_faithful_fill(question: str, template: ProjectTemplate, project: Project) -> bool:
    """An LLM-filled question must keep most of the template and name the project or its tech."""
    words = set(_WORD_RE.findall(question.lower()))
    fixed = template_words(template)
    kept = len(fixed & words) / len(fixed) if fixed else 1.0
    text = question.lower()
    anchored = project.name.lower() in text or any(
        t.lower() in text for t in project.technologies if len(t) > 1
    )
    return kept >= 0.6 and anchored and 15 <= len(question) <= 400
