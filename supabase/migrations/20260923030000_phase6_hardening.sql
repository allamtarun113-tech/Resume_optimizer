-- Phase 6: security hardening and cost reporting.

-- The sign-up trigger function must not be callable through the REST API
-- (Supabase advisor 0028/0029). Triggers still fire without EXECUTE grants.
revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- Daily LLM usage per agent/model, for cost dashboards (SQL editor or service role).
create view public.llm_usage_daily
with (security_invoker = true) as
select
  date_trunc('day', created_at)::date as day,
  agent,
  model,
  count(*) as calls,
  count(*) filter (where cached) as cached_calls,
  sum(input_tokens) as input_tokens,
  sum(output_tokens) as output_tokens,
  count(distinct analysis_id) as analyses
from public.llm_calls
group by 1, 2, 3;

revoke all on public.llm_usage_daily from anon, authenticated;
grant select on public.llm_usage_daily to service_role;
