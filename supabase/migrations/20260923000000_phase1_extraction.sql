-- Phase 1: extraction results, LLM result cache and LLM call accounting.

-- ---------------------------------------------------------------------------
-- analysis_results: agent outputs for one analysis (filled in phase by phase)
-- ---------------------------------------------------------------------------
create table public.analysis_results (
  analysis_id uuid primary key references public.analyses (id) on delete cascade,
  student_profile jsonb,
  job_requirements jsonb,
  matches jsonb,
  suggestions jsonb,
  gaps jsonb,
  learning_path jsonb,
  created_at timestamptz not null default now()
);

alter table public.analysis_results enable row level security;

create policy "analysis_results: read own" on public.analysis_results
  for select to authenticated
  using (exists (
    select 1 from public.analyses a
    where a.id = analysis_id and a.user_id = (select auth.uid())
  ));

-- ---------------------------------------------------------------------------
-- llm_cache: structured LLM outputs keyed by
-- sha256(prompt name + prompt version + model + output schema + input)
-- ---------------------------------------------------------------------------
create table public.llm_cache (
  key text primary key,
  agent text not null,
  model text not null,
  prompt_version text not null,
  response jsonb not null,
  created_at timestamptz not null default now()
);

-- Backend-only (secret key). RLS on with no policies blocks anon/authenticated access.
alter table public.llm_cache enable row level security;

-- ---------------------------------------------------------------------------
-- llm_calls: one row per LLM call, including cache hits (cost accounting)
-- ---------------------------------------------------------------------------
create table public.llm_calls (
  id bigint generated always as identity primary key,
  agent text not null,
  model text not null,
  prompt_version text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cached boolean not null,
  latency_ms integer not null,
  analysis_id uuid references public.analyses (id) on delete set null,
  user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);

create index llm_calls_analysis_id_idx on public.llm_calls (analysis_id);
create index llm_calls_created_at_idx on public.llm_calls (created_at);

alter table public.llm_calls enable row level security;

-- ---------------------------------------------------------------------------
-- Grants for the Data API (explicit, in case the project does not auto-expose
-- new tables). RLS still applies to anon/authenticated.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on
  public.documents, public.analyses, public.analysis_results, public.llm_cache, public.llm_calls
  to service_role;
grant select, delete on public.documents, public.analyses to authenticated;
grant select on public.analysis_results to authenticated;
