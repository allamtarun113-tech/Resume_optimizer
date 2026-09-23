"""Agent 5: Matcher (minimal LLM). Finds the student's evidence for each requirement.

Order: taxonomy id match (direct, then "implies" edges) -> fuzzy name match -> batched
EvidenceMatcher LLM calls for everything still without direct evidence (domains, soft
skills, education, experience, and skills the taxonomy doesn't know): one call over the
resume's evidence and one over the supplementary evidence, so the resume's judgements
depend only on the resume.
"""

import asyncio

from rapidfuzz import fuzz

from app.agents.skill_normalizer import NormalizedSkills
from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.schemas.matching import (
    EvidenceJudgements,
    EvidenceRef,
    MatchMethod,
    RequirementEvidence,
)
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements, Requirement
from app.skills.taxonomy import Taxonomy, skill_key

MAX_OUTPUT_TOKENS = 6_000
NAME_FUZZY_CUTOFF = 92
MAX_DETAIL_CHARS = 300
# Requirements naming a specific product (a language, tool, database or cloud) need
# evidence that names it: a job description can't show GitHub or MySQL unless it says so.
NAMED_CATEGORIES = frozenset({"language", "tool", "database", "cloud"})
GENERIC_NAMED_IDS = frozenset(
    {"cloud-computing", "serverless", "command-line", "rpa", "vector-databases"}
)


