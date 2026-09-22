import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.agents.matcher import Matcher
from app.agents.scorer import Scorer
from app.agents.skill_normalizer import SkillNormalizer
from app.core.config import Settings
from app.llm.client import LLMClient
from app.skills.taxonomy import load_taxonomy
from tests.fakes import FakeModel, InMemoryRepository
from tests.golden.cases import CASES, GoldenCase

pytestmark = pytest.mark.anyio

GOLDEN_DIR = Path(__file__).parent / "golden"
AS_OF = date(2026, 9, 1)


async def _run(case: GoldenCase) -> dict[str, Any]:
    taxonomy = load_taxonomy()
    llm = LLMClient(
        Settings(_env_file=None, openai_model_small="small-model"),
        InMemoryRepository(),
        FakeModel({"EvidenceJudgements": case.judgements}),
    )
    normalized = SkillNormalizer(taxonomy).run(case.profile, case.requirements)
    evidence = await Matcher(llm, taxonomy).run(case.profile, case.requirements, normalized)
    result = Scorer().run(case.requirements, evidence, case.profile, as_of=AS_OF)
    return {
        "fit_score": result.fit_score,
        "potential_score": result.potential_score,
        "requirements": [
            {
                "name": m.name,
                "skill_id": m.skill_id,
                "method": m.method,
                "resume_strength": m.resume_strength,
                "best_strength": m.best_strength,
                "bucket": m.bucket,
            }
            for m in result.matches
        ],
    }


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_golden(case: GoldenCase) -> None:
    path = GOLDEN_DIR / f"{case.name}.json"
    actual = await _run(case)
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(json.dumps(actual, indent=2) + "\n")
    assert actual == json.loads(path.read_text())


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_same_input_same_score_across_runs(case: GoldenCase) -> None:
    results = [await _run(case) for _ in range(5)]
    assert all(r == results[0] for r in results)
