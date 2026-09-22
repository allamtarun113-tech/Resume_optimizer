"""Cost per analysis from llm_calls rows. Pure functions (the script does the I/O)."""

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True)
class CostReport:
    analyses: int
    calls: int
    cached_calls: int
    total_usd: float
    average_usd: float
    median_usd: float
    max_usd: float
    by_agent_usd: dict[str, float]
    target_usd: float

    @property
    def within_target(self) -> bool:
        return self.average_usd <= self.target_usd


def call_cost(row: dict[str, Any], input_per_m: float, output_per_m: float) -> float:
    tokens_in, tokens_out = int(row["input_tokens"]), int(row["output_tokens"])
    return (tokens_in * input_per_m + tokens_out * output_per_m) / 1_000_000


def cost_report(
    rows: list[dict[str, Any]], *, input_per_m: float, output_per_m: float, target_usd: float
) -> CostReport:
    """Rows: llm_calls with analysis_id, agent, cached, input_tokens, output_tokens.
    Interview-prep calls count towards the analysis they belong to."""
    per_analysis: dict[str, float] = defaultdict(float)
    per_agent: dict[str, float] = defaultdict(float)
    for row in rows:
        cost = call_cost(row, input_per_m, output_per_m)
        per_agent[row["agent"]] += cost
        if row.get("analysis_id"):
            per_analysis[row["analysis_id"]] += cost
    costs = list(per_analysis.values())
    return CostReport(
        analyses=len(costs),
        calls=len(rows),
        cached_calls=sum(1 for r in rows if r["cached"]),
        total_usd=sum(per_agent.values()),
        average_usd=sum(costs) / len(costs) if costs else 0.0,
        median_usd=median(costs) if costs else 0.0,
        max_usd=max(costs, default=0.0),
        by_agent_usd=dict(sorted(per_agent.items(), key=lambda kv: -kv[1])),
        target_usd=target_usd,
    )