def _clip(text: str, limit: int = MAX_DETAIL_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class EvidenceCatalog:
    """Numbered evidence items for the LLM prompt, and their mapping back to EvidenceRefs.

    `sources` limits the catalog to evidence from those documents ("resume" or
    "supplementary"); refs keep their index in the full profile."""

    def __init__(
        self, profile: StudentProfile, sources: tuple[str, ...] = ("resume", "supplementary")
    ) -> None:
        self.lines: list[str] = []
        self._refs: dict[str, list[EvidenceRef]] = {}

        def keep(source: str) -> bool:
            return ("resume" if source == "resume" else "supplementary") in sources

        skill_groups: dict[str, str] = {}  # skill_key -> catalog id
        for i, m in enumerate(profile.skills):
            if not keep(m.source):
                continue
            ref = skill_ref(profile, i, direct=True)
            key = skill_key(m.name)
            if key not in skill_groups:
                skill_groups[key] = self._add("K", f"skill: {m.name}")
            self._refs[skill_groups[key]].append(ref)

        for i, p in enumerate(profile.projects):
            if not keep(p.source):
                continue
            detail = f"{p.summary} Tech: {', '.join(p.technologies)}. {' '.join(p.highlights)}"
            cid = self._add("P", f"project: {p.name} — {_clip(detail)}")
            self._refs[cid].append(project_ref(profile, i, direct=True))
        for i, x in enumerate(profile.experience):
            if not keep(x.source):
                continue
            dates = f"{x.start or '?'} to {x.end or '?'}, {x.employment_type}"
            detail = f"Tech: {', '.join(x.technologies)}. {' '.join(x.highlights)}"
            cid = self._add("X", f"job: {x.title} at {x.organization} ({dates}) — {_clip(detail)}")
            self._refs[cid].append(experience_ref(profile, i, direct=True))
        for i, e in enumerate(profile.education):
            if not keep(e.source):
                continue
            parts = [e.degree, e.field_of_study, e.institution, e.grade]
            cid = self._add("E", "education: " + ", ".join(p for p in parts if p))
            self._refs[cid].append(
                EvidenceRef(
                    kind="education",
                    index=i,
                    context="education",
                    source=e.source,
                    label=e.degree or e.institution,
                    snippet=e.evidence,
                    direct=True,
                )
            )
        for i, c in enumerate(profile.certifications):
            if not keep(c.source):
                continue
            issuer = f" ({c.issuer})" if c.issuer else ""
            cid = self._add("C", f"certification: {c.name}{issuer}")
            self._refs[cid].append(
                EvidenceRef(
                    kind="certification",
                    index=i,
                    context="certification",
                    source=c.source,
                    label=c.name,
                    snippet=c.evidence,
                    direct=True,
                )
            )

    def _add(self, prefix: str, text: str) -> str:
        count = sum(1 for k in self._refs if k.startswith(prefix))
        cid = f"{prefix}{count + 1}"
        self._refs[cid] = []
        self.lines.append(f"{cid} {text}")
        return cid

    def refs(self, catalog_id: str, *, direct: bool) -> list[EvidenceRef]:
        return [
            r.model_copy(update={"direct": direct})
            for r in self._refs.get(catalog_id.strip().upper(), [])
        ]


def skill_ref(profile: StudentProfile, i: int, *, direct: bool) -> EvidenceRef:
    m = profile.skills[i]
    return EvidenceRef(
        kind="skill",
        index=i,
        context=m.context,
        source=m.source,
        label=m.name,
        snippet=m.evidence,
        direct=direct,
    )


def project_ref(profile: StudentProfile, i: int, *, direct: bool) -> EvidenceRef:
    p = profile.projects[i]
    return EvidenceRef(
        kind="project",
        index=i,
        context="project",
        source=p.source,
        label=p.name,
        snippet=p.evidence,
        direct=direct,
    )


def experience_ref(profile: StudentProfile, i: int, *, direct: bool) -> EvidenceRef:
    x = profile.experience[i]
    return EvidenceRef(
        kind="experience",
        index=i,
        context="experience",
        source=x.source,
        label=f"{x.title} at {x.organization}",
        snippet=x.evidence,
        direct=direct,
    )


def _dedupe(refs: list[EvidenceRef]) -> list[EvidenceRef]:
    """Keep one ref per evidence item, preferring direct ones."""
    best: dict[tuple[str, int], EvidenceRef] = {}
    for ref in refs:
        key = (ref.kind, ref.index)
        if key not in best or (ref.direct and not best[key].direct):
            best[key] = ref
    return list(best.values())


class Matcher:
    name = "evidence_matcher"
    uses_llm = True

    def __init__(self, llm: LLMClient, taxonomy: Taxonomy) -> None:
        self._llm = llm
        self._taxonomy = taxonomy
        self.prompt = load_prompt(self.name)

    def taxonomy_refs(
        self, skill_id: str, profile: StudentProfile, normalized: NormalizedSkills
    ) -> list[EvidenceRef]:
        """Evidence whose canonical ids are skill_id (direct) or imply it (not direct)."""
        refs: list[EvidenceRef] = []
        groups = (
            (normalized.mention_ids, skill_ref),
            (normalized.project_ids, project_ref),
            (normalized.experience_ids, experience_ref),
        )
        for ids_per_item, make_ref in groups:
            for i, ids in enumerate(ids_per_item):
                if skill_id in ids:
                    refs.append(make_ref(profile, i, direct=True))
                elif any(skill_id in self._taxonomy.implied_by(sid) for sid in ids):
                    refs.append(make_ref(profile, i, direct=False))
        return _dedupe(refs)

    @staticmethod
    def name_refs(requirement: Requirement, profile: StudentProfile) -> list[EvidenceRef]:
        key = skill_key(requirement.name)
        return [
            skill_ref(profile, i, direct=True)
            for i, m in enumerate(profile.skills)
            if fuzz.ratio(key, skill_key(m.name)) >= NAME_FUZZY_CUTOFF
        ]

    async def run(
        self,
        profile: StudentProfile,
        requirements: JobRequirements,
        normalized: NormalizedSkills,
        *,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> list[RequirementEvidence]:
        results: list[RequirementEvidence] = []
        pending: list[int] = []  # no direct evidence anywhere yet
        pending_resume: list[int] = []  # no direct evidence in the resume yet
        for i, req in enumerate(requirements.requirements):
            skill_id = normalized.requirement_ids[i]
            method: MatchMethod
            alternatives = normalized.requirement_alternatives[i]
            if skill_id:
                refs, method = self.taxonomy_refs(skill_id, profile, normalized), "taxonomy"
            elif alternatives:
                # Any one alternative satisfies the requirement.
                refs = _dedupe(
                    [r for a in alternatives for r in self.taxonomy_refs(a, profile, normalized)]
                )
                method = "taxonomy"
            else:
                refs, method = self.name_refs(req, profile), "fuzzy"
            has_direct = any(r.direct for r in refs)
            results.append(
                RequirementEvidence(
                    requirement_index=i,
                    skill_id=skill_id,
                    method=method if has_direct else ("implied" if refs else "none"),
                    evidence=refs,
                )
            )
            # Experience requirements need judgement about which jobs are relevant.
            experience = req.category == "experience"
            if experience or not has_direct:
                pending.append(i)
            if experience or not any(r.direct and r.source == "resume" for r in refs):
                pending_resume.append(i)

        # Resume evidence and supplementary evidence are judged in separate calls, so the
        # resume's judgements (and the job fit score) never change with the other documents.
        catalogs = [
            (EvidenceCatalog(profile, ("resume",)), pending_resume),
            (EvidenceCatalog(profile, ("supplementary",)), pending),
        ]
        asks = [(c, idx) for c, idx in catalogs if c.lines and idx]
        answers = await asyncio.gather(
            *(self._ask(requirements, c, idx, analysis_id, user_id) for c, idx in asks)
        )
        for (catalog, idx), judged in zip(asks, answers, strict=True):
            self._apply(judged, catalog, idx, results, profile, normalized)
        return results

    def _names_it(
        self,
        ref: EvidenceRef,
        known: set[str],
        profile: StudentProfile,
        normalized: NormalizedSkills,
    ) -> bool:
        """Whether a project or job names one of the `known` skills (or one implying it)."""
        if ref.kind == "project":
            p = profile.projects[ref.index]
            ids = set(normalized.project_ids[ref.index])
            text = " ".join([p.name, p.summary, *p.technologies, *p.highlights, p.evidence])
        else:
            x = profile.experience[ref.index]
            ids = set(normalized.experience_ids[ref.index])
            text = " ".join([x.title, *x.technologies, *x.highlights, x.evidence])
        ids |= self._taxonomy.find_in_text(text)
        return any(sid in known or known & self._taxonomy.implied_by(sid) for sid in ids)

    def _contradicts_taxonomy(
        self, ref: EvidenceRef, known: set[str], normalized: NormalizedSkills
    ) -> bool:
        """A skill the taxonomy knows can only support a known requirement through the
        taxonomy (same id or `implies`). Stops the LLM linking unrelated skills, e.g.
        "Linear algebra" as evidence for "Algorithms"."""
        if ref.kind != "skill":
            return False
        ids = normalized.mention_ids[ref.index]
        return bool(ids) and not any(
            sid in known or known & self._taxonomy.implied_by(sid) for sid in ids
        )

    def _is_named(self, known: set[str]) -> bool:
        return all(
            self._taxonomy.skills[sid].category in NAMED_CATEGORIES and sid not in GENERIC_NAMED_IDS
            for sid in known
        )

    async def _ask(
        self,
        requirements: JobRequirements,
        catalog: EvidenceCatalog,
        pending: list[int],
        analysis_id: str | None,
        user_id: str | None,
    ) -> EvidenceJudgements:
        req_lines = []
        for i in pending:
            req = requirements.requirements[i]
            req_lines.append(f'R{i + 1} [{req.category}] {req.name} — "{_clip(req.evidence)}"')
        input_text = (
            "<requirements>\n" + "\n".join(req_lines) + "\n</requirements>\n\n"
            "<evidence>\n" + "\n".join(catalog.lines) + "\n</evidence>"
        )
        return await self._llm.parse(
            agent=self.name,
            prompt=self.prompt,
            input_text=input_text,
            output_type=EvidenceJudgements,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            analysis_id=analysis_id,
            user_id=user_id,
        )

    def _apply(
        self,
        judged: EvidenceJudgements,
        catalog: EvidenceCatalog,
        pending: list[int],
        results: list[RequirementEvidence],
        profile: StudentProfile,
        normalized: NormalizedSkills,
    ) -> None:
        allowed = set(pending)
        for judgement in judged.judgements:
            try:
                index = int(judgement.requirement_id.strip().upper().removeprefix("R")) - 1
            except ValueError:
                continue
            if index not in allowed or judgement.relation == "none":
                continue
            direct = judgement.relation == "direct"
            refs = [r for cid in judgement.evidence_ids for r in catalog.refs(cid, direct=direct)]
            known = {
                i
                for i in (
                    normalized.requirement_ids[index],
                    *normalized.requirement_alternatives[index],
                )
                if i
            }
            if known:
                refs = [r for r in refs if not self._contradicts_taxonomy(r, known, normalized)]
                if self._is_named(known):
                    refs = [
                        r
                        for r in refs
                        if r.kind not in ("project", "experience")
                        or self._names_it(r, known, profile, normalized)
                    ]
            if not refs:
                continue
            current = results[index]
            merged = _dedupe(current.evidence + refs)
            results[index] = current.model_copy(
                update={
                    "evidence": merged,
                    "method": "llm" if any(r.direct for r in merged) else "implied",
                }
            )
            allowed.discard(index)
