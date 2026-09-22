-- Phase 0: core tables, RLS and private uploads bucket.
-- Later phases add analysis_results, interview_sets, interview_questions (pgvector),
-- learning_resources, llm_cache and llm_calls.

-- ---------------------------------------------------------------------------
-- profiles: one row per auth user, created automatically on sign-up
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles: read own" on public.profiles
  for select to authenticated using ((select auth.uid()) = id);
create policy "profiles: update own" on public.profiles
  for update to authenticated using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data ->> 'full_name');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- documents: resumes, supporting docs, JDs and pasted text
-- ---------------------------------------------------------------------------
create type public.document_kind as enum ('resume', 'supporting', 'jd', 'extra_text');

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  kind public.document_kind not null,
  filename text,
  storage_path text,          -- null for pasted text
  extracted_text text,
  text_hash text,             -- sha256 of normalized text, used for LLM caching
  created_at timestamptz not null default now()
);

create index documents_user_id_idx on public.documents (user_id);

alter table public.documents enable row level security;

create policy "documents: read own" on public.documents
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "documents: delete own" on public.documents
  for delete to authenticated using ((select auth.uid()) = user_id);
-- Inserts/updates go through the backend (service role), which validates files.

-- ---------------------------------------------------------------------------
-- analyses: one job-fit analysis run
-- ---------------------------------------------------------------------------
create type public.analysis_status as enum (
  'queued', 'parsing', 'extracting', 'scoring', 'advising', 'done', 'failed'
);

create table public.analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  resume_doc_id uuid references public.documents (id) on delete set null,
  jd_doc_id uuid references public.documents (id) on delete set null,
  supporting_doc_ids uuid[] not null default '{}',
  status public.analysis_status not null default 'queued',
  error text,
  fit_score smallint check (fit_score between 0 and 100),
  potential_score smallint check (potential_score between 0 and 100),
  scoring_version text,
  prompt_versions jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index analyses_user_id_created_at_idx on public.analyses (user_id, created_at desc);

alter table public.analyses enable row level security;

create policy "analyses: read own" on public.analyses
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "analyses: delete own" on public.analyses
  for delete to authenticated using ((select auth.uid()) = user_id);

create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger analyses_set_updated_at
  before update on public.analyses
  for each row execute function public.set_updated_at();

-- Frontend subscribes to status changes via Supabase Realtime.
alter publication supabase_realtime add table public.analyses;

-- ---------------------------------------------------------------------------
-- Storage: private uploads bucket, files stored under <user_id>/...
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'uploads', 'uploads', false, 5242880,
  array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain'
  ]
);

create policy "uploads: read own" on storage.objects
  for select to authenticated
  using (bucket_id = 'uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
