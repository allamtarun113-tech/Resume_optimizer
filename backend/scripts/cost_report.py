"""Average LLM cost per analysis, from the llm_calls table.

Run from backend/:  uv run python -m scripts.cost_report [--days 30]
Prices come from OPENAI_PRICE_INPUT_PER_M / OPENAI_PRICE_OUTPUT_PER_M (USD per 1M tokens).
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.supabase import _auth_headers
from app.reporting.costs import cost_report

PAGE = 1000


async def fetch_calls(days: int) -> list[dict[str, Any]]:
    settings = get_settings()
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    base = f"{settings.supabase_url.rstrip('/')}/rest/v1/llm_calls"
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=60, headers=_auth_headers(settings.supabase_service_role_key)
    ) as http:
        while True:
            response = await http.get(
                base,
                params={
                    "select": "analysis_id,agent,model,cached,input_tokens,output_tokens",
                    "created_at": f"gte.{since}",
                    "order": "id",
                    "limit": str(PAGE),
                    "offset": str(len(rows)),
                },
            )
            response.raise_for_status()
            page = response.json()
            rows += page
            if len(page) < PAGE:
                return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="LLM cost per analysis")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    settings = get_settings()
    rows = await fetch_calls(args.days)
    report = cost_report(
        rows,
        input_per_m=settings.openai_price_input_per_m,
        output_per_m=settings.openai_price_output_per_m,
        target_usd=settings.cost_target_per_analysis,
    )
    models = sorted({r["model"] for r in rows})
    print(f"Last {args.days} days · models: {', '.join(models) or '-'}")
    print(f"Analyses: {report.analyses} · LLM calls: {report.calls} ({report.cached_calls} cached)")
    print(
        f"Cost per analysis: average ${report.average_usd:.4f}, median ${report.median_usd:.4f}, "
        f"max ${report.max_usd:.4f} · total ${report.total_usd:.4f}"
    )
    for agent, usd in report.by_agent_usd.items():
        print(f"  {agent:24} ${usd:.4f}")
    verdict = "within" if report.within_target else "OVER"
    print(f"Target ${report.target_usd:.2f} per analysis: {verdict} target")


if __name__ == "__main__":
    asyncio.run(main())
