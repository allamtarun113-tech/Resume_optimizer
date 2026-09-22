-- Phase 5: interview question corpus (pgvector), embedding cache, generated interview sets.

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- interview_questions: public-domain / permissively licensed questions from
-- allow-listed GitHub repos (ingestion/sources.yaml). Loaded offline.
-- ---------------------------------------------------------------------------
create table public.interview_questions (
  id uuid primary key default gen_random_uuid(),
  text text not null,
  text_hash text not null unique,          -- sha256 of normalized text (dedupe)
  category text not null check (category in ('technical', 'general', 'personal')),
  topics text[] not null default '{}',     -- taxonomy skill ids
  role_tags text[] not null default '{}',
  difficulty text check (difficulty in ('easy', 'medium', 'hard')),
  source_repo text not null,               -- "owner/repo"
  source_path text not null,
  source_url text not null,
  license text not null,
  embedding extensions.vector(1536) not null,
  created_at timestamptz not null default now()
);

create index interview_questions_category_idx on public.interview_questions (category);
create index interview_questions_topics_idx on public.interview_questions using gin (topics);
create index interview_questions_embedding_idx on public.interview_questions
  using hnsw (embedding extensions.vector_cosine_ops);

alter table public.interview_questions enable row level security;
create policy "interview_questions: public read" on public.interview_questions
  for select to anon, authenticated using (true);
grant select on public.interview_questions to anon, authenticated;
grant select, insert, update, delete on public.interview_questions to service_role;

-- Similarity search with optional metadata filters (called by the backend via RPC).
create function public.match_interview_questions(
  query_embedding extensions.vector(1536),
  match_count int default 10,
  filter_category text default null,
  filter_topics text[] default null,
  filter_roles text[] default null
)
returns table (
  id uuid, text text, category text, topics text[], role_tags text[], difficulty text,
  source_repo text, source_path text, source_url text, license text, similarity float
)
language sql stable
set search_path = public, extensions
as $$
  select q.id, q.text, q.category, q.topics, q.role_tags, q.difficulty,
         q.source_repo, q.source_path, q.source_url, q.license,
         1 - (q.embedding <=> query_embedding) as similarity
  from public.interview_questions q
  where (filter_category is null or q.category = filter_category)
    and (filter_topics is null or q.topics && filter_topics)
    and (filter_roles is null or q.role_tags && filter_roles)
  order by q.embedding <=> query_embedding
  limit least(match_count, 50);
$$;

revoke execute on function public.match_interview_questions from public, anon, authenticated;
grant execute on function public.match_interview_questions to service_role;

-- ---------------------------------------------------------------------------
-- embedding_cache: query embeddings keyed by sha256(model + text)
-- ---------------------------------------------------------------------------
create table public.embedding_cache (
  key text primary key,
  model text not null,
  embedding extensions.vector(1536) not null,
  created_at timestamptz not null default now()
);
alter table public.embedding_cache enable row level security;
grant select, insert, update, delete on public.embedding_cache to service_role;

-- ---------------------------------------------------------------------------
-- interview_sets: one generated "Prepare Me for Interview" set per analysis
-- ---------------------------------------------------------------------------
create table public.interview_sets (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null unique references public.analyses (id) on delete cascade,
  questions jsonb not null,
  created_at timestamptz not null default now()
);

alter table public.interview_sets enable row level security;
create policy "interview_sets: read own" on public.interview_sets
  for select to authenticated
  using (exists (
    select 1 from public.analyses a
    where a.id = analysis_id and a.user_id = (select auth.uid())
  ));
grant select on public.interview_sets to authenticated;
grant select, insert, update, delete on public.interview_sets to service_role;
